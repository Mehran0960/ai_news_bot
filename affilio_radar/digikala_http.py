"""Browser-compatible HTTP transport for DigiKala's public storefront APIs.

The product API paths are intentionally kept in their existing, tested callers.
This module changes only the HTTP client fingerprint and browser request headers;
it does not relax product, price, stock, discount, or demand validation.
"""
from __future__ import annotations

import requests as fallback_requests

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - CI installs curl_cffi from requirements.txt
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
    """Create a fresh per-thread/per-process browser-compatible API session."""
    if curl_requests is not None:
        session = curl_requests.Session(impersonate="chrome")
        transport = "curl_cffi_chrome"
    else:
        # Keep local/offline tooling importable without the optional dependency.
        # Production workflows install curl_cffi and use the impersonated path.
        session = fallback_requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        })
        transport = "requests_fallback"

    session.headers.update(DIGIKALA_API_HEADERS)
    print(f"DIGIKALA_HTTP_SESSION transport={transport}")
    return session
