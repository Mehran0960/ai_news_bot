from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from . import parallel_catalog_sweep as sweep
except ImportError:  # unittest discovery from the workflow's affilio_radar working directory
    import parallel_catalog_sweep as sweep


class ParallelCatalogSweepTests(unittest.TestCase):
    def test_legacy_worker_checkpoint_is_normalized_to_the_first_trial_level_once(self):
        legacy = {}
        self.assertEqual(sweep._apply_worker_ramp_policy(legacy, 13, 16), 12)
        self.assertEqual(
            legacy["parallel_worker_ramp_policy_version"],
            sweep.WORKER_RAMP_POLICY_VERSION,
        )
        # The marker prevents the one-time reset from undoing later 14/16 steps.
        self.assertEqual(sweep._apply_worker_ramp_policy(legacy, 14, 16), 14)
        self.assertEqual(sweep._apply_worker_ramp_policy(legacy, 16, 16), 16)

    def test_legacy_checkpoint_below_12_is_preserved_for_gradual_ramp(self):
        state = {}
        self.assertEqual(sweep._apply_worker_ramp_policy(state, 9, 16), 9)
        self.assertEqual(sweep._apply_worker_ramp_policy(state, 11, 16), 11)

    def test_legacy_checkpoint_respects_a_lower_requested_ceiling(self):
        state = {}
        self.assertEqual(sweep._apply_worker_ramp_policy(state, 13, 10), 10)

    def test_clean_worker_ramp_uses_the_12_14_16_trial_points(self):
        # The preceding legacy run may have left the saved limit at 11.
        self.assertEqual(sweep._next_worker_limit(11, 16, 0, 0), 12)
        self.assertEqual(sweep._next_worker_limit(12, 16, 0, 0), 14)
        self.assertEqual(sweep._next_worker_limit(14, 16, 0, 0), 16)
        self.assertEqual(sweep._next_worker_limit(16, 16, 0, 0), 16)
        self.assertEqual(sweep._next_worker_limit(10, 14, 0, 0), 12)
        self.assertEqual(sweep._next_worker_limit(12, 14, 0, 0), 14)
        self.assertEqual(sweep._next_worker_limit(12, 12, 0, 0), 12)

    def test_worker_controller_backs_off_on_rate_limits_and_transient_failures(self):
        self.assertEqual(sweep._next_worker_limit(12, 16, 1, 1), 10)
        self.assertEqual(sweep._next_worker_limit(12, 16, 3, 3), 6)
        self.assertEqual(sweep._next_worker_limit(12, 16, 0, 1), 11)
        self.assertEqual(sweep._next_worker_limit(12, 16, 0, 3), 6)
        self.assertEqual(sweep._next_worker_limit(2, 16, 3, 3), 2)

    def test_single_isolated_5xx_holds_capacity_but_repeated_5xx_backs_off(self):
        self.assertEqual(
            sweep._next_worker_limit(6, 16, 0, 1, http_5xx_retry_count=1),
            6,
        )
        self.assertEqual(
            sweep._next_worker_limit(12, 16, 0, 2, http_5xx_retry_count=2),
            11,
        )
        self.assertEqual(
            sweep._next_worker_limit(12, 16, 0, 3, http_5xx_retry_count=3),
            6,
        )

    def test_timeout_still_triggers_backoff_even_when_a_5xx_is_also_seen(self):
        self.assertEqual(
            sweep._next_worker_limit(
                12, 16, 0, 2,
                timeout_retry_count=1,
                http_5xx_retry_count=1,
            ),
            11,
        )

    def test_request_latency_percentiles_use_nearest_rank(self):
        self.assertEqual(sweep._percentile([0.25, 1.25], 0.50), 0.25)
        self.assertEqual(sweep._percentile([0.25, 1.25], 0.95), 1.25)
        self.assertEqual(sweep._percentile([], 0.95), 0.0)
    def test_parallel_candidate_buffer_keeps_demand_context_before_discount(self):
        rows = [
            {"product_id": f"dkp-{i}", "catalog_category_id": "10", "catalog_category_ids": ["10"], "review_count": 10000-i, "discount_percent": 20, "savings_toman": 200_000}
            for i in range(1, 6)
        ] + [
            {"product_id": "dkp-20", "catalog_category_id": "20", "catalog_category_ids": ["20"], "review_count": 1, "discount_percent": 99, "savings_toman": 990_000},
            {"product_id": "dkp-30", "catalog_category_id": "30", "catalog_category_ids": ["30"], "review_count": 1, "discount_percent": 95, "savings_toman": 950_000},
        ]
        retained = sweep.base.retain_diverse_candidates(rows, limit=4)
        self.assertEqual([row["product_id"] for row in retained], ["dkp-1", "dkp-2", "dkp-3", "dkp-4"])

    def test_fresh_digikala_bestseller_rank_precedes_a_larger_discount_in_shortlist(self):
        now = datetime.now(timezone.utc)
        rows = [
            {
                "product_id": "dkp-native-rank-4",
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": 4,
                "catalog_rank_observed_at": now.isoformat(),
                "catalog_best_selling_ranks_by_category": {
                    "10": {"rank": 4, "observed_at": now.isoformat(), "category_name": "گوشی"},
                },
                "discount_percent": 12,
                "savings_toman": 120_000,
            },
            {
                "product_id": "dkp-native-rank-55",
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": 55,
                "catalog_rank_observed_at": now.isoformat(),
                "catalog_best_selling_ranks_by_category": {
                    "20": {"rank": 55, "observed_at": now.isoformat(), "category_name": "خانه"},
                },
                "discount_percent": 35,
                "savings_toman": 350_000,
            },
            {
                "product_id": "dkp-no-fresh-rank",
                "review_count": 100,
                "rating": 4.0,
                "discount_percent": 99,
                "savings_toman": 990_000,
            },
        ]
        retained = sweep.base.retain_diverse_candidates(rows, limit=3)
        self.assertEqual(
            [row["product_id"] for row in retained],
            ["dkp-native-rank-4", "dkp-native-rank-55", "dkp-no-fresh-rank"],
        )

    def test_parallel_scan_summary_reports_the_real_demand_first_order(self):
        source = Path(sweep.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "sort=harmonic_four_factor,demand,affordability,generality,discount_value",
            source,
        )
        self.assertNotIn(
            "sort=discount_percent_desc,savings_toman_desc",
            source,
        )

    def test_initial_queue_starts_every_category_at_page_one_even_with_old_cursor(self):
        categories = [
            {"id": "1", "name": "mobile"},
            {"id": "2", "name": "home"},
            {"id": "3", "name": "fashion"},
        ]
        state = {
            "categories": categories,
            "category_index": 2,
            "page": 7,
            "parallel_queue_initialized": True,
            "parallel_pending_pages": [{"category_id": "3", "page": 3, "attempts": 2}],
            "parallel_known_category_ids": ["1", "2", "3"],
        }
        tasks = sweep._ensure_parallel_state(state)
        self.assertEqual({(row["category_id"], row["page"]) for row in tasks}, {("1", 1), ("2", 1), ("3", 1)})
        self.assertEqual(state["parallel_scan_policy_version"], "all_categories_all_pages_v3_cycle_snapshot")

    def test_full_catalog_counter_restarts_legacy_page_queue_for_exhaustive_cycle(self):
        state = {
            "categories": [{"id": "10", "name": "mobile"}],
            "parallel_queue_initialized": True,
            "parallel_scan_policy_version": "all_categories_all_pages_v2",
            "parallel_known_category_ids": ["10"],
            "parallel_pending_pages": [{"category_id": "10", "page": 7, "attempts": 2}],
            "parallel_cycle_pages_success": 41,
            "stats": {"completed_cycles": 9},
            "completed_cycles": 9,
            "last_cycle_completed_at": "2026-11-03T00:00:00+00:00",
        }
        queued = sweep._ensure_parallel_state(state)
        self.assertEqual([(row["category_id"], row["page"], row["attempts"]) for row in queued], [("10", 1, 0)])
        self.assertEqual(state["stats"]["completed_cycles"], 0)
        self.assertEqual(state["completed_cycles"], 0)
        self.assertEqual(state["legacy_completed_partial_sweeps_before_full_catalog"], 9)
        self.assertNotIn("last_cycle_completed_at", state)
        self.assertEqual(state["parallel_cycle_pages_success"], 0)

    def test_parallel_queue_preserves_deep_pages_without_an_arbitrary_cap(self):
        state = {
            "categories": [{"id": "10", "name": "mobile"}],
            "parallel_queue_initialized": True,
            "parallel_known_category_ids": ["10"],
            "parallel_scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "parallel_deep_pages_pruned": 0,
            "parallel_pending_pages": [
                {"category_id": "10", "page": 1, "attempts": 0},
                {"category_id": "10", "page": 3, "attempts": 0},
                {"category_id": "10", "page": 4, "attempts": 0},
                {"category_id": "10", "page": 500, "attempts": 2},
            ],
        }
        queued = sweep._ensure_parallel_state(state)
        self.assertEqual([(row["category_id"], row["page"]) for row in queued], [("10", 1), ("10", 3), ("10", 4), ("10", 500)])
        self.assertEqual(state["parallel_deep_pages_pruned"], 0)

    def test_fetch_page_requests_best_selling_order(self):
        captured = {}

        class Response:
            status_code = 404
        class Session:
            def get(self, url, params, timeout):
                captured.update({"url": url, "params": params, "timeout": timeout})
                return Response()

        with patch.object(sweep, "_session", return_value=Session()):
            result = sweep._fetch_page({"category_id": "123", "page": 2})

        self.assertEqual(result["kind"], "terminal")
        self.assertEqual(captured["url"], "https://api.digikala.com/v2/category/123/")
        self.assertEqual(captured["params"], {"page": 2, "sort": 5})

    def test_persisted_page_queue_sweeps_leaf_page_one_before_parent_and_deeper_pages(self):
        state = {
            "categories": [
                {"id": "1", "name": "root", "parent_id": "", "depth": 0},
                {"id": "2", "name": "branch", "parent_id": "1", "depth": 1},
                {"id": "3", "name": "leaf", "parent_id": "2", "depth": 2},
            ],
            "parallel_queue_initialized": True,
            "parallel_scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "parallel_known_category_ids": ["1", "2", "3"],
            "parallel_pending_pages": [
                {"category_id": "1", "page": 1, "attempts": 0},
                {"category_id": "2", "page": 1, "attempts": 0},
                {"category_id": "3", "page": 2, "attempts": 0},
                {"category_id": "3", "page": 1, "attempts": 0},
            ],
        }
        queued = sweep._ensure_parallel_state(state)
        self.assertEqual(
            [(row["category_id"], row["page"]) for row in queued],
            [("3", 1), ("2", 1), ("1", 1), ("3", 2)],
        )
        self.assertEqual(state["parallel_leaf_category_count"], 1)

    def test_next_page_only_when_more_product_pages_exist(self):
        task = {"category_id": "12", "category_name": "x", "page": 2}
        self.assertEqual(sweep._next_page_task(task, total_pages=4, product_count=20)["page"], 3)
        self.assertIsNone(sweep._next_page_task(task, total_pages=2, product_count=20))
        self.assertIsNone(sweep._next_page_task(task, total_pages=4, product_count=0))
        self.assertEqual(sweep._next_page_task({"category_id": "12", "page": 5000}, None, 20)["page"], 5001)
        self.assertEqual(sweep._next_page_task({"category_id": "12", "page": 3}, 200, 20)["page"], 4)

    def test_parallel_sweep_preserves_seen_candidate_after_live_card_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = root / "state.json"
            candidates_path = root / "candidates.json"
            publisher_state_path = root / "publisher.json"
            now = datetime.now(timezone.utc)
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
            changed = {
                **original,
                "current_price": 400_000,
                "discount_percent": 60,
                "savings_toman": 600_000,
                "last_seen_at": now.isoformat(),
            }
            state_path.write_text(json.dumps({
                "categories": [{"id": "10", "name": "mobile"}],
                "categories_refreshed_at": now.isoformat(),
                "parallel_queue_initialized": True,
                "parallel_scan_policy_version": "all_categories_all_pages_v2",
                "parallel_known_category_ids": ["10"],
                "parallel_pending_pages": [
                    {"category_id": "10", "category_name": "mobile", "page": 1, "attempts": 0}
                ],
                "parallel_cycle_completed_category_ids": [],
                "parallel_cycle_unqueryable_category_ids": [],
                "parallel_cycle_pages_success": 0,
                "parallel_cycle_product_rows_success": 0,
                "stats": {},
            }), encoding="utf-8")
            candidates_path.write_text(
                json.dumps({"candidates": [original]}, ensure_ascii=False),
                encoding="utf-8",
            )
            publisher_state_path.write_text(json.dumps({
                "catalog_sweep_handoff": {
                    "seen_ids": {
                        "dkp-55": {
                            "seen_at": (now - timedelta(hours=1)).isoformat(),
                            "fingerprint": sweep.base.catalog_handoff_fingerprint(original),
                        }
                    }
                }
            }), encoding="utf-8")

            def fake_fetch(task):
                return {"kind": "ok", "rows": [changed], "total_pages": 1}

            with patch.object(sweep.base, "refresh_categories", return_value=None):
                result = sweep.run_parallel_sweep(
                    pages_per_run=1,
                    workers=1,
                    state_path=state_path,
                    candidates_path=candidates_path,
                    publisher_state_path=publisher_state_path,
                    fetcher=fake_fetch,
                )

            self.assertEqual(result, 0)
            saved = json.loads(candidates_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["candidate_count"], 1)
            self.assertEqual(saved["candidates"][0]["product_id"], "dkp-55")
            self.assertEqual(saved["candidates"][0]["current_price"], 400_000)

    def test_parallel_run_persists_follow_up_and_retries_failed_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = root / "state.json"
            candidates_path = root / "candidates.json"
            publisher_state_path = root / "publisher.json"
            state_path.write_text(json.dumps({
                "categories": [
                    {"id": "10", "name": "mobile"},
                    {"id": "20", "name": "accessories"},
                ],
                "categories_refreshed_at": datetime.now(timezone.utc).isoformat(),
                "category_index": 0,
                "page": 1,
                "stats": {},
            }), encoding="utf-8")
            candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
            publisher_state_path.write_text("{}", encoding="utf-8")

            def fake_fetch(task):
                if task["category_id"] == "10":
                    return {
                        "kind": "ok",
                        "rows": [{
                            "product_id": "dkp-1",
                            "title": "نمونه محصول معتبر",
                            "current_price": 400_000,
                            "original_price": 1_000_000,
                            "discount_percent": 60,
                            "savings_toman": 600_000,
                            "review_count": 100,
                            "first_seen_at": datetime.now(timezone.utc).isoformat(),
                            "last_seen_at": datetime.now(timezone.utc).isoformat(),
                        }],
                        "total_pages": 2,
                        "elapsed_seconds": 0.25,
                    }
                return {
                    "kind": "retry",
                    "rows": [],
                    "status_code": 429,
                    "error": "rate_limited",
                    "elapsed_seconds": 1.25,
                }

            result = sweep.run_parallel_sweep(
                pages_per_run=2,
                workers=2,
                state_path=state_path,
                candidates_path=candidates_path,
                publisher_state_path=publisher_state_path,
                fetcher=fake_fetch,
            )
            self.assertEqual(result, 0)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            pending = {
                (row["category_id"], row["page"])
                for row in saved["parallel_pending_pages"]
            }
            self.assertIn(("10", 2), pending)
            self.assertIn(("20", 1), pending)
            self.assertGreaterEqual(saved["parallel_last_batch_retries"], 1)
            candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate_data["candidates"][0]["product_id"], "dkp-1")
            candidate = candidate_data["candidates"][0]
            self.assertEqual(candidate["catalog_sort_mode"], "best_selling")
            self.assertEqual(candidate["catalog_best_selling_rank"], 1)
            self.assertEqual(candidate["catalog_best_selling_category_id"], "10")
            self.assertEqual(saved["stats"]["pages_scanned_total"], 1)
            for metric in (
                "parallel_last_batch_fetch_seconds",
                "parallel_last_batch_processing_seconds",
                "parallel_last_batch_candidate_write_seconds",
                "parallel_last_batch_pages_per_second",
                "parallel_last_batch_rows_per_second",
                "parallel_last_batch_candidate_file_bytes",
                "parallel_last_batch_request_count",
                "parallel_last_batch_request_p50_seconds",
                "parallel_last_batch_request_p95_seconds",
                "parallel_last_batch_request_max_seconds",
                "parallel_last_batch_timeout_retries",
                "parallel_last_batch_http_5xx_retries",
            ):
                self.assertIn(metric, saved)
                self.assertGreaterEqual(saved[metric], 0)
            self.assertGreater(saved["parallel_last_batch_pages_per_second"], 0)
            self.assertGreater(saved["parallel_last_batch_rows_per_second"], 0)
            self.assertGreater(saved["parallel_last_batch_candidate_file_bytes"], 0)
            self.assertEqual(saved["parallel_last_batch_request_count"], 2)
            self.assertEqual(saved["parallel_last_batch_request_p50_seconds"], 0.25)
            self.assertEqual(saved["parallel_last_batch_request_p95_seconds"], 1.25)
            self.assertEqual(saved["parallel_last_batch_request_max_seconds"], 1.25)


    def test_clean_batch_records_actual_workers_and_increases_next_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = datetime.now(timezone.utc).isoformat()
            categories = [{"id": str(value), "name": f"category-{value}"} for value in (10, 20, 30)]
            state_path = root / "state.json"
            candidates_path = root / "candidates.json"
            publisher_state_path = root / "publisher.json"
            state_path.write_text(json.dumps({
                "categories": categories,
                "categories_refreshed_at": now,
                "parallel_queue_initialized": True,
                "parallel_scan_policy_version": "all_categories_all_pages_v2",
                "parallel_known_category_ids": ["10", "20", "30"],
                "parallel_pending_pages": [
                    {"category_id": str(value), "category_name": f"category-{value}", "page": 1, "attempts": 0}
                    for value in (10, 20, 30)
                ],
                "parallel_cycle_completed_category_ids": [],
                "parallel_cycle_unqueryable_category_ids": [],
                "parallel_cycle_pages_success": 0,
                "parallel_cycle_product_rows_success": 0,
                "parallel_worker_limit": 2,
                "stats": {},
            }), encoding="utf-8")
            candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
            publisher_state_path.write_text("{}", encoding="utf-8")

            with patch.object(sweep.base, "refresh_categories", return_value=None):
                result = sweep.run_parallel_sweep(
                    pages_per_run=3,
                    workers=5,
                    state_path=state_path,
                    candidates_path=candidates_path,
                    publisher_state_path=publisher_state_path,
                    fetcher=lambda task: {"kind": "ok", "rows": [], "total_pages": 1},
                )

            self.assertEqual(result, 0)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["parallel_workers_used"], 2)
            self.assertEqual(saved["parallel_worker_limit"], 4)

    def test_terminal_deep_page_is_a_catalog_gap_not_a_clean_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = datetime.now(timezone.utc).isoformat()
            state_path = root / "state.json"
            candidates_path = root / "candidates.json"
            publisher_state_path = root / "publisher.json"
            state_path.write_text(json.dumps({
                "categories": [{"id": "10", "name": "mobile"}],
                "categories_refreshed_at": now,
                "parallel_queue_initialized": True,
                "parallel_scan_policy_version": "all_categories_all_pages_v2",
                "parallel_full_catalog_mode": "all_categories_all_pages",
                "parallel_known_category_ids": ["10"],
                "parallel_pending_pages": [
                    {"category_id": "10", "category_name": "mobile", "page": 2, "attempts": 0}
                ],
                "parallel_cycle_completed_category_ids": [],
                "parallel_cycle_unqueryable_category_ids": [],
                "parallel_cycle_pages_success": 1,
                "parallel_cycle_product_rows_success": 20,
                "stats": {},
            }), encoding="utf-8")
            candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
            publisher_state_path.write_text("{}", encoding="utf-8")

            with patch.object(sweep.base, "refresh_categories", return_value=None):
                result = sweep.run_parallel_sweep(
                    pages_per_run=1,
                    workers=1,
                    state_path=state_path,
                    candidates_path=candidates_path,
                    publisher_state_path=publisher_state_path,
                    fetcher=lambda task: {
                        "kind": "terminal", "status_code": 404, "rows": []
                    },
                )

            self.assertEqual(result, 0)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["parallel_cycle_unqueryable_category_ids"], ["10"])
            self.assertEqual(saved["parallel_cycle_completed_category_ids"], [])
            self.assertEqual(saved["stats"]["unqueryable_categories_total"], 1)

    def test_single_429_reduces_next_limit_but_keeps_actual_batch_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = datetime.now(timezone.utc).isoformat()
            category_ids = (10, 20, 30, 40)
            categories = [{"id": str(value), "name": f"category-{value}"} for value in category_ids]
            state_path = root / "state.json"
            candidates_path = root / "candidates.json"
            publisher_state_path = root / "publisher.json"
            state_path.write_text(json.dumps({
                "categories": categories,
                "categories_refreshed_at": now,
                "parallel_queue_initialized": True,
                "parallel_scan_policy_version": "all_categories_all_pages_v2",
                "parallel_known_category_ids": [str(value) for value in category_ids],
                "parallel_pending_pages": [
                    {"category_id": str(value), "category_name": f"category-{value}", "page": 1, "attempts": 0}
                    for value in category_ids
                ],
                "parallel_cycle_completed_category_ids": [],
                "parallel_cycle_unqueryable_category_ids": [],
                "parallel_cycle_pages_success": 0,
                "parallel_cycle_product_rows_success": 0,
                "parallel_worker_limit": 4,
                "stats": {},
            }), encoding="utf-8")
            candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
            publisher_state_path.write_text("{}", encoding="utf-8")

            def fake_fetch(task):
                if task["category_id"] == "40":
                    return {"kind": "retry", "rows": [], "status_code": 429, "error": "rate_limited"}
                return {"kind": "ok", "rows": [], "total_pages": 1}

            with patch.object(sweep.base, "refresh_categories", return_value=None):
                result = sweep.run_parallel_sweep(
                    pages_per_run=4,
                    workers=8,
                    state_path=state_path,
                    candidates_path=candidates_path,
                    publisher_state_path=publisher_state_path,
                    fetcher=fake_fetch,
                )

            self.assertEqual(result, 0)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["parallel_last_batch_rate_limited"], 1)
            self.assertEqual(saved["parallel_workers_used"], 4)
            self.assertEqual(saved["parallel_worker_limit"], 2)


if __name__ == "__main__":
    unittest.main()
