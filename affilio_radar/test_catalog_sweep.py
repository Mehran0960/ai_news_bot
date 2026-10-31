from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from affilio_radar.catalog_sweep import (
    _advance_cursor,
    catalog_candidate_sort_key,
    discover_categories,
    extract_categories,
    extract_product_rows,
    extract_total_pages,
    load_catalog_candidates_for_handoff,
    run_sweep,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


class CatalogSweepTests(unittest.TestCase):
    def test_extract_categories_walks_nested_category_tree(self):
        payload = {
            "data": {
                "category_tree": [
                    {
                        "id": 10, "title_fa": "کالای دیجیتال",
                        "children": [
                            {"id": 11, "title_fa": "موبایل", "slug": "mobile"},
                            {"id": 12, "title_fa": "لوازم جانبی", "children": [
                                {"id": 13, "title_fa": "شارژر"}
                            ]},
                        ],
                    }
                ]
            }
        }
        categories = extract_categories(payload)
        self.assertEqual({item["id"] for item in categories}, {"10", "11", "12", "13"})
        child = next(item for item in categories if item["id"] == "13")
        self.assertEqual(child["parent_id"], "12")
        self.assertEqual(child["depth"], 2)

    def test_extract_categories_falls_back_to_category_filter_facets(self):
        payload = {
            "data": {
                "filters": [
                    {
                        "key": "categories",
                        "values": [
                            {"id": 22, "title": "خانه"},
                            {"id": 23, "title": "آشپزخانه"},
                        ],
                    }
                ]
            }
        }
        self.assertEqual(
            {row["id"] for row in extract_categories(payload)},
            {"22", "23"},
        )

    def test_discover_categories_uses_public_dictionary_endpoint(self):
        payload = {"data": {"category_tree": [{"id": 5, "title": "خانه", "children": []}]}}
        session = FakeSession([payload])
        categories = discover_categories(session)
        self.assertEqual(categories[0]["id"], "5")
        self.assertIn("types[5]", dict(session.calls[0][1]))
        self.assertEqual(dict(session.calls[0][1])["types[5]"], "category_tree")

    def test_extract_product_rows_parses_prices_reviews_and_product_id(self):
        payload = {
            "data": {
                "products": [
                    {
                        "id": 1234,
                        "url": "/product/dkp-1234/sample/",
                        "title_fa": "هدفون بلوتوثی مدل نمونه",
                        "default_variant": {
                            "price": {
                                "selling_price_toman": 800000,
                                "rrp_price_toman": 1200000,
                                "discount_percent": 33,
                            }
                        },
                        "rating": {"rate": 4.6, "rate_count": 1200},
                    },
                    {
                        "id": 1235,
                        "url": "/product/dkp-1235/sample/",
                        "title_fa": "کابل شارژ معمولی",
                        "price": {"selling_price": 5000000, "rrp_price": 7000000},
                    },
                ]
            },
            "pager": {"total_pages": 17},
        }
        rows = extract_product_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_id"], "dkp-1234")
        self.assertEqual(rows[0]["discount_percent"], 33)
        self.assertEqual(rows[0]["savings_toman"], 400000)
        self.assertEqual(rows[0]["review_count"], 1200)
        self.assertEqual(rows[1]["discount_percent"], 29)
        self.assertEqual(extract_total_pages(payload, 1, len(rows)), 17)

    def test_missing_product_array_raises_instead_of_advancing_cursor(self):
        with self.assertRaises(RuntimeError):
            extract_product_rows({"data": {"items": []}})

    def test_cursor_advances_only_after_successful_page(self):
        state = {"category_index": 0, "page": 1, "completed_cycles": 0}
        _advance_cursor(state, category_count=3, total_pages=3, products_count=20)
        self.assertEqual(state["category_index"], 0)
        self.assertEqual(state["page"], 2)
        _advance_cursor(state, category_count=3, total_pages=3, products_count=20)
        self.assertEqual(state["page"], 3)
        _advance_cursor(state, category_count=3, total_pages=3, products_count=20)
        self.assertEqual(state["category_index"], 1)
        self.assertEqual(state["page"], 1)

    def test_cursor_completes_cycle_and_resets(self):
        state = {"category_index": 0, "page": 1, "completed_cycles": 0}
        _advance_cursor(state, category_count=1, total_pages=1, products_count=5)
        self.assertEqual(state["category_index"], 0)
        self.assertEqual(state["page"], 1)
        self.assertEqual(state["completed_cycles"], 1)

    def test_candidate_rank_prioritizes_demand_before_discount(self):
        popular = {"review_count": 30000, "rating": 4.7, "discount_percent": 20}
        extreme_discount = {"review_count": 30, "rating": 3.8, "discount_percent": 90}
        self.assertGreater(
            catalog_candidate_sort_key(popular),
            catalog_candidate_sort_key(extreme_discount),
        )

    def test_handoff_marks_only_new_candidates_and_skips_seen(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            path.write_text(json.dumps({"candidates": [
                {"product_id": "dkp-1", "product_url": "https://www.digikala.com/product/dkp-1/", "title": "هدفون بلوتوثی نمونه", "discount_percent": 50},
                {"product_id": "dkp-2", "product_url": "https://www.digikala.com/product/dkp-2/", "title": "پاوربانک مدل نمونه", "discount_percent": 70},
            ]}, ensure_ascii=False), encoding="utf-8")
            state = {"catalog_sweep_handoff": {"seen_ids": {"dkp-1": "2026-10-30T00:00:00+00:00"}}}
            selected = load_catalog_candidates_for_handoff(
                path, state, max_count=10,
            )
            self.assertEqual([row["product_id"] for row in selected], ["dkp-2"])
            self.assertIn("dkp-2", state["catalog_sweep_handoff"]["seen_ids"])

    def test_run_sweep_checkpoints_page_and_candidates(self):
        category_payload = {"data": {"category_tree": [{"id": 7, "title": "کالای دیجیتال"}]}}
        page_payload = {
            "data": {
                "products": [{
                    "id": 777, "url": "/product/dkp-777/",
                    "title_fa": "پاوربانک مدل آزمایشی",
                    "default_variant": {"price": {
                        "selling_price_toman": 700000,
                        "rrp_price_toman": 1000000,
                        "discount_percent": 30,
                    }},
                    "rating": {"rate": 4.5, "rate_count": 500},
                }]
            },
            "pager": {"total_pages": 1},
        }
        session = FakeSession([category_payload, page_payload])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            state_path = base / "state.json"
            candidates_path = base / "candidates.json"
            publisher_state_path = base / "publisher.json"
            publisher_state_path.write_text("{}", encoding="utf-8")
            result = run_sweep(
                pages_per_run=1,
                session=session,
                state_path=state_path,
                candidates_path=candidates_path,
                publisher_state_path=publisher_state_path,
            )
            self.assertEqual(result, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            self.assertEqual(state["stats"]["pages_scanned_total"], 1)
            self.assertEqual(state["stats"]["product_rows_scanned_total"], 1)
            self.assertEqual(candidates["candidate_count"], 1)
            self.assertEqual(state["completed_cycles"], 1)


if __name__ == "__main__":
    unittest.main()
