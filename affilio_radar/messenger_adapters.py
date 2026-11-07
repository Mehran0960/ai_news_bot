"""Opt-in delivery adapters for additional Iranian messengers."""
from __future__ import annotations
import os
import re
from typing import Any
from urllib.parse import urlsplit
import requests

RUBIKA_API = "https://botapi.rubika.ir/v3"
EITAA_API = "https://eitaayar.ir/api"
REQUEST_TIMEOUT = (15, 90)
MAX_IMAGE_BYTES = 10_000_000


def _response_json(response: Any, label: str) -> dict:
    try:
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        raise RuntimeError(f"{label}: network or HTTP failure") from None
    except ValueError:
        raise RuntimeError(f"{label}: invalid JSON response") from None
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}: unexpected response shape")
    return payload


def _rubika_data(payload: dict, label: str) -> dict:
    if str(payload.get("status") or "").upper() not in {"OK", "SUCCESS"}:
        raise RuntimeError(f"Rubika {label} rejected the request")
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


def _caption(renderer: Any, item: dict, affiliate_url: str, channel: str) -> str:
    host = "rubika.ir" if channel == "rubika" else "eitaa.com"
    platform_name = "روبیکا" if channel == "rubika" else "ایتا"
    caption = renderer.build_caption(
        item, affiliate_url, channel_label=f"https://{host}",
        use_unicode_strikethrough=True,
    )
    caption = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        lambda match: f"{match.group(1)} در {platform_name}",
        caption,
    )
    return (caption + f"\n\n🛍️ مشاهده و خرید:\n{affiliate_url}")[:3800]


def _render(renderer: Any, item: dict, image_bytes: bytes, channel: str) -> bytes:
    mark = ("rubika", "روبیکا | آفِرچین") if channel == "rubika" else ("eitaa", "ایتا | آفِرچین")
    return renderer.build_discount_image(
        image_bytes, item.get("discount_percent"),
        merchant=item.get("merchant") or "دیجی‌کالا",
        extra_watermarks=[mark],
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
    upload_data = upload_payload.get("data")
    if not isinstance(upload_data, dict):
        upload_data = upload_payload
    file_id = str(upload_data.get("file_id") or "").strip()
    if not file_id:
        raise RuntimeError("Rubika image upload returned no file_id")

    sent = _rubika_call(token, "sendFile", {
        "chat_id": channel_id,
        "file_id": file_id,
        "text": _caption(renderer, item, affiliate_url, "rubika"),
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
