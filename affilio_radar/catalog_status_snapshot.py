#!/usr/bin/env python3
"""Build and validate compact, fail-closed metadata for complete catalog-cycle snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "catalog_sweep_state.json"
STATUS_PATH = ROOT / "catalog_sweep_status.json"
COMPLETED_CANDIDATES_PATH = ROOT / "catalog_sweep_completed_candidates.json"
SCAN_POLICY_VERSION = "all_categories_all_pages_v3_cycle_snapshot"


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _candidate_snapshot_details(
    state: dict[str, Any],
    completed_candidates: Any,
) -> tuple[bool, str, int, list[str]]:
    """Validate the immutable candidate snapshot against the exact completed cycle."""
    if not isinstance(completed_candidates, dict):
        return False, "", 0, []
    cycle_at = str(state.get("last_cycle_completed_at") or "")
    cycle_started_at = str(state.get("last_cycle_started_at") or "")
    category_ids = sorted(
        {str(value) for value in state.get("last_cycle_category_ids", []) if str(value).isdigit()},
        key=lambda value: int(value),
    )
    rows = completed_candidates.get("candidates")
    if not isinstance(rows, list):
        return False, "", 0, []
    snapshot_ids: list[str] = []
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return False, "", 0, []
        product_id = str(row.get("product_id") or "")
        if not re.fullmatch(r"dkp-\d{1,12}", product_id):
            return False, "", 0, []
        if str(row.get("catalog_cycle_completed_at") or "") != cycle_at:
            return False, "", 0, []
        if _integer(row.get("catalog_cycle_snapshot_rank")) != rank:
            return False, "", 0, []
        snapshot_ids.append(product_id)
    if len(snapshot_ids) != len(set(snapshot_ids)):
        return False, "", 0, []
    snapshot_category_ids = sorted(
        {str(value) for value in completed_candidates.get("category_ids", []) if str(value).isdigit()},
        key=lambda value: int(value),
    )
    valid = bool(
        completed_candidates.get("schema_version") == 1
        and completed_candidates.get("scan_policy_version") == SCAN_POLICY_VERSION
        and completed_candidates.get("cycle_status") == "complete"
        and str(completed_candidates.get("cycle_started_at") or "") == cycle_started_at
        and str(completed_candidates.get("cycle_completed_at") or "") == cycle_at
        and snapshot_category_ids == category_ids
        and _integer(completed_candidates.get("candidate_count"), -1) == len(rows)
        and bool(cycle_at)
        and bool(cycle_started_at)
    )
    digest = hashlib.sha256(_canonical_json(completed_candidates)).hexdigest() if valid else ""
    return valid, digest, len(rows), snapshot_ids


def build_status_snapshot(
    state: dict[str, Any],
    generated_at: str | None = None,
    completed_candidates: Any = None,
) -> dict[str, Any]:
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    categories = state.get("categories") if isinstance(state.get("categories"), list) else []
    queue = state.get("parallel_pending_pages") if isinstance(state.get("parallel_pending_pages"), list) else []
    category_ids = {
        str(row.get("id")) for row in categories
        if isinstance(row, dict) and str(row.get("id") or "").isdigit()
    }
    last_cycle_category_ids = {
        str(value) for value in state.get("last_cycle_category_ids", [])
        if str(value).isdigit()
    }
    last_cycle_completed_ids = {
        str(value) for value in state.get("last_cycle_completed_category_ids", [])
        if str(value).isdigit()
    }
    last_cycle_unqueryable_ids = {
        str(value) for value in state.get("last_cycle_unqueryable_category_ids", [])
        if str(value).isdigit()
    }
    total = _integer(state.get("last_cycle_categories_total"))
    completed_count = _integer(state.get("last_cycle_categories_complete"))
    unqueryable_count = _integer(state.get("last_cycle_categories_unqueryable"))
    coverage = _number(state.get("last_cycle_category_coverage_percent"))
    pages = _integer(state.get("last_cycle_pages_success"))
    cycles = _integer(stats.get("completed_cycles", state.get("completed_cycles")))
    completed_at = str(state.get("last_cycle_completed_at") or "")
    cycle_status = str(state.get("last_cycle_status") or "in_progress")

    clean = bool(
        state.get("parallel_full_catalog_mode") == "all_categories_all_pages"
        and state.get("parallel_scan_policy_version") == SCAN_POLICY_VERSION
        and cycle_status == "complete"
        and total > 0
        and completed_count == total
        and unqueryable_count == 0
        and coverage >= 100
        and pages > 0
        and cycles > 0
        and completed_at
        and len(last_cycle_category_ids) == total
        and len(last_cycle_completed_ids) == total
        and last_cycle_category_ids == last_cycle_completed_ids
        and not last_cycle_unqueryable_ids
        and category_ids == last_cycle_category_ids
    )
    candidate_valid, candidate_sha, candidate_count, candidate_ids = (
        _candidate_snapshot_details(state, completed_candidates)
    )
    candidate_valid = bool(clean and candidate_valid)
    retries = sum(
        1 for item in queue
        if isinstance(item, dict) and _integer(item.get("attempts")) > 0
    )
    generated = generated_at or datetime.now(timezone.utc).isoformat()

    return {
        "schema_version": 2,
        "generated_at": generated,
        "full_catalog_mode": str(state.get("parallel_full_catalog_mode") or ""),
        "scan_policy_version": str(state.get("parallel_scan_policy_version") or ""),
        "last_cycle_status": cycle_status,
        "last_cycle_clean": clean,
        "last_cycle_started_at": state.get("last_cycle_started_at"),
        "last_cycle_completed_at": completed_at or None,
        "catalog_category_ids": sorted(category_ids, key=lambda value: int(value)),
        "last_cycle_category_ids": sorted(last_cycle_category_ids, key=lambda value: int(value)),
        "last_cycle_completed_category_ids": sorted(last_cycle_completed_ids, key=lambda value: int(value)),
        "last_cycle_unqueryable_category_ids": sorted(last_cycle_unqueryable_ids, key=lambda value: int(value)),
        "last_cycle_categories_total": total,
        "last_cycle_categories_complete": completed_count,
        "last_cycle_categories_unqueryable": unqueryable_count,
        "last_cycle_category_coverage_percent": coverage,
        "last_cycle_pages_success": pages,
        "last_cycle_product_rows_success": _integer(state.get("last_cycle_product_rows_success")),
        "completed_cycles": cycles,
        "completed_candidates_snapshot_valid": candidate_valid,
        "completed_candidates_cycle_at": completed_at if candidate_valid else None,
        "completed_candidates_count": candidate_count if candidate_valid else 0,
        "completed_candidates_ids": candidate_ids if candidate_valid else [],
        "completed_candidates_sha256": candidate_sha if candidate_valid else "",
        "current_cycle_started_at": state.get("parallel_cycle_started_at"),
        "current_cycle_pages_success": _integer(state.get("parallel_cycle_pages_success")),
        "current_cycle_categories_complete": len(state.get("parallel_cycle_completed_category_ids", [])),
        "current_cycle_categories_unqueryable": len(state.get("parallel_cycle_unqueryable_category_ids", [])),
        "pending_page_count": len(queue),
        "pending_retry_pages": retries,
        "catalog_category_count": len(category_ids),
        "known_category_count": len(state.get("parallel_known_category_ids", [])),
        "last_batch_at": state.get("parallel_last_batch_at"),
        "last_error": str(state.get("last_error") or "")[:240],
    }


def load_completed_candidates_snapshot(
    status_path: Path = STATUS_PATH,
    candidates_path: Path = COMPLETED_CANDIDATES_PATH,
) -> dict[str, Any] | None:
    """Return only a hash-verified, fully scanned, immutable candidate snapshot."""
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        candidates_payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(status, dict) or not isinstance(candidates_payload, dict):
        return None
    if (
        status.get("schema_version") != 2
        or status.get("last_cycle_clean") is not True
        or status.get("completed_candidates_snapshot_valid") is not True
        or status.get("scan_policy_version") != SCAN_POLICY_VERSION
    ):
        return None
    cycle_at = str(status.get("last_cycle_completed_at") or "")
    if not cycle_at or str(status.get("completed_candidates_cycle_at") or "") != cycle_at:
        return None
    category_ids = status.get("last_cycle_category_ids")
    if not isinstance(category_ids, list) or category_ids != status.get("catalog_category_ids"):
        return None
    valid, digest, count, product_ids = _candidate_snapshot_details(
        {
            "last_cycle_completed_at": cycle_at,
            "last_cycle_started_at": status.get("last_cycle_started_at"),
            "last_cycle_category_ids": category_ids,
        },
        candidates_payload,
    )
    if not valid:
        return None
    if count != _integer(status.get("completed_candidates_count"), -1):
        return None
    if digest != str(status.get("completed_candidates_sha256") or ""):
        return None
    status_ids = status.get("completed_candidates_ids")
    if not isinstance(status_ids, list) or status_ids != product_ids:
        return None
    rows = candidates_payload.get("candidates")
    by_id = {str(row.get("product_id")): row for row in rows if isinstance(row, dict)}
    return {
        "cycle_completed_at": cycle_at,
        "cycle_started_at": str(candidates_payload.get("cycle_started_at") or ""),
        "candidate_ids": set(product_ids),
        "candidate_by_id": by_id,
        "candidates": rows,
        "candidate_count": count,
        "status": status,
    }


def candidate_matches_completed_snapshot(
    candidate: Any,
    snapshot: dict[str, Any] | None,
) -> bool:
    if not isinstance(candidate, dict) or not isinstance(snapshot, dict):
        return False
    product_id = str(candidate.get("product_id") or "")
    if not product_id or product_id not in snapshot.get("candidate_ids", set()):
        return False
    if str(candidate.get("catalog_cycle_completed_at") or "") != str(snapshot.get("cycle_completed_at") or ""):
        return False
    try:
        rank = int(candidate.get("catalog_cycle_snapshot_rank") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    expected = snapshot.get("candidate_by_id", {}).get(product_id)
    return bool(
        rank > 0
        and isinstance(expected, dict)
        and rank == _integer(expected.get("catalog_cycle_snapshot_rank"))
    )


def write_status_snapshot(
    state_path: Path = STATE_PATH,
    status_path: Path = STATUS_PATH,
    completed_candidates_path: Path = COMPLETED_CANDIDATES_PATH,
) -> dict[str, Any]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot_read_catalog_state:{type(exc).__name__}") from exc
    try:
        completed_candidates = json.loads(completed_candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        completed_candidates = None
    if not isinstance(state, dict):
        raise RuntimeError("catalog_state_not_object")
    snapshot = build_status_snapshot(state, completed_candidates=completed_candidates)
    status_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "OFFERCHIN_CATALOG_STATUS "
        f"clean={snapshot['last_cycle_clean']} "
        f"candidate_snapshot_valid={snapshot['completed_candidates_snapshot_valid']} "
        f"cycle_status={snapshot['last_cycle_status']} "
        f"completed_at={snapshot['last_cycle_completed_at']} "
        f"categories={snapshot['last_cycle_categories_complete']}/{snapshot['last_cycle_categories_total']} "
        f"candidates={snapshot['completed_candidates_count']} "
        f"pending_pages={snapshot['pending_page_count']} "
        f"retry_pages={snapshot['pending_retry_pages']}"
    )
    return snapshot


if __name__ == "__main__":
    write_status_snapshot()
