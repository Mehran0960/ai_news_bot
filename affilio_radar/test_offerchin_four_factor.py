from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import affilio_radar as radar
from offerchin_four_factor import (
    POLICY_VERSION,
    affordability_absolute_score,
    apply_four_factor_scores,
    discount_attractiveness_score,
    discount_publish_gate,
    four_factor_sort_key,
    generality_score,
    harmonic_mean,
)


class OfferChinFourFactorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    def _score(self, rows, independent=None):
        independent = independent or set()
        return apply_four_factor_scores(
            rows,
            live_demand_score_fn=lambda row: row.get("test_live_demand", 80),
            use_case_group_fn=lambda row: row.get("test_group", "kitchen_food"),
            discount_verified_fn=lambda row: row.get("product_id") in independent,
            now=self.now,
        )

    def test_low_percentage_and_low_savings_are_rejected_without_independent_price_evidence(self):
        row = {
            "current_price": 9_500_000,
            "original_price": 10_000_000,
            "discount_percent": 5,
            "savings_toman": 500_000,
        }
        eligible, score, evidence = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)
        self.assertLess(score, 40)
        self.assertEqual(evidence, "live_retailer_markdown_only")

    def test_small_percentage_can_pass_only_when_independently_verified_and_savings_are_real(self):
        row = {
            "current_price": 9_500_000,
            "original_price": 10_000_000,
            "discount_percent": 5,
            "savings_toman": 500_000,
        }
        eligible, score, evidence = discount_publish_gate(row, independently_verified=True)
        self.assertTrue(eligible)
        self.assertGreaterEqual(score, 40)
        self.assertEqual(evidence, "fresh_independent_history_or_market")

    def test_other_strong_factors_cannot_override_a_weak_discount_gate(self):
        row = {
            "current_price": 9_500_000,
            "original_price": 10_000_000,
            "discount_percent": 5,
            "savings_toman": 500_000,
            "test_live_demand": 100,
            "test_group": "home_cleaning",
        }
        self._score([row])
        self.assertGreater(row["offerchin_four_factor"]["live_demand"], 90)
        self.assertGreater(row["offerchin_four_factor"]["generality"], 90)
        self.assertLess(row["offerchin_four_factor"]["discount_attractiveness"], 40)
        eligible, _, _ = discount_publish_gate(row, independently_verified=False)
        self.assertFalse(eligible)

    def test_harmonic_mean_penalizes_a_single_weak_dimension(self):
        balanced = harmonic_mean([100, 100, 100, 10])
        self.assertAlmostEqual(balanced, 30.77, places=2)
        self.assertLess(balanced, sum([100, 100, 100, 10]) / 4)

    def test_incomplete_four_factor_data_falls_back_without_discount_tiebreak(self):
        row = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 80,
            "savings_toman": 800_000,
        }
        apply_four_factor_scores(
            [row],
            live_demand_score_fn=lambda _row: 0,
            use_case_group_fn=lambda _row: "kitchen_food",
            discount_verified_fn=lambda _row: True,
            now=self.now,
        )
        self.assertEqual(four_factor_sort_key(row), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    def test_affordability_uses_final_price_as_share_of_household_spending(self):
        self.assertEqual(affordability_absolute_score(150_000), 100)
        self.assertEqual(affordability_absolute_score(300_000), 90)
        self.assertEqual(affordability_absolute_score(600_000), 80)
        self.assertEqual(affordability_absolute_score(1_200_000), 70)
        self.assertEqual(affordability_absolute_score(2_400_000), 60)
        self.assertEqual(affordability_absolute_score(4_800_000), 50)
        self.assertEqual(affordability_absolute_score(9_600_000), 40)
        self.assertEqual(affordability_absolute_score(0), 0)

    def test_installment_down_payment_never_replaces_the_final_cash_price(self):
        cash_only = {
            "current_price": 10_000_000,
            "installment_down_payment_toman": 1_000_000,
            "installment_terms_verified": False,
        }
        verified_installment = {
            **cash_only,
            "installment_terms_verified": True,
        }
        rows = [cash_only, verified_installment]
        self._score(rows)
        first, second = rows
        self.assertEqual(
            first["offerchin_four_factor"]["affordability_basis"],
            "final_cash_price_vs_household_spend_proxy",
        )
        self.assertEqual(
            second["offerchin_four_factor"]["affordability_basis"],
            "final_cash_price_vs_household_spend_proxy",
        )
        self.assertEqual(
            first["offerchin_four_factor"]["affordability"],
            second["offerchin_four_factor"]["affordability"],
        )
        self.assertEqual(
            second["offerchin_four_factor"]["affordability_price_to_monthly_spend_percent"],
            33.333,
        )

    def test_unknown_use_case_is_not_mistaken_for_general_mass_market(self):
        self.assertGreater(generality_score("kitchen_food"), generality_score("tabletop_games"))
        self.assertGreater(generality_score("home_cleaning"), generality_score("unknown"))

    def test_independent_price_evidence_improves_discount_attractiveness(self):
        row = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
        }
        listed_score, listed_source = discount_attractiveness_score(row, False)
        verified_score, verified_source = discount_attractiveness_score(row, True)
        self.assertGreater(verified_score, listed_score)
        self.assertEqual(listed_source, "live_retailer_markdown_only")
        self.assertEqual(verified_source, "fresh_independent_history_or_market")

    def test_inconsistent_discount_arithmetic_gets_no_value_score(self):
        score, reason = discount_attractiveness_score({
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 70,
            "savings_toman": 500_000,
        })
        self.assertEqual(score, 0)
        self.assertEqual(reason, "inconsistent_markdown_arithmetic")

    def test_category_price_cohort_prefers_lower_entry_price(self):
        rows = []
        for index in range(8):
            price = (index + 1) * 100_000
            rows.append({
                "product_id": f"dkp-{index + 1}",
                "current_price": price,
                "original_price": price * 2,
                "discount_percent": 50,
                "savings_toman": price,
                "test_live_demand": 80,
                "test_group": "kitchen_food",
            })
        self._score(rows)
        cheapest, most_expensive = rows[0], rows[-1]
        cheap_scores = cheapest["offerchin_four_factor"]
        high_scores = most_expensive["offerchin_four_factor"]
        self.assertEqual(cheap_scores["price_cohort_size"], 8)
        self.assertGreater(cheap_scores["affordability"], high_scores["affordability"])
        self.assertGreater(
            four_factor_sort_key(cheapest),
            four_factor_sort_key(most_expensive),
        )

    def test_equal_candidates_are_ranked_by_all_four_dimensions(self):
        base = {
            "current_price": 1_000_000,
            "original_price": 1_500_000,
            "discount_percent": 33,
            "savings_toman": 500_000,
        }
        candidates = [
            {"product_id": "cheap_niche", **base, "current_price": 200_000, "original_price": 300_000,
             "discount_percent": 33, "savings_toman": 100_000, "test_live_demand": 80, "test_group": "tabletop_games"},
            {"product_id": "balanced_daily", **base, "test_live_demand": 80, "test_group": "kitchen_food"},
            {"product_id": "weak_demand", **base, "test_live_demand": 35, "test_group": "kitchen_food"},
        ]
        self._score(candidates)
        ranked = sorted(candidates, key=four_factor_sort_key, reverse=True)
        self.assertEqual(ranked[0]["product_id"], "balanced_daily")
        self.assertLess(
            candidates[1]["offerchin_four_factor"]["balanced_score"],
            80,
        )

    def test_clicks_and_synthetic_popularity_fields_do_not_change_any_score(self):
        baseline = {
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "test_live_demand": 75,
            "test_group": "kitchen_food",
        }
        changed = {
            **baseline,
            "click_count_30d": 1_000_000,
            "demand_score": 100_000,
            "current_demand_score": 100_000,
            "review_count": 999_999,
            "rating": 5,
        }
        self._score([baseline, changed])
        self.assertEqual(
            baseline["offerchin_four_factor"],
            changed["offerchin_four_factor"],
        )

    def test_live_publication_selector_uses_batch_four_factor_scores(self):
        products = []
        for index in range(8):
            price = (index + 1) * 100_000
            pid = f"dkp-{100 + index}"
            products.append({
                "product_id": pid,
                "title": f"چای ساز کاربردی مدل {index}",
                "current_price": price,
                "original_price": price * 2,
                "discount_percent": 50,
                "savings_toman": price,
                "selection_discount_floor": 1,
                "test_group": "kitchen_food",
                "test_live_demand": 80,
            })
        queue = {row["product_id"]: {} for row in products}
        eligible = {row["product_id"]: row for row in products}
        with patch.object(radar, "has_verified_market_demand", return_value=True), \
             patch.object(radar, "has_attractive_discount_value", return_value=False), \
             patch.object(radar, "_publication_use_case_group", side_effect=lambda row: row["test_group"]), \
             patch.object(radar, "_offerchin_live_demand_score", side_effect=lambda row, now=None: row["test_live_demand"]):
            selected = radar.select_publish_candidates(
                queue, eligible, now=self.now, published={}, recent_publications=[]
            )
        self.assertTrue(selected)
        self.assertEqual(selected[0]["product_id"], "dkp-100")
        self.assertEqual(
            selected[0]["offerchin_four_factor"]["policy_version"],
            POLICY_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
