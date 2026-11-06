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
        load_publication_catalog_context,
        is_initial_catalog_warmup,
        candidate_allowed_by_publication_context,
    )
except ImportError:
    from catalog_status_snapshot import (
        build_status_snapshot,
        candidate_matches_completed_snapshot,
        load_completed_candidates_snapshot,
        load_publication_catalog_context,
        is_initial_catalog_warmup,
        candidate_allowed_by_publication_context,
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
            "completed_category_ids": ["1", "2", "3"],
            "unqueryable_category_ids": [],
            "categories_total": 3,
            "categories_complete": 3,
            "categories_unqueryable": 0,
            "category_coverage_percent": 100,
            "pages_success": 120,
            "product_rows_success": 2400,
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

    def test_clean_snapshot_is_usable_while_next_sweep_is_running(self):
        state = {
            **self.state,
            "last_cycle_status": "in_progress",
            "last_cycle_completed_at": None,
            "last_cycle_categories_total": 3,
            "last_cycle_categories_complete": 1,
            "last_cycle_categories_unqueryable": 0,
            "parallel_cycle_started_at": "2026-11-06T16:00:00+00:00",
            "parallel_cycle_pages_success": 2,
            "parallel_cycle_completed_category_ids": ["1"],
            "parallel_pending_pages": [{"category_id": "1", "page": 3, "attempts": 0}],
            "stats": {"completed_cycles": 1},
        }
        status = build_status_snapshot(
            state,
            "2026-11-06T16:01:00+00:00",
            completed_candidates=self.candidates,
        )
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_completed_at"], self.completed_at)
        self.assertEqual(status["completed_candidates_count"], 2)
        self.assertEqual(status["last_cycle_status"], "in_progress")
        self.assertEqual(status["pending_page_count"], 1)

    def test_failed_new_cycle_does_not_erase_last_known_good_snapshot(self):
        failed = {
            **self.state,
            "last_cycle_status": "complete_with_gaps",
            "last_cycle_categories_complete": 2,
            "last_cycle_categories_unqueryable": 1,
            "last_cycle_category_coverage_percent": 66.67,
        }
        status = build_status_snapshot(failed, completed_candidates=self.candidates)
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_completed_at"], self.completed_at)
        self.assertEqual(status["last_cycle_status"], "complete_with_gaps")

    def test_category_set_must_still_match_the_snapshot(self):
        changed = {
            **self.state,
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "4"}],
        }
        status = build_status_snapshot(changed, completed_candidates=self.candidates)
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "unavailable")

    def test_candidate_snapshot_metadata_must_prove_full_coverage(self):
        for key, value in (
            ("cycle_status", "complete_with_gaps"),
            ("categories_unqueryable", 1),
            ("categories_complete", 2),
            ("category_coverage_percent", 99.9),
            ("pages_success", 0),
            ("completed_category_ids", ["1", "2"]),
        ):
            with self.subTest(key=key):
                changed = {**self.candidates, key: value}
                status = build_status_snapshot(
                    self.state, completed_candidates=changed
                )
                self.assertFalse(status["completed_candidates_snapshot_valid"])

    def test_candidate_snapshot_must_have_matching_ids_timestamps_and_rank_order(self):
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
        wrong_order = {
            **self.candidates,
            "candidates": list(reversed(self.candidates["candidates"])),
        }
        self.assertFalse(
            build_status_snapshot(self.state, completed_candidates=wrong_order)[
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

            tampered = {
                **self.candidates,
                "candidates": [
                    {**self.candidates["candidates"][0], "discount_percent": 97},
                    self.candidates["candidates"][1],
                ],
            }
            candidates_path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertIsNone(
                load_completed_candidates_snapshot(status_path, candidates_path)
            )

    def test_invalid_snapshot_file_does_not_enable_warmup_semantics(self):
        status = build_status_snapshot(
            self.state,
            completed_candidates={**self.candidates, "candidates": []},
        )
        self.assertTrue(status["completed_candidates_snapshot_present"])
        self.assertFalse(status["completed_candidates_snapshot_valid"])

    
    def test_initial_warmup_is_the_only_live_discovery_fallback(self):
        status = {
            "schema_version": 2,
            "full_catalog_mode": "all_categories_all_pages",
            "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "completed_candidates_snapshot_present": False,
            "completed_candidates_snapshot_valid": False,
            "last_clean_cycle_status": "unavailable",
            "last_clean_cycle_completed_at": None,
            "completed_cycles": 0,
        }
        self.assertTrue(is_initial_catalog_warmup(status))
        self.assertFalse(is_initial_catalog_warmup({**status, "completed_cycles": 1}))
        self.assertFalse(is_initial_catalog_warmup({**status, "completed_candidates_snapshot_present": True}))
        self.assertFalse(is_initial_catalog_warmup(None))

    def test_publication_context_requires_the_hash_verified_current_snapshot_after_warmup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            status_path = root / "status.json"
            candidates_path = root / "completed.json"
            status = build_status_snapshot(self.state, completed_candidates=self.candidates)
            status_path.write_text(json.dumps(status), encoding="utf-8")
            candidates_path.write_text(json.dumps(self.candidates), encoding="utf-8")

            context = load_publication_catalog_context(status_path, candidates_path)
            self.assertEqual(context["mode"], "full_catalog")
            self.assertTrue(candidate_allowed_by_publication_context(
                self.candidates["candidates"][0], context
            ))
            outside = {
                "product_id": "dkp-999",
                "catalog_cycle_completed_at": self.completed_at,
                "catalog_cycle_snapshot_rank": 999,
            }
            self.assertFalse(candidate_allowed_by_publication_context(outside, context))
            self.assertTrue(candidate_allowed_by_publication_context(
                {"product_id": "snp-123", "discount_percent": 80},
                context,
            ))

            tampered = {**self.candidates, "candidates": [
                {**self.candidates["candidates"][0], "discount_percent": 97},
                self.candidates["candidates"][1],
            ]}
            candidates_path.write_text(json.dumps(tampered), encoding="utf-8")
            blocked = load_publication_catalog_context(status_path, candidates_path)
            self.assertEqual(blocked["mode"], "blocked")
            self.assertFalse(candidate_allowed_by_publication_context(outside, blocked))

    def test_catalog_snapshot_expires_after_96_hours(self):
        status = build_status_snapshot(
            self.state,
            generated_at="2026-11-10T17:00:00+00:00",
            completed_candidates=self.candidates,
        )
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "unavailable")

    def test_sweep_workflow_persists_the_immutable_candidate_snapshot(self):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "offerchin-digikala-catalog-sweep.yml"
        )
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn(
            "if [[ -f affilio_radar/catalog_sweep_completed_candidates.json ]]; then "
            "git add affilio_radar/catalog_sweep_completed_candidates.json; fi",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
