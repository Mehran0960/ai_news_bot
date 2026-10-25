"""Durable hand-off contract between OfferChin content selection and platform delivery.

The selector writes a platform-neutral payload into state.json. The publisher reads
that queue later and updates per-platform delivery statuses. Platform adapters never
perform product discovery, and discovery never calls a platform publishing adapter.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


TERMINAL_QUEUE_STATUSES = {"published", "cancelled", "stale_selection"}
TERMINAL_PLATFORM_STATUSES = {"sent", "not_connected", "manual_review"}
PENDING_PLATFORM_STATUSES = {"pending", "failed", "retry"}


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
    for entry in queue.values():
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        existing_slot = _utc(entry.get("scheduled_at"))
        if existing_slot and existing_slot >= next_slot:
            next_slot = existing_slot + timedelta(seconds=interval_seconds)

    added = skipped = 0
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
                "telegram": {"status": "pending", "attempts": 0},
                "bale": {"status": "pending", "attempts": 0},
                "youtube": {"status": "pending", "attempts": 0},
                "aparat": {"status": "pending", "attempts": 0},
            },
        }
        added += 1
        next_slot = scheduled + timedelta(seconds=interval_seconds)

    summary = {
        "added": added,
        "skipped": skipped,
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
        due.append((scheduled, -int((entry.get("payload") or {}).get("demand_score") or 0), str(product_id), entry))
    due.sort(key=lambda row: (row[0], row[1], row[2]))
    return [(product_id, entry) for _scheduled, _score, product_id, entry in due[:max(1, int(limit))]]


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
