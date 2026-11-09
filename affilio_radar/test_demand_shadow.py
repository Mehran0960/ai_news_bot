import unittest
from datetime import datetime, timedelta, timezone

from demand_shadow import annotate_shadow_demand_evidence


class DigiKalaShadowDemandTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 5, 0, tzinfo=timezone.utc)

    def product(self, product_id="dkp-12345", **overrides):
        row = {
            "product_id": product_id,
            "title": "هدفون بلوتوثی مدل آزمایشی",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 7,
            "catalog_best_selling_category_id": "211",
            "catalog_best_selling_category_name": "هدفون و هندزفری",
            "catalog_rank_observed_at": (self.now - timedelta(hours=2)).isoformat(),
            "discount_percent": 30,
            "current_price": 900000,
        }
        row.update(overrides)
        return row

    def test_accepts_fresh_digikala_bestseller_rank(self):
        product = self.product()
        report = annotate_shadow_demand_evidence([product], now=self.now)

        evidence = product["shadow_demand_evidence"]
        self.assertEqual(evidence["evidence_level"], "fresh_digikala_bestseller")
        self.assertEqual(evidence["digikala_bestseller"]["rank"], 7)
        self.assertEqual(evidence["digikala_bestseller"]["category_id"], "211")
        self.assertEqual(evidence["digikala_bestseller"]["scope"], "category_local")
        self.assertFalse(evidence["production_ranking_affected"])
        self.assertEqual(report["fresh_digikala_rank_count"], 1)

    def test_rejects_stale_future_invalid_and_non_digikala_ranks(self):
        rejected = [
            self.product("dkp-1", catalog_rank_observed_at=(self.now - timedelta(hours=24, seconds=1)).isoformat()),
            self.product("dkp-2", catalog_rank_observed_at=(self.now + timedelta(minutes=1)).isoformat()),
            self.product("dkp-3", catalog_best_selling_rank=61),
            self.product("dkp-4", catalog_best_selling_rank=0),
            self.product("dkp-5", catalog_sort_mode="discount"),
            self.product("snp-123"),
            self.product("dkp-6", catalog_best_selling_category_id=""),
            self.product("dkp-7", catalog_best_selling_category_id="not-a-number"),
            self.product("dkp-8", catalog_best_selling_rank=2.5),
        ]
        report = annotate_shadow_demand_evidence(rejected, now=self.now)
        self.assertEqual(report["fresh_digikala_rank_count"], 0)
        self.assertEqual(report["no_fresh_digikala_rank_count"], len(rejected))
        self.assertTrue(all(
            row["shadow_demand_evidence"]["digikala_bestseller"] is None
            for row in rejected
        ))

    def test_keeps_categories_separate_and_sorts_only_inside_each_category(self):
        rows = [
            self.product(
                "dkp-101",
                catalog_best_selling_rank=8,
                catalog_best_selling_category_id="20",
                catalog_best_selling_category_name="دسته دوم",
            ),
            self.product(
                "dkp-102",
                catalog_best_selling_rank=2,
                catalog_best_selling_category_id="10",
                catalog_best_selling_category_name="دسته اول",
            ),
            self.product(
                "dkp-103",
                catalog_best_selling_rank=1,
                catalog_best_selling_category_id="20",
                catalog_best_selling_category_name="دسته دوم",
            ),
        ]
        original_ids = [row["product_id"] for row in rows]
        report = annotate_shadow_demand_evidence(rows, now=self.now)

        self.assertEqual([row["product_id"] for row in rows], original_ids)
        self.assertEqual(
            [group["category_id"] for group in report["categories"]],
            ["10", "20"],
        )
        self.assertEqual(
            [item["rank"] for item in report["categories"][1]["products"]],
            [1, 8],
        )
        self.assertEqual(report["category_count"], 2)
        self.assertIn("not comparable", report["cross_category_comparability"])

    def test_does_not_use_torob_or_review_growth_as_shadow_sources(self):
        product = self.product(
            torob_trend={"rank": 1, "query": "هدفون"},
            current_demand_verified=True,
            recent_review_growth_window=999,
        )
        report = annotate_shadow_demand_evidence([product], now=self.now)

        self.assertEqual(report["source"], "existing_digikala_full_catalog_scanner")
        self.assertEqual(
            report["excluded_sources"],
            ["Torob trends", "SnappShop", "Google Trends", "review-growth proxy"],
        )
        self.assertFalse(any(key.startswith("torob") for key in report))
        self.assertEqual(
            product["shadow_demand_evidence"]["evidence_level"],
            "fresh_digikala_bestseller",
        )

    def test_missing_bestseller_evidence_does_not_block_or_reorder_products(self):
        first = self.product("dkp-201", catalog_best_selling_rank=1)
        second = self.product("dkp-202", catalog_sort_mode="discount")
        third = self.product("snp-203")
        rows = [first, second, third]
        before = [row["product_id"] for row in rows]

        report = annotate_shadow_demand_evidence(rows, now=self.now)

        self.assertEqual([row["product_id"] for row in rows], before)
        self.assertEqual(report["fresh_digikala_rank_count"], 1)
        self.assertFalse(report["production_ranking_affected"])


if __name__ == "__main__":
    unittest.main()
