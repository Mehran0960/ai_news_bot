#!/usr/bin/env python3
"""Write a compact, fail-closed publication gate from the resumable catalog state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "catalog_sweep_state.json"
STATUS_PATH = ROOT / "catalog_sweep_status.json"


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


def build_status_snapshot(state: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
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
        and state.get("parallel_scan_policy_version") == "all_categories_all_pages_v2"
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
        and not last_cycle_unqueryable_ids
        and category_ids.issubset(last_cycle_category_ids)
        and category_ids.issubset(last_cycle_completed_ids)
    )
    retries = sum(
        1 for item in queue
        if isinstance(item, dict) and _integer(item.get("attempts")) > 0
    )
    generated = generated_at or datetime.now(timezone.utc).isoformat()

    return {
        "schema_version": 1,
        "generated_at": generated,
        "full_catalog_mode": str(state.get("parallel_full_catalog_mode") or ""),
        "scan_policy_version": str(state.get("parallel_scan_policy_version") or ""),
        "last_cycle_status": cycle_status,
        "last_cycle_clean": clean,
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


def write_status_snapshot(
    state_path: Path = STATE_PATH,
    status_path: Path = STATUS_PATH,
) -> dict[str, Any]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot_read_catalog_state:{type(exc).__name__}") from exc
    if not isinstance(state, dict):
        raise RuntimeError("catalog_state_not_object")
    snapshot = build_status_snapshot(state)
    status_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "OFFERCHIN_CATALOG_STATUS "
        f"clean={snapshot['last_cycle_clean']} "
        f"cycle_status={snapshot['last_cycle_status']} "
        f"completed_at={snapshot['last_cycle_completed_at']} "
        f"categories={snapshot['last_cycle_categories_complete']}/{snapshot['last_cycle_categories_total']} "
        f"pending_pages={snapshot['pending_page_count']} "
        f"retry_pages={snapshot['pending_retry_pages']}"
    )
    return snapshot


if __name__ == "__main__":
    write_status_snapshot()
