"""Durable hand-off contract between OfferChin content selection and platform delivery.

The selector writes a platform-neutral payload into state.json. The publisher reads
that queue later and updates per-platform delivery statuses. Platform adapters never
perform product discovery, and discovery never calls a platform publishing adapter.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from platform_registry import PLATFORM_NAMES, VIDEO_PLATFORMS


TERMINAL_QUEUE_STATUSES = {"published", "cancelled", "stale_selection", "superseded"}
TERMINAL_PLATFORM_STATUSES = {"sent", "not_connected", "manual_review", "superseded"}
PENDING_PLATFORM_STATUSES = {"pending", "failed", "retry"}

# Retain only a short hand-off window: failed destinations may retry briefly,
# but they must not accumulate an unbounded backlog that hides fresh selections.
MAX_ACTIVE_DELIVERY_ITEMS = 3


def _utc(value: Any, default: datetime | None = None) -> datetime | None:
    if value in (None, ""):
        return default
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return default


def _active_publication(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    terminal = {"deleted", "already_absent"}
    for id_field, status_field in (
        ("telegram_message_id", "expiry_status"),
        ("bale_message_id", "bale_expiry_status"),
    ):
        if str(record.get(id_field) or "").isdigit() and record.get(status_field) not in terminal:
            return True
    if record.get("youtube_video_id") and record.get("youtube_expiry_status") not in terminal:
        return True
    if record.get("aparat_video_hash") and record.get("aparat_expiry_status") not in terminal:
        return True
    return False



def _has_any_delivery_success(state: dict, product_id: str, entry: dict) -> bool:
    """Return whether any destination has already published this selected content."""
    platforms = entry.get("platforms")
    if isinstance(platforms, dict) and any(
        isinstance(target, dict) and target.get("status") == "sent"
        for target in platforms.values()
    ):
        return True
    published = state.get("published")
    record = published.get(product_id) if isinstance(published, dict) else None
    delivery = record.get("delivery_status") if isinstance(record, dict) else None
    return isinstance(delivery, dict) and any(status == "sent" for status in delivery.values())


def refresh_unpublished_selections(
    state: dict,
    *,
    now: datetime | None = None,
    stale_after_minutes: int = 8,
) -> int:
    """Discard future or stale selections that have not reached any destination.

    Discovery runs more often than the publication cadence. A future-scheduled item
    must not pin the next slot to an old product; an already-due failed selection is
    given a short delivery window before the next live scan replaces it. Items that
    reached even one platform are retained for independent destination retries.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    stale_after = timedelta(minutes=max(1, int(stale_after_minutes)))
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return 0

    replaced = 0
    pending = state.get("pending_queue")
    for product_id, entry in list(queue.items()):
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        if _has_any_delivery_success(state, str(product_id), entry):
            continue

        scheduled = _utc(entry.get("scheduled_at"))
        selected = _utc(entry.get("selected_at"), scheduled)
        future_scheduled = scheduled is not None and scheduled > now
        stale_due = selected is not None and now - selected >= stale_after
        if not future_scheduled and not stale_due:
            continue

        detail = "future_selection_replaced_by_live_scan" if future_scheduled else "stale_unpublished_selection_replaced_by_live_scan"
        finish_queue_item(
            state, str(product_id), "stale_selection", now=now, detail=detail
        )
        if isinstance(pending, dict):
            pending.pop(str(product_id), None)
        replaced += 1
    return replaced


def due_unpublished_selection(state: dict, *, now: datetime | None = None) -> str | None:
    """Find an already-due selection still awaiting its first successful destination."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return None
    for product_id, entry in queue.items():
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        if _has_any_delivery_success(state, str(product_id), entry):
            continue
        scheduled = _utc(entry.get("scheduled_at"))
        if scheduled is not None and scheduled <= now:
            return str(product_id)
    return None


def enqueue_selected_content(
    state: dict,
    items: list[dict],
    *,
    now: datetime | None = None,
    interval_seconds: int = 1200,
    max_items: int = 1,
    minimum_runway_minutes: int = 60,
) -> dict:
    """Persist ranked selections for a separate publisher; never publish from here."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    interval_seconds = max(60, int(interval_seconds))
    max_items = max(1, int(max_items))
    minimum_runway_minutes = max(0, int(minimum_runway_minutes))

    queue = state.setdefault("content_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["content_delivery_queue"] = queue
    history = state.setdefault("content_delivery_history", [])
    if not isinstance(history, list):
        history = []
        state["content_delivery_history"] = history
    published = state.get("published") if isinstance(state.get("published"), dict) else {}

    last_published = _utc(state.get("last_published_at"))
    next_slot = max(now, last_published + timedelta(seconds=interval_seconds)) if last_published else now
    # Do not push a fresh selection behind the scheduled time of an older,
    # partially delivered item. The current selection slot is authoritative.
    added = skipped = 0
    added_ids: list[str] = []
    for item in items:
        if added >= max_items:
            break
        if not isinstance(item, dict):
            skipped += 1
            continue
        product_id = str(item.get("product_id") or "").strip().lower()
        product_url = str(item.get("product_url") or "").strip()
        affiliate_url = str(item.get("affiliate_url") or "").strip()
        try:
            price = int(item.get("current_price") or 0)
        except (TypeError, ValueError, OverflowError):
            price = 0
        if not product_id or not product_url.startswith("https://") or not affiliate_url.startswith("https://") or price <= 0:
            skipped += 1
            continue

        existing = queue.get(product_id)
        if isinstance(existing, dict) and existing.get("status") not in TERMINAL_QUEUE_STATUSES:
            skipped += 1
            continue
        if _active_publication(published.get(product_id)):
            skipped += 1
            continue

        deadline = _utc(item.get("deal_expires_at"))
        scheduled = max(now, next_slot)
        if deadline and deadline <= scheduled + timedelta(minutes=minimum_runway_minutes):
            skipped += 1
            continue

        # Keep only JSON-compatible fields in the hand-off record. New platform
        # adapters can consume this contract without importing the discovery module.
        payload = json.loads(json.dumps(item, ensure_ascii=False, default=str))
        queue[product_id] = {
            "content_id": product_id,
            "product_id": product_id,
            "selected_at": now.isoformat(),
            "scheduled_at": scheduled.isoformat(),
            "next_attempt_at": scheduled.isoformat(),
            "status": "queued",
            "attempt_count": 0,
            "payload": payload,
            "platforms": {
                name: {"status": "pending", "attempts": 0}
                for name in PLATFORM_NAMES
            },
        }
        added += 1
        added_ids.append(product_id)
        next_slot = scheduled + timedelta(seconds=interval_seconds)

    # Bound existing backlog as well as every newly created selection. The newest
    # selection(s) are protected; retired entries remain in bounded history.
    trimmed = _trim_active_delivery_queue(
        state, protect_ids=set(added_ids), now=now
    )

    summary = {
        "added": added,
        "skipped": skipped,
        "trimmed": trimmed,
        "queue_size": sum(
            1 for entry in queue.values()
            if isinstance(entry, dict) and entry.get("status") not in TERMINAL_QUEUE_STATUSES
        ),
    }
    state["content_delivery_last_enqueue_summary"] = {
        **summary,
        "at": now.isoformat(),
    }
    return summary


def due_content(state: dict, *, now: datetime | None = None, limit: int = 1) -> list[tuple[str, dict]]:
    """Return scheduled items due for delivery in stable schedule/priority order."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return []
    due = []
    for product_id, entry in queue.items():
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        scheduled = _utc(entry.get("scheduled_at"))
        retry_at = _utc(entry.get("next_attempt_at"), scheduled)
        if scheduled is None or scheduled > now or (retry_at and retry_at > now):
            continue
        # New content with zero successful deliveries must outrank old partial items.
        # A slow/broken platform therefore cannot monopolize the publisher's single-item run.
        has_success = _has_any_delivery_success(state, str(product_id), entry)
        due.append((
            1 if has_success else 0,
            scheduled,
            -int((entry.get("payload") or {}).get("demand_score") or 0),
            str(product_id),
            entry,
        ))
    due.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return [
        (product_id, entry)
        for _partial, _scheduled, _score, product_id, entry in due[:max(1, int(limit))]
    ]


def finish_queue_item(state: dict, product_id: str, status: str, *, now: datetime | None = None, detail: str = "") -> None:
    """Move a terminal item to bounded history; preserve nonterminal partial deliveries."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return
    entry = queue.get(product_id)
    if not isinstance(entry, dict):
        return
    entry["status"] = status
    entry["updated_at"] = now.isoformat()
    if detail:
        entry["last_detail"] = str(detail)[:400]
    if status in TERMINAL_QUEUE_STATUSES:
        history = state.setdefault("content_delivery_history", [])
        if not isinstance(history, list):
            history = []
            state["content_delivery_history"] = history
        history.append(entry)
        state["content_delivery_history"] = history[-200:]
        queue.pop(product_id, None)



def _retire_queue_entry(
    state: dict,
    product_id: str,
    entry: dict,
    *,
    now: datetime,
    detail: str,
) -> bool:
    """Retire an old hand-off safely without risking duplicate sends in flight."""
    platforms = entry.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}
        entry["platforms"] = platforms

    # Never evict a destination while its external send may still be in flight.
    # If the result has been uncertain for 30+ minutes, preserve that uncertainty
    # as manual_review rather than retrying blindly.
    for target in platforms.values():
        if not isinstance(target, dict) or target.get("status") != "sending":
            continue
        started = _utc(target.get("attempt_started_at"))
        if started is None or now - started < timedelta(minutes=30):
            return False

    for name, target in platforms.items():
        if not isinstance(target, dict):
            continue
        status = str(target.get("status") or "pending")
        if status == "sending":
            target["status"] = "manual_review"
            target["last_error"] = "send_outcome_unknown_during_queue_eviction"
        elif status not in TERMINAL_PLATFORM_STATUSES:
            target["status"] = "superseded"
            target["last_error"] = detail[:300]
        else:
            continue
        target["updated_at"] = now.isoformat()
        target.pop("next_attempt_at", None)

        published = state.get("published")
        record = published.get(product_id) if isinstance(published, dict) else None
        if isinstance(record, dict):
            delivery_status = record.setdefault("delivery_status", {})
            if delivery_status.get(name) != "sent":
                delivery_status[name] = target["status"]

    if all(
        isinstance(target, dict)
        and str(target.get("status") or "pending") in TERMINAL_PLATFORM_STATUSES
        for target in platforms.values()
    ):
        finish_queue_item(state, product_id, "superseded", now=now, detail=detail)
        return True
    return False


def _trim_active_delivery_queue(
    state: dict,
    *,
    protect_ids: set[str] | None = None,
    now: datetime | None = None,
) -> int:
    """Keep at most three active selections, favouring the freshest hand-offs."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    protect_ids = set(protect_ids or ())
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return 0

    def selected_sort(item: tuple[str, dict]) -> tuple[datetime, str]:
        product_id, entry = item
        selected_at = _utc(entry.get("selected_at")) or _utc(entry.get("scheduled_at")) or now
        return selected_at, product_id

    active = [
        (str(product_id), entry)
        for product_id, entry in queue.items()
        if isinstance(entry, dict) and entry.get("status") not in TERMINAL_QUEUE_STATUSES
    ]
    active.sort(key=selected_sort)

    # If a caller passes an oversized batch, protect only its newest three items.
    if len(protect_ids) > MAX_ACTIVE_DELIVERY_ITEMS:
        protected_in_order = [pid for pid, _ in active if pid in protect_ids]
        protect_ids = set(protected_in_order[-MAX_ACTIVE_DELIVERY_ITEMS:])

    remaining = len(active)
    trimmed = 0
    for product_id, entry in active:
        if remaining <= MAX_ACTIVE_DELIVERY_ITEMS:
            break
        if product_id in protect_ids:
            continue
        if _retire_queue_entry(
            state,
            product_id,
            entry,
            now=now,
            detail="superseded_by_newer_live_selection_to_bound_delivery_queue",
        ):
            remaining -= 1
            trimmed += 1
    return trimmed
