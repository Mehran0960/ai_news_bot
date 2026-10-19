#!/usr/bin/env python3
"""Generate short vertical OfferChin product videos and publish them via YouTube's official API.

Video overlays intentionally contain only the existing discount badge and the two channel IDs.
A valid deadline is required by the calling workflow; expired videos can be switched to private.
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
        label = f"{discount}% OFF"
        badge_font = _font(27)
        left, top = WIDTH - 42 - 190, 154
        draw.rounded_rectangle((left, top, left + 190, top + 58), radius=17, fill=(22, 163, 74, 255))
        draw.text((left + 95, top + 29), label, font=badge_font, fill=(255, 255, 255, 255), anchor="mm")

    # Match the lower-left watermark area used on channel images, with both IDs on separate lines.
    footer = (34, 1040, 430, 1190)
    draw.rounded_rectangle(footer, radius=22, fill=(14, 28, 22, 232), outline=(255, 255, 255, 230), width=2)
    watermark_font = _font(23)
    draw.text((58, 1074), "T.me/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")
    draw.text((58, 1142), "ble.ir/OfferChin", font=watermark_font, fill=(255, 255, 255, 255), anchor="lm")

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
    """Render a silent 9:16 MP4 with a gentle zoom, using ffmpeg from the runner."""
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
        poster_path.write_bytes(poster)
        zoom_filter = (
            "zoompan="
            "z='min(zoom+0.00022,1.04)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={frame_rate},"
            "format=yuv420p"
        )
        command = [
            binary, "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", str(frame_rate), "-i", str(poster_path),
            "-vf", zoom_filter,
            "-frames:v", str(frame_count),
            "-r", str(frame_rate),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "25",
            "-pix_fmt", "yuv420p",
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
            detail = (result.stderr or "").strip()[:300]
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
    description = (
        "معرفی کوتاه محصول از آفِرچین.\n"
        "قیمت، موجودی و شرایط تخفیف ممکن است تغییر کند؛ پیش از خرید، وضعیت روز محصول را بررسی کنید.\n\n"
        "تخفیف‌های به‌روز در کانال‌های آفِرچین:\n"
        "https://t.me/OfferChin\n"
        "https://ble.ir/OfferChin\n\n"
        "این محتوا در چارچوب همکاری در فروش منتشر شده است؛ ممکن است از خرید واجدشرایط کمیسیون دریافت شود."
    )
    video = {
        "snippet": {
            "title": video_title,
            "description": description,
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
