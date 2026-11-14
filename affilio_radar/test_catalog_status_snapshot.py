from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

try:
    from .catalog_status_snapshot import (
        build_status_snapshot,
        load_emergency_continuity_candidates,
        upgrade_legacy_demand_first_snapshot,
        candidate_matches_completed_snapshot,
        load_completed_candidates_snapshot,
        load_publication_catalog_context,
        is_initial_catalog_warmup,
        is_degraded_live_fallback_available,
        candidate_allowed_by_publication_context,
        _category_addition_budget,
    )
except ImportError:
    from catalog_status_snapshot import (
        build_status_snapshot,
        upgrade_legacy_demand_first_snapshot,
        candidate_matches_completed_snapshot,
        load_completed_candidates_snapshot,
        load_publication_catalog_context,
        is_initial_catalog_warmup,
        is_degraded_live_fallback_available,
        candidate_allowed_by_publication_context,
        _category_addition_budget,
    )


class CatalogStatusSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.status_time = datetime.now(timezone.utc)
        self.started_at = (self.status_time - timedelta(hours=4)).isoformat()
        self.completed_at = (self.status_time - timedelta(hours=1)).isoformat()
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
            "parallel_cycle_started_at": self.completed_at,
            "parallel_cycle_pages_success": 2,
            "parallel_cycle_completed_category_ids": ["1"],
            "parallel_cycle_unqueryable_category_ids": [],
            "parallel_pending_pages": [{"category_id": "1", "page": 3, "attempts": 0}],
            "parallel_known_category_ids": ["1", "2", "3"],
            "parallel_last_batch_pages": 480,
            "parallel_workers_used": 12,
            "parallel_worker_limit": 14,
            "parallel_last_batch_pages_per_second": 15.5,
            "parallel_last_batch_request_count": 480,
            "parallel_last_batch_request_p50_seconds": 0.55,
            "parallel_last_batch_request_p95_seconds": 1.8,
            "parallel_last_batch_request_max_seconds": 7.2,
            "parallel_last_batch_retries": 0,
            "parallel_last_batch_rate_limited": 0,
            "parallel_last_batch_timeout_retries": 0,
            "parallel_last_batch_http_5xx_retries": 0,
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "stats": {"completed_cycles": 1},
        }
        self.candidates = {
            "schema_version": 1,
            "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "candidate_order_policy": "catalog_demand_first_v1",
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
            "parallel_cycle_started_at": self.completed_at,
            "parallel_cycle_pages_success": 2,
            "parallel_cycle_completed_category_ids": ["1"],
            "parallel_pending_pages": [{"category_id": "1", "page": 3, "attempts": 0}],
            "stats": {"completed_cycles": 1},
        }
        status = build_status_snapshot(
            state,
            self.status_time.isoformat(),
            completed_candidates=self.candidates,
        )
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_completed_at"], self.completed_at)
        self.assertEqual(status["completed_candidates_count"], 2)
        self.assertEqual(status["last_cycle_status"], "in_progress")
        self.assertEqual(status["pending_page_count"], 1)
        self.assertEqual(status["last_batch_pages"], 480)
        self.assertEqual(status["last_batch_workers_used"], 12)
        self.assertEqual(status["next_worker_limit"], 14)
        self.assertEqual(status["last_batch_pages_per_second"], 15.5)
        self.assertEqual(status["last_batch_request_count"], 480)
        self.assertEqual(status["last_batch_request_p50_seconds"], 0.55)
        self.assertEqual(status["last_batch_request_p95_seconds"], 1.8)
        self.assertEqual(status["last_batch_request_max_seconds"], 7.2)
        self.assertEqual(status["last_batch_retries"], 0)
        self.assertEqual(status["last_batch_rate_limited"], 0)

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

    def test_category_removal_or_replacement_invalidates_the_snapshot(self):
        changed = {
            **self.state,
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "4"}],
        }
        status = build_status_snapshot(changed, completed_candidates=self.candidates)
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "unavailable")

    def test_small_number_of_new_categories_keeps_the_verified_snapshot_usable(self):
        changed = {
            **self.state,
            "categories": [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}],
        }
        status = build_status_snapshot(changed, completed_candidates=self.candidates)
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "complete")
        self.assertEqual(status["last_clean_cycle_categories_total"], 3)
        self.assertEqual(status["catalog_category_count"], 4)
        self.assertEqual(status["unscanned_new_category_count"], 1)
        self.assertEqual(status["unscanned_new_category_budget"], 1)

    def test_new_category_additions_above_one_percent_budget_are_blocked(self):
        changed = {
            **self.state,
            "categories": [{"id": str(value)} for value in range(1, 8)],
        }
        status = build_status_snapshot(changed, completed_candidates=self.candidates)
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "unavailable")

    def test_new_category_addition_budget_is_capped_at_fifty(self):
        self.assertEqual(_category_addition_budget(10000), 50)


    def test_legacy_full_demand_first_snapshot_is_migrated_without_resorting(self):
        rows = [
            {
                "product_id": "dkp-100",
                "source": "digikala_catalog_sweep",
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": 1,
                "catalog_rank_observed_at": self.completed_at,
                "catalog_best_selling_ranks_by_category": {
                    "1": {"rank": 1, "observed_at": self.completed_at}
                },
                "discount_percent": 10,
                "savings_toman": 10000,
                "catalog_cycle_completed_at": self.completed_at,
                "catalog_cycle_snapshot_rank": 1,
            },
            {
                "product_id": "dkp-200",
                "source": "digikala_catalog_sweep",
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": 45,
                "catalog_rank_observed_at": self.completed_at,
                "catalog_best_selling_ranks_by_category": {
                    "2": {"rank": 45, "observed_at": self.completed_at}
                },
                "discount_percent": 90,
                "savings_toman": 900000,
                "catalog_cycle_completed_at": self.completed_at,
                "catalog_cycle_snapshot_rank": 2,
            },
        ]
        legacy = {**self.candidates, "candidates": rows}
        legacy.pop("candidate_order_policy", None)

        upgraded, changed = upgrade_legacy_demand_first_snapshot(legacy)
        self.assertTrue(changed)
        self.assertEqual(upgraded["candidate_order_policy"], "catalog_demand_first_v1")
        self.assertEqual(
            [row["product_id"] for row in upgraded["candidates"]],
            ["dkp-100", "dkp-200"],
            "migration must preserve the historical bestseller-first order",
        )
        self.assertEqual(
            [row["catalog_cycle_snapshot_rank"] for row in upgraded["candidates"]],
            [1, 2],
        )
        status = build_status_snapshot(
            self.state, self.completed_at, completed_candidates=upgraded
        )
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["completed_candidates_count"], 2)

    def test_legacy_snapshot_migration_refuses_incomplete_or_unproven_rows(self):
        rows = []
        for index, source in enumerate(("digikala_catalog_sweep", "unknown_source"), start=1):
            rows.append({
                "product_id": f"dkp-{index * 100}",
                "source": source,
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": index,
                "catalog_rank_observed_at": self.completed_at,
                "catalog_best_selling_ranks_by_category": {
                    "1": {"rank": index, "observed_at": self.completed_at}
                },
                "discount_percent": 10,
                "savings_toman": 10000,
                "catalog_cycle_completed_at": self.completed_at,
                "catalog_cycle_snapshot_rank": index,
            })
        legacy = {**self.candidates, "candidates": rows}
        legacy.pop("candidate_order_policy", None)
        upgraded, changed = upgrade_legacy_demand_first_snapshot(legacy)
        self.assertFalse(changed)
        self.assertEqual(upgraded, legacy)

        incomplete = {**legacy, "categories_complete": 2}
        _unchanged, changed = upgrade_legacy_demand_first_snapshot(incomplete)
        self.assertFalse(changed)

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
        stale_at = (self.status_time - timedelta(days=5)).isoformat()
        stale = {
            **self.candidates,
            "cycle_completed_at": stale_at,
            "candidates": [
                {**row, "catalog_cycle_completed_at": stale_at}
                for row in self.candidates["candidates"]
            ],
        }
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

    def test_demand_first_snapshot_accepts_non_monotonic_discount_order(self):
        changed = {
            **self.candidates,
            "candidates": [
                {
                    **self.candidates["candidates"][0],
                    "discount_percent": 10,
                    "savings_toman": 100_000,
                },
                {
                    **self.candidates["candidates"][1],
                    "discount_percent": 80,
                    "savings_toman": 800_000,
                },
            ],
        }
        status = build_status_snapshot(self.state, completed_candidates=changed)
        self.assertTrue(status["completed_candidates_snapshot_valid"])

    def test_unknown_candidate_order_policy_is_rejected(self):
        changed = {**self.candidates, "candidate_order_policy": "unknown_policy"}
        status = build_status_snapshot(self.state, completed_candidates=changed)
        self.assertFalse(status["completed_candidates_snapshot_valid"])

    def test_valid_demand_first_snapshot_exposes_compact_preview(self):
        status = build_status_snapshot(
            self.state,
            self.status_time.isoformat(),
            completed_candidates=self.candidates,
        )
        self.assertTrue(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["completed_candidates_order_policy"], "catalog_demand_first_v1")
        self.assertEqual(status["top_candidates_preview_count"], 2)
        self.assertEqual(
            [row["product_id"] for row in status["top_candidates_preview"]],
            ["dkp-100", "dkp-200"],
        )
        self.assertEqual(
            [row["snapshot_rank"] for row in status["top_candidates_preview"]],
            [1, 2],
        )

    def test_invalid_or_legacy_snapshot_exposes_no_demand_first_preview(self):
        invalid = {**self.candidates, "candidates": []}
        status = build_status_snapshot(
            self.state,
            self.status_time.isoformat(),
            completed_candidates=invalid,
        )
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["top_candidates_preview_count"], 0)
        self.assertEqual(status["top_candidates_preview"], [])

        legacy = {key: value for key, value in self.candidates.items() if key != "candidate_order_policy"}
        legacy_status = build_status_snapshot(
            self.state,
            self.status_time.isoformat(),
            completed_candidates=legacy,
        )
        self.assertTrue(legacy_status["completed_candidates_snapshot_valid"])
        self.assertEqual(legacy_status["top_candidates_preview_count"], 0)
        self.assertEqual(legacy_status["top_candidates_preview"], [])

    def test_sweep_writer_declares_the_demand_first_order_policy(self):
        scanner = (
            Path(__file__).resolve().parent / "parallel_catalog_sweep.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"candidate_order_policy": "catalog_demand_first_v1"', scanner)

    def test_loader_accepts_small_new_category_additions_without_weakening_hash_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            status_path = root / "status.json"
            candidates_path = root / "completed.json"
            changed = {
                **self.state,
                "categories": [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}],
            }
            status = build_status_snapshot(changed, completed_candidates=self.candidates)
            status_path.write_text(json.dumps(status), encoding="utf-8")
            candidates_path.write_text(json.dumps(self.candidates), encoding="utf-8")

            loaded = load_completed_candidates_snapshot(status_path, candidates_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["candidate_count"], 2)
            self.assertTrue(candidate_matches_completed_snapshot(self.candidates["candidates"][0], loaded))

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
            degraded = load_publication_catalog_context(status_path, candidates_path)
            self.assertEqual(degraded["mode"], "degraded_live_fallback")
            self.assertFalse(candidate_allowed_by_publication_context(outside, degraded))

    def test_degraded_live_fallback_requires_a_complete_numeric_taxonomy_registry(self):
        status = {
            "schema_version": 2,
            "full_catalog_mode": "all_categories_all_pages",
            "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
            "last_clean_cycle_status": "unavailable",
            "completed_candidates_snapshot_present": True,
            "completed_candidates_snapshot_valid": False,
            "last_clean_cycle_completed_at": None,
            "catalog_category_count": 3,
            "catalog_category_ids": ["1", "2", "3"],
        }
        self.assertTrue(is_degraded_live_fallback_available(status))
        self.assertFalse(is_degraded_live_fallback_available({
            **status, "catalog_category_ids": ["1", "2"]
        }))
        self.assertFalse(is_degraded_live_fallback_available({
            **status, "catalog_category_ids": ["1", "2", "2"]
        }))
        self.assertFalse(is_degraded_live_fallback_available({
            **status, "catalog_category_ids": ["1", "2", "x"]
        }))
        self.assertFalse(is_degraded_live_fallback_available({
            **status, "scan_policy_version": "unknown"
        }))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            status_path = root / "status.json"
            candidates_path = root / "missing-candidates.json"
            status_path.write_text(json.dumps(status), encoding="utf-8")
            context = load_publication_catalog_context(status_path, candidates_path)
            self.assertEqual(context["mode"], "degraded_live_fallback")
            self.assertTrue(candidate_allowed_by_publication_context({
                "product_id": "dkp-123",
                "product_url": "https://www.digikala.com/product/dkp-123/",
            }, context))
            self.assertFalse(candidate_allowed_by_publication_context({
                "product_id": "dkp-123",
                "product_url": "https://example.com/product/dkp-123/",
            }, context))
            self.assertTrue(candidate_allowed_by_publication_context({
                "product_id": "snp-456",
                "product_url": "https://snappshop.ir/product/snp-456/",
            }, context))
            self.assertFalse(candidate_allowed_by_publication_context({
                "product_id": "other-789",
                "product_url": "https://example.com/product/789/",
            }, context))

    def test_catalog_snapshot_expires_after_96_hours(self):
        status = build_status_snapshot(
            self.state,
            generated_at=(datetime.fromisoformat(self.completed_at) + timedelta(hours=97)).isoformat(),
            completed_candidates=self.candidates,
        )
        self.assertFalse(status["completed_candidates_snapshot_valid"])
        self.assertEqual(status["last_clean_cycle_status"], "unavailable")



    def test_emergency_snapshot_is_hash_pinned_and_exposes_only_live_recheck_leads(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates_path = Path(temp) / "completed.json"
            payload = {
                **self.candidates,
                "candidates": [
                    {
                        **self.candidates["candidates"][0],
                        "product_url": "https://www.digikala.com/product/dkp-100/",
                        "title": "پاوربانک نمونه",
                        "brand": "نمونه",
                        "catalog_best_selling_rank": 1,
                        "catalog_rank_observed_at": self.completed_at,
                    },
                    {
                        **self.candidates["candidates"][1],
                        "product_url": "https://www.digikala.com/product/dkp-200/",
                        "title": "شارژر نمونه",
                        "brand": "برند نمونه",
                        "current_price": 1,
                        "original_price": 999999,
                        "availability": "in_stock",
                        "catalog_best_selling_rank": 2,
                        "catalog_rank_observed_at": self.completed_at,
                    },
                ],
            }
            status = build_status_snapshot(
                self.state, self.status_time.isoformat(), completed_candidates=payload
            )
            self.assertTrue(status["completed_candidates_snapshot_valid"])
            candidates_path.write_text(json.dumps(payload), encoding="utf-8")
            record = {
                "status": "active",
                "started_at": self.status_time.isoformat(),
                "expires_at": (self.status_time + timedelta(hours=72)).isoformat(),
                "baseline_clean_cycle_started_at": self.started_at,
                "baseline_clean_cycle_completed_at": self.completed_at,
                "baseline_snapshot_sha256": status["completed_candidates_sha256"],
                "baseline_snapshot_candidate_count": status["completed_candidates_count"],
                "candidate_cursor": 1,
            }

            loaded = load_emergency_continuity_candidates(
                record,
                candidates_path,
                now=self.status_time + timedelta(hours=8),
                limit=1,
            )
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["candidate_count"], 2)
            self.assertEqual(loaded["candidates"][0]["product_id"], "dkp-200")
            self.assertEqual(loaded["next_cursor"], 0)
            self.assertEqual(loaded["candidates"][0]["source"], "digikala_emergency_last_clean_snapshot")
            for stale_field in (
                "current_price", "original_price", "discount_percent",
                "savings_toman", "availability", "expires_at", "deal_expires_at",
            ):
                self.assertNotIn(stale_field, loaded["candidates"][0])

            expired = load_emergency_continuity_candidates(
                record,
                candidates_path,
                now=self.status_time + timedelta(hours=73),
                limit=1,
            )
            self.assertIsNone(expired)

    def test_emergency_snapshot_rejects_payload_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates_path = Path(temp) / "completed.json"
            candidates_path.write_text(json.dumps(self.candidates), encoding="utf-8")
            status = build_status_snapshot(
                self.state, self.status_time.isoformat(), completed_candidates=self.candidates
            )
            record = {
                "status": "active",
                "expires_at": (self.status_time + timedelta(hours=72)).isoformat(),
                "baseline_clean_cycle_started_at": self.started_at,
                "baseline_clean_cycle_completed_at": self.completed_at,
                "baseline_snapshot_sha256": status["completed_candidates_sha256"],
                "baseline_snapshot_candidate_count": status["completed_candidates_count"],
            }
            changed = {**self.candidates, "candidates": list(reversed(self.candidates["candidates"]))}
            candidates_path.write_text(json.dumps(changed), encoding="utf-8")
            loaded = load_emergency_continuity_candidates(
                record, candidates_path, now=self.status_time + timedelta(hours=1)
            )
            self.assertIsNone(loaded)

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
