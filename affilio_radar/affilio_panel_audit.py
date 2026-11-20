#!/usr/bin/env python3
"""Read-only Affilio publisher-panel session and report-route audit.

Credentials are read only from AFFILIO_USER/AFFILIO_PASS environment variables.
The script never prints, writes, uploads, or persists credentials, cookies,
tokens, account data, or report rows. Session state is held in memory only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

PANEL_ORIGIN = "https://publisher.affilio.ir/"
SSO_HOST = "sso.digiwise.ir"
SSO_REALM = "/realms/services"
AUTH_PATH = SSO_REALM + "/protocol/openid-connect/auth"
TOKEN_PATH = SSO_REALM + "/protocol/openid-connect/token"
LOGIN_ACTION_PATH = SSO_REALM + "/login-actions/authenticate"
CLIENT_ID = "affilio-publisher-panel"
MAX_HTML_BYTES = 2_000_000
MAX_SCRIPT_BYTES = 2_000_000
MAX_SCRIPTS = 20
KEYWORDS = re.compile(
    r"(api|graphql|report|performance|commission|transaction|order|click|analytics|"
    r"statistic|sales|conversion|payout|earning|affiliate|publisher|finance|revenue|"
    r"dashboard|overview|summary|metric|link|product)",
    re.IGNORECASE,
)
ROUTE_LITERAL = re.compile(r'''['"`](/[^'"`\\s<>]{1,220})['"`]''')
ABSOLUTE_URL_LITERAL = re.compile(r'''['"`](https://[^'"`\\s<>]{1,400})['"`]''')
REDIRECT_CODES = {301, 302, 303, 307, 308}


class PanelHTMLParser(HTMLParser):
    """Extract only form metadata, same-page links, and script references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.links: list[tuple[str, str]] = []
        self.scripts: list[str] = []
        self._form: dict | None = None
        self._anchor: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._form = {
                "id": values.get("id", ""),
                "action": values.get("action", ""),
                "method": values.get("method", "get").lower(),
                "inputs": [],
            }
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            self._form["inputs"].append(values)
        elif tag == "a":
            self._anchor = {"href": values.get("href", ""), "text": []}
        elif tag == "script" and values.get("src"):
            self.scripts.append(values["src"])

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            label = " ".join(" ".join(self._anchor["text"]).split())
            self.links.append((self._anchor["href"], label))
            self._anchor = None
        elif tag == "form":
            self._form = None


class StopRedirectHandler(HTTPRedirectHandler):
    """Capture the OIDC callback rather than following it without a browser."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_page(html: str) -> PanelHTMLParser:
    parser = PanelHTMLParser()
    parser.feed(html)
    return parser


def find_login_form(parser: PanelHTMLParser) -> dict | None:
    for form in parser.forms:
        if form.get("id") == "kc-form-login":
            return form
    for form in parser.forms:
        if LOGIN_ACTION_PATH in form.get("action", ""):
            return form
    return None


def trusted_login_action(raw_action: str, page_url: str) -> str | None:
    action = urljoin(page_url, raw_action)
    parsed = urlsplit(action)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != SSO_HOST
        or parsed.path != LOGIN_ACTION_PATH
        or parsed.username
        or parsed.password
    ):
        return None
    return action


def build_authorization_request() -> tuple[str, str, str]:
    """Create a fresh OIDC PKCE request; return URL, state, and verifier."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    query = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": PANEL_ORIGIN,
            "state": state,
            "nonce": nonce,
            "response_mode": "fragment",
            "response_type": "code",
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"https://{SSO_HOST}{AUTH_PATH}?{query}", state, verifier


def extract_authorization_code(callback_url: str, expected_state: str) -> str | None:
    """Accept a code only from the registered redirect URI and matching state."""
    parsed = urlsplit(callback_url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "publisher.affilio.ir"
        or parsed.path not in ("", "/")
    ):
        return None
    values: dict[str, str] = {}
    values.update(dict(parse_qsl(parsed.query, keep_blank_values=True)))
    values.update(dict(parse_qsl(parsed.fragment, keep_blank_values=True)))
    code = values.get("code", "")
    state = values.get("state", "")
    if not code or not expected_state or not secrets.compare_digest(state, expected_state):
        return None
    return code


def normalized_path(raw_url: str, base_url: str) -> str | None:
    resolved = urljoin(base_url, raw_url)
    parsed = urlsplit(resolved)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not (
            hostname == "publisher.affilio.ir"
            or hostname.endswith(".affilio.ir")
            or hostname.endswith(".digiwise.ir")
        )
        or parsed.username
        or parsed.password
    ):
        return None
    path = parsed.path or "/"
    path = re.sub(
        r"(?i)(?<=/)[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?=/|$)",
        "{id}",
        path,
    )
    path = re.sub(r"(?<=/)\\d{5,}(?=/|$)", "{id}", path)
    normalized = path[:220] if hostname == "publisher.affilio.ir" else f"{hostname}{path[:180]}"
    return normalized


def report_route_candidates(
    parser: PanelHTMLParser,
    page_url: str,
    script_texts: list[str],
) -> list[str]:
    paths: set[str] = set()
    for raw_href, _label in parser.links:
        path = normalized_path(raw_href, page_url)
        if path and KEYWORDS.search(path):
            paths.add(path)

    for source in script_texts:
        for match in ROUTE_LITERAL.finditer(source):
            path = normalized_path(match.group(1), page_url)
            if path and (
                KEYWORDS.search(path)
                or path.startswith(("/api/", "/v1/", "/v2/", "/graphql"))
                or "/api/" in path
            ):
                paths.add(path)
        for match in ABSOLUTE_URL_LITERAL.finditer(source):
            path = normalized_path(match.group(1), page_url)
            if path and (
                KEYWORDS.search(path)
                or path.endswith(("/graphql", "/api", "/v1", "/v2"))
                or "/api/" in path
            ):
                paths.add(path)

    return sorted(paths)[:60]


def _read_response(opener, request: Request, max_bytes: int) -> tuple[str, str, int]:
    with opener.open(request, timeout=25) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("response_too_large")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), response.geturl(), response.status


def _post_without_following_redirect(
    opener, request: Request, max_bytes: int
) -> tuple[str, str, int]:
    try:
        return _read_response(opener, request, max_bytes)
    except HTTPError as exc:
        if exc.code in REDIRECT_CODES:
            location = exc.headers.get("Location", "")
            if location:
                return "", urljoin(request.full_url, location), exc.code
        raise


def _exchange_code_for_token(opener, code: str, verifier: str) -> str | None:
    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": PANEL_ORIGIN,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = Request(
        f"https://{SSO_HOST}{TOKEN_PATH}",
        data=payload,
        headers={
            "User-Agent": "OfferChinReadOnlyPanelAudit/1.0",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        body, final_url, status = _read_response(opener, request, 256_000)
    except Exception:
        return None
    if (
        status != 200
        or (urlsplit(final_url).hostname or "").lower() != SSO_HOST
        or urlsplit(final_url).path != TOKEN_PATH
    ):
        return None
    try:
        response = json.loads(body)
    except (TypeError, ValueError):
        return None
    token = response.get("access_token") if isinstance(response, dict) else None
    return token if isinstance(token, str) and token else None


def audit_panel() -> int:
    username = os.environ.get("AFFILIO_USER", "")
    password = os.environ.get("AFFILIO_PASS", "")
    print(f"AFFILIO_USER_SECRET_PRESENT={'yes' if username else 'no'}")
    print(f"AFFILIO_PASS_SECRET_PRESENT={'yes' if password else 'no'}")
    if not username or not password:
        print("AFFILIO_PANEL_AUDIT_RESULT=blocked_missing_secret")
        return 2

    # Cookies and OAuth tokens remain in memory for this process only.
    opener = build_opener(HTTPCookieProcessor(CookieJar()), StopRedirectHandler())
    headers = {
        "User-Agent": "OfferChinReadOnlyPanelAudit/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        authorization_url, expected_state, verifier = build_authorization_request()
        login_html, login_page_url, login_status = _read_response(
            opener, Request(authorization_url, headers=headers), MAX_HTML_BYTES
        )
        if (
            login_status != 200
            or (urlsplit(login_page_url).hostname or "").lower() != SSO_HOST
            or urlsplit(login_page_url).path != AUTH_PATH
        ):
            print("AFFILIO_PANEL_AUDIT_RESULT=unexpected_sso_response")
            return 3

        form = find_login_form(parse_page(login_html))
        if form is None:
            print("AFFILIO_PANEL_AUDIT_RESULT=login_form_not_found")
            return 4
        action = trusted_login_action(form.get("action", ""), login_page_url)
        if action is None or form.get("method") != "post":
            print("AFFILIO_PANEL_AUDIT_RESULT=untrusted_login_form")
            return 5

        fields: dict[str, str] = {}
        for item in form.get("inputs", []):
            name = item.get("name", "")
            if name and item.get("type", "").lower() == "hidden":
                fields[name] = item.get("value", "")
        fields["username"] = username
        fields["password"] = password

        post_headers = dict(headers)
        post_headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{SSO_HOST}",
                "Referer": login_page_url,
            }
        )
        post_request = Request(
            action,
            data=urlencode(fields).encode("utf-8"),
            headers=post_headers,
            method="POST",
        )
        try:
            _login_body, callback_url, callback_status = _post_without_following_redirect(
                opener, post_request, MAX_HTML_BYTES
            )
        except HTTPError as exc:
            print(f"AFFILIO_PANEL_AUDIT_RESULT=authentication_rejected_http_{exc.code}")
            return 6

        if callback_status not in REDIRECT_CODES:
            # A 200 response usually means rejected credentials, an MFA step, or a changed flow.
            print("AFFILIO_PANEL_AUDIT_RESULT=login_rejected_or_additional_challenge")
            return 7

        code = extract_authorization_code(callback_url, expected_state)
        if not code:
            print("AFFILIO_PANEL_AUDIT_RESULT=callback_state_or_code_invalid")
            return 8

        access_token = _exchange_code_for_token(opener, code, verifier)
        if not access_token:
            print("AFFILIO_PANEL_AUDIT_RESULT=oidc_token_exchange_failed")
            return 9

        # The token is intentionally not printed, persisted, or sent to non-Affilio hosts.
        panel_html, final_url, panel_status = _read_response(
            opener,
            Request(PANEL_ORIGIN, headers=headers),
            MAX_HTML_BYTES,
        )
        if panel_status != 200 or (urlsplit(final_url).hostname or "").lower() != "publisher.affilio.ir":
            print("AFFILIO_PANEL_AUDIT_RESULT=panel_shell_unavailable")
            return 10

        parser = parse_page(panel_html)
        script_texts: list[str] = []
        seen_scripts: set[str] = set()
        for source in parser.scripts:
            script_url = urljoin(final_url, source)
            parsed = urlsplit(script_url)
            if (
                parsed.scheme != "https"
                or (parsed.hostname or "").lower() != "publisher.affilio.ir"
                or script_url in seen_scripts
            ):
                continue
            seen_scripts.add(script_url)
            if len(seen_scripts) > MAX_SCRIPTS:
                break
            try:
                script, _script_url, _script_status = _read_response(
                    opener, Request(script_url, headers=headers), MAX_SCRIPT_BYTES
                )
                script_texts.append(script)
            except Exception:
                continue

        routes = report_route_candidates(parser, final_url, script_texts)
        combined = panel_html + "\n" + "\n".join(script_texts)
        report_terms_found = bool(KEYWORDS.search(combined))

        print("AFFILIO_PANEL_AUDIT_RESULT=authenticated_read_only")
        print("AFFILIO_OIDC_FLOW=authorization_code_pkce")
        print("AFFILIO_PANEL_FINAL_HOST=publisher.affilio.ir")
        print(f"AFFILIO_PANEL_SCRIPT_COUNT={len(script_texts)}")
        print(f"AFFILIO_REPORT_TERMS_FOUND={'yes' if report_terms_found else 'no'}")
        print(f"AFFILIO_REPORT_ROUTE_CANDIDATES={len(routes)}")
        for path in routes:
            print(f"AFFILIO_REPORT_ROUTE={path}")
        print("AFFILIO_PANEL_RAW_DATA_EXPORTED=no")
        print("AFFILIO_PANEL_COOKIE_PERSISTED=no")
        print("AFFILIO_OIDC_TOKEN_PERSISTED=no")
        return 0

    except (URLError, TimeoutError, ValueError):
        print("AFFILIO_PANEL_AUDIT_RESULT=network_or_response_error")
        return 11
    except Exception:
        print("AFFILIO_PANEL_AUDIT_RESULT=unexpected_error")
        return 12


if __name__ == "__main__":
    sys.exit(audit_panel())
