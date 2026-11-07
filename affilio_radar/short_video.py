#!/usr/bin/env python3
# [repair-all-captions] Trigger button restoration without also queueing the cleanup workflow.
"""Generate short vertical OfferChin product videos for configured video destinations.

The overlay contains retailer and DigiPay brand tiles, current price, discount, and top-safe-area channel links.
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
import offerchin_visuals
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features
from offerchin_visuals import (
    draw_discount_burst, draw_digipay_badge, draw_retailer_badge,
    adaptive_text_colors, discount_badge_dimensions_for_reference_bounds,
    public_channel_links, draw_platform_logo, platform_footer_label,
)
from offerchin_audio import write_original_soundtrack

WIDTH = 720
HEIGHT = 1280
FPS = 24
DURATION_SECONDS = 8
TITLE_FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "Lalezar-Regular.ttf"
VIDEO_LOGO_COLUMN_WIDTH = 112
VIDEO_LOGO_TEXT_GAP = 12
VIDEO_LOGO_MAX_WIDTH = 96
VIDEO_PURCHASE_CTA_LABELS = {
    "youtube": "لینک خرید: توضیحات کانال",
    "aparat": "لینک خرید: کپشن ویدئو و توضیحات کانال",
}
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




def _title_font(size: int) -> ImageFont.ImageFont:
    """Load the bundled Persian display face for product headlines."""
    layout_engine = (
        ImageFont.Layout.RAQM if PERSIAN_TEXT_RAQM_AVAILABLE
        else ImageFont.Layout.BASIC
    )
    try:
        if TITLE_FONT_PATH.is_file():
            return ImageFont.truetype(
                str(TITLE_FONT_PATH),
                size=max(10, int(size)),
                layout_engine=layout_engine,
            )
    except OSError as exc:
        print(f"VIDEO_TITLE_FONT_LOAD_FAILED error={type(exc).__name__}")
    return _font(size, bold=True)


def _draw_video_channel_logo(
    draw: ImageDraw.ImageDraw,
    platform: str,
    x: int,
    y: int,
    size: int = 20,
    *,
    canvas: Image.Image | None = None,
    max_width: int = 84,
) -> tuple[int, int]:
    """Use the exact same bundled official platform artwork as product images."""
    if canvas is None:
        canvas = getattr(draw, "_image", None)
    if canvas is None:
        return (0, 0)
    return draw_platform_logo(
        canvas, platform, x, y,
        max_height=size, max_width=max_width, solid_backdrop=False,
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


def video_purchase_cta_text(destination_platform: str) -> str:
    """Return the approved short purchase-location CTA for each video destination."""
    return VIDEO_PURCHASE_CTA_LABELS.get(
        str(destination_platform or "").strip().lower(), ""
    )


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


def format_persian_discount(value: object) -> str:
    """Return a compact Persian discount label with a matching fire emoji."""
    try:
        discount = int(str(value).replace("٪", "").replace("%", "").strip())
    except (TypeError, ValueError, OverflowError):
        return ""
    if not 0 < discount <= 100:
        return ""
    persian = str(discount).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return f"🔥 {persian}٪ تخفیف"


def _draw_discount_flame(draw: ImageDraw.ImageDraw, center_x: int, center_y: int, size: int = 30) -> None:
    """Draw a small, crisp fire-emoji mark without depending on emoji font coverage."""
    cx, cy, radius = int(center_x), int(center_y), max(8, int(size)) // 2
    outer = [
        (cx, cy - radius),
        (cx + radius // 2, cy - radius // 4),
        (cx + radius, cy + radius // 3),
        (cx + radius // 2, cy + radius),
        (cx - radius // 4, cy + radius),
        (cx - radius, cy + radius // 3),
        (cx - radius // 2, cy - radius // 5),
    ]
    draw.polygon(outer, fill=(239, 78, 35, 255))
    inner = [
        (cx + 1, cy - radius // 4),
        (cx + radius // 3, cy + radius // 5),
        (cx + radius // 4, cy + radius * 3 // 4),
        (cx - radius // 4, cy + radius * 3 // 4),
        (cx - radius // 3, cy + radius // 4),
    ]
    draw.polygon(inner, fill=(255, 190, 53, 255))
    core = [
        (cx, cy + radius // 5),
        (cx + radius // 6, cy + radius // 2),
        (cx - radius // 5, cy + radius // 2),
    ]
    draw.polygon(core, fill=(255, 239, 165, 255))


def build_vertical_poster(
    image_bytes: bytes,
    discount_percent: object = None,
    *,
    title: str = "",
    current_price: object = None,
    original_price: object = None,
    merchant: str = "دیجی‌کالا",
    destination_platform: str = "youtube",
) -> bytes:
    """Build a self-contained 9:16 product card with other-platform IDs only."""
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

    # Never publish a video that silently omits the requested official DigiPay logo.
    # The caller records this as a video-only retry; channel photo publication is separate.
    if offerchin_visuals._load_digipay_logo() is None:
        raise RuntimeError("official DigiPay logo unavailable; defer only the video render")

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
    title_font = _title_font(32)
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

    # List every verified public destination except the platform receiving this video.
    # A separate poster is rendered per platform so a destination never lists itself.
    cta_panel = (34, 160, WIDTH - 34, 292)
    draw.rounded_rectangle(
        cta_panel,
        radius=19,
        fill=(246, 255, 247, 248),
        outline=(78, 177, 105, 245),
        width=2,
    )
    channel_font = _font(16)
    channel_color = (17, 77, 43, 255)
    purchase_cta = video_purchase_cta_text(destination_platform)
    if purchase_cta:
        cta_font_size = 19
        cta_font = _font(cta_font_size)
        while _text_width(draw, purchase_cta, cta_font) > 590 and cta_font_size > 15:
            cta_font_size -= 1
            cta_font = _font(cta_font_size)
        draw.text(
            (WIDTH // 2, 175),
            _shape_rtl(purchase_cta),
            font=cta_font,
            fill=channel_color,
            anchor="mm",
            **_rtl_layout_kwargs(),
        )
    video_channels = public_channel_links(destination_platform)
    for index, (platform, url) in enumerate(video_channels):
        # Twenty-pixel logos plus their official-brand padding require a 26px
        # row pitch; this prevents the horizontal YouTube wordmark tile overlapping
        # neighbouring rows while keeping all four destinations in the safe panel.
        row_top = 188 + index * 26
        logo_width, _logo_height = _draw_video_channel_logo(
            draw,
            platform,
            64 + max(0, (VIDEO_LOGO_COLUMN_WIDTH - VIDEO_LOGO_MAX_WIDTH) // 2),
            row_top,
            20,
            canvas=background,
            max_width=VIDEO_LOGO_MAX_WIDTH,
        )
        # Align every ID at one fixed x-coordinate. Official wordmarks have
        # different natural widths; their visual width must not move the ID column.
        label_x = 64 + VIDEO_LOGO_COLUMN_WIDTH + VIDEO_LOGO_TEXT_GAP
        label = platform_footer_label(platform, url)
        draw.text(
            (label_x, row_top + 13),
            label, font=channel_font,
            fill=channel_color, anchor="lm",
        )

    # Product photo gets its own clean card; the CTA strip above remains outside it.
    card = (34, 298, WIDTH - 34, 704)
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

    # Match the channel-image hierarchy inside the actual product-photo bounds:
    # retailer logo upper-left, discount tile upper-right, and DigiPay directly
    # below the retailer logo. Derive all bounds from the fitted photo so portrait,
    # landscape, and square product images keep the same relative placement.
    min_dim = min(fitted.width, fitted.height)
    brand_margin = max(10, int(min_dim * 0.025))
    max_badge_width = max(1, (fitted.width - 2 * brand_margin) // 2)
    retailer_badge_width = min(
        max_badge_width, max(124, min(320, int(min_dim * 0.38)))
    )
    retailer_badge_height = max(48, min(88, int(min_dim * 0.14)))

    retailer_bounds = draw_retailer_badge(
        background,
        x + brand_margin,
        y + brand_margin,
        retailer_badge_width,
        retailer_badge_height,
        merchant,
    )

    try:
        discount_value = int(str(discount_percent).replace("٪", "").replace("%", "").strip())
    except (TypeError, ValueError, OverflowError):
        discount_value = 0
    if 0 < discount_value <= 100:
        discount_width, discount_height = discount_badge_dimensions_for_reference_bounds(
            retailer_badge_width, retailer_badge_height
        )
        discount_left = x + fitted.width - brand_margin - discount_width
        discount_top = y + brand_margin
        draw_discount_burst(
            draw,
            discount_left,
            discount_top,
            min(discount_width, x + fitted.width - discount_left),
            min(discount_height, y + fitted.height - discount_top),
            discount_value,
            merchant=merchant,
        )

    if retailer_bounds:
        retailer_left, retailer_top, retailer_width, retailer_height = retailer_bounds
        digipay_gap = max(4, int(retailer_height * 0.08))
        draw_digipay_badge(
            background,
            retailer_left,
            retailer_top + retailer_height + digipay_gap,
            retailer_width,
            retailer_height,
        )

    # Keep the current price as the primary amount. The discount is shown once,
    # in the upper-right badge that matches the channel-image layout.
    price_panel = (34, 721, WIDTH - 34, 974)
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
        (WIDTH // 2, 751),
        _shape_rtl(f"قیمت ویژه در {merchant}"),
        font=_font(25),
        fill=(24, 111, 54, 255),
        anchor="mm",
        **_rtl_layout_kwargs(),
    )
    current_text = format_persian_price(current_price)
    if current_text:
        draw.text(
            (WIDTH // 2, 809),
            _shape_rtl(f"{current_text} تومان"),
            font=_font(43),
            fill=(10, 79, 40, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )
    else:
        draw.text(
            (WIDTH // 2, 844),
            _shape_rtl(f"مشاهده قیمت روز در {merchant}"),
            font=_font(28),
            fill=(10, 79, 40, 255),
            anchor="mm",
            **_rtl_layout_kwargs(),
        )

    tagline = _shape_rtl("آفِرچین | شکار تخفیف‌های واقعی")
    tagline_font = _font(19)
    tagline_pos = (WIDTH // 2, 1207)
    tagline_bbox = draw.textbbox(tagline_pos, tagline, font=tagline_font, anchor="mm", **_rtl_layout_kwargs())
    tagline_fill, tagline_stroke = adaptive_text_colors(
        background, (tagline_bbox[0] - 5, tagline_bbox[1] - 3, tagline_bbox[2] + 5, tagline_bbox[3] + 3)
    )
    draw.text(
        tagline_pos, tagline, font=tagline_font, fill=tagline_fill, anchor="mm",
        stroke_width=2, stroke_fill=tagline_stroke, **_rtl_layout_kwargs(),
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
    merchant: str = "دیجی‌کالا",
    destination_platform: str = "youtube",
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
        merchant=merchant,
        destination_platform=destination_platform,
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
        "t.me/OfferChin\n"
        "ble.ir/OfferChin\n"
        "rubika.ir/offerchin\n"
        "aparat.com/OfferChin"
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
    """Refuse removal: published YouTube videos are retained permanently by policy."""
    raise RuntimeError("YouTube deletion is disabled by permanent-retention policy")


def set_youtube_video_private(video_id: str, *, session=None, env: Mapping[str, str] | None = None) -> bool:
    """Refuse privacy changes: published YouTube videos must remain published."""
    raise RuntimeError("YouTube privacy changes are disabled by permanent-retention policy")
