"""Browser-compatible HTTP session for DigiKala's current public JSON APIs.

The API now expects browser/XHR headers and a Chrome-like TLS fingerprint.
Do not silently fall back to plain requests: that path returned 404s/empty data
from GitHub Actions even when these exact routes worked in a real browser-like
session.
"""
from __future__ import annotations

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - dependencies install from requirements.txt
    curl_requests = None


DIGIKALA_API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Origin": "https://www.digikala.com",
    "Referer": "https://www.digikala.com/",
    "x-web-client": "desktop",
    "x-web-client-id": "web",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "priority": "u=1, i",
}


def new_digikala_session():
    """Create a per-process/per-worker Chrome-impersonating DigiKala session."""
    if curl_requests is None:
        raise RuntimeError("curl_cffi_required_for_current_digikala_api")
    session = curl_requests.Session(impersonate="chrome")
    session.headers.update(DIGIKALA_API_HEADERS)
    return session
