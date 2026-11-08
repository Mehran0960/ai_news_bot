"""Opt-in delivery adapters for additional Iranian messengers."""
from __future__ import annotations
import os
import re
from typing import Any
from urllib.parse import urlsplit
import requests

try:
    from .offerchin_copy import MEMBERSHIP_BUTTON_TEXT, purchase_action_label
except ImportError:
    from offerchin_copy import MEMBERSHIP_BUTTON_TEXT, purchase_action_label

RUBIKA_API = "https://botapi.rubika.ir/v3"
EITAA_API = "https://eitaayar.ir/api"
REQUEST_TIMEOUT = (15, 90)
MAX_IMAGE_BYTES = 10_000_000
RUBIKA_CHANNEL_URL = "https://rubika.ir/offerchin"
RUBIKA_MEMBERSHIP_BUTTON_TEXT = MEMBERSHIP_BUTTON_TEXT
EITAA_CHANNEL_URL = os.getenv("EITAA_CHANNEL_URL", "").strip()


def _response_json(response: Any, label: str) -> dict:
    try:
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError:
        status = getattr(response, "status_code", "unknown")
        raise RuntimeError(f"{label}: HTTP {status}") from None
    except requests.RequestException:
        raise RuntimeError(f"{label}: network failure") from None
    except ValueError:
        raise RuntimeError(f"{label}: invalid JSON response") from None
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}: unexpected response shape")
    return payload


def _safe_rubika_error_detail(payload: dict) -> str:
    """Return a bounded API error summary without URLs, tokens, or raw payloads."""
    details: list[str] = []
    for key in ("error_code", "code"):
        value = payload.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            details.append(f"{key}={str(value).strip()[:32]}")

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("code", "error_code"):
            value = error.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                details.append(f"error_{key}={str(value).strip()[:32]}")
        for key in ("message", "description"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                details.append(value.strip())
    elif isinstance(error, str) and error.strip():
        details.append(error.strip())

    for key in ("message", "description", "error_description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            details.append(value.strip())

    detail = " | ".join(details)
    detail = re.sub(r"(?i)https?://\S+", "[redacted-url]", detail)
    detail = re.sub(r"(?i)\b(token|authorization|secret)\b\s*[:=]\s*\S+", r"\1=[redacted]", detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    return detail[:150]


def _rubika_data(payload: dict, label: str) -> dict:
    status = str(payload.get("status") or "").upper()
    if status not in {"OK", "SUCCESS"}:
        detail = _safe_rubika_error_detail(payload)
        suffix = f"; {detail}" if detail else ""
        raise RuntimeError(f"Rubika {label} rejected the request (status={status or 'unknown'}{suffix})")
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload.get("result")
    if not isinstance(data, dict):
        raise RuntimeError(f"Rubika {label} returned no data object")
    return data


def _rubika_call(token: str, method: str, data: dict | None = None) -> dict:
    if not token:
        raise RuntimeError("Rubika bot token is not configured")
    try:
        response = requests.post(
            f"{RUBIKA_API}/{token}/{method}", json=data or {}, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException:
        raise RuntimeError(f"Rubika {method}: network failure") from None
    return _rubika_data(_response_json(response, f"Rubika {method}"), method)


def _valid_affiliate_url(renderer: Any, affiliate_url: str) -> bool:
    validator = getattr(renderer, "_is_valid_affilio_tracking_url", None)
    return bool(callable(validator) and validator(str(affiliate_url or "").strip()))


def _validated_eitaa_channel_url() -> str:
    """Accept only a configured HTTPS public Eitaa channel URL; never invent one."""
    value = str(EITAA_CHANNEL_URL or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return value


def _caption(renderer: Any, item: dict, affiliate_url: str, channel: str) -> str:
    if channel == "rubika":
        # Keep the shared caption body. Rubika's membership action is rendered in
        # the same inline keypad as the purchase action because its text field is plain.
        caption = renderer.build_caption(
            item, affiliate_url, channel_label=RUBIKA_CHANNEL_URL,
            use_unicode_strikethrough=True,
        )
        caption = re.sub(r"\[([^\]]+)\]\([^)]+\)", "", caption).rstrip()
        caption = re.sub(r"\\([\\_*()\[\]])", r"\1", caption)
        caption = caption.replace("*", "")
        return caption[:3800]

    if channel != "eitaa":
        raise ValueError(f"Unsupported caption channel: {channel}")

    eitaa_channel_url = _validated_eitaa_channel_url()
    # EitaaYar currently gets a plain caption. A real public channel URL is optional;
    # if configured, it is emitted as a bare HTTPS URL so the client can linkify it.
    caption = renderer.build_caption(
        item, affiliate_url,
        channel_label=eitaa_channel_url or "https://eitaa.com",
        use_unicode_strikethrough=True,
    )

    def plain_link(match: re.Match) -> str:
        label = match.group(1)
        if label == MEMBERSHIP_BUTTON_TEXT:
            return f"{label}\n{eitaa_channel_url}" if eitaa_channel_url else ""
        return label

    caption = re.sub(r"\[([^\]]+)\]\([^)]+\)", plain_link, caption)
    caption = re.sub(r"\\([\\_*()\[\]])", r"\1", caption)
    caption = caption.replace("*", "")
    label_builder = getattr(renderer, "purchase_button_label", None)
    purchase_label = (
        str(label_builder(affiliate_url))
        if callable(label_builder)
        else purchase_action_label(item.get("merchant") or "دیجی‌کالا")
    )
    # Eitaa's file adapter has no verified inline-URL-button contract. Keep the
    # exact purchase-action wording, followed by the verified, auto-linkable URL.
    return (caption.rstrip() + f"\n\n{purchase_label}\n{affiliate_url}")[:3800]


def _rubika_inline_keypad(renderer: Any, item: dict, affiliate_url: str) -> dict:
    """Attach direct purchase and channel-membership URL buttons to the same photo post."""
    label_builder = getattr(renderer, "purchase_button_label", None)
    if callable(label_builder):
        purchase_label = str(label_builder(affiliate_url))
    else:
        purchase_label = purchase_action_label(item.get("merchant") or "دیجی‌کالا")
    return {
        "rows": [
            {
                "buttons": [{
                    "id": "offerchin_buy_product",
                    "type": "Link",
                    "button_text": purchase_label,
                    "button_link": {
                        "type": "url",
                        "link_url": affiliate_url,
                    },
                }],
            },
            {
                "buttons": [{
                    "id": "offerchin_join_rubika",
                    "type": "Link",
                    "button_text": RUBIKA_MEMBERSHIP_BUTTON_TEXT,
                    "button_link": {
                        "type": "url",
                        "link_url": RUBIKA_CHANNEL_URL,
                    },
                }],
            },
        ],
    }


def _render(renderer: Any, item: dict, image_bytes: bytes, channel: str) -> bytes:
    # Rubika now appears in the shared cross-channel link list on every product card.
    # Keep the Eitaa brand label only until a public Eitaa channel URL is configured.
    extra_watermarks = [("eitaa", "ایتا | آفِرچین")] if channel == "eitaa" else None
    return renderer.build_discount_image(
        image_bytes, item.get("discount_percent"),
        merchant=item.get("merchant") or "دیجی‌کالا",
        extra_watermarks=extra_watermarks,
        destination_platform=channel,
    )


def send_rubika_photo(token: str, channel_id: str, item: dict, image_bytes: bytes,
                      affiliate_url: str, renderer: Any) -> dict:
    if not token or not channel_id:
        raise RuntimeError("Rubika token/channel are not configured")
    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("Rubika image is empty or exceeds the 10 MB safety limit")
    if not _valid_affiliate_url(renderer, affiliate_url):
        raise RuntimeError("Refusing Rubika publication without a verified affiliate URL")

    photo = _render(renderer, item, image_bytes, "rubika")
    upload_info = _rubika_call(token, "requestSendFile", {"type": "Image"})
    upload_url = str(upload_info.get("upload_url") or "").strip()
    parsed = urlsplit(upload_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError("Rubika returned an invalid upload URL")
    try:
        upload_response = requests.post(
            upload_url, files={"file": ("offerchin.jpg", photo, "image/jpeg")},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise RuntimeError("Rubika image upload: network failure") from None
    upload_payload = _response_json(upload_response, "Rubika image upload")
    upload_status = str(upload_payload.get("status") or "").upper()
    if upload_status and upload_status not in {"OK", "SUCCESS"}:
        _rubika_data(upload_payload, "image upload")
    upload_data = upload_payload.get("data")
    if not isinstance(upload_data, dict):
        upload_data = upload_payload
    file_id = str(upload_data.get("file_id") or "").strip()
    if not file_id:
        raise RuntimeError("Rubika image upload returned no file_id")

    send_payload = {
        "chat_id": channel_id,
        "file_id": file_id,
        "text": _caption(renderer, item, affiliate_url, "rubika"),
        "inline_keypad": _rubika_inline_keypad(renderer, item, affiliate_url),
    }
    try:
        sent = _rubika_call(token, "sendFile", send_payload)
    except RuntimeError as exc:
        # An explicit INVALID_INPUT response means Rubika rejected the request;
        # no message was accepted, so one conservative retry without the optional
        # keypad cannot duplicate a public post. Network/unknown failures are never retried.
        if "INVALID_INPUT" not in str(exc).upper():
            raise
        label_builder = getattr(renderer, "purchase_button_label", None)
        purchase_label = (
            str(label_builder(affiliate_url))
            if callable(label_builder)
            else purchase_action_label(item.get("merchant") or "دیجی‌کالا")
        )
        link_footer = (
            f"\n\n{purchase_label}\n{affiliate_url}"
            f"\n\n{RUBIKA_MEMBERSHIP_BUTTON_TEXT}\n{RUBIKA_CHANNEL_URL}"
        )
        plain_caption = _caption(renderer, item, affiliate_url, "rubika").rstrip()
        plain_caption = plain_caption[: max(0, 3800 - len(link_footer))] + link_footer
        print("RUBIKA_INLINE_KEYPAD_REJECTED fallback=plain_caption_links")
        sent = _rubika_call(token, "sendFile", {
            "chat_id": channel_id,
            "file_id": file_id,
            "text": plain_caption,
        })
    message_id = str(sent.get("message_id") or "").strip()
    if not message_id:
        raise RuntimeError("Rubika sendFile returned no message_id")
    return {"message_id": message_id}


def send_eitaa_photo(token: str, channel_id: str, item: dict, image_bytes: bytes,
                     affiliate_url: str, renderer: Any) -> dict:
    """EitaaYar sendFile; caller must enforce explicit opt-in."""
    if not token or not channel_id:
        raise RuntimeError("Eitaa token/channel are not configured")
    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("Eitaa image is empty or exceeds the 10 MB safety limit")
    if not _valid_affiliate_url(renderer, affiliate_url):
        raise RuntimeError("Refusing Eitaa publication without a verified affiliate URL")

    photo = _render(renderer, item, image_bytes, "eitaa")
    try:
        response = requests.post(
            f"{EITAA_API}/{token}/sendFile",
            data={
                "chat_id": channel_id,
                "caption": _caption(renderer, item, affiliate_url, "eitaa"),
                "title": "پیشنهاد آفِرچین",
            },
            files={"file": ("offerchin.jpg", photo, "image/jpeg")},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise RuntimeError("EitaaYar sendFile: network failure") from None
    payload = _response_json(response, "EitaaYar sendFile")
    result = payload.get("result")
    accepted = (
        payload.get("ok") is True
        or str(payload.get("status") or "").lower() == "success"
        or (isinstance(result, str) and result.lower() == "success")
    )
    if not accepted:
        raise RuntimeError("EitaaYar sendFile did not confirm acceptance")
    message_id = ""
    if isinstance(result, dict):
        message_id = str(result.get("message_id") or result.get("id") or "").strip()
    if not message_id and isinstance(payload.get("data"), dict):
        message_id = str(payload["data"].get("message_id") or payload["data"].get("id") or "").strip()
    return {"message_id": message_id} if message_id else {"delivery_receipt": "eitaayar-api-accepted"}


def send_photo(platform: str, item: dict, image_bytes: bytes,
               affiliate_url: str, renderer: Any) -> dict:
    if platform == "rubika":
        return send_rubika_photo(
            os.getenv("RUBIKA_BOT_TOKEN", "").strip(),
            os.getenv("RUBIKA_CHANNEL_ID", "").strip(),
            item, image_bytes, affiliate_url, renderer,
        )
    if platform == "eitaa":
        return send_eitaa_photo(
            os.getenv("EITAA_BOT_TOKEN", "").strip(),
            os.getenv("EITAA_CHANNEL_ID", "").strip(),
            item, image_bytes, affiliate_url, renderer,
        )
    raise ValueError(f"Unsupported messenger adapter: {platform}")
