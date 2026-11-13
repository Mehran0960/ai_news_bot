"""Event-driven editorial fallback publisher.

Editorial content uses the shared publication sequence but never enters the SKU/price
product pipeline. Live network actions require the explicit --publish flag.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

import affilio_radar as radar
from content_delivery import (
    allocate_publication_sequence,
    get_last_channel_published_at,
    refresh_unpublished_selections,
)
from editorial_content import record_editorial_delivery, select_editorial_fallback
from platform_registry import PLATFORM_NAMES

ROOT = Path(__file__).resolve().parent
EDITORIAL_BANK = ROOT / "editorial_bank.json"
CHANNEL_DESTINATIONS = ("telegram", "bale", "rubika", "eitaa")
VIDEO_DESTINATIONS = ("youtube", "aparat", "filo")
TERMINAL = {"sent", "not_connected", "manual_review", "skipped_limit"}
RETRYABLE = {"pending", "failed", "retry"}
PRODUCTS_PER_EDITORIAL = max(1, min(20, int(os.getenv("OFFERCHIN_EDITORIAL_PRODUCTS_PER_POST", "4"))))
MINIMUM_GAP_MINUTES = max(
    27,
    min(59, int(os.getenv(
        "OFFERCHIN_EDITORIAL_CHANNEL_GAP_MINUTES",
        str(round(float(radar.MIN_POST_INTERVAL_HOURS) * 60)),
    ))),
)
EDITORIAL_ATTEMPT_COOLDOWN_MINUTES = max(
    50, min(59, int(os.getenv("OFFERCHIN_EDITORIAL_GAP_MINUTES", "55")))
)
RETRY_BASE_SECONDS = max(60, min(1800, int(os.getenv("OFFERCHIN_EDITORIAL_RETRY_SECONDS", "300"))))
MAX_ATTEMPTS = max(1, min(5, int(os.getenv("OFFERCHIN_EDITORIAL_MAX_ATTEMPTS", "3"))))


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


def _load_bank() -> list[dict]:
    try:
        value = json.loads(EDITORIAL_BANK.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"editorial_bank_unavailable:{type(exc).__name__}") from exc
    if not isinstance(value, list):
        raise RuntimeError("editorial_bank_must_be_a_list")
    return value


def _active_editorial_entries(state: dict) -> list[dict]:
    queue = state.get("editorial_delivery_queue")
    if not isinstance(queue, dict):
        return []
    rows = [
        row for row in queue.values()
        if isinstance(row, dict) and row.get("status") not in {"completed", "cancelled", "failed"}
    ]
    return sorted(rows, key=lambda row: int(row.get("sequence_number") or 0))


def _pending_product_video_exists(
    state: dict,
    *,
    before_sequence_number: int | None = None,
) -> bool:
    """Check only product videos that precede a given editorial FIFO sequence."""
    published = state.get("published")
    if not isinstance(published, dict):
        return False
    checker = getattr(radar, "_has_pending_video_destination", None)
    if not callable(checker):
        return False
    for row in published.values():
        if not isinstance(row, dict) or not checker(row):
            continue
        if before_sequence_number is None:
            return True
        try:
            product_sequence = int(row.get("sequence_number") or 0)
        except (TypeError, ValueError, OverflowError):
            product_sequence = 0
        # Missing legacy sequence numbers are conservatively treated as older.
        if product_sequence <= 0 or product_sequence < before_sequence_number:
            return True
    return False


def _recent_attempt_anchor(state: dict) -> datetime | None:
    """Return the last editorial attempt/success, excluding ordinary product posts."""
    candidates = [
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


def queue_editorial_if_due(
    state: dict,
    bank: list[dict],
    *,
    now: datetime | None = None,
) -> dict | None:
    """Reuse the active editorial item or allocate a new one after product FIFO is clear."""
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    active = _active_editorial_entries(state)
    if active:
        return active[0]

    # Old, never-delivered product selections are retired after the same short
    # reservation window used by the product delivery contract.
    refresh_unpublished_selections(state, now=current, stale_after_minutes=8)
    product_queue = state.get("content_delivery_queue")
    if isinstance(product_queue, dict) and any(
        isinstance(row, dict) and row.get("status") not in {"published", "cancelled", "stale_selection"}
        for row in product_queue.values()
    ):
        print("EDITORIAL_FALLBACK_WAIT reason=product_photo_fifo_not_terminal")
        return None
    # Product videos may still be pending, but that must not reserve a photo-channel
    # slot. The editorial's later video pass independently waits for older sequences.

    try:
        product_posts_since_editorial = max(
            0, int(state.get("product_channel_posts_since_editorial") or 0)
        )
    except (TypeError, ValueError, OverflowError):
        product_posts_since_editorial = 0
    if product_posts_since_editorial < PRODUCTS_PER_EDITORIAL:
        print(
            "EDITORIAL_FALLBACK_WAIT reason=product_post_quota "
            f"observed={product_posts_since_editorial} required={PRODUCTS_PER_EDITORIAL}"
        )
        return None

    channel_anchor = get_last_channel_published_at(state)
    if channel_anchor and current - channel_anchor < timedelta(minutes=MINIMUM_GAP_MINUTES):
        remaining = max(
            0,
            int((
                timedelta(minutes=MINIMUM_GAP_MINUTES) - (current - channel_anchor)
            ).total_seconds()),
        )
        print(f"EDITORIAL_FALLBACK_NOT_DUE reason=minimum_channel_spacing remaining_seconds={remaining}")
        return None

    attempt_anchor = _recent_attempt_anchor(state)
    if attempt_anchor and current - attempt_anchor < timedelta(minutes=EDITORIAL_ATTEMPT_COOLDOWN_MINUTES):
        remaining = max(
            0,
            int((
                timedelta(minutes=EDITORIAL_ATTEMPT_COOLDOWN_MINUTES) - (current - attempt_anchor)
            ).total_seconds()),
        )
        print(f"EDITORIAL_FALLBACK_NOT_DUE reason=editorial_attempt_cooldown remaining_seconds={remaining}")
        return None

    item = select_editorial_fallback(bank, state, now=current)
    if not item:
        state["last_editorial_empty_bank_check_at"] = current.isoformat()
        print("EDITORIAL_FALLBACK_EMPTY reason=no_valid_nonrepeating_reviewed_item")
        return None

    sequence_number = allocate_publication_sequence(state)
    item["sequence_number"] = sequence_number
    queue = state.setdefault("editorial_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["editorial_delivery_queue"] = queue
    entry = {
        "content_id": item["content_id"],
        "content_type": "editorial",
        "sequence_number": sequence_number,
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
    }
    queue[item["content_id"]] = entry
    state["last_editorial_attempt_at"] = current.isoformat()
    print(f"EDITORIAL_FALLBACK_QUEUED content_id={item['content_id']} sequence={sequence_number}")
    return entry


def _format_message(item: dict) -> str:
    lines = [
        "🧭 راهنمای کاربردی آفِرچین",
        "",
        str(item.get("title") or "").strip(),
        "",
        str(item.get("body") or "").strip(),
        "",
        "منابع:",
    ]
    for source in item.get("sources") or []:
        if isinstance(source, dict):
            title = str(source.get("title") or "منبع")
            url = str(source.get("url") or "")
            if url.startswith("https://"):
                lines.append(f"• {title}: {url}")
    lines.extend(["", "آفِرچین | t.me/OfferChin"])
    message = "\n".join(lines)
    return message[:3900]


def _send_bot_message(platform: str, message: str) -> dict:
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
    response = requests.post(
        endpoint,
        data={"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"},
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
    if destination in {"telegram", "bale"}:
        state["last_channel_published_at"] = now.isoformat()
        state["last_published_at"] = now.isoformat()
        state["last_editorial_channel_published_at"] = now.isoformat()
        state["product_channel_posts_since_editorial"] = 0
    state["last_editorial_confirmed_at"] = now.isoformat()
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    try:
        record_editorial_delivery(
            state, payload, published_at=now,
            destinations=entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {},
        )
    except ValueError:
        pass
    history = state.get("editorial_delivery_history")
    if isinstance(history, list):
        for row in reversed(history):
            if isinstance(row, dict) and row.get("content_id") == entry.get("content_id"):
                row["destinations"] = entry.get("platforms", {})
                row["sequence_number"] = entry.get("sequence_number")
                break


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
    state: dict, entry: dict, destination: str, image_bytes: bytes, message: str, now: datetime
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
            _save(state)
        return
    if target.get("status") in TERMINAL:
        return
    if target.get("status") == "sending":
        target["status"] = "manual_review"
        target["last_error"] = "interrupted_during_send_outcome_unknown"
        target["updated_at"] = now.isoformat()
        _save(state)
        return
    if target.get("status") in {"failed", "retry"}:
        # A delayed editorial retry could appear after a newer product on this
        # destination. Terminalize the unconfirmed editorial attempt instead.
        target["status"] = "manual_review"
        target["last_error"] = "editorial_retry_suppressed_to_preserve_destination_fifo"
        target["updated_at"] = now.isoformat()
        _save(state)
        return

    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    target["attempts"] = int(target.get("attempts") or 0) + 1
    entry["status"] = "publishing"
    _save(state)
    try:
        if destination in {"telegram", "bale"}:
            receipt = _send_bot_message(destination, message)
        elif destination == "rubika":
            receipt = _send_rubika_image(image_bytes, message)
        else:
            receipt = _send_eitaa_image(image_bytes, message)
        confirmed = bool(receipt.get("message_id"))
        if receipt.get("api_accepted") and not receipt.get("message_id"):
            target["status"] = "manual_review"
            target["last_error"] = "api_accepted_without_public_message_id_unverified"
            target["updated_at"] = _now().isoformat()
            _save(state)
            print(
                f"EDITORIAL_DESTINATION_UNVERIFIED content_id={entry['content_id']} "
                f"platform={destination} reason=api_accepted_without_public_message_id"
            )
            return
        if not confirmed:
            raise RuntimeError("destination_receipt_missing")
        _record_success(state, entry, destination, receipt, _now())
        _save(state)
        print(f"EDITORIAL_DESTINATION_SENT content_id={entry['content_id']} platform={destination}")
    except Exception as exc:
        _record_failure(entry, destination, exc, _now())
        if target.get("status") == "failed":
            target["status"] = "manual_review"
            target["last_error"] = (
                "editorial_delivery_not_confirmed_no_late_retry:"
                + str(target.get("last_error") or type(exc).__name__)
            )[:300]
            target["updated_at"] = _now().isoformat()
        _save(state)
        print(
            f"EDITORIAL_DESTINATION_FAILED content_id={entry['content_id']} "
            f"platform={destination} error={type(exc).__name__} detail={_safe_error(exc)}"
        )


def _video_description(item: dict) -> str:
    parts = [str(item.get("body") or "").strip(), "", "منابع:"]
    for source in item.get("sources") or []:
        if isinstance(source, dict) and str(source.get("url") or "").startswith("https://"):
            parts.append(f"{source.get('title')}: {source.get('url')}")
    parts.extend(["", "t.me/OfferChin", "ble.ir/OfferChin"])
    return "\n".join(parts)[:2900]


def _handle_video_destination(
    state: dict, entry: dict, destination: str, video_path: Path, now: datetime
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
    if target.get("status") in {"failed", "retry"}:
        # Preserve destination FIFO: never retry this editorial after a newer
        # product-video dispatch may have started.
        target["status"] = "manual_review"
        target["last_error"] = "editorial_video_retry_suppressed_to_preserve_destination_fifo"
        target["updated_at"] = now.isoformat()
        _save(state)
        return

    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    target["attempts"] = int(target.get("attempts") or 0) + 1
    entry["status"] = "publishing"
    _save(state)
    item = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    title = "راهنمای آفِرچین: " + str(item.get("title") or "")
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
            target["status"] = "skipped_limit"
            target["last_error"] = "youtube_daily_quota_exceeded"
            state["youtube_uploads_paused_until"] = radar._next_youtube_daily_upload_retry_at(_now()).isoformat()
            state["youtube_upload_pause_reason"] = "daily_upload_limit"
            target["updated_at"] = _now().isoformat()
        else:
            _record_failure(entry, destination, exc, _now())
            if target.get("status") == "failed":
                target["status"] = "manual_review"
                target["last_error"] = (
                    "editorial_video_not_confirmed_no_late_retry:"
                    + str(target.get("last_error") or type(exc).__name__)
                )[:300]
                target["updated_at"] = _now().isoformat()
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


def _finalize_if_terminal(state: dict, entry: dict, now: datetime) -> bool:
    targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
    if not all(
        isinstance(targets.get(name), dict) and targets[name].get("status") in TERMINAL
        for name in PLATFORM_NAMES
    ):
        entry["status"] = "partial"
        return False
    # A manual-review result is ambiguous for FIFO: the destination may have
    # accepted the content even though public delivery was not confirmed. Keep the
    # canonical sequence alive until a human resolves that destination.
    if any(
        targets[name].get("status") == "manual_review"
        for name in PLATFORM_NAMES
    ):
        entry["status"] = "manual_review"
        entry["updated_at"] = now.isoformat()
        entry["terminal_summary"] = {
            name: targets[name].get("status") for name in PLATFORM_NAMES
        }
        return False
    success = any(targets[name].get("status") == "sent" for name in PLATFORM_NAMES)
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
    attempt_anchor = _recent_attempt_anchor(shadow_state_for_anchor)
    attempt_elapsed = (current - attempt_anchor) if attempt_anchor else None
    attempt_remaining = (
        max(
            0,
            int((
                timedelta(minutes=EDITORIAL_ATTEMPT_COOLDOWN_MINUTES) - attempt_elapsed
            ).total_seconds()),
        )
        if attempt_elapsed is not None
        and attempt_elapsed < timedelta(minutes=EDITORIAL_ATTEMPT_COOLDOWN_MINUTES)
        else 0
    )
    channel_anchor = get_last_channel_published_at(shadow_state_for_anchor)
    channel_elapsed = (current - channel_anchor) if channel_anchor else None
    channel_remaining = (
        max(
            0,
            int((timedelta(minutes=MINIMUM_GAP_MINUTES) - channel_elapsed).total_seconds()),
        )
        if channel_elapsed is not None and channel_elapsed < timedelta(minutes=MINIMUM_GAP_MINUTES)
        else 0
    )
    remaining = max(attempt_remaining, channel_remaining)
    try:
        product_posts_since_editorial = max(
            0, int(state.get("product_channel_posts_since_editorial") or 0)
        )
    except (TypeError, ValueError, OverflowError):
        product_posts_since_editorial = 0
    products_until_editorial = max(0, PRODUCTS_PER_EDITORIAL - product_posts_since_editorial)

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
    elif products_until_editorial:
        decision = "wait_for_product_post_quota"
        item_id = None
        sequence = None
    elif remaining:
        decision = (
            "wait_for_minimum_channel_spacing"
            if channel_remaining else "wait_for_editorial_attempt_cooldown"
        )
        item_id = None
        sequence = None
    else:
        # Simulate enqueue against a JSON copy only. The live state and queue are read-only.
        shadow_state = json.loads(json.dumps(state, ensure_ascii=False, default=str))
        candidate = select_editorial_fallback(bank, shadow_state, now=current)
        if candidate is None:
            decision = "no_valid_nonrepeating_reviewed_item"
            item_id = None
            sequence = None
        else:
            sequence = allocate_publication_sequence(shadow_state)
            decision = "would_queue_editorial"
            item_id = str(candidate.get("content_id") or "")

    return {
        "observed_at": current.astimezone(timezone.utc).isoformat(),
        "mode": "shadow_read_only",
        "public_publish_performed": False,
        "decision": decision,
        "would_select_content_id": item_id,
        "would_allocate_sequence_number": sequence,
        "fallback_interval_minutes": MINIMUM_GAP_MINUTES,
        "editorial_attempt_cooldown_minutes": EDITORIAL_ATTEMPT_COOLDOWN_MINUTES,
        "products_per_editorial": PRODUCTS_PER_EDITORIAL,
        "product_channel_posts_since_editorial": product_posts_since_editorial,
        "product_posts_until_editorial_due": products_until_editorial,
        "seconds_until_fallback_due": remaining,
        "editorial_bank_total": len(bank),
        "editorial_bank_valid": len(valid_items),
        "editorial_bank_invalid": invalid_items,
        "active_editorial_queue_items": len(active),
        "active_product_photo_queue_items": len(active_products),
        "older_product_video_pending_before_next_editorial": bool(pending_videos),
        "editorial_video_waits_for_older_product_video_fifo": True,
        "destination_credentials_present": destination_config,
        "platform_quota_and_upload_health_probed": False,
        "state_mutated": False,
        "limitations": [
            "Credentials are checked locally only; no destination API is contacted.",
            "This is not proof of a public post or of destination availability.",
            "A 24-hour run must be reviewed before enabling public editorial publishing.",
        ],
    }


def run_editorial_publisher(
    *,
    mode: str,
    publish: bool,
    now: datetime | None = None,
    resume_active_only: bool = False,
) -> int:
    if mode not in {"channels", "videos"}:
        raise ValueError("mode_must_be_channels_or_videos")
    current = now or _now()
    state = radar.load_state(apply_integrity_ledger=False)
    bank = _load_bank()
    if resume_active_only:
        active = _active_editorial_entries(state)
        entry = active[0] if active else None
    else:
        entry = queue_editorial_if_due(state, bank, now=current)
    if publish:
        # Persist the canonical id and allocated sequence before rendering or any
        # outbound request, so a runner restart cannot allocate a duplicate sequence.
        _save(state)
    if not entry:
        if publish:
            _save(state)
        return 0
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    if not publish:
        print(
            f"EDITORIAL_DRY_RUN mode={mode} content_id={entry.get('content_id')} "
            f"sequence={entry.get('sequence_number')} destinations={','.join(PLATFORM_NAMES)}"
        )
        return 0

    if mode == "channels":
        try:
            from editorial_video import render_editorial_poster
            image_bytes = render_editorial_poster(payload)
        except Exception as exc:
            print(f"EDITORIAL_POSTER_RENDER_FAILED error={type(exc).__name__}")
            return 1
        message = _format_message(payload)
        for destination in CHANNEL_DESTINATIONS:
            _handle_channel_destination(state, entry, destination, image_bytes, message, _now())
    else:
        # Keep all older product videos ahead of a newer editorial video.
        try:
            editorial_sequence = int(entry.get("sequence_number") or 0)
        except (TypeError, ValueError, OverflowError):
            editorial_sequence = 0
        if _pending_product_video_exists(
            state, before_sequence_number=editorial_sequence or None
        ):
            print("EDITORIAL_VIDEO_WAIT reason=older_product_video_fifo_pending")
            _save(state)
            return 0
        output_path = Path("video_artifacts") / (
            f"editorial-{payload.get('editorial_id')}-{entry.get('sequence_number')}.mp4"
        )
        try:
            from editorial_video import render_editorial_video
            if any(
                _target(entry, name).get("status") not in TERMINAL
                for name in VIDEO_DESTINATIONS
            ):
                render_editorial_video(payload, output_path)
        except Exception as exc:
            for destination in VIDEO_DESTINATIONS:
                target = _target(entry, destination)
                if target.get("status") not in TERMINAL:
                    target["status"] = "manual_review"
                    target["last_error"] = f"editorial_video_render_failed:{type(exc).__name__}"
            _save(state)
            return 1
        for destination in VIDEO_DESTINATIONS:
            _handle_video_destination(state, entry, destination, output_path, _now())

    now_after = _now()
    _refresh_delivery_history(state, entry, now_after)
    finalized = _finalize_if_terminal(state, entry, now_after)
    if finalized:
        print(
            f"EDITORIAL_DELIVERY_TERMINAL content_id={entry.get('content_id')} "
            f"status={entry.get('status')} sequence={entry.get('sequence_number')}"
        )
    _save(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OfferChin editorial fallback delivery")
    parser.add_argument("--channels-only", action="store_true")
    parser.add_argument("--videos-only", action="store_true")
    parser.add_argument("--publish", action="store_true", help="perform external publishing; otherwise dry-run only")
    parser.add_argument(
        "--resume-active-only",
        action="store_true",
        help="resume an existing editorial item without allocating a new sequence",
    )
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
        resume_active_only=args.resume_active_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
