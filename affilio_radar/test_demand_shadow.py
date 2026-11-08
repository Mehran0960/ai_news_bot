from __future__ import annotations

import unittest
from unittest.mock import patch

import affilio_radar as radar_module
from datetime import datetime, timedelta, timezone

from demand_shadow import (
    build_demand_shadow_report,
    extract_digikala_bestseller_evidence,
    match_torob_trends_to_product,
    sanitize_torob_trends,
    torob_trends_snapshot_status,
)


class DemandShadowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def test_uses_fresh_category_local_bestseller_rank(self):
        product = {
            "catalog_best_selling_ranks_by_category": {
                "11": {
                    "rank": 8,
                    "category_name": "هدفون",
                    "observed_at": (self.now - timedelta(hours=1)).isoformat(),
                }
            }
        }
        result = extract_digikala_bestseller_evidence(product, self.now)
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["best_rank"], 8)
        self.assertEqual(result["rank_tier"], "top_10")
        self.assertEqual(result["category_name"], "هدفون")

    def test_chooses_best_fresh_rank_across_categories_but_keeps_all(self):
        product = {
            "catalog_best_selling_ranks_by_category": {
                "11": {"rank": 28, "category_name": "صوتی", "observed_at": self.now.isoformat()},
                "12": {"rank": 4, "category_name": "هدفون", "observed_at": self.now.isoformat()},
            }
        }
        result = extract_digikala_bestseller_evidence(product, self.now)
        self.assertEqual(result["best_rank"], 4)
        self.assertEqual(result["category_id"], "12")
        self.assertEqual(len(result["fresh_category_ranks"]), 2)

    def test_ignores_stale_or_future_rank(self):
        product = {
            "catalog_best_selling_ranks_by_category": {
                "11": {"rank": 3, "category_name": "هدفون", "observed_at": (self.now - timedelta(hours=30)).isoformat()},
                "12": {"rank": 4, "category_name": "صوتی", "observed_at": (self.now + timedelta(hours=2)).isoformat()},
            }
        }
        result = extract_digikala_bestseller_evidence(product, self.now)
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["best_rank"])

    def test_ignores_rank_outside_top_sixty(self):
        product = {
            "catalog_best_selling_ranks_by_category": {
                "11": {"rank": 61, "category_name": "هدفون", "observed_at": self.now.isoformat()}
            }
        }
        result = extract_digikala_bestseller_evidence(product, self.now)
        self.assertEqual(result["status"], "missing")

    def test_accepts_legacy_flattened_rank_only_when_history_mapping_absent(self):
        product = {
            "catalog_best_selling_rank": 15,
            "catalog_best_selling_category_id": "12",
            "catalog_best_selling_category_name": "هدفون",
            "catalog_rank_observed_at": self.now.isoformat(),
        }
        result = extract_digikala_bestseller_evidence(product, self.now)
        self.assertEqual(result["best_rank"], 15)

    def test_sanitizes_torob_trend_payload_to_small_safe_fields(self):
        snapshot = sanitize_torob_trends({
            "trends": [
                {"query": "هندزفری بلوتوث", "category_id": "3", "sample": {"name_fa": "هندزفری بلوتوثی نمونه", "url": "https://example.invalid", "price_toman": 123}},
                {"query": "", "category_id": "4"},
            ],
            "note": "آمار جست‌وجوی لحظه‌ای",
        }, self.now)
        self.assertEqual(snapshot["count"], 1)
        self.assertEqual(snapshot["trends"][0]["query"], "هندزفری بلوتوث")
        self.assertNotIn("url", snapshot["trends"][0])
        self.assertNotIn("price_toman", snapshot["trends"][0])

    def test_invalid_or_empty_trend_payload_is_not_accepted_as_snapshot(self):
        self.assertIsNone(sanitize_torob_trends({"trends": []}, self.now))
        self.assertIsNone(sanitize_torob_trends({"wrong_field": []}, self.now))

    def test_rejects_stale_torob_trend_snapshot(self):
        snapshot = sanitize_torob_trends(
            {"trends": [{"query": "هندزفری بلوتوث"}]},
            self.now - timedelta(hours=13),
        )
        self.assertEqual(torob_trends_snapshot_status(snapshot, self.now)[0], "stale")
        match = match_torob_trends_to_product(
            {"title": "هندزفری بلوتوث انکر"},
            snapshot,
            self.now,
        )
        self.assertEqual(match["status"], "stale")

    def test_marks_two_term_torob_query_match_as_strong(self):
        snapshot = sanitize_torob_trends({
            "trends": [{"query": "هندزفری بلوتوث", "category_id": "5"}]
        }, self.now)
        result = match_torob_trends_to_product(
            {"title": "هندزفری بلوتوثی انکر مدل نمونه"},
            snapshot,
            self.now,
        )
        self.assertEqual(len(result["strong_matches"]), 1)
        self.assertEqual(result["strong_matches"][0]["match_strength"], "strong")

    def test_marks_single_term_match_as_weak(self):
        snapshot = sanitize_torob_trends({
            "trends": [{"query": "سامسونگ", "category_id": "9"}]
        }, self.now)
        result = match_torob_trends_to_product(
            {"title": "گوشی موبایل سامسونگ مدل نمونه"},
            snapshot,
            self.now,
        )
        self.assertEqual(len(result["weak_matches"]), 1)
        self.assertEqual(result["strong_matches"], [])

    def test_does_not_match_only_generic_query_words(self):
        snapshot = sanitize_torob_trends({
            "trends": [{"query": "قیمت خرید گوشی موبایل"}]
        }, self.now)
        result = match_torob_trends_to_product(
            {"title": "گوشی موبایل سامسونگ مدل نمونه"},
            snapshot,
            self.now,
        )
        self.assertEqual(result["status"], "no_match")

    def test_category_rankings_are_separate_and_sorted_by_category_rank(self):
        products = [
            {
                "product_id": "dkp-2", "title": "هندزفری بلوتوث مدل دوم",
                "discount_percent": 50, "savings_toman": 300000,
                "catalog_best_selling_ranks_by_category": {
                    "11": {"rank": 19, "category_name": "هدفون", "observed_at": self.now.isoformat()}
                },
            },
            {
                "product_id": "dkp-1", "title": "هندزفری بلوتوث مدل اول",
                "discount_percent": 20, "savings_toman": 100000,
                "catalog_best_selling_ranks_by_category": {
                    "11": {"rank": 3, "category_name": "هدفون", "observed_at": self.now.isoformat()}
                },
            },
            {
                "product_id": "dkp-3", "title": "گوشی سامسونگ مدل سوم",
                "catalog_best_selling_ranks_by_category": {
                    "12": {"rank": 1, "category_name": "موبایل", "observed_at": self.now.isoformat()}
                },
            },
        ]
        report = build_demand_shadow_report(products, now=self.now)
        categories = {row["category_id"]: row for row in report["category_rankings"]}
        self.assertEqual(categories["11"]["products"][0]["product_id"], "dkp-1")
        self.assertEqual(categories["12"]["products"][0]["product_id"], "dkp-3")
        self.assertEqual(report["mode"], "shadow_only")
        self.assertFalse(report["live_ranking_changed"])
        self.assertEqual(report["global_cross_category_bestseller_rank"], "not_computed")

    def test_torob_matches_are_separate_from_digikala_rankings(self):
        snapshot = sanitize_torob_trends({
            "trends": [{"query": "هندزفری بلوتوث", "category_id": "5"}]
        }, self.now)
        report = build_demand_shadow_report([
            {
                "product_id": "dkp-1",
                "title": "هندزفری بلوتوثی انکر",
                "catalog_best_selling_ranks_by_category": {
                    "11": {"rank": 8, "category_name": "هدفون", "observed_at": self.now.isoformat()}
                },
            }
        ], snapshot, self.now)
        self.assertEqual(report["summary"]["products_with_fresh_digikala_rank"], 1)
        self.assertEqual(report["summary"]["products_with_strong_torob_trend_match"], 1)
        self.assertEqual(len(report["torob_trend_matches"]), 1)


    def test_enrich_market_prices_refreshes_trends_when_no_price_checks_are_due(self):
        state = {}
        with patch.object(
            radar_module,
            "_prepare_torob_mcp",
            return_value={"search_products", "product_details", "torob_trends"},
        ) as prepare, patch.object(
            radar_module,
            "_torob_tool",
            return_value={"trends": [{"query": "هندزفری بلوتوث", "category_id": "7"}]},
        ) as call:
            radar_module.enrich_market_prices([], state, now=self.now)
        prepare.assert_called_once()
        call.assert_called_once_with("torob_trends", {"limit": 30}, 10)
        self.assertEqual(state["torob_trends_snapshot"]["count"], 1)
        self.assertEqual(state["torob_trends_last_status"]["status"], "ok")

    def test_enrich_market_prices_reuses_fresh_trends_snapshot_without_network_calls(self):
        state = {
            "torob_trends_snapshot": sanitize_torob_trends(
                {"trends": [{"query": "هندزفری بلوتوث"}]},
                self.now - timedelta(hours=2),
            ),
            "torob_trends_next_attempt_at": (self.now + timedelta(hours=4)).isoformat(),
        }
        with patch.object(radar_module, "_prepare_torob_mcp") as prepare, patch.object(
            radar_module, "_torob_tool"
        ) as call:
            radar_module.enrich_market_prices([], state, now=self.now)
        prepare.assert_not_called()
        call.assert_not_called()

    def test_missing_torob_trends_tool_does_not_block_empty_market_queue(self):
        state = {}
        with patch.object(
            radar_module,
            "_prepare_torob_mcp",
            return_value={"search_products", "product_details"},
        ), patch.object(radar_module, "_torob_tool") as call:
            radar_module.enrich_market_prices([], state, now=self.now)
        call.assert_not_called()
        self.assertEqual(state["torob_trends_last_status"]["status"], "tool_not_available")

    def test_trends_expire_after_twelve_hours(self):
        snapshot = sanitize_torob_trends({
            "trends": [{"query": "هندزفری بلوتوث"}]
        }, self.now - timedelta(hours=12, minutes=1))
        self.assertEqual(torob_trends_snapshot_status(snapshot, self.now)[0], "stale")


if __name__ == "__main__":
    unittest.main()
