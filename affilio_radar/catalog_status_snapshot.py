#!/usr/bin/env python3
"""Build a small, verifiable marker for the last known-good full catalog snapshot."""
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


def _sorted_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids = [str(item) for item in value]
    if not ids or any(not item.isdigit() for item in ids) or len(ids) != len(set(ids)):
        return []
    return sorted(ids, key=int)


def _valid_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except (TypeError, ValueError, OverflowError):
        return False


def _candidate_snapshot_details(payload: Any) -> dict[str, Any]:
    """Validate a frozen snapshot on its own, not against the scan currently in progress."""
    empty = {
        "present": isinstance(payload, dict),
        "valid": False,
        "sha256": "",
        "candidate_count": 0,
        "candidate_ids": [],
        "category_ids": [],
        "completed_category_ids": [],
        "unqueryable_category_ids": [],
        "cycle_started_at": "",
        "cycle_completed_at": "",
        "categories_total": 0,
        "categories_complete": 0,
        "categories_unqueryable": 0,
        "category_coverage_percent": 0.0,
        "pages_success": 0,
        "product_rows_success": 0,
    }
    if not isinstance(payload, dict):
        return empty

    rows = payload.get("candidates")
    if not isinstance(rows, list):
        return empty

    cycle_started = str(payload.get("cycle_started_at") or "")
    cycle_completed = str(payload.get("cycle_completed_at") or "")
    category_ids = _sorted_ids(payload.get("category_ids"))
    completed_ids = _sorted_ids(payload.get("completed_category_ids"))
    unqueryable_ids = _sorted_ids(payload.get("unqueryable_category_ids"))
    categories_total = _integer(payload.get("categories_total"))
    categories_complete = _integer(payload.get("categories_complete"))
    categories_unqueryable = _integer(payload.get("categories_unqueryable"))
    coverage = _number(payload.get("category_coverage_percent"))
    pages_success = _integer(payload.get("pages_success"))
    product_rows_success = _integer(payload.get("product_rows_success"))

    candidate_ids: list[str] = []
    previous_sort_key: tuple[int, int] | None = None
    rows_valid = True
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            rows_valid = False
            break
        product_id = str(row.get("product_id") or "")
        if not re.fullmatch(r"dkp-\d{1,12}", product_id):
            rows_valid = False
            break
        if str(row.get("catalog_cycle_completed_at") or "") != cycle_completed:
            rows_valid = False
            break
        if _integer(row.get("catalog_cycle_snapshot_rank")) != rank:
            rows_valid = False
            break
        discount = _integer(row.get("discount_percent"))
        savings = max(0, _integer(row.get("savings_toman")))
        if discount < 1:
            rows_valid = False
            break
        sort_key = (discount, savings)
        if previous_sort_key is not None and sort_key > previous_sort_key:
            rows_valid = False
            break
        previous_sort_key = sort_key
        candidate_ids.append(product_id)

    valid = bool(
        payload.get("schema_version") == 1
        and payload.get("scan_policy_version") == SCAN_POLICY_VERSION
        and payload.get("cycle_status") == "complete"
        and _valid_timestamp(cycle_started)
        and _valid_timestamp(cycle_completed)
        and category_ids
        and completed_ids == category_ids
        and not unqueryable_ids
        and categories_total == len(category_ids)
        and categories_complete == categories_total
        and categories_unqueryable == 0
        and coverage >= 100
        and pages_success > 0
        and _integer(payload.get("candidate_count"), -1) == len(rows)
        and len(candidate_ids) == len(set(candidate_ids))
        and bool(candidate_ids)
        and rows_valid
    )
    return {
        **empty,
        "valid": valid,
        "sha256": hashlib.sha256(_canonical_json(payload)).hexdigest() if valid else "",
        "candidate_count": len(rows) if valid else 0,
        "candidate_ids": candidate_ids if valid else [],
        "category_ids": category_ids,
        "completed_category_ids": completed_ids,
        "unqueryable_category_ids": unqueryable_ids,
        "cycle_started_at": cycle_started,
        "cycle_completed_at": cycle_completed,
        "categories_total": categories_total,
        "categories_complete": categories_complete,
        "categories_unqueryable": categories_unqueryable,
        "category_coverage_percent": coverage,
        "pages_success": pages_success,
        "product_rows_success": product_rows_success,
    }


def build_status_snapshot(
    state: dict[str, Any],
    generated_at: str | None = None,
    completed_candidates: Any = None,
) -> dict[str, Any]:
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    categories = state.get("categories") if isinstance(state.get("categories"), list) else []
    queue = state.get("parallel_pending_pages") if isinstance(state.get("parallel_pending_pages"), list) else []
    current_ids_raw = [
        str(row.get("id"))
        for row in categories
        if isinstance(row, dict) and str(row.get("id") or "").isdigit()
    ]
    current_ids = sorted(set(current_ids_raw), key=int)
    current_ids_unique = len(current_ids_raw) == len(set(current_ids_raw))

    snapshot = _candidate_snapshot_details(completed_candidates)
    policy_ok = bool(
        state.get("parallel_full_catalog_mode") == "all_categories_all_pages"
        and state.get("parallel_scan_policy_version") == SCAN_POLICY_VERSION
    )
    snapshot_valid = bool(
        policy_ok
        and current_ids_unique
        and snapshot["valid"]
        and snapshot["category_ids"] == current_ids
    )
    cycles = _integer(stats.get("completed_cycles", state.get("completed_cycles")))
    latest_cycle_status = str(state.get("last_cycle_status") or "in_progress")
    latest_completed_at = str(state.get("last_cycle_completed_at") or "")
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
        # Latest attempted cycle is diagnostic; it must not erase a prior good snapshot.
        "last_cycle_status": latest_cycle_status,
        "last_cycle_started_at": state.get("last_cycle_started_at"),
        "last_cycle_completed_at": latest_completed_at or None,
        "last_cycle_categories_total": _integer(state.get("last_cycle_categories_total")),
        "last_cycle_categories_complete": _integer(state.get("last_cycle_categories_complete")),
        "last_cycle_categories_unqueryable": _integer(state.get("last_cycle_categories_unqueryable")),
        "last_cycle_category_coverage_percent": _number(state.get("last_cycle_category_coverage_percent")),
        "last_cycle_pages_success": _integer(state.get("last_cycle_pages_success")),
        "last_cycle_product_rows_success": _integer(state.get("last_cycle_product_rows_success")),
        "last_cycle_clean": snapshot_valid,
        # Stable fields below describe the last known-good immutable snapshot.
        "last_clean_cycle_status": "complete" if snapshot_valid else "unavailable",
        "last_clean_cycle_started_at": snapshot["cycle_started_at"] if snapshot_valid else None,
        "last_clean_cycle_completed_at": snapshot["cycle_completed_at"] if snapshot_valid else None,
        "last_clean_cycle_category_ids": snapshot["category_ids"] if snapshot_valid else [],
        "last_clean_cycle_completed_category_ids": snapshot["completed_category_ids"] if snapshot_valid else [],
        "last_clean_cycle_unqueryable_category_ids": snapshot["unqueryable_category_ids"] if snapshot_valid else [],
        "last_clean_cycle_categories_total": snapshot["categories_total"] if snapshot_valid else 0,
        "last_clean_cycle_categories_complete": snapshot["categories_complete"] if snapshot_valid else 0,
        "last_clean_cycle_categories_unqueryable": snapshot["categories_unqueryable"] if snapshot_valid else 0,
        "last_clean_cycle_category_coverage_percent": snapshot["category_coverage_percent"] if snapshot_valid else 0,
        "last_clean_cycle_pages_success": snapshot["pages_success"] if snapshot_valid else 0,
        "last_clean_cycle_product_rows_success": snapshot["product_rows_success"] if snapshot_valid else 0,
        "catalog_category_ids": current_ids,
        "catalog_category_count": len(current_ids),
        "completed_cycles": cycles,
        "completed_candidates_snapshot_present": bool(
            snapshot["present"] and snapshot["cycle_completed_at"]
        ),
        "completed_candidates_snapshot_valid": snapshot_valid,
        "completed_candidates_cycle_at": snapshot["cycle_completed_at"] if snapshot_valid else None,
        "completed_candidates_count": snapshot["candidate_count"] if snapshot_valid else 0,
        "completed_candidates_ids": snapshot["candidate_ids"] if snapshot_valid else [],
        "completed_candidates_sha256": snapshot["sha256"] if snapshot_valid else "",
        "current_cycle_started_at": state.get("parallel_cycle_started_at"),
        "current_cycle_pages_success": _integer(state.get("parallel_cycle_pages_success")),
        "current_cycle_categories_complete": len(state.get("parallel_cycle_completed_category_ids", [])),
        "current_cycle_categories_unqueryable": len(state.get("parallel_cycle_unqueryable_category_ids", [])),
        "pending_page_count": len(queue),
        "pending_retry_pages": retries,
        "known_category_count": len(state.get("parallel_known_category_ids", [])),
        "last_batch_at": state.get("parallel_last_batch_at"),
        "last_error": str(state.get("last_error") or "")[:240],
    }


def load_completed_candidates_snapshot(
    status_path: Path = STATUS_PATH,
    candidates_path: Path = COMPLETED_CANDIDATES_PATH,
) -> dict[str, Any] | None:
    """Return only a hash-verified full-catalog snapshot matching the current category set."""
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        candidates_payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(status, dict) or not isinstance(candidates_payload, dict):
        return None
    if (
        status.get("schema_version") != 2
        or status.get("last_clean_cycle_status") != "complete"
        or status.get("completed_candidates_snapshot_present") is not True
        or status.get("completed_candidates_snapshot_valid") is not True
        or status.get("scan_policy_version") != SCAN_POLICY_VERSION
    ):
        return None

    details = _candidate_snapshot_details(candidates_payload)
    if not details["valid"]:
        return None
    if details["cycle_completed_at"] != str(status.get("last_clean_cycle_completed_at") or ""):
        return None
    if details["cycle_started_at"] != str(status.get("last_clean_cycle_started_at") or ""):
        return None
    category_ids = status.get("last_clean_cycle_category_ids")
    current_ids = status.get("catalog_category_ids")
    if not isinstance(category_ids, list) or category_ids != current_ids:
        return None
    if details["category_ids"] != category_ids:
        return None
    if details["candidate_count"] != _integer(status.get("completed_candidates_count"), -1):
        return None
    if details["sha256"] != str(status.get("completed_candidates_sha256") or ""):
        return None
    if details["candidate_ids"] != status.get("completed_candidates_ids"):
        return None

    rows = candidates_payload.get("candidates")
    by_id = {str(row.get("product_id")): row for row in rows if isinstance(row, dict)}
    return {
        "cycle_completed_at": details["cycle_completed_at"],
        "cycle_started_at": details["cycle_started_at"],
        "candidate_ids": set(details["candidate_ids"]),
        "candidate_by_id": by_id,
        "candidates": rows,
        "candidate_count": details["candidate_count"],
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
    rank = _integer(candidate.get("catalog_cycle_snapshot_rank"))
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
        f"last_clean_snapshot_valid={snapshot['completed_candidates_snapshot_valid']} "
        f"latest_attempt_status={snapshot['last_cycle_status']} "
        f"last_clean_cycle_at={snapshot['last_clean_cycle_completed_at']} "
        f"categories={snapshot['last_clean_cycle_categories_complete']}/{snapshot['last_clean_cycle_categories_total']} "
        f"candidates={snapshot['completed_candidates_count']} "
        f"pending_pages={snapshot['pending_page_count']} "
        f"retry_pages={snapshot['pending_retry_pages']}"
    )
    return snapshot


if __name__ == "__main__":
    write_status_snapshot()
