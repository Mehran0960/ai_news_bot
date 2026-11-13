#!/usr/bin/env python3
"""Concurrent, resumable DigiKala category/page sweep for OfferChin.

This module reuses the existing parsing and candidate-ranking contract from
catalog_sweep.py, but replaces the single cursor with a persisted page queue.
A failed page is requeued and cannot silently advance the sweep.
"""
from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests

try:
    import catalog_sweep as base
except ImportError:  # pragma: no cover
    from . import catalog_sweep as base

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "catalog_sweep_state.json"
CANDIDATES_PATH = ROOT / "catalog_sweep_candidates.json"
PUBLISHER_STATE_PATH = ROOT / "state.json"
DEFAULT_PAGES_PER_RUN = 480
DEFAULT_WORKERS = 16
WORKER_RAMP_POLICY_VERSION = "explicit_12_14_16_v1"
_thread_local = threading.local()


def _apply_worker_ramp_policy(state: dict, current: int, requested: int) -> int:
    """Normalize one legacy checkpoint to the explicit 12/14/16 trial ladder.

    Older adaptive runs could leave 13, 15, or 16 as the next limit. On the
    first run with this policy, restart any legacy value above 12 at 12.
    Once the policy marker is persisted, later 14/16 steps remain intact.
    """
    ceiling = max(1, min(32, base._normal_int(requested, 1)))
    limit = max(1, min(ceiling, base._normal_int(current, ceiling)))
    if state.get("parallel_worker_ramp_policy_version") != WORKER_RAMP_POLICY_VERSION:
        if limit > 12 and ceiling >= 12:
            limit = 12
        state["parallel_worker_ramp_policy_version"] = WORKER_RAMP_POLICY_VERSION
    return limit


def _session() -> requests.Session:
    """Give each worker its own HTTP session; never share mutable sessions."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
            "Referer": "https://www.digikala.com/",
        })
        _thread_local.session = session
    return session


def build_initial_page_queue(
    categories: list[dict], legacy_category_index: int = 0, legacy_page: int = 1
) -> list[dict]:
    """Seed one page per category, preserving the old sequential cursor."""
    start_index = max(0, min(len(categories), int(legacy_category_index or 0)))
    page = max(1, int(legacy_page or 1))
    tasks: list[dict] = []
    for index, category in enumerate(categories):
        if index < start_index or not isinstance(category, dict):
            continue
        category_id = str(category.get("id") or "")
        if not category_id.isdigit():
            continue
        tasks.append({
            "category_id": category_id,
            "category_name": str(category.get("name") or category_id),
            "page": page if index == start_index else 1,
            "attempts": 0,
        })
    return tasks


def _task_key(task: dict) -> tuple[str, int]:
    return str(task.get("category_id") or ""), max(1, base._normal_int(task.get("page"), 1))



def _next_page_task(task: dict, total_pages: int | None, product_count: int) -> dict | None:
    """Follow all reported pages; if pagination is unknown, stop only at an empty page."""
    page = max(1, base._normal_int(task.get("page"), 1))
    if product_count <= 0:
        return None
    if total_pages is not None and page >= max(1, int(total_pages)):
        return None
    return {
        "category_id": str(task.get("category_id") or ""),
        "category_name": str(task.get("category_name") or task.get("category_id") or ""),
        "page": page + 1,
        "attempts": 0,
    }

def _fetch_page(task: dict) -> dict:
    """Fetch one page and attach end-to-end request/parse latency telemetry.

    400/404 close an unqueryable category/page; other failures are retryable
    and remain in the persisted queue.
    """
    request_started = time.monotonic()
    category_id = str(task.get("category_id") or "")
    page = max(1, base._normal_int(task.get("page"), 1))

    def timed_result(kind: str, **fields: object) -> dict:
        return {
            "kind": kind,
            **fields,
            "elapsed_seconds": round(time.monotonic() - request_started, 3),
        }

    try:
        url, params = base._category_page_url(category_id, page)
        response = _session().get(
            url,
            params=params,
            timeout=base.REQUEST_TIMEOUT,
        )
        if response.status_code in (400, 404):
            return timed_result("terminal", status_code=response.status_code, rows=[])
        if response.status_code == 429:
            return timed_result("retry", status_code=429, rows=[], error="rate_limited")
        response.raise_for_status()
        if len(response.content) > 8_000_000:
            raise base.CatalogSweepError("api_response_exceeded_8mb")
        try:
            payload = response.json()
        except ValueError as exc:
            raise base.CatalogSweepError("api_returned_non_json") from exc
        if not isinstance(payload, dict):
            raise base.CatalogSweepError("api_payload_not_object")
        rows = base.extract_product_rows(payload)
        total_pages = base.extract_total_pages(payload, page, len(rows))
        return timed_result(
            "ok",
            rows=rows,
            total_pages=total_pages,
            status_code=response.status_code,
        )
    except Exception as exc:  # keep the cursor safe on all transient/schema failures
        return timed_result(
            "retry",
            rows=[],
            error=f"{type(exc).__name__}:{str(exc)[:140]}",
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
        )


def _percentile(values: list[float], percentile: float) -> float:
    """Return a stable nearest-rank percentile rounded to milliseconds."""
    if not values:
        return 0.0
    ordered = sorted(max(0.0, float(value)) for value in values)
    quantile = min(1.0, max(0.0, float(percentile)))
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 3)


def _next_worker_limit(
    current: int,
    requested: int,
    rate_limited_count: int,
    retry_count: int,
    *,
    timeout_retry_count: int = 0,
    http_5xx_retry_count: int = 0,
) -> int:
    """Ramp on clean batches; distinguish isolated 5xx from congestion signals.

    Below 12 workers, increase by two but stop at 12. Then test 14 and 16.
    Any 429 backs off by two; three or more retries/429s halve concurrency.
    Timeouts and non-5xx transient failures back off by one. A single isolated
    5xx holds the current limit (it is retried and checkpointed); repeated 5xx
    failures back off by one. The requested count remains a hard ceiling.
    """
    ceiling = max(1, min(32, base._normal_int(requested, 1)))
    current_limit = max(1, min(ceiling, base._normal_int(current, ceiling)))
    floor = min(2, ceiling)
    retries = max(0, base._normal_int(retry_count))
    rate_limits = max(0, base._normal_int(rate_limited_count))
    timeouts = max(0, base._normal_int(timeout_retry_count))
    server_errors = min(retries, max(0, base._normal_int(http_5xx_retry_count)))
    if rate_limits >= 3 or retries >= 3:
        return max(floor, current_limit // 2)
    if rate_limits:
        return max(floor, current_limit - 2)
    if timeouts or retries > server_errors:
        return max(floor, current_limit - 1)
    if server_errors >= 2:
        return max(floor, current_limit - 1)
    if server_errors == 1:
        return current_limit
    if current_limit < 12:
        return min(ceiling, 12, current_limit + 2)
    if current_limit < 14:
        return min(ceiling, 14)
    if current_limit < 16:
        return min(ceiling, 16)
    return min(ceiling, current_limit)

def _ensure_parallel_state(state: dict) -> list[dict]:
    categories = state.get("categories", [])
    if not isinstance(categories, list):
        categories = []
    queue = state.get("parallel_pending_pages")
    if not isinstance(queue, list):
        queue = []
    known = state.get("parallel_known_category_ids")
    if not isinstance(known, list):
        known = []
    known_ids = {str(value) for value in known}

    if (
        not state.get("parallel_queue_initialized")
        or state.get("parallel_scan_policy_version") != "all_categories_all_pages_v3_cycle_snapshot"
    ):
        # Legacy cursors AND previously initialized top-60 queues may have skipped
        # already-processed categories/tail pages. Force one exhaustive restart.
        queue = build_initial_page_queue(categories, legacy_category_index=0, legacy_page=1)
        known_ids = {str(row.get("id")) for row in categories if isinstance(row, dict)}
        state["parallel_queue_initialized"] = True
        state["parallel_cycle_started_at"] = base.iso_now()
        state["parallel_cycle_completed_category_ids"] = []
        state["parallel_cycle_unqueryable_category_ids"] = []
        state["parallel_cycle_pages_success"] = 0
        state["parallel_cycle_product_rows_success"] = 0
        state["parallel_full_catalog_mode"] = "all_categories_all_pages"
        state["parallel_scan_policy_version"] = "all_categories_all_pages_v3_cycle_snapshot"
    else:
        # Category dictionary refreshes may introduce new categories. Append only
        # genuinely new IDs; do not reset progress for existing IDs.
        for category in categories:
            if not isinstance(category, dict):
                continue
            category_id = str(category.get("id") or "")
            if category_id.isdigit() and category_id not in known_ids:
                queue.append({
                    "category_id": category_id,
                    "category_name": str(category.get("name") or category_id),
                    "page": 1,
                    "attempts": 0,
                })
                known_ids.add(category_id)

    # Older completed_cycles values describe top-60 partial sweeps, not full
    # catalog cycles. Reset the counter once while preserving the active page queue.
    if not state.get("parallel_full_cycle_counter_initialized"):
        stats = state.get("stats", {})
        if not isinstance(stats, dict):
            stats = {}
            state["stats"] = stats
        legacy_count = max(0, base._normal_int(stats.get("completed_cycles")))
        if legacy_count:
            state["legacy_completed_partial_sweeps_before_full_catalog"] = legacy_count
        stats["completed_cycles"] = 0
        state["completed_cycles"] = 0
        if state.get("last_cycle_completed_at"):
            state["legacy_last_partial_sweep_at"] = state.pop("last_cycle_completed_at")
        state["parallel_full_cycle_counter_initialized"] = True

    # De-duplicate persisted work without pruning any page depth or retry record.
    unique: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for task in queue:
        if not isinstance(task, dict):
            continue
        key = _task_key(task)
        if not key[0].isdigit() or key in seen:
            continue
        seen.add(key)
        unique.append(task)
    state.setdefault("parallel_deep_pages_pruned", 0)  # Legacy telemetry; no pruning occurs in full-catalog mode.
    state.setdefault("parallel_cycle_completed_category_ids", [])
    state.setdefault("parallel_cycle_unqueryable_category_ids", [])
    state.setdefault("parallel_cycle_pages_success", 0)
    state.setdefault("parallel_cycle_product_rows_success", 0)
    state["parallel_full_catalog_mode"] = "all_categories_all_pages"
    state["parallel_known_category_ids"] = sorted(
        known_ids, key=lambda value: int(value) if value.isdigit() else 0
    )
    ordered_categories = base.sort_categories_for_sweep(categories)
    category_rank = {
        str(row.get("id") or ""): index
        for index, row in enumerate(ordered_categories)
        if isinstance(row, dict)
    }
    # Sweep every leaf category's first page before spending capacity on deeper
    # pages or parent nodes. This prevents parent-only pages from monopolizing
    # the crawler's early batches.
    unique.sort(
        key=lambda task: (
            max(1, base._normal_int(task.get("page"), 1)),
            category_rank.get(str(task.get("category_id") or ""), len(category_rank)),
            base._normal_int(task.get("attempts")),
        )
    )
    parent_ids = {
        str(row.get("parent_id") or "")
        for row in ordered_categories
        if str(row.get("parent_id") or "").isdigit()
    }
    state["parallel_pending_pages"] = unique
    state["parallel_leaf_category_count"] = sum(
        str(row.get("id") or "") not in parent_ids
        for row in ordered_categories
    )
    return unique


def run_parallel_sweep(
    pages_per_run: int = DEFAULT_PAGES_PER_RUN,
    workers: int = DEFAULT_WORKERS,
    state_path: Path = STATE_PATH,
    candidates_path: Path = CANDIDATES_PATH,
    completed_candidates_path: Path = ROOT / "catalog_sweep_completed_candidates.json",
    publisher_state_path: Path = PUBLISHER_STATE_PATH,
    force_refresh: bool = False,
    fetcher: Callable[[dict], dict] | None = None,
) -> int:
    """Process a bounded page batch concurrently and checkpoint atomically."""
    run_started = time.monotonic()
    state = base._read_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    stats = state.setdefault("stats", {})
    if not isinstance(stats, dict):
        stats = {}
        state["stats"] = stats
    for key in (
        "pages_scanned_total", "product_rows_scanned_total",
        "discounted_candidates_found_total", "catalog_candidate_cards_found_total",
        "api_failures_total", "completed_cycles", "unqueryable_categories_total",
        "empty_product_pages_total", "nonempty_product_pages_total",
        "cycles_with_gaps_total",
    ):
        stats[key] = max(0, base._normal_int(stats.get(key)))

    try:
        base.refresh_categories(state, base.SESSION, force=force_refresh)
    except Exception as exc:
        state["last_error"] = f"category_refresh:{type(exc).__name__}:{str(exc)[:160]}"
        state["last_error_at"] = base.iso_now()
        base._write_json(state_path, state)
        print(
            f"PARALLEL_CATALOG_CATEGORY_REFRESH_FAILED "
            f"error={type(exc).__name__} detail={str(exc)[:160]!r}"
        )
        return 1

    categories = state.get("categories", [])
    if not isinstance(categories, list) or not categories:
        print("PARALLEL_CATALOG_ABORTED reason=no_categories")
        return 1

    queue = _ensure_parallel_state(state)
    active_cycle_started_at = str(state.get("parallel_cycle_started_at") or "")
    candidate_payload = base._read_json(candidates_path, {})
    candidate_capture_matches = bool(
        isinstance(candidate_payload, dict)
        and candidate_payload.get("cycle_started_at") == active_cycle_started_at
        and candidate_payload.get("scan_policy_version") == "all_categories_all_pages_v3_cycle_snapshot"
    )
    candidates = (
        base._load_candidates_by_id(candidates_path)
        if candidate_capture_matches else {}
    )

    if not queue:
        valid_categories = [
            row for row in categories
            if isinstance(row, dict) and str(row.get("id") or "").isdigit()
        ]
        category_ids = {str(row.get("id")) for row in valid_categories}
        if not category_ids:
            print("PARALLEL_CATALOG_ABORTED reason=no_valid_category_ids")
            return 1

        completed_ids = {
            str(value) for value in state.get("parallel_cycle_completed_category_ids", [])
            if str(value).isdigit()
        } & category_ids
        unqueryable_ids = {
            str(value) for value in state.get("parallel_cycle_unqueryable_category_ids", [])
            if str(value).isdigit()
        } & category_ids
        accounted_ids = completed_ids | unqueryable_ids
        missing_ids = category_ids - accounted_ids

        if missing_ids:
            # An empty queue is not proof that every category was accounted for.
            missing_categories = [
                row for row in valid_categories if str(row.get("id")) in missing_ids
            ]
            queue = build_initial_page_queue(missing_categories, 0, 1)
            state["parallel_pending_pages"] = queue
            state["parallel_unaccounted_categories_requeued"] = len(queue)
            print(
                "PARALLEL_CATALOG_CYCLE_REPAIRED "
                f"unaccounted_categories={len(missing_ids)} requeued={len(queue)}"
            )
        else:
            finished_at = base.iso_now()
            completed_cycle_started_at = str(state.get("parallel_cycle_started_at") or "")
            clean_full_cycle = bool(
                len(completed_ids) == len(category_ids)
                and not unqueryable_ids
                and candidate_capture_matches
            )
            state["last_cycle_started_at"] = completed_cycle_started_at
            state["last_cycle_finished_at"] = finished_at
            state["last_cycle_candidate_snapshot_valid"] = clean_full_cycle
            state["last_cycle_status"] = "complete" if clean_full_cycle else "complete_with_gaps"
            state["last_cycle_category_ids"] = sorted(
                category_ids, key=lambda value: int(value)
            )
            state["last_cycle_completed_category_ids"] = sorted(
                completed_ids, key=lambda value: int(value)
            )
            state["last_cycle_categories_complete"] = len(completed_ids)
            state["last_cycle_categories_unqueryable"] = len(unqueryable_ids)
            state["last_cycle_unqueryable_category_ids"] = sorted(
                unqueryable_ids, key=lambda value: int(value)
            )
            state["last_cycle_categories_total"] = len(category_ids)
            state["last_cycle_categories_accounted"] = len(accounted_ids)
            state["last_cycle_category_accounted_percent"] = round(
                100 * len(accounted_ids) / max(1, len(category_ids)), 2
            )
            # Unqueryable categories are gaps, not successful coverage.
            state["last_cycle_category_coverage_percent"] = round(
                100 * len(completed_ids) / max(1, len(category_ids)), 2
            )
            state["last_cycle_pages_success"] = max(
                0, base._normal_int(state.get("parallel_cycle_pages_success"))
            )
            state["last_cycle_product_rows_success"] = max(
                0, base._normal_int(state.get("parallel_cycle_product_rows_success"))
            )
            if clean_full_cycle:
                cycle_ranked = base.retain_diverse_candidates(
                    [
                        row for row in candidates.values()
                        if isinstance(row, dict)
                        and base._normal_int(row.get("discount_percent")) >= base.MIN_CANDIDATE_DISCOUNT
                    ],
                    limit=base.MAX_RETAINED_CANDIDATES,
                    rotation=0,
                )
                snapshot_rows = []
                for rank, candidate in enumerate(cycle_ranked, start=1):
                    snapshot_rows.append({
                        **candidate,
                        "catalog_cycle_completed_at": finished_at,
                        "catalog_cycle_snapshot_rank": rank,
                    })
                base._write_json(completed_candidates_path, {
                    "schema_version": 1,
                    "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
                    "candidate_order_policy": "catalog_demand_first_v1",
                    "cycle_status": "complete",
                    "cycle_started_at": completed_cycle_started_at,
                    "cycle_completed_at": finished_at,
                    "category_ids": sorted(category_ids, key=lambda value: int(value)),
                    "completed_category_ids": sorted(completed_ids, key=lambda value: int(value)),
                    "unqueryable_category_ids": sorted(unqueryable_ids, key=lambda value: int(value)),
                    "categories_total": len(category_ids),
                    "categories_complete": len(completed_ids),
                    "categories_unqueryable": len(unqueryable_ids),
                    "category_coverage_percent": round(
                        100 * len(completed_ids) / max(1, len(category_ids)), 2
                    ),
                    "pages_success": max(0, base._normal_int(state.get("parallel_cycle_pages_success"))),
                    "product_rows_success": max(0, base._normal_int(state.get("parallel_cycle_product_rows_success"))),
                    "candidate_count": len(snapshot_rows),
                    "candidates": snapshot_rows,
                })
                state["last_cycle_completed_at"] = finished_at
                state["last_cycle_candidate_count"] = len(snapshot_rows)
                stats["completed_cycles"] += 1
            else:
                state["last_cycle_candidate_count"] = 0
                stats["cycles_with_gaps_total"] += 1
            state["completed_cycles"] = stats["completed_cycles"]

            queue = build_initial_page_queue(valid_categories, 0, 1)
            state["parallel_pending_pages"] = queue
            state["parallel_cycle_started_at"] = base.iso_now()
            candidates = {}
            state["parallel_cycle_completed_category_ids"] = []
            state["parallel_cycle_unqueryable_category_ids"] = []
            state["parallel_cycle_pages_success"] = 0
            state["parallel_cycle_product_rows_success"] = 0
            print(
                "PARALLEL_CATALOG_CYCLE_FINISHED "
                f"status={state['last_cycle_status']} "
                f"categories_complete={len(completed_ids)}/{len(category_ids)} "
                f"unqueryable={len(unqueryable_ids)} "
                f"accounted_pct={state['last_cycle_category_accounted_percent']} "
                f"strict_coverage_pct={state['last_cycle_category_coverage_percent']} "
                f"pages={state['last_cycle_pages_success']} "
                f"products={state['last_cycle_product_rows_success']} "
                f"clean_full_cycles={stats['completed_cycles']} "
                f"cycles_with_gaps={stats['cycles_with_gaps_total']}"
            )

    batch_limit = max(1, min(2000, int(pages_per_run)))
    requested_workers = max(1, min(32, int(workers)))
    batch = queue[:batch_limit]
    remaining = queue[batch_limit:]
    worker_fn = fetcher or _fetch_page
    worker_limit = requested_workers
    saved_limit = base._normal_int(state.get("parallel_worker_limit"), requested_workers)
    if saved_limit > 0:
        worker_limit = max(1, min(requested_workers, saved_limit))
    worker_limit = _apply_worker_ramp_policy(state, worker_limit, requested_workers)
    # Persist the capacity actually assigned to this batch separately from the
    # next batch's adaptive limit; otherwise telemetry reports the future limit.
    worker_limit_before = worker_limit
    workers_used = min(worker_limit, len(batch) or 1)

    fetch_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers_used) as pool:
        results = list(pool.map(worker_fn, batch))
    fetch_seconds = time.monotonic() - fetch_started
    processing_started = time.monotonic()

    now = base.utc_now()
    retry_count = 0
    rate_limited_count = 0
    processed_count = 0
    terminal_count = 0
    page_row_count = 0
    empty_product_pages = 0
    nonempty_product_pages = 0
    timeout_retry_count = 0
    http_5xx_retry_count = 0
    request_latencies = [
        float(result["elapsed_seconds"])
        for result in results
        if isinstance(result, dict)
        and isinstance(result.get("elapsed_seconds"), (int, float))
    ]
    request_latency_p50 = _percentile(request_latencies, 0.50)
    request_latency_p95 = _percentile(request_latencies, 0.95)
    request_latency_max = round(max(request_latencies), 3) if request_latencies else 0.0
    pending_keys = {_task_key(task) for task in remaining if isinstance(task, dict)}

    for task, result in zip(batch, results):
        if not isinstance(result, dict):
            result = {"kind": "retry", "rows": [], "error": "invalid_worker_result"}
        kind = str(result.get("kind") or "retry")
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        category_id = str(task.get("category_id") or "")
        page = max(1, base._normal_int(task.get("page"), 1))

        if kind == "retry":
            retry_count += 1
            stats["api_failures_total"] += 1
            status_code = result.get("status_code")
            if status_code == 429:
                rate_limited_count += 1
            error_text = str(result.get("error") or "").lower()
            if "timeout" in error_text or "timed out" in error_text:
                timeout_retry_count += 1
            try:
                numeric_status = int(status_code)
            except (TypeError, ValueError, OverflowError):
                numeric_status = 0
            if 500 <= numeric_status <= 599:
                http_5xx_retry_count += 1
            retry_task = dict(task)
            retry_task["attempts"] = base._normal_int(task.get("attempts")) + 1
            retry_task["last_error"] = str(
                result.get("error") or f"http_{status_code or 'unknown'}"
            )[:160]
            if _task_key(retry_task) not in pending_keys:
                remaining.append(retry_task)
                pending_keys.add(_task_key(retry_task))
            continue

        processed_count += 1
        if rows:
            nonempty_product_pages += 1
            stats["nonempty_product_pages_total"] += 1
        else:
            empty_product_pages += 1
            stats["empty_product_pages_total"] += 1
        if kind == "terminal":
            terminal_count += 1
            unqueryable = {
                str(v) for v in state.get("parallel_cycle_unqueryable_category_ids", [])
                if str(v).isdigit()
            }
            if category_id not in unqueryable:
                stats["unqueryable_categories_total"] += 1
            unqueryable.add(category_id)
            state["parallel_cycle_unqueryable_category_ids"] = sorted(
                unqueryable, key=lambda value: int(value)
            )
            completed = {
                str(v) for v in state.get("parallel_cycle_completed_category_ids", [])
                if str(v).isdigit() and str(v) != category_id
            }
            state["parallel_cycle_completed_category_ids"] = sorted(
                completed, key=lambda value: int(value)
            )
            print(
                "PARALLEL_CATALOG_PAGE_UNQUERYABLE "
                f"category={category_id} page={page} status={result.get('status_code', 'unknown')}"
            )
            continue

        total_pages = result.get("total_pages")
        total_pages = max(1, int(total_pages)) if total_pages is not None else None
        state["parallel_cycle_pages_success"] = max(0, base._normal_int(state.get("parallel_cycle_pages_success"))) + 1
        state["parallel_cycle_product_rows_success"] = max(0, base._normal_int(state.get("parallel_cycle_product_rows_success"))) + len(rows)
        page_observed_at = base.iso_now()
        page_start_rank = (page - 1) * base.BEST_SELLING_PAGE_SIZE
        category_name = str(task.get("category_name") or category_id)
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            pid = str(row.get("product_id") or "")
            if not pid:
                continue
            old = candidates.get(pid, {})
            old = old if isinstance(old, dict) else {}
            first_seen = old.get("first_seen_at") or page_observed_at
            previous_categories = old.get("catalog_category_ids", [])
            category_ids = {str(v) for v in previous_categories if str(v).isdigit()} if isinstance(previous_categories, list) else set()
            category_ids.add(category_id)

            ranks_by_category = old.get("catalog_best_selling_ranks_by_category", {})
            ranks_by_category = dict(ranks_by_category) if isinstance(ranks_by_category, dict) else {}
            category_rank = page_start_rank + row_index + 1
            previous_rank_record = ranks_by_category.get(category_id, {})
            previous_rank_record = previous_rank_record if isinstance(previous_rank_record, dict) else {}
            rank_history = previous_rank_record.get("rank_history")
            rank_history = list(rank_history) if isinstance(rank_history, list) else []
            if not rank_history:
                legacy_rank = base._normal_int(previous_rank_record.get("rank"))
                legacy_observed = str(previous_rank_record.get("observed_at") or "")
                if legacy_rank > 0 and legacy_observed:
                    rank_history.append({
                        "rank": legacy_rank,
                        "observed_at": legacy_observed,
                        "category_name": str(previous_rank_record.get("category_name") or category_name),
                    })
            last_sample = rank_history[-1] if rank_history and isinstance(rank_history[-1], dict) else {}
            last_rank = base._normal_int(last_sample.get("rank"))
            try:
                last_observed = base.datetime.fromisoformat(
                    str(last_sample.get("observed_at") or "").replace("Z", "+00:00")
                )
                if last_observed.tzinfo is None:
                    last_observed = last_observed.replace(tzinfo=base.timezone.utc)
                history_age_hours = (
                    now.astimezone(base.timezone.utc) - last_observed.astimezone(base.timezone.utc)
                ).total_seconds() / 3600
            except (TypeError, ValueError, OverflowError):
                history_age_hours = 999999
            # Record a sample when rank changes or at least six hours have elapsed.
            # The bounded per-category history allows later ranking by actual rank movement.
            if not rank_history or last_rank != category_rank or history_age_hours >= 6:
                rank_history.append({
                    "rank": category_rank,
                    "observed_at": page_observed_at,
                    "category_name": category_name,
                })
            rank_history = [
                item for item in rank_history[-8:]
                if isinstance(item, dict)
                and 1 <= base._normal_int(item.get("rank")) <= base.BEST_SELLING_PAGE_SIZE * base.BEST_SELLING_MAX_PAGES_PER_CATEGORY
            ]
            ranks_by_category[category_id] = {
                "rank": category_rank,
                "observed_at": page_observed_at,
                "category_name": category_name,
                "rank_history": rank_history,
            }
            valid_ranks = []
            for rank_category_id, rank_record in ranks_by_category.items():
                if not str(rank_category_id).isdigit() or not isinstance(rank_record, dict):
                    continue
                saved_rank = base._normal_int(rank_record.get("rank"))
                if not 1 <= saved_rank <= base.BEST_SELLING_PAGE_SIZE * base.BEST_SELLING_MAX_PAGES_PER_CATEGORY:
                    continue
                try:
                    rank_observed = base.datetime.fromisoformat(
                        str(rank_record.get("observed_at") or "").replace("Z", "+00:00")
                    )
                    if rank_observed.tzinfo is None:
                        rank_observed = rank_observed.replace(tzinfo=base.timezone.utc)
                    rank_age_hours = (
                        now.astimezone(base.timezone.utc) - rank_observed.astimezone(base.timezone.utc)
                    ).total_seconds() / 3600
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 <= rank_age_hours <= base.BEST_SELLING_MAX_AGE_HOURS:
                    valid_ranks.append((saved_rank, str(rank_category_id), rank_record))
            best_rank, best_category_id, best_rank_record = (
                min(valid_ranks, key=lambda item: item[0]) if valid_ranks
                else (category_rank, category_id, {
                    "observed_at": page_observed_at,
                    "category_name": category_name,
                })
            )
            candidates[pid] = {
                **old, **row,
                "first_seen_at": first_seen,
                "catalog_category_id": category_id,
                "catalog_category_name": category_name,
                "catalog_category_ids": sorted(category_ids, key=lambda value: int(value)),
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_ranks_by_category": ranks_by_category,
                "catalog_best_selling_rank": best_rank,
                "catalog_best_selling_category_id": best_category_id,
                "catalog_best_selling_category_name": str(best_rank_record.get("category_name") or category_name),
                "catalog_rank_observed_at": str(best_rank_record.get("observed_at") or page_observed_at),
            }
            stats["catalog_candidate_cards_found_total"] += 1
            if base._normal_int(row.get("discount_percent")) >= base.MIN_CANDIDATE_DISCOUNT:
                stats["discounted_candidates_found_total"] += 1
        page_row_count += len(rows)
        stats["pages_scanned_total"] += 1
        stats["product_rows_scanned_total"] += len(rows)
        next_task = _next_page_task(task, total_pages, len(rows))
        if next_task and _task_key(next_task) not in pending_keys:
            remaining.append(next_task)
            pending_keys.add(_task_key(next_task))
        elif next_task is None:
            completed = {str(v) for v in state.get("parallel_cycle_completed_category_ids", []) if str(v).isdigit()}
            completed.add(category_id)
            state["parallel_cycle_completed_category_ids"] = sorted(completed, key=lambda value: int(value))

        state["last_successful_category_id"] = category_id
        state["last_successful_category_name"] = str(task.get("category_name") or category_id)
        state["last_successful_page"] = page
        state["last_successful_page_at"] = base.iso_now()
        state["last_error"] = ""

    # Increase quickly through the explicit 12 -> 14 -> 16 trial points,
    # while backing off on 429s, timeouts, and server-side failures.
    worker_limit = _next_worker_limit(
        worker_limit,
        requested_workers,
        rate_limited_count,
        retry_count,
        timeout_retry_count=timeout_retry_count,
        http_5xx_retry_count=http_5xx_retry_count,
    )
    state["parallel_worker_limit"] = worker_limit

    ordered_candidates = base.retain_diverse_candidates(
        list(candidates.values()),
        limit=base.MAX_RETAINED_CANDIDATES,
        rotation=0,
    )
    processing_seconds = time.monotonic() - processing_started
    candidate_write_started = time.monotonic()
    base._write_json(candidates_path, {
        "updated_at": base.iso_now(),
        "cycle_started_at": str(state.get("parallel_cycle_started_at") or ""),
        "scan_policy_version": "all_categories_all_pages_v3_cycle_snapshot",
        "candidate_count": len(ordered_candidates),
        "candidates": ordered_candidates,
    })
    candidate_write_seconds = time.monotonic() - candidate_write_started
    try:
        candidate_file_bytes = candidates_path.stat().st_size
    except OSError:
        candidate_file_bytes = 0

    state["parallel_pending_pages"] = remaining
    state["pending_page_count"] = len(remaining)
    state["parallel_last_batch_at"] = base.iso_now()
    state["parallel_last_batch_pages"] = len(batch)
    state["parallel_last_batch_successes"] = processed_count
    state["parallel_last_batch_terminals"] = terminal_count
    state["parallel_last_batch_retries"] = retry_count
    state["parallel_last_batch_rate_limited"] = rate_limited_count
    state["parallel_last_batch_product_rows"] = page_row_count
    state["parallel_last_batch_empty_product_pages"] = empty_product_pages
    state["parallel_last_batch_nonempty_product_pages"] = nonempty_product_pages
    state["parallel_last_batch_fetch_seconds"] = round(fetch_seconds, 3)
    state["parallel_last_batch_processing_seconds"] = round(processing_seconds, 3)
    state["parallel_last_batch_candidate_write_seconds"] = round(candidate_write_seconds, 3)
    state["parallel_last_batch_pages_per_second"] = round(
        len(batch) / max(fetch_seconds, 0.001), 2
    )
    state["parallel_last_batch_rows_per_second"] = round(
        page_row_count / max(fetch_seconds + processing_seconds + candidate_write_seconds, 0.001), 2
    )
    state["parallel_last_batch_candidate_file_bytes"] = candidate_file_bytes
    state["parallel_last_batch_worker_limit_before"] = worker_limit_before
    state["parallel_last_batch_worker_limit_next"] = worker_limit
    state["parallel_last_batch_request_count"] = len(request_latencies)
    state["parallel_last_batch_request_p50_seconds"] = request_latency_p50
    state["parallel_last_batch_request_p95_seconds"] = request_latency_p95
    state["parallel_last_batch_request_max_seconds"] = request_latency_max
    state["parallel_last_batch_timeout_retries"] = timeout_retry_count
    state["parallel_last_batch_http_5xx_retries"] = http_5xx_retry_count
    state["unacknowledged_candidate_count"] = len(ordered_candidates)
    state["stats"] = stats
    state["category_count"] = len(categories)
    state["parallel_workers_used"] = workers_used
    if remaining:
        state["category_index"] = 0
        state["page"] = base._normal_int(remaining[0].get("page"), 1)
    state_write_started = time.monotonic()
    base._write_json(state_path, state)
    state_write_seconds = time.monotonic() - state_write_started
    total_run_seconds = time.monotonic() - run_started

    print(
        "PARALLEL_CATALOG_SWEEP_SUMMARY "
        f"pages_attempted={len(batch)} pages_ok={processed_count} "
        f"terminal_pages={terminal_count} retries={retry_count} "
        f"empty_product_pages={empty_product_pages} nonempty_product_pages={nonempty_product_pages} "
        f"rate_limited={rate_limited_count} workers={state['parallel_workers_used']} "
        f"next_workers={worker_limit} "
        f"request_latency_count={len(request_latencies)} "
        f"request_latency_p50_s={request_latency_p50:.3f} "
        f"request_latency_p95_s={request_latency_p95:.3f} "
        f"request_latency_max_s={request_latency_max:.3f} "
        f"timeout_retries={timeout_retry_count} http_5xx_retries={http_5xx_retry_count} "
        f"products={page_row_count} categories={len(categories)} leaf_categories={state.get('parallel_leaf_category_count', 0)} "
        f"pending_pages={len(remaining)} candidates={len(ordered_candidates)} "
        f"pages_total={stats['pages_scanned_total']} "
        f"cycle_categories_complete={len(state.get('parallel_cycle_completed_category_ids', []))} "
        f"cycle_categories_unqueryable={len(state.get('parallel_cycle_unqueryable_category_ids', []))} "
        f"cycle_pages={state.get('parallel_cycle_pages_success', 0)} "
        f"fetch_s={fetch_seconds:.3f} process_s={processing_seconds:.3f} "
        f"candidate_write_s={candidate_write_seconds:.3f} state_write_s={state_write_seconds:.3f} "
        f"total_s={total_run_seconds:.3f} fetch_pages_per_s={state['parallel_last_batch_pages_per_second']:.2f} "
        f"rows_per_s={state['parallel_last_batch_rows_per_second']:.2f} "
        f"candidate_bytes={candidate_file_bytes} "
        f"sort=harmonic_four_factor,demand,affordability,generality,discount_value full_pages=true "
        f"completed_cycles={stats['completed_cycles']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent resumable DigiKala catalog sweep")
    parser.add_argument("--pages-per-run", type=int, default=DEFAULT_PAGES_PER_RUN)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--refresh-categories", action="store_true")
    args = parser.parse_args()
    return run_parallel_sweep(
        pages_per_run=args.pages_per_run,
        workers=args.workers,
        force_refresh=args.refresh_categories,
    )


if __name__ == "__main__":
    sys.exit(main())
