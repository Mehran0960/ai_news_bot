import unittest
from datetime import datetime, timedelta, timezone

import affilio_radar as radar
from demand_shadow import (
    annotate_shadow_demand_evidence,
    build_torob_trends_snapshot,
    normalize_search_tokens,
    torob_trends_snapshot_is_fresh,
)
from publisher import _eligible_fallback_candidates


class OfferChinSelectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def _verified_review_growth(self, **overrides):
        record = {
            "current_demand_verified": True,
            "recent_review_growth_window": 6,
            "recent_review_growth_7d": 6,
            "demand_window_hours": 6,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        record.update(overrides)
        return record

    def test_review_growth_is_only_an_indirect_fresh_proxy_not_sales(self):
        record = self._verified_review_growth()
        self.assertTrue(radar.has_current_demand_signal(record, now=self.now))
        self.assertTrue(radar.has_actionable_demand_signal(record, now=self.now))

        stale = dict(
            record,
            demand_observed_at=(self.now - timedelta(hours=radar.CURRENT_DEMAND_MAX_SIGNAL_AGE_HOURS + 1)).isoformat(),
        )
        self.assertFalse(radar.has_actionable_demand_signal(stale, now=self.now))

        lifetime_reviews_only = {
            "review_count": 250_000,
            "rating": 4.9,
            "historical_popularity_score": 100,
            "demand_score": 100,
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": self.now.isoformat(),
        }
        self.assertFalse(radar.has_actionable_demand_signal(lifetime_reviews_only, now=self.now))

    def test_discount_and_savings_always_beat_review_growth_proxy(self):
        high_discount_without_growth = {
            "product_id": "dkp-high-discount",
            "discount_percent": 85,
            "savings_toman": 8_500_000,
            "review_count": 0,
        }
        lower_discount_with_growth = {
            "product_id": "dkp-review-growth",
            "discount_percent": 18,
            "savings_toman": 180_000,
            "review_count": 50,
            **self._verified_review_growth(),
        }
        self.assertGreater(
            radar.deal_sort_key(high_discount_without_growth, now=self.now),
            radar.deal_sort_key(lower_discount_with_growth, now=self.now),
        )
        self.assertGreater(
            radar.discovery_queue_sort_key(high_discount_without_growth, now=self.now),
            radar.discovery_queue_sort_key(lower_discount_with_growth, now=self.now),
        )

    def test_fresh_review_growth_is_used_only_after_both_discount_keys_tie(self):
        no_growth = {
            "product_id": "dkp-no-growth",
            "discount_percent": 70,
            "savings_toman": 700_000,
            "review_count": 900_000,
            "rating": 5.0,
            "demand_score": 999,
        }
        with_growth = {
            "product_id": "dkp-growth",
            "discount_percent": 70,
            "savings_toman": 700_000,
            "review_count": 1,
            **self._verified_review_growth(),
        }
        self.assertGreater(
            radar.deal_sort_key(with_growth, now=self.now),
            radar.deal_sort_key(no_growth, now=self.now),
        )

        lower_savings_even_with_growth = {
            **with_growth,
            "product_id": "dkp-lower-savings",
            "savings_toman": 699_999,
        }
        self.assertGreater(
            radar.deal_sort_key(no_growth, now=self.now),
            radar.deal_sort_key(lower_savings_even_with_growth, now=self.now),
        )

    def test_fresh_bestseller_rank_never_counts_as_review_growth_or_sales(self):
        bestseller_only = {
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": self.now.isoformat(),
            "review_count": 25_000,
            "rating": 4.9,
        }
        self.assertFalse(radar.has_actionable_demand_signal(bestseller_only, now=self.now))

    def test_positive_market_or_history_confirmation_is_not_required(self):
        product = {
            "product_id": "dkp-1234567",
            "product_url": "https://www.digikala.com/product/dkp-1234567/",
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 900_000,
            "original_price": 1_000_000,
            "discount_percent": 10,
            "savings_toman": 100_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1234567%2F",
            "selection_discount_floor": 1,
            "publication_policy": "discount_first_review_growth_tiebreak_v3",
        }
        # No review-growth or independent market/history evidence is present.
        self.assertTrue(radar.is_discount_publish_eligible(product, minimum_discount_percent=1, now=self.now))
        eligible = _eligible_fallback_candidates([product], self.now)
        self.assertEqual([row["product_id"] for row in eligible], ["dkp-1234567"])

    def test_fresh_verified_contradictory_history_can_veto_but_stale_history_cannot(self):
        base = {
            "product_id": "dkp-history-check",
            "product_url": "https://www.digikala.com/product/dkp-1234567/",
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 900_000,
            "original_price": 1_000_000,
            "discount_percent": 10,
            "savings_toman": 100_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1234567%2F",
        }
        fresh_reject = {
            **base,
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": self.now.isoformat(),
        }
        self.assertFalse(radar.is_discount_publish_eligible(fresh_reject, minimum_discount_percent=1, now=self.now))

        stale_reject = {
            **base,
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": (self.now - timedelta(hours=radar.PRICE_HISTORY_RECHECK_HOURS + 1)).isoformat(),
        }
        self.assertTrue(radar.is_discount_publish_eligible(stale_reject, minimum_discount_percent=1, now=self.now))

    def test_price_math_must_match_and_default_floor_is_any_positive_markdown(self):
        valid = {
            "discount_percent": 10,
            "savings_toman": 100_000,
            "current_price": 900_000,
            "original_price": 1_000_000,
        }
        self.assertTrue(radar.has_meaningful_discount(valid))
        self.assertFalse(radar.has_meaningful_discount({**valid, "discount_percent": 11}))
        self.assertFalse(radar.has_meaningful_discount({**valid, "savings_toman": 99_000}))
        self.assertTrue(radar.has_meaningful_discount({
            "discount_percent": 1,
            "savings_toman": 10_000,
            "current_price": 990_000,
            "original_price": 1_000_000,
        }))


    def test_torob_trend_snapshot_deduplicates_without_reordering_source_ranks(self):
        snapshot = build_torob_trends_snapshot(
            {
                "trends": [
                    {"query": "هندزفری بلوتوثی", "category_id": "11",
                     "sample": {"name_fa": "هندزفری بلوتوثی مدل TWS X"}},
                    {"query": "هندزفری بلوتوثی", "category_id": "12",
                     "sample": {"name_fa": "مدل تکراری"}},
                    {"query": "جارو شارژی", "category_id": "13",
                     "sample": {"name_fa": "جارو شارژی مدل نمونه"}},
                ]
            },
            self.now,
        )
        self.assertEqual(snapshot["count"], 2)
        self.assertEqual(snapshot["trends"][0]["rank"], 1)
        self.assertEqual(snapshot["trends"][1]["rank"], 3)
        self.assertEqual(snapshot["trends"][0]["category_id"], "11")
        self.assertTrue(torob_trends_snapshot_is_fresh(snapshot, self.now))

    def test_torob_search_normalization_handles_arabic_characters_and_persian_digits(self):
        tokens = normalize_search_tokens("هندزفری بلوتوثي مدل X ۱۲۳")
        self.assertIn("هندزفری", tokens)
        self.assertIn("بلوتوثی", tokens)
        self.assertIn("123", tokens)
        self.assertNotIn("مدل", tokens)

    def test_shadow_evidence_requires_fresh_bestseller_rank_and_specific_torob_match(self):
        snapshot = build_torob_trends_snapshot(
            {
                "trends": [
                    {"query": "هندزفری بلوتوثی", "category_id": "55",
                     "sample": {"name_fa": "هندزفری بلوتوثی مدل TWS X"}}
                ]
            },
            self.now - timedelta(minutes=5),
        )
        product = {
            "product_id": "dkp-12345",
            "title": "هندزفری بلوتوثی مدل TWS X با کیس شارژ",
            "discount_percent": 20,
            "current_price": 900_000,
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 8,
            "catalog_best_selling_category_id": "211",
            "catalog_best_selling_category_name": "هدفون و هندزفری",
            "catalog_rank_observed_at": (self.now - timedelta(hours=2)).isoformat(),
        }
        unrelated = {
            "product_id": "dkp-12346",
            "title": "جارو شارژی مدل نمونه",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 4,
            "catalog_best_selling_category_id": "127",
            "catalog_best_selling_category_name": "لوازم خانه",
            "catalog_rank_observed_at": (self.now - timedelta(hours=2)).isoformat(),
        }
        report = annotate_shadow_demand_evidence([product, unrelated], snapshot, self.now)
        evidence = product["shadow_demand_evidence"]
        self.assertEqual(evidence["evidence_level"], "cross_source")
        self.assertEqual(evidence["digikala_bestseller"]["rank"], 8)
        self.assertEqual(evidence["torob_trend"]["rank"], 1)
        self.assertEqual(unrelated["shadow_demand_evidence"]["evidence_level"], "digikala_bestseller_only")
        self.assertEqual(report["evidence_counts"]["cross_source"], 1)
        self.assertFalse(report["production_ranking_affected"])
        self.assertEqual(report["ranking_method"], "transparent_evidence_tiers_no_weighted_score")

    def test_shadow_evidence_rejects_stale_digikala_rank_and_stale_torob_snapshot(self):
        stale_snapshot = build_torob_trends_snapshot(
            {"trends": [{"query": "هندزفری بلوتوثی"}]},
            self.now - timedelta(hours=2),
        )
        self.assertFalse(torob_trends_snapshot_is_fresh(stale_snapshot, self.now))
        product = {
            "product_id": "dkp-12347",
            "title": "هندزفری بلوتوثی مدل TWS X",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_best_selling_category_id": "211",
            "catalog_best_selling_category_name": "هدفون",
            "catalog_rank_observed_at": (self.now - timedelta(hours=30)).isoformat(),
        }
        report = annotate_shadow_demand_evidence([product], stale_snapshot, self.now)
        self.assertEqual(
            product["shadow_demand_evidence"]["evidence_level"],
            "no_verified_demand_signal",
        )
        self.assertEqual(report["evidence_counts"]["no_verified_demand_signal"], 1)
        self.assertEqual(report["torob"]["status"], "unavailable_or_stale")

    def test_review_growth_remains_explicitly_an_indirect_demand_proxy(self):
        product = {
            "product_id": "snp-123456",
            "title": "وسیله کاربردی مدل آزمایشی",
            "current_demand_verified": True,
            "recent_review_growth_window": 6,
            "demand_window_hours": 12,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "snappshop_recent_review_growth",
        }
        report = annotate_shadow_demand_evidence([product], None, self.now)
        self.assertEqual(
            product["shadow_demand_evidence"]["evidence_level"],
            "review_growth_proxy_only",
        )
        self.assertEqual(report["evidence_counts"]["review_growth_proxy_only"], 1)
        self.assertIn(
            "not units sold",
            report["cross_category_comparability"]["review_growth"],
        )



if __name__ == "__main__":
    unittest.main()
