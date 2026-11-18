"""Event-driven editorial fallback publisher.

Editorial content uses the shared publication sequence but never enters the SKU/price
product pipeline. Live network actions require the explicit --publish flag.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests

import affilio_radar as radar
from merge_state_conflicts import three_way_merge
from content_delivery import (
    allocate_publication_sequence,
    channel_publication_wait_seconds,
    editorial_delivery_p90_seconds,
    editorial_dispatch_poll_seconds,
    editorial_dispatch_runway_seconds,
    get_last_channel_published_at,
    next_channel_publication_at,
    refresh_unpublished_selections,
    reflow_product_queue_after_delivery,
)
from publication_policy import (
    MAX_CHANNEL_POST_INTERVAL_SECONDS,
    MIN_CHANNEL_POST_INTERVAL_SECONDS,
    PRODUCTS_PER_EDITORIAL_POST,
    channel_post_interval_seconds,
    editorial_frequency_allowed,
    products_published_since_last_editorial,
)
from editorial_content import (
    editorial_content_fingerprint,
    editorial_topics_for_product,
    record_editorial_delivery,
    select_editorial_fallback,
    validate_editorial_item,
)
from platform_registry import PLATFORM_NAMES

ROOT = Path(__file__).resolve().parent
EDITORIAL_BANK = ROOT / "editorial_bank.json"
EDITORIAL_APPROVED_ITEMS = ROOT / "editorial_approved_items.json"
CHANNEL_DESTINATIONS = ("telegram", "bale", "rubika", "eitaa")
VIDEO_DESTINATIONS = ("youtube", "aparat", "filo")
TERMINAL = {"sent", "not_connected", "manual_review", "skipped_limit"}
RETRYABLE = {"pending", "failed", "retry"}
# Editorial is only placed inside an actual product-to-product window.
# It never creates a standalone publication slot or delays a product.
RETRY_BASE_SECONDS = max(60, min(1800, int(os.getenv("OFFERCHIN_EDITORIAL_RETRY_SECONDS", "300"))))
MAX_ATTEMPTS = max(1, min(5, int(os.getenv("OFFERCHIN_EDITORIAL_MAX_ATTEMPTS", "3"))))
EDITORIAL_ORPHAN_RECOVERY_MAX_AGE_HOURS = 24
EDITORIAL_ORPHAN_RECOVERY_LIMIT = 20


def _utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save(state: dict) -> None:
    radar.save_json(radar.STATE, state)


def _refresh_dispatch_projection(state: dict) -> None:
    """Persist the current editorial/product due times for the minute dispatcher."""
    try:
        projection = radar.build_video_upload_dispatch_state(state, now=_now())
        radar.save_json(ROOT / "video_upload_dispatch_state.json", projection)
    except Exception as exc:
        print(f"EDITORIAL_DISPATCH_PROJECTION_REFRESH_FAILED error={type(exc).__name__}")


def _load_bank() -> list[dict]:
    try:
        value = json.loads(EDITORIAL_BANK.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"editorial_bank_unavailable:{type(exc).__name__}") from exc
    if not isinstance(value, list):
        raise RuntimeError("editorial_bank_must_be_a_list")

    # Newly reviewed Persian summaries from the editorial-source pipeline can be
    # appended here without editing the evergreen bank. Raw RSS metadata is never
    # accepted as a publishable item because validate_editorial_item requires claims,
    # source provenance, review timestamps and an original Persian body.
    dynamic = []
    if EDITORIAL_APPROVED_ITEMS.is_file():
        try:
            loaded = json.loads(EDITORIAL_APPROVED_ITEMS.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                raise RuntimeError("editorial_approved_items_must_be_a_list")
            dynamic = loaded
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError(f"editorial_approved_items_unavailable:{type(exc).__name__}") from exc

    by_id = {}
    for item in value + dynamic:
        if not isinstance(item, dict):
            continue
        editorial_id = str(item.get("editorial_id") or "").strip()
        if editorial_id:
            by_id[editorial_id] = item
    return list(by_id.values())


def _active_editorial_entries(state: dict) -> list[dict]:
    queue = state.get("editorial_delivery_queue")
    if not isinstance(queue, dict):
        return []
    rows = [
        row for row in queue.values()
        if isinstance(row, dict) and row.get("status") not in {"completed", "cancelled", "failed"}
    ]
    return sorted(rows, key=lambda row: int(row.get("sequence_number") or 0))


def _editorial_photo_delivery_started(entry: dict) -> bool:
    """Whether this event has already had a photo-channel attempt or confirmed receipt."""
    if not isinstance(entry, dict):
        return False
    if entry.get("photo_slot_attempted_at"):
        return True
    platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
    for destination in CHANNEL_DESTINATIONS:
        target = platforms.get(destination)
        if not isinstance(target, dict):
            continue
        status = str(target.get("status") or "").strip().lower()
        if status in {"sent", "manual_review"}:
            return True
        try:
            attempts = int(target.get("attempts") or 0)
        except (TypeError, ValueError, OverflowError):
            attempts = 0
        if attempts > 0 or target.get("attempt_started_at"):
            return True
    return False


def _has_pending_editorial_destinations(entry: dict) -> bool:
    """Whether this editorial still has a destination that can usefully be resumed."""
    platforms = entry.get("platforms") if isinstance(entry, dict) and isinstance(entry.get("platforms"), dict) else {}
    retryable = RETRYABLE | {"pending_credentials", "sending"}
    for destination, target in platforms.items():
        if not isinstance(target, dict):
            continue
        status = str(target.get("status") or "").strip().lower()
        if status in retryable:
            return True
        if destination == "youtube" and status == "skipped_limit":
            return True
    return False


def _channel_spacing_guard_applies(state: dict) -> bool:
    """Apply global channel spacing only before reserving a new editorial event.

    A previously reserved event must be allowed to finish on each independent
    destination even when another destination has already advanced the channel clock.
    """
    return not bool(_active_editorial_entries(state))


def _selected_channel_destinations() -> tuple[str, ...]:
    """Select one photo channel for isolated repair workers; default to all channels."""
    selected = str(os.getenv("OFFERCHIN_EDITORIAL_CHANNEL_DESTINATION") or "").strip().lower()
    if not selected:
        return CHANNEL_DESTINATIONS
    if selected not in CHANNEL_DESTINATIONS:
        raise ValueError("unsupported_editorial_channel_destination")
    return (selected,)


def _selected_video_destinations() -> tuple[str, ...]:
    """Select one video destination for isolated workers; default to all for legacy runs."""
    selected = str(os.getenv("OFFERCHIN_EDITORIAL_VIDEO_DESTINATION") or "").strip().lower()
    if not selected:
        return VIDEO_DESTINATIONS
    if selected not in VIDEO_DESTINATIONS:
        raise ValueError("unsupported_editorial_video_destination")
    return (selected,)


def _pending_product_video_exists(
    state: dict, destinations: set[str] | None = None
) -> bool:
    published = state.get("published")
    if not isinstance(published, dict):
        return False
    checker = getattr(radar, "_has_pending_video_destination", None)
    if not callable(checker):
        return False
    return any(
        checker(row, destinations)
        for row in published.values() if isinstance(row, dict)
    )


def _hydrate_confirmed_editorial_receipts(state: dict, entry: dict) -> int:
    """Restore known receipts from history before attempting an ambiguous queue snapshot."""
    history = state.get("editorial_delivery_history")
    if not isinstance(history, list):
        return 0
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    editorial_id = str(payload.get("editorial_id") or "").strip()
    fingerprint = editorial_content_fingerprint(payload)
    matches = []
    for row in history:
        if not isinstance(row, dict):
            continue
        same_id = editorial_id and str(row.get("editorial_id") or "").strip() == editorial_id
        same_fingerprint = fingerprint and str(row.get("content_fingerprint") or "").strip() == fingerprint
        if same_id or same_fingerprint:
            matches.append(row)
    restored = 0
    platforms = entry.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        entry["platforms"] = platforms
    for row in reversed(matches):
        receipts = row.get("destinations") if isinstance(row.get("destinations"), dict) else {}
        for destination, receipt in receipts.items():
            if destination not in (*CHANNEL_DESTINATIONS, *VIDEO_DESTINATIONS) or not isinstance(receipt, dict):
                continue
            receipt_status = str(receipt.get("status") or "").strip().lower()
            if receipt_status not in {"sent", "manual_review"}:
                continue
            target = platforms.setdefault(destination, {})
            if not isinstance(target, dict):
                target = {}
                platforms[destination] = target
            current_status = str(target.get("status") or "").strip().lower()
            if current_status in {"sent", "manual_review"}:
                continue
            target.update(receipt)
            target["restored_from_delivery_history"] = True
            restored += 1
    if restored:
        print(
            f"EDITORIAL_RECEIPTS_RESTORED content_id={entry.get('content_id')} "
            f"destinations={restored} source=confirmed_history"
        )
    return restored


def _rehydrate_orphaned_editorial_entries(
    state: dict,
    bank: list[dict],
    *,
    now: datetime | None = None,
) -> int:
    """Recover recent history events whose active queue entry was lost by a concurrent state write.

    Only events with a confirmed public photo receipt and at least one unfinished video
    destination are eligible. Sent/manual-review receipts are copied as-is, so recovery
    can never replay a channel post that already succeeded. The 24-hour age limit avoids
    reviving stale editorial assets or expired product context.
    """
    if not isinstance(state, dict):
        return 0
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    queue = state.get("editorial_delivery_queue")
    if not isinstance(queue, dict):
        queue = {}
        state["editorial_delivery_queue"] = queue
    history = state.get("editorial_delivery_history")
    if not isinstance(history, list):
        return 0
    attempts = state.get("editorial_delivery_attempts")
    attempts = attempts if isinstance(attempts, list) else []
    terminal_attempts = {
        (str(row.get("content_id") or ""), str(row.get("sequence_number") or ""))
        for row in attempts
        if isinstance(row, dict)
        and str(row.get("status") or "").lower() in {"completed", "failed", "cancelled"}
    }
    bank_by_id = {
        str(item.get("editorial_id") or "").strip(): item
        for item in bank if isinstance(item, dict) and str(item.get("editorial_id") or "").strip()
    }
    recovered = 0
    for row in reversed(history):
        if recovered >= EDITORIAL_ORPHAN_RECOVERY_LIMIT:
            break
        if not isinstance(row, dict):
            continue
        content_id = str(row.get("content_id") or "").strip()
        editorial_id = str(row.get("editorial_id") or "").strip()
        try:
            sequence = int(row.get("sequence_number") or 0)
        except (TypeError, ValueError, OverflowError):
            sequence = 0
        if not content_id or not editorial_id or sequence <= 0:
            continue
        if content_id in queue:
            continue
        if (content_id, str(sequence)) in terminal_attempts:
            continue
        published_at = _utc(row.get("published_at"))
        if published_at is None:
            continue
        age = current - published_at
        if age < timedelta(0) or age > timedelta(hours=EDITORIAL_ORPHAN_RECOVERY_MAX_AGE_HOURS):
            continue
        receipts = row.get("destinations") if isinstance(row.get("destinations"), dict) else {}
        if not any(
            isinstance(receipts.get(name), dict)
            and str(receipts[name].get("status") or "").strip().lower() == "sent"
            for name in CHANNEL_DESTINATIONS
        ):
            continue
        pending_videos = {
            name: receipts.get(name)
            for name in VIDEO_DESTINATIONS
            if isinstance(receipts.get(name), dict)
            and (
                str(receipts[name].get("status") or "").strip().lower()
                in {"pending", "pending_credentials", "failed", "retry", "sending"}
                or (
                    name == "youtube"
                    and str(receipts[name].get("status") or "").strip().lower() == "skipped_limit"
                )
            )
        }
        if not pending_videos:
            continue
        item = bank_by_id.get(editorial_id)
        valid, reason = validate_editorial_item(item, now=current) if item else (
            False, "editorial_id_not_in_current_reviewed_bank"
        )
        if not valid:
            print(
                "EDITORIAL_ORPHAN_RECOVERY_SKIPPED "
                f"content_id={content_id} reason={reason}"
            )
            continue
        fingerprint = str(row.get("content_fingerprint") or "").strip()
        if fingerprint and fingerprint != editorial_content_fingerprint(item):
            print(f"EDITORIAL_ORPHAN_RECOVERY_SKIPPED content_id={content_id} reason=fingerprint_mismatch")
            continue
        payload = dict(item)
        payload.update({
            "content_id": content_id,
            "sequence_number": sequence,
            "related_product_id": str(row.get("related_product_id") or "").strip(),
        })
        platforms = {}
        for destination in (*CHANNEL_DESTINATIONS, *VIDEO_DESTINATIONS):
            receipt = receipts.get(destination)
            if isinstance(receipt, dict):
                platforms[destination] = dict(receipt)
            else:
                platforms[destination] = {
                    "status": "not_connected",
                    "attempts": 0,
                    "last_error": "destination_receipt_missing_in_history",
                }
        entry = {
            "content_id": content_id,
            "content_type": "editorial",
            "sequence_number": sequence,
            "selected_at": published_at.isoformat(),
            "scheduled_at": current.isoformat(),
            "next_attempt_at": current.isoformat(),
            "window_closes_at": None,
            "photo_slot_attempted_at": published_at.isoformat(),
            "delivery_started_at": published_at.isoformat(),
            "status": "partial",
            "attempt_count": 0,
            "payload": payload,
            "related_product_id": payload["related_product_id"],
            "platforms": platforms,
            "recovered_from_delivery_history_at": current.isoformat(),
            "recovery_reason": "recent_orphaned_editorial_with_pending_video",
        }
        queue[content_id] = entry
        recovered += 1
        print(
            "EDITORIAL_ORPHAN_RECOVERED "
            f"content_id={content_id} sequence={sequence} "
            f"pending_videos={','.join(sorted(pending_videos))}"
        )
    return recovered


def _recent_attempt_anchor(state: dict) -> datetime | None:
    candidates = [
        get_last_channel_published_at(state),
        _utc(state.get("last_editorial_confirmed_at")),
        _utc(state.get("last_editorial_attempt_at")),
    ]
    history = state.get("editorial_delivery_history")
    if isinstance(history, list):
        candidates.extend(
            _utc(row.get("published_at"))
            for row in history if isinstance(row, dict)
        )
    valid = [value for value in candidates if value is not None]
    return max(valid) if valid else None


def _product_has_core_channel_success(entry: dict) -> bool:
    platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
    return any(
        isinstance(platforms.get(name), dict)
        and platforms[name].get("status") == "sent"
        for name in ("telegram", "bale", "rubika", "eitaa")
    )


def _next_product_slot(state: dict, now: datetime) -> tuple[str, dict, datetime] | None:
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return None
    due_products = []
    future_products = []
    for product_id, entry in queue.items():
        if not isinstance(entry, dict) or entry.get("status") in {"published", "cancelled", "stale_selection"}:
            continue
        if str(entry.get("content_type") or "product") != "product":
            continue
        if _product_has_core_channel_success(entry):
            continue
        scheduled = _utc(entry.get("scheduled_at"))
        if scheduled is None:
            continue
        row = (str(product_id), entry, scheduled)
        if scheduled <= now:
            due_products.append(row)
        else:
            future_products.append(row)
    if due_products:
        # A due product always takes precedence; editorial must never preempt it.
        return min(due_products, key=lambda row: row[2])
    return min(future_products, key=lambda row: row[2]) if future_products else None


def queue_editorial_if_due(
    state: dict,
    bank: list[dict],
    *,
    now: datetime | None = None,
) -> dict | None:
    """Reserve one reviewed editorial inside the shared channel sequence after six products.

    Editorial never publishes on its own or creates a standalone product slot. It is
    scheduled only against a selected next product, and a reserved product bridge is
    released when the editorial is cancelled or receives no public channel receipt.
    """
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    active = _active_editorial_entries(state)
    product_queue = state.get("content_delivery_queue")
    active_products = product_queue if isinstance(product_queue, dict) else {}
    if active:
        valid_active = []
        delivery_runway = max(
            timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS),
            timedelta(seconds=editorial_delivery_p90_seconds(state)),
        )
        current_bank = {
            str(row.get("editorial_id") or "").strip(): row
            for row in bank if isinstance(row, dict) and str(row.get("editorial_id") or "").strip()
        }
        for queued_editorial in active:
            related_id = str(queued_editorial.get("related_product_id") or "").strip()
            product_entry = active_products.get(related_id) if related_id else None
            queued_payload = (
                queued_editorial.get("payload")
                if isinstance(queued_editorial.get("payload"), dict) else {}
            )
            editorial_id = str(queued_payload.get("editorial_id") or "").strip()
            reviewed_item = current_bank.get(editorial_id)
            valid_item, invalid_reason = (
                validate_editorial_item(reviewed_item, now=current)
                if reviewed_item else (False, "editorial_id_not_in_current_reviewed_bank")
            )
            payload_fields = ("title", "body", "topic", "sources", "claims", "reviewed_at", "review_due_at")
            payload_matches_reviewed = bool(reviewed_item) and all(
                queued_payload.get(field) == reviewed_item.get(field)
                for field in payload_fields
            )
            if (
                valid_item
                and payload_matches_reviewed
                and _editorial_photo_delivery_started(queued_editorial)
                and _has_pending_editorial_destinations(queued_editorial)
            ):
                # The photo slot has already been consumed. Resume only destinations
                # still pending; do not cancel because the linked product slot passed.
                valid_active.append(queued_editorial)
                continue
            product_payload = (
                product_entry.get("payload")
                if isinstance(product_entry, dict) and isinstance(product_entry.get("payload"), dict)
                else {}
            )
            topic_is_relevant = (
                str(queued_payload.get("topic") or "").strip().lower()
                in editorial_topics_for_product(product_payload)
            )
            stale_reason = ""
            if not valid_item:
                stale_reason = invalid_reason
            elif not payload_matches_reviewed:
                stale_reason = "queued_payload_differs_from_current_reviewed_bank"
            elif not isinstance(product_entry, dict):
                stale_reason = "related_product_slot_missing"
            elif not topic_is_relevant:
                stale_reason = "queued_topic_not_relevant_to_related_product"
            if stale_reason:
                queued_editorial["status"] = "cancelled"
                _release_failed_editorial_product_reservation(state, queued_editorial)
                queued_editorial["last_detail"] = f"stale_or_irrelevant_editorial:{stale_reason}"
                editorial_queue = state.get("editorial_delivery_queue")
                if isinstance(editorial_queue, dict):
                    editorial_queue.pop(str(queued_editorial.get("content_id") or ""), None)
                print(
                    "EDITORIAL_STALE_QUEUE_CANCELLED "
                    f"content_id={queued_editorial.get('content_id')} reason={stale_reason}"
                )
                continue
            product_slot_at = _utc(product_entry.get("scheduled_at"))
            product_slot_is_due = product_slot_at is not None and product_slot_at <= current
            dispatch_window_closed = (
                product_slot_at is not None
                and product_slot_at - current < delivery_runway
            )
            if (
                isinstance(product_entry, dict)
                and product_slot_at is not None
                and product_entry.get("status") not in {"published", "cancelled", "stale_selection"}
                and not _product_has_core_channel_success(product_entry)
                and not product_slot_is_due
                and not dispatch_window_closed
            ):
                # Once awake, the publisher may send until the safe bridge window closes;
                # its reserved next-product slot is part of the shared 31–47 minute cadence.
                queued_editorial["window_closes_at"] = (
                    product_slot_at
                    - delivery_runway
                ).isoformat()
                valid_active.append(queued_editorial)
                continue
            queued_editorial["status"] = "cancelled"
            _release_failed_editorial_product_reservation(state, queued_editorial)
            if product_slot_is_due:
                queued_editorial["last_detail"] = "editorial_midpoint_passed_related_product_due"
            elif dispatch_window_closed:
                queued_editorial["last_detail"] = "editorial_dispatch_window_closed_before_product"
            else:
                queued_editorial["last_detail"] = "editorial_requires_an_active_related_product_slot"
            editorial_queue = state.get("editorial_delivery_queue")
            if isinstance(editorial_queue, dict):
                editorial_queue.pop(str(queued_editorial.get("content_id") or ""), None)
        if valid_active:
            return valid_active[0]

    if not editorial_frequency_allowed(state):
        products_since = products_published_since_last_editorial(state)
        print(
            "EDITORIAL_FREQUENCY_GUARD "
            f"products_since_last_editorial={products_since} "
            f"required_products={PRODUCTS_PER_EDITORIAL_POST}"
        )
        return None

    refresh_unpublished_selections(state, now=current, stale_after_minutes=8)
    next_product = _next_product_slot(state, current)
    if not next_product:
        print("EDITORIAL_WAIT_FOR_PRODUCT_SLOT reason=no_selected_product_in_queue")
        return None

    related_product_id, product_entry, product_at = next_product
    if product_at <= current:
        print("EDITORIAL_WAIT_FOR_PRODUCT_SLOT reason=product_slot_due")
        return None

    related_product = (
        product_entry.get("payload")
        if isinstance(product_entry.get("payload"), dict) else {}
    )
    history = state.get("editorial_delivery_history")
    history = history if isinstance(history, list) else []
    already_linked = any(
        str(row.get("related_product_id") or "") == related_product_id
        for row in history if isinstance(row, dict)
    )
    active_queue = state.get("editorial_delivery_queue")
    if isinstance(active_queue, dict):
        already_linked = already_linked or any(
            isinstance(row, dict)
            and str(row.get("related_product_id") or "") == related_product_id
            and row.get("status") not in {"completed", "cancelled", "failed"}
            for row in active_queue.values()
        )
    if already_linked:
        return None

    if radar.daily_channel_posts_count(state, current) >= radar.MAX_DAILY_CHANNEL_POSTS:
        print(
            "EDITORIAL_FALLBACK_DAILY_CAP_REACHED "
            f"limit={radar.MAX_DAILY_CHANNEL_POSTS}"
        )
        return None

    item = select_editorial_fallback(
        bank, state, now=current, related_product=related_product
    )
    if not item:
        state["last_editorial_empty_bank_check_at"] = current.isoformat()
        print("EDITORIAL_FALLBACK_EMPTY reason=no_valid_reviewed_item_or_bank_cycle")
        return None

    anchor = get_last_channel_published_at(state) or current
    dispatch_runway_seconds = editorial_dispatch_runway_seconds(state)
    delivery_runway_seconds = editorial_delivery_p90_seconds(state)
    # Editorial is an explicit slot in the one shared channel sequence. Reserve
    # one 31–47 minute interval after the last confirmed post, then preserve a
    # second 31–47 minute interval before the next product. This makes the 6:1
    # product/editorial mix real without allowing a burst to catch up missed slots.
    editorial_gap_seconds = channel_post_interval_seconds(
        f"editorial:{item.get('editorial_id')}:{related_product_id}"
    )
    scheduled_at = max(
        current,
        anchor + timedelta(seconds=editorial_gap_seconds),
    )
    product_gap_seconds = min(
        MAX_CHANNEL_POST_INTERVAL_SECONDS,
        max(
            MIN_CHANNEL_POST_INTERVAL_SECONDS + max(0, editorial_dispatch_poll_seconds()),
            channel_post_interval_seconds(
                f"product-after-editorial:{related_product_id}:{product_entry.get('sequence_number', '')}"
            ),
        ),
    )
    original_product_at = product_at
    reserved_product_at = max(
        product_at,
        scheduled_at + timedelta(seconds=product_gap_seconds),
    )
    deal_deadline = _utc(related_product.get("deal_expires_at"))
    if deal_deadline is not None and deal_deadline <= reserved_product_at:
        print(
            "EDITORIAL_SLOT_SKIPPED_NEAR_EXPIRY_PRODUCT "
            f"product_id={related_product_id} deadline={deal_deadline.isoformat()} "
            f"reserved_product_slot={reserved_product_at.isoformat()}"
        )
        return None
    reservation_seconds = max(0.0, (reserved_product_at - original_product_at).total_seconds())
    if reservation_seconds > 0:
        # Shift the related next product and later product slots by the same amount;
        # published records and already confirmed sends are never rewritten.
        for queued_product_id, queued_product in active_products.items():
            if not isinstance(queued_product, dict):
                continue
            queued_at = _utc(queued_product.get("scheduled_at"))
            if queued_at is None or queued_at < original_product_at:
                continue
            queued_product_at = queued_at + timedelta(seconds=reservation_seconds)
            queued_product["scheduled_at"] = queued_product_at.isoformat()
            retry_at = _utc(queued_product.get("next_attempt_at"))
            queued_product["next_attempt_at"] = (
                max(queued_product_at, retry_at).isoformat()
                if retry_at is not None and retry_at > current
                else queued_product_at.isoformat()
            )
        product_at = reserved_product_at
        print(
            "EDITORIAL_PRODUCT_SLOT_RESERVED "
            f"product_id={related_product_id} added_seconds={int(reservation_seconds)} "
            f"editorial_slot={scheduled_at.isoformat()} next_product_slot={product_at.isoformat()}"
        )

    sequence_number = allocate_publication_sequence(state)
    item["sequence_number"] = sequence_number
    item["related_product_id"] = related_product_id
    queue = state.setdefault("editorial_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["editorial_delivery_queue"] = queue
    entry = {
        "content_id": item["content_id"],
        "content_type": "editorial",
        "sequence_number": sequence_number,
        "selected_at": current.isoformat(),
        "scheduled_at": scheduled_at.isoformat(),
        "next_attempt_at": scheduled_at.isoformat(),
        "window_closes_at": (
            product_at
            - timedelta(seconds=max(MIN_CHANNEL_POST_INTERVAL_SECONDS, delivery_runway_seconds))
        ).isoformat(),
        "dispatch_runway_seconds": dispatch_runway_seconds,
        "delivery_runway_seconds": delivery_runway_seconds,
        "status": "queued",
        "attempt_count": 0,
        "payload": item,
        "related_product_id": related_product_id,
        "related_product_original_scheduled_at": original_product_at.isoformat(),
        "related_product_reserved_scheduled_at": product_at.isoformat(),
        "platforms": {
            name: {"status": "pending", "attempts": 0}
            for name in PLATFORM_NAMES
        },
    }
    queue[item["content_id"]] = entry
    state["last_editorial_attempt_at"] = current.isoformat()
    print(
        "EDITORIAL_FALLBACK_QUEUED "
        f"content_id={item['content_id']} sequence={sequence_number} "
        f"related_product_id={related_product_id} "
        f"scheduled_at={scheduled_at.isoformat()} "
        f"product_slot={product_at.isoformat()}"
    )
    return entry


def _topic_emoji(item: dict) -> str:
    """Return a small topic-specific marker for an editorial title."""
    topic = str(item.get("topic") or "").strip().lower()
    mapping = {
        "purchase-planning": "🛒",
        "review-literacy": "⭐",
        "seller-check": "🛍️",
        "seller-verification": "🔎",
        "purchase-records": "🧾",
        "product-inspection": "🔍",
        "product-condition": "📦",
        "total-cost": "💰",
        "fit-and-size": "📏",
        "device-compatibility": "🔌",
        "warranty-and-service": "🛠️",
        "maintenance-and-care": "🧰",
        "privacy-and-security": "🛡️",
        "safe-payment": "💳",
        "product-safety": "⚠️",
        "shipping-and-returns": "🚚",
        "parcel-check": "📦",
        "delivery": "🚚",
        "security": "🔐",
        "account-security": "🔐",
        "privacy": "🛡️",
        "home-care": "🏠",
        "mobile": "📱",
    }
    return mapping.get(topic, "💡")


def _readable_editorial_body(value: Any) -> str:
    """Render original editorial prose while stripping public source/affiliate material.

    Provenance remains in the reviewed bank and internal delivery ledger. It is never
    appended to a public caption or video description. A whole line containing a link
    or source/commerce footer is discarded to avoid leaving a broken markdown CTA.
    """
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    forbidden_markers = (
        "📚 منبع:",
        "منبع:",
        "منابع:",
        "پیوند همکاری در فروش",
        "مشاهدهٔ پیشنهاد مرتبط",
        "مشاهده پیشنهاد مرتبط",
        "aflo.ir",
        "digikala.com/mag/",
    )
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        folded = line.casefold()
        if any(marker.casefold() in folded for marker in forbidden_markers):
            continue
        if re.search(r"https?://|www\.", line, flags=re.IGNORECASE) or "](" in line:
            continue
        sentences = re.split(r"(?<=[.!?؟])\s+", line)
        paragraphs.extend(part.strip() for part in sentences if part.strip())
    return "\n\n".join(paragraphs)


def _public_editorial_payload(item: dict) -> dict:
    """Return display-only editorial fields with no source/commerce footer leakage."""
    public_item = dict(item)
    public_item["title"] = _readable_editorial_body(item.get("title")).replace("\n", " ").strip()[:110]
    public_item["body"] = _readable_editorial_body(item.get("body"))
    return public_item


def _format_message(item: dict, *, html_mode: bool = True, platform: str = "telegram") -> str:
    """Render a self-contained editorial post with no public sources or commercial links."""
    title = _readable_editorial_body(item.get("title")).replace("\n", " ").strip()[:110]
    body = _readable_editorial_body(item.get("body"))
    if len(body) > 430:
        shortened = body[:427].rsplit(" ", 1)[0].rstrip()
        body = shortened + "…"
    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
    emoji = _topic_emoji(item)
    rendered = [f"{emoji} {html.escape(title) if html_mode else title}", ""]
    for index, value in enumerate(paragraphs):
        marker = "💡" if index == 0 else (
            "✅" if index == len(paragraphs) - 1 and len(paragraphs) > 1 else "📌"
        )
        rendered.append(f"{marker} {html.escape(value) if html_mode else value}")
    message = "\n".join(rendered).rstrip()
    # Defensive output contract: approved source metadata and affiliate URLs are
    # internal-only and must never leak from a future bank/template change.
    forbidden = ("📚 منبع:", "پیوند همکاری در فروش", "aflo.ir", "digikala.com/mag/")
    if any(token.casefold() in message.casefold() for token in forbidden):
        raise ValueError("editorial_public_provenance_or_commerce_leak")
    return message[:1000 if html_mode else 3400]



def _send_bot_message(platform: str, message: str, item: dict | None = None) -> dict:
    if platform == "telegram":
        token = radar.BOT_TOKEN
        chat_id = radar.TARGET_CHAT
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    elif platform == "bale":
        token = radar.BALE_BOT_TOKEN
        chat_id = radar.BALE_CHANNEL_ID
        endpoint = f"https://tapi.bale.ai/bot{token}/sendMessage"
    else:
        raise ValueError("unsupported_bot_message_destination")
    if not token or not chat_id:
        raise RuntimeError("destination_credentials_missing")
    payload_data = {"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}
    if "<b>" in message or "<a href=" in message:
        payload_data["parse_mode"] = "HTML"
    response = requests.post(
        endpoint,
        data=payload_data,
        timeout=(15, 45),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is not True or not isinstance(payload.get("result"), dict):
        raise RuntimeError(f"{platform}_send_message_not_confirmed")
    result = payload["result"]
    message_id = result.get("message_id") or result.get("id")
    if message_id in (None, ""):
        return {"api_accepted": True}
    return {"message_id": str(message_id)}


def _send_bot_photo(
    platform: str, image_bytes: bytes, caption: str, item: dict | None = None
) -> dict:
    if platform == "telegram":
        token = radar.BOT_TOKEN
        chat_id = radar.TARGET_CHAT
        endpoint = f"https://api.telegram.org/bot{token}/sendPhoto"
    elif platform == "bale":
        token = radar.BALE_BOT_TOKEN
        chat_id = radar.BALE_CHANNEL_ID
        endpoint = f"https://tapi.bale.ai/bot{token}/sendPhoto"
    else:
        raise ValueError("unsupported_bot_photo_destination")
    if not token or not chat_id:
        raise RuntimeError("destination_credentials_missing")
    data = {"chat_id": chat_id, "caption": caption[:1000]}
    if "<b>" in caption or "<a href=" in caption:
        data["parse_mode"] = "HTML"
    response = requests.post(
        endpoint,
        data=data,
        files={"photo": ("offerchin-editorial.png", image_bytes, "image/png")},
        timeout=(15, 90),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is not True or not isinstance(payload.get("result"), dict):
        raise RuntimeError(f"{platform}_send_photo_not_confirmed")
    result = payload["result"]
    message_id = result.get("message_id") or result.get("id")
    if message_id in (None, ""):
        return {"api_accepted": True}
    return {"message_id": str(message_id)}


def _send_rubika_image(image_bytes: bytes, caption: str) -> dict:
    import messenger_adapters as adapters

    token = os.getenv("RUBIKA_BOT_TOKEN", "").strip()
    channel_id = os.getenv("RUBIKA_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        raise RuntimeError("rubika_credentials_missing")
    upload_info = adapters._rubika_call(token, "requestSendFile", {"type": "Image"})
    upload_url = str(upload_info.get("upload_url") or "").strip()
    from urllib.parse import urlsplit
    parsed = urlsplit(upload_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError("rubika_upload_url_invalid")
    response = requests.post(
        upload_url, files={"file": ("offerchin-editorial.png", image_bytes, "image/png")},
        timeout=(15, 90),
    )
    data = adapters._response_json(response, "Rubika editorial image upload")
    status = str(data.get("status") or "").upper()
    if status and status not in {"OK", "SUCCESS"}:
        adapters._rubika_data(data, "editorial image upload")
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    file_id = str(payload.get("file_id") or "").strip()
    if not file_id:
        raise RuntimeError("rubika_editorial_file_id_missing")
    sent = adapters._rubika_call(token, "sendFile", {
        "chat_id": channel_id, "file_id": file_id, "text": caption[:3800],
    })
    message_id = str(sent.get("message_id") or "").strip()
    if not message_id:
        return {"api_accepted": True}
    return {"message_id": message_id}


def _send_eitaa_image(image_bytes: bytes, caption: str) -> dict:
    import messenger_adapters as adapters

    token = os.getenv("EITAA_BOT_TOKEN", "").strip()
    channel_id = os.getenv("EITAA_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        raise RuntimeError("eitaa_credentials_missing")
    response = requests.post(
        f"{adapters.EITAA_API}/{token}/sendFile",
        data={"chat_id": channel_id, "caption": caption[:3800], "title": "راهنمای آفِرچین"},
        files={"file": ("offerchin-editorial.png", image_bytes, "image/png")},
        timeout=(15, 90),
    )
    payload = adapters._response_json(response, "Eitaa editorial image")
    result = payload.get("result")
    accepted = (
        payload.get("ok") is True
        or str(payload.get("status") or "").lower() == "success"
        or (isinstance(result, str) and result.lower() == "success")
    )
    if not accepted:
        raise RuntimeError("eitaa_editorial_send_not_confirmed")
    message_id = ""
    if isinstance(result, dict):
        message_id = str(result.get("message_id") or result.get("id") or "").strip()
    if not message_id and isinstance(payload.get("data"), dict):
        message_id = str(payload["data"].get("message_id") or payload["data"].get("id") or "").strip()
    if not message_id:
        return {"api_accepted": True}
    return {"message_id": message_id}


def _destination_ready(name: str, state: dict, now: datetime) -> tuple[bool, str]:
    if name == "telegram":
        return bool(radar.BOT_TOKEN), "telegram_credentials_missing"
    if name == "bale":
        return bool(radar.BALE_BOT_TOKEN and radar.BALE_CHANNEL_ID), "bale_credentials_missing"
    if name == "rubika":
        enabled = os.getenv("RUBIKA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
        ready = enabled and bool(os.getenv("RUBIKA_BOT_TOKEN", "").strip()) and bool(os.getenv("RUBIKA_CHANNEL_ID", "").strip())
        return ready, "rubika_not_enabled_or_credentials_missing"
    if name == "eitaa":
        enabled = os.getenv("EITAA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
        ready = enabled and bool(os.getenv("EITAA_BOT_TOKEN", "").strip()) and bool(os.getenv("EITAA_CHANNEL_ID", "").strip())
        return ready, "eitaa_not_enabled_or_credentials_missing"
    if name == "youtube":
        from short_video import youtube_credentials_available
        pause = _utc(state.get("youtube_uploads_paused_until"))
        if pause and pause > now:
            return False, "youtube_daily_quota_pause"
        return bool(youtube_credentials_available()), "youtube_credentials_missing"
    if name == "aparat":
        from aparat_uploader import aparat_credentials_available
        if not radar.APARAT_UPLOAD_ENABLED:
            return False, "aparat_upload_disabled"
        if os.getenv("APARAT_VIDEO_PASS", "1").strip() != "0":
            return False, "aparat_public_upload_not_enabled"
        return bool(aparat_credentials_available()), "aparat_credentials_missing"
    if name == "filo":
        from filo_uploader import filo_credentials_available
        if not filo_credentials_available():
            return False, "filo_credentials_missing"
        if not radar._filo_login_verified(state, now):
            return False, "filo_login_not_verified"
        return True, ""
    return False, "unsupported_destination"


def _terminal_skip_reason(name: str, reason: str) -> str:
    if "quota" in reason or "rate" in reason or "limit" in reason:
        return "skipped_limit"
    return "not_connected"


def _target(entry: dict, name: str) -> dict:
    targets = entry.setdefault("platforms", {})
    target = targets.get(name)
    if not isinstance(target, dict):
        target = {"status": "pending", "attempts": 0}
        targets[name] = target
    target.setdefault("status", "pending")
    target.setdefault("attempts", 0)
    return target


def _safe_error(exc: Exception) -> str:
    detail = " ".join(str(exc or "").split())
    detail = re.sub(r"https?://\S+", "[redacted-url]", detail)
    detail = re.sub(r"(?i)\b(token|secret|authorization|cookie)\b\s*[:=]\s*\S+", r"\1=[redacted]", detail)
    detail = re.sub(r"\b[A-Za-z0-9_-]{28,}\b", "[redacted-id]", detail)
    return (detail[:180] or type(exc).__name__)


def _record_success(state: dict, entry: dict, destination: str, receipt: dict, now: datetime) -> None:
    target = _target(entry, destination)
    target["status"] = "sent"
    target["updated_at"] = now.isoformat()
    target.pop("last_error", None)
    target.pop("next_attempt_at", None)
    if receipt.get("message_id") is not None:
        target["message_id"] = str(receipt["message_id"])
    if receipt.get("url"):
        target["url"] = str(receipt["url"])
    if destination in CHANNEL_DESTINATIONS:
        state["last_channel_published_at"] = now.isoformat()
        state["last_published_at"] = now.isoformat()
    state["last_editorial_confirmed_at"] = now.isoformat()
    payload = dict(entry.get("payload")) if isinstance(entry.get("payload"), dict) else {}
    # Use the reserved delivery identity, not a worker-local timestamp, so all
    # parallel destination receipts are merged into one editorial event.
    content_id = str(entry.get("content_id") or payload.get("content_id") or "").strip()
    if content_id:
        payload["content_id"] = content_id
    sequence_number = entry.get("sequence_number")
    if sequence_number not in (None, ""):
        payload["sequence_number"] = sequence_number
    try:
        # Record only this worker's receipt. Sibling destinations are merged
        # from their own workers by destination key; copying the entire local
        # platform map here would let pending siblings overwrite sent receipts.
        record_editorial_delivery(
            state, payload, published_at=now,
            destinations={destination: dict(target)},
        )
    except ValueError:
        pass
    if destination in CHANNEL_DESTINATIONS:
        reflow_product_queue_after_delivery(state, now=now)


def _record_failure(entry: dict, destination: str, exc: Exception, now: datetime) -> None:
    target = _target(entry, destination)
    detail = _safe_error(exc)
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        status_code = int(status_code) if status_code is not None else None
    except (TypeError, ValueError, OverflowError):
        status_code = None
    if (
        isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
        or "network failure" in detail.casefold()
        or (status_code and status_code >= 500)
    ):
        target["status"] = "manual_review"
        target["last_error"] = f"outcome_unknown:{type(exc).__name__}:{detail}"[:300]
        target["updated_at"] = now.isoformat()
        return
    if status_code == 429:
        target["status"] = "skipped_limit"
        target["last_error"] = "platform_rate_limited"
        target["updated_at"] = now.isoformat()
        return
    try:
        attempts = int(target.get("attempts") or 0)
    except (TypeError, ValueError, OverflowError):
        attempts = MAX_ATTEMPTS
    if attempts >= MAX_ATTEMPTS:
        target["status"] = "manual_review"
        target["last_error"] = f"retry_limit_reached:{detail}"[:300]
        target["updated_at"] = now.isoformat()
        return
    target["status"] = "failed"
    target["last_error"] = f"{type(exc).__name__}:{detail}"[:300]
    target["next_attempt_at"] = (
        now + timedelta(seconds=min(3600, RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1))))
    ).isoformat()
    target["updated_at"] = now.isoformat()


def _handle_channel_destination(
    state: dict, entry: dict, destination: str, image_bytes: bytes, message: str, now: datetime,
    *, persist: bool = True,
) -> None:
    target = _target(entry, destination)
    ready, unavailable_reason = _destination_ready(destination, state, now)
    if target.get("status") == "not_connected" and ready:
        target.update({"status": "pending"})
        target.pop("last_error", None)
    if not ready:
        if target.get("status") not in TERMINAL:
            target["status"] = _terminal_skip_reason(destination, unavailable_reason)
            target["last_error"] = unavailable_reason
            target["updated_at"] = now.isoformat()
            if persist:
                _save(state)
        return
    if target.get("status") in TERMINAL:
        return
    if target.get("status") == "sending":
        target["status"] = "manual_review"
        target["last_error"] = "interrupted_during_send_outcome_unknown"
        target["updated_at"] = now.isoformat()
        if persist:
            _save(state)
        return
    retry_at = _utc(target.get("next_attempt_at"))
    if target.get("status") == "failed" and retry_at and retry_at > now:
        return

    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    target["attempts"] = int(target.get("attempts") or 0) + 1
    entry["status"] = "publishing"
    if persist:
        _save(state)
    try:
        if destination in {"telegram", "bale"}:
            editorial_payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
            receipt = (
                _send_bot_photo(destination, image_bytes, message, item=editorial_payload)
                if image_bytes else _send_bot_message(destination, message, item=editorial_payload)
            )
        elif destination == "rubika":
            receipt = _send_rubika_image(image_bytes, message)
        else:
            receipt = _send_eitaa_image(image_bytes, message)
        confirmed = bool(receipt.get("message_id"))
        if receipt.get("api_accepted") and not receipt.get("message_id"):
            target["status"] = "manual_review"
            target["last_error"] = "api_accepted_without_public_message_id_unverified"
            target["updated_at"] = _now().isoformat()
            if persist:
                _save(state)
            print(
                f"EDITORIAL_DESTINATION_UNVERIFIED content_id={entry['content_id']} "
                f"platform={destination} reason=api_accepted_without_public_message_id"
            )
            return
        if not confirmed:
            raise RuntimeError("destination_receipt_missing")
        _record_success(state, entry, destination, receipt, _now())
        if persist:
            _save(state)
        print(f"EDITORIAL_DESTINATION_SENT content_id={entry['content_id']} platform={destination}")
    except Exception as exc:
        _record_failure(entry, destination, exc, _now())
        if persist:
            _save(state)
        print(
            f"EDITORIAL_DESTINATION_FAILED content_id={entry['content_id']} "
            f"platform={destination} error={type(exc).__name__} detail={_safe_error(exc)}"
        )


def _deliver_channel_destination_isolated(
    base_state: dict,
    content_id: str,
    destination: str,
    image_bytes: bytes,
    message: str,
    now: datetime,
) -> dict:
    """Send one editorial photo destination against a private, non-persisting state copy."""
    local_state = copy.deepcopy(base_state)
    queue = local_state.get("editorial_delivery_queue")
    if not isinstance(queue, dict) or not isinstance(queue.get(content_id), dict):
        raise KeyError(f"editorial_delivery_queue_entry_missing:{content_id}")
    local_entry = queue[content_id]
    _handle_channel_destination(
        local_state,
        local_entry,
        destination,
        image_bytes,
        message,
        now,
        persist=False,
    )
    return local_state


def _deliver_channels_concurrently(
    state: dict,
    entry: dict,
    image_bytes: bytes,
    destinations: tuple[str, ...],
    now: datetime,
) -> dict:
    """Fan out editorial photo delivery independently and merge destination receipts safely."""
    selected = tuple(dict.fromkeys(str(name).strip().lower() for name in destinations if str(name).strip()))
    if not selected:
        return entry

    content_id = str(entry.get("content_id") or "").strip()
    if not content_id:
        raise ValueError("editorial_content_id_missing")

    base_state = copy.deepcopy(state)
    merged_state = copy.deepcopy(state)
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}

    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {
            executor.submit(
                _deliver_channel_destination_isolated,
                base_state,
                content_id,
                destination,
                image_bytes,
                _format_message(
                    payload,
                    html_mode=destination in {"telegram", "bale"},
                    platform=destination,
                ),
                now,
            ): destination
            for destination in selected
        }
        for future in as_completed(futures):
            destination = futures[future]
            try:
                local_state = future.result()
            except Exception as exc:
                # An adapter exception is local to this destination; preserve its
                # retry/manual-review outcome without discarding sibling receipts.
                local_state = copy.deepcopy(base_state)
                local_queue = local_state.get("editorial_delivery_queue")
                local_entry = local_queue.get(content_id) if isinstance(local_queue, dict) else None
                if not isinstance(local_entry, dict):
                    raise
                _record_failure(local_entry, destination, exc, _now())
                print(
                    f"EDITORIAL_DESTINATION_FAILED content_id={content_id} "
                    f"platform={destination} error={type(exc).__name__} detail={_safe_error(exc)}"
                )
            merged_state = three_way_merge(base_state, merged_state, local_state)

    state.clear()
    state.update(merged_state)
    queue = state.get("editorial_delivery_queue")
    updated_entry = queue.get(content_id) if isinstance(queue, dict) else None
    if not isinstance(updated_entry, dict):
        raise KeyError(f"editorial_delivery_queue_entry_missing_after_merge:{content_id}")
    return updated_entry


def _video_description(item: dict) -> str:
    """Keep editorial video descriptions utility-only and free of sources or affiliate links."""
    description = _readable_editorial_body(item.get("body"))
    forbidden = ("📚 منبع:", "پیوند همکاری در فروش", "aflo.ir", "digikala.com/mag/")
    if any(token.casefold() in description.casefold() for token in forbidden):
        raise ValueError("editorial_video_public_provenance_or_commerce_leak")
    return description[:2900]


def _handle_video_destination(
    state: dict, entry: dict, destination: str, video_path: Path, now: datetime
) -> None:
    target = _target(entry, destination)
    ready, unavailable_reason = _destination_ready(destination, state, now)
    if target.get("status") == "not_connected" and ready:
        target.update({"status": "pending"})
        target.pop("last_error", None)
    if not ready:
        target["status"] = _terminal_skip_reason(destination, unavailable_reason)
        target["last_error"] = unavailable_reason
        target["updated_at"] = now.isoformat()
        _save(state)
        return
    if target.get("status") in TERMINAL:
        return
    if target.get("status") == "sending":
        target["status"] = "manual_review"
        target["last_error"] = "interrupted_during_upload_outcome_unknown"
        target["updated_at"] = now.isoformat()
        _save(state)
        return
    retry_at = _utc(target.get("next_attempt_at"))
    if target.get("status") == "failed" and retry_at and retry_at > now:
        return

    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    target["attempts"] = int(target.get("attempts") or 0) + 1
    entry["status"] = "publishing"
    _save(state)
    item = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    title = str(item.get("title") or "راهنمای خرید کاربردی")
    description = _video_description(item)
    try:
        if destination == "youtube":
            from short_video import upload_youtube_video
            result = upload_youtube_video(
                video_path, title, None, description=description,
            )
            receipt = {"message_id": result.get("video_id"), "url": result.get("url")}
        elif destination == "aparat":
            from aparat_uploader import upload_aparat_video
            result = upload_aparat_video(
                video_path, title, description=description,
                tags=["آفِرچین", "راهنمای خرید", "آموزش کاربردی"],
            )
            if result.get("visibility") != "public":
                target["status"] = "manual_review"
                target["last_error"] = "aparat_submission_not_confirmed_public"
                target["video_hash"] = str(result.get("video_hash") or "")
                target["updated_at"] = _now().isoformat()
                _save(state)
                return
            receipt = {"message_id": result.get("video_hash") or result.get("video_id"), "url": result.get("url")}
        else:
            from filo_uploader import FiloUploadError, upload_filo_video
            try:
                result = upload_filo_video(video_path, title, description)
            except FiloUploadError as exc:
                if exc.submission_started:
                    target["status"] = "manual_review"
                    target["last_error"] = f"filo_submission_outcome_unknown:{exc.code}"
                    target["updated_at"] = _now().isoformat()
                    _save(state)
                    return
                raise
            if result.get("status") == "submitted_pending_approval":
                target["status"] = "manual_review"
                target["last_error"] = "filo_submitted_pending_approval_not_public"
                target["url"] = str(result.get("public_url") or "")
                target["updated_at"] = _now().isoformat()
                _save(state)
                return
            if result.get("status") != "published":
                target["status"] = "manual_review"
                target["last_error"] = str(result.get("error_code") or result.get("status") or "filo_not_publicly_verified")
                target["updated_at"] = _now().isoformat()
                _save(state)
                return
            receipt = {"message_id": result.get("video_code"), "url": result.get("public_url")}
        if not receipt.get("message_id"):
            raise RuntimeError("video_destination_receipt_missing")
        _record_success(state, entry, destination, receipt, _now())
        if destination == "youtube":
            state["youtube_last_upload_success_at"] = _now().isoformat()
        elif destination == "aparat":
            state["aparat_last_upload_success_at"] = _now().isoformat()
        _save(state)
        print(f"EDITORIAL_VIDEO_SENT content_id={entry['content_id']} platform={destination}")
    except Exception as exc:
        # The existing product pipeline treats a lost upload response as uncertain;
        # editorial uploads follow the same no-blind-duplicate rule.
        detail = _safe_error(exc).lower()
        if destination == "youtube" and any(token in detail for token in (
            "uploadlimitexceeded", "video uploads per day", "daily video upload limit"
        )):
            retry_at = radar._next_youtube_daily_upload_retry_at(_now())
            target["status"] = "retry"
            target["next_attempt_at"] = retry_at.isoformat()
            target["last_error"] = "youtube_daily_quota_exceeded"
            state["youtube_uploads_paused_until"] = retry_at.isoformat()
            state["youtube_upload_pause_reason"] = "daily_upload_limit"
            target["updated_at"] = _now().isoformat()
        else:
            _record_failure(entry, destination, exc, _now())
        _save(state)
        print(
            f"EDITORIAL_VIDEO_FAILED content_id={entry['content_id']} "
            f"platform={destination} error={type(exc).__name__} detail={_safe_error(exc)}"
        )


def _refresh_delivery_history(state: dict, entry: dict, now: datetime) -> None:
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
    if any(isinstance(value, dict) and value.get("status") == "sent" for value in targets.values()):
        history = state.get("editorial_delivery_history")
        row = next(
            (item for item in reversed(history) if isinstance(item, dict) and item.get("content_id") == entry.get("content_id")),
            None,
        ) if isinstance(history, list) else None
        if row is None:
            record_editorial_delivery(state, payload, published_at=now, destinations=targets)
            history = state.get("editorial_delivery_history")
            row = history[-1] if isinstance(history, list) and history else None
        if isinstance(row, dict):
            row["destinations"] = targets
            row["sequence_number"] = entry.get("sequence_number")
            if entry.get("delivery_duration_seconds") is not None:
                row["delivery_duration_seconds"] = entry.get("delivery_duration_seconds")


def _release_failed_editorial_product_reservation(state: dict, entry: dict) -> None:
    """Undo a planned product delay when no public channel actually received editorial."""
    related_id = str(entry.get("related_product_id") or "").strip()
    original_at = _utc(entry.get("related_product_original_scheduled_at"))
    reserved_at = _utc(entry.get("related_product_reserved_scheduled_at"))
    if not related_id or original_at is None or reserved_at is None:
        return
    shift = reserved_at - original_at
    if shift.total_seconds() <= 0:
        return
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict):
        return
    for product_id, product_entry in queue.items():
        if not isinstance(product_entry, dict) or product_entry.get("status") in {
            "published", "completed", "cancelled", "stale_selection"
        }:
            continue
        if str(product_id) != related_id:
            product_at = _utc(product_entry.get("scheduled_at"))
            if product_at is None or product_at < reserved_at:
                continue
            new_at = product_at - shift
        else:
            new_at = original_at
        product_entry["scheduled_at"] = new_at.isoformat()
        retry_at = _utc(product_entry.get("next_attempt_at"))
        product_entry["next_attempt_at"] = (
            max(new_at, retry_at).isoformat()
            if retry_at is not None and retry_at > _now()
            else new_at.isoformat()
        )
    print(
        "EDITORIAL_PRODUCT_SLOT_RESERVATION_RELEASED "
        f"related_product_id={related_id} restored_seconds={int(shift.total_seconds())}"
    )


def _finalize_if_terminal(state: dict, entry: dict, now: datetime) -> bool:
    targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
    if not all(
        isinstance(targets.get(name), dict) and targets[name].get("status") in TERMINAL
        for name in PLATFORM_NAMES
    ):
        entry["status"] = "partial"
        return False
    success = any(targets[name].get("status") == "sent" for name in PLATFORM_NAMES)
    channel_success = any(
        isinstance(targets.get(name), dict) and targets[name].get("status") == "sent"
        for name in CHANNEL_DESTINATIONS
    )
    if not channel_success:
        _release_failed_editorial_product_reservation(state, entry)
    entry["status"] = "completed" if success else "failed"
    entry["updated_at"] = now.isoformat()
    entry["terminal_summary"] = {name: targets[name].get("status") for name in PLATFORM_NAMES}
    queue = state.get("editorial_delivery_queue")
    history = state.setdefault("editorial_delivery_attempts", [])
    if not isinstance(history, list):
        history = []
        state["editorial_delivery_attempts"] = history
    history.append({
        "content_id": entry.get("content_id"),
        "sequence_number": entry.get("sequence_number"),
        "status": entry["status"],
        "terminal_summary": entry["terminal_summary"],
        "delivery_duration_seconds": entry.get("delivery_duration_seconds"),
        "updated_at": now.isoformat(),
    })
    state["editorial_delivery_attempts"] = history[-200:]
    if isinstance(queue, dict):
        queue.pop(str(entry.get("content_id") or ""), None)
    return True


def build_editorial_shadow_report(*, now: datetime | None = None) -> dict:
    """Read-only assessment for a no-publication 24-hour shadow window."""
    current = now or _now()
    state = radar.load_state(apply_integrity_ledger=False)
    bank = _load_bank()
    valid_items = []
    invalid_items = []
    from editorial_content import validate_editorial_item
    for item in bank:
        valid, reason = validate_editorial_item(item, now=current)
        if valid:
            valid_items.append(item)
        else:
            invalid_items.append({"editorial_id": str(item.get("editorial_id") or ""), "reason": reason})

    active = _active_editorial_entries(state)
    product_queue = state.get("content_delivery_queue")
    active_products = [
        row for row in (product_queue.values() if isinstance(product_queue, dict) else [])
        if isinstance(row, dict) and row.get("status") not in {"published", "cancelled", "stale_selection"}
    ]
    pending_videos = _pending_product_video_exists(state)
    shadow_state_for_anchor = json.loads(json.dumps(state, ensure_ascii=False, default=str))
    anchor = _recent_attempt_anchor(shadow_state_for_anchor)
    remaining = 0

    destination_config = {
        "telegram": bool(radar.BOT_TOKEN and radar.TARGET_CHAT),
        "bale": bool(radar.BALE_BOT_TOKEN and radar.BALE_CHANNEL_ID),
        "rubika": bool(os.getenv("RUBIKA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
                       and os.getenv("RUBIKA_BOT_TOKEN", "").strip()
                       and os.getenv("RUBIKA_CHANNEL_ID", "").strip()),
        "eitaa": bool(os.getenv("EITAA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
                      and os.getenv("EITAA_BOT_TOKEN", "").strip()
                      and os.getenv("EITAA_CHANNEL_ID", "").strip()),
    }
    try:
        from short_video import youtube_credentials_available
        destination_config["youtube"] = bool(youtube_credentials_available())
    except Exception:
        destination_config["youtube"] = False
    try:
        from aparat_uploader import aparat_credentials_available
        destination_config["aparat"] = bool(radar.APARAT_UPLOAD_ENABLED and aparat_credentials_available())
    except Exception:
        destination_config["aparat"] = False
    try:
        from filo_uploader import filo_credentials_available
        destination_config["filo"] = bool(filo_credentials_available() and radar._filo_login_verified(state, current))
    except Exception:
        destination_config["filo"] = False

    if active:
        selected = active[0]
        decision = "resume_active_editorial"
        item_id = str(selected.get("content_id") or "")
        sequence = selected.get("sequence_number")
    elif active_products:
        decision = "wait_for_older_product_photo_fifo"
        item_id = None
        sequence = None
    elif pending_videos:
        decision = "wait_for_older_product_video_fifo"
        item_id = None
        sequence = None
    else:
        # Editorial may only occupy a reserved shared-channel slot before a selected product.
        # The shadow report must never predict a standalone editorial post.
        candidate_product = _next_product_slot(state, current)
        if candidate_product is None:
            decision = "wait_for_selected_product_slot"
            item_id = None
            sequence = None
        else:
            shadow_state = json.loads(json.dumps(state, ensure_ascii=False, default=str))
            candidate = select_editorial_fallback(
                bank, shadow_state, now=current,
                related_product=(
                    candidate_product[1].get("payload")
                    if isinstance(candidate_product[1].get("payload"), dict) else {}
                ),
            )
            if candidate is None:
                decision = "no_valid_nonrepeating_reviewed_item"
                item_id = None
                sequence = None
            else:
                sequence = allocate_publication_sequence(shadow_state)
                decision = "would_queue_editorial_before_product"
                item_id = str(candidate.get("content_id") or "")

    return {
        "observed_at": current.astimezone(timezone.utc).isoformat(),
        "mode": "shadow_read_only",
        "public_publish_performed": False,
        "decision": decision,
        "would_select_content_id": item_id,
        "would_allocate_sequence_number": sequence,
        "requires_selected_product_slot": True,
        "editorial_bank_total": len(bank),
        "editorial_bank_valid": len(valid_items),
        "editorial_bank_invalid": invalid_items,
        "active_editorial_queue_items": len(active),
        "active_product_photo_queue_items": len(active_products),
        "older_product_video_pending": bool(pending_videos),
        "destination_credentials_present": destination_config,
        "platform_quota_and_upload_health_probed": False,
        "state_mutated": False,
        "limitations": [
            "Credentials are checked locally only; no destination API is contacted.",
            "This is not proof of a public post or of destination availability.",
            "A 24-hour run must be reviewed before enabling public editorial publishing.",
        ],
    }


def run_editorial_publisher(*, mode: str, publish: bool, now: datetime | None = None) -> int:
    if mode not in {"channels", "videos"}:
        raise ValueError("mode_must_be_channels_or_videos")
    current = now or _now()
    state = radar.load_state(apply_integrity_ledger=False)
    bank = _load_bank()
    if publish:
        recovered = _rehydrate_orphaned_editorial_entries(state, bank, now=current)
        if recovered:
            _save(state)
            _refresh_dispatch_projection(state)
    if publish and mode == "channels" and _channel_spacing_guard_applies(state):
        spacing_wait = channel_publication_wait_seconds(state, now=current)
        if spacing_wait > 0:
            next_slot = next_channel_publication_at(state)
            print(
                "EDITORIAL_SHARED_CHANNEL_SPACING_GUARD "
                f"remaining_seconds={spacing_wait} "
                f"next_slot={next_slot.isoformat() if next_slot else 'unknown'} "
                f"minimum_gap_seconds={MIN_CHANNEL_POST_INTERVAL_SECONDS}"
            )
            _refresh_dispatch_projection(state)
            return 0
    entry = queue_editorial_if_due(state, bank, now=current)
    if publish:
        # Persist the canonical id and allocated sequence before rendering or any
        # outbound request, so a runner restart cannot allocate a duplicate sequence.
        _save(state)
        _refresh_dispatch_projection(state)
    if not entry:
        if publish:
            _save(state)
        return 0
    scheduled_at = _utc(entry.get("scheduled_at"))
    if scheduled_at is not None and scheduled_at > current.astimezone(timezone.utc):
        print(
            "EDITORIAL_NOT_DUE "
            f"content_id={entry.get('content_id')} scheduled_at={scheduled_at.isoformat()}"
        )
        if publish:
            _save(state)
            _refresh_dispatch_projection(state)
        return 0
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    if not publish:
        print(
            f"EDITORIAL_DRY_RUN mode={mode} content_id={entry.get('content_id')} "
            f"sequence={entry.get('sequence_number')} destinations={','.join(PLATFORM_NAMES)}"
        )
        return 0

    window_closes_at = _utc(entry.get("window_closes_at"))
    if window_closes_at is not None and current.astimezone(timezone.utc) > window_closes_at:
        entry["status"] = "cancelled"
        _release_failed_editorial_product_reservation(state, entry)
        entry["last_detail"] = "editorial_dispatch_window_closed_before_product"
        queue = state.get("editorial_delivery_queue")
        if isinstance(queue, dict):
            queue.pop(str(entry.get("content_id") or ""), None)
        print(
            "EDITORIAL_WINDOW_CLOSED "
            f"content_id={entry.get('content_id')} window_closes_at={window_closes_at.isoformat()}"
        )
        _save(state)
        _refresh_dispatch_projection(state)
        return 0

    if _hydrate_confirmed_editorial_receipts(state, entry):
        _save(state)

    if mode == "channels":
        channel_destinations = _selected_channel_destinations()
        entry["delivery_started_at"] = _now().isoformat()
        _save(state)
        try:
            from editorial_video import render_editorial_poster
            image_bytes = render_editorial_poster(_public_editorial_payload(payload))
        except Exception as exc:
            print(f"EDITORIAL_POSTER_RENDER_FAILED error={type(exc).__name__}")
            return 1
        entry = _deliver_channels_concurrently(
            state,
            entry,
            image_bytes,
            channel_destinations,
            _now(),
        )
    else:
        # Each video workflow follows its own destination FIFO. A quota pause or
        # retry on YouTube must not hold Aparat or Filo (and vice versa).
        video_destinations = _selected_video_destinations()
        if _pending_product_video_exists(state, set(video_destinations)):
            print(
                "EDITORIAL_VIDEO_WAIT reason=older_product_video_fifo_pending "
                f"destinations={','.join(video_destinations)}"
            )
            _save(state)
            _refresh_dispatch_projection(state)
            return 0
        entry["delivery_started_at"] = _now().isoformat()
        _save(state)
        output_path = Path("video_artifacts") / (
            f"editorial-{payload.get('editorial_id')}-{entry.get('sequence_number')}.mp4"
        )
        try:
            from editorial_video import render_editorial_video
            if any(
                _target(entry, name).get("status") not in TERMINAL
                for name in video_destinations
            ):
                render_editorial_video(_public_editorial_payload(payload), output_path)
        except Exception as exc:
            for destination in video_destinations:
                target = _target(entry, destination)
                if target.get("status") not in TERMINAL:
                    target["status"] = "manual_review"
                    target["last_error"] = f"editorial_video_render_failed:{type(exc).__name__}"
            _save(state)
            return 1
        for destination in video_destinations:
            _handle_video_destination(state, entry, destination, output_path, _now())

    now_after = _now()
    delivery_started_at = _utc(entry.get("delivery_started_at"))
    if delivery_started_at is not None:
        entry["delivery_duration_seconds"] = round(
            max(0.0, (now_after - delivery_started_at).total_seconds()), 1
        )
    _refresh_delivery_history(state, entry, now_after)
    finalized = _finalize_if_terminal(state, entry, now_after)
    if finalized:
        print(
            f"EDITORIAL_DELIVERY_TERMINAL content_id={entry.get('content_id')} "
            f"status={entry.get('status')} sequence={entry.get('sequence_number')}"
        )
    _save(state)
    if publish:
        _refresh_dispatch_projection(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OfferChin editorial fallback delivery")
    parser.add_argument("--channels-only", action="store_true")
    parser.add_argument("--videos-only", action="store_true")
    parser.add_argument("--publish", action="store_true", help="perform external publishing; otherwise dry-run only")
    parser.add_argument("--shadow-report", action="store_true", help="write a read-only shadow report; never publish or mutate state")
    parser.add_argument("--report-path", default="editorial_shadow_report.json")
    args = parser.parse_args()
    if args.shadow_report:
        report = build_editorial_shadow_report()
        output = Path(args.report_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if args.channels_only == args.videos_only:
        parser.error("choose exactly one of --channels-only or --videos-only")
    return run_editorial_publisher(
        mode="channels" if args.channels_only else "videos",
        publish=args.publish,
    )


if __name__ == "__main__":
    raise SystemExit(main())
