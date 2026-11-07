"""Filo video uploader for OfferChin's own short product videos.

This adapter uses Filo's authenticated upload page, not its native-republish API.
It deliberately distinguishes a public publication from an accepted submission
that is still awaiting review. Credentials are read only from the process env.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

FILO_ORIGIN = "https://ifilo.net"
FILO_LOGIN_PATH = "/login?m=3&r=%2Fupload"
FILO_UPLOAD_PATH = "/upload"
FILO_MY_VIDEOS_PATH = "/my/videos"
FILO_PUBLISH_PATH = "/api/v1/video/publish"
FILO_PENDING_MARKERS = (
    "در صف انتشار",
    "در حال پردازش",
    "در انتظار تایید",
    "در انتظار تأیید",
    "ارسال شده برای اصلاح",
    "ارسال شده برای سانسور",
)


class FiloUploadError(RuntimeError):
    """Safe, credential-free uploader error with a known submission boundary."""

    def __init__(self, code: str, *, submission_started: bool = False):
        self.code = str(code or "filo_upload_failed")[:120]
        self.submission_started = bool(submission_started)
        super().__init__(self.code)


def filo_credentials_available(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return bool(
        str(source.get("FILO_USER", "")).strip()
        and str(source.get("FILO_PASS", "")).strip()
    )


def _success_flag(value: object) -> bool:
    return value is True or value == 1 or str(value).strip().lower() in {"1", "true", "yes"}


def _response_payload(response) -> dict:
    try:
        data = response.json()
    except Exception:
        return {}
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if unicodedata.category(ch) != "Mn")
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _title_matches(text: object, title: str) -> bool:
    expected = _normalize_text(title)
    observed = _normalize_text(text)
    return bool(expected and observed and (expected in observed or observed in expected))


def _extract_cover(video_path: Path, directory: Path) -> Path:
    """Extract a frame locally; do not fetch external artwork or expose video metadata."""
    binary = shutil.which("ffmpeg")
    if not binary:
        try:
            import imageio_ffmpeg
            binary = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise FiloUploadError("filo_cover_ffmpeg_unavailable") from exc
    cover = directory / "filo-cover.jpg"
    try:
        result = subprocess.run(
            [
                binary, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", "0.6", "-i", str(video_path),
                "-frames:v", "1", "-vf",
                "scale=1280:720:force_original_aspect_ratio=decrease,"
                "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-q:v", "2", str(cover),
            ],
            check=False, capture_output=True, timeout=30,
        )
    except Exception as exc:
        raise FiloUploadError("filo_cover_extraction_failed") from exc
    if result.returncode != 0 or not cover.is_file() or cover.stat().st_size < 2_000:
        raise FiloUploadError("filo_cover_extraction_failed")
    return cover


def _safe_video_links(page) -> list[dict]:
    return page.locator("a[href*='/v/'], a[href*='/video/']").evaluate_all(
        """nodes => nodes.map(a => ({
          href: a.href.split('?')[0],
          text: String(a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '')
            .trim().replace(/\\s+/g, ' '),
          cardText: String((a.closest('article, li, [class*="item"], [class*="Item"], [class*="card"], [class*="Card"], [class*="video"], [class*="Video"]') || a.parentElement || a).innerText || '')
            .trim().replace(/\\s+/g, ' ').slice(0, 400)
        })).filter(x => /^https?:\\/\\/(?:www\\.)?ifilo\\.net\\/(?:v|video)\\//i.test(x.href))"""
    )


def _visible_first(page, selectors):
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible():
            return locator
    return None


def _find_title_field(page):
    field = _visible_first(page, [
        'input[name*="title" i]',
        'input[id*="title" i]',
        'input[placeholder*="عنوان"]',
        'input[aria-label*="عنوان"]',
        'textarea[name*="title" i]',
        'input[placeholder*="نام ویدیو"]',
        'input[placeholder*="نام ویدئو"]',
    ])
    if field is not None:
        return field
    candidates = page.locator("input, textarea").evaluate_all(
        """nodes => nodes.map((el, index) => {
          const style = getComputedStyle(el);
          const visible = Boolean(el.getBoundingClientRect().width && el.getBoundingClientRect().height) &&
            style.visibility !== 'hidden' && style.display !== 'none';
          const labels = Array.from(el.labels || []).map(x => x.innerText || '').join(' ');
          return {index, visible, tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(),
            id: el.id || '', name: el.name || '', placeholder: el.placeholder || '',
            ariaLabel: el.getAttribute('aria-label') || '', label: labels};
        })"""
    )
    for item in candidates:
        identity = " ".join(str(item.get(key) or "") for key in ("id", "name", "placeholder", "ariaLabel", "label"))
        if item.get("visible") and item.get("type") in {"text", ""} and re.search(
            r"عنوان|title|نام ویدیو|نام ویدئو", identity, re.I
        ):
            return page.locator("input, textarea").nth(int(item["index"]))
    return None


def _find_description_field(page):
    field = _visible_first(page, [
        'textarea[name*="description" i]',
        'textarea[id*="description" i]',
        'textarea[placeholder*="توضیح"]',
        'textarea[placeholder*="شرح"]',
        '[contenteditable="true"][aria-label*="توضیح"]',
        '[contenteditable="true"]',
    ])
    if field is not None:
        return field
    candidates = page.locator("textarea").evaluate_all(
        """nodes => nodes.map((el, index) => {
          const r = el.getBoundingClientRect(), style = getComputedStyle(el);
          return {index, visible: Boolean(r.width && r.height) && style.visibility !== 'hidden' && style.display !== 'none',
            id: el.id || '', name: el.name || '', placeholder: el.placeholder || '',
            ariaLabel: el.getAttribute('aria-label') || '',
            label: Array.from(el.labels || []).map(x => x.innerText || '').join(' ')};
        })"""
    )
    for item in candidates:
        identity = " ".join(str(item.get(key) or "") for key in ("id", "name", "placeholder", "ariaLabel", "label"))
        if item.get("visible") and re.search(r"توضیح|شرح|description", identity, re.I):
            return page.locator("textarea").nth(int(item["index"]))
    return None


def _find_publish_button(page):
    locator = page.locator("button, input[type='submit'], [role='button']")
    buttons = locator.evaluate_all(
        """nodes => nodes.map((el, index) => {
          const r = el.getBoundingClientRect(), style = getComputedStyle(el);
          return {
            index,
            tag: el.tagName.toLowerCase(),
            text: String(el.getAttribute('aria-label') || el.innerText || el.getAttribute('value') || '')
              .trim().replace(/\\s+/g, ' ').slice(0, 90),
            disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
            visible: Boolean(r.width && r.height) && style.visibility !== 'hidden' && style.display !== 'none'
          };
        })"""
    )
    for button in buttons:
        label = str(button.get("text") or "")
        if (
            button.get("visible")
            and re.search(r"بارگذاری ویدیو|آپلود ویدیو|انتشار|ارسال ویدیو|ثبت ویدیو|بارگذاری|آپلود", label)
            and not re.search(r"انتخاب فایل|انتخاب ویدیو|لغو|انصراف|بستن|بازگشت|ویرایش", label)
            and not button.get("disabled")
        ):
            candidate = locator.nth(int(button["index"]))
            if candidate.count() and candidate.is_visible() and candidate.is_enabled():
                return candidate
    return None


def _login(page, username: str, password: str) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    page.goto(FILO_ORIGIN + "/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(0.6)
    sign_in_href = page.locator("a[href]").evaluate_all(
        """nodes => {
          const a = nodes.find(x => {
            let p = '';
            try { p = new URL(x.href).pathname; } catch {}
            const t = (x.innerText || x.getAttribute('aria-label') || '').trim();
            return p === '/login' || /ورود به فیلو|ورود به حساب|login/i.test(t);
          });
          return a ? a.href : '';
        }"""
    )
    page.goto(sign_in_href or FILO_ORIGIN + FILO_LOGIN_PATH,
              wait_until="domcontentloaded", timeout=30_000)
    password_field = page.locator("input[type='password']").first
    try:
        password_field.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise FiloUploadError("filo_login_password_field_missing") from exc

    username_selectors = [
        'input[autocomplete="username"]',
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[name*="mobile" i]',
        'input[placeholder*="شماره"]',
        'input[placeholder*="موبایل"]',
        'input[placeholder*="ایمیل"]',
        'input[type="email"]',
        'input[name*="user" i]',
        'input[name*="email" i]',
        'input[type="text"]',
    ]
    password_form = password_field.locator("xpath=ancestor::form[1]")
    username_field = _visible_first(password_form, username_selectors)
    if username_field is None:
        username_field = _visible_first(page, username_selectors)
    if username_field is None:
        raise FiloUploadError("filo_login_username_field_missing")
    username_field.fill(username)
    password_field.fill(password)
    username_field.press("Tab")
    password_field.press("Tab")

    submit = _visible_first(page, ["button[type='submit']", "input[type='submit']"])
    if submit is None:
        submit = page.get_by_role("button", name=re.compile(r"^ورود$|^login$", re.I)).first
    if not submit.count() or not submit.is_visible():
        raise FiloUploadError("filo_login_submit_not_ready")
    enabled = False
    for _ in range(24):
        enabled = submit.is_enabled()
        if enabled:
            break
        time.sleep(0.4)
    if not enabled:
        raise FiloUploadError("filo_login_submit_stayed_disabled")

    login_response = None
    try:
        with page.expect_response(
            lambda response: (
                urlparse(response.url).hostname == "ifilo.net"
                and urlparse(response.url).path == "/api/v1/users/login"
                and response.request.method == "POST"
            ),
            timeout=15_000,
        ) as response_info:
            submit.click()
        login_response = response_info.value
    except PlaywrightTimeoutError:
        # Some Filo front-end revisions do not expose the response to the page waiter;
        # the protected upload route below remains the authority for login success.
        pass

    if login_response is not None:
        payload = _response_payload(login_response)
        if login_response.status >= 400 or (
            any(key in payload for key in ("success", "status", "s"))
            and not _success_flag(payload.get("s", payload.get("success", payload.get("status"))))
        ):
            raise FiloUploadError("filo_login_rejected")

    time.sleep(1.5)
    body = page.locator("body").inner_text(timeout=5_000)
    if re.search(r"کد تایید|کد تأیید|رمز یکبار مصرف|captcha|verify you are human|تایید هویت", body, re.I):
        raise FiloUploadError("filo_login_challenge_required")

    upload_response = page.goto(FILO_ORIGIN + FILO_UPLOAD_PATH,
                                wait_until="domcontentloaded", timeout=30_000)
    if upload_response is not None and upload_response.status >= 400:
        raise FiloUploadError("filo_upload_route_access_denied")
    if urlparse(page.url).path.startswith("/login"):
        raise FiloUploadError("filo_login_not_confirmed")

    evidence = page.evaluate(
        """() => ({
          path: location.pathname,
          body: (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 1600),
          logout: Array.from(document.querySelectorAll('a')).some(a =>
            /خروج|logout|sign.?out/i.test((a.innerText || '') + ' ' + (a.getAttribute('href') || ''))),
          password: Array.from(document.querySelectorAll('input[type="password"]')).some(x => x.offsetParent !== null)
        })"""
    )
    if (
        not str(evidence.get("path") or "").startswith("/upload")
        or evidence.get("password")
        or re.search(r"اول باید به حساب کاربریت ورود کنی|ورود به فیلو|ورود به حساب", evidence.get("body", ""), re.I)
    ):
        raise FiloUploadError("filo_login_not_confirmed")


def verify_filo_login(*, env: Mapping[str, str] | None = None) -> dict:
    """Verify the account can access Filo's upload page without uploading anything."""
    source = env if env is not None else os.environ
    username = str(source.get("FILO_USER", "")).strip()
    password = str(source.get("FILO_PASS", "")).strip()
    if not username or not password:
        raise FiloUploadError("filo_credentials_missing")

    from playwright.sync_api import sync_playwright

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                locale="fa-IR",
                viewport={"width": 1365, "height": 1000},
            )
            page = context.new_page()
            page.set_default_timeout(15_000)
            _login(page, username, password)
            return {
                "status": "login_verified",
                "upload_route_available": urlparse(page.url).path.startswith("/upload"),
            }
    except FiloUploadError:
        raise
    except Exception as exc:
        raise FiloUploadError("filo_login_check_unexpected") from exc
    finally:
        if context is not None:
            try:
                context.clear_cookies()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def upload_filo_video(
    video_path: str | Path,
    title: str,
    description: str = "",
    *,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Upload one OfferChin MP4 to Filo and verify its resulting account status.

    A missing publish response after clicking the final button is treated as an
    unknown outcome. The caller must not automatically retry such a submission.
    """
    source = env if env is not None else os.environ
    username = str(source.get("FILO_USER", "")).strip()
    password = str(source.get("FILO_PASS", "")).strip()
    if not username or not password:
        raise FiloUploadError("filo_credentials_missing")
    path = Path(video_path)
    clean_title = re.sub(r"\s+", " ", str(title or "").strip())[:180]
    clean_description = str(description or "").strip()[:1_800]
    if not path.is_file() or path.stat().st_size < 1_024 or path.suffix.lower() != ".mp4":
        raise FiloUploadError("filo_video_file_invalid")
    if not clean_title or len(clean_title) < 5:
        raise FiloUploadError("filo_video_title_invalid")

    # Keep validation-only calls and unit tests independent from the browser runtime.
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    temporary_dir = tempfile.TemporaryDirectory(prefix="offerchin-filo-")
    browser = None
    context = None
    submission_started = False
    try:
        cover_path = _extract_cover(path, Path(temporary_dir.name))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                locale="fa-IR",
                viewport={"width": 1365, "height": 1000},
                accept_downloads=True,
            )
            page = context.new_page()
            page.set_default_timeout(15_000)
            observed_upload_responses = []
            page.on("response", lambda response: observed_upload_responses.append({
                "path": urlparse(response.url).path,
                "status": response.status,
                "method": response.request.method,
            }) if response.request.method != "GET" and
                 re.search(r"uploadFromFile", urlparse(response.url).path, re.I) else None)

            _login(page, username, password)

            # Snapshot existing posts before the attempt; never mistake an old video
            # with a similar title for the newly submitted item.
            page.goto(FILO_ORIGIN + FILO_MY_VIDEOS_PATH,
                      wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.0)
            existing_links = {item["href"] for item in _safe_video_links(page)}
            page.goto(FILO_ORIGIN + FILO_UPLOAD_PATH,
                      wait_until="domcontentloaded", timeout=30_000)
            device_option = page.get_by_text(re.compile(r"از دستگاه.{0,8}ت")).first
            if device_option.count() and device_option.is_visible():
                device_option.click()
                time.sleep(0.6)

            video_input = page.locator("#fileInput").first
            if not video_input.count():
                video_input = page.locator("input[type='file'][accept*='video']").first
            if not video_input.count():
                try:
                    page.locator("input[type='file']").first.wait_for(state="attached", timeout=8_000)
                except PlaywrightTimeoutError:
                    pass
                video_input = page.locator("#fileInput").first
                if not video_input.count():
                    video_input = page.locator("input[type='file'][accept*='video']").first
            if not video_input.count():
                raise FiloUploadError("filo_video_file_input_missing")
            video_input.set_input_files(str(path))

            title_field = None
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                title_field = _find_title_field(page)
                if title_field is not None:
                    break
                body = page.locator("body").inner_text(timeout=5_000)
                if re.search(r"خطا در بارگذاری|فایل بیش از حد مجاز|فرمت فایل نامعتبر|آپلود ناموفق", body):
                    raise FiloUploadError("filo_video_transfer_rejected")
                time.sleep(1.0)
            upload_responses = [
                item for item in observed_upload_responses
                if item["method"] == "POST" and re.search(r"uploadFromFile", item["path"], re.I)
            ]
            if any(item["status"] >= 400 for item in upload_responses):
                raise FiloUploadError("filo_video_transfer_rejected")
            if title_field is None:
                code = "filo_video_transfer_incomplete" if upload_responses else "filo_video_transfer_not_confirmed"
                raise FiloUploadError(code)

            title_field.fill(clean_title)
            description_field = _find_description_field(page)
            if description_field is not None and description_field.is_visible():
                description_field.fill(clean_description)

            # Filo's uploader requires the thumbnail to be uploaded and selected.
            tile = page.locator("#uploadVideoThumb").first
            if not tile.count():
                raise FiloUploadError("filo_thumbnail_tile_missing")
            thumb_input = _visible_first(page, [
                "#uploadVideoThumb input[type='file']",
                "input[type='file']#dut",
                "input[type='file'][name='dut']",
                "#uploadVideoThumb input[accept*='image']",
                "input[type='file'][accept*='image']",
            ])
            if thumb_input is None:
                thumb_input = page.locator(
                    "#uploadVideoThumb input[type='file'], input[type='file']#dut, "
                    "input[type='file'][name='dut'], input[type='file'][accept*='image']"
                ).first
            if not thumb_input.count():
                raise FiloUploadError("filo_thumbnail_file_input_missing")
            try:
                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and re.search(r"upload(?:VideoThumb|EditorImageVideo)", urlparse(response.url).path, re.I),
                    timeout=30_000,
                ) as thumb_response_info:
                    thumb_input.set_input_files(str(cover_path))
                thumb_response = thumb_response_info.value
            except PlaywrightTimeoutError as exc:
                raise FiloUploadError("filo_thumbnail_upload_not_confirmed") from exc
            thumb_payload = _response_payload(thumb_response)
            if thumb_response.status >= 400 or (
                "s" in thumb_payload and not _success_flag(thumb_payload.get("s"))
            ):
                raise FiloUploadError("filo_thumbnail_upload_rejected")
            tile_heading = tile.locator("h3").first
            if tile_heading.count() and tile_heading.is_visible():
                tile_heading.click()
            else:
                tile.click(position={"x": 18, "y": 18})
            time.sleep(0.5)
            if not re.search(r"\bselected\b", tile.get_attribute("class") or ""):
                raise FiloUploadError("filo_thumbnail_not_selected")

            publish_button = _find_publish_button(page)
            if publish_button is None:
                raise FiloUploadError("filo_publish_button_not_found")

            # From this point onward, a lost response must never trigger an automatic
            # duplicate submission. Mark the boundary before the click, not after it.
            submission_started = True
            publish_response = None
            try:
                with page.expect_response(
                    lambda response: (
                        urlparse(response.url).hostname == "ifilo.net"
                        and urlparse(response.url).path == FILO_PUBLISH_PATH
                        and response.request.method == "POST"
                    ),
                    timeout=35_000,
                ) as publish_response_info:
                    publish_button.click()
                publish_response = publish_response_info.value
            except PlaywrightTimeoutError:
                return {
                    "status": "upload_result_unknown",
                    "error_code": "filo_publish_response_missing",
                    "submission_started": True,
                    "public_url": "",
                }

            payload = _response_payload(publish_response)
            accepted = _success_flag(payload.get("s"))
            if publish_response.status >= 500:
                return {
                    "status": "upload_result_unknown",
                    "error_code": "filo_publish_server_error_after_submit",
                    "http_status": publish_response.status,
                    "submission_started": True,
                    "public_url": "",
                }
            if publish_response.status in {401, 403, 408, 425, 429}:
                return {
                    "status": "retry",
                    "error_code": f"filo_publish_http_{publish_response.status}",
                    "http_status": publish_response.status,
                    "submission_started": True,
                    "public_url": "",
                }
            if publish_response.status >= 400 or not accepted:
                return {
                    "status": "rejected_by_filo",
                    "error_code": "filo_publish_not_accepted",
                    "http_status": publish_response.status,
                    "submission_started": True,
                    "public_url": "",
                }

            time.sleep(4.0)
            current_url = page.url.split("?", 1)[0]
            fresh_link = None
            if (
                urlparse(current_url).hostname in {"ifilo.net", "www.ifilo.net"}
                and re.match(r"^/(?:v|video)/", urlparse(current_url).path)
                and current_url not in existing_links
            ):
                fresh_link = {"href": current_url, "text": "", "cardText": ""}
            if fresh_link is None:
                page.goto(FILO_ORIGIN + FILO_MY_VIDEOS_PATH,
                          wait_until="domcontentloaded", timeout=30_000)
                time.sleep(2.0)
                links = [
                    item for item in _safe_video_links(page)
                    if item["href"] not in existing_links
                ]
                matches = [
                    item for item in links
                    if _title_matches(item.get("text", "") + " " + item.get("cardText", ""), clean_title)
                ]
                fresh_link = matches[0] if matches else (links[0] if len(links) == 1 else None)

            if fresh_link is None:
                return {
                    "status": "submitted_unconfirmed",
                    "error_code": "filo_publish_accepted_public_url_unconfirmed",
                    "http_status": publish_response.status,
                    "submission_started": True,
                    "public_url": "",
                }

            card_text = str(fresh_link.get("cardText") or fresh_link.get("text") or "")
            pending = any(marker in card_text for marker in FILO_PENDING_MARKERS)
            active = bool(re.search(r"(?:^|\s)فعال(?:\s|$)", card_text)) and not pending
            public_url = fresh_link["href"]
            return {
                "status": "published" if active else "submitted_pending_approval",
                "error_code": "",
                "http_status": publish_response.status,
                "submission_started": True,
                "public_url": public_url,
                "video_code": urlparse(public_url).path.rsplit("/", 1)[-1],
                "visibility": "public" if active else "pending_review",
            }
    except FiloUploadError:
        raise
    except Exception as exc:
        # The caller uses this flag to suppress a retry after the final submit click.
        code = "filo_upload_unexpected_after_submit" if submission_started else "filo_upload_unexpected"
        raise FiloUploadError(code, submission_started=submission_started) from exc
    finally:
        if context is not None:
            try:
                context.clear_cookies()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        temporary_dir.cleanup()
