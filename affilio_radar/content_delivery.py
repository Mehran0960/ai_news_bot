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
from publication_policy import MIN_CHANNEL_POST_INTERVAL_SECONDS


TERMINAL_QUEUE_STATUSES = {"published", "cancelled", "stale_selection"}
TERMINAL_PLATFORM_STATUSES = {"sent", "not_connected", "manual_review"}
PENDING_PLATFORM_STATUSES = {"pending", "failed", "retry"}

# Product slots still use the observed scan window, but every public channel post
# (product or editorial) must respect the shared 21-minute minimum spacing.
MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS = 57 * 60
PRODUCT_ID_PATTERN = re.compile(r"^(?:dkp|snp)-\d{1,12}$", re.IGNORECASE)


def editorial_dispatch_poll_seconds() -> int:
    """Configured scheduler polling horizon; defaults to the Cloudflare minute poll."""
    try:
        poll_seconds = int(os.getenv("OFFERCHIN_EDITORIAL_DISPATCH_POLL_SECONDS", "60"))
    except (TypeError, ValueError, OverflowError):
        poll_seconds = 60
    return max(15, min(180, poll_seconds))


def editorial_delivery_p90_seconds(state: dict | None = None) -> int:
    """Estimate a conservative editorial send duration from recent confirmed attempts."""
    try:
        default_delivery = int(os.getenv("OFFERCHIN_EDITORIAL_DEFAULT_DELIVERY_SECONDS", "30"))
    except (TypeError, ValueError, OverflowError):
        default_delivery = 30
    default_delivery = max(10, min(180, default_delivery))

    durations: list[float] = []
    if isinstance(state, dict):
        for key in ("editorial_delivery_history", "editorial_delivery_attempts"):
            rows = state.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows[-30:]:
                if not isinstance(row, dict):
                    continue
                try:
                    duration = float(row.get("delivery_duration_seconds") or 0)
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 < duration <= 900:
                    durations.append(duration)

    if not durations:
        return default_delivery
    durations.sort()
    index = max(0, min(len(durations) - 1, math.ceil(0.90 * len(durations)) - 1))
    return max(10, int(math.ceil(durations[index])))


def editorial_dispatch_runway_seconds(state: dict | None = None) -> int:
    """Combined scheduler-poll + delivery runway, not a fixed interval between posts."""
    return editorial_dispatch_poll_seconds() + editorial_delivery_p90_seconds(state)


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
    """Distribute selected products across the scan window with a 57-minute ceiling.

    Short windows remain evenly spaced. Long or sparse windows never schedule a
    product more than 57 minutes after the previous product when a slot is available.
    Editorial items are independent and fit into the gaps between product slots.
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
    observed_cycle_seconds = 0
    if clean_started and clean_completed:
        observed_cycle_seconds = int((clean_completed - clean_started).total_seconds())
        if observed_cycle_seconds <= 0:
            observed_cycle_seconds = 0

    active_scan_started = _utc(
        status.get("current_cycle_started_at") or status.get("last_cycle_started_at")
    )
    if active_scan_started and (clean_completed is None or active_scan_started > clean_completed):
        scan_anchor = active_scan_started
    else:
        scan_anchor = clean_completed or clean_started

    explicit_eta = _utc(
        status.get("estimated_next_clean_scan_at")
        or status.get("next_clean_scan_at")
    )
    if explicit_eta and explicit_eta > current:
        expected_next = explicit_eta
        eta_source = "catalog_status_estimate"
    elif scan_anchor and observed_cycle_seconds > 0:
        expected_next = scan_anchor + timedelta(seconds=observed_cycle_seconds)
        eta_source = "last_observed_full_cycle_duration"
    else:
        expected_next = current
        eta_source = "no_verified_scan_eta"

    # An expired or unavailable ETA must not strand the already selected queue.
    # Use a provisional max-interval window, without claiming it is a real scan ETA.
    provisional_window = expected_next <= current
    if provisional_window:
        eta_source = f"{eta_source}_provisional_max_interval"
        expected_next = current + timedelta(
            seconds=MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS * max(1, candidates)
        )
    horizon_seconds = max(0.0, (expected_next - current).total_seconds())
    cycle_id = clean_completed.isoformat() if clean_completed else (
        clean_started.isoformat() if clean_started else "initial-warmup"
    )
    previous_cycle_id = str(state.get("product_publication_plan_cycle_id") or "")
    last_channel = get_last_channel_published_at(state)

    if previous_cycle_id != cycle_id:
        last_product_in_cycle = bool(last_channel and scan_anchor and last_channel >= scan_anchor)
    else:
        last_product_in_cycle = bool(last_channel and scan_anchor and last_channel >= scan_anchor)

    last_channel_age_seconds = (
        max(0.0, (current - last_channel).total_seconds())
        if last_channel is not None else None
    )
    first_slot_due_now = bool(
        candidates > 0
        and (last_channel_age_seconds is None
             or last_channel_age_seconds >= MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS)
    )
    if first_slot_due_now:
        # Initial publication starts at the cycle anchor; overdue recovery follows a real product receipt.
        anchor = current
        anchor_kind = (
            "cycle_start" if last_channel is None
            else "cycle_start_after_max_gap"
        )
    elif last_channel is not None:
        # The maximum interval is global across catalog scan-cycle boundaries.
        anchor = last_channel
        anchor_kind = "last_channel_provisional" if provisional_window else "last_channel"
    else:
        anchor = current
        anchor_kind = "cycle_start"

    remaining_seconds = max(0.0, (expected_next - anchor).total_seconds())
    if candidates > 0 and remaining_seconds > 0:
        planned_slots = candidates
        interval_seconds = max(
            float(MIN_CHANNEL_POST_INTERVAL_SECONDS),
            min(
                remaining_seconds / candidates,
                float(MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS),
            ),
        )
    else:
        planned_slots = 0
        interval_seconds = 0.0
        first_slot_due_now = False

    state["product_publication_plan_cycle_id"] = cycle_id
    state["product_publication_plan_anchor_at"] = anchor.isoformat()
    state["product_publication_plan_anchor_kind"] = anchor_kind

    result = {
        "calculated_at": current.isoformat(),
        "catalog_cycle_id": cycle_id,
        "candidate_count": candidates,
        "last_clean_cycle_completed_at": clean_completed.isoformat() if clean_completed else "",
        "current_cycle_started_at": scan_anchor.isoformat() if scan_anchor else "",
        "plan_anchor_at": anchor.isoformat(),
        "plan_anchor_kind": anchor_kind,
        "estimated_next_clean_scan_at": "" if provisional_window else expected_next.isoformat(),
        "planned_window_end_at": expected_next.isoformat(),
        "scan_eta_is_provisional": provisional_window,
        "scan_eta_source": eta_source,
        "seconds_until_estimated_next_clean_scan": (
            0.0 if provisional_window else max(0.0, (expected_next - current).total_seconds())
        ),
        "seconds_from_plan_anchor_to_next_scan": remaining_seconds,
        "estimated_clean_cycle_seconds": observed_cycle_seconds,
        "planned_product_slots": planned_slots,
        "daily_post_limit": daily_limit,
        "interval_seconds": interval_seconds,
        "interval_minutes": round(interval_seconds / 60, 3),
        "maximum_product_interval_seconds": MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS,
        "first_slot_due_now": first_slot_due_now,
        "policy": "shared_21_minimum_channel_spacing_with_product_max_interval_57_minutes",
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
    """Reflow unsent products with an exact equal share capped at 57 minutes."""
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

    raw_interval = max(0.0, float((cadence or {}).get("interval_seconds") or 0.0))
    interval = (
        max(float(MIN_CHANNEL_POST_INTERVAL_SECONDS), min(raw_interval, float(MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS)))
        if raw_interval > 0 else 0.0
    )
    anchor = _utc(state.get("product_publication_plan_anchor_at")) or current
    anchor_kind = str(state.get("product_publication_plan_anchor_kind") or "cycle_start")
    last_channel = get_last_channel_published_at(state)
    if last_channel and last_channel > anchor:
        anchor = last_channel
        anchor_kind = "last_channel"
        state["product_publication_plan_anchor_at"] = anchor.isoformat()
        state["product_publication_plan_anchor_kind"] = anchor_kind

    # The 21-minute floor and 57-minute ceiling are enforced during every queue reflow.
    deferred = 0
    if interval <= 0:
        for _sequence, _product_id, entry in pending:
            entry["status"] = "queued"
            entry["last_detail"] = "waiting_for_next_clean_scan_eta"
            entry.pop("scheduled_at", None)
            entry.pop("next_attempt_at", None)
        deferred = len(pending)
    else:
        first_due_now = bool((cadence or {}).get("first_slot_due_now"))
        for index, (_sequence, _product_id, entry) in enumerate(pending):
            if first_due_now and index == 0:
                scheduled = current
            else:
                slot_index = index if first_due_now else index + 1
                scheduled = anchor + timedelta(seconds=interval * slot_index)
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
        "scheduled_product_count": len(pending) - deferred,
        "interval_seconds": interval,
        "interval_minutes": round(interval / 60, 3),
        "maximum_product_interval_seconds": MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS,
        "first_slot_due_now": bool((cadence or {}).get("first_slot_due_now")),
        "product_ids": [product_id for _sequence, product_id, _entry in pending],
        "updated_at": current.isoformat(),
    })
    return {"scheduled": len(pending) - deferred, "deferred": deferred, "interval_seconds": interval}


def reflow_product_queue_after_delivery(
    state: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Recalculate remaining product slots; use a provisional 57-minute clock if scan ETA expires."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    queue = state.get("content_delivery_queue")
    cadence = state.get("product_publication_cadence")
    if not isinstance(queue, dict) or not isinstance(cadence, dict):
        return {"scheduled": 0, "deferred": 0, "reason": "product_plan_unavailable"}

    pending_count = 0
    for entry in queue.values():
        if not isinstance(entry, dict) or entry.get("status") in {
            "published", "completed", "cancelled", "stale_selection", "rejected", "failed"
        }:
            continue
        if str(entry.get("content_type") or "product") != "product":
            continue
        platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
        core_statuses = [
            str((platforms.get(name) or {}).get("status") or "pending").strip().lower()
            for name in ("telegram", "bale")
        ]
        if all(status in {"sent", "not_connected", "manual_review", "skipped_limit"} for status in core_statuses):
            continue
        pending_count += 1

    if pending_count == 0:
        return {"scheduled": 0, "deferred": 0, "pending_products": 0}

    scan_eta = _utc(cadence.get("estimated_next_clean_scan_at"))
    last_channel = get_last_channel_published_at(state)
    if last_channel is None:
        return {
            "scheduled": 0,
            "deferred": pending_count,
            "pending_products": pending_count,
            "reason": "channel_receipt_unavailable",
        }

    last_channel_age_seconds = max(0.0, (current - last_channel).total_seconds())
    first_slot_due_now = last_channel_age_seconds >= MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS
    provisional_window = scan_eta is None or scan_eta <= current
    anchor = current if first_slot_due_now else last_channel
    if provisional_window:
        # Keep already selected products moving until a fresh, verified scan ETA arrives.
        # This is a provisional product window, not a fabricated scan ETA.
        remaining_seconds = MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS * pending_count
        next_clean_scan_value = ""
        eta_source = "provisional_max_interval_after_overdue_or_missing_scan_eta"
    else:
        remaining_seconds = max(0.0, (scan_eta - anchor).total_seconds())
        next_clean_scan_value = scan_eta.isoformat()
        eta_source = str(cadence.get("scan_eta_source") or "catalog_status_estimate")

    interval_seconds = max(
        float(MIN_CHANNEL_POST_INTERVAL_SECONDS),
        min(
            remaining_seconds / pending_count,
            float(MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS),
        ),
    )
    anchor_kind = (
        "cycle_start_after_max_gap" if first_slot_due_now
        else "last_channel_provisional" if provisional_window
        else "last_channel"
    )
    updated_cadence = dict(cadence)
    updated_cadence.update({
        "calculated_at": current.isoformat(),
        "candidate_count": pending_count,
        "planned_product_slots": pending_count,
        "plan_anchor_at": anchor.isoformat(),
        "plan_anchor_kind": anchor_kind,
        "estimated_next_clean_scan_at": next_clean_scan_value,
        "planned_window_end_at": (anchor + timedelta(seconds=remaining_seconds)).isoformat(),
        "scan_eta_is_provisional": provisional_window,
        "scan_eta_source": eta_source,
        "first_slot_due_now": first_slot_due_now,
        "seconds_until_estimated_next_clean_scan": (
            0.0 if provisional_window else max(0.0, (scan_eta - current).total_seconds())
        ),
        "seconds_from_plan_anchor_to_next_scan": remaining_seconds,
        "interval_seconds": interval_seconds,
        "interval_minutes": round(interval_seconds / 60, 3),
        "maximum_product_interval_seconds": MAX_PRODUCT_PUBLICATION_INTERVAL_SECONDS,
        "policy": "shared_21_minimum_channel_spacing_with_product_max_interval_57_minutes_and_provisional_fallback",
    })
    state["product_publication_cadence"] = updated_cadence
    state["product_publication_interval_seconds"] = interval_seconds
    state["product_publication_plan_anchor_at"] = anchor.isoformat()
    state["product_publication_plan_anchor_kind"] = anchor_kind

    result = reschedule_product_queue_evenly(state, updated_cadence, now=current)
    return {
        **result,
        "pending_products": pending_count,
        "next_clean_scan_at": next_clean_scan_value,
        "interval_seconds": interval_seconds,
    }


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
            for destination in ("telegram", "bale", "rubika", "eitaa"):
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


def next_channel_publication_at(state: dict) -> datetime | None:
    """Return the earliest safe next slot after any confirmed channel content."""
    last_channel = get_last_channel_published_at(state)
    if last_channel is None:
        return None
    return last_channel + timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS)


def channel_publication_wait_seconds(
    state: dict, *, now: datetime | None = None
) -> int:
    """Return remaining shared spacing time for product and editorial channel posts."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    next_slot = next_channel_publication_at(state)
    if next_slot is None:
        return 0
    return max(0, int(math.ceil((next_slot - current).total_seconds())))


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
    interval_seconds: float = 0.0,
    max_items: int = 1,
    minimum_runway_minutes: int = 0,
    max_active_items: int | None = None,
) -> dict:
    """Persist ranked selections for a separate publisher; never publish from here."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    interval_seconds = max(0.0, float(interval_seconds))
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
    # This is only an initial hand-off estimate. The catalog-aware planner
    # subsequently reflows every unsent selection across the full scan window.
    effective_interval_seconds = max(
        float(MIN_CHANNEL_POST_INTERVAL_SECONDS), interval_seconds
    )
    next_slot = max(
        now,
        last_channel_published + timedelta(seconds=effective_interval_seconds)
        if last_channel_published else now,
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
        next_slot = scheduled + timedelta(seconds=effective_interval_seconds)

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
