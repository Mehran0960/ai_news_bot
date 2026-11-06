from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from .catalog_status_snapshot import (
        build_status_snapshot,
        candidate_matches_completed_snapshot,
        load_completed_candidates_snapshot,
    )
except ImportError:  # unittest discovery from the workflow's affilio_radar working directory
    from catalog_status_snapshot import (
        build_status_snapshot,
        candidate_matches_completed_snapshot,
        load_completed_candidates_snapshot,
    )


class CatalogStatusSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.started_at = "2026-11-06T12:00:00+00:00"
        self.completed_at = "2026-11-06T16:00:00+00:00"
        self.state = {
            "parallel_full_catalog_mode": "all_categories_all_pages",
            "parallel_scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "last_cycle_status": "complete",
            "last_cycle_started_at": self.started_at,
            "last_cycle_completed_at": self.completed_at,
            "last_cycle_category_ids": ["1", "2", "3"],
            "last_cycle_completed_category_ids": ["1", "2", "3"],
            "last_cycle_unqueryable_category_ids": [],
            "last_cycle_categories_total": 3,
            "last_cycle_categories_complete": 3,
            "last_cycle_categories_unqueryable": 0,
            "last_cycle_category_coverage_percent": 100,
            "last_cycle_pages_success": 120,
            "last_cycle_product_rows_success": 2400,
            "parallel_cycle_started_at": "2026-11-06T16:00:00+00:00",
            "parallel_cycle_pages_success": 2,
            "parallel_cycle_completed_category_ids": ["1"],
            "parallel_cycle_unqueryable_category_ids": [],
            "parallel_pending_pages": [{"category_id": "1", "page": 3, "attempts": 0}],
            "parallel_known_category_ids": ["1", "2", "3"],
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "stats": {"completed_cycles": 1},
        }
        self.candidates = {
            "schema_version": 1,
            "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "cycle_status": "complete",
            "cycle_started_at": self.started_at,
            "cycle_completed_at": self.completed_at,
            "category_ids": ["1", "2", "3"],
            "candidate_count": 2,
            "candidates": [
                {
                    "product_id": "dkp-100",
                    "discount_percent": 90,
                    "savings_toman": 900000,
                    "catalog_cycle_completed_at": self.completed_at,
                    "catalog_cycle_snapshot_rank": 1,
                },
                {
                    "product_id": "dkp-200",
                    "discount_percent": 80,
                    "savings_toman": 800000,
                    "catalog_cycle_completed_at": self.completed_at,
                    "catalog_cycle_snapshot_rank": 2,
                },
            ],
        }

    def test_clean_full_cycle_and_matching_candidate_snapshot_are_eligible(self):
        status = build_status_snapshot(
            self.state,
            "2026-11-06T16:01:00+00:00",
            completed_candidates=self.candidates,
        )
        self.assertTrue(status["last_cycle_clean"])
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["completed_candidates_count"], 2)
        self.assertEqual(status["last_cycle_categories_complete"], 3)
        self.assertEqual(status["pending_page_count"], 1)

    def test_category_set_must_match_the_completed_cycle(self):
        changed = {
            **self.state,
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "4"}],
        }
        status = build_status_snapshot(changed, completed_candidates=self.candidates)
        self.assertFalse(status["last_cycle_clean"])
        self.assertFalse(status["completed_candidates_snapshot_valid"])

    def test_any_gap_prevents_clean_full_cycle(self):
        for key, value in (
            ("last_cycle_status", "complete_with_gaps"),
            ("last_cycle_categories_unqueryable", 1),
            ("last_cycle_categories_complete", 2),
            ("last_cycle_category_coverage_percent", 99.9),
            ("last_cycle_pages_success", 0),
        ):
            with self.subTest(key=key):
                state = {**self.state, key: value}
                status = build_status_snapshot(state, completed_candidates=self.candidates)
                self.assertFalse(status["last_cycle_clean"])
                self.assertFalse(status["completed_candidates_snapshot_valid"])

    def test_candidate_snapshot_must_match_exact_cycle_and_all_categories(self):
        stale = {**self.candidates, "cycle_completed_at": "2026-11-06T15:00:00+00:00"}
        self.assertFalse(
            build_status_snapshot(self.state, completed_candidates=stale)[
                "completed_candidates_snapshot_valid"
            ]
        )
        wrong_categories = {**self.candidates, "category_ids": ["1", "2"]}
        self.assertFalse(
            build_status_snapshot(self.state, completed_candidates=wrong_categories)[
                "completed_candidates_snapshot_valid"
            ]
        )
        wrong_rank = {
            **self.candidates,
            "candidates": [
                {**self.candidates["candidates"][0], "catalog_cycle_snapshot_rank": 2},
                self.candidates["candidates"][1],
            ],
        }
        self.assertFalse(
            build_status_snapshot(self.state, completed_candidates=wrong_rank)[
                "completed_candidates_snapshot_valid"
            ]
        )

    def test_loaded_snapshot_is_hash_verified_and_provenance_matched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            status_path = root / "status.json"
            candidates_path = root / "completed.json"
            status = build_status_snapshot(self.state, completed_candidates=self.candidates)
            status_path.write_text(json.dumps(status), encoding="utf-8")
            candidates_path.write_text(json.dumps(self.candidates), encoding="utf-8")

            loaded = load_completed_candidates_snapshot(status_path, candidates_path)
            self.assertIsNotNone(loaded)
            self.assertTrue(
                candidate_matches_completed_snapshot(
                    self.candidates["candidates"][0], loaded
                )
            )
            self.assertFalse(
                candidate_matches_completed_snapshot(
                    {
                        **self.candidates["candidates"][0],
                        "catalog_cycle_completed_at": "2026-11-05T00:00:00+00:00",
                    },
                    loaded,
                )
            )

            tampered = {**self.candidates, "candidates": [self.candidates["candidates"][1]]}
            candidates_path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertIsNone(load_completed_candidates_snapshot(status_path, candidates_path))

    def test_partial_legacy_cycle_is_not_eligible(self):
        state = {**self.state, "parallel_scan_policy_version": "top_60_partial"}
        status = build_status_snapshot(state, completed_candidates=self.candidates)
        self.assertFalse(status["last_cycle_clean"])
        self.assertFalse(status["completed_candidates_snapshot_valid"])


if __name__ == "__main__":
    unittest.main()
