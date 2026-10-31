from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog_sweeper as sweep


class CatalogSweeperTests(unittest.TestCase):
    def test_extracts_queryable_children_and_deduplicates_ids(self):
        payload = {
            "data": {
                "filters": {
                    "categories": {
                        "options": [
                            {"id": 11, "title_fa": "موبایل", "code": "mobile-phone"},
                            {"id": 12, "title_fa": "لپ‌تاپ", "code": "laptop"},
                            {"id": 13, "title_fa": "بدون کد"},
                            {"id": 11, "title_fa": "موبایل تکراری", "code": "mobile-phone"},
                            {"id": "bad", "title_fa": "شناسه نامعتبر", "code": "bad"},
                        ]
                    }
                }
            }
        }
        rows = sweep.extract_queryable_categories(payload, parent_id=1)
        self.assertEqual([row["id"] for row in rows], [11, 12])
        self.assertEqual(rows[0]["code"], "mobile-phone")

    def test_extracts_pagination_from_nested_api_metadata(self):
        payload = {
            "data": {
                "pager": {"page": 1, "total_pages": "37"},
                "products": [{"id": 123}],
            }
        }
        self.assertEqual(sweep.extract_total_pages(payload), 37)
        self.assertIsNone(sweep.extract_total_pages({"data": {"products": []}}))

    def test_converts_listing_card_prices_ratings_and_demand(self):
        product = {
            "id": 12345,
            "title_fa": "پاوربانک نمونه",
            "url": "/product/dkp-12345/powerbank/",
            "default_variant": {
                "price": {
                    "selling_price": 9_000_000,
                    "rrp_price": 18_000_000,
                    "discount_percent": 50,
                },
                "rating": {"rate": 92, "rate_count": 1200},
            },
        }
        row = sweep.product_card_to_candidate(product, 77, "پاوربانک")
        self.assertIsNotNone(row)
        self.assertEqual(row["product_id"], "dkp-12345")
        self.assertEqual(row["current_price"], 900_000)
        self.assertEqual(row["original_price"], 1_800_000)
        self.assertEqual(row["discount_percent"], 50)
        self.assertEqual(row["savings_toman"], 900_000)
        self.assertEqual(row["rating"], 4.6)
        self.assertEqual(row["review_count"], 1200)
        self.assertGreater(row["demand_score"], 0)

    def test_excludes_non_product_and_no_discount_cards(self):
        self.assertIsNone(sweep.product_card_to_candidate(
            {"id": 123, "title_fa": "بدون تخفیف", "url": "/product/dkp-123/"},
            1, "ریشه",
        ))
        self.assertIsNone(sweep.product_card_to_candidate(
            {"id": 124, "title_fa": "محصول واریانت", "url": "/product/dkpi-124/"},
            1, "ریشه",
        ))

    def test_candidate_pool_is_deduplicated_and_demand_ranked(self):
        now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        base = {
            "product_url": "https://www.digikala.com/product/dkp-",
            "title": "کالای آزمایشی",
            "observed_at": now.isoformat(),
        }
        low = {**base, "product_id": "dkp-1", "demand_score": 5, "discount_percent": 95}
        high = {**base, "product_id": "dkp-2", "demand_score": 25, "discount_percent": 55}
        updated_low = {**low, "discount_percent": 99}
        rows = sweep.merge_candidate_pool([low], [high, updated_low], now=now, limit=10)
        self.assertEqual([row["product_id"] for row in rows], ["dkp-2", "dkp-1"])
        self.assertEqual(rows[1]["discount_percent"], 99)

    def test_candidate_pool_drops_records_older_than_ten_days(self):
        now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        old = {
            "product_id": "dkp-1",
            "observed_at": "2026-10-01T12:00:00+00:00",
            "demand_score": 100,
            "discount_percent": 99,
        }
        self.assertEqual(sweep.merge_candidate_pool([old], [], now=now), [])


if __name__ == "__main__":
    unittest.main()
