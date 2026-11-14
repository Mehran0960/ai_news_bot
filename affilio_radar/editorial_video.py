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


def render_editorial_poster(item: dict, output_path: str | Path | None = None) -> bytes:
    """Create a Persian, non-product poster; never display DigiKala/DigiPay offer marks."""
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if not title or not body:
        raise ValueError("editorial_title_and_body_required")

    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((34, 42, WIDTH - 34, HEIGHT - 42), radius=34, fill=PANEL)
    draw.rounded_rectangle((58, 68, WIDTH - 58, 156), radius=24, fill=PANEL_ALT)
    _draw_centered(draw, "آفِرچین | راهنمای کاربردی", 91, _font(34, True), TEXT)
    draw.rounded_rectangle((WIDTH // 2 - 84, 184, WIDTH // 2 + 84, 194), radius=5, fill=ACCENT)

    title_font = _title_font(48)
    title_lines = _wrap_rtl_text(draw, title, title_font, WIDTH - 140, max_lines=3)
    title_y = 244
    for line in title_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=title_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, title_y), shaped,
                  font=title_font, fill=ACCENT, **_rtl_layout_kwargs())
        title_y += 66

    body_font = _font(29, False)
    body_lines = _wrap_rtl_text(draw, body, body_font, WIDTH - 140, max_lines=11)
    body_y = max(470, title_y + 28)
    for line in body_lines:
        shaped = _shape_rtl(line)
        bbox = draw.textbbox((0, 0), shaped, font=body_font, **_rtl_layout_kwargs())
        draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, body_y), shaped,
                  font=body_font, fill=TEXT, **_rtl_layout_kwargs())
        body_y += 54

    source_count = len(item.get("sources") or [])
    _draw_centered(draw, f"مبنای مطلب: {source_count} منبع", HEIGHT - 218, _font(24, False), MUTED)
    draw.line((100, HEIGHT - 176, WIDTH - 100, HEIGHT - 176), fill=(70, 91, 119), width=2)
    _draw_centered(draw, "برای نکته‌های بیشتر، آفِرچین را دنبال کنید", HEIGHT - 142, _font(23, True), TEXT)

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
