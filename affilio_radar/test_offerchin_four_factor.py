from __future__ import annotations

import unittest
from datetime import datetime, timezone

import affilio_radar as radar
from offerchin_four_factor import (
    POLICY_VERSION,
    apply_three_factor_scores,
    discount_attractiveness_score,
    discount_publish_gate,
    infer_use_case_group,
    three_factor_sort_key,
)


class OfferChinThreeFactorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)

    def product(self, **overrides):
        return {
            "current_price": 1_000_000,
            "original_price": 2_000_000,
            "discount_percent": 50,
            "savings_toman": 1_000_000,
            **overrides,
        }

    def score(self, rows):
        return apply_three_factor_scores(
            rows,
            live_demand_score_fn=lambda row: row.get("test_demand", 80),
            use_case_group_fn=lambda row: row.get("test_group", "kitchen_food"),
            discount_verified_fn=lambda row: bool(row.get("independent_price_evidence")),
            now=self.now,
        )

    def test_three_factor_policy_contains_only_demand_generality_and_discount(self):
        row = self.product()
        self.score([row])
        score = row["offerchin_three_factor"]
        self.assertEqual(score["policy_version"], POLICY_VERSION)
        self.assertEqual(score["factor_count"], 3)
        self.assertEqual(
            set(score) & {"live_demand", "generality", "discount_attractiveness"},
            {"live_demand", "generality", "discount_attractiveness"},
        )
        self.assertNotIn("affordability", score)
        self.assertEqual(len(three_factor_sort_key(row)), 5)

    def test_affordability_or_price_never_changes_candidate_priority(self):
        low_price = self.product(current_price=100_000, original_price=200_000, savings_toman=100_000)
        high_price = self.product(current_price=90_000_000, original_price=180_000_000, savings_toman=90_000_000)
        self.score([low_price, high_price])
        self.assertEqual(low_price["offerchin_three_factor"]["balanced_score"],
                         high_price["offerchin_three_factor"]["balanced_score"])
        self.assertEqual(three_factor_sort_key(low_price), three_factor_sort_key(high_price))

    def test_false_discount_arithmetic_is_rejected(self):
        row = self.product(discount_percent=80)
        eligible, score, evidence = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)
        self.assertEqual(score, 0)
        self.assertEqual(evidence, "inconsistent_markdown_arithmetic")

    def test_small_discount_requires_independent_evidence_to_clear_gate(self):
        row = self.product(
            current_price=9_500_000,
            original_price=10_000_000,
            discount_percent=5,
            savings_toman=500_000,
        )
        weak = discount_publish_gate(row, independently_verified=False)
        strong = discount_publish_gate(row, independently_verified=True)
        self.assertFalse(weak[0])
        self.assertTrue(strong[0])
        self.assertGreater(strong[1], weak[1])

    def test_weak_discount_cannot_be_compensated_by_demand_or_generality(self):
        row = self.product(
            current_price=9_500_000,
            original_price=10_000_000,
            discount_percent=5,
            savings_toman=500_000,
            test_demand=100,
            test_group="home_cleaning",
        )
        self.score([row])
        self.assertLess(row["offerchin_three_factor"]["discount_attractiveness"], 40)
        self.assertFalse(discount_publish_gate(row)[0])

    def test_product_title_taxonomy_precedes_parent_catalog_category(self):
        self.assertEqual(
            infer_use_case_group("دفترچه یادداشت طرح گربه", "آرایشی و بهداشتی"),
            "books_learning",
        )
        self.assertEqual(
            radar.classify_category("دفترچه یادداشت طرح گربه"),
            "books_stationery",
        )

    def test_generic_animal_artwork_is_not_pet_care(self):
        self.assertEqual(
            infer_use_case_group("دفترچه یادداشت طرح گربه", ""),
            "books_learning",
        )

    def test_food_and_automotive_titles_get_specific_use_cases(self):
        self.assertEqual(infer_use_case_group("کره نارگیل طبیعی", "آرایشی و بهداشتی"), "grocery_food")
        self.assertEqual(infer_use_case_group("ضدیخ و مایع رادیاتور خودرو", ""), "automotive")

    def test_category_metadata_remains_a_fallback_when_title_is_unknown(self):
        self.assertEqual(infer_use_case_group("کالای مدل X", "نرم افزار و سیستم عامل"), "software_tools")


if __name__ == "__main__":
    unittest.main()
