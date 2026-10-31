from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from . import parallel_catalog_sweep as sweep


class ParallelCatalogSweepTests(unittest.TestCase):
    def test_initial_queue_covers_categories_and_preserves_legacy_cursor(self):
        categories = [
            {"id": "1", "name": "mobile"},
            {"id": "2", "name": "home"},
            {"id": "3", "name": "fashion"},
        ]
        tasks = sweep.build_initial_page_queue(categories, legacy_category_index=1, legacy_page=7)
        self.assertEqual(
            [(row["category_id"], row["page"]) for row in tasks],
            [("2", 7), ("3", 1)],
        )

    def test_next_page_only_when_more_product_pages_exist(self):
        task = {"category_id": "12", "category_name": "x", "page": 2}
        self.assertEqual(sweep._next_page_task(task, total_pages=4, product_count=20)["page"], 3)
        self.assertIsNone(sweep._next_page_task(task, total_pages=2, product_count=20))
        self.assertIsNone(sweep._next_page_task(task, total_pages=4, product_count=0))
        self.assertIsNone(
            sweep._next_page_task({"category_id": "12", "page": 5000}, None, 20)
        )

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
            self.assertEqual(saved["stats"]["pages_scanned_total"], 1)


if __name__ == "__main__":
    unittest.main()
