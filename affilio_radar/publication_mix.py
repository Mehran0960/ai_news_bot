"""Plan product and editorial posts across one full-catalog scan window.

Products are distributed across the available 27-minute slots. Editorial items
are created just-in-time for the unoccupied slots by editorial_publisher.py.
The estimate is deliberately refreshed on every selection run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATUS_PATH = ROOT / "catalog_sweep_status.json"
DEFAULT_INTERVAL_MINUTES = 27
DEFAULT_SCAN_HORIZON_HOURS = 30
MAX_SCAN_HORIZON_HOURS = 72
DEFAULT_QUEUE_LIMIT = 100


def parse_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def load_catalog_status(path: Path = STATUS_PATH) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def catalog_cycle_id(status: dict) -> str:
    """Use the immutable clean snapshot identity; fall back only during warm-up."""
    if not isinstance(status, dict):
        return "warmup"
    for key in (
        "completed_candidates_cycle_at",
        "last_clean_cycle_completed_at",
        "current_cycle_started_at",
        "last_cycle_started_at",
    ):
        value = str(status.get(key) or "").strip()
        if value:
            return value
    return "warmup"


def estimate_next_clean_scan_deadline(
    status: dict,
    *,
    now: datetime | None = None,
    fallback_hours: float | None = None,
) -> tuple[datetime, str]:
    """Estimate the next clean snapshot; fall back safely when the live scan is stalled.

    A previous clean cycle gives a duration estimate. It is projected from the
    current cycle's start. If that estimate is already overdue, malformed, or
    implausibly far away, use a rolling fallback horizon and recalculate next run.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    if fallback_hours is None:
        try:
            fallback_hours = float(os.getenv(
                "AFFILIO_DEFAULT_SCAN_HORIZON_HOURS",
                str(DEFAULT_SCAN_HORIZON_HOURS),
            ))
        except (TypeError, ValueError, OverflowError):
            fallback_hours = DEFAULT_SCAN_HORIZON_HOURS
    fallback_hours = max(3.0, min(float(MAX_SCAN_HORIZON_HOURS), float(fallback_hours)))
    fallback = current + timedelta(hours=fallback_hours)

    if not isinstance(status, dict):
        return fallback, "rolling_fallback"

    clean_start = parse_utc(status.get("last_clean_cycle_started_at"))
    clean_end = parse_utc(status.get("last_clean_cycle_completed_at"))
    active_start = parse_utc(
        status.get("current_cycle_started_at") or status.get("last_cycle_started_at")
    )
    if clean_start and clean_end and active_start:
        duration = clean_end - clean_start
        if timedelta(hours=1) <= duration <= timedelta(hours=MAX_SCAN_HORIZON_HOURS):
            projected = active_start + duration
            remaining = projected - current
            if timedelta(minutes=30) <= remaining <= timedelta(hours=MAX_SCAN_HORIZON_HOURS):
                return projected, "previous_clean_cycle_duration"
    return fallback, "rolling_fallback"


def available_slot_count(
    start_at: datetime,
    scan_deadline: datetime,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    safety_slots: int = 1,
) -> int:
    """Count 27-minute slots before the clean-scan deadline and safety reserve."""
    interval = timedelta(minutes=max(1, int(interval_minutes)))
    start = start_at if start_at.tzinfo else start_at.replace(tzinfo=timezone.utc)
    deadline = scan_deadline if scan_deadline.tzinfo else scan_deadline.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    deadline = deadline.astimezone(timezone.utc) - interval * max(0, int(safety_slots))
    if deadline < start:
        return 0
    return int((deadline - start).total_seconds() // interval.total_seconds()) + 1


def spread_product_slots(
    product_ids: list[str],
    *,
    start_at: datetime,
    scan_deadline: datetime,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    safety_slots: int = 1,
    max_items: int = DEFAULT_QUEUE_LIMIT,
) -> dict:
    """Spread ranked product IDs evenly through the usable slots.

    The first product occupies the next available publication slot. The final
    product is kept at least one full interval ahead of the estimated scan.
    When candidate volume exceeds capacity, only the ranked prefix is planned;
    the remainder stays in discovery and is not acknowledged by this function.
    """
    interval_minutes = max(1, int(interval_minutes))
    start = start_at if start_at.tzinfo else start_at.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    slot_count = available_slot_count(
        start,
        scan_deadline,
        interval_minutes=interval_minutes,
        safety_slots=safety_slots,
    )
    unique_ids = []
    seen = set()
    for raw in product_ids:
        product_id = str(raw or "").strip()
        if product_id and product_id not in seen:
            seen.add(product_id)
            unique_ids.append(product_id)

    planned_count = min(len(unique_ids), slot_count, max(0, int(max_items)))
    if planned_count <= 0:
        return {
            "items": [],
            "available_slots": slot_count,
            "candidate_count": len(unique_ids),
            "planned_count": 0,
            "deferred_ids": unique_ids,
            "product_spacing_minutes": None,
        }

    if planned_count == 1:
        slot_indexes = [0]
    else:
        last_index = slot_count - 1
        slot_indexes = [
            int(round(index * last_index / (planned_count - 1)))
            for index in range(planned_count)
        ]

    items = []
    for rank, (product_id, slot_index) in enumerate(
        zip(unique_ids[:planned_count], slot_indexes),
        start=1,
    ):
        scheduled = start + timedelta(minutes=interval_minutes * slot_index)
        items.append({
            "product_id": product_id,
            "rank": rank,
            "slot_index": slot_index,
            "scheduled_at": scheduled.isoformat(),
        })

    gaps = [
        slot_indexes[index + 1] - slot_indexes[index]
        for index in range(len(slot_indexes) - 1)
    ]
    spacing = round(sum(gaps) * interval_minutes / len(gaps), 1) if gaps else None
    return {
        "items": items,
        "available_slots": slot_count,
        "candidate_count": len(unique_ids),
        "planned_count": planned_count,
        "deferred_ids": unique_ids[planned_count:],
        "product_spacing_minutes": spacing,
    }


def _has_channel_success(entry: dict) -> bool:
    platforms = entry.get("platforms")
    if not isinstance(platforms, dict):
        return False
    return any(
        isinstance(platforms.get(name), dict)
        and str(platforms[name].get("status") or "").lower() == "sent"
        for name in ("telegram", "bale", "rubika", "eitaa")
    )


def apply_product_publication_schedule(
    state: dict,
    *,
    now: datetime,
    scan_deadline: datetime,
    cycle_id: str,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    safety_slots: int = 1,
    max_items: int = DEFAULT_QUEUE_LIMIT,
) -> dict:
    """Rebalance all not-yet-attempted product entries within the current scan window."""
    queue = state.setdefault("content_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["content_delivery_queue"] = queue

    active = []
    for product_id, entry in queue.items():
        if not isinstance(entry, dict) or entry.get("status") in {
            "published", "cancelled", "stale_selection"
        }:
            continue
        if _has_channel_success(entry):
            continue
        if int(entry.get("attempt_count") or 0) > 0:
            continue
        if entry.get("status") == "publishing":
            continue
        active.append((str(product_id), entry))

    last_channel = parse_utc(state.get("last_channel_published_at"))
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    start = max(current, last_channel + timedelta(minutes=interval_minutes)) if last_channel else current

    plan = spread_product_slots(
        [product_id for product_id, _entry in active],
        start_at=start,
        scan_deadline=scan_deadline,
        interval_minutes=interval_minutes,
        safety_slots=safety_slots,
        max_items=max_items,
    )
    by_id = {product_id: entry for product_id, entry in active}
    for item in plan["items"]:
        entry = by_id[item["product_id"]]
        entry["scheduled_at"] = item["scheduled_at"]
        entry["next_attempt_at"] = item["scheduled_at"]
        entry["publication_plan_cycle_id"] = str(cycle_id)
        entry["publication_plan_rank"] = item["rank"]
        entry["publication_plan_slot_index"] = item["slot_index"]
        entry["publication_plan_scan_deadline_at"] = scan_deadline.astimezone(timezone.utc).isoformat()

    summary = {
        "schema_version": 1,
        "cycle_id": str(cycle_id),
        "planned_at": current.isoformat(),
        "scan_deadline_at": scan_deadline.astimezone(timezone.utc).isoformat(),
        "interval_minutes": int(interval_minutes),
        "safety_slots": int(safety_slots),
        "available_slots": plan["available_slots"],
        "product_count": plan["planned_count"],
        "product_candidates_seen": plan["candidate_count"],
        "deferred_product_ids": plan["deferred_ids"],
        "product_spacing_minutes": plan["product_spacing_minutes"],
        "editorial_slots_available": max(0, plan["available_slots"] - plan["planned_count"]),
    }
    state["publication_mix_plan"] = summary
    return summary
