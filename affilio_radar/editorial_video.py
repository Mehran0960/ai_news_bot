"""Render non-commercial OfferChin editorial cards and short videos."""
from __future__ import annotations

import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from offerchin_audio import write_original_soundtrack
from short_video import (
    HEIGHT, WIDTH, _font, _title_font, _shape_rtl, _rtl_layout_kwargs,
    _wrap_rtl_text, _resolve_ffmpeg_binary,
)

BACKGROUND = (14, 25, 43)
PANEL = (26, 42, 66)
PANEL_ALT = (33, 55, 82)
TEXT = (247, 249, 252)
MUTED = (179, 194, 214)
ACCENT = (255, 190, 74)


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill) -> None:
    shaped = _shape_rtl(text)
    bbox = draw.textbbox((0, 0), shaped, font=font, **_rtl_layout_kwargs())
    width = bbox[2] - bbox[0]
    draw.text(((WIDTH - width) // 2, y), shaped, font=font, fill=fill, **_rtl_layout_kwargs())


def _load_related_product_image(item: dict) -> Image.Image | None:
    """Fetch only a verified DigiKala product photo for a related editorial card."""
    value = str(item.get("related_product_image_url") or "").strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        allowed = (
            host == "digikala.com"
            or host.endswith(".digikala.com")
            or host == "dkstatics-public.digikala.com"
        )
        if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
            return None
        response = requests.get(
            value,
            headers={"User-Agent": "Mozilla/5.0 OfferChinEditorial/1.0", "Accept": "image/avif,image/webp,image/png,image/jpeg"},
            timeout=(5, 12),
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()
        final = urlsplit(response.url)
        final_host = (final.hostname or "").lower()
        if final.scheme != "https" or not (final_host == "digikala.com" or final_host.endswith(".digikala.com")):
            return None
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            return None
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > 6_000_000:
            return None
        data = bytearray()
        for chunk in response.iter_content(64_000):
            if not chunk:
                continue
            data.extend(chunk)
            if len(data) > 6_000_000:
                return None
        image = Image.open(BytesIO(bytes(data)))
        image.load()
        if image.width < 180 or image.height < 120:
            return None
        return image.convert("RGB")
    except Exception:
        return None


def _draw_topic_illustration(draw: ImageDraw.ImageDraw, topic: str) -> None:
    """Draw original topic-specific artwork when no cleared related photo exists."""
    center = WIDTH // 2
    top = 230
    topic = str(topic or "").strip().lower()
    if topic in {"delivery", "parcel-check"}:
        left, right, bottom = center - 112, center + 112, top + 184
        draw.rounded_rectangle((left, top + 42, right, bottom), radius=22,
                               fill=PANEL_ALT, outline=ACCENT, width=7)
        draw.polygon([
            (left, top + 62), (center, top + 118),
            (right, top + 62), (center, top + 8),
        ], fill=(43, 68, 98), outline=ACCENT)
        draw.line((center, top + 9, center, bottom - 2), fill=ACCENT, width=7)
        draw.line((left + 7, top + 63, center, top + 118), fill=ACCENT, width=5)
        draw.line((right - 7, top + 63, center, top + 118), fill=ACCENT, width=5)
        draw.rounded_rectangle((center - 23, top + 12, center + 23, top + 67),
                               radius=8, fill=ACCENT)
        return
    if topic in {"security", "account-security", "privacy", "privacy-and-security"}:
        points = [
            (center, top + 8), (center + 112, top + 52),
            (center + 94, top + 151), (center, top + 205),
            (center - 94, top + 151), (center - 112, top + 52),
        ]
        draw.polygon(points, fill=PANEL_ALT, outline=ACCENT)
        draw.line((center - 48, top + 104, center - 10, top + 142, center + 58, top + 74),
                  fill=ACCENT, width=13, joint="curve")
        return
    if topic in {"mobile", "device-compatibility"}:
        draw.rounded_rectangle((center - 82, top, center + 82, top + 212),
                               radius=30, fill=PANEL_ALT, outline=ACCENT, width=8)
        draw.rounded_rectangle((center - 56, top + 26, center + 56, top + 171),
                               radius=10, fill=BACKGROUND, outline=MUTED, width=3)
        draw.ellipse((center - 9, top + 184, center + 9, top + 202), fill=ACCENT)
        return
    draw.rounded_rectangle((center - 122, top + 78, center + 122, top + 190),
                           radius=18, fill=PANEL_ALT, outline=ACCENT, width=8)
    draw.line((center - 86, top + 78, center - 48, top + 10), fill=ACCENT, width=9)
    draw.line((center + 86, top + 78, center + 48, top + 10), fill=ACCENT, width=9)
    for x in (center - 58, center, center + 58):
        draw.line((x, top + 92, x, top + 178), fill=MUTED, width=5)


def render_editorial_poster(item: dict, output_path: str | Path | None = None) -> bytes:
    """Create a Persian editorial card; use the upcoming product's verified image when available."""
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if not title or not body:
        raise ValueError("editorial_title_and_body_required")

    related_image = _load_related_product_image(item)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((34, 42, WIDTH - 34, HEIGHT - 42), radius=34, fill=PANEL)
    draw.rounded_rectangle((58, 68, WIDTH - 58, 156), radius=24, fill=PANEL_ALT)
    _draw_centered(draw, "آفِرچین | راهنمای کاربردی", 91, _font(34, True), TEXT)
    draw.rounded_rectangle((WIDTH // 2 - 84, 184, WIDTH // 2 + 84, 194), radius=5, fill=ACCENT)

    if related_image is not None:
        photo_box = (72, 220, WIDTH - 72, 545)
        photo = ImageOps.fit(
            related_image,
            (photo_box[2] - photo_box[0], photo_box[3] - photo_box[1]),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        photo = ImageEnhance.Color(photo).enhance(0.88)
        photo = ImageEnhance.Contrast(photo).enhance(1.06)
        canvas.paste(photo, (photo_box[0], photo_box[1]))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(photo_box, radius=26, outline=ACCENT, width=4)
        title_y = 586
        title_font = _title_font(43)
        max_body_lines = 5
        body_y = 738
        body_line_gap = 48
    else:
        _draw_topic_illustration(draw, str(item.get("topic") or ""))
        title_y = 448
        title_font = _title_font(44)
        max_body_lines = 6
        body_y = None
        body_line_gap = 50

    title_lines = _wrap_rtl_text(draw, title, title_font, WIDTH - 140, max_lines=2)
    for line in title_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=title_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, title_y), shaped,
                  font=title_font, fill=ACCENT, **_rtl_layout_kwargs())
        title_y += 58 if related_image else 66

    body_font = _font(27, False)
    body_lines = _wrap_rtl_text(
        draw, body, body_font, WIDTH - 140, max_lines=max_body_lines
    )
    if body_y is None:
        body_y = max(470, title_y + 28)
    for line in body_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=body_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, body_y), shaped,
                  font=body_font, fill=TEXT, **_rtl_layout_kwargs())
        body_y += body_line_gap

    source_count = len(item.get("sources") or [])
    _draw_centered(draw, f"مبنای مطلب: {source_count} منبع", HEIGHT - 218, _font(24, False), MUTED)
    draw.line((100, HEIGHT - 176, WIDTH - 100, HEIGHT - 176), fill=(70, 91, 119), width=2)
    _draw_centered(draw, "t.me/OfferChin  |  ble.ir/OfferChin", HEIGHT - 142, _font(23, True), TEXT)

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return data


def render_editorial_video(
    item: dict,
    output_path: str | Path,
    *,
    duration_seconds: int = 10,
    fps: int = 24,
    ffmpeg_binary: str | None = None,
) -> Path:
    """Render a short vertical explainer card with the project's original soundtrack."""
    target = Path(output_path)
    if target.suffix.lower() != ".mp4":
        raise ValueError("editorial video output path must end in .mp4")
    duration = max(6, min(12, int(duration_seconds)))
    frame_rate = max(12, min(30, int(fps)))
    poster = render_editorial_poster(item)
    binary = _resolve_ffmpeg_binary(ffmpeg_binary)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="offerchin-editorial-") as directory:
        poster_path = Path(directory) / "poster.png"
        music_path = Path(directory) / "offerchin-original-editorial.wav"
        poster_path.write_bytes(poster)
        write_original_soundtrack(music_path, duration)
        frames = duration * frame_rate
        zoom_filter = (
            "zoompan=z='1.01+0.018*(0.5+0.5*sin(on/34))':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={frame_rate},"
            "eq=saturation=1.04:contrast=1.02,"
            "fade=t=in:st=0:d=0.2,"
            f"fade=t=out:st={max(0.1, duration - 0.4):.3f}:d=0.35,"
            "format=yuv420p"
        )
        command = [
            binary, "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", str(frame_rate), "-i", str(poster_path),
            "-i", str(music_path),
            "-vf", zoom_filter,
            "-af", (
                "loudnorm=I=-16:TP=-1.5:LRA=11,"
                "afade=t=in:st=0:d=0.2,"
                f"afade=t=out:st={max(0.1, duration - 0.45):.3f}:d=0.4"
            ),
            "-map", "0:v:0", "-map", "1:a:0",
            "-frames:v", str(frames), "-r", str(frame_rate),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", str(target),
        ]
        try:
            result = subprocess.run(command, check=False, capture_output=True,
                                    text=True, timeout=180)
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg_not_available") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("editorial_video_render_timeout") from exc
        if result.returncode != 0:
            raise RuntimeError(f"editorial_ffmpeg_failed:{(result.stderr or '')[:300]}")
    if not target.is_file() or target.stat().st_size < 1024:
        raise RuntimeError("editorial_video_artifact_invalid")
    return target
