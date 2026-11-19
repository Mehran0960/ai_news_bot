from __future__ import annotations

import unittest
from datetime import datetime, timezone

from offerchin_four_factor import (
    POLICY_VERSION,
    apply_four_factor_scores,
    discount_attractiveness_score,
    discount_publish_gate,
    four_factor_sort_key,
    generality_score,
    harmonic_mean,
    infer_use_case_group,
)


class OfferChinThreeFactorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

    def _score(self, rows, independent=None):
        independent = independent or set()
        return apply_four_factor_scores(
            rows,
            live_demand_score_fn=lambda row: row.get("test_live_demand", 80),
            use_case_group_fn=lambda row: row.get("test_group", "kitchen_food"),
            discount_verified_fn=lambda row: row.get("product_id") in independent,
            now=self.now,
        )

    def _deal(self, product_id="dkp-test", price=950000):
        return {
            "product_id": product_id,
            "current_price": price,
            "original_price": price + 500000,
            "discount_percent": round(100 * 500000 / (price + 500000)),
            "savings_toman": 500000,
            "test_live_demand": 80,
            "test_group": "grocery_food",
        }

    def test_low_percentage_and_low_savings_are_rejected_without_independent_price_evidence(self):
        row = {
            "current_price": 9_500_000, "original_price": 10_000_000,
            "discount_percent": 5, "savings_toman": 500_000,
        }
        eligible, score, evidence = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)
        self.assertLess(score, 40)
        self.assertEqual(evidence, "live_retailer_markdown_only")

    def test_even_a_large_retailer_markdown_cannot_pass_without_independent_evidence(self):
        row = {
            "current_price": 100_000,
            "original_price": 1_000_000,
            "discount_percent": 90,
            "savings_toman": 900_000,
        }
        eligible, score, evidence = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)
        self.assertGreaterEqual(score, 40)
        self.assertEqual(evidence, "live_retailer_markdown_only")

    def test_small_percentage_can_pass_only_when_independently_verified_and_savings_are_real(self):
        row = {
            "current_price": 9_500_000, "original_price": 10_000_000,
            "discount_percent": 5, "savings_toman": 500_000,
        }
        eligible, score, evidence = discount_publish_gate(row, independently_verified=True)
        self.assertTrue(eligible)
        self.assertGreaterEqual(score, 40)
        self.assertEqual(evidence, "fresh_independent_history_or_market")

    def test_other_factors_cannot_override_a_weak_discount_gate(self):
        row = {
            "current_price": 9_500_000, "original_price": 10_000_000,
            "discount_percent": 5, "savings_toman": 500_000,
            "test_live_demand": 100, "test_group": "home_cleaning",
        }
        self._score([row])
        self.assertGreater(row["offerchin_four_factor"]["live_demand"], 90)
        self.assertGreater(row["offerchin_four_factor"]["generality"], 90)
        self.assertLess(row["offerchin_four_factor"]["discount_attractiveness"], 40)
        eligible, _, _ = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)

    def test_product_taxonomy_distinguishes_software_from_mobile_hardware(self):
        self.assertEqual(infer_use_case_group("", "[MA, نرم افزار]"), "software_tools")
        self.assertEqual(infer_use_case_group("", "گوشی 512 گیگابایت"), "mobile_productivity")
        self.assertEqual(generality_score("software_tools"), 40)

    def test_gram_in_food_titles_does_not_trigger_ram_or_mobile_group(self):
        self.assertEqual(infer_use_case_group("پودر سیر شاهسوند - 120 گرم"), "grocery_food")

    def test_educational_kids_products_are_not_classified_as_books(self):
        self.assertEqual(infer_use_case_group("شورت آموزشی کودک"), "baby_care")

    def test_harmonic_mean_penalizes_a_single_weak_dimension(self):
        self.assertAlmostEqual(harmonic_mean([100, 100, 10]), 25.0, places=2)
        self.assertEqual(harmonic_mean([100, 0, 100]), 0.0)

    def test_incomplete_three_factor_data_falls_back_without_discount_tiebreak(self):
        row = {}
        apply_four_factor_scores(
            [row], live_demand_score_fn=lambda _: 80,
            use_case_group_fn=lambda _: "kitchen_food",
            discount_verified_fn=lambda _: False, now=self.now,
        )
        self.assertEqual(four_factor_sort_key(row), (0.0, 0.0, 0.0, 0.0, 0.0))

    def test_absolute_price_is_not_a_separate_scoring_dimension(self):
        cheap = self._deal("dkp-cheap", 100_000)
        expensive = self._deal("dkp-expensive", 90_000_000)
        self._score([cheap, expensive])
        cheap_score = cheap["offerchin_four_factor"]
        expensive_score = expensive["offerchin_four_factor"]
        self.assertEqual(
            cheap_score["dimensions"],
            ["live_demand", "generality", "discount_attractiveness"],
        )
        self.assertEqual(cheap_score["dimensions"], expensive_score["dimensions"])
        self.assertTrue(cheap_score["price_independent"])
        self.assertTrue(expensive_score["price_independent"])
        self.assertNotIn("affordability", str(cheap_score).lower())
        self.assertNotIn("current_price", cheap_score)
        self.assertNotIn("current_price", expensive_score)
        # The cash-savings component may differ for the same percentage at
        # different ticket sizes; no separate affordability/price factor exists.
        self.assertEqual(
            set(cheap_score),
            set(expensive_score),
        )

    def test_scores_contain_only_the_three_published_dimensions(self):
        row = self._deal()
        self._score([row])
        score = row["offerchin_four_factor"]
        self.assertEqual(
            score["dimensions"],
            ["live_demand", "generality", "discount_attractiveness"],
        )
        self.assertEqual(score["policy_version"], POLICY_VERSION)
        self.assertIn("three_factor", POLICY_VERSION)
        self.assertNotIn("affordability", str(score).lower())

    def test_discount_arithmetic_mismatch_is_zero(self):
        row = {
            "current_price": 750_000, "original_price": 1_000_000,
            "discount_percent": 20, "savings_toman": 250_000,
        }
        score, evidence = discount_attractiveness_score(row)
        self.assertEqual(score, 0)
        self.assertEqual(evidence, "inconsistent_markdown_arithmetic")


if __name__ == "__main__":
    unittest.main()
