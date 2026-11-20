#!/usr/bin/env python3
"""Read-only Affilio publisher-panel session and report-route audit.

Credentials are read only from AFFILIO_USER/AFFILIO_PASS environment variables.
The script never prints, writes, uploads, or persists credentials, cookies,
tokens, account data, or report rows. Cookies live in memory for this process.
"""

from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

PANEL_ORIGIN = "https://publisher.affilio.ir/"
SSO_HOST = "sso.digiwise.ir"
LOGIN_ACTION_PATH = "/realms/services/login-actions/authenticate"
MAX_HTML_BYTES = 2_000_000
MAX_SCRIPT_BYTES = 2_000_000
MAX_SCRIPTS = 20
KEYWORDS = re.compile(
    r"(report|performance|commission|transaction|order|click|analytics|"
    r"statistic|sales|conversion|payout|earning)",
    re.IGNORECASE,
)
ROUTE_LITERAL = re.compile(r'''['"`](/[^'"\`\s<>]{1,220})['"`]''')


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


def normalized_path(raw_url: str, base_url: str) -> str | None:
    resolved = urljoin(base_url, raw_url)
    parsed = urlsplit(resolved)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "publisher.affilio.ir":
        return None
    path = parsed.path or "/"
    path = re.sub(
        r"(?i)(?<=/)[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?=/|$)",
        "{id}",
        path,
    )
    path = re.sub(r"(?<=/)\d{5,}(?=/|$)", "{id}", path)
    return path[:220]


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
            if path and KEYWORDS.search(path):
                paths.add(path)

    return sorted(paths)[:40]


def _read_response(opener, request: Request, max_bytes: int) -> tuple[str, str, int]:
    with opener.open(request, timeout=25) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("response_too_large")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), response.geturl(), response.status


def audit_panel() -> int:
    username = os.environ.get("AFFILIO_USER", "")
    password = os.environ.get("AFFILIO_PASS", "")
    print(f"AFFILIO_USER_SECRET_PRESENT={'yes' if username else 'no'}")
    print(f"AFFILIO_PASS_SECRET_PRESENT={'yes' if password else 'no'}")
    if not username or not password:
        print("AFFILIO_PANEL_AUDIT_RESULT=blocked_missing_secret")
        return 2

    # Session cookies are held in memory only and discarded at process exit.
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    headers = {
        "User-Agent": "OfferChinReadOnlyPanelAudit/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        html, login_page_url, status = _read_response(
            opener, Request(PANEL_ORIGIN, headers=headers), MAX_HTML_BYTES
        )
        if status != 200:
            print(f"AFFILIO_PANEL_AUDIT_RESULT=blocked_http_{status}")
            return 3

        login_parser = parse_page(html)
        form = find_login_form(login_parser)
        if form is None:
            if (urlsplit(login_page_url).hostname or "").lower() == "publisher.affilio.ir":
                # An already-authenticated session is not expected in a fresh runner.
                print("AFFILIO_PANEL_AUDIT_RESULT=login_form_not_found")
            else:
                print("AFFILIO_PANEL_AUDIT_RESULT=unexpected_login_flow")
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
            authenticated_html, final_url, final_status = _read_response(
                opener, post_request, MAX_HTML_BYTES
            )
        except HTTPError as exc:
            print(f"AFFILIO_PANEL_AUDIT_RESULT=authentication_rejected_http_{exc.code}")
            return 6

        final_host = (urlsplit(final_url).hostname or "").lower()
        authenticated_parser = parse_page(authenticated_html)
        if (
            final_status != 200
            or final_host != "publisher.affilio.ir"
            or find_login_form(authenticated_parser) is not None
        ):
            print("AFFILIO_PANEL_AUDIT_RESULT=login_rejected_or_additional_challenge")
            return 7

        script_texts: list[str] = []
        seen_scripts: set[str] = set()
        for source in authenticated_parser.scripts:
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
                # A failed static asset must not expose response text or stop the audit.
                continue

        routes = report_route_candidates(authenticated_parser, final_url, script_texts)
        combined = authenticated_html + "\n" + "\n".join(script_texts)
        report_terms_found = bool(KEYWORDS.search(combined))

        print("AFFILIO_PANEL_AUDIT_RESULT=authenticated_read_only")
        print("AFFILIO_PANEL_FINAL_HOST=publisher.affilio.ir")
        print(f"AFFILIO_PANEL_SCRIPT_COUNT={len(script_texts)}")
        print(f"AFFILIO_REPORT_TERMS_FOUND={'yes' if report_terms_found else 'no'}")
        print(f"AFFILIO_REPORT_ROUTE_CANDIDATES={len(routes)}")
        for path in routes:
            print(f"AFFILIO_REPORT_ROUTE={path}")
        print("AFFILIO_PANEL_RAW_DATA_EXPORTED=no")
        print("AFFILIO_PANEL_COOKIE_PERSISTED=no")
        return 0

    except (URLError, TimeoutError, ValueError):
        # Avoid printing exception text; it can contain URLs, cookies, or response details.
        print("AFFILIO_PANEL_AUDIT_RESULT=network_or_response_error")
        return 8
    except Exception:
        print("AFFILIO_PANEL_AUDIT_RESULT=unexpected_error")
        return 9


if __name__ == "__main__":
    sys.exit(audit_panel())
