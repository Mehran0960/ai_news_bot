"""Platform delivery worker for the OfferChin selected-content queue.

Discovery and ranking happen in affilio_radar.py. This module only consumes the
persisted hand-off contract, revalidates price/stock, and invokes destination
adapters independently. A platform failure never blocks another adapter.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import affilio_radar as radar
from content_delivery import _active_publication, due_content, enforce_queue_limit, finish_queue_item
from platform_registry import PLATFORM_NAMES, PHOTO_PLATFORMS, VIDEO_PLATFORMS, validate_registry
from integrity_audit_state import apply_integrity_audit_ledger


RETRY_BASE_SECONDS = max(60, int(os.getenv("AFFILIO_PUBLISH_RETRY_BASE_SECONDS", "300")))
MAX_ITEMS_PER_RUN = max(1, min(3, int(os.getenv("AFFILIO_PUBLISHER_BATCH_SIZE", "1"))))
TERMINAL_PLATFORM = {"sent", "not_connected", "manual_review"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save(state: dict) -> None:
    radar.save_json(radar.STATE, state)


def _utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _duplicate_guard_reason(existing: Any, delivery_id: str) -> str:
    """Prevent a new queue generation from reposting an already-active product."""
    if not isinstance(existing, dict) or not _active_publication(existing):
        return ""
    previous_delivery = str(existing.get("distribution_queue_id") or "")
    if previous_delivery and previous_delivery == str(delivery_id or ""):
        # This is a retry of the same hand-off, not a duplicate new selection.
        return ""
    return "active_publication_exists"


def _target(entry: dict, name: str) -> dict:
    platforms = entry.setdefault("platforms", {})
    value = platforms.get(name)
    if not isinstance(value, dict):
        value = {"status": "pending", "attempts": 0}
        platforms[name] = value
    value.setdefault("status", "pending")
    value.setdefault("attempts", 0)
    return value


def _target_ready(name: str) -> bool:
    if name == "telegram":
        return bool(radar.BOT_TOKEN)
    if name == "bale":
        return bool(radar.BALE_BOT_TOKEN and radar.BALE_CHANNEL_ID)
    if name == "youtube":
        try:
            from short_video import youtube_credentials_available
            return bool(youtube_credentials_available())
        except Exception:
            return False
    if name == "aparat":
        try:
            from aparat_uploader import aparat_credentials_available
            return bool(radar.APARAT_UPLOAD_ENABLED and aparat_credentials_available())
        except Exception:
            return False
    return False


def _set_target(entry: dict, name: str, status: str, now: datetime, detail: str = "") -> None:
    target = _target(entry, name)
    target["status"] = status
    target["updated_at"] = now.isoformat()
    if detail:
        target["last_error"] = str(detail)[:300]
    elif status == "sent":
        target.pop("last_error", None)
        target.pop("next_attempt_at", None)


def _target_retry(entry: dict, name: str, now: datetime, detail: str = "") -> None:
    target = _target(entry, name)
    try:
        attempts = int(target.get("attempts") or 0) + 1
    except (TypeError, ValueError, OverflowError):
        attempts = 1
    target["attempts"] = attempts
    target["status"] = "failed"
    target["last_error"] = str(detail or "delivery_failed")[:300]
    target["next_attempt_at"] = (
        now + timedelta(seconds=min(3600, RETRY_BASE_SECONDS * (2 ** min(attempts - 1, 4))))
    ).isoformat()


def _record_from_item(item: dict, old: dict | None, now: datetime, delivery_id: str) -> dict:
    expiry_at = str(item.get("deal_expires_at") or "").strip()
    same_delivery = isinstance(old, dict) and str(old.get("distribution_queue_id") or "") == delivery_id
    record = {
        "ts": now.timestamp(),
        "title": str(item.get("title") or "پیشنهاد منتخب آفرچین"),
        "product_url": str(item.get("product_url") or ""),
        "image_url": str(item.get("image_url") or ""),
        "video_generation_status": "pending",
        "youtube_upload_status": "pending",
        "aparat_upload_status": "pending",
        "click_tracking_url": "",
        "telegram_message_id": None,
        "bale_message_id": None,
        "delivery_version": 1,
        "delivery_status": {name: "pending" for name in PLATFORM_NAMES},
        "delivery_attempts": {name: 0 for name in PLATFORM_NAMES},
        "expires_at": expiry_at,
        "expiry_source": str(item.get("expiry_source") or "unavailable"),
        "expiry_estimated": bool(item.get("expiry_estimated")),
        "expiry_deadline_verified_directly": (
            item.get("expiry_deadline_verified_directly") is True
            and str(item.get("expiry_source") or "") in {
                "digikala_live_deals_feed", "digikala_product_detail_api"
            }
        ),
        "expiry_deadline_verified_from_site_card": (
            item.get("expiry_deadline_verified_from_site_card") is True
            and str(item.get("expiry_source") or "") == "digikala_mcp_offer_card"
        ),
        "caption_deadline_format_version": radar.CAPTION_DEADLINE_FORMAT_VERSION,
        "posted_discount_percent": int(item.get("discount_percent") or 0),
        "posted_current_price": int(item.get("current_price") or 0),
        "posted_original_price": int(item.get("original_price") or 0),
        "demand_score": int(item.get("demand_score") or 0),
        "promo_score": int(item.get("promo_score") or 0),
        "click_count_30d": int(item.get("click_count_30d") or 0),
        "distribution_queue_id": str(item.get("product_id") or ""),
    }
    old_history = list(old.get("post_history") or []) if isinstance(old, dict) and isinstance(old.get("post_history"), list) else []
    if isinstance(old, dict) and old and not same_delivery:
        snapshot = dict(old)
        snapshot.pop("post_history", None)
        if any(str(snapshot.get(k) or "").isdigit() for k in ("telegram_message_id", "bale_message_id")) or snapshot.get("youtube_video_id") or snapshot.get("aparat_video_hash"):
            old_history.append(snapshot)
    if old_history:
        record["post_history"] = old_history[-12:]
    # Only reuse destination IDs for a retry of the exact queue generation.
    # A later campaign for the same product must never inherit old platform IDs.
    if same_delivery:
        for field in (
            "telegram_message_id", "bale_message_id", "youtube_video_id",
            "youtube_video_url", "youtube_upload_status", "youtube_uploaded_at",
            "aparat_video_hash", "aparat_video_url", "aparat_upload_status",
            "aparat_uploaded_at", "video_file_name", "video_generation_status",
        ):
            if old.get(field) not in (None, ""):
                record[field] = old[field]
        if isinstance(old.get("delivery_status"), dict):
            record["delivery_status"].update(old["delivery_status"])
        if isinstance(old.get("delivery_attempts"), dict):
            record["delivery_attempts"].update(old["delivery_attempts"])
    record["distribution_queue_id"] = delivery_id
    return record


def _fresh_selected_item(entry: dict, now: datetime) -> tuple[dict | None, str]:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None, "missing_selection_payload"
    product_url = radar.safe_product_url(str(payload.get("product_url") or ""))
    product_id = str(payload.get("product_id") or "").lower()
    if not product_url or radar.product_id(product_url) != product_id:
        return None, "invalid_product_identity"

    # New queue entries persist the exact fallback tier selected by discovery.
    # Legacy queue entries without this field retain the historical 50% default.
    raw_discount_floor = payload.get("selection_discount_floor")
    minimum_discount_percent = None
    if raw_discount_floor is not None:
        try:
            minimum_discount_percent = int(raw_discount_floor)
        except (TypeError, ValueError, OverflowError):
            return None, "invalid_selection_discount_floor"
        if minimum_discount_percent not in radar.DISCOUNT_FALLBACK_FLOORS:
            return None, "invalid_selection_discount_floor"

    try:
        fresh = radar.fetch_product_record(product_url)
    except Exception as exc:
        return None, f"live_product_fetch_{type(exc).__name__}"
    if not isinstance(fresh, dict):
        return None, "live_product_details_incomplete"
    if radar.is_prohibited_product_title(fresh.get("title")):
        return None, "live_product_prohibited_title"
    if not radar.is_publishable_product_title(fresh.get("title")) or not fresh.get("image_url"):
        return None, "live_product_details_incomplete"
    fresh["product_id"] = product_id
    fresh["product_url"] = product_url
    fresh["merchant"] = "اسنپ‌شاپ" if product_id.startswith("snp-") else "دیجی‌کالا"

    try:
        selected_price = int(payload.get("current_price") or 0)
        live_price = int(fresh.get("current_price") or 0)
    except (TypeError, ValueError, OverflowError):
        return None, "live_price_unusable"
    if selected_price <= 0 or live_price <= 0:
        return None, "live_price_unusable"
    if live_price != selected_price:
        return None, f"selected_price_stale_selected={selected_price}_live={live_price}"

    # Keep the selection's approved tracking link and ranking signals, but never
    # reuse a stale listed price. The price/stock and image above are freshly read.
    fresh["affiliate_url"] = str(payload.get("affiliate_url") or "").strip()
    if not fresh["affiliate_url"]:
        fresh["affiliate_url"] = radar.build_affilio_tracking_link(product_url)
    fresh["has_affiliate_link"] = bool(fresh["affiliate_url"])
    for key in (
        "demand_score", "promo_score", "click_count_30d", "market_status",
        "market_reference_price_toman", "market_price_advantage_pct",
        "market_match_score", "market_seller_count",
    ):
        if key in payload and key not in fresh:
            fresh[key] = payload[key]
    if not fresh.get("affiliate_url") or not radar._is_valid_affilio_tracking_url(fresh["affiliate_url"]):
        return None, "affiliate_link_not_verified"

    try:
        fresh = radar.score_product(fresh)
    except Exception:
        pass
    price_check = radar.verify_live_page_price(fresh)
    if not price_check.get("ok"):
        return None, f"live_price_recheck_{price_check.get('reason') or 'unconfirmed'}"
    if price_check.get("page_price") and int(price_check["page_price"]) != live_price:
        return None, "live_page_price_changed_during_validation"

    # Prefer a current page/API deadline, otherwise keep the selected card timer
    # only if the price still matches; the price-audit monitor will invalidate
    # open-ended offers if price/stock later changes.
    # Preserve the selected live-card deadline only when the fresh product price
    # still matches. Prefer any newer deadline returned by the page/API.
    current_deadline = str(
        price_check.get("deal_expires_at")
        or fresh.get("deal_expires_at")
        or payload.get("deal_expires_at")
        or ""
    ).strip()
    if current_deadline:
        fresh["deal_expires_at"] = current_deadline
        source_candidates = [
            str(price_check.get("expiry_source") or ""),
            str(fresh.get("expiry_source") or ""),
            str(payload.get("expiry_source") or ""),
        ]
        valid_deadline_sources = {
            "digikala_live_deals_feed",
            "digikala_product_detail_api",
            "digikala_mcp_offer_card",
        }
        source = next((value for value in source_candidates if value in valid_deadline_sources), "")
        if not source:
            source = next((value for value in source_candidates if value), "")
        if source:
            fresh["expiry_source"] = source
        if source in {"digikala_live_deals_feed", "digikala_product_detail_api"}:
            fresh["expiry_deadline_verified_directly"] = True
            fresh["expiry_deadline_verified_from_site_card"] = False
            fresh["expiry_estimated"] = False
        elif source == "digikala_mcp_offer_card":
            fresh["expiry_deadline_verified_from_site_card"] = (
                price_check.get("expiry_deadline_verified_from_site_card") is True
                or fresh.get("expiry_deadline_verified_from_site_card") is True
                or payload.get("expiry_deadline_verified_from_site_card") is True
            )
            fresh["expiry_deadline_verified_directly"] = False
            fresh["expiry_estimated"] = False
    else:
        fresh["deal_expires_at"] = ""
        fresh["expiry_source"] = "unavailable"
        fresh["expiry_deadline_verified_directly"] = False
        fresh["expiry_deadline_verified_from_site_card"] = False
        fresh["expiry_estimated"] = False

    if fresh.get("availability") != "in_stock":
        return None, "live_stock_not_confirmed"
    if not radar.is_discount_publish_eligible(
        fresh, minimum_discount_percent=minimum_discount_percent
    ):
        return None, "live_discount_no_longer_eligible"
    if not radar.is_market_value_publish_eligible(fresh):
        return None, "live_market_value_rejected"
    if not radar.has_publishable_expiry_or_open_offer(fresh, now):
        return None, "live_offer_expired_or_unverified"
    expiry = _utc(fresh.get("deal_expires_at"))
    if expiry and expiry <= now + timedelta(minutes=radar.MIN_PUBLICATION_RUNWAY_MINUTES):
        return None, "insufficient_publication_runway"
    return fresh, ""


def _process_photo_destination(
    state: dict,
    entry: dict,
    record: dict,
    item: dict,
    image_bytes: bytes,
    destination: str,
    now: datetime,
) -> None:
    target = _target(entry, destination)
    record_status = record.setdefault("delivery_status", {})
    status = str(target.get("status") or "pending")
    if status == "sent":
        return
    if status == "sending":
        started = _utc(target.get("attempt_started_at"))
        if started and (now - started).total_seconds() < 1800:
            return
        _set_target(entry, destination, "manual_review", now, "previous_send_outcome_unknown")
        record_status[destination] = "manual_review"
        _save(state)
        print(f"PLATFORM_DELIVERY_MANUAL_REVIEW product_id={entry['product_id']} platform={destination} reason=previous_send_outcome_unknown")
        return
    if not _target_ready(destination):
        _set_target(entry, destination, "not_connected", now, "credentials_not_configured")
        record_status[destination] = "not_connected"
        _save(state)
        return
    retry_at = _utc(target.get("next_attempt_at"))
    if status in {"failed", "retry"} and retry_at and retry_at > now:
        return

    # Persist an in-flight marker before the external side effect. If a runner is
    # interrupted here, don't blindly repeat an uncertain send on the next cycle.
    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    try:
        target["attempts"] = int(target.get("attempts") or 0) + 1
    except (TypeError, ValueError, OverflowError):
        target["attempts"] = 1
    _save(state)
    try:
        result = radar._send_platform_photo(destination, item, image_bytes, str(item["affiliate_url"]))
        message_id = result.get("message_id")
        if not message_id:
            raise RuntimeError("platform did not return a message id")
        _set_target(entry, destination, "sent", _now())
        record_status[destination] = "sent"
        if destination == "telegram":
            record["telegram_message_id"] = message_id
        elif destination == "bale":
            record["bale_message_id"] = message_id
        else:
            # Future channel adapters keep their own IDs under a neutral field;
            # new destinations never require changes to content discovery.
            record.setdefault("platform_message_ids", {})[destination] = message_id
        record.setdefault("delivery_attempts", {})[destination] = target["attempts"]
        record["delivery_last_attempt_at"] = _now().isoformat()
        _save(state)
        print(f"PLATFORM_DELIVERY_OK product_id={entry['product_id']} platform={destination} message_id={message_id}")
    except Exception as exc:
        _target_retry(entry, destination, _now(), f"{type(exc).__name__}: {str(exc)[:180]}")
        record_status[destination] = "failed"
        record.setdefault("delivery_attempts", {})[destination] = target["attempts"]
        record["delivery_last_attempt_at"] = _now().isoformat()
        _save(state)
        print(f"PLATFORM_DELIVERY_FAILED product_id={entry['product_id']} platform={destination} error={type(exc).__name__}")


def _process_video_destinations(state: dict, entry: dict, record: dict, now: datetime) -> None:
    product_id = str(entry.get("product_id") or "")
    for target_name in VIDEO_PLATFORMS:
        target = _target(entry, target_name)
        if target.get("status") == "sent":
            continue
        if not _target_ready(target_name):
            _set_target(entry, target_name, "not_connected", now, "credentials_not_configured")
            _save(state)
        elif target.get("status") == "not_connected":
            # A later-added platform becomes eligible without rerunning discovery.
            target["status"] = "pending"
            target.pop("last_error", None)
            _save(state)
    if any(_target(entry, name).get("status") in {"pending", "failed", "retry", "sending"} for name in VIDEO_PLATFORMS):
        try:
            # The same selected product is processed immediately. The video processor
            # bypasses only its normal cross-item time slot, not platform quotas or errors.
            radar.process_pending_short_video(
                state,
                now=now,
                destinations={"youtube", "aparat"},
                # Respect each video platform's own quota/cadence. The selected
                # content remains queued for that destination until its next slot.
                force_due=False,
                only_product_id=product_id,
            )
        except Exception as exc:
            print(f"VIDEO_DESTINATION_DISPATCH_FAILED product_id={product_id} error={type(exc).__name__}")
            record["video_delivery_last_error"] = type(exc).__name__
            _save(state)

    youtube_status = str(record.get("youtube_upload_status") or "pending")
    if youtube_status == "uploaded":
        _set_target(entry, "youtube", "sent", _now())
    elif not _target_ready("youtube"):
        _set_target(entry, "youtube", "not_connected", _now(), "credentials_not_configured")
    elif youtube_status == "upload_result_unknown":
        _set_target(entry, "youtube", "manual_review", _now(), str(record.get("youtube_last_error") or "upload_result_unknown"))
    elif youtube_status == "skipped_unverified_deadline":
        _target(entry, "youtube")["status"] = "pending"
        _target(entry, "youtube")["last_error"] = "waiting_for_verified_deadline"
    elif youtube_status in {"retry", "pending", "pending_credentials", "uploading"}:
        t = _target(entry, "youtube")
        t["status"] = "failed" if youtube_status == "retry" else "pending"
        t["last_error"] = str(record.get("youtube_last_error") or youtube_status)
        next_slot = (
            _utc(record.get("youtube_next_attempt_at"))
            or _utc(state.get("youtube_uploads_paused_until"))
            or _utc(state.get("youtube_next_upload_at"))
        )
        t["next_attempt_at"] = (
            next_slot if next_slot and next_slot > now else now + timedelta(minutes=15)
        ).isoformat()
    else:
        _target(entry, "youtube")["status"] = "pending"

    aparat_status = str(record.get("aparat_upload_status") or "pending")
    if aparat_status == "uploaded":
        _set_target(entry, "aparat", "sent", _now())
    elif not _target_ready("aparat"):
        _set_target(entry, "aparat", "not_connected", _now(), "credentials_not_configured")
    elif aparat_status == "upload_result_unknown":
        _set_target(entry, "aparat", "manual_review", _now(), str(record.get("aparat_last_error") or "upload_result_unknown"))
    elif aparat_status == "waiting_shorts_uploader":
        _set_target(entry, "aparat", "manual_review", _now(), "shorts_uploader_not_supported_by_current_path")
    elif aparat_status == "skipped_unverified_deadline":
        _target(entry, "aparat")["status"] = "pending"
        _target(entry, "aparat")["last_error"] = "waiting_for_verified_deadline"
    elif aparat_status in {"retry", "pending", "pending_credentials", "uploading"}:
        t = _target(entry, "aparat")
        t["status"] = "failed" if aparat_status == "retry" else "pending"
        t["last_error"] = str(record.get("aparat_last_error") or aparat_status)
        next_slot = _utc(record.get("aparat_next_attempt_at")) or _utc(state.get("aparat_next_upload_at"))
        t["next_attempt_at"] = (
            next_slot if next_slot and next_slot > now else now + timedelta(minutes=15)
        ).isoformat()
    else:
        _target(entry, "aparat")["status"] = "pending"
    _save(state)


def publish_due_queue() -> int:
    validate_registry()
    state = radar.load_state(apply_integrity_ledger=False)
    if apply_integrity_audit_ledger(state):
        _save(state)
        print("PUBLISHER_INTEGRITY_LEDGER_APPLIED")
    now = _now()
    evicted = enforce_queue_limit(state, now=now)
    if evicted:
        _save(state)
        print(f"PUBLISHER_RETRY_QUEUE_BOUNDED evicted={evicted}")
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict) or not queue:
        print("PUBLISHER_QUEUE_EMPTY")
        return 0
    due = due_content(state, now=now, limit=MAX_ITEMS_PER_RUN)
    if not due:
        print(f"PUBLISHER_NOTHING_DUE queue_size={len(queue)}")
        return 0

    sent_content = 0
    for product_id, entry in due:
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        delivery_id = f"{product_id}:{entry.get('selected_at') or entry.get('scheduled_at') or 'unknown'}"
        existing = state.get("published", {}).get(product_id)
        duplicate_reason = _duplicate_guard_reason(existing, delivery_id)
        if duplicate_reason:
            # A stale queue entry can survive after another run has already sent the
            # same product. Cancel it before any media/network side effects and preserve
            # the current public record; this is a last-line guard beyond discovery dedupe.
            entry["status"] = "cancelled"
            entry["last_detail"] = duplicate_reason
            finish_queue_item(state, product_id, "cancelled", now=now, detail=duplicate_reason)
            state.get("pending_queue", {}).pop(product_id, None)
            _save(state)
            print(f"CONTENT_DUPLICATE_BLOCKED product_id={product_id} reason={duplicate_reason}")
            continue
        entry["status"] = "publishing"
        entry["last_attempt_at"] = now.isoformat()
        try:
            entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
        except (TypeError, ValueError, OverflowError):
            entry["attempt_count"] = 1
        _save(state)

        fresh, reason = _fresh_selected_item(entry, now)
        if fresh is None:
            # A selected item that no longer matches its live price is removed
            # from the delivery queue and will re-enter only after fresh selection.
            if reason.startswith("selected_price_stale") or reason in {
                "live_product_details_incomplete", "live_stock_not_confirmed",
                "live_discount_no_longer_eligible", "live_market_value_rejected",
                "live_offer_expired_or_unverified", "insufficient_publication_runway",
            }:
                entry["status"] = "stale_selection"
                entry["last_detail"] = reason
                finish_queue_item(state, product_id, "stale_selection", now=now, detail=reason)
                state.get("pending_queue", {}).pop(product_id, None)
                _save(state)
                print(f"CONTENT_SELECTION_STALE product_id={product_id} reason={reason}")
                continue
            entry["status"] = "queued"
            entry["last_detail"] = reason
            entry["next_attempt_at"] = (now + timedelta(seconds=RETRY_BASE_SECONDS)).isoformat()
            for name in ("telegram", "bale", "youtube", "aparat"):
                target = _target(entry, name)
                if target.get("status") not in {"sent", "not_connected", "manual_review"}:
                    _target_retry(entry, name, now, reason)
            _save(state)
            print(f"CONTENT_REVALIDATION_DEFERRED product_id={product_id} reason={reason}")
            continue

        old = state.get("published", {}).get(product_id)
        if not isinstance(old, dict):
            old = {}
        record = _record_from_item(fresh, old, now, delivery_id)
        state.setdefault("published", {})[product_id] = record
        _save(state)

        try:
            image_bytes = radar._fetch_image(str(fresh.get("image_url") or ""))
        except Exception as exc:
            reason = f"image_fetch_{type(exc).__name__}"
            entry["status"] = "queued"
            entry["last_detail"] = reason
            entry["next_attempt_at"] = (now + timedelta(seconds=RETRY_BASE_SECONDS)).isoformat()
            _save(state)
            print(f"CONTENT_IMAGE_UNAVAILABLE product_id={product_id} error={type(exc).__name__}")
            continue

        prior_public_status = {
            name: str(_target(entry, name).get("status") or "pending")
            for name in PHOTO_PLATFORMS
        }
        for destination in PHOTO_PLATFORMS:
            _process_photo_destination(state, entry, record, fresh, image_bytes, destination, now)
        # Refresh mutable status after each adapter. This same record is the hand-off
        # to the public video publishers, not a second independent content selection.
        state.setdefault("published", {})[product_id] = record
        _save(state)
        _process_video_destinations(state, entry, record, now)

        platforms = {name: str(_target(entry, name).get("status") or "pending") for name in PLATFORM_NAMES}
        completed = all(status in TERMINAL_PLATFORM for status in platforms.values())
        any_success = any(status == "sent" for status in platforms.values())
        unresolved = [name for name, status in platforms.items() if status not in TERMINAL_PLATFORM]
        new_public_delivery = any(
            prior_public_status.get(name) != "sent" and platforms.get(name) == "sent"
            for name in PHOTO_PLATFORMS
        )
        if new_public_delivery:
            public_posted_at = _now().isoformat()
            state["last_channel_published_at"] = public_posted_at
            state["last_published_at"] = public_posted_at

        # Preserve the original post timestamp when retrying pending video platforms.
        # Destination updated_at is written only when that platform actually sends.
        existing_same_delivery = (
            isinstance(old, dict)
            and str(old.get("distribution_queue_id") or "") == delivery_id
        )
        if existing_same_delivery:
            sent_epochs = [
                dt.timestamp()
                for name in PHOTO_PLATFORMS
                if _target(entry, name).get("status") == "sent"
                and (dt := _utc(_target(entry, name).get("updated_at"))) is not None
            ]
            if sent_epochs:
                try:
                    previous_epoch = float(old.get("ts") or 0)
                except (TypeError, ValueError, OverflowError):
                    previous_epoch = 0
                first_channel_epoch = min(sent_epochs)
                record["ts"] = (
                    min(previous_epoch, first_channel_epoch)
                    if previous_epoch > 0 else first_channel_epoch
                )
        if completed:
            if any_success:
                record["delivery_status"] = {
                    name: ("sent" if status == "sent" else status)
                    for name, status in platforms.items()
                }
                state.get("pending_queue", {}).pop(product_id, None)
                finish_queue_item(state, product_id, "published", now=_now(), detail=",".join(f"{k}={v}" for k, v in platforms.items()))
                sent_content += 1
                print(f"CONTENT_DELIVERY_COMPLETE product_id={product_id} platforms={platforms}")
            else:
                finish_queue_item(state, product_id, "cancelled", now=_now(), detail="no_connected_platform_delivered")
                print(f"CONTENT_DELIVERY_CANCELLED product_id={product_id} platforms={platforms}")
        else:
            entry["status"] = "partial"
            retry_times = []
            for name in unresolved:
                t = _target(entry, name)
                retry_at = _utc(t.get("next_attempt_at"))
                if retry_at:
                    retry_times.append(retry_at)
                elif t.get("status") in {"pending", "failed", "retry"}:
                    retry_times.append(now + timedelta(minutes=15))
            entry["next_attempt_at"] = (min(retry_times) if retry_times else now + timedelta(minutes=15)).isoformat()
            entry["last_detail"] = "unresolved=" + ",".join(unresolved)
            if any_success:
                state.get("pending_queue", {}).pop(product_id, None)
            print(f"CONTENT_DELIVERY_PARTIAL product_id={product_id} platforms={platforms} retry_at={entry['next_attempt_at']}")
        _save(state)

    print(f"PUBLISHER_RUN_SUMMARY due={len(due)} completed={sent_content} remaining={sum(1 for x in state.get('content_delivery_queue', {}).values() if isinstance(x, dict))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(publish_due_queue())
    except Exception as exc:
        print(f"PUBLISHER_RUN_FAILED error={type(exc).__name__}: {str(exc)[:240]}")
        raise
