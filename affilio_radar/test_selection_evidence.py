import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import affilio_radar as radar
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

    def test_same_family_candidates_are_blocked_before_primary_and_backup_selection(self):
        products = [
            {
                "product_id": f"dkp-family-{index}",
                "product_url": f"https://www.digikala.com/product/dkp-family-{index}/",
                "title": title,
                "brand": brand,
                "availability": "in_stock",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": discount,
                "savings_toman": 500_000,
                "catalog_category_id": "812",
                "catalog_category_name": "پاوربانک",
                "catalog_category_ids": ["812"],
                "catalog_best_selling_category_id": "812",
                "catalog_best_selling_category_name": "پاوربانک",
            }
            for index, (title, brand, discount) in enumerate((
                ("پاوربانک ۲۰۰۰۰ میلی آمپر مدل A", "Brand A", 90),
                ("شارژر همراه ۱۰۰۰۰ میلی آمپر مدل B", "Brand B", 85),
                ("پاوربانک باریک ۵۰۰۰ میلی آمپر مدل C", "Brand C", 80),
            ), start=1)
        ]
        state = {"published": {}, "recent_publications": []}
        with (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
        ):
            selected, floor, quality = radar.select_discount_fallback_candidates(
                products, state, now=self.now, include_fallback_bands=True
            )
        self.assertEqual(floor, 1)
        self.assertEqual(len(quality), 3)
        self.assertEqual(
            [row["product_id"] for row in selected],
            ["dkp-family-1"],
            "only the highest-ranked family member may pass as primary or backup",
        )
        rejected = radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS["rejection_events"]
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all("family_repeat" in row["reasons"] for row in rejected))
        self.assertEqual({row["catalog_category_id"] for row in rejected}, {"812"})
        self.assertTrue(all(row["catalog_category_name"] == "پاوربانک" for row in rejected))

    def test_publication_classifier_uses_digikala_category_and_application(self):
        automotive = {
            "title": "چراغ شارژی مدل آزمایشی",
            "catalog_best_selling_category_id": "91",
            "catalog_best_selling_category_name": "چراغ خودرو و تجهیزات روشنایی",
        }
        travel = {
            "title": "چراغ شارژی مدل آزمایشی",
            "catalog_best_selling_category_id": "92",
            "catalog_best_selling_category_name": "چراغ کمپینگ و کوهنوردی",
        }
        self.assertEqual(radar._publication_use_case_group(automotive), "automotive")
        self.assertEqual(radar._publication_use_case_group(travel), "outdoor_travel")
        auto_category, auto_family, _ = radar._publication_diversity_group(automotive)
        travel_category, travel_family, _ = radar._publication_diversity_group(travel)
        self.assertNotEqual(auto_category, travel_category)
        self.assertNotEqual(auto_family, travel_family)
        self.assertIn("digikala_category:91", auto_family)
        self.assertIn("digikala_category:92", travel_family)

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
            "product_id": "dkp-lifetime",
            "review_count": 250_000,
            "rating": 4.9,
            "historical_popularity_score": 100,
            "demand_score": 100,
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": self.now.isoformat(),
        }
        self.assertFalse(radar.has_actionable_demand_signal(lifetime_reviews_only, now=self.now))
        self.assertEqual(
            radar._fresh_digikala_bestseller_evidence(lifetime_reviews_only, self.now)["best_rank_across_categories"],
            1,
        )

    def test_fresh_review_growth_outranks_a_larger_markdown_when_no_bestseller_rank_exists(self):
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
            radar.deal_sort_key(lower_discount_with_growth, now=self.now),
            radar.deal_sort_key(high_discount_without_growth, now=self.now),
        )
        self.assertGreater(
            radar.discovery_queue_sort_key(lower_discount_with_growth, now=self.now),
            radar.discovery_queue_sort_key(high_discount_without_growth, now=self.now),
        )

    def test_direct_bestseller_rank_precedes_review_growth_and_deal_value(self):
        top_seller = {
            "product_id": "dkp-top-seller",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 2,
            "catalog_rank_observed_at": self.now.isoformat(),
            "discount_percent": 10,
            "savings_toman": 100_000,
            "review_count": 25,
            "rating": 4.0,
        }
        review_spike = {
            "product_id": "dkp-review-spike",
            "discount_percent": 90,
            "savings_toman": 9_000_000,
            "review_count": 100,
            **self._verified_review_growth(),
        }
        self.assertGreater(
            radar.deal_sort_key(top_seller, now=self.now),
            radar.deal_sort_key(review_spike, now=self.now),
        )

        stale_bestseller = {
            **top_seller,
            "catalog_rank_observed_at": (
                self.now - timedelta(hours=radar.DIGIKALA_BESTSELLER_MAX_AGE_HOURS + 1)
            ).isoformat(),
        }
        self.assertFalse(radar._fresh_digikala_bestseller_evidence(stale_bestseller, self.now))
        self.assertGreater(
            radar.deal_sort_key(review_spike, now=self.now),
            radar.deal_sort_key(stale_bestseller, now=self.now),
        )

    def test_discount_is_the_final_tiebreak_after_equal_demand_evidence(self):
        base = {
            "product_id": "dkp-equal-demand",
            "review_count": 500,
            "rating": 4.5,
            **self._verified_review_growth(),
        }
        larger_discount = {**base, "discount_percent": 70, "savings_toman": 700_000}
        smaller_discount = {**base, "discount_percent": 20, "savings_toman": 200_000}
        self.assertGreater(
            radar.deal_sort_key(larger_discount, now=self.now),
            radar.deal_sort_key(smaller_discount, now=self.now),
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


if __name__ == "__main__":
    unittest.main()
