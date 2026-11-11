import unittest
from datetime import datetime, timedelta, timezone

from cycle_offer_pool import (
    BASE_PUBLICATION_INTERVAL_SECONDS,
    cycle_offer_candidates,
    mark_cycle_offer_consumed,
    mark_cycle_offer_rejected,
    merge_cycle_offers,
    pool_remaining_count,
    pool_runtime_projection,
    set_pool_dispatchable_count,
)


class CycleOfferPoolTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
        self.started = self.now - timedelta(hours=34)
        self.completed = self.now - timedelta(hours=1)

    def item(self, pid, price, rank=5, *, category="100", now=None):
        observed = now or self.now
        original = int(price * 1.25)
        return {
            "product_id": pid,
            "title": f"محصول آزمایشی {pid}",
            "current_price": price,
            "original_price": original,
            "discount_percent": 20,
            "savings_toman": original - price,
            "catalog_category_ids": [category],
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": rank,
            "catalog_rank_observed_at": observed.isoformat(),
            "selection_bestseller_category_count": 1,
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 6,
            "market_price_checked_at": observed.isoformat(),
        }

    def merge(self, state, items, *, completed=None, started=None):
        return merge_cycle_offers(
            state,
            items,
            cycle_completed_at=completed or self.completed.isoformat(),
            cycle_started_at=started or self.started.isoformat(),
            now=self.now,
        )

    def test_pool_boundary_rejects_missing_or_stale_demand_and_value_proof(self):
        no_value = self.item("dkp-10001", 100_000)
        no_value.pop("market_status")
        no_value.pop("market_reference_kind")
        no_value.pop("market_price_advantage_pct")
        no_value.pop("market_price_checked_at")
        no_demand = self.item("dkp-10002", 120_000)
        no_demand.pop("catalog_best_selling_rank")
        no_demand.pop("catalog_rank_observed_at")
        stale_value = self.item(
            "dkp-10003", 140_000, now=self.now - timedelta(hours=25)
        )
        state = {}
        result = self.merge(state, [no_value, no_demand, stale_value])
        self.assertEqual(result["added"], 0)
        self.assertEqual(pool_remaining_count(state), 0)

    def test_verified_fresh_review_growth_can_satisfy_demand_without_bestseller_rank(self):
        item = self.item("dkp-10006", 100_000)
        item.pop("catalog_best_selling_rank")
        item.pop("catalog_rank_observed_at")
        item.update({
            "current_demand_verified": True,
            "recent_review_growth_window": 5,
            "recent_review_growth_7d": 5,
            "demand_window_hours": 8,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        })
        state = {}
        result = self.merge(state, [item])
        self.assertEqual(result["added"], 1)
        ranked = cycle_offer_candidates(state, now=self.now)
        self.assertEqual(ranked[0]["product_id"], "dkp-10006")

    def test_unverified_review_growth_cannot_satisfy_demand(self):
        item = self.item("dkp-10007", 100_000)
        item.pop("catalog_best_selling_rank")
        item.pop("catalog_rank_observed_at")
        item.update({
            "current_demand_verified": False,
            "recent_review_growth_window": 10,
            "recent_review_growth_7d": 10,
            "demand_window_hours": 8,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        })
        state = {}
        self.merge(state, [item])
        self.assertEqual(pool_remaining_count(state), 0)

    def test_fresh_historical_price_proof_also_qualifies(self):
        item = self.item("dkp-10004", 100_000)
        item.update({
            "history_status": "verified",
            "historical_deal_eligible": True,
            "history_checked_at": self.now.isoformat(),
            "market_status": "not_checked",
            "market_reference_kind": "",
            "market_price_advantage_pct": None,
        })
        state = {}
        result = self.merge(state, [item])
        self.assertEqual(result["added"], 1)
        self.assertEqual(pool_remaining_count(state), 1)

    def test_fresh_negative_history_verdict_cannot_be_overridden_by_market_proof(self):
        contradicted = self.item("dkp-10005", 100_000)
        contradicted.update({
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": self.now.isoformat(),
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 15,
            "market_price_checked_at": self.now.isoformat(),
        })
        state = {}
        self.merge(state, [contradicted])
        self.assertEqual(pool_remaining_count(state), 0)

    def test_affordability_percentile_prefers_lower_price_within_category(self):
        state = {}
        items = [
            self.item("dkp-10101", 100_000),
            self.item("dkp-10102", 200_000),
            self.item("dkp-10103", 300_000),
            self.item("dkp-10104", 400_000),
            self.item("dkp-10105", 500_000),
        ]
        self.merge(state, items)
        ranked = cycle_offer_candidates(state, now=self.now)
        self.assertEqual(ranked[0]["product_id"], "dkp-10101")
        by_id = {row["product_id"]: row for row in ranked}
        self.assertEqual(by_id["dkp-10101"]["selection_affordability_tier"], "accessible")
        self.assertEqual(by_id["dkp-10105"]["selection_affordability_tier"], "premium")
        self.assertGreater(
            by_id["dkp-10101"]["selection_affordability_percentile"],
            by_id["dkp-10105"]["selection_affordability_percentile"],
        )

    def test_fresher_stronger_demand_precedes_affordability(self):
        state = {}
        premium_top_rank = self.item("dkp-10201", 900_000, rank=1)
        affordable_lower_rank = self.item("dkp-10202", 100_000, rank=5)
        self.merge(state, [premium_top_rank, affordable_lower_rank])
        ranked = cycle_offer_candidates(state, now=self.now)
        self.assertEqual(ranked[0]["product_id"], "dkp-10201")

    def test_cross_category_bestseller_breadth_precedes_affordability_and_markdown(self):
        state = {}
        narrow = self.item("dkp-10311", 100_000, rank=5, category="101")
        broad = self.item("dkp-10312", 300_000, rank=5, category="102")
        narrow["selection_bestseller_category_count"] = 1
        broad["selection_bestseller_category_count"] = 4
        # Both have the same fresh rank; the broader demand footprint is the next signal.
        self.merge(state, [narrow, broad])
        ranked = cycle_offer_candidates(state, now=self.now)
        self.assertEqual(ranked[0]["product_id"], "dkp-10312")
        self.assertEqual(ranked[0]["selection_generality_tier"], "broad")
        self.assertEqual(ranked[1]["selection_generality_tier"], "single_category")

    def test_taxonomy_breadth_is_only_weak_generality_context(self):
        state = {}
        taxonomy_only = self.item("dkp-10321", 100_000, rank=5)
        taxonomy_only["catalog_category_ids"] = ["101", "102", "103", "104"]
        taxonomy_only.pop("selection_bestseller_category_count", None)
        verified_single = self.item("dkp-10322", 100_000, rank=5)
        verified_single["selection_bestseller_category_count"] = 1
        self.merge(state, [taxonomy_only, verified_single])
        ranked = cycle_offer_candidates(state, now=self.now)
        by_id = {row["product_id"]: row for row in ranked}
        self.assertEqual(by_id["dkp-10321"]["selection_generality_tier"], "taxonomy_only")
        self.assertEqual(by_id["dkp-10322"]["selection_generality_tier"], "single_category")
        self.assertGreater(
            by_id["dkp-10322"]["selection_generality_score"],
            by_id["dkp-10321"]["selection_generality_score"],
        )

    def test_consumed_and_rejected_items_do_not_reenter_selection(self):
        state = {}
        items = [
            self.item("dkp-10301", 100_000),
            self.item("dkp-10302", 200_000),
            self.item("dkp-10303", 300_000),
        ]
        self.merge(state, items)
        mark_cycle_offer_consumed(state, "dkp-10301", now=self.now)
        mark_cycle_offer_rejected(state, "dkp-10302", "live_price_changed", now=self.now)
        remaining = {row["product_id"] for row in cycle_offer_candidates(state, now=self.now)}
        self.assertEqual(remaining, {"dkp-10303"})
        self.assertEqual(pool_remaining_count(state), 1)

    def test_new_completed_cycle_replaces_previous_pool_and_consumption_ledger(self):
        state = {}
        self.merge(state, [self.item("dkp-10401", 100_000)])
        mark_cycle_offer_consumed(state, "dkp-10401", now=self.now)
        next_completed = (self.now + timedelta(hours=1)).isoformat()
        next_started = (self.now - timedelta(hours=33)).isoformat()
        self.merge(
            state,
            [self.item("dkp-10402", 200_000)],
            completed=next_completed,
            started=next_started,
        )
        pool = state["cycle_offer_pool"]
        self.assertEqual(pool["cycle_completed_at"], next_completed)
        self.assertEqual(pool["consumed_ids"], [])
        self.assertEqual([row["product_id"] for row in pool["items"]], ["dkp-10402"])

    def test_adaptive_interval_keeps_27_minute_floor_and_spreads_small_pool(self):
        state = {}
        items = [
            self.item(f"dkp-{10500 + index}", 100_000 + index * 1_000, rank=5)
            for index in range(100)
        ]
        self.merge(state, items)
        set_pool_dispatchable_count(state, 100, now=self.now)
        initial = pool_runtime_projection(state, now=self.now)
        self.assertEqual(initial["interval_seconds"], BASE_PUBLICATION_INTERVAL_SECONDS)
        self.assertEqual(initial["available_count"], 100)

        for item in items[:95]:
            mark_cycle_offer_consumed(state, item["product_id"], now=self.now)
        set_pool_dispatchable_count(state, 5, now=self.now)
        spread = pool_runtime_projection(state, now=self.now)
        self.assertEqual(spread["available_count"], 5)
        self.assertGreater(spread["interval_seconds"], BASE_PUBLICATION_INTERVAL_SECONDS)

    def test_active_queued_pool_item_remains_dispatchable_after_selector_returns_zero(self):
        state = {}
        item = self.item("dkp-10601", 100_000)
        self.merge(state, [item])
        state["content_delivery_queue"] = {
            "dkp-10601": {"status": "queued"}
        }
        set_pool_dispatchable_count(state, 0, now=self.now)
        projection = pool_runtime_projection(state, now=self.now)
        self.assertEqual(projection["available_count"], 1)

    def test_legacy_active_queue_is_not_stranded_during_rollout(self):
        state = {
            "content_delivery_queue": {
                "dkp-10701": {"status": "queued"}
            }
        }
        projection = pool_runtime_projection(state, now=self.now)
        self.assertEqual(projection["available_count"], 1)


if __name__ == "__main__":
    unittest.main()
