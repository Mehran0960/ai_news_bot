from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from . import parallel_catalog_sweep as sweep
except ImportError:  # unittest discovery from the workflow's affilio_radar working directory
    import parallel_catalog_sweep as sweep


class ParallelCatalogSweepTests(unittest.TestCase):
    def test_parallel_candidate_buffer_keeps_global_highest_discounts(self):
        rows = [
            {"product_id": f"dkp-{i}", "catalog_category_id": "10", "catalog_category_ids": ["10"], "review_count": 10000-i, "discount_percent": 20, "savings_toman": 200_000}
            for i in range(1, 6)
        ] + [
            {"product_id": "dkp-20", "catalog_category_id": "20", "catalog_category_ids": ["20"], "review_count": 1, "discount_percent": 99, "savings_toman": 990_000},
            {"product_id": "dkp-30", "catalog_category_id": "30", "catalog_category_ids": ["30"], "review_count": 1, "discount_percent": 95, "savings_toman": 950_000},
        ]
        retained = sweep.base.retain_diverse_candidates(rows, limit=4)
        self.assertEqual([row["product_id"] for row in retained], ["dkp-20", "dkp-30", "dkp-1", "dkp-2"])

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
        self.assertEqual(state["parallel_scan_policy_version"], "all_categories_all_pages_v2")

    def test_parallel_queue_preserves_deep_pages_without_an_arbitrary_cap(self):
        state = {
            "categories": [{"id": "10", "name": "mobile"}],
            "parallel_queue_initialized": True,
            "parallel_known_category_ids": ["10"],
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
        self.assertEqual(captured["params"]["categories[]"], "123")
        self.assertEqual(captured["params"]["page"], 2)
        self.assertEqual(captured["params"]["sort"], 7)

    def test_persisted_page_queue_sweeps_leaf_page_one_before_parent_and_deeper_pages(self):
        state = {
            "categories": [
                {"id": "1", "name": "root", "parent_id": "", "depth": 0},
                {"id": "2", "name": "branch", "parent_id": "1", "depth": 1},
                {"id": "3", "name": "leaf", "parent_id": "2", "depth": 2},
            ],
            "parallel_queue_initialized": True,
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
                            "discount_percent": 60,
                            "review_count": 100,
                            "first_seen_at": datetime.now(timezone.utc).isoformat(),
                            "last_seen_at": datetime.now(timezone.utc).isoformat(),
                        }],
                        "total_pages": 2,
                    }
                return {
                    "kind": "retry",
                    "rows": [],
                    "status_code": 429,
                    "error": "rate_limited",
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


if __name__ == "__main__":
    unittest.main()
