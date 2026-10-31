"""Durable hand-off contract between OfferChin content selection and platform delivery.

The selector writes a platform-neutral payload into state.json. The publisher reads
that queue later and updates per-platform delivery statuses. Platform adapters never
perform product discovery, and discovery never calls a platform publishing adapter.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from platform_registry import PLATFORM_NAMES
from product_quality import is_publishable_product_title


TERMINAL_QUEUE_STATUSES = {"published", "cancelled", "stale_selection"}
TERMINAL_PLATFORM_STATUSES = {"sent", "not_connected", "manual_review"}
PENDING_PLATFORM_STATUSES = {"pending", "failed", "retry"}


def _configured_queue_limit(value: Any = None) -> int:
    """Return a defensive upper bound for live content hand-off/retry records."""
    raw = value if value is not None else os.getenv("AFFILIO_CONTENT_DELIVERY_QUEUE_LIMIT", "6")
    try:
        parsed = int(raw)
    except (TypeError, ValueError, OverflowError):
        parsed = 6
    return max(1, min(20, parsed))


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


def has_fresh_unpublished_selection(
    state: dict,
    *,
    now: datetime,
    stale_after_minutes: int = 8,
) -> bool:
    """Whether an active selection with no Telegram/Bale success still reserves the slot."""
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return False
    current = _utc(now)
    if current is None:
        return False
    cutoff = current - timedelta(minutes=max(1, int(stale_after_minutes)))
    for entry in queue.values():
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        platforms = entry.get("platforms")
        if not isinstance(platforms, dict):
            return True
        if any(
            isinstance(platforms.get(name), dict)
            and platforms[name].get("status") == "sent"
            for name in ("telegram", "bale")
        ):
            continue
        selected = _utc(
            entry.get("selected_at")
            or entry.get("scheduled_at")
            or entry.get("created_at")
        )
        # Unknown timestamps are handled conservatively: do not enqueue another
        # selection until the existing hand-off is resolved.
        if selected is None or selected >= cutoff:
            return True
    return False


def selection_cadence_anchor(
    last_selected_at: Any,
    last_channel_published_at: Any,
    *,
    has_fresh_unpublished_selection: bool = False,
) -> datetime | None:
    """Only a fresh, active unpublished selection can reserve the selection cadence."""
    channel_post = _utc(last_channel_published_at)
    if not has_fresh_unpublished_selection:
        return channel_post
    selected = _utc(last_selected_at)
    anchors = [value for value in (selected, channel_post) if value is not None]
    return max(anchors) if anchors else None


def get_last_channel_published_at(state: dict) -> datetime | None:
    """Return the latest real Telegram/Bale send time and migrate old state safely.

    Older publisher versions could advance last_published_at on every partial retry,
    even when Telegram and Bale had already sent successfully. Per-destination
    updated_at values remain stable and provide a safe recovery source.
    """
    if not isinstance(state, dict):
        return None

    stored = _utc(state.get("last_channel_published_at"))
    observed: list[datetime] = []
    for collection in (
        state.get("content_delivery_queue"),
        state.get("content_delivery_history"),
    ):
        entries = collection.values() if isinstance(collection, dict) else (
            collection if isinstance(collection, list) else []
        )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            platforms = entry.get("platforms")
            if not isinstance(platforms, dict):
                continue
            for destination in ("telegram", "bale"):
                target = platforms.get(destination)
                if not isinstance(target, dict) or target.get("status") != "sent":
                    continue
                sent_at = _utc(target.get("updated_at"))
                if sent_at is not None:
                    observed.append(sent_at)

    observed_latest = max(observed) if observed else None
    legacy = _utc(state.get("last_published_at"))
    candidates = [value for value in (stored, observed_latest) if value is not None]
    anchor = max(candidates) if candidates else legacy
    if anchor is None:
        return None

    if stored is None or anchor != stored:
        state["last_channel_published_at"] = anchor.isoformat()

    # Keep the legacy field in sync too, so older/direct publishing paths do not
    # inherit a timestamp that was only advanced by a YouTube/Aparat retry.
    if legacy is None or abs((legacy - anchor).total_seconds()) > 90:
        state["last_published_at"] = anchor.isoformat()
        print(
            "CHANNEL_PUBLICATION_CLOCK_RECOVERED "
            f"previous={legacy.isoformat() if legacy else 'missing'} actual={anchor.isoformat()}"
        )
    return anchor


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


def _active_queue_entries(queue: Any) -> list[tuple[str, dict]]:
    if not isinstance(queue, dict):
        return []
    return [
        (str(product_id), entry)
        for product_id, entry in queue.items()
        if isinstance(entry, dict) and entry.get("status") not in TERMINAL_QUEUE_STATUSES
    ]


def _evict_oldest_active_queue_item(state: dict, now: datetime) -> bool:
    """Drop the oldest unresolved hand-off when the bounded queue needs a slot."""
    queue = state.get("content_delivery_queue")
    entries = _active_queue_entries(queue)
    if not entries:
        return False

    minimum_time = datetime.min.replace(tzinfo=timezone.utc)

    def selected_time(pair: tuple[str, dict]) -> datetime:
        entry = pair[1]
        return (
            _utc(entry.get("selected_at"))
            or _utc(entry.get("scheduled_at"))
            or minimum_time
        )

    product_id, _entry = min(entries, key=selected_time)
    finish_queue_item(
        state,
        product_id,
        "cancelled",
        now=now,
        detail="bounded_retry_queue_eviction: oldest unresolved selection dropped to protect fresh slots",
    )
    return True


def enforce_queue_limit(
    state: dict,
    *,
    now: datetime | None = None,
    max_active_items: int | None = None,
) -> int:
    """Keep the hand-off/retry queue bounded; never replay a long publication backlog."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    limit = _configured_queue_limit(max_active_items)
    evicted = 0
    while len(_active_queue_entries(state.get("content_delivery_queue"))) > limit:
        if not _evict_oldest_active_queue_item(state, current):
            break
        evicted += 1
    return evicted


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
    max_active_items: int | None = None,
) -> dict:
    """Persist ranked selections for a separate publisher; never publish from here."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    interval_seconds = max(60, int(interval_seconds))
    max_items = max(1, int(max_items))
    minimum_runway_minutes = max(0, int(minimum_runway_minutes))
    queue_limit = _configured_queue_limit(max_active_items)

    queue = state.setdefault("content_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["content_delivery_queue"] = queue
    history = state.setdefault("content_delivery_history", [])
    if not isinstance(history, list):
        history = []
        state["content_delivery_history"] = history
    published = state.get("published") if isinstance(state.get("published"), dict) else {}

    # Existing retry entries do not reserve future publication slots. A slow or
    # unavailable destination must never push fresh selections into a long queue.
    queue_evicted = enforce_queue_limit(state, now=now, max_active_items=queue_limit)
    last_channel_published = get_last_channel_published_at(state)
    next_slot = (
        max(now, last_channel_published + timedelta(seconds=interval_seconds))
        if last_channel_published else now
    )

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
        title = str(item.get("title") or "").strip()
        if not is_publishable_product_title(title):
            skipped += 1
            continue
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

        # Make room for the fresh selection rather than building a long retry backlog.
        # Partial deliveries remain retryable until evicted by this bound or rejected
        # by live price/stock/deadline validation in the publisher.
        while len(_active_queue_entries(queue)) >= queue_limit:
            if not _evict_oldest_active_queue_item(state, now):
                break
            queue_evicted += 1

        # Keep only JSON-compatible fields in the hand-off record. New platform
        # adapters can consume this contract without importing the discovery module.
        payload = json.loads(json.dumps(item, ensure_ascii=False, default=str))
        payload["title"] = title
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
        next_slot = scheduled + timedelta(seconds=interval_seconds)

    summary = {
        "added": added,
        "skipped": skipped,
        "queue_size": len(_active_queue_entries(queue)),
        "queue_evicted": queue_evicted,
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



def promote_fallback_selection(
    state: dict,
    candidates: list[dict],
    *,
    now: datetime | None = None,
    reason: str = "",
) -> str | None:
    """Promote the next ranked backup immediately after a hard-stale selection.

    Backups are stored with the selected queue item, not as separately scheduled
    posts. They are only promoted when live validation proves the primary stale,
    so a healthy primary still respects the normal publication cadence.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if not isinstance(state, dict) or not isinstance(candidates, list):
        return None

    queue = state.setdefault("content_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["content_delivery_queue"] = queue
    published = state.get("published") if isinstance(state.get("published"), dict) else {}

    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            continue
        item = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
        product_id = str(item.get("product_id") or "").strip().lower()
        product_url = str(item.get("product_url") or "").strip()
        affiliate_url = str(item.get("affiliate_url") or "").strip()
        title = str(item.get("title") or "").strip()
        try:
            price = int(item.get("current_price") or 0)
        except (TypeError, ValueError, OverflowError):
            price = 0
        if (
            not re.fullmatch(r"(?:dkp|snp)-\d{1,12}", product_id)
            or not product_url.startswith("https://")
            or not affiliate_url.startswith("https://")
            or not is_publishable_product_title(title)
            or price <= 0
        ):
            continue

        existing = queue.get(product_id)
        if isinstance(existing, dict) and existing.get("status") not in TERMINAL_QUEUE_STATUSES:
            continue
        if _active_publication(published.get(product_id)):
            continue

        remaining = [
            value for value in candidates[index + 1:]
            if isinstance(value, dict)
        ][:5]
        queue[product_id] = {
            "content_id": product_id,
            "product_id": product_id,
            "selected_at": current.isoformat(),
            "scheduled_at": current.isoformat(),
            "next_attempt_at": current.isoformat(),
            "status": "queued",
            "attempt_count": 0,
            "payload": item,
            "platforms": {
                name: {"status": "pending", "attempts": 0}
                for name in PLATFORM_NAMES
            },
            "fallback_candidates": remaining,
            "fallback_promoted_after": str(reason or "primary_selection_stale")[:120],
        }
        print(
            f"INLINE_FALLBACK_PROMOTED product_id={product_id} "
            f"remaining_backups={len(remaining)} reason={str(reason or 'stale')[:100]}"
        )
        return product_id
    return None
