#!/usr/bin/env python3
"""Build a small, verifiable marker for the last known-good full catalog snapshot."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

try:
    from .catalog_sweep import MAX_RETAINED_CANDIDATES
except ImportError:  # pragma: no cover - direct script execution
    from catalog_sweep import MAX_RETAINED_CANDIDATES
STATE_PATH = ROOT / "catalog_sweep_state.json"
STATUS_PATH = ROOT / "catalog_sweep_status.json"
COMPLETED_CANDIDATES_PATH = ROOT / "catalog_sweep_completed_candidates.json"
SCAN_POLICY_VERSION = "all_categories_all_pages_v3_cycle_snapshot"
MAX_CATALOG_SNAPSHOT_AGE_HOURS = 96
MAX_UNSCANNED_CATEGORY_ADDITIONS = 50
TOP_CANDIDATES_PREVIEW_LIMIT = 100


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


def _category_addition_budget(current_count: int) -> int:
    """Allow at most 1% newly-added categories, capped at 50, during a rescan."""
    count = max(0, int(current_count))
    return max(1, min(MAX_UNSCANNED_CATEGORY_ADDITIONS, (count + 99) // 100))


def _category_ids_compatible_with_current_catalog(snapshot_ids: Any, current_ids: Any) -> bool:
    """Allow additions only; removals/replacements invalidate the snapshot."""
    snapshot = _sorted_ids(snapshot_ids)
    current = _sorted_ids(current_ids)
    if not snapshot or not current:
        return False
    snapshot_set = set(snapshot)
    current_set = set(current)
    if not snapshot_set.issubset(current_set):
        return False
    return len(current_set - snapshot_set) <= _category_addition_budget(len(current_set))


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _valid_timestamp(value: str) -> bool:
    return _parse_timestamp(value) is not None


def _snapshot_is_fresh(completed_at: Any, now: datetime | None = None) -> bool:
    completed = _parse_timestamp(completed_at)
    if completed is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_hours = (current.astimezone(timezone.utc) - completed).total_seconds() / 3600
    return -0.25 <= age_hours <= MAX_CATALOG_SNAPSHOT_AGE_HOURS


def is_initial_catalog_warmup(status: Any) -> bool:
    """Permit live discovery only before the first valid full-catalog snapshot exists."""
    if not isinstance(status, dict) or _integer(status.get("schema_version")) != 2:
        return False
    return bool(
        status.get("full_catalog_mode") == "all_categories_all_pages"
        and status.get("scan_policy_version") == SCAN_POLICY_VERSION
        and status.get("completed_candidates_snapshot_present") is False
        and status.get("completed_candidates_snapshot_valid") is False
        and status.get("last_clean_cycle_status") == "unavailable"
        and not status.get("last_clean_cycle_completed_at")
        and _integer(status.get("completed_cycles")) == 0
    )


def _candidate_snapshot_details(payload: Any) -> dict[str, Any]:
    """Validate the frozen snapshot without recomputing its time-sensitive ranking."""
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
        "order_policy": "",
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
    candidate_order_policy = str(
        payload.get("candidate_order_policy") or "discount_value_desc"
    )
    supported_order_policies = {
        "discount_value_desc",
        "catalog_demand_first_v1",
    }
    previous_sort_key: tuple[int, int] | None = None
    rows_valid = candidate_order_policy in supported_order_policies
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
        if candidate_order_policy == "discount_value_desc":
            sort_key = (discount, savings)
            if previous_sort_key is not None and sort_key > previous_sort_key:
                rows_valid = False
                break
            previous_sort_key = sort_key
        # catalog_demand_first_v1 freezes the producer's native demand-first order.
        # Never reinterpret it as a global markdown sort during validation.
        # Snapshot-rank continuity and the status-file hash still protect this order.
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
        "order_policy": candidate_order_policy,
    }


def _top_candidates_preview(completed_candidates: Any, valid: bool) -> list[dict[str, Any]]:
    """Expose a compact demand-first shortlist only from a valid, explicitly ranked snapshot.

    Prices and availability are listing observations, never substitutes for live checks.
    """
    if not valid or not isinstance(completed_candidates, dict):
        return []
    if str(completed_candidates.get("candidate_order_policy") or "") != "catalog_demand_first_v1":
        return []
    rows = completed_candidates.get("candidates")
    if not isinstance(rows, list):
        return []

    preview: list[dict[str, Any]] = []
    for row in rows[:TOP_CANDIDATES_PREVIEW_LIMIT]:
        if not isinstance(row, dict):
            continue
        raw_brand = row.get("brand") or row.get("brand_name") or ""
        if isinstance(raw_brand, dict):
            raw_brand = raw_brand.get("name") or raw_brand.get("title") or raw_brand.get("value") or ""
        category_ids = _sorted_ids(row.get("catalog_category_ids"))
        preview.append({
            "snapshot_rank": _integer(row.get("catalog_cycle_snapshot_rank")),
            "product_id": str(row.get("product_id") or ""),
            "product_url": str(row.get("product_url") or ""),
            "title": str(row.get("title") or "")[:180],
            "brand": str(raw_brand or "")[:100],
            "current_price": max(0, _integer(row.get("current_price"))),
            "original_price": max(0, _integer(row.get("original_price"))),
            "discount_percent": max(0, _integer(row.get("discount_percent"))),
            "savings_toman": max(0, _integer(row.get("savings_toman"))),
            "listing_availability": str(row.get("availability") or ""),
            "rating": _number(row.get("rating")),
            "review_count": max(0, _integer(row.get("review_count"))),
            "best_selling_rank": max(0, _integer(row.get("catalog_best_selling_rank"))),
            "best_selling_category_id": str(row.get("catalog_best_selling_category_id") or ""),
            "best_selling_category_name": str(row.get("catalog_best_selling_category_name") or "")[:120],
            "best_selling_rank_observed_at": str(row.get("catalog_rank_observed_at") or ""),
            "category_ids": category_ids[:12],
            "category_count": len(category_ids),
        })
    return preview


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
    status_time = _parse_timestamp(generated_at) if generated_at else datetime.now(timezone.utc)
    snapshot_valid = bool(
        policy_ok
        and current_ids_unique
        and snapshot["valid"]
        and _category_ids_compatible_with_current_catalog(snapshot["category_ids"], current_ids)
        and _snapshot_is_fresh(snapshot["cycle_completed_at"], status_time)
    )
    top_candidates_preview = _top_candidates_preview(completed_candidates, snapshot_valid)
    cycles = _integer(stats.get("completed_cycles", state.get("completed_cycles")))
    latest_cycle_status = str(state.get("last_cycle_status") or "in_progress")
    latest_completed_at = str(state.get("last_cycle_completed_at") or "")
    retries = sum(
        1 for item in queue
        if isinstance(item, dict) and _integer(item.get("attempts")) > 0
    )
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    category_refreshed = _parse_timestamp(state.get("categories_refreshed_at"))
    category_cache_age_hours = (
        round(max(0.0, (status_time - category_refreshed).total_seconds() / 3600), 2)
        if category_refreshed is not None else None
    )

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
        "category_cache_refreshed_at": state.get("categories_refreshed_at"),
        "category_cache_age_hours": category_cache_age_hours,
        "category_discovery_fallback_used": bool(state.get("category_discovery_fallback_used")),
        "category_discovery_last_failed_at": state.get("category_discovery_last_failed_at"),
        "category_discovery_last_error": str(state.get("category_discovery_last_error") or "")[:220],
        "category_discovery_retry_after": state.get("category_discovery_retry_after"),
        "completed_cycles": cycles,
        "completed_candidates_snapshot_present": bool(
            snapshot["present"] and snapshot["cycle_completed_at"]
        ),
        "completed_candidates_snapshot_valid": snapshot_valid,
        "completed_candidates_cycle_at": snapshot["cycle_completed_at"] if snapshot_valid else None,
        "completed_candidates_count": snapshot["candidate_count"] if snapshot_valid else 0,
        "unscanned_new_category_count": (
            len(set(current_ids) - set(snapshot["category_ids"])) if snapshot_valid else 0
        ),
        "unscanned_new_category_budget": (
            _category_addition_budget(len(current_ids)) if snapshot_valid else 0
        ),
        "completed_candidates_ids": snapshot["candidate_ids"] if snapshot_valid else [],
        "completed_candidates_sha256": snapshot["sha256"] if snapshot_valid else "",
        "completed_candidates_order_policy": snapshot["order_policy"] if snapshot_valid else "",
        "top_candidates_preview_count": len(top_candidates_preview),
        "top_candidates_preview": top_candidates_preview,
        "current_cycle_started_at": state.get("parallel_cycle_started_at"),
        "current_cycle_pages_success": _integer(state.get("parallel_cycle_pages_success")),
        "current_cycle_categories_complete": len(state.get("parallel_cycle_completed_category_ids", [])),
        "current_cycle_categories_unqueryable": len(state.get("parallel_cycle_unqueryable_category_ids", [])),
        "pending_page_count": len(queue),
        "pending_retry_pages": retries,
        "known_category_count": len(state.get("parallel_known_category_ids", [])),
        "last_batch_at": state.get("parallel_last_batch_at"),
        "last_batch_pages": _integer(state.get("parallel_last_batch_pages")),
        "last_batch_workers_used": _integer(state.get("parallel_workers_used")),
        "next_worker_limit": _integer(state.get("parallel_worker_limit")),
        "last_batch_pages_per_second": _number(state.get("parallel_last_batch_pages_per_second")),
        "last_batch_request_count": _integer(state.get("parallel_last_batch_request_count")),
        "last_batch_request_p50_seconds": _number(state.get("parallel_last_batch_request_p50_seconds")),
        "last_batch_request_p95_seconds": _number(state.get("parallel_last_batch_request_p95_seconds")),
        "last_batch_request_max_seconds": _number(state.get("parallel_last_batch_request_max_seconds")),
        "last_batch_retries": _integer(state.get("parallel_last_batch_retries")),
        "last_batch_rate_limited": _integer(state.get("parallel_last_batch_rate_limited")),
        "last_batch_timeout_retries": _integer(state.get("parallel_last_batch_timeout_retries")),
        "last_batch_http_5xx_retries": _integer(state.get("parallel_last_batch_http_5xx_retries")),
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
    if not details["valid"] or not _snapshot_is_fresh(details["cycle_completed_at"]):
        return None
    if details["cycle_completed_at"] != str(status.get("last_clean_cycle_completed_at") or ""):
        return None
    if details["cycle_started_at"] != str(status.get("last_clean_cycle_started_at") or ""):
        return None
    category_ids = status.get("last_clean_cycle_category_ids")
    current_ids = status.get("catalog_category_ids")
    if not isinstance(category_ids, list) or not _category_ids_compatible_with_current_catalog(category_ids, current_ids):
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




def load_emergency_continuity_candidates(
    continuity_record: Any,
    candidates_path: Path = COMPLETED_CANDIDATES_PATH,
    *,
    now: datetime | None = None,
    limit: int = 50,
    required_product_id: str | None = None,
) -> dict[str, Any] | None:
    """Load a frozen last-known-good catalog as lead IDs only during one emergency window.

    The emergency record pins the exact SHA and scan timestamps. Snapshot price, discount,
    availability, and expiry are deliberately not returned: every lead must be fetched and
    revalidated against live product data before it can enter the publication queue.
    """
    if not isinstance(continuity_record, dict) or continuity_record.get("status") != "active":
        return None

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    try:
        expires_at = datetime.fromisoformat(
            str(continuity_record.get("expires_at") or "").replace("Z", "+00:00")
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    if expires_at.astimezone(timezone.utc) <= current:
        return None

    expected_started = str(continuity_record.get("baseline_clean_cycle_started_at") or "").strip()
    expected_completed = str(continuity_record.get("baseline_clean_cycle_completed_at") or "").strip()
    expected_sha = str(continuity_record.get("baseline_snapshot_sha256") or "").strip()
    try:
        expected_count = max(0, int(continuity_record.get("baseline_snapshot_candidate_count") or 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not expected_started or not expected_completed or not re.fullmatch(r"[a-f0-9]{64}", expected_sha) or expected_count <= 0:
        return None

    try:
        payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    details = _candidate_snapshot_details(payload)
    if (
        not details.get("valid")
        or details.get("cycle_started_at") != expected_started
        or details.get("cycle_completed_at") != expected_completed
        or details.get("sha256") != expected_sha
        or details.get("candidate_count") != expected_count
    ):
        return None

    rows = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    if required_product_id:
        wanted_id = str(required_product_id).strip()
        selected_rows = [
            row for row in rows
            if isinstance(row, dict) and str(row.get("product_id") or "").strip() == wanted_id
        ][:1]
        if not selected_rows:
            return None
        try:
            cursor = max(0, int(continuity_record.get("candidate_cursor") or 0)) % len(rows)
        except (TypeError, ValueError, OverflowError):
            cursor = 0
    else:
        try:
            batch_limit = max(1, min(250, int(limit)))
        except (TypeError, ValueError, OverflowError):
            batch_limit = 50
        try:
            cursor = max(0, int(continuity_record.get("candidate_cursor") or 0)) % len(rows)
        except (TypeError, ValueError, OverflowError):
            cursor = 0
        selected_rows = [rows[(cursor + offset) % len(rows)] for offset in range(min(batch_limit, len(rows)))]

    leads = []
    for row in selected_rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("product_id") or "").strip()
        url = str(row.get("product_url") or "").strip()
        if not re.fullmatch(r"dkp-\d{1,12}", pid) or not url.endswith(f"/{pid}/"):
            continue
        # Explicit allow-list: do not leak historical price, discount, stock or expiry
        # into live publication eligibility through the emergency hand-off.
        lead = {
            "product_id": pid,
            "product_url": url,
            "title": str(row.get("title") or "")[:180],
            "brand": str(row.get("brand") or row.get("brand_name") or "")[:100],
            "source": "digikala_emergency_last_clean_snapshot",
        }
        for field in (
            "catalog_sort_mode",
            "catalog_best_selling_rank",
            "catalog_best_selling_category_id",
            "catalog_best_selling_category_name",
            "catalog_rank_observed_at",
            "catalog_best_selling_ranks_by_category",
            "catalog_cycle_completed_at",
            "catalog_cycle_snapshot_rank",
            "catalog_category_ids",
            "catalog_category_name",
            "catalog_category_path",
        ):
            if row.get(field) not in (None, ""):
                lead[field] = row[field]
        leads.append(lead)

    return {
        "candidates": leads,
        "candidate_count": len(rows),
        "cursor": cursor,
        "next_cursor": (
            cursor if required_product_id else (cursor + len(selected_rows)) % len(rows)
        ),
        "cycle_started_at": expected_started,
        "cycle_completed_at": expected_completed,
        "sha256": expected_sha,
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }


def is_degraded_live_fallback_available(status: Any) -> bool:
    """Allow live-verified discovery only when DigiKala's taxonomy registry is intact."""
    if not isinstance(status, dict) or _integer(status.get("schema_version")) != 2:
        return False
    if status.get("full_catalog_mode") != "all_categories_all_pages":
        return False
    if status.get("scan_policy_version") != SCAN_POLICY_VERSION:
        return False
    category_count = _integer(status.get("catalog_category_count"))
    category_ids = _sorted_ids(status.get("catalog_category_ids"))
    return category_count > 0 and len(category_ids) == category_count


def load_publication_catalog_context(
    status_path: Path = STATUS_PATH,
    candidates_path: Path = COMPLETED_CANDIDATES_PATH,
) -> dict[str, Any]:
    """Resolve the current publication gate: verified snapshot, first warm-up, or blocked."""
    snapshot = load_completed_candidates_snapshot(status_path, candidates_path)
    if snapshot is not None:
        return {"mode": "full_catalog", "snapshot": snapshot}
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        status = None
    if is_initial_catalog_warmup(status):
        return {"mode": "initial_warmup", "snapshot": None}
    if is_degraded_live_fallback_available(status):
        return {"mode": "degraded_live_fallback", "snapshot": None}
    return {"mode": "blocked", "snapshot": None}


def candidate_allowed_by_publication_context(
    candidate: Any,
    context: dict[str, Any] | None,
) -> bool:
    """Only current snapshot members may enter normal publication; SnapShop remains live-verified."""
    if not isinstance(candidate, dict) or not isinstance(context, dict):
        return False
    mode = str(context.get("mode") or "")
    if mode == "initial_warmup":
        return True
    if mode == "degraded_live_fallback":
        product_id = str(candidate.get("product_id") or "").lower()
        product_url = str(candidate.get("product_url") or "").strip().lower()
        if product_id.startswith("dkp-"):
            return bool(re.search(
                r"https?://(?:www\.|m\.)?digikala\.com/product/" + re.escape(product_id) + r"(?:/|[?#]|$)",
                product_url,
            ))
        if product_id.startswith("snp-"):
            return bool(re.search(r"https?://(?:www\.)?snappshop\.ir/product/", product_url))
        return False
    if mode != "full_catalog":
        return False
    product_id = str(candidate.get("product_id") or "").lower()
    if product_id.startswith("snp-"):
        return True
    return candidate_matches_completed_snapshot(candidate, context.get("snapshot"))


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



def upgrade_legacy_demand_first_snapshot(payload: Any) -> tuple[dict[str, Any], bool]:
    """Tag a pre-policy snapshot only when its full-catalog demand-first provenance is provable.

    The previous writer used catalog_sweep.retain_diverse_candidates(), whose
    ordering was already demand-first, but did not persist candidate_order_policy.
    Re-sorting now would be unsafe because bestseller ranks age with time. This
    migration preserves the recorded order and only adds its explicit policy marker
    after verifying the full cycle and every row's provenance.
    """
    if not isinstance(payload, dict) or payload.get("candidate_order_policy"):
        return (payload if isinstance(payload, dict) else {}), False

    rows = payload.get("candidates")
    if not isinstance(rows, list) or not rows:
        return payload, False

    category_ids = _sorted_ids(payload.get("category_ids"))
    completed_ids = _sorted_ids(payload.get("completed_category_ids"))
    unqueryable_ids = payload.get("unqueryable_category_ids")
    cycle_started = str(payload.get("cycle_started_at") or "")
    cycle_completed = str(payload.get("cycle_completed_at") or "")
    total = _integer(payload.get("categories_total"))
    complete = _integer(payload.get("categories_complete"))
    unqueryable_count = _integer(payload.get("categories_unqueryable"))
    coverage = _number(payload.get("category_coverage_percent"))
    pages_success = _integer(payload.get("pages_success"))
    product_rows = _integer(payload.get("product_rows_success"))
    full_cycle_proven = bool(
        payload.get("schema_version") == 1
        and payload.get("scan_policy_version") == SCAN_POLICY_VERSION
        and payload.get("cycle_status") == "complete"
        and _valid_timestamp(cycle_started)
        and _valid_timestamp(cycle_completed)
        and category_ids
        and completed_ids == category_ids
        and isinstance(unqueryable_ids, list)
        and not unqueryable_ids
        and total == len(category_ids)
        and complete == total
        and unqueryable_count == 0
        and coverage >= 100
        and pages_success > 0
        and product_rows > 0
        and _integer(payload.get("candidate_count"), -1) == len(rows)
        and len(rows) <= MAX_RETAINED_CANDIDATES
    )
    if not full_cycle_proven:
        return payload, False

    candidate_ids: set[str] = set()
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return payload, False
        product_id = str(row.get("product_id") or "")
        if (
            not re.fullmatch(r"dkp-\d{1,12}", product_id)
            or product_id in candidate_ids
            or row.get("source") != "digikala_catalog_sweep"
            or row.get("catalog_sort_mode") != "best_selling"
            or str(row.get("catalog_cycle_completed_at") or "") != cycle_completed
            or _integer(row.get("catalog_cycle_snapshot_rank")) != rank
            or _integer(row.get("catalog_best_selling_rank")) <= 0
            or not _valid_timestamp(row.get("catalog_rank_observed_at"))
            or _integer(row.get("discount_percent")) < 1
            or _integer(row.get("savings_toman")) <= 0
        ):
            return payload, False
        ranks = row.get("catalog_best_selling_ranks_by_category")
        if not isinstance(ranks, dict) or not ranks:
            return payload, False
        candidate_ids.add(product_id)

    upgraded_rows = [
        {
            **row,
            "catalog_cycle_completed_at": cycle_completed,
            "catalog_cycle_snapshot_rank": rank,
        }
        for rank, row in enumerate(rows, start=1)
    ]
    upgraded = {
        **payload,
        "candidate_order_policy": "catalog_demand_first_v1",
        "candidate_count": len(upgraded_rows),
        "candidates": upgraded_rows,
    }
    return upgraded, True

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

    upgraded_candidates, migrated = upgrade_legacy_demand_first_snapshot(completed_candidates)
    if migrated:
        temporary_path = completed_candidates_path.with_suffix(
            completed_candidates_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(upgraded_candidates, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(completed_candidates_path)
        completed_candidates = upgraded_candidates
        print(
            "OFFERCHIN_CATALOG_SNAPSHOT_LEGACY_ORDER_UPGRADED "
            f"candidates={len(upgraded_candidates['candidates'])} "
            "policy=catalog_demand_first_v1; original order preserved"
        )

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
