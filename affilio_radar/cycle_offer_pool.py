"""Cycle-scoped, quality-gated OfferChin candidate pool and adaptive cadence."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

BASE_PUBLICATION_INTERVAL_SECONDS = 27 * 60
DEFAULT_CYCLE_DURATION_SECONDS = 34 * 60 * 60
MAX_CYCLE_POOL_ITEMS = 500
MIN_CATEGORY_PEERS = 5


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").replace(",", "").strip()))
    except (TypeError, ValueError, OverflowError):
        return default


def _cycle_duration(started_at: Any, completed_at: Any) -> int:
    started = _utc(started_at)
    completed = _utc(completed_at)
    if started is None or completed is None:
        return DEFAULT_CYCLE_DURATION_SECONDS
    seconds = int((completed - started).total_seconds())
    # Ignore corrupt clocks and implausible outliers rather than creating a
    # multi-week publication pause from a malformed status record.
    if seconds < 2 * 60 * 60 or seconds > 14 * 24 * 60 * 60:
        return DEFAULT_CYCLE_DURATION_SECONDS
    return seconds


def _category_key(item: dict) -> str:
    category_ids = item.get("catalog_category_ids")
    if isinstance(category_ids, list):
        valid = [str(value) for value in category_ids if str(value).isdigit()]
        if valid:
            return "id:" + valid[-1]
    for key in ("catalog_category_id", "category"):
        value = str(item.get(key) or "").strip().lower()
        if value:
            return key + ":" + value
    return "unknown"


def _fresh_bestseller_rank(item: dict, now: datetime) -> int:
    source = str(item.get("selection_demand_evidence") or "")
    if source == "digikala_native_bestseller_rank":
        rank = _int(item.get("selection_bestseller_rank"))
        observed = _utc(item.get("selection_bestseller_observed_at"))
        if not 1 <= rank <= 60 or observed is None:
            return 0
        age = (now - observed).total_seconds() / 3600
        return rank if -0.1 <= age <= 24 else 0

    # Compatibility for candidates which reached the pool without selection
    # metadata: require the catalog's explicit native bestseller sort mode.
    if item.get("catalog_sort_mode") != "best_selling":
        return 0
    if not str(item.get("product_id") or "").lower().startswith("dkp-"):
        return 0
    rank = _int(item.get("catalog_best_selling_rank"))
    observed = _utc(item.get("catalog_rank_observed_at"))
    if not 1 <= rank <= 60 or observed is None:
        return 0
    age = (now - observed).total_seconds() / 3600
    return rank if -0.1 <= age <= 24 else 0


def _demand_sort_key(item: dict, now: datetime) -> tuple[int, int, int]:
    rank = _fresh_bestseller_rank(item, now)
    if rank:
        tier = 3 if rank <= 10 else 2 if rank <= 30 else 1
        return tier, 61 - rank, 0
    growth = _int(item.get("recent_review_growth_window", item.get("recent_review_growth_7d")))
    window = _int(item.get("demand_window_hours"))
    source = str(item.get("demand_signal_source") or "")
    observed = _utc(item.get("demand_observed_at"))
    age = (now - observed).total_seconds() / 3600 if observed else 999999
    verified = (
        item.get("current_demand_verified") is True
        and growth >= 3
        and 6 <= window <= 24
        and source in {"digikala_recent_review_growth", "snappshop_recent_review_growth"}
        and -0.1 <= age <= 12
    )
    if verified:
        return 0, 0, min(20, growth)
    return 0, 0, 0


def _apply_affordability_percentiles(items: list[dict]) -> None:
    prices = [_int(row.get("current_price")) for row in items if _int(row.get("current_price")) > 0]
    categories: dict[str, list[int]] = {}
    for row in items:
        price = _int(row.get("current_price"))
        if price > 0:
            categories.setdefault(_category_key(row), []).append(price)
    for row in items:
        price = _int(row.get("current_price"))
        if price <= 0 or not prices:
            row["selection_global_affordability_percentile"] = 0
            row["selection_category_affordability_percentile"] = 0
            row["selection_affordability_percentile"] = 0
            row["selection_affordability_tier"] = "unknown"
            continue
        global_percentile = round(100 * sum(peer >= price for peer in prices) / len(prices))
        category_peers = categories.get(_category_key(row), [])
        category_percentile = (
            round(100 * sum(peer >= price for peer in category_peers) / len(category_peers))
            if len(category_peers) >= MIN_CATEGORY_PEERS else global_percentile
        )
        # Global purchase accessibility has the larger weight; category position
        # prevents expensive categories from being discarded automatically.
        percentile = max(0, min(100, round(global_percentile * 0.70 + category_percentile * 0.30)))
        row["selection_global_affordability_percentile"] = global_percentile
        row["selection_category_affordability_percentile"] = category_percentile
        row["selection_affordability_percentile"] = percentile
        row["selection_affordability_tier"] = (
            "accessible" if percentile >= 67
            else "midrange" if percentile >= 34
            else "premium"
        )


def _has_fresh_demand(item: dict, now: datetime) -> bool:
    if _fresh_bestseller_rank(item, now) > 0:
        return True
    growth = _int(item.get("recent_review_growth_window", item.get("recent_review_growth_7d")))
    window = _int(item.get("demand_window_hours"))
    observed = _utc(item.get("demand_observed_at"))
    source = str(item.get("demand_signal_source") or "")
    age = (now - observed).total_seconds() / 3600 if observed else 999999
    return bool(
        item.get("current_demand_verified") is True
        and growth >= 3
        and 6 <= window <= 24
        and source in {"digikala_recent_review_growth", "snappshop_recent_review_growth"}
        and -0.1 <= age <= 12
    )


def _has_verified_discount_value(item: dict, now: datetime) -> bool:
    history_at = _utc(item.get("history_checked_at"))
    history_fresh = bool(
        history_at is not None
        and -0.1 <= (now - history_at).total_seconds() / 3600 <= 24
    )
    if item.get("history_status") == "verified" and history_fresh:
        # A fresh negative history verdict is a hard contradiction; market proof
        # must not be used to wash it out.
        return item.get("historical_deal_eligible") is True
    market_at = _utc(item.get("market_price_checked_at"))
    market_fresh = bool(
        market_at is not None
        and -0.1 <= (now - market_at).total_seconds() / 3600 <= 24
    )
    return bool(
        item.get("market_status") == "verified"
        and item.get("market_reference_kind") == "seller_median"
        and market_fresh
        and _int(item.get("market_price_advantage_pct")) >= 5
    )


def _value_sort_key(item: dict) -> tuple[int, int, int, int]:
    history = int(
        item.get("history_status") == "verified"
        and item.get("historical_deal_eligible") is True
    )
    advantage = _int(item.get("market_price_advantage_pct"))
    discount = max(0, min(100, _int(item.get("discount_percent"))))
    savings = max(0, _int(item.get("savings_toman")))
    return history, advantage, discount, savings


def _sort_key(item: dict, now: datetime) -> tuple:
    demand_tier, rank_strength, growth = _demand_sort_key(item, now)
    return (
        demand_tier,
        rank_strength,
        growth,
        _int(item.get("selection_affordability_percentile"), 50),
        *_value_sort_key(item),
        str(item.get("product_id") or ""),
    )


def _normalize_pool(state: dict, cycle_completed_at: str, cycle_started_at: str, now: datetime) -> dict:
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict) or str(pool.get("cycle_completed_at") or "") != cycle_completed_at:
        duration = _cycle_duration(cycle_started_at, cycle_completed_at)
        completed = _utc(cycle_completed_at) or now
        target = completed + timedelta(seconds=duration)
        if target <= now:
            target = now + timedelta(seconds=duration)
        pool = {
            "schema_version": 1,
            "cycle_completed_at": cycle_completed_at,
            "cycle_started_at": cycle_started_at,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "cycle_duration_seconds": duration,
            "target_next_cycle_at": target.isoformat(),
            "items": [],
            "consumed_ids": [],
            "rejected_ids": {},
        }
        state["cycle_offer_pool"] = pool
    if not isinstance(pool.get("items"), list):
        pool["items"] = []
    if not isinstance(pool.get("consumed_ids"), list):
        pool["consumed_ids"] = []
    if not isinstance(pool.get("rejected_ids"), dict):
        pool["rejected_ids"] = {}
    return pool


def merge_cycle_offers(
    state: dict,
    candidates: list[dict],
    *,
    cycle_completed_at: Any,
    cycle_started_at: Any = None,
    now: datetime | None = None,
    max_items: int = MAX_CYCLE_POOL_ITEMS,
) -> dict[str, int]:
    """Merge only already quality-gated candidates into the immutable cycle pool."""
    current = _utc(now) or datetime.now(timezone.utc)
    cycle_id = str(cycle_completed_at or "").strip()
    if not cycle_id:
        return {"added": 0, "updated": 0, "remaining": 0}
    pool = _normalize_pool(
        state, cycle_id, str(cycle_started_at or ""), current
    )
    items_by_id = {
        str(item.get("product_id") or "").lower(): dict(item)
        for item in pool["items"]
        if isinstance(item, dict) and str(item.get("product_id") or "")
    }
    consumed = {str(value).lower() for value in pool["consumed_ids"]}
    rejected = {str(value).lower() for value in pool["rejected_ids"]}
    added = updated = 0
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        pid = str(candidate.get("product_id") or "").strip().lower()
        if not re.fullmatch(r"(?:dkp|snp)-\d{1,12}", pid):
            continue
        if pid in consumed or pid in rejected:
            continue
        price = _int(candidate.get("current_price"))
        if price <= 0 or _int(candidate.get("discount_percent")) <= 0:
            continue
        if not _has_fresh_demand(candidate, current):
            continue
        if not _has_verified_discount_value(candidate, current):
            continue
        value = dict(candidate)
        value["product_id"] = pid
        value["cycle_pool_seen_at"] = current.isoformat()
        if pid in items_by_id:
            updated += 1
        else:
            added += 1
        items_by_id[pid] = value

    items = list(items_by_id.values())
    _apply_affordability_percentiles(items)
    items.sort(key=lambda item: _sort_key(item, current), reverse=True)
    cap = max(1, min(3000, int(max_items)))
    if len(items) > cap:
        keep_ids = {
            str(item.get("product_id") or "")
            for item in items[:cap]
        }
        # Never drop a candidate that is already queued for a partial channel retry.
        queue = state.get("content_delivery_queue")
        if isinstance(queue, dict):
            for pid, entry in queue.items():
                if isinstance(entry, dict) and entry.get("status") not in {
                    "published", "cancelled", "stale_selection", "expired"
                }:
                    keep_ids.add(str(pid))
        items = [item for item in items if str(item.get("product_id") or "") in keep_ids]
    pool["items"] = items
    pool["updated_at"] = current.isoformat()
    pool.pop("dispatchable_count", None)
    pool.pop("dispatchable_updated_at", None)
    return {
        "added": added,
        "updated": updated,
        "remaining": pool_remaining_count(state),
        "retained": len(items),
    }


def cycle_offer_candidates(state: dict, *, now: datetime | None = None, limit: int = 500) -> list[dict]:
    """Return unconsumed cycle candidates; active queue entries remain reserved."""
    current = _utc(now) or datetime.now(timezone.utc)
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict) or not isinstance(pool.get("items"), list):
        return []
    consumed = {str(value).lower() for value in pool.get("consumed_ids", [])}
    rejected = {
        str(value).lower()
        for value in (pool.get("rejected_ids") or {})
    }
    published = state.get("published") if isinstance(state.get("published"), dict) else {}
    active_queue = state.get("content_delivery_queue")
    active_ids = set()
    if isinstance(active_queue, dict):
        active_ids = {
            str(pid).lower()
            for pid, entry in active_queue.items()
            if isinstance(entry, dict) and entry.get("status") not in {
                "published", "cancelled", "stale_selection", "expired"
            }
        }
    candidates = []
    for raw in pool["items"]:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("product_id") or "").lower()
        if not pid or pid in consumed or pid in rejected or pid in active_ids:
            continue
        record = published.get(pid)
        if isinstance(record, dict):
            delivery = record.get("delivery_status") if isinstance(record.get("delivery_status"), dict) else {}
            if any(value == "sent" for value in delivery.values()):
                continue
            if any(str(record.get(field) or "").isdigit() for field in (
                "telegram_message_id", "bale_message_id", "rubika_message_id", "eitaa_message_id"
            )):
                continue
        candidates.append(dict(raw))
    _apply_affordability_percentiles(candidates)
    candidates.sort(key=lambda item: _sort_key(item, current), reverse=True)
    return candidates[:max(1, int(limit))]


def mark_cycle_offer_consumed(state: dict, product_id: str, *, now: datetime | None = None) -> None:
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict):
        return
    pid = str(product_id or "").lower()
    if not pid:
        return
    consumed = pool.setdefault("consumed_ids", [])
    if pid not in consumed:
        consumed.append(pid)
    rejected = pool.get("rejected_ids")
    if isinstance(rejected, dict):
        rejected.pop(pid, None)
    pool["updated_at"] = (_utc(now) or datetime.now(timezone.utc)).isoformat()


def mark_cycle_offer_rejected(
    state: dict,
    product_id: str,
    reason: str,
    *,
    now: datetime | None = None,
) -> None:
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict):
        return
    pid = str(product_id or "").lower()
    if not pid:
        return
    rejected = pool.setdefault("rejected_ids", {})
    if isinstance(rejected, dict):
        rejected[pid] = {
            "reason": str(reason or "quality_gate_failed")[:120],
            "at": (_utc(now) or datetime.now(timezone.utc)).isoformat(),
        }
    pool["updated_at"] = (_utc(now) or datetime.now(timezone.utc)).isoformat()


def pool_remaining_count(state: dict) -> int:
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict) or not isinstance(pool.get("items"), list):
        return 0
    consumed = {str(value).lower() for value in pool.get("consumed_ids", [])}
    rejected = {str(value).lower() for value in (pool.get("rejected_ids") or {})}
    published = state.get("published") if isinstance(state.get("published"), dict) else {}
    count = 0
    for item in pool["items"]:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("product_id") or "").lower()
        if not pid or pid in consumed or pid in rejected:
            continue
        record = published.get(pid)
        if isinstance(record, dict):
            delivery = record.get("delivery_status") if isinstance(record.get("delivery_status"), dict) else {}
            if any(value == "sent" for value in delivery.values()):
                continue
            if any(str(record.get(field) or "").isdigit() for field in (
                "telegram_message_id", "bale_message_id", "rubika_message_id", "eitaa_message_id"
            )):
                continue
        count += 1
    return count


def set_pool_dispatchable_count(
    state: dict,
    count: int,
    *,
    now: datetime | None = None,
) -> None:
    """Store the count that passed the current demand/value/cooldown selector."""
    pool = state.get("cycle_offer_pool")
    if not isinstance(pool, dict):
        return
    pool["dispatchable_count"] = max(0, int(count))
    pool["dispatchable_updated_at"] = (_utc(now) or datetime.now(timezone.utc)).isoformat()


def _active_queue_ids(state: dict) -> set[str]:
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return set()
    terminal = {"published", "cancelled", "stale_selection", "expired"}
    return {
        str(pid).lower()
        for pid, entry in queue.items()
        if isinstance(entry, dict) and entry.get("status") not in terminal
    }


def pool_runtime_projection(
    state: dict,
    *,
    now: datetime | None = None,
    base_interval_seconds: int = BASE_PUBLICATION_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Compute the adaptive slot and pending-work count for Cloudflare's compact sidecar."""
    current = _utc(now) or datetime.now(timezone.utc)
    base = max(BASE_PUBLICATION_INTERVAL_SECONDS, int(base_interval_seconds))
    pool = state.get("cycle_offer_pool")
    active_ids = _active_queue_ids(state)
    if not isinstance(pool, dict) or not isinstance(pool.get("items"), list):
        # Complete legacy one-item hand-offs during rollout even before a cycle pool exists.
        return {
            "available_count": len(active_ids),
            "remaining_count": 0,
            "interval_seconds": base,
            "cycle_completed_at": "",
        }

    remaining = pool_remaining_count(state)
    pool_ids = {
        str(item.get("product_id") or "").lower()
        for item in pool["items"] if isinstance(item, dict)
    }
    consumed_ids = {str(value).lower() for value in pool.get("consumed_ids", [])}
    rejected_ids = {str(value).lower() for value in (pool.get("rejected_ids") or {})}
    active_pool_ids = active_ids.intersection(pool_ids - consumed_ids - rejected_ids)
    legacy_active_count = len(active_ids - pool_ids)
    consumed = len(consumed_ids)

    # A recent selector count represents candidates which passed fresh demand,
    # price-value, and cooldown checks. Queue reservations are added separately
    # because a subsequent selector run intentionally excludes already queued IDs.
    dispatchable = remaining
    dispatchable_at = _utc(pool.get("dispatchable_updated_at"))
    if dispatchable_at is not None and 0 <= (current - dispatchable_at).total_seconds() <= 45 * 60:
        dispatchable = max(0, min(remaining, _int(pool.get("dispatchable_count"), remaining)))
    available = min(remaining, dispatchable + len(active_pool_ids)) + legacy_active_count

    if available <= 0 or consumed == 0:
        interval = base
    else:
        target = _utc(pool.get("target_next_cycle_at"))
        duration = max(2 * 60 * 60, _int(pool.get("cycle_duration_seconds"), DEFAULT_CYCLE_DURATION_SECONDS))
        remaining_window = (target - current).total_seconds() if target else duration
        if remaining_window <= 0:
            remaining_window = duration
            pool["target_next_cycle_at"] = (current + timedelta(seconds=duration)).isoformat()
        interval = max(base, int(math.ceil(remaining_window / max(1, available))))
    return {
        "available_count": available,
        "remaining_count": remaining,
        "interval_seconds": interval,
        "cycle_completed_at": str(pool.get("cycle_completed_at") or ""),
        "cycle_duration_seconds": _int(pool.get("cycle_duration_seconds"), DEFAULT_CYCLE_DURATION_SECONDS),
    }
