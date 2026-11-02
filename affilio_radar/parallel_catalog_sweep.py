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


def build_initial_page_queue(categories: list[dict], legacy_category_index: int = 0, legacy_page: int = 1) -> list[dict]:
    """Start each cycle at page one for both demand sort orders."""
    tasks = []
    for sort_mode in ("best_selling", "most_viewed"):
        for category in categories:
            if not isinstance(category, dict): continue
            cid = str(category.get("id") or "")
            if cid.isdigit():
                tasks.append({"category_id":cid,"category_name":str(category.get("name") or cid),
                              "page":1,"sort_mode":sort_mode,"attempts":0})
    return tasks


def _task_key(task: dict) -> tuple[str, int, str]:
    mode = str(task.get("sort_mode") or "best_selling")
    return (str(task.get("category_id") or ""), max(1, base._normal_int(task.get("page"),1)),
            mode if mode in {"best_selling","most_viewed"} else "best_selling")


def _next_page_task(task: dict, total_pages: int | None, product_count: int) -> dict | None:
    page=max(1,base._normal_int(task.get("page"),1)); mode=str(task.get("sort_mode") or "best_selling")
    if product_count<=0: return None
    if mode=="most_viewed" and page>=base.MOST_VIEWED_MAX_PAGES_PER_CATEGORY: return None
    if total_pages is not None and page>=total_pages: return None
    nxt={"category_id":str(task.get("category_id") or ""),
         "category_name":str(task.get("category_name") or task.get("category_id") or ""),
         "page":page+1,"sort_mode":mode,"attempts":0}
    if total_pages is not None: nxt["known_total_pages"]=int(total_pages)
    return nxt


def _fetch_page(task: dict) -> dict:
    """Fetch one page; label inferred pagination boundaries explicitly."""
    cid=str(task.get("category_id") or ""); page=max(1,base._normal_int(task.get("page"),1))
    mode=str(task.get("sort_mode") or "best_selling")
    sort_value=base.MOST_VIEWED_SORT_VALUE if mode=="most_viewed" else base.BEST_SELLING_SORT_VALUE
    try:
        response=_session().get(base.SEARCH_URL,params={"categories[]":cid,"page":page,"sort":sort_value},
                                timeout=base.REQUEST_TIMEOUT)
        if response.status_code==404 and page>1:
            known=base._normal_int(task.get("known_total_pages"))
            return {"kind":"end" if not known or page>known else "terminal","status_code":404,
                    "rows":[],"inferred_boundary":not bool(known)}
        if response.status_code in (400,404): return {"kind":"terminal","status_code":response.status_code,"rows":[]}
        if response.status_code==429: return {"kind":"retry","status_code":429,"rows":[]}
        response.raise_for_status()
        if len(response.content)>8_000_000: raise base.CatalogSweepError("api_response_exceeded_8mb")
        try: payload=response.json()
        except ValueError as exc: raise base.CatalogSweepError("api_returned_non_json") from exc
        if not isinstance(payload,dict): raise base.CatalogSweepError("api_payload_not_object")
        rows=base.extract_product_rows(payload)
        total=base.extract_total_pages(payload,page,len(rows))
        total_items=base.extract_total_items(payload)
        return {"kind":"ok","rows":rows,"total_pages":total,"total_items":total_items,
                "status_code":response.status_code}
    except Exception as exc:
        return {"kind":"retry","rows":[],"error":f"{type(exc).__name__}:{str(exc)[:140]}",
                "status_code":getattr(getattr(exc,"response",None),"status_code",None)}


def _ensure_parallel_state(state: dict) -> list[dict]:
    cats=state.get("categories",[]); cats=cats if isinstance(cats,list) else []
    raw=state.get("parallel_pending_pages",[]); queue=raw if isinstance(raw,list) else []
    known=state.get("parallel_known_category_ids",[]); known_ids={str(x) for x in known} if isinstance(known,list) else set()
    if not state.get("parallel_queue_initialized"):
        queue=build_initial_page_queue(cats)
        known_ids={str(row.get("id")) for row in cats if isinstance(row,dict)}
        state["parallel_queue_initialized"]=True
        state["parallel_most_viewed_seeded"]=True
        state["parallel_exhaustive_pages_seeded"]=True
        state["parallel_cycle_started_at"]=base.iso_now()
        state["parallel_cycle_pages_succeeded"]=0
        state["parallel_cycle_unqueryable_tasks"]=[]
        state["parallel_cycle_inferred_end_pages"]=0
    else:
        for c in cats:
            if not isinstance(c,dict): continue
            cid=str(c.get("id") or "")
            if cid.isdigit() and cid not in known_ids:
                for mode in ("best_selling","most_viewed"):
                    queue.append({"category_id":cid,"category_name":str(c.get("name") or cid),
                                  "page":1,"sort_mode":mode,"attempts":0})
                known_ids.add(cid)
        if not state.get("parallel_exhaustive_pages_seeded"):
            # One-time migration from the former 3-page cap: every category
            # must resume at page 4, including categories with no old pending task.
            for c in cats:
                if not isinstance(c,dict): continue
                cid=str(c.get("id") or "")
                if cid.isdigit():
                    queue.append({"category_id":cid,"category_name":str(c.get("name") or cid),
                                  "page":4,"sort_mode":"best_selling","attempts":0})
            state["parallel_exhaustive_pages_seeded"]=True
        if not state.get("parallel_most_viewed_seeded"):
            for c in cats:
                if isinstance(c,dict) and str(c.get("id") or "").isdigit():
                    cid=str(c["id"])
                    queue.append({"category_id":cid,"category_name":str(c.get("name") or cid),
                                  "page":1,"sort_mode":"most_viewed","attempts":0})
            state["parallel_most_viewed_seeded"]=True
    unique=[]; seen=set()
    for raw_task in queue:
        if not isinstance(raw_task,dict): continue
        task=dict(raw_task)
        if task.get("sort_mode") not in {"best_selling","most_viewed"}: task["sort_mode"]="best_selling"
        key=_task_key(task)
        if not key[0].isdigit() or key in seen: continue
        seen.add(key); unique.append(task)
    state["parallel_known_category_ids"]=sorted(known_ids,key=lambda x:int(x) if x.isdigit() else 0)
    ordered=base.sort_categories_for_sweep(cats)
    ranks={str(row.get("id") or ""):i for i,row in enumerate(ordered) if isinstance(row,dict)}
    unique.sort(key=lambda t:(max(1,base._normal_int(t.get("page"),1)),
                              0 if t.get("sort_mode")=="best_selling" else 1,
                              ranks.get(str(t.get("category_id") or ""),len(ranks)),
                              base._normal_int(t.get("attempts"))))
    parent_ids={str(row.get("parent_id") or "") for row in ordered
                if str(row.get("parent_id") or "").isdigit()}
    state["parallel_pending_pages"]=unique
    state["parallel_leaf_category_count"]=sum(str(row.get("id") or "") not in parent_ids for row in ordered)
    state["parallel_sort_modes"]=["best_selling","most_viewed"]
    return unique


def _merge_ranked_candidate(old: dict, row: dict, task: dict, rank: int,
                            total_pages: int | None, total_items: int | None,
                            observed_at: str, first_seen_at: str) -> dict:
    cid=str(task.get("category_id") or ""); name=str(task.get("category_name") or cid)
    mode=str(task.get("sort_mode") or "best_selling")
    category_ids={str(x) for x in old.get("catalog_category_ids",[]) if str(x).isdigit()}
    category_ids.add(cid)
    key="catalog_best_selling_ranks_by_category" if mode=="best_selling" else "catalog_most_viewed_ranks_by_category"
    records=old.get(key,{}); records=dict(records) if isinstance(records,dict) else {}
    percentile=base._rank_percentile(
        rank,total_pages,base.BEST_SELLING_PAGE_SIZE,total_items=total_items
    )
    current={"rank":rank,"observed_at":observed_at,"category_name":name,
             "total_pages":total_pages,"total_items":total_items}
    if percentile is not None: current["percentile"]=percentile
    records[cid]=current
    valid=[]
    for saved_id,rec in records.items():
        if not str(saved_id).isdigit() or not isinstance(rec,dict): continue
        saved_rank=base._normal_int(rec.get("rank"))
        try:
            stamp=base.datetime.fromisoformat(str(rec.get("observed_at") or "").replace("Z","+00:00"))
            if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=base.timezone.utc)
            age=(base.utc_now()-stamp.astimezone(base.timezone.utc)).total_seconds()/3600
        except (TypeError,ValueError,OverflowError): continue
        max_age=base.BEST_SELLING_MAX_AGE_HOURS if mode=="best_selling" else base.MOST_VIEWED_MAX_AGE_HOURS
        if saved_rank>0 and 0<=age<=max_age: valid.append((rec.get("percentile"),saved_rank,saved_id,rec))
    def quality(item):
        pct,r,_,_=item
        return (1,float(pct),-r) if pct is not None else (0,0.0,-r)
    best=max(valid,key=quality) if valid else (percentile,rank,cid,current)
    result={**old,**row,"first_seen_at":first_seen_at,"catalog_category_id":cid,
            "catalog_category_name":name,"catalog_category_ids":sorted(category_ids,key=int),
            "catalog_category_page_counts":{**(old.get("catalog_category_page_counts") or {}),f"{mode}:{cid}":total_pages},
            "catalog_category_product_counts":{**(old.get("catalog_category_product_counts") or {}),f"{mode}:{cid}":total_items}}
    if mode=="best_selling":
        result.update({"catalog_sort_mode":"best_selling","catalog_best_selling_ranks_by_category":records,
                       "catalog_best_selling_rank":best[1],"catalog_best_selling_percentile":best[0] or 0,
                       "catalog_best_selling_category_id":best[2],
                       "catalog_best_selling_category_name":str(best[3].get("category_name") or name),
                       "catalog_rank_observed_at":str(best[3].get("observed_at") or observed_at)})
    else:
        result.update({"catalog_most_viewed_ranks_by_category":records,"catalog_most_viewed_rank":best[1],
                       "catalog_most_viewed_percentile":best[0] or 0,
                       "catalog_most_viewed_category_id":best[2],
                       "catalog_most_viewed_category_name":str(best[3].get("category_name") or name),
                       "catalog_most_viewed_observed_at":str(best[3].get("observed_at") or observed_at)})
        if old.get("catalog_sort_mode")!="best_selling": result["catalog_sort_mode"]="most_viewed"
    return result


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
        "empty_product_pages_total", "nonempty_product_pages_total",
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
        unavailable = state.get("parallel_cycle_unqueryable_tasks", [])
        unavailable = unavailable if isinstance(unavailable, list) else []
        inferred = max(0, base._normal_int(state.get("parallel_cycle_inferred_end_pages")))
        status = "partial_unqueryable_categories" if unavailable else "complete_with_inferred_boundaries" if inferred else "complete"
        state["last_cycle_coverage"] = {
            "status": status, "finished_at": base.iso_now(),
            "pages_succeeded": max(0, base._normal_int(state.get("parallel_cycle_pages_succeeded"))),
            "unqueryable_category_sort_tasks": unavailable, "inferred_pagination_boundaries": inferred,
            "category_count": len(categories), "sort_modes": ["best_selling", "most_viewed"],
        }
        if status == "complete": stats["completed_cycles"] += 1
        else: stats["partial_cycles"] = max(0, base._normal_int(stats.get("partial_cycles"))) + 1
        state["completed_cycles"] = stats["completed_cycles"]
        state["last_cycle_completed_at"] = base.iso_now()
        queue = build_initial_page_queue(categories)
        state["parallel_pending_pages"] = queue
        state["parallel_cycle_started_at"] = base.iso_now()
        state["parallel_cycle_pages_succeeded"] = 0
        state["parallel_cycle_unqueryable_tasks"] = []
        state["parallel_cycle_inferred_end_pages"] = 0
        print(f"PARALLEL_CATALOG_CYCLE_COMPLETED coverage={status}")

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
    empty_product_pages = 0
    nonempty_product_pages = 0
    pending_keys = {_task_key(task) for task in remaining if isinstance(task, dict)}
    end_count = inferred_end_count = 0
    unqueryable_tasks = state.get("parallel_cycle_unqueryable_tasks", [])
    if not isinstance(unqueryable_tasks, list): unqueryable_tasks = []
    unavailable_set = set(str(x) for x in unqueryable_tasks)

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

        if kind == "end":
            end_count += 1
            terminal_count += 1
            if result.get("inferred_boundary"):
                inferred_end_count += 1
                state["parallel_cycle_inferred_end_pages"] = base._normal_int(state.get("parallel_cycle_inferred_end_pages")) + 1
            continue
        if kind == "terminal":
            terminal_count += 1
            marker=f"{category_id}:{task.get('sort_mode') or 'best_selling'}"
            if marker not in unavailable_set:
                unqueryable_tasks.append(marker); unavailable_set.add(marker)
            stats["unqueryable_categories_total"] += 1
            continue
        processed_count += 1
        state["parallel_cycle_pages_succeeded"] = base._normal_int(state.get("parallel_cycle_pages_succeeded")) + 1
        if rows:
            nonempty_product_pages += 1; stats["nonempty_product_pages_total"] += 1
        else:
            empty_product_pages += 1; stats["empty_product_pages_total"] += 1
        total_pages=result.get("total_pages")
        total_pages=max(1,int(total_pages)) if total_pages is not None else None
        total_items=result.get("total_items")
        total_items=max(1,int(total_items)) if total_items is not None else None
        observed=base.iso_now(); start_rank=(page-1)*base.BEST_SELLING_PAGE_SIZE
        for idx,row in enumerate(rows):
            if not isinstance(row,dict): continue
            pid=str(row.get("product_id") or "")
            if not pid: continue
            old=candidates.get(pid,{})
            old=old if isinstance(old,dict) else {}
            candidates[pid]=_merge_ranked_candidate(
                old,row,task,start_rank+idx+1,total_pages,total_items,observed,
                old.get("first_seen_at") or observed
            )
            stats["catalog_candidate_cards_found_total"] += 1
            if base._normal_int(row.get("discount_percent"))>=base.MIN_CANDIDATE_DISCOUNT:
                stats["discounted_candidates_found_total"] += 1
        page_row_count += len(rows)
        stats["pages_scanned_total"] += 1
        stats["product_rows_scanned_total"] += len(rows)
        next_task=_next_page_task(task,total_pages,len(rows))
        if next_task and _task_key(next_task) not in pending_keys:
            remaining.append(next_task); pending_keys.add(_task_key(next_task))
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
    ordered_candidates = base.retain_diverse_candidates(
        list(candidates.values()), limit=base.MAX_RETAINED_CANDIDATES,
        rotation=stats["pages_scanned_total"],
    )
    base._write_json(candidates_path, {
        "updated_at": base.iso_now(),
        "candidate_count": len(ordered_candidates),
        "candidates": ordered_candidates,
    })

    state["parallel_pending_pages"] = remaining
    state["pending_page_count"] = len(remaining)
    state["parallel_cycle_unqueryable_tasks"] = unqueryable_tasks
    state["parallel_last_batch_at"] = base.iso_now()
    state["parallel_last_batch_pages"] = len(batch)
    state["parallel_last_batch_successes"] = processed_count
    state["parallel_last_batch_terminals"] = terminal_count
    state["parallel_last_batch_retries"] = retry_count
    state["parallel_last_batch_rate_limited"] = rate_limited_count
    state["parallel_last_batch_product_rows"] = page_row_count
    state["parallel_last_batch_empty_product_pages"] = empty_product_pages
    state["parallel_last_batch_nonempty_product_pages"] = nonempty_product_pages
    state["parallel_last_batch_end_pages"] = end_count
    state["parallel_last_batch_inferred_boundaries"] = inferred_end_count
    state["parallel_last_batch_unqueryable_tasks"] = len(unavailable_set)
    state["parallel_coverage_status"] = (
        "in_progress" if remaining else
        "partial_unqueryable_categories" if unavailable_set else
        "complete_with_inferred_boundaries" if base._normal_int(state.get("parallel_cycle_inferred_end_pages")) else
        "complete"
    )
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
        f"empty_product_pages={empty_product_pages} nonempty_product_pages={nonempty_product_pages} "
        f"rate_limited={rate_limited_count} workers={state['parallel_workers_used']} "
        f"products={page_row_count} categories={len(categories)} leaf_categories={state.get('parallel_leaf_category_count', 0)} "
        f"pending_pages={len(remaining)} candidates={len(ordered_candidates)} "
        f"pages_total={stats['pages_scanned_total']} end_pages={end_count} "
        f"unqueryable_tasks={len(unavailable_set)} sort=best_selling+most_viewed bestseller_pages=uncapped "
        f"coverage={state['parallel_coverage_status']} completed_cycles={stats['completed_cycles']} "
        f"partial_cycles={stats.get('partial_cycles', 0)}"
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
