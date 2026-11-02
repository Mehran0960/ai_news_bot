import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import affilio_radar as radar


class OfferChinSelectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 16, 30, tzinfo=timezone.utc)

    def test_recent_review_growth_must_meet_threshold_and_be_fresh(self):
        record = {
            "current_demand_verified": True,
            "recent_review_growth_7d": radar.CURRENT_DEMAND_MIN_REVIEW_GROWTH,
            "demand_window_hours": radar.CURRENT_DEMAND_MIN_OBSERVATION_HOURS,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        self.assertTrue(radar.has_actionable_demand_signal(record, now=self.now))

        below_threshold = dict(record)
        below_threshold["recent_review_growth_7d"] = max(
            0, radar.CURRENT_DEMAND_MIN_REVIEW_GROWTH - 1
        )
        self.assertFalse(radar.has_actionable_demand_signal(below_threshold, now=self.now))

        stale = dict(record)
        stale["demand_observed_at"] = (
            self.now - timedelta(hours=radar.CURRENT_DEMAND_MAX_SIGNAL_AGE_HOURS + 1)
        ).isoformat()
        self.assertFalse(radar.has_actionable_demand_signal(stale, now=self.now))

    def test_fresh_digikala_bestseller_rank_is_actionable_but_stale_or_outside_top60_is_not(self):
        record = {
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 12,
            "catalog_rank_observed_at": (self.now - timedelta(hours=2)).isoformat(),
        }
        self.assertTrue(radar.has_actionable_demand_signal(record, now=self.now))

        outside_top60 = dict(record, catalog_best_selling_rank=61)
        self.assertFalse(radar.has_actionable_demand_signal(outside_top60, now=self.now))

        stale = dict(
            record,
            catalog_rank_observed_at=(
                self.now - timedelta(hours=radar.BEST_SELLING_MAX_AGE_HOURS + 1)
            ).isoformat(),
        )
        self.assertFalse(radar.has_actionable_demand_signal(stale, now=self.now))

        wrong_sort = dict(record, catalog_sort_mode="price")
        self.assertFalse(radar.has_actionable_demand_signal(wrong_sort, now=self.now))

    def test_stale_or_missing_price_evidence_cannot_qualify_as_verified_value(self):
        base = {"discount_percent": 14, "savings_toman": 140_000}
        self.assertFalse(radar.has_attractive_discount_value(base, now=self.now))
        # Even a very large displayed markdown is not proof when its reference price
        # has not been independently verified.
        self.assertFalse(
            radar.has_attractive_discount_value(
                dict(base, discount_percent=85, savings_toman=850_000),
                now=self.now,
            )
        )

        stale_history = {
            **base,
            "discount_percent": 10,
            "history_status": "verified",
            "historical_deal_eligible": True,
            "history_checked_at": (
                self.now - timedelta(hours=radar.PRICE_HISTORY_RECHECK_HOURS + 1)
            ).isoformat(),
        }
        self.assertFalse(radar.has_attractive_discount_value(stale_history, now=self.now))

        fresh_history_reject = {
            **base,
            "discount_percent": 80,
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": (self.now - timedelta(hours=2)).isoformat(),
        }
        self.assertFalse(
            radar.has_attractive_discount_value(fresh_history_reject, now=self.now)
        )

    def test_fresh_independent_price_comparisons_can_prove_value(self):
        fresh_history = {
            "discount_percent": 5,
            "savings_toman": 100_000,
            "history_status": "verified",
            "historical_deal_eligible": True,
            "history_checked_at": (self.now - timedelta(hours=1)).isoformat(),
        }
        self.assertTrue(radar.has_attractive_discount_value(fresh_history, now=self.now))

        fresh_market = {
            "discount_percent": 5,
            "savings_toman": 100_000,
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": radar.VERIFIED_MARKET_MIN_ADVANTAGE_PERCENT,
            "market_price_checked_at": (self.now - timedelta(hours=1)).isoformat(),
        }
        self.assertTrue(radar.has_attractive_discount_value(fresh_market, now=self.now))

        stale_market = dict(
            fresh_market,
            discount_percent=14,
            market_price_checked_at=(
                self.now - timedelta(hours=radar.MARKET_PRICE_RECHECK_HOURS + 1)
            ).isoformat(),
        )
        self.assertFalse(radar.has_attractive_discount_value(stale_market, now=self.now))

    def test_selector_hands_off_live_discounts_in_demand_first_order(self):
        def candidate(pid, discount, rank, market_verified=False):
            row = {
                "product_id": pid,
                "product_url": f"https://www.digikala.com/product/{pid}/",
                "title": f"محصول آزمایشی {pid}",
                "availability": "in_stock",
                "current_price": 400_000,
                "original_price": 500_000,
                "discount_percent": discount,
                "savings_toman": 500_000 - 500_000 * (100 - discount) // 100,
                "image_url": "https://example.com/product.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2F"
                                 + pid + "%2F",
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": rank,
                "catalog_rank_observed_at": self.now.isoformat(),
            }
            if market_verified:
                row.update({
                    "market_status": "verified",
                    "market_reference_kind": "seller_median",
                    "market_price_advantage_pct": radar.VERIFIED_MARKET_MIN_ADVANTAGE_PERCENT,
                    "market_price_checked_at": self.now.isoformat(),
                })
            return row

        good = candidate("dkp-101", 20, 12, market_verified=True)
        weak_demand = candidate("dkp-102", 80, 61, market_verified=True)
        weak_value = candidate("dkp-103", 85, 8)

        with (
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "is_market_value_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(
                radar,
                "_order_candidates_by_primary_rank",
                side_effect=lambda records, **_kwargs: list(records),
            ),
        ):
            selected, _floor, _quality_pool = radar.select_discount_fallback_candidates(
                [weak_demand, weak_value, good],
                {},
                now=self.now,
            )

        self.assertEqual(
            [row["product_id"] for row in selected],
            ["dkp-103", "dkp-101", "dkp-102"],
        )


if __name__ == "__main__":
    unittest.main()