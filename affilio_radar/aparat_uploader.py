#!/usr/bin/env python3
"""Best-effort Aparat uploader using the authenticated web session cookie.

Aparat does not publish a stable public upload API for this workflow. This module
uses the site's current web upload endpoints and keeps TLS verification enabled.
Because those endpoints are undocumented, the uploader must be treated as a
best-effort integration and tested with a non-public upload before public mode.
"""
from __future__ import annotations

import mimetypes
import os
import json
import uuid
from pathlib import Path
from typing import Mapping
from urllib.parse import urljoin, urlsplit

import requests

APARAT_ORIGIN = "https://www.aparat.com"
APARAT_UPLOAD_CONFIG_URL = f"{APARAT_ORIGIN}/api/fa/v1/video/upload/upload_config"
APARAT_UPLOAD_URL = f"{APARAT_ORIGIN}/api/fa/v1/video/upload/upload_url"
APARAT_MY_VIDEOS_URL = f"{APARAT_ORIGIN}/api/fa/v1/user/video/videos"


class AparatPrivacyUpdateError(RuntimeError):
    """A privacy-update HTTP failure with safe stage/status metadata."""

    def __init__(self, stage: str, status_code: int | None):
        self.stage = stage
        self.status_code = status_code
        super().__init__(f"Aparat {stage} request failed with HTTP {status_code or 'unknown'}")


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
PENDING_APARAT_STATUSES = {"pending", "pending_credentials", "retry"}


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def _cookie_header(env: Mapping[str, str] | None = None) -> str:
    value = str(_env(env).get("APARAT_COOKIE_HEADER", "")).strip()
    if "\r" in value or "\n" in value:
        raise ValueError("APARAT_COOKIE_HEADER must be a single-line cookie header")

    # Accept either a complete Cookie header or a bare JWT copied from the
    # AuthV1 cookie value. Normalize only a single, JWT-shaped token; never log it.
    if (
        value
        and "AuthV1=" not in value
        and value.count(".") == 2
        and ";" not in value
        and "=" not in value
        and not any(char.isspace() for char in value)
    ):
        value = f"AuthV1={value}"
    return value


def aparat_credentials_available(env: Mapping[str, str] | None = None) -> bool:
    """Check only for the session cookie; never log or expose its value."""
    try:
        cookies = _cookie_header(env)
    except ValueError:
        return False
    return bool(cookies and "AuthV1=" in cookies)


def _site_session(cookie_header: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
            "Referer": f"{APARAT_ORIGIN}/uploadvideo",
            "Origin": APARAT_ORIGIN,
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "isNext": "true",
            "jsonType": "simple",
            "domain": "aparat",
            "currentUrl": f"{APARAT_ORIGIN}/uploadvideo",
            "Cookie": cookie_header,
        }
    )
    return session


def _read_json(response, *, operation: str) -> dict:
    response.raise_for_status()
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"Aparat returned invalid JSON during {operation}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Aparat returned an unexpected response during {operation}")
    if payload.get("success") is False or str(payload.get("status", "")).lower() in {
        "error", "failed", "fail"
    }:
        raise RuntimeError(f"Aparat rejected the request during {operation}")
    if payload.get("error"):
        raise RuntimeError(f"Aparat reported an upload error during {operation}")
    return payload


def _approved_upload_server(value: object) -> str:
    server = str(value or "").strip().rstrip("/")
    parts = urlsplit(server)
    hostname = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or not hostname
        or not (hostname == "aparat.com" or hostname.endswith(".aparat.com"))
        or parts.username
        or parts.password
    ):
        raise RuntimeError("Aparat returned an untrusted upload server URL")
    return server


def _upload_attributes(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {}
    attributes = data.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    return attributes | data


def _find_video_hash(value: object) -> str:
    """Extract an Aparat video hash from the API response without guessing a user ID."""
    preferred = {"videohash", "video_hash", "hash", "videoid", "video_id", "uid"}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).replace("-", "").lower() in preferred and isinstance(child, (str, int)):
                candidate = str(child).strip()
                if candidate and candidate.replace("_", "").replace("-", "").isalnum():
                    return candidate
        for child in value.values():
            found = _find_video_hash(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_video_hash(child)
            if found:
                return found
    return ""


def _find_video_record_id(value: object) -> str:
    """Extract the Aparat database record ID, which is distinct from its public UID."""
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict):
            candidate = data.get("id")
            if isinstance(candidate, (str, int)) and str(candidate).strip():
                return str(candidate).strip()
            nested = data.get("data")
            if isinstance(nested, dict):
                candidate = nested.get("id")
                if isinstance(candidate, (str, int)) and str(candidate).strip():
                    return str(candidate).strip()
    return ""


def find_uploaded_aparat_video(
    title: str,
    *,
    video_id: str | int | None = None,
    session=None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Look up an already-uploaded video by record ID or exact title; never uploads anything."""
    source = _env(env)
    cookies = _cookie_header(source)
    if "AuthV1=" not in cookies:
        raise RuntimeError("Aparat session is not configured; AuthV1 cookie is missing")

    site = session or _site_session(cookies)
    if session is not None:
        site.headers.setdefault("Cookie", cookies)
        site.headers.setdefault("User-Agent", USER_AGENT)
        site.headers.setdefault("Origin", APARAT_ORIGIN)
        site.headers.setdefault("Referer", f"{APARAT_ORIGIN}/uploadvideo")
        site.headers.setdefault("Content-Type", "application/json; charset=utf-8")

    payload = _read_json(
        site.get(APARAT_MY_VIDEOS_URL, timeout=(10, 30)),
        operation="my videos lookup",
    )
    included = payload.get("included")
    if not isinstance(included, list):
        data = payload.get("data")
        included = data.get("included") if isinstance(data, dict) else None
    if not isinstance(included, list):
        included = []

    wanted_id = str(video_id or "").strip()
    wanted_title = " ".join(str(title or "").split()).casefold()
    title_matches = []
    id_match = None
    for item in included:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        current_id = str(item.get("id") or attrs.get("id") or "").strip()
        current_title = " ".join(str(attrs.get("title") or item.get("title") or "").split()).casefold()
        if wanted_id and current_id == wanted_id:
            id_match = item
            break
        if wanted_title and current_title == wanted_title:
            title_matches.append(item)

    matched = id_match or (title_matches[0] if title_matches else None)
    if not isinstance(matched, dict):
        return {"video_id": wanted_id, "video_hash": "", "url": "", "found": False}

    attrs = matched.get("attributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    found_id = str(matched.get("id") or attrs.get("id") or wanted_id).strip()
    video_hash = _find_video_hash(attrs) or _find_video_hash(matched)
    url = f"{APARAT_ORIGIN}/v/{video_hash}" if video_hash else ""
    return {
        "video_id": found_id,
        "video_hash": video_hash,
        "url": url,
        "title": str(attrs.get("title") or matched.get("title") or ""),
        "found": True,
    }


def upload_aparat_video(
    video_path: str | Path,
    title: str,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    session=None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Upload one MP4 to Aparat through its current web uploader endpoints.

    APARAT_VIDEO_PASS=1 (default) requests a non-public upload for the first test.
    Set it to 0 only after the upload flow and metadata have been verified.
    """
    source = _env(env)
    cookies = _cookie_header(source)
    if "AuthV1=" not in cookies:
        raise RuntimeError("Aparat session is not configured; AuthV1 cookie is missing")

    path = Path(video_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Aparat upload file does not exist or is empty")
    if path.suffix.lower() != ".mp4":
        raise ValueError("Aparat uploader accepts MP4 files only")

    video_pass = str(source.get("APARAT_VIDEO_PASS", "1")).strip()
    if video_pass not in {"0", "1"}:
        raise ValueError("APARAT_VIDEO_PASS must be 1 (non-public test) or 0 (publish)")
    try:
        category_id = str(int(source.get("APARAT_CATEGORY_ID", "5")))
    except (TypeError, ValueError):
        category_id = "5"

    name = str(title or "پیشنهاد آفِرچین").strip()[:100]
    desc = str(
        description
        or (
            "پیشنهادهای کاربردی و تخفیف‌های منتخب دیجی‌کالا در آفِرچین.\n"
            "قیمت و موجودی ممکن است تغییر کند؛ پیش از خرید، اطلاعات روز محصول را در دیجی‌کالا بررسی کنید.\n\n"
            "تلگرام: https://t.me/OfferChin\n"
            "بله: https://ble.ir/OfferChin"
        )
    ).strip()[:3000]
    clean_tags = tags or ["آفِرچین", "دیجی‌کالا", "تخفیف", "پیشنهاد ویژه"]
    tags_string = "-".join(str(tag).strip().replace("-", " ") for tag in clean_tags if str(tag).strip())

    site = session or _site_session(cookies)
    if session is not None:
        # Test sessions may be injected; production sessions must carry the cookie securely.
        site.headers.setdefault("Cookie", cookies)
        site.headers.setdefault("User-Agent", USER_AGENT)
        site.headers.setdefault("Origin", APARAT_ORIGIN)
        site.headers.setdefault("Referer", f"{APARAT_ORIGIN}/uploadvideo")
        site.headers.setdefault("Content-Type", "application/json; charset=utf-8")

    config = _read_json(site.get(APARAT_UPLOAD_CONFIG_URL, timeout=(10, 30)), operation="upload config")
    config_data = config.get("data") if isinstance(config.get("data"), dict) else {}
    server = _approved_upload_server(config_data.get("server"))

    qquuid = str(uuid.uuid4())
    upload_info = _read_json(
        site.post(
            APARAT_UPLOAD_URL,
            json={"uploadIds": [qquuid], "upload_base_url": server, "upload_cnt": 1},
            timeout=(10, 30),
        ),
        operation="upload reservation",
    )
    attributes = _upload_attributes(upload_info)
    upload_id = str(attributes.get("uploadId") or attributes.get("upload_id") or "").strip()
    upload_token = str(attributes.get("token") or "").strip()
    if not upload_id or not upload_token:
        raise RuntimeError("Aparat upload reservation was missing required upload fields")

    # Do not forward authenticated-site cookies to the separate upload host.
    upload_session = requests.Session()
    upload_session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Referer": f"{APARAT_ORIGIN}/",
            "Origin": APARAT_ORIGIN,
            "X-Token": upload_token,
        }
    )

    file_size = path.stat().st_size
    chunk_size = 3_000_000
    total_parts = (file_size + chunk_size - 1) // chunk_size
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    with path.open("rb") as handle:
        part_index = 0
        byte_offset = 0
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            data = {
                "qqchunksize": len(chunk),
                "qqtotalfilesize": file_size,
                "qqtype": mime_type,
                "qquuid": qquuid,
                "qqfilename": path.name,
                "qqfilepath": path.name,
                "qqtotalparts": total_parts,
                "qqpartindex": part_index,
                "qqpartbyteoffset": byte_offset,
            }
            response = upload_session.post(
                urljoin(server + "/", "upload"),
                data=data,
                files={"qqfile": (path.name, chunk, mime_type)},
                timeout=(15, 180),
            )
            if response.status_code not in {200, 201}:
                response.raise_for_status()
                raise RuntimeError(f"Aparat rejected upload chunk {part_index + 1}")
            byte_offset += len(chunk)
            part_index += 1

    final_state = upload_session.get(urljoin(server + "/", f"file/{qquuid}"), timeout=(10, 30))
    if final_state.status_code >= 500:
        final_state.raise_for_status()
    completed = upload_session.post(
        urljoin(server + "/", "chunksdone"),
        data={
            "qquuid": qquuid,
            "qqfilename": path.name,
            "qqtotalfilesize": file_size,
            "qqtotalparts": total_parts,
        },
        timeout=(10, 60),
    )
    completed.raise_for_status()

    metadata = {
        "uploadId": upload_id,
        "upload_base_url": server,
        "video": qquuid,
        "video_pass": video_pass,
        "watermark": "1",
        "category": category_id,
        "comment": "yes",
        "kids_friendly": True,
        "title": name,
        "descr": desc,
        "tags": tags_string,
        "new_playlist": "",
        "playlist_temp": "",
        "playlistid": "",
        "subtitle": "",
        "publish_date": "",
    }
    result = _read_json(
        site.post(
            f"{APARAT_ORIGIN}/api/fa/v1/video/upload/upload/uploadId/{upload_id}",
            json=metadata,
            timeout=(15, 60),
        ),
        operation="video metadata and publication",
    )
    video_hash = _find_video_hash(result)
    video_id = _find_video_record_id(result)
    url = f"{APARAT_ORIGIN}/v/{video_hash}" if video_hash else ""
    lookup_error = ""
    if not video_hash:
        try:
            found = find_uploaded_aparat_video(name, video_id=video_id or None, session=site, env=source)
            video_id = video_id or found.get("video_id", "")
            video_hash = found.get("video_hash", "")
            url = found.get("url", "")
        except Exception as exc:
            # The metadata submission already succeeded. Never turn a lookup failure
            # into an upload retry that could create a duplicate video.
            lookup_error = type(exc).__name__
    return {
        "video_id": video_id,
        "video_hash": video_hash,
        "url": url,
        "lookup_error": lookup_error,
        "visibility": "public" if video_pass == "0" else "non_public_test",
        "title": name,
        "response": result,
    }


def set_aparat_video_private(
    video_hash: str,
    *,
    session=None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Stop sharing a tracked Aparat video using the authenticated web edit endpoint.

    This web endpoint is undocumented. Treat it as best-effort; the caller records
    failures and retries later rather than claiming a privacy change succeeded.
    """
    safe_hash = str(video_hash or "").strip()
    if not safe_hash or not safe_hash.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid Aparat video hash")
    cookies = _cookie_header(env)
    if "AuthV1=" not in cookies:
        raise RuntimeError("Aparat session is not configured; AuthV1 cookie is missing")

    site = session or _site_session(cookies)
    if session is not None:
        site.headers.setdefault("Cookie", cookies)
        site.headers.setdefault("User-Agent", USER_AGENT)
        site.headers.setdefault("Origin", APARAT_ORIGIN)
        site.headers.setdefault("Referer", f"{APARAT_ORIGIN}/uploadvideo")
        site.headers.setdefault("Content-Type", "application/json; charset=utf-8")
        site.headers.setdefault("isNext", "true")
        site.headers.setdefault("jsonType", "simple")
        site.headers.setdefault("domain", "aparat")
        site.headers.setdefault("currentUrl", f"{APARAT_ORIGIN}/uploadvideo")

    try:
        details_response = site.get(
            f"{APARAT_ORIGIN}/api/fa/v1/video/video/show/videohash/{safe_hash}",
            params={"pr": "1", "mf": "1"},
            timeout=(10, 30),
        )
        details = _read_json(details_response, operation="video details")
    except requests.exceptions.HTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        raise AparatPrivacyUpdateError("video_details", status_code) from exc
    data = details.get("data") if isinstance(details.get("data"), dict) else {}

    category = data.get("category") if isinstance(data.get("category"), dict) else {}
    category_id = category.get("id") or data.get("category_id") or 5
    playlist = data.get("playList") if isinstance(data.get("playList"), dict) else {}
    playlist_data = playlist.get("data") if isinstance(playlist.get("data"), dict) else {}
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    video_id = data.get("id") or data.get("video_id")
    if not video_id:
        raise RuntimeError("Aparat video details did not include the internal video ID")

    edit_payload = {
        "title": str(data.get("title") or "پیشنهاد آفِرچین"),
        "descr": str(data.get("description") or data.get("descr") or ""),
        "kids_friendly": bool(data.get("kids_friendly", True)),
        "new_playlist": None,
        "playlistid": playlist_data.get("id"),
        "publish_date": None,
        "video_id": video_id,
        # The web uploader's edit endpoint uses a truthy value to stop sharing the video.
        "video_pass": True,
        "comment": data.get("comment_enable", "yes"),
        "category": category_id,
        "tags": "-".join(str(tag).strip().replace("-", " ") for tag in tags if str(tag).strip()),
    }
    try:
        # Aparat's current web endpoint uses a raw JSON string body, not the
        # requests helper's json= argument. Match the established request shape.
        response = site.post(
            f"{APARAT_ORIGIN}/api/fa/v1/video/video/edit/videohash/{safe_hash}",
            data=json.dumps(edit_payload, ensure_ascii=False),
            timeout=(10, 45),
        )
        _read_json(response, operation="video privacy update")
    except requests.exceptions.HTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        raise AparatPrivacyUpdateError("video_edit", status_code) from exc
    return True
