"""Durable hand-off contract between OfferChin content selection and platform delivery.

The selector writes a platform-neutral payload into state.json. The publisher reads
that queue later and updates per-platform delivery statuses. Platform adapters never
perform product discovery, and discovery never calls a platform publishing adapter.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from platform_registry import PLATFORM_NAMES
from product_quality import is_publishable_product_title


TERMINAL_QUEUE_STATUSES = {"published", "cancelled", "stale_selection"}
TERMINAL_PLATFORM_STATUSES = {"sent", "not_connected", "manual_review"}
PENDING_PLATFORM_STATUSES = {"pending", "failed", "retry"}

# The publisher heartbeat is separate from content timing. Product slots are adaptive.
# 27 minutes is a hard minimum; the catalog horizon and shared daily cap determine the actual gap.
PRODUCT_DEFAULT_SELECTION_INTERVAL_SECONDS = 27 * 60
PRODUCT_MIN_SELECTION_INTERVAL_SECONDS = 27 * 60  # Minimum product-to-product spacing
DEFAULT_CATALOG_CYCLE_SECONDS = 24 * 60 * 60
MIN_CATALOG_CYCLE_SECONDS = 60 * 60
MAX_CATALOG_CYCLE_SECONDS = 72 * 60 * 60
PRODUCT_ID_PATTERN = re.compile(r"^(?:dkp|snp)-\d{1,12}$", re.IGNORECASE)


def _configured_queue_limit(value: Any = None) -> int:
    """Return a defensive upper bound for live content hand-off/retry records."""
    raw = value if value is not None else os.getenv("AFFILIO_CONTENT_DELIVERY_QUEUE_LIMIT", "250")
    try:
        parsed = int(raw)
    except (TypeError, ValueError, OverflowError):
        parsed = 6
    return max(1, min(250, parsed))


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


def get_last_product_channel_published_at(state: dict) -> datetime | None:
    """Return the last confirmed product-channel send, excluding editorial posts.

    New state stores this clock explicitly. Older state is recovered from product
    receipts; only pre-editorial legacy state may fall back to the global channel clock.
    """
    if not isinstance(state, dict):
        return None

    stored = _utc(state.get("last_product_channel_published_at"))
    observed: list[datetime] = []

    published = state.get("published")
    if isinstance(published, dict):
        for product_key, record in published.items():
            if not PRODUCT_ID_PATTERN.fullmatch(str(product_key or "")) or not isinstance(record, dict):
                continue
            delivery = record.get("delivery_status") if isinstance(record.get("delivery_status"), dict) else {}
            has_channel_send = (
                any(delivery.get(name) == "sent" for name in ("telegram", "bale", "rubika", "eitaa"))
                or any(
                    str(record.get(f"{name}_message_id") or "").isdigit()
                    for name in ("telegram", "bale", "rubika", "eitaa")
                )
            )
            if not has_channel_send:
                continue
            try:
                timestamp = float(record.get("ts") or 0)
                if timestamp > 0:
                    observed.append(datetime.fromtimestamp(timestamp, timezone.utc))
            except (TypeError, ValueError, OverflowError, OSError):
                continue

    history = state.get("content_delivery_history")
    rows = history.values() if isinstance(history, dict) else (history if isinstance(history, list) else [])
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        content_id = str(entry.get("content_id") or entry.get("product_id") or "")
        if not PRODUCT_ID_PATTERN.fullmatch(content_id):
            continue
        platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
        for destination in ("telegram", "bale", "rubika", "eitaa"):
            target = platforms.get(destination)
            if isinstance(target, dict) and target.get("status") == "sent":
                sent_at = _utc(target.get("updated_at"))
                if sent_at is not None:
                    observed.append(sent_at)

    candidates = [value for value in (stored, max(observed) if observed else None) if value is not None]
    if candidates:
        anchor = max(candidates)
        if stored is None or anchor != stored:
            state["last_product_channel_published_at"] = anchor.isoformat()
        return anchor

    # Migration fallback is safe only before editorial history exists. Once it does,
    # last_channel_published_at may point to an editorial item, not a product.
    editorial_history = state.get("editorial_delivery_history")
    if not isinstance(editorial_history, list) or not editorial_history:
        return get_last_channel_published_at(state)
    return None


def calculate_product_publication_cadence(
    state: dict,
    catalog_status: dict,
    candidate_count: int,
    *,
    now: datetime | None = None,
    max_daily_posts: int = 72,
) -> dict:
    """Spread the pending product cohort evenly from its anchor to the next catalog scan.

    A product publication advances this clock. Editorial posts do not. If no product
    has yet been published in the current cycle, the first selected product may go now;
    otherwise the next product must respect the minimum product-to-product interval.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    status = catalog_status if isinstance(catalog_status, dict) else {}

    try:
        candidates = max(0, int(candidate_count))
    except (TypeError, ValueError, OverflowError):
        candidates = 0
    try:
        daily_limit = max(1, min(90, int(max_daily_posts)))
    except (TypeError, ValueError, OverflowError):
        daily_limit = 72

    clean_started = _utc(status.get("last_clean_cycle_started_at"))
    clean_completed = _utc(status.get("last_clean_cycle_completed_at"))
    cycle_seconds = DEFAULT_CATALOG_CYCLE_SECONDS
    if clean_started and clean_completed:
        observed_duration = int((clean_completed - clean_started).total_seconds())
        if MIN_CATALOG_CYCLE_SECONDS <= observed_duration <= MAX_CATALOG_CYCLE_SECONDS:
            cycle_seconds = observed_duration

    active_scan_started = _utc(
        status.get("current_cycle_started_at") or status.get("last_cycle_started_at")
    )
    if active_scan_started and (clean_completed is None or active_scan_started > clean_completed):
        scan_anchor = active_scan_started
    else:
        scan_anchor = clean_completed or current

    expected_next = scan_anchor + timedelta(seconds=cycle_seconds)
    if expected_next <= current:
        # An overdue or stalled scan must not freeze publication. Continue with a
        # rolling safety horizon and let a genuinely clean cycle replace this estimate.
        expected_next = current + timedelta(seconds=DEFAULT_CATALOG_CYCLE_SECONDS)

    cycle_id = clean_completed.isoformat() if clean_completed else (
        clean_started.isoformat() if clean_started else "initial-warmup"
    )
    previous_cycle_id = str(state.get("product_publication_plan_cycle_id") or "")
    last_product = get_last_product_channel_published_at(state)

    if previous_cycle_id != cycle_id:
        anchor = max(current, last_product) if last_product else current
        anchor_kind = "last_product" if last_product and last_product >= current else "cycle_start"
        state["product_publication_plan_cycle_id"] = cycle_id
        state["product_publication_plan_anchor_at"] = anchor.isoformat()
        state["product_publication_plan_anchor_kind"] = anchor_kind
    else:
        anchor = _utc(state.get("product_publication_plan_anchor_at")) or current
        anchor_kind = str(state.get("product_publication_plan_anchor_kind") or "cycle_start")
        if last_product and last_product > anchor:
            anchor = last_product
            anchor_kind = "last_product"
            state["product_publication_plan_anchor_at"] = anchor.isoformat()
            state["product_publication_plan_anchor_kind"] = anchor_kind

    horizon_seconds = max(0, int((expected_next - anchor).total_seconds()))
    minimum_gap = PRODUCT_MIN_SELECTION_INTERVAL_SECONDS
    has_prior_product_anchor = anchor_kind == "last_product"

    if candidates <= 0:
        planned_slots = 0
        interval_seconds = PRODUCT_DEFAULT_SELECTION_INTERVAL_SECONDS
    else:
        # Leave one minimum-gap buffer on both sides of a previously published product;
        # with no product yet, the first slot may be immediate and only inter-product gaps count.
        cadence_capacity = max(
            0,
            int(horizon_seconds // minimum_gap) - (1 if has_prior_product_anchor else 0),
        )
        daily_capacity = max(0, int(horizon_seconds * daily_limit // (24 * 60 * 60)))
        capacity = min(cadence_capacity, daily_capacity)
        planned_slots = min(candidates, capacity)
        if planned_slots <= 0:
            interval_seconds = PRODUCT_DEFAULT_SELECTION_INTERVAL_SECONDS
        else:
            divisor = planned_slots + 1 if has_prior_product_anchor else planned_slots
            interval_seconds = max(minimum_gap, int(math.ceil(horizon_seconds / max(1, divisor))))

    result = {
        "calculated_at": current.isoformat(),
        "catalog_cycle_id": cycle_id,
        "candidate_count": candidates,
        "last_clean_cycle_completed_at": clean_completed.isoformat() if clean_completed else "",
        "current_cycle_started_at": scan_anchor.isoformat(),
        "plan_anchor_at": anchor.isoformat(),
        "plan_anchor_kind": anchor_kind,
        "estimated_next_clean_scan_at": expected_next.isoformat(),
        "seconds_until_estimated_next_clean_scan": max(0, int((expected_next - current).total_seconds())),
        "seconds_from_plan_anchor_to_next_scan": horizon_seconds,
        "estimated_clean_cycle_seconds": cycle_seconds,
        "planned_product_slots": planned_slots,
        "daily_post_limit": daily_limit,
        "minimum_product_gap_seconds": minimum_gap,
        "interval_seconds": interval_seconds,
        "interval_minutes": round(interval_seconds / 60, 2),
        "policy": "equal_product_spacing_from_last_product_or_cycle_start_until_next_clean_scan",
    }
    state["product_publication_interval_seconds"] = interval_seconds
    state["product_publication_cadence"] = result
    return result


def reschedule_product_queue_evenly(
    state: dict,
    cadence: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Reflow every unsent product slot evenly without moving editorial timestamps."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return {"scheduled": 0, "deferred": 0}

    pending = []
    for product_id, entry in queue.items():
        if not isinstance(entry, dict) or entry.get("status") in TERMINAL_QUEUE_STATUSES:
            continue
        platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
        core_sent = any(
            isinstance(platforms.get(name), dict)
            and platforms[name].get("status") == "sent"
            for name in ("telegram", "bale", "rubika", "eitaa")
        )
        if core_sent:
            continue
        if str(entry.get("content_type") or "product") != "product":
            continue
        try:
            sequence = int(entry.get("sequence_number") or 0)
        except (TypeError, ValueError, OverflowError):
            sequence = 0
        pending.append((sequence, str(product_id), entry))
    pending.sort(key=lambda row: (row[0], row[1]))

    if not pending:
        plan = state.get("product_publication_plan")
        if isinstance(plan, dict):
            plan["pending_product_count"] = 0
            plan["scheduled_product_count"] = 0
            plan["updated_at"] = current.isoformat()
        return {"scheduled": 0, "deferred": 0}

    anchor = _utc(state.get("product_publication_plan_anchor_at")) or current
    anchor_kind = str(state.get("product_publication_plan_anchor_kind") or "cycle_start")
    last_product = get_last_product_channel_published_at(state)
    if last_product and last_product > anchor:
        anchor = last_product
        anchor_kind = "last_product"
        state["product_publication_plan_anchor_at"] = anchor.isoformat()
        state["product_publication_plan_anchor_kind"] = anchor_kind

    interval = max(
        PRODUCT_MIN_SELECTION_INTERVAL_SECONDS,
        int((cadence or {}).get("interval_seconds") or PRODUCT_DEFAULT_SELECTION_INTERVAL_SECONDS),
    )
    next_slot = (
        max(current, anchor + timedelta(seconds=interval))
        if anchor_kind == "last_product"
        else max(current, anchor)
    )
    for index, (_sequence, _product_id, entry) in enumerate(pending):
        scheduled = next_slot + timedelta(seconds=index * interval)
        entry["scheduled_at"] = scheduled.isoformat()
        retry_at = _utc(entry.get("next_attempt_at"))
        if entry.get("status") in {"failed", "retry", "partial"} and retry_at and retry_at > current:
            entry["next_attempt_at"] = max(scheduled, retry_at).isoformat()
        else:
            entry["next_attempt_at"] = scheduled.isoformat()
        entry["product_plan_cycle_id"] = str((cadence or {}).get("catalog_cycle_id") or "")

    plan = state.setdefault("product_publication_plan", {})
    if not isinstance(plan, dict):
        plan = {}
        state["product_publication_plan"] = plan
    plan.update({
        "catalog_cycle_id": str((cadence or {}).get("catalog_cycle_id") or ""),
        "anchor_at": anchor.isoformat(),
        "anchor_kind": anchor_kind,
        "next_clean_scan_at": str((cadence or {}).get("estimated_next_clean_scan_at") or ""),
        "pending_product_count": len(pending),
        "scheduled_product_count": len(pending),
        "interval_seconds": interval,
        "interval_minutes": round(interval / 60, 2),
        "product_ids": [product_id for _sequence, product_id, _entry in pending],
        "updated_at": current.isoformat(),
    })
    return {"scheduled": len(pending), "deferred": 0, "interval_seconds": interval}



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

    Discovery runs more often than the publication cadence. Future-scheduled items
    are retained as deliberate slots in the product plan; only an already-due failed
    selection is given a short delivery window before the next live scan replaces it.
    Items that reached even one platform are retained for independent destination retries.
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
        # A future slot is now an intentional part of the floating catalog-cycle plan.
        # Only retire an item after its scheduled time has arrived and its delivery
        # reservation has remained unresolved beyond the short recovery window.
        if scheduled is not None and scheduled > now:
            continue
        selected = _utc(entry.get("selected_at"), scheduled)
        stale_due = selected is not None and now - max(selected, scheduled or selected) >= stale_after
        if not stale_due:
            continue

        finish_queue_item(
            state,
            str(product_id),
            "stale_selection",
            now=now,
            detail="stale_due_unpublished_selection_replaced_by_live_scan",
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


def allocate_publication_sequence(state: dict) -> int:
    """Allocate one monotonically increasing sequence shared by product and editorial items."""
    if not isinstance(state, dict):
        raise TypeError("publication_state_must_be_a_dictionary")
    highest = 0
    try:
        highest = max(0, int(state.get("publication_sequence_counter") or 0))
    except (TypeError, ValueError, OverflowError):
        highest = 0
    for key in (
        "content_delivery_queue", "content_delivery_history",
        "editorial_delivery_queue", "editorial_delivery_history",
        "editorial_delivery_attempts",
    ):
        collection = state.get(key)
        rows = collection.values() if isinstance(collection, dict) else (
            collection if isinstance(collection, list) else []
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                highest = max(highest, int(row.get("sequence_number") or 0))
            except (TypeError, ValueError, OverflowError):
                continue
    published = state.get("published")
    if isinstance(published, dict):
        for row in published.values():
            if isinstance(row, dict):
                try:
                    highest = max(highest, int(row.get("sequence_number") or 0))
                except (TypeError, ValueError, OverflowError):
                    pass
    next_value = highest + 1
    state["publication_sequence_counter"] = next_value
    return next_value


def enqueue_selected_content(
    state: dict,
    items: list[dict],
    *,
    now: datetime | None = None,
    interval_seconds: int = 1380,
    max_items: int = 1,
    minimum_runway_minutes: int = 0,
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
    last_channel_published = get_last_product_channel_published_at(state)
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
        sequence_number = allocate_publication_sequence(state)
        payload["content_id"] = product_id
        payload["sequence_number"] = sequence_number
        queue[product_id] = {
            "content_id": product_id,
            "sequence_number": sequence_number,
            "content_type": "product",
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
        # Preserve queue/schedule order; demand or popularity telemetry must never
        # reorder items after the discount-first selector has already ranked them.
        due.append((
            1 if has_success else 0,
            scheduled,
            str(product_id),
            entry,
        ))
    # Python's stable sort retains queue insertion (selection) order on an exact schedule tie.
    due.sort(key=lambda row: (row[0], row[1]))
    return [
        (product_id, entry)
        for _partial, _scheduled, product_id, entry in due[:max(1, int(limit))]
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
        # A last-mile replacement inherits the failed slot's sequence when available;
        # it must not overtake or be overtaken by content selected after that slot.
        history = state.get("content_delivery_history")
        previous_sequence = None
        if isinstance(history, list) and history:
            previous = history[-1]
            if (
                isinstance(previous, dict)
                and previous.get("status") == "stale_selection"
                and str(previous.get("last_detail") or "") == str(reason or "")
            ):
                try:
                    previous_sequence = int(previous.get("sequence_number") or 0) or None
                except (TypeError, ValueError, OverflowError):
                    previous_sequence = None
        sequence_number = previous_sequence or allocate_publication_sequence(state)
        item["content_id"] = product_id
        item["content_type"] = "product"
        item["sequence_number"] = sequence_number
        queue[product_id] = {
            "content_id": product_id,
            "content_type": "product",
            "sequence_number": sequence_number,
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
