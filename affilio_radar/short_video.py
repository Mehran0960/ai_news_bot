#!/usr/bin/env python3
# [repair-all-captions] Trigger button restoration without also queueing the cleanup workflow.
"""Generate short vertical OfferChin product videos for configured video destinations.

The overlay contains the discount badge and two platform-marked channel IDs only.
A verified deadline is required; expired platform videos are permanently deleted, with privacy as a failure fallback.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Mapping

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features
from offerchin_visuals import draw_discount_burst
from offerchin_audio import write_original_soundtrack

WIDTH = 720
HEIGHT = 1280
FPS = 24
DURATION_SECONDS = 8
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


# Use exactly one right-to-left layout engine. Pillow's RAQM engine performs
# Arabic shaping and bidirectional ordering itself; the manual reshaper/bidi path
# is used only on runners where RAQM is unavailable.
try:
    PERSIAN_TEXT_RAQM_AVAILABLE = bool(features.check_feature("raqm"))
except Exception:
    PERSIAN_TEXT_RAQM_AVAILABLE = False


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    layout_engine = (
        ImageFont.Layout.RAQM if PERSIAN_TEXT_RAQM_AVAILABLE
        else ImageFont.Layout.BASIC
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(
                candidate, size=size, layout_engine=layout_engine
            )
        except OSError:
            continue
    return ImageFont.load_default()




def _draw_telegram_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 36) -> None:
    """Draw a compact Telegram mark in the standard blue circle."""
    draw.ellipse((x, y, x + size, y + size), fill=(36, 161, 222, 255))
    draw.polygon(
        [
            (x + 7, y + 17),
            (x + size - 6, y + 7),
            (x + size - 12, y + size - 6),
            (x + 16, y + 23),
            (x + 13, y + 29),
            (x + 12, y + 21),
        ],
        fill=(255, 255, 255, 255),
    )
    draw.polygon(
        [(x + 16, y + 23), (x + size - 12, y + 12), (x + 20, y + 27)],
        fill=(190, 230, 247, 255),
    )


def _draw_bale_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 36) -> None:
    """Draw Bale's green round mark with a white check-shaped glyph."""
    draw.ellipse((x, y, x + size, y + size), fill=(0, 184, 148, 255))
    draw.polygon(
        [
            (x + 6, y + 18),
            (x + 11, y + 13),
            (x + 17, y + 19),
            (x + 27, y + 8),
            (x + 32, y + 13),
            (x + 17, y + 29),
        ],
        fill=(255, 255, 255, 255),
    )


def telegram_video_review_available(env: Mapping[str, str] | None = None) -> bool:
    """Whether a private Telegram review destination has explicitly been configured."""
    source = env if env is not None else os.environ
    return bool(
        str(source.get("TELEGRAM_BOT_TOKEN", "")).strip()
        and str(source.get("AFFILIO_VIDEO_REVIEW_CHAT_ID", "")).strip()
    )


def send_telegram_video_review(
    video_path: str | Path,
    title: str,
    discount_percent: object = None,
    *,
    session=None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Send the generated MP4 to a configured private Telegram chat for preview."""
    source = env if env is not None else os.environ
    token = str(source.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(source.get("AFFILIO_VIDEO_REVIEW_CHAT_ID", "")).strip()
    if not token or not chat_id:
        raise RuntimeError("private Telegram video-review credentials are not configured")
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("video review file does not exist or is empty")

    discount_text = ""
    try:
        discount = int(discount_percent)
        if 0 < discount <= 100:
            discount_text = f"\n🏷️ تخفیف ثبت‌شده: {discount}٪"
    except (TypeError, ValueError, OverflowError):
        pass
    caption = (
        "🎬 پیش‌نمایش ویدئوی آفِرچین\n"
        f"🛍️ {str(title or 'محصول پیشنهادی دیجی‌کالا').strip()}"
        f"{discount_text}\n\n"
        "این پیام برای بازبینی اولیه است؛ پیش از انتشار عمومی، تطابق قیمت، موجودی و مهلت پیشنهاد بررسی شود."
    )[:1024]

    http = session or requests.Session()
    with path.open("rb") as handle:
        response = http.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={"chat_id": chat_id, "caption": caption, "supports_streaming": "true"},
            files={"video": (path.name, handle, "video/mp4")},
            timeout=(15, 240),
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram rejected the private video-review upload")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {"message_id": result.get("message_id"), "chat_id": chat_id}




def _rtl_layout_kwargs() -> dict:
    """Return Pillow options for RTL paragraphs when RAQM is available."""
    return {"direction": "rtl"} if PERSIAN_TEXT_RAQM_AVAILABLE else {}


def _shape_rtl(value: object) -> str:
    """Prepare Persian text once; never bidi-reorder text before RAQM processes it."""
    text = str(value or "").strip()
    if not text:
        return ""
    if PERSIAN_TEXT_RAQM_AVAILABLE:
        # RAQM combines Arabic shaping and the Unicode bidi algorithm at draw time.
        # Passing pre-reordered text here applies bidi twice and corrupts word order.
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text), base_dir="R")
    except Exception:
        # The project's dependencies install these libraries; this fallback remains
        # non-fatal on constrained environments, while BASIC avoids double bidi.
        return text


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox(
        (0, 0), _shape_rtl(text), font=font, **_rtl_layout_kwargs()
    )
    return int(bbox[2] - bbox[0])


def _wrap_rtl_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 2,
) -> list[str]:
    """Wrap Persian/Latin mixed product titles to a strict visual width."""
    words = str(text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    truncated = False
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) >= max_lines:
            truncated = True
            current = ""
            break
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        truncated = True
        lines = lines[:max_lines]
    if truncated and lines:
        last = lines[-1].rstrip()
        suffix = "…"
        while last and _text_width(draw, last + suffix, font) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = (last + suffix) if last else suffix
    return lines


def format_persian_price(value: object) -> str:
    """Format a positive integer price with Persian digits and separators."""
    try:
        amount = int(str(value).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError, OverflowError):
        return ""
    if amount <= 0:
        return ""
    latin = f"{amount:,}".replace(",", "٬")
    return latin.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def build_vertical_poster(
    image_bytes: bytes,
    discount_percent: object = None,
    *,
    title: str = "",
    current_price: object = None,
    original_price: object = None,
) -> bytes:
    """Build a self-contained 9:16 product card: name, price, discount and DigiKala CTA."""
    with Image.open(BytesIO(image_bytes)) as raw:
        raw.load()
        product = raw.convert("RGB")

    background = ImageOps.fit(product, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=34)).convert("RGBA")
    background = Image.alpha_composite(
        background,
        Image.new("RGBA", (WIDTH, HEIGHT), (9, 18, 16, 150)),
    )
    draw = ImageDraw.Draw(background)

    # Keep the top clear of channel IDs; the product title leads the frame.
    # Product name is readable without opening the caption.
    title_panel = (34, 34, WIDTH - 34, 150)
    draw.rounded_rectangle(
        (title_panel[0] + 4, title_panel[1] + 6, title_panel[2] + 4, title_panel[3] + 6),
        radius=24,
        fill=(0, 0, 0, 70),
    )
    draw.rounded_rectangle(
        title_panel,
        radius=24,
        fill=(250, 252, 247, 255),
        outline=(130, 220, 150, 255),
        width=3,
    )
    title_font = _font(29)
    title_lines = _wrap_rtl_text(
        draw,
        str(title or "پیشنهاد ویژه دیجی‌کالا"),
        title_font,
        max_width=574,
        max_lines=2,
    )
    line_y = 73 if len(title_lines) == 1 else 65
    for line in title_lines:
        draw.text(
            (WIDTH // 2, line_y),
            _shape_rtl(line),
            font=title_font,
            fill=(17, 57, 34, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )
        line_y += 47

    # Product photo gets its own clean card; all critical selling copy sits outside it.
    card = (34, 164, WIDTH - 34, 678)
    draw.rounded_rectangle(
        (card[0] + 5, card[1] + 9, card[2] + 5, card[3] + 9),
        radius=30,
        fill=(0, 0, 0, 76),
    )
    draw.rounded_rectangle(card, radius=30, fill=(250, 250, 248, 255))
    inner = (card[2] - card[0] - 32, card[3] - card[1] - 32)
    fitted = ImageOps.contain(product, inner, method=Image.Resampling.LANCZOS)
    x = (WIDTH - fitted.width) // 2
    y = card[1] + (card[3] - card[1] - fitted.height) // 2
    background.alpha_composite(fitted.convert("RGBA"), (x, y))
    draw = ImageDraw.Draw(background)

    try:
        discount = int(discount_percent)
    except (TypeError, ValueError, OverflowError):
        discount = 0
    if 0 < discount <= 100:
        badge_width, badge_height = 188, 140
        left, top = WIDTH - 44 - badge_width, 173
        draw_discount_burst(draw, left, top, badge_width, badge_height, discount)

    # Large current price and a crossed-out former price communicate the deal instantly.
    price_panel = (34, 695, WIDTH - 34, 948)
    draw.rounded_rectangle(
        (price_panel[0] + 4, price_panel[1] + 7, price_panel[2] + 4, price_panel[3] + 7),
        radius=26,
        fill=(0, 0, 0, 70),
    )
    draw.rounded_rectangle(
        price_panel,
        radius=26,
        fill=(246, 255, 247, 255),
        outline=(63, 173, 94, 255),
        width=3,
    )
    draw.text(
        (WIDTH // 2, 725),
        _shape_rtl("قیمت ویژه در دیجی‌کالا"),
        font=_font(25),
        fill=(24, 111, 54, 255),
        anchor="mm",
        **_rtl_layout_kwargs(),
    )
    current_text = format_persian_price(current_price)
    if current_text:
        draw.text(
            (WIDTH // 2, 783),
            _shape_rtl(f"{current_text} تومان"),
            font=_font(43),
            fill=(10, 79, 40, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )
    else:
        draw.text(
            (WIDTH // 2, 883),
            _shape_rtl("مشاهده قیمت روز در دیجی‌کالا"),
            font=_font(28),
            fill=(10, 79, 40, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )

    old_amount = format_persian_price(original_price)
    try:
        is_old_price_valid = bool(current_text and old_amount and int(str(original_price).replace(",", "").replace("٬", "")) > int(str(current_price).replace(",", "").replace("٬", "")))
    except (TypeError, ValueError, OverflowError):
        is_old_price_valid = False
    if is_old_price_valid:
        old_line = f"قیمت اصلی: {old_amount} تومان"
        old_font = _font(21)
        old_visual = _shape_rtl(old_line)
        old_bbox = draw.textbbox((WIDTH // 2, 886), old_visual, font=old_font, anchor="mm", **_rtl_layout_kwargs())
        draw.text(
            (WIDTH // 2, 986),
            old_visual,
            font=old_font,
            fill=(92, 102, 95, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )
        draw.line(
            (old_bbox[0] - 2, 986, old_bbox[2] + 2, 986),
            fill=(200, 48, 48, 255),
            width=3,
        )

    # YouTube video frames are not clickable: direct viewers to the channel links.
    social_panel = (34, 970, WIDTH - 34, 1245)
    draw.rounded_rectangle(
        (social_panel[0] + 4, social_panel[1] + 7, social_panel[2] + 4, social_panel[3] + 7),
        radius=28,
        fill=(0, 0, 0, 85),
    )
    draw.rounded_rectangle(
        social_panel,
        radius=28,
        fill=(14, 28, 22, 246),
        outline=(255, 255, 255, 240),
        width=2,
    )
    draw.text(
        (WIDTH // 2, 1000),
        _shape_rtl("لینک خرید: کانال بله و تلگرام"),
        font=_font(23),
        fill=(255, 220, 75, 255),
        anchor="mm",
        **_rtl_layout_kwargs(),
    )
    watermark_font = _font(23)
    _draw_telegram_logo(draw, 56, 1020, 36)
    draw.text((103, 1038), "T.me/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")
    _draw_bale_logo(draw, 56, 1078, 36)
    draw.text((103, 1096), "ble.ir/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")
    draw.text(
        (WIDTH // 2, 1207),
        _shape_rtl("آفِرچین | شکار تخفیف‌های واقعی"),
        font=_font(19),
        fill=(255, 255, 255, 245),
        anchor="mm",
        **_rtl_layout_kwargs(),
    )

    output = BytesIO()
    background.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def _bundled_ffmpeg_binary() -> str | None:
    """Use imageio-ffmpeg's bundled executable when the hosted runner lacks system ffmpeg."""
    try:
        import imageio_ffmpeg
        candidate = str(imageio_ffmpeg.get_ffmpeg_exe() or "").strip()
        if candidate and Path(candidate).is_file():
            return candidate
    except Exception:
        return None
    return None


def _resolve_ffmpeg_binary(configured: str | None = None) -> str:
    preferred = str(configured or os.getenv("FFMPEG_BINARY", "")).strip()
    if preferred:
        if Path(preferred).is_file():
            return preferred
        located = shutil.which(preferred)
        if located:
            return located

    system_binary = shutil.which("ffmpeg")
    if system_binary:
        return system_binary

    bundled = _bundled_ffmpeg_binary()
    if bundled:
        return bundled
    raise RuntimeError("FFmpeg unavailable: install imageio-ffmpeg or provide FFMPEG_BINARY")


def render_short_video(
    image_bytes: bytes,
    discount_percent: object,
    output_path: str | Path,
    *,
    title: str = "",
    current_price: object = None,
    original_price: object = None,
    ffmpeg_binary: str | None = None,
    duration_seconds: int = DURATION_SECONDS,
    fps: int = FPS,
) -> Path:
    """Render a sales-ready 9:16 MP4 with product facts and an original soundtrack."""
    target = Path(output_path)
    if target.suffix.lower() != ".mp4":
        raise ValueError("video output path must end in .mp4")
    duration = max(5, min(12, int(duration_seconds)))
    frame_rate = max(12, min(30, int(fps)))
    frame_count = duration * frame_rate
    binary = _resolve_ffmpeg_binary(ffmpeg_binary)
    poster = build_vertical_poster(
        image_bytes,
        discount_percent,
        title=title,
        current_price=current_price,
        original_price=original_price,
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="offerchin-poster-") as directory:
        poster_path = Path(directory) / "poster.png"
        music_path = Path(directory) / "offerchin-original-jingle.wav"
        poster_path.write_bytes(poster)
        write_original_soundtrack(music_path, duration)

        # Gentle push-in/pull-back and a small drifting pan add a camera feel without
        # moving the product badge or watermark out of frame.
        zoom_filter = (
            "zoompan="
            "z='1.015+0.025*(0.5+0.5*sin(on/31))':"
            "x='iw/2-(iw/zoom/2)+5*sin(on/19)':"
            "y='ih/2-(ih/zoom/2)+7*cos(on/23)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={frame_rate},"
            "eq=saturation=1.08:contrast=1.03,"
            "fade=t=in:st=0:d=0.18,"
            f"fade=t=out:st={max(0.1, duration - 0.36):.3f}:d=0.35,"
            "format=yuv420p"
        )
        audio_filter = (
            "volume=0.84,"
            "afade=t=in:st=0:d=0.18,"
            f"afade=t=out:st={max(0.1, duration - 0.42):.3f}:d=0.40"
        )
        command = [
            binary, "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", str(frame_rate), "-i", str(poster_path),
            "-i", str(music_path),
            "-vf", zoom_filter,
            "-af", audio_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-frames:v", str(frame_count),
            "-r", str(frame_rate),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "24",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(target),
        ]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=180)
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is not installed on the runner") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ffmpeg timed out while rendering the product short") from exc
        if result.returncode != 0:
            detail = (result.stderr or "").strip()[:500]
            raise RuntimeError(f"ffmpeg failed with code {result.returncode}: {detail}")
    if not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError("ffmpeg did not produce a valid MP4 file")
    return target

def _raise_for_youtube_http_error(response, operation: str) -> None:
    """Raise an HTTP error with Google's safe, concise reason/message for diagnostics.

    Never include the request URL or headers: they may contain sensitive values.
    """
    status_code = getattr(response, "status_code", None)
    try:
        status_code = int(status_code) if status_code is not None else None
    except (TypeError, ValueError, OverflowError):
        status_code = None

    if status_code is None or status_code < 400:
        response.raise_for_status()
        return

    payload = {}
    try:
        candidate = response.json()
        if isinstance(candidate, dict):
            payload = candidate
    except (ValueError, TypeError, AttributeError):
        pass

    raw_error = payload.get("error", {})
    error = raw_error if isinstance(raw_error, dict) else {}
    errors = error.get("errors", [])
    first_detail = next((item for item in errors if isinstance(item, dict)), {})
    reason = str(
        first_detail.get("reason")
        or error.get("status")
        or (raw_error if isinstance(raw_error, str) else "")
        or payload.get("error_description")
        or ""
    ).strip()
    message = str(
        first_detail.get("message")
        or error.get("message")
        or payload.get("error_description")
        or ""
    )
    message = " ".join(message.split())[:200]
    detail = f"YouTube {operation} HTTP {status_code}"
    if reason:
        detail += f" reason={reason[:80]}"
    if message:
        detail += f" message={message}"
    raise requests.HTTPError(detail, response=response)


def youtube_credentials_available(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return all(str(source.get(name, "")).strip() for name in (
        "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"
    ))


def _youtube_access_token(session, env: Mapping[str, str]) -> str:
    if not youtube_credentials_available(env):
        raise RuntimeError("YouTube OAuth secrets are not configured")
    response = session.post(
        YOUTUBE_TOKEN_URL,
        data={
            "client_id": env["YOUTUBE_CLIENT_ID"],
            "client_secret": env["YOUTUBE_CLIENT_SECRET"],
            "refresh_token": env["YOUTUBE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=(10, 30),
    )
    _raise_for_youtube_http_error(response, "OAuth token refresh")
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Google OAuth token refresh returned no access token")
    return token


def upload_youtube_video(
    video_path: str | Path,
    title: str,
    discount_percent: object = None,
    *,
    description: str | None = None,
    session=None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Upload a short through YouTube Data API v3 with a refresh-token OAuth credential."""
    source = env if env is not None else os.environ
    http = session or requests.Session()
    token = _youtube_access_token(http, source)
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("YouTube upload file does not exist or is empty")

    title_clean = str(title or "پیشنهاد آفِرچین").strip()
    suffix = ""
    try:
        discount = int(discount_percent)
        if 0 < discount <= 100:
            suffix = f" | {discount}٪ تخفیف"
    except (TypeError, ValueError, OverflowError):
        pass
    video_title = (title_clean + suffix)[:100]
    description_text = str(description or "").strip() or (
        "پیشنهادهای کاربردی و تخفیف‌های منتخب دیجی‌کالا را در آفِرچین دنبال کنید.\n\n"
        "کانال تلگرام:\n"
        "https://t.me/OfferChin\n"
        "کانال بله:\n"
        "https://ble.ir/OfferChin\n"
        "آپارات:\n"
        "https://www.aparat.com/OfferChin"
    )
    video = {
        "snippet": {
            "title": video_title,
            "description": description_text,
            "tags": ["آفرچین", "تخفیف", "پیشنهاد ویژه", "خرید"],
            "categoryId": "22",
            "defaultLanguage": "fa",
        },
        "status": {
            "privacyStatus": str(source.get("YOUTUBE_PRIVACY_STATUS", "public")).strip().lower(),
            "selfDeclaredMadeForKids": False,
        },
    }
    if video["status"]["privacyStatus"] not in {"public", "unlisted", "private"}:
        raise RuntimeError("YOUTUBE_PRIVACY_STATUS must be public, unlisted, or private")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(path.stat().st_size),
    }
    init = http.post(
        YOUTUBE_UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "false"},
        json=video,
        headers=headers,
        timeout=(10, 45),
    )
    _raise_for_youtube_http_error(init, "resumable upload initialization")
    upload_url = str(init.headers.get("Location") or "").strip()
    if not upload_url.startswith("https://www.googleapis.com/upload/youtube/"):
        raise RuntimeError("YouTube did not return a safe resumable-upload URL")

    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "video/mp4",
        "Content-Length": str(path.stat().st_size),
    }
    with path.open("rb") as handle:
        uploaded = http.put(upload_url, data=handle, headers=upload_headers, timeout=(30, 240))
    _raise_for_youtube_http_error(uploaded, "video content upload")
    result = uploaded.json()
    video_id = str(result.get("id") or "").strip()
    if not video_id:
        raise RuntimeError("YouTube upload response did not contain a video ID")
    return {"video_id": video_id, "title": video_title, "url": f"https://www.youtube.com/shorts/{video_id}"}


def update_youtube_video_description(
    video_id: str,
    description: str,
    *,
    session=None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Replace the description of a tracked YouTube video while preserving its other metadata."""
    source = env if env is not None else os.environ
    safe_id = str(video_id or "").strip()
    if not safe_id or not safe_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid YouTube video ID")
    description_text = str(description or "").strip()
    if not description_text:
        raise ValueError("YouTube video description cannot be empty")
    if len(description_text) > 5000:
        raise ValueError("YouTube video description exceeds the 5000-character limit")

    http = session or requests.Session()
    token = _youtube_access_token(http, source)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = http.get(
        YOUTUBE_API_URL,
        params={"part": "snippet", "id": safe_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=(10, 45),
    )
    _raise_for_youtube_http_error(response, "video metadata lookup")
    payload = response.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []
    current = next(
        (item for item in items if isinstance(item, dict) and str(item.get("id") or "") == safe_id),
        None,
    )
    if current is None or not isinstance(current.get("snippet"), dict):
        raise RuntimeError("YouTube did not return metadata for the requested video")

    existing = current["snippet"]
    update_snippet = {}
    # videos.update replaces writable fields in the snippet part, so preserve values we do not
    # intend to change (title, tags, category, language, and any existing localizations).
    for field in ("title", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage"):
        if field in existing:
            update_snippet[field] = existing[field]
    if "title" not in update_snippet or "categoryId" not in update_snippet:
        raise RuntimeError("Existing YouTube metadata omitted required title or category")
    update_snippet["description"] = description_text
    localized = existing.get("localized")
    if isinstance(localized, dict):
        update_snippet["localized"] = {
            language: ({**details, "description": description_text} if isinstance(details, dict) else details)
            for language, details in localized.items()
        }

    updated = http.put(
        YOUTUBE_API_URL,
        params={"part": "snippet"},
        json={"id": safe_id, "snippet": update_snippet},
        headers=headers,
        timeout=(10, 45),
    )
    _raise_for_youtube_http_error(updated, "video description update")
    return True


def delete_youtube_video(video_id: str, *, session=None, env: Mapping[str, str] | None = None) -> str:
    """Permanently delete a tracked YouTube video; return deleted/already_absent."""
    source = env if env is not None else os.environ
    safe_id = str(video_id or "").strip()
    if not safe_id or not safe_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid YouTube video ID")

    http = session or requests.Session()
    token = _youtube_access_token(http, source)
    response = http.delete(
        YOUTUBE_API_URL,
        params={"id": safe_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=(10, 45),
    )
    if response.status_code == 204:
        return "deleted"
    if response.status_code == 404:
        try:
            payload = response.json()
        except (ValueError, TypeError, AttributeError):
            payload = {}
        error_value = payload.get("error") if isinstance(payload, dict) else {}
        error = error_value if isinstance(error_value, dict) else {}
        errors = error.get("errors", [])
        reasons = {
            str(item.get("reason") or "")
            for item in errors if isinstance(item, dict)
        }
        if "videoNotFound" in reasons or str(error.get("status") or "") == "NOT_FOUND":
            return "already_absent"
    _raise_for_youtube_http_error(response, "video deletion")
    raise RuntimeError(f"YouTube delete returned unexpected HTTP {response.status_code}")


def set_youtube_video_private(video_id: str, *, session=None, env: Mapping[str, str] | None = None) -> bool:
    """Make a tracked YouTube video private once its associated time-limited deal expires."""
    source = env if env is not None else os.environ
    safe_id = str(video_id or "").strip()
    if not safe_id or not safe_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid YouTube video ID")
    http = session or requests.Session()
    token = _youtube_access_token(http, source)
    response = http.put(
        YOUTUBE_API_URL,
        params={"part": "status"},
        json={"id": safe_id, "status": {"privacyStatus": "private"}},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=(10, 45),
    )
    _raise_for_youtube_http_error(response, "privacy update")
    return True
