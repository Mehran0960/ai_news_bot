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
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    def score(self, rows, demand=80):
        return apply_four_factor_scores(
            rows,
            live_demand_score_fn=lambda row: row.get("test_live_demand", demand),
            use_case_group_fn=lambda row: row.get("test_group", "kitchen_food"),
            discount_verified_fn=lambda row: row.get("independent_discount_evidence") is True,
            now=self.now,
            # Legacy API argument remains accepted, but must have no score effect.
            price_group_fn=lambda row: row.get("test_price_group", "default"),
        )

    def test_policy_has_exactly_three_dimensions_and_no_affordability(self):
        row = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
        }
        self.score([row])
        score = row["offerchin_three_factor"]
        self.assertEqual(
            score["score_dimensions"],
            ["live_demand", "generality", "discount_attractiveness"],
        )
        self.assertNotIn("affordability", score)
        self.assertNotIn("offerchin_four_factor", row)
        self.assertIn("no_affordability", POLICY_VERSION)

    def test_price_group_compatibility_argument_does_not_create_price_affordability(self):
        rows = [
            {
                "product_id": "dkp-a",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "test_price_group": "low_ticket",
            },
            {
                "product_id": "dkp-b",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "test_price_group": "high_ticket",
            },
        ]
        self.score(rows)
        self.assertEqual(
            rows[0]["offerchin_three_factor"]["balanced_score"],
            rows[1]["offerchin_three_factor"]["balanced_score"],
        )
        self.assertEqual(
            rows[0]["offerchin_three_factor"]["generality"],
            rows[1]["offerchin_three_factor"]["generality"],
        )

    def test_missing_live_demand_cannot_be_hidden_by_strong_generalization_or_discount(self):
        row = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "test_group": "home_cleaning",
        }
        self.score([row], demand=0)
        self.assertEqual(row["offerchin_three_factor"]["balanced_score"], 0)
        self.assertEqual(four_factor_sort_key(row), (0.0, 0.0, 0.0, 0.0, 0.0))

    def test_unknown_use_case_is_scored_below_broad_everyday_categories(self):
        self.assertGreater(generality_score("home_cleaning"), generality_score("unknown"))
        self.assertGreater(generality_score("grocery_food"), generality_score("tabletop_games"))
        self.assertLess(generality_score("unknown"), 25)

    def test_use_case_extractor_recognizes_nested_taxonomy_and_software(self):
        self.assertEqual(
            infer_use_case_group("نسخه نرم افزار تدوین", "نرم‌افزار"),
            "software_tools",
        )
        self.assertEqual(
            infer_use_case_group("گوشی موبایل سامسونگ", "کالای دیجیتال > گوشی موبایل"),
            "mobile_productivity",
        )

    def test_discount_gate_rejects_false_or_inconsistent_markdowns(self):
        eligible, score, reason = discount_publish_gate({
            "current_price": 950_000,
            "original_price": 1_000_000,
            "discount_percent": 70,
            "savings_toman": 50_000,
        })
        self.assertFalse(eligible)
        self.assertEqual(score, 0)
        self.assertEqual(reason, "inconsistent_markdown_arithmetic")

    def test_independent_discount_history_increases_confidence_not_affordability(self):
        row = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
        }
        listed_score, listed_reason = discount_attractiveness_score(row, False)
        verified_score, verified_reason = discount_attractiveness_score(row, True)
        self.assertGreater(verified_score, listed_score)
        self.assertEqual(listed_reason, "live_retailer_markdown_only")
        self.assertEqual(verified_reason, "fresh_independent_history_or_market")

    def test_harmonic_mean_penalizes_a_single_weak_factor(self):
        balanced = harmonic_mean([100, 100, 10])
        self.assertAlmostEqual(balanced, 25, places=2)
        self.assertLess(balanced, (100 + 100 + 10) / 3)

    def test_three_factor_sort_uses_balanced_score_and_weakest_dimension(self):
        rows = [
            {
                "product_id": "dkp-general",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "test_live_demand": 80,
                "test_group": "home_cleaning",
            },
            {
                "product_id": "dkp-niche",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "test_live_demand": 80,
                "test_group": "tabletop_games",
            },
        ]
        self.score(rows)
        ranked = sorted(rows, key=four_factor_sort_key, reverse=True)
        self.assertEqual(ranked[0]["product_id"], "dkp-general")
        self.assertEqual(len(four_factor_sort_key(ranked[0])), 5)


if __name__ == "__main__":
    unittest.main()
