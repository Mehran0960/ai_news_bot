from __future__ import annotations

import json
import requests
import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path
from unittest.mock import Mock

try:
    from .catalog_sweep import (
        _advance_cursor,
        _clean_old_candidates,
        catalog_handoff_fingerprint,
        catalog_candidate_sort_key,
        retain_diverse_candidates,
        acknowledge_catalog_candidates_handoff,
        defer_catalog_candidates_handoff,
        discover_categories,
        refresh_categories,
        CatalogSweepError,
        extract_categories,
        extract_product_rows,
        extract_total_pages,
        _category_page_url,
        _fresh_best_selling_rank,
        load_catalog_candidates_for_handoff,
        run_sweep,
    )
except ImportError:
    from catalog_sweep import (
        _advance_cursor,
        _clean_old_candidates,
        catalog_handoff_fingerprint,
        catalog_candidate_sort_key,
        retain_diverse_candidates,
        acknowledge_catalog_candidates_handoff,
        defer_catalog_candidates_handoff,
        discover_categories,
        refresh_categories,
        CatalogSweepError,
        extract_categories,
        extract_product_rows,
        extract_total_pages,
        _category_page_url,
        _fresh_best_selling_rank,
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
            raise requests.HTTPError(f"http_{self.status_code}", response=self)

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
        response = self.responses.pop(0)
        return response if hasattr(response, "raise_for_status") else FakeResponse(response)


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

    def test_extract_categories_prioritizes_leaf_categories_before_parents(self):
        payload = {
            "data": {
                "category_tree": [{
                    "id": 10, "title_fa": "کالای دیجیتال",
                    "children": [
                        {"id": 11, "title_fa": "موبایل"},
                        {"id": 12, "title_fa": "لوازم جانبی", "children": [
                            {"id": 13, "title_fa": "شارژر"}
                        ]},
                    ],
                }]
            }
        }
        categories = extract_categories(payload)
        positions = {row["id"]: index for index, row in enumerate(categories)}
        self.assertLess(positions["13"], positions["12"])
        self.assertLess(positions["11"], positions["10"])
        self.assertLess(positions["13"], positions["10"])

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

    def test_discover_categories_preserves_http_status_for_both_public_endpoints(self):
        session = FakeSession([
            FakeResponse({}, status_code=403),
            FakeResponse({}, status_code=403),
        ])
        with self.assertRaises(CatalogSweepError) as raised:
            discover_categories(session)
        self.assertIn("dictionaries_http_403", str(raised.exception))
        self.assertIn("search_http_403", str(raised.exception))

    def test_refresh_categories_uses_recent_verified_cache_during_api_outage(self):
        categories = [
            {"id": "10", "name": "خانه", "parent_id": "", "depth": 0},
            {"id": "11", "name": "آشپزخانه", "parent_id": "10", "depth": 1},
        ]
        refreshed = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        state = {
            "categories": categories,
            "categories_refreshed_at": refreshed,
            "category_index": 1,
            "page": 7,
        }
        session = FakeSession([
            FakeResponse({}, status_code=403),
            FakeResponse({}, status_code=403),
        ])
        refresh_categories(state, session)
        self.assertEqual(state["categories"], categories)
        self.assertEqual(state["category_index"], 1)
        self.assertEqual(state["page"], 7)
        self.assertTrue(state["category_discovery_fallback_used"])
        self.assertIn("dictionaries_http_403", state["category_discovery_last_error"])
        self.assertIn("search_http_403", state["category_discovery_last_error"])
        self.assertGreater(
            datetime.fromisoformat(state["category_discovery_retry_after"]),
            datetime.now(timezone.utc),
        )

    def test_refresh_categories_respects_retry_backoff_without_repeating_api_calls(self):
        now = datetime.now(timezone.utc)
        state = {
            "categories": [{"id": "10", "name": "خانه", "parent_id": "", "depth": 0}],
            "categories_refreshed_at": (now - timedelta(hours=48)).isoformat(),
            "category_discovery_retry_after": (now + timedelta(hours=2)).isoformat(),
            "category_index": 0,
            "page": 4,
        }
        session = FakeSession([])
        refresh_categories(state, session)
        self.assertEqual(session.calls, [])
        self.assertEqual(state["page"], 4)

    def test_refresh_categories_does_not_use_expired_taxonomy_cache_after_api_failure(self):
        refreshed = (datetime.now(timezone.utc) - timedelta(hours=120)).isoformat()
        state = {
            "categories": [{"id": "10", "name": "خانه", "parent_id": "", "depth": 0}],
            "categories_refreshed_at": refreshed,
        }
        session = FakeSession([
            FakeResponse({}, status_code=403),
            FakeResponse({}, status_code=403),
        ])
        with self.assertRaises(CatalogSweepError):
            refresh_categories(state, session)

    def test_category_page_url_uses_current_v2_category_route_and_best_selling_sort(self):
        url, params = _category_page_url("19", 3)
        self.assertEqual(url, "https://api.digikala.com/v2/category/19/")
        self.assertEqual(params, {"page": 3, "sort": 5})

    def test_extract_product_rows_parses_v2_vertical_product_listing_widgets(self):
        payload = {
            "data": {
                "pager": {"current_page": 1, "total_pages": 17, "total_items": 321},
                "widgets": [{
                    "type": "vertical_product_listing",
                    "data": {
                        "widgets": [
                            {
                                "type": "product",
                                "data": {
                                    "id": 777,
                                    "title_fa": "گوشی پوکو مدل آزمایشی",
                                    "url": {"uri": "/product/dkp-777/sample/"},
                                    "status": "marketable",
                                    "default_variant": {
                                        "price": {
                                            "selling_price": 8_000_000,
                                            "rrp_price": 12_000_000,
                                            "discount_percent": 33,
                                        }
                                    },
                                    "rating": {"rate": 90, "count": 200},
                                },
                            },
                            {
                                "type": "product",
                                "data": {
                                    "id": 778,
                                    "title_fa": "محصول ناموجود",
                                    "url": {"uri": "/product/dkp-778/sample/"},
                                    "status": "unavailable",
                                    "default_variant": {"price": {
                                        "selling_price": 8_000_000,
                                        "rrp_price": 12_000_000,
                                        "discount_percent": 33,
                                    }},
                                },
                            },
                        ]
                    },
                }],
            }
        }
        rows = extract_product_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_id"], "dkp-777")
        self.assertEqual(rows[0]["current_price"], 800_000)
        self.assertEqual(rows[0]["original_price"], 1_200_000)
        self.assertEqual(rows[0]["discount_percent"], 33)
        self.assertEqual(rows[0]["rating"], 4.5)
        self.assertEqual(rows[0]["review_count"], 200)
        self.assertEqual(rows[0]["availability"], "marketable_unverified_stock")
        self.assertEqual(extract_total_pages(payload, 1, len(rows)), 17)

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
                            },
                            "is_in_stock": False,
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
        self.assertEqual(rows[0]["availability"], "out_of_stock")
        self.assertEqual(rows[0]["review_count"], 1200)
        self.assertEqual(rows[1]["discount_percent"], 29)
        self.assertEqual(rows[1]["availability"], "unknown")
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

    def test_category_search_requests_best_selling_sort(self):
        url, params = _category_page_url("123", 2)
        self.assertEqual(url, "https://api.digikala.com/v2/category/123/")
        self.assertEqual(params, {"page": 2, "sort": 5})

    def test_fresh_digikala_bestseller_rank_outranks_a_larger_discount(self):
        now = datetime.now(timezone.utc)
        popular_low_discount = {
            "product_id": "dkp-101",
            "catalog_sort_mode": "best_selling", "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": now.isoformat(), "review_count": 250_000,
            "rating": 4.9, "discount_percent": 15, "savings_toman": 150_000,
        }
        obscure_high_discount = {
            "product_id": "dkp-102",
            "catalog_sort_mode": "best_selling", "catalog_best_selling_rank": 60,
            "catalog_rank_observed_at": now.isoformat(), "review_count": 1,
            "rating": 3.1, "discount_percent": 85, "savings_toman": 850_000,
        }
        self.assertEqual(_fresh_best_selling_rank(popular_low_discount, now), 1)
        self.assertGreater(
            catalog_candidate_sort_key(popular_low_discount),
            catalog_candidate_sort_key(obscure_high_discount),
        )

    def test_candidate_retention_keeps_demand_context_before_markdown_value(self):
        rows = [
            {"product_id": f"dkp-{i}", "catalog_category_id": "10", "catalog_category_ids": ["10"], "review_count": 10000-i, "discount_percent": 50, "savings_toman": 500_000}
            for i in range(1, 6)
        ] + [
            {"product_id": "dkp-20", "catalog_category_id": "20", "catalog_category_ids": ["20"], "review_count": 1, "discount_percent": 95, "savings_toman": 950_000},
            {"product_id": "dkp-30", "catalog_category_id": "30", "catalog_category_ids": ["30"], "review_count": 1, "discount_percent": 90, "savings_toman": 900_000},
            {"product_id": "dkp-40", "catalog_category_id": "40", "catalog_category_ids": ["40"], "review_count": 1, "discount_percent": 85, "savings_toman": 850_000},
        ]
        retained = retain_diverse_candidates(rows, limit=4, rotation=0)
        self.assertEqual([row["product_id"] for row in retained], ["dkp-1", "dkp-2", "dkp-3", "dkp-4"])

    def test_handoff_acknowledges_only_after_queue_retention_and_rotates_overflow(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            path.write_text(json.dumps({"candidates": [
                {"product_id": "dkp-1", "product_url": "https://www.digikala.com/product/dkp-1/", "title": "هدفون بلوتوثی نمونه", "current_price": 250_000, "original_price": 500_000, "discount_percent": 50, "availability": "in_stock"},
                {"product_id": "dkp-2", "product_url": "https://www.digikala.com/product/dkp-2/", "title": "پاوربانک مدل نمونه", "current_price": 300_000, "original_price": 1_000_000, "discount_percent": 70, "savings_toman": 700_000, "availability": "in_stock"},
            ]}, ensure_ascii=False), encoding="utf-8")
            state = {}
            fixed_now = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
            acknowledge_catalog_candidates_handoff(
                state,
                ["dkp-1"],
                now=fixed_now - timedelta(days=1),
                candidates=[{
                    "product_id": "dkp-1",
                    "current_price": 250_000,
                    "original_price": 500_000,
                    "discount_percent": 50,
                    "availability": "in_stock",
                }],
            )
            selected = load_catalog_candidates_for_handoff(path, state, max_count=10, now=fixed_now)
            self.assertEqual([row["product_id"] for row in selected], ["dkp-2"])
            self.assertNotIn("dkp-2", state["catalog_sweep_handoff"]["seen_ids"])
            self.assertEqual(defer_catalog_candidates_handoff(
                state, ["dkp-2"], now=fixed_now, retry_minutes=15,
            ), 1)
            self.assertEqual(load_catalog_candidates_for_handoff(path, state, now=fixed_now), [])
            selected_again = load_catalog_candidates_for_handoff(
                path, state, now=fixed_now + timedelta(minutes=16),
            )
            self.assertEqual([row["product_id"] for row in selected_again], ["dkp-2"])
            self.assertEqual(acknowledge_catalog_candidates_handoff(
                state,
                ["dkp-2"],
                now=fixed_now + timedelta(minutes=16),
                candidates=[{
                    "product_id": "dkp-2",
                    "current_price": 300_000,
                    "original_price": 1_000_000,
                    "discount_percent": 70,
                    "availability": "in_stock",
                }],
            ), 1)
            self.assertIn("dkp-2", state["catalog_sweep_handoff"]["seen_ids"])


    def test_candidate_cleanup_drops_unchanged_seen_cards_but_keeps_price_or_stock_changes(self):
        now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
        original = {
            "product_id": "dkp-55",
            "product_url": "https://www.digikala.com/product/dkp-55/",
            "title": "هدفون بلوتوثی نمونه",
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "availability": "in_stock",
            "last_seen_at": now.isoformat(),
        }
        seen_records = {
            "dkp-55": {
                "seen_at": (now - timedelta(hours=1)).isoformat(),
                "fingerprint": catalog_handoff_fingerprint(original),
            }
        }

        unchanged = _clean_old_candidates(
            {"dkp-55": original}, {"dkp-55"}, now, seen_records=seen_records
        )
        self.assertNotIn("dkp-55", unchanged)

        changed_price = {
            **original,
            "current_price": 400_000,
            "discount_percent": 60,
        }
        retained_price = _clean_old_candidates(
            {"dkp-55": changed_price}, {"dkp-55"}, now, seen_records=seen_records
        )
        self.assertEqual(retained_price["dkp-55"]["current_price"], 400_000)

        changed_stock = {**original, "availability": "out_of_stock"}
        retained_stock = _clean_old_candidates(
            {"dkp-55": changed_stock}, {"dkp-55"}, now, seen_records=seen_records
        )
        self.assertEqual(retained_stock["dkp-55"]["availability"], "out_of_stock")

    def test_candidate_cleanup_allows_legacy_seen_record_without_fingerprint_once(self):
        now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
        candidate = {
            "product_id": "dkp-56",
            "product_url": "https://www.digikala.com/product/dkp-56/",
            "title": "پاوربانک قابل حمل نمونه",
            "discount_percent": 40,
            "last_seen_at": now.isoformat(),
        }
        cleaned = _clean_old_candidates(
            {"dkp-56": candidate},
            {"dkp-56"},
            now,
            seen_records={"dkp-56": {"seen_at": now.isoformat()}},
        )
        self.assertIn("dkp-56", cleaned)

    def test_changed_catalog_card_bypasses_queue_deferral_and_refreshes_existing_queue_entry(self):
        now = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
        original = {
            "product_id": "dkp-57",
            "product_url": "https://www.digikala.com/product/dkp-57/",
            "title": "هدفون بی‌سیم نمونه",
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "availability": "in_stock",
            "last_seen_at": now.isoformat(),
        }
        changed = {
            **original,
            "current_price": 350_000,
            "discount_percent": 65,
            "availability": "in_stock",
            "last_seen_at": (now + timedelta(minutes=1)).isoformat(),
        }
        state = {"catalog_sweep_handoff": {"seen_ids": {}, "deferred_ids": {}}}
        defer_catalog_candidates_handoff(
            state, {"dkp-57"}, now=now, retry_minutes=60, candidates=[original]
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            path.write_text(json.dumps({"candidates": [changed]}, ensure_ascii=False), encoding="utf-8")
            selected = load_catalog_candidates_for_handoff(
                path, state, max_count=10, now=now + timedelta(minutes=2)
            )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-57"])

    def test_handoff_rechecks_price_change_before_seen_ttl(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            original = {
                "product_id": "dkp-55",
                "product_url": "https://www.digikala.com/product/dkp-55/",
                "title": "هدفون بلوتوثی نمونه",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "availability": "in_stock",
            }
            state = {}
            now = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
            path.write_text(json.dumps({"candidates": [original]}, ensure_ascii=False), encoding="utf-8")
            acknowledge_catalog_candidates_handoff(
                state, ["dkp-55"], now=now, candidates=[original]
            )
            # An unchanged catalog card should not consume another deep-check.
            self.assertEqual(
                load_catalog_candidates_for_handoff(path, state, now=now + timedelta(hours=1)),
                [],
            )
            changed = dict(original, current_price=400_000, discount_percent=60, savings_toman=600_000)
            path.write_text(json.dumps({"candidates": [changed]}, ensure_ascii=False), encoding="utf-8")
            selected = load_catalog_candidates_for_handoff(
                path, state, now=now + timedelta(hours=1)
            )
            self.assertEqual([row["product_id"] for row in selected], ["dkp-55"])

    def test_handoff_rechecks_price_or_stock_changes_before_seen_ttl(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            original = {
                "product_id": "dkp-55",
                "product_url": "https://www.digikala.com/product/dkp-55/",
                "title": "هدفون بلوتوثی نمونه",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": 50,
                "savings_toman": 500_000,
                "availability": "in_stock",
            }
            state = {}
            now = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
            path.write_text(json.dumps({"candidates": [original]}, ensure_ascii=False), encoding="utf-8")
            acknowledge_catalog_candidates_handoff(
                state, ["dkp-55"], now=now, candidates=[original]
            )
            self.assertEqual(
                load_catalog_candidates_for_handoff(path, state, now=now + timedelta(hours=1)),
                [],
            )
            changed_price = dict(original, current_price=400_000, discount_percent=60, savings_toman=600_000)
            path.write_text(json.dumps({"candidates": [changed_price]}, ensure_ascii=False), encoding="utf-8")
            selected = load_catalog_candidates_for_handoff(
                path, state, now=now + timedelta(hours=1)
            )
            self.assertEqual([row["product_id"] for row in selected], ["dkp-55"])
            acknowledge_catalog_candidates_handoff(
                state, ["dkp-55"], now=now + timedelta(hours=1), candidates=[changed_price]
            )
            changed_stock = dict(changed_price, availability="out_of_stock")
            path.write_text(json.dumps({"candidates": [changed_stock]}, ensure_ascii=False), encoding="utf-8")
            selected_stock = load_catalog_candidates_for_handoff(
                path, state, now=now + timedelta(hours=2)
            )
            self.assertEqual([row["product_id"] for row in selected_stock], ["dkp-55"])

    def test_handoff_batch_is_demand_then_discount_order_without_category_rotation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            rows = [
                {
                    "product_id": f"dkp-{index}",
                    "product_url": f"https://www.digikala.com/product/dkp-{index}/",
                    "title": f"هدفون بلوتوثی مدل {index}",
                    "catalog_category_id": "10",
                    "catalog_category_ids": ["10"],
                    "review_count": 10000 - index,
                    "rating": 4.7,
                    "discount_percent": 25,
                    "savings_toman": 250_000,
                }
                for index in range(1, 6)
            ]
            rows.extend([
                {
                    "product_id": "dkp-20",
                    "product_url": "https://www.digikala.com/product/dkp-20/",
                    "title": "چراغ اضطراری نمونه",
                    "catalog_category_id": "20",
                    "catalog_category_ids": ["20"],
                    "review_count": 100,
                    "rating": 4.5,
                    "discount_percent": 20,
                    "savings_toman": 200_000,
                },
                {
                    "product_id": "dkp-30",
                    "product_url": "https://www.digikala.com/product/dkp-30/",
                    "title": "کفش روزمره نمونه",
                    "catalog_category_id": "30",
                    "catalog_category_ids": ["30"],
                    "review_count": 90,
                    "rating": 4.4,
                    "discount_percent": 30,
                    "savings_toman": 300_000,
                },
                {
                    "product_id": "dkp-40",
                    "product_url": "https://www.digikala.com/product/dkp-40/",
                    "title": "عطر روزمره نمونه",
                    "catalog_category_id": "40",
                    "catalog_category_ids": ["40"],
                    "review_count": 80,
                    "rating": 4.3,
                    "discount_percent": 40,
                    "savings_toman": 400_000,
                },
            ])
            path.write_text(
                json.dumps({"candidates": rows}, ensure_ascii=False),
                encoding="utf-8",
            )
            selected = load_catalog_candidates_for_handoff(
                path,
                {},
                max_count=4,
                now=datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc),
            )
            self.assertEqual([row["product_id"] for row in selected], ["dkp-1", "dkp-2", "dkp-3", "dkp-4"])

    def test_legacy_serial_sweep_does_not_skip_page_four_or_later(self):
        page_payload = {
            "data": {
                "products": [{
                    "id": 8804,
                    "url": "/product/dkp-8804/page-four/",
                    "title_fa": "کالای تستی صفحه چهارم",
                    "default_variant": {"price": {
                        "selling_price_toman": 700_000,
                        "rrp_price_toman": 1_000_000,
                        "discount_percent": 30,
                    }},
                }]
            },
            "pager": {"total_pages": 5},
        }
        session = FakeSession([page_payload])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            state_path = base / "state.json"
            candidates_path = base / "candidates.json"
            publisher_state_path = base / "publisher.json"
            state_path.write_text(json.dumps({
                "categories": [{"id": "7", "name": "کالای دیجیتال"}],
                "categories_refreshed_at": datetime.now(timezone.utc).isoformat(),
                "category_index": 0,
                "page": 4,
                "stats": {},
            }), encoding="utf-8")
            publisher_state_path.write_text("{}", encoding="utf-8")

            result = run_sweep(
                pages_per_run=1,
                session=session,
                state_path=state_path,
                candidates_path=candidates_path,
                publisher_state_path=publisher_state_path,
            )

            self.assertEqual(result, 0)
            self.assertEqual(dict(session.calls[0][1])["page"], 4)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["page"], 5)
            self.assertEqual(saved["stats"]["pages_scanned_total"], 1)


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
                }, {
                    "id": 778, "url": "/product/dkp-778/",
                    "title_fa": "تخفیف در کارت نمایش داده نشده",
                    "default_variant": {"price": {
                        "selling_price_toman": 900000,
                        "rrp_price_toman": 900000,
                        "discount_percent": 0,
                    }},
                    "rating": {"rate": 4.1, "rate_count": 40},
                }, {
                    "id": 779, "url": "/product/dkp-779/",
                    "title_fa": "",
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
            self.assertEqual(state["stats"]["product_rows_scanned_total"], 3)
            self.assertEqual(candidates["candidate_count"], 1)
            self.assertEqual(state["stats"]["catalog_candidate_cards_found_total"], 3)
            self.assertEqual(state["stats"]["discounted_candidates_found_total"], 1)
            self.assertEqual(session.calls[1][0], "https://api.digikala.com/v2/category/7/")
            self.assertEqual(dict(session.calls[1][1]).get("sort"), 5)
            by_id = {row["product_id"]: row for row in candidates["candidates"]}
            self.assertEqual(set(by_id), {"dkp-777"})
            self.assertEqual(by_id["dkp-777"]["catalog_sort_mode"], "best_selling")
            self.assertEqual(by_id["dkp-777"]["catalog_best_selling_rank"], 1)
            self.assertEqual(by_id["dkp-777"]["discount_percent"], 30)
            self.assertEqual(state["completed_cycles"], 1)


    def test_candidate_retention_filters_prohibited_health_products_before_shortlist_cap(self):
        rows = [
            {
                "product_id": "dkp-health",
                "title": "قرص ویتامین D3-1000 واحدی بسته 60 عددی",
                "discount_percent": 80,
                "savings_toman": 800_000,
            },
            {
                "product_id": "dkp-book",
                "title": "کتاب سه دقیقه در قیامت اثر جمعی از نویسندگان",
                "discount_percent": 45,
                "savings_toman": 250_000,
            },
            {
                "product_id": "dkp-earbuds",
                "title": "هدفون بی‌سیم بلوتوثی مدل نمونه",
                "discount_percent": 35,
                "savings_toman": 300_000,
            },
        ]
        retained = retain_diverse_candidates(rows, limit=3)
        retained_ids = {row["product_id"] for row in retained}
        self.assertEqual(retained_ids, {"dkp-book", "dkp-earbuds"})
        self.assertNotIn("dkp-health", retained_ids)

    def test_catalog_handoff_counts_prohibited_health_title_rejections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidates.json"
            path.write_text(json.dumps({"candidates": [
                {
                    "product_id": "dkp-501",
                    "product_url": "https://www.digikala.com/product/dkp-501/",
                    "title": "قرص زینک پلاس پابا یوروویتال بسته 60 عددی",
                    "discount_percent": 40,
                    "savings_toman": 400_000,
                },
                {
                    "product_id": "dkp-502",
                    "product_url": "https://www.digikala.com/product/dkp-502/",
                    "title": "کتاب سه دقیقه در قیامت اثر جمعی از نویسندگان",
                    "discount_percent": 30,
                    "savings_toman": 150_000,
                },
            ]}, ensure_ascii=False), encoding="utf-8")
            state = {}
            selected = load_catalog_candidates_for_handoff(
                path,
                state,
                max_count=10,
                now=datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc),
            )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-502"])
        diagnostics = state["catalog_sweep_handoff"]["last_selection_diagnostics"]
        self.assertEqual(diagnostics["rows_seen"], 2)
        self.assertEqual(diagnostics["prohibited_health_title"], 1)
        self.assertEqual(diagnostics["fresh_eligible"], 1)
        self.assertEqual(diagnostics["selected"], 1)


if __name__ == "__main__":
    unittest.main()
