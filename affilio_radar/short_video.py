#!/usr/bin/env python3
"""Generate short vertical OfferChin product videos for configured video destinations.

The overlay contains the discount badge and two platform-marked channel IDs only.
A valid deadline is required; expired YouTube videos can be switched to private.
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
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


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
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
    description: str | None = None,
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




def build_vertical_poster(image_bytes: bytes, discount_percent: object = None) -> bytes:
    """Create a 9:16 poster from the product image without adding product copy or price."""
    with Image.open(BytesIO(image_bytes)) as raw:
        raw.load()
        product = raw.convert("RGB")

    background = ImageOps.fit(product, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=34)).convert("RGBA")
    background = Image.alpha_composite(
        background,
        Image.new("RGBA", (WIDTH, HEIGHT), (9, 18, 16, 142)),
    )
    draw = ImageDraw.Draw(background)

    # A clean card presents the unmodified product photo on a subdued background.
    card = (34, 132, WIDTH - 34, 1000)
    draw.rounded_rectangle(
        (card[0] + 5, card[1] + 9, card[2] + 5, card[3] + 9),
        radius=30,
        fill=(0, 0, 0, 70),
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
        # Keep the badge at the upper-right, with a little breathing room from the edges.
        badge_width, badge_height = 218, 160
        left, top = WIDTH - 34 - badge_width, 142
        draw_discount_burst(draw, left, top, badge_width, badge_height, discount)

    # Match the lower-left watermark area used on channel images, with both IDs on separate lines.
    footer = (34, 1040, 430, 1190)
    draw.rounded_rectangle(footer, radius=22, fill=(14, 28, 22, 232), outline=(255, 255, 255, 230), width=2)
    watermark_font = _font(23)
    _draw_telegram_logo(draw, 56, 1056, 36)
    draw.text((103, 1074), "T.me/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")
    _draw_bale_logo(draw, 56, 1124, 36)
    draw.text((103, 1142), "ble.ir/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")

    output = BytesIO()
    background.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_short_video(
    image_bytes: bytes,
    discount_percent: object,
    output_path: str | Path,
    *,
    ffmpeg_binary: str | None = None,
    duration_seconds: int = DURATION_SECONDS,
    fps: int = FPS,
) -> Path:
    """Render a moving 9:16 MP4 with an original, upbeat synthesized instrumental."""
    target = Path(output_path)
    if target.suffix.lower() != ".mp4":
        raise ValueError("video output path must end in .mp4")
    duration = max(5, min(12, int(duration_seconds)))
    frame_rate = max(12, min(30, int(fps)))
    frame_count = duration * frame_rate
    binary = ffmpeg_binary or os.getenv("FFMPEG_BINARY", "ffmpeg")
    poster = build_vertical_poster(image_bytes, discount_percent)
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
    response.raise_for_status()
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
        "پیشنهادهای کاربردی و تخفیف‌های منتخب دیجی‌کالا را در آفِرچین دنبال کنید.\n"
        "قیمت، موجودی و شرایط تخفیف ممکن است تغییر کند؛ پیش از خرید، اطلاعات روز محصول را در دیجی‌کالا بررسی کنید.\n\n"
        "کانال‌های آفِرچین:\n"
        "تلگرام: https://t.me/OfferChin\n"
        "بله: https://ble.ir/OfferChin"
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
    init.raise_for_status()
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
    uploaded.raise_for_status()
    result = uploaded.json()
    video_id = str(result.get("id") or "").strip()
    if not video_id:
        raise RuntimeError("YouTube upload response did not contain a video ID")
    return {"video_id": video_id, "title": video_title, "url": f"https://www.youtube.com/shorts/{video_id}"}


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
    response.raise_for_status()
    return True
