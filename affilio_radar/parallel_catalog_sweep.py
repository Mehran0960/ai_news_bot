#!/usr/bin/env python3
"""Concurrent, resumable DigiKala category/page sweep for OfferChin.

This module reuses the existing parsing and candidate-ranking contract from
catalog_sweep.py, but replaces the single cursor with a persisted page queue.
A failed page is requeued and cannot silently advance the sweep.
"""
from __future__ import annotations

import argparse
import sys
import threading
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
DEFAULT_WORKERS = 12
_thread_local = threading.local()


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
    page = max(1, base._normal_int(task.get("page"), 1))
    if product_count <= 0 or page >= base.MAX_PAGES_PER_CATEGORY:
        return None
    if total_pages is not None and page >= total_pages:
        return None
    return {
        "category_id": str(task.get("category_id") or ""),
        "category_name": str(task.get("category_name") or task.get("category_id") or ""),
        "page": page + 1,
        "attempts": 0,
    }


def _fetch_page(task: dict) -> dict:
    """Fetch one page. 400/404 close an unqueryable category/page; other
    failures are retryable and remain in the persisted queue.
    """
    category_id = str(task.get("category_id") or "")
    page = max(1, base._normal_int(task.get("page"), 1))
    try:
        response = _session().get(
            base.SEARCH_URL,
            params={"categories[]": category_id, "page": page},
            timeout=base.REQUEST_TIMEOUT,
        )
        if response.status_code in (400, 404):
            return {"kind": "terminal", "status_code": response.status_code, "rows": []}
        if response.status_code == 429:
            return {"kind": "retry", "status_code": 429, "rows": []}
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
        return {
            "kind": "ok", "rows": rows, "total_pages": total_pages,
            "status_code": response.status_code,
        }
    except Exception as exc:  # keep the cursor safe on all transient/schema failures
        return {
            "kind": "retry", "rows": [],
            "error": f"{type(exc).__name__}:{str(exc)[:140]}",
            "status_code": getattr(getattr(exc, "response", None), "status_code", None),
        }


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

    if not state.get("parallel_queue_initialized"):
        queue = build_initial_page_queue(
            categories,
            legacy_category_index=state.get("category_index", 0),
            legacy_page=state.get("page", 1),
        )
        known_ids = {str(row.get("id")) for row in categories if isinstance(row, dict)}
        state["parallel_queue_initialized"] = True
        state["parallel_cycle_started_at"] = base.iso_now()
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

    # De-duplicate persisted work without dropping retry attempt metadata.
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
    state["parallel_known_category_ids"] = sorted(
        known_ids, key=lambda value: int(value) if value.isdigit() else 0
    )
    state["parallel_pending_pages"] = unique
    return unique


def run_parallel_sweep(
    pages_per_run: int = DEFAULT_PAGES_PER_RUN,
    workers: int = DEFAULT_WORKERS,
    state_path: Path = STATE_PATH,
    candidates_path: Path = CANDIDATES_PATH,
    publisher_state_path: Path = PUBLISHER_STATE_PATH,
    force_refresh: bool = False,
    fetcher: Callable[[dict], dict] | None = None,
) -> int:
    """Process a bounded page batch concurrently and checkpoint atomically."""
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
    if not queue:
        # A cycle is complete only after every known page has been either read
        # successfully or explicitly shown to be an invalid/empty terminal page.
        stats["completed_cycles"] += 1
        state["completed_cycles"] = stats["completed_cycles"]
        state["last_cycle_completed_at"] = base.iso_now()
        queue = build_initial_page_queue(categories, 0, 1)
        state["parallel_pending_pages"] = queue
        state["parallel_cycle_started_at"] = base.iso_now()
        print("PARALLEL_CATALOG_CYCLE_COMPLETED")

    batch_limit = max(1, min(2000, int(pages_per_run)))
    requested_workers = max(1, min(32, int(workers)))
    batch = queue[:batch_limit]
    remaining = queue[batch_limit:]
    worker_fn = fetcher or _fetch_page
    worker_limit = requested_workers
    saved_limit = base._normal_int(state.get("parallel_worker_limit"), requested_workers)
    if saved_limit > 0:
        worker_limit = max(1, min(requested_workers, saved_limit))

    with ThreadPoolExecutor(max_workers=min(worker_limit, len(batch) or 1)) as pool:
        results = list(pool.map(worker_fn, batch))

    candidates = base._load_candidates_by_id(candidates_path)
    now = base.utc_now()
    seen_ids = base._publisher_seen_ids(publisher_state_path)
    candidates = base._clean_old_candidates(candidates, seen_ids, now)
    retry_count = 0
    rate_limited_count = 0
    processed_count = 0
    terminal_count = 0
    page_row_count = 0
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
        if kind == "terminal":
            terminal_count += 1
            if page == 1:
                stats["unqueryable_categories_total"] += 1
            continue

        total_pages = result.get("total_pages")
        total_pages = max(1, int(total_pages)) if total_pages is not None else None
        for row in rows:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("product_id") or "")
            if not pid:
                continue
            old = candidates.get(pid, {})
            first_seen = old.get("first_seen_at") or base.iso_now()
            candidates[pid] = {**old, **row, "first_seen_at": first_seen}
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

        state["last_successful_category_id"] = category_id
        state["last_successful_category_name"] = str(task.get("category_name") or category_id)
        state["last_successful_page"] = page
        state["last_successful_page_at"] = base.iso_now()
        state["last_error"] = ""

    # Sustained 429s automatically back concurrency down. A clean batch restores
    # one worker per run, never exceeding the configured ceiling.
    if rate_limited_count >= 3:
        worker_limit = max(2, worker_limit // 2)
    elif retry_count == 0 and worker_limit < requested_workers:
        worker_limit += 1
    state["parallel_worker_limit"] = worker_limit

    candidates = base._clean_old_candidates(candidates, seen_ids, base.utc_now())
    ordered_candidates = sorted(
        candidates.values(), key=base.catalog_candidate_sort_key, reverse=True
    )[:base.MAX_RETAINED_CANDIDATES]
    base._write_json(candidates_path, {
        "updated_at": base.iso_now(),
        "candidate_count": len(ordered_candidates),
        "candidates": ordered_candidates,
    })

    state["parallel_pending_pages"] = remaining
    state["pending_page_count"] = len(remaining)
    state["parallel_last_batch_at"] = base.iso_now()
    state["parallel_last_batch_pages"] = len(batch)
    state["parallel_last_batch_successes"] = processed_count
    state["parallel_last_batch_terminals"] = terminal_count
    state["parallel_last_batch_retries"] = retry_count
    state["parallel_last_batch_rate_limited"] = rate_limited_count
    state["parallel_last_batch_product_rows"] = page_row_count
    state["unacknowledged_candidate_count"] = len(ordered_candidates)
    state["stats"] = stats
    state["category_count"] = len(categories)
    state["parallel_workers_used"] = min(worker_limit, len(batch) or 1)
    if remaining:
        state["category_index"] = 0
        state["page"] = base._normal_int(remaining[0].get("page"), 1)
    base._write_json(state_path, state)

    print(
        "PARALLEL_CATALOG_SWEEP_SUMMARY "
        f"pages_attempted={len(batch)} pages_ok={processed_count} "
        f"terminal_pages={terminal_count} retries={retry_count} "
        f"rate_limited={rate_limited_count} workers={state['parallel_workers_used']} "
        f"products={page_row_count} categories={len(categories)} "
        f"pending_pages={len(remaining)} candidates={len(ordered_candidates)} "
        f"pages_total={stats['pages_scanned_total']} "
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
