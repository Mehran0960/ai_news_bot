"""Render non-commercial OfferChin editorial cards and short videos."""
from __future__ import annotations

import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

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


def _draw_topic_illustration(draw: ImageDraw.ImageDraw, topic: str) -> None:
    """Draw an original, topic-led illustration; editorial artwork never uses product photos."""
    center = WIDTH // 2
    top = 220
    topic = str(topic or "").strip().lower()

    if topic in {"delivery", "shipping-and-returns", "parcel-check"}:
        left, right, bottom = center - 128, center + 128, top + 204
        draw.rounded_rectangle((left, top + 48, right, bottom), radius=24,
                               fill=PANEL_ALT, outline=ACCENT, width=8)
        draw.polygon([
            (left, top + 68), (center, top + 128),
            (right, top + 68), (center, top + 8),
        ], fill=(43, 68, 98), outline=ACCENT)
        draw.line((center, top + 10, center, bottom - 2), fill=ACCENT, width=8)
        draw.line((left + 8, top + 68, center, top + 128), fill=ACCENT, width=6)
        draw.line((right - 8, top + 68, center, top + 128), fill=ACCENT, width=6)
        return

    if topic in {"privacy-and-security", "security", "account-security", "privacy",
                 "safe-payment", "product-safety", "warranty-and-service"}:
        points = [
            (center, top + 4), (center + 132, top + 54),
            (center + 110, top + 176), (center, top + 238),
            (center - 110, top + 176), (center - 132, top + 54),
        ]
        draw.polygon(points, fill=PANEL_ALT, outline=ACCENT)
        if topic == "safe-payment":
            draw.rounded_rectangle((center - 70, top + 84, center + 70, top + 170),
                                   radius=16, fill=BACKGROUND, outline=TEXT, width=6)
            draw.rectangle((center - 70, top + 106, center + 70, top + 132), fill=ACCENT)
            draw.rounded_rectangle((center - 18, top + 140, center + 18, top + 158),
                                   radius=5, fill=ACCENT)
        else:
            draw.line((center - 55, top + 120, center - 14, top + 164, center + 64, top + 82),
                      fill=ACCENT, width=15, joint="curve")
        return

    if topic in {"mobile", "device-compatibility"}:
        draw.rounded_rectangle((center - 92, top + 2, center + 92, top + 238),
                               radius=34, fill=PANEL_ALT, outline=ACCENT, width=9)
        draw.rounded_rectangle((center - 64, top + 30, center + 64, top + 190),
                               radius=12, fill=BACKGROUND, outline=MUTED, width=3)
        draw.ellipse((center - 11, top + 207, center + 11, top + 229), fill=ACCENT)
        draw.line((center + 104, top + 118, center + 144, top + 118), fill=ACCENT, width=12)
        draw.line((center + 124, top + 98, center + 124, top + 138), fill=ACCENT, width=8)
        return

    if topic in {"product-inspection", "product-condition", "review-literacy",
                 "seller-check", "seller-verification"}:
        draw.ellipse((center - 100, top + 8, center + 106, top + 214),
                     fill=PANEL_ALT, outline=ACCENT, width=13)
        draw.line((center + 78, top + 188, center + 166, top + 276),
                  fill=ACCENT, width=25)
        if topic == "review-literacy":
            star = [
                (center, top + 54), (center + 20, top + 104),
                (center + 76, top + 108), (center + 32, top + 144),
                (center + 46, top + 198), (center, top + 166),
                (center - 46, top + 198), (center - 32, top + 144),
                (center - 76, top + 108), (center - 20, top + 104),
            ]
            draw.polygon(star, fill=ACCENT)
        else:
            draw.rounded_rectangle((center - 48, top + 78, center + 52, top + 142),
                                   radius=12, outline=TEXT, width=6)
            draw.line((center - 28, top + 110, center + 32, top + 110),
                      fill=TEXT, width=6)
        return

    if topic in {"total-cost", "purchase-records"}:
        draw.rounded_rectangle((center - 120, top + 10, center + 110, top + 252),
                               radius=20, fill=PANEL_ALT, outline=ACCENT, width=8)
        draw.line((center - 75, top + 76, center + 62, top + 76), fill=TEXT, width=7)
        draw.line((center - 75, top + 112, center + 42, top + 112), fill=MUTED, width=6)
        draw.line((center - 75, top + 148, center + 62, top + 148), fill=MUTED, width=6)
        for y in (184, 218):
            draw.ellipse((center - 38, top + y - 15, center - 8, top + y + 15),
                         fill=ACCENT)
            draw.line((center + 8, top + y, center + 70, top + y), fill=TEXT, width=6)
        return

    if topic == "fit-and-size":
        draw.rounded_rectangle((center - 150, top + 82, center + 150, top + 160),
                               radius=12, fill=ACCENT)
        for offset in range(-122, 141, 30):
            height = 46 if offset % 60 == -2 or offset % 60 == 0 else 26
            draw.line((center + offset, top + 84, center + offset, top + 84 + height),
                      fill=BACKGROUND, width=6)
        return

    if topic == "maintenance-and-care":
        draw.ellipse((center - 105, top + 25, center + 105, top + 235),
                     fill=PANEL_ALT, outline=ACCENT, width=16)
        draw.ellipse((center - 38, top + 92, center + 38, top + 168),
                     fill=BACKGROUND, outline=TEXT, width=8)
        for angle_x, angle_y in ((0, -132), (132, 0), (0, 132), (-132, 0)):
            draw.line((center + angle_x * 0.72, top + 130 + angle_y * 0.72,
                       center + angle_x, top + 130 + angle_y),
                      fill=ACCENT, width=24)
        return

    # Purchase planning and unknown topics use a neutral shopping-basket motif.
    draw.rounded_rectangle((center - 132, top + 104, center + 132, top + 224),
                           radius=20, fill=PANEL_ALT, outline=ACCENT, width=9)
    draw.line((center - 100, top + 104, center - 48, top + 24), fill=ACCENT, width=11)
    draw.line((center + 100, top + 104, center + 48, top + 24), fill=ACCENT, width=11)
    for x in (center - 60, center, center + 60):
        draw.line((x, top + 120, x, top + 202), fill=MUTED, width=7)


def render_editorial_poster(item: dict, output_path: str | Path | None = None) -> bytes:
    """Create a topic-led Persian editorial card without product photography or source credits."""
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if not title or not body:
        raise ValueError("editorial_title_and_body_required")

    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((34, 42, WIDTH - 34, HEIGHT - 42), radius=34, fill=PANEL)
    draw.rounded_rectangle((58, 68, WIDTH - 58, 156), radius=24, fill=PANEL_ALT)
    _draw_centered(draw, "آفِرچین | راهنمای کاربردی", 91, _font(34, True), TEXT)
    draw.rounded_rectangle((WIDTH // 2 - 84, 184, WIDTH // 2 + 84, 194),
                           radius=5, fill=ACCENT)

    _draw_topic_illustration(draw, str(item.get("topic") or ""))
    title_y = 520
    title_font = _title_font(44)
    title_lines = _wrap_rtl_text(draw, title, title_font, WIDTH - 140, max_lines=2)
    for line in title_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=title_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, title_y), shaped,
                  font=title_font, fill=ACCENT, **_rtl_layout_kwargs())
        title_y += 66

    body_font = _font(27, False)
    body_lines = _wrap_rtl_text(
        draw, body, body_font, WIDTH - 140, max_lines=6
    )
    body_y = max(635, title_y + 24)
    for line in body_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=body_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, body_y), shaped,
                  font=body_font, fill=TEXT, **_rtl_layout_kwargs())
        body_y += 48

    draw.line((100, HEIGHT - 176, WIDTH - 100, HEIGHT - 176),
              fill=(70, 91, 119), width=2)
    _draw_centered(draw, "آفِرچین • انتخاب آگاهانه، خرید بهتر", HEIGHT - 142,
                   _font(23, True), TEXT)

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
