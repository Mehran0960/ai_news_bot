import unittest
from datetime import datetime, timedelta, timezone

from four_factor_scoring import (
    FACTOR_WEIGHTS,
    SCORE_VERSION,
    _infer_use_case,
    score_candidates,
    sort_key,
)


class FourFactorScoringTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    def _ranked(self, rank, *, price=1_000_000, discount=20, savings=200_000, category="گوشی موبایل"):
        return {
            "product_id": f"dkp-{rank}",
            "title": "محصول نمونه",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": rank,
            "catalog_best_selling_category_id": "100",
            "catalog_best_selling_category_name": category,
            "catalog_rank_observed_at": self.now.isoformat(),
            "current_price": price,
            "original_price": price + savings,
            "discount_percent": round(100 * savings / (price + savings)),
            "savings_toman": savings,
        }

    def _verified_discount(self, product, *, market=True, history=False):
        if market:
            product.update({
                "market_status": "verified",
                "market_reference_kind": "seller_median",
                "market_price_advantage_pct": 12,
                "market_price_checked_at": self.now.isoformat(),
            })
        if history:
            product.update({
                "history_status": "verified",
                "historical_deal_eligible": True,
                "history_checked_at": self.now.isoformat(),
                "discount_vs_30d_median_pct": 8,
            })
        return product

    def test_factor_weights_are_equal_and_combined_score_is_their_mean(self):
        self.assertEqual(set(FACTOR_WEIGHTS.values()), {0.25})
        candidate = self._verified_discount(self._ranked(1))
        scored = score_candidates([candidate], now=self.now)[0]
        factors = scored["selection_factor_scores"]
        expected = round(sum(factors[key] for key in (
            "live_demand", "affordability", "generality", "discount_attractiveness"
        )) / 4)
        self.assertEqual(scored["selection_four_factor_score"], expected)
        self.assertEqual(scored["four_factor_score_version"], SCORE_VERSION)

    def test_fresh_native_bestseller_is_stronger_than_review_growth_proxy(self):
        bestseller = self._ranked(3)
        review_growth = {
            "product_id": "dkp-200",
            "current_demand_verified": True,
            "recent_review_growth_window": 12,
            "demand_window_hours": 24,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
            "current_price": 1_000_000,
            "original_price": 1_200_000,
            "discount_percent": 17,
            "savings_toman": 200_000,
        }
        scored = score_candidates([bestseller, review_growth], now=self.now)
        self.assertGreater(
            scored[0]["selection_demand_score"],
            scored[1]["selection_demand_score"],
        )

    def test_affordability_rewards_lower_actual_prices_within_candidate_pool(self):
        cheap = self._ranked(1, price=100_000, discount=20, savings=20_000)
        medium = self._ranked(2, price=1_000_000, discount=20, savings=200_000)
        expensive = self._ranked(3, price=10_000_000, discount=20, savings=2_000_000)
        scored = score_candidates([cheap, medium, expensive], now=self.now)
        by_id = {row["product_id"]: row for row in scored}
        self.assertGreater(
            by_id[cheap["product_id"]]["selection_affordability_score"],
            by_id[medium["product_id"]]["selection_affordability_score"],
        )
        self.assertGreater(
            by_id[medium["product_id"]]["selection_affordability_score"],
            by_id[expensive["product_id"]]["selection_affordability_score"],
        )
        self.assertEqual(
            by_id[cheap["product_id"]]["selection_affordability_reference"],
            "current_candidate_pool_not_household_income",
        )

    def test_affordability_uses_same_use_case_comparison_when_sample_is_large_enough(self):
        rows = [
            self._ranked(1, price=500_000, category="گوشی موبایل"),
            self._ranked(2, price=1_000_000, category="گوشی موبایل"),
            self._ranked(3, price=2_000_000, category="گوشی موبایل"),
            self._ranked(4, price=10_000_000, category="ابزار صنعتی"),
        ]
        def resolver(row):
            return "mobile_productivity" if row["catalog_best_selling_category_name"] == "گوشی موبایل" else "tools_industrial"
        scored = score_candidates(rows, now=self.now, use_case_resolver=resolver)
        self.assertGreater(
            scored[0]["selection_affordability_score"],
            scored[2]["selection_affordability_score"],
        )

    def test_general_consumables_get_higher_generality_than_specialized_tools(self):
        rows = [
            {**self._ranked(1), "current_price": 1_000_000},
            {**self._ranked(2), "current_price": 1_000_000},
        ]
        scored = score_candidates(
            rows,
            now=self.now,
            use_case_resolver=lambda row: (
                "grocery_food" if row["product_id"] == "dkp-1" else "tools_industrial"
            ),
        )
        by_id = {row["product_id"]: row for row in scored}
        self.assertGreater(
            by_id["dkp-1"]["selection_generality_score"],
            by_id["dkp-2"]["selection_generality_score"],
        )

    def test_mobile_titles_are_not_misclassified_as_hair_care(self):
        self.assertEqual(
            _infer_use_case({"title": "گوشی موبایل اقتصادی", "catalog_category_name": "گوشی موبایل"}),
            "mobile_productivity",
        )
        self.assertEqual(
            _infer_use_case({"title": "شامپو مو برای مراقبت مو", "catalog_category_name": "مراقبت شخصی"}),
            "personal_care",
        )

    def test_verified_history_or_market_evidence_outweighs_unverified_list_price(self):
        unverified = self._ranked(1, price=900_000, savings=900_000)
        unverified["product_id"] = "dkp-101"
        verified = self._verified_discount(self._ranked(2, price=900_000, savings=900_000), market=True)
        scored = score_candidates([unverified, verified], now=self.now)
        by_id = {row["product_id"]: row for row in scored}
        self.assertLessEqual(
            by_id["dkp-101"]["selection_discount_attractiveness_score"],
            40,
        )
        self.assertGreater(
            by_id["dkp-2"]["selection_discount_attractiveness_score"],
            by_id["dkp-101"]["selection_discount_attractiveness_score"],
        )
        self.assertEqual(
            by_id["dkp-2"]["selection_discount_evidence"],
            "verified_history_and_or_market",
        )

    def test_discount_score_rejects_inconsistent_price_arithmetic(self):
        candidate = self._verified_discount(self._ranked(1))
        candidate["savings_toman"] += 1
        scored = score_candidates([candidate], now=self.now)[0]
        self.assertEqual(scored["selection_discount_attractiveness_score"], 0)

    def test_stale_market_and_history_evidence_does_not_validate_a_markdown(self):
        candidate = self._verified_discount(self._ranked(1))
        old = (self.now - timedelta(hours=30)).isoformat()
        candidate["market_price_checked_at"] = old
        scored = score_candidates([candidate], now=self.now)[0]
        self.assertEqual(scored["selection_discount_attractiveness_score"], 40)

    def test_clicks_commission_and_synthetic_scores_do_not_create_live_demand(self):
        candidate = {
            "product_id": "dkp-500",
            "review_count": 1_000_000,
            "rating": 5.0,
            "click_count_30d": 99_999,
            "commission_toman": 999_999_999,
            "demand_score": 999,
            "current_demand_score": 999,
            "current_price": 500_000,
        }
        scored = score_candidates([candidate], now=self.now)[0]
        self.assertEqual(scored["selection_demand_score"], 0)

    def test_sort_key_uses_composite_then_component_scores(self):
        low = self._ranked(55, price=8_000_000, discount=15, savings=1_000_000)
        high = self._ranked(1, price=500_000, discount=60, savings=300_000)
        scored = score_candidates([low, high], now=self.now)
        self.assertGreater(sort_key(scored[1]), sort_key(scored[0]))


if __name__ == "__main__":
    unittest.main()
