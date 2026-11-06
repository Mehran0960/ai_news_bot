from __future__ import annotations

import unittest

try:
    from .catalog_status_snapshot import build_status_snapshot
except ImportError:  # unittest discovery from the workflow's affilio_radar working directory
    from catalog_status_snapshot import build_status_snapshot


class CatalogStatusSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "parallel_full_catalog_mode": "all_categories_all_pages",
            "parallel_scan_policy_version": "all_categories_all_pages_v2",
            "last_cycle_status": "complete",
            "last_cycle_completed_at": "2026-11-06T16:00:00+00:00",
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

    def test_clean_full_cycle_is_explicitly_eligible(self):
        status = build_status_snapshot(self.state, "2026-11-06T16:01:00+00:00")
        self.assertTrue(status["last_cycle_clean"])
        self.assertEqual(status["last_cycle_categories_complete"], 3)
        self.assertEqual(status["pending_page_count"], 1)

    def test_category_set_must_match_the_completed_cycle(self):
        changed = {
            **self.state,
            "last_cycle_category_ids": ["1", "2", "3"],
            "last_cycle_completed_category_ids": ["1", "2", "3"],
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "4"}],
        }
        self.assertFalse(build_status_snapshot(changed)["last_cycle_clean"])

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
                self.assertFalse(build_status_snapshot(state)["last_cycle_clean"])

    def test_partial_legacy_cycle_is_not_eligible(self):
        state = {**self.state, "parallel_scan_policy_version": "top_60_partial"}
        self.assertFalse(build_status_snapshot(state)["last_cycle_clean"])


if __name__ == "__main__":
    unittest.main()
