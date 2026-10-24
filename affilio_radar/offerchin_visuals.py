"""Shared OfferChin artwork primitives for image posts and animated shorts."""
from __future__ import annotations

import math
from pathlib import Path
from functools import lru_cache


def _sale_font(size: int):
    """Find a bold Latin font for clear, readable percentage labels."""
    for font_path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(font_path).is_file():
            try:
                from PIL import ImageFont
                return ImageFont.truetype(font_path, size=max(10, int(size)))
            except OSError:
                pass
    from PIL import ImageFont
    return ImageFont.load_default()


def draw_discount_burst(draw, left: int, top: int, width: int, height: int, discount: int) -> None:
    """Draw a red comic-burst sticker with a golden discount percentage and OFF label."""
    width, height = int(width), int(height)
    if width < 50 or height < 45 or not 0 < int(discount) <= 100:
        return

    center_x = left + width / 2
    center_y = top + height / 2
    points = []
    spikes = 14
    for index in range(spikes * 2):
        angle = -math.pi / 2 + index * math.pi / spikes
        outer = index % 2 == 0
        radius_x = width * (0.50 if outer else 0.405)
        radius_y = height * (0.50 if outer else 0.405)
        points.append((
            round(center_x + math.cos(angle) * radius_x),
            round(center_y + math.sin(angle) * radius_y),
        ))

    # An offset charcoal shadow and double outline give the sticker depth.
    draw.polygon([(x + 6, y + 8) for x, y in points], fill=(25, 10, 10))
    draw.polygon(points, fill=(196, 8, 12), outline=(255, 255, 244), width=max(2, min(width, height) // 34))
    draw.line(points + [points[0]], fill=(255, 216, 35), width=max(2, min(width, height) // 52), joint="curve")

    percentage = f"{int(discount)}%"
    percentage_size = max(13, int(height * 0.34))
    percentage_font = _sale_font(percentage_size)
    while percentage_size > max(12, int(height * 0.20)):
        bbox = draw.textbbox((0, 0), percentage, font=percentage_font, stroke_width=1)
        if bbox[2] - bbox[0] <= width * 0.80:
            break
        percentage_size -= 2
        percentage_font = _sale_font(percentage_size)

    draw.text(
        (round(center_x), round(top + height * 0.41)),
        percentage,
        font=percentage_font,
        fill=(255, 222, 36),
        anchor="mm",
        stroke_width=max(1, min(width, height) // 60),
        stroke_fill=(105, 0, 0),
    )
    off_font = _sale_font(max(11, int(height * 0.15)))
    draw.text(
        (round(center_x), round(top + height * 0.70)),
        "OFF",
        font=off_font,
        fill=(255, 237, 82),
        anchor="mm",
        stroke_width=max(1, min(width, height) // 75),
        stroke_fill=(105, 0, 0),
    )




# Official first-party retailer assets are stored in the repository. Normal rendering
# reads these local files only: a temporary CDN outage can never remove a logo.
_RETAILER_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "retailer-logos"
_LOCAL_LOGO_PATHS = {
    "digikala": _RETAILER_LOGO_DIR / "digikala-official.webp",
    "snappshop": _RETAILER_LOGO_DIR / "snappshop-official.webp",
}


def adaptive_text_colors(image, region, threshold: int = 145):
    """Choose readable foreground and opposing outline from pixels behind the text.

    Returns (text_fill, text_stroke), each an RGB tuple. No panel is drawn.
    """
    try:
        x0, y0, x1, y1 = (int(value) for value in region)
        width, height = image.size
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("empty text-background sample")
        gray = image.crop((x0, y0, x1, y1)).convert("RGB").convert("L")
        histogram = gray.histogram()
        count = sum(histogram)
        midpoint = (count - 1) // 2
        cumulative = 0
        median_luminance = 145
        for luminance, frequency in enumerate(histogram):
            cumulative += frequency
            if cumulative > midpoint:
                median_luminance = luminance
                break
        if median_luminance < int(threshold):
            return (255, 255, 255), (12, 15, 18)
        return (18, 23, 28), (255, 255, 255)
    except Exception:
        return (255, 255, 255), (12, 15, 18)


def _decode_retailer_logo(content: bytes, is_snappshop: bool):
    """Decode the complete official retailer artwork without recoloring or stripping its background."""
    from io import BytesIO
    from PIL import Image

    if not content or len(content) > 3_000_000:
        return None

    image_bytes = content
    is_svg = content.lstrip().startswith(b"<svg") or b"<svg" in content[:500]
    if is_svg:
        try:
            import cairosvg
            image_bytes = cairosvg.svg2png(bytestring=image_bytes, output_width=900)
        except Exception:
            return None

    try:
        with Image.open(BytesIO(image_bytes)) as raw:
            raw.load()
            logo = raw.convert("RGBA")
    except Exception:
        return None

    if logo.width < 2 or logo.height < 2 or logo.getbbox() is None:
        return None
    return logo.copy()


@lru_cache(maxsize=2)
def _load_retailer_logo(is_snappshop: bool):
    """Read only the committed retailer files; never fetch assets during publishing."""
    key = "snappshop" if is_snappshop else "digikala"
    path = _LOCAL_LOGO_PATHS[key]
    try:
        if path.is_file():
            return _decode_retailer_logo(path.read_bytes(), is_snappshop)
    except Exception as exc:
        print(f"RETAILER_LOGO_LOCAL_READ_FAILED store={key} error={type(exc).__name__}")
    print(f"RETAILER_LOGO_LOCAL_ASSET_UNAVAILABLE store={key} path={path.name}")
    return None


def draw_retailer_badge(image, left: int, top: int, width: int, height: int, merchant: str) -> None:
    """Place the complete official retailer logo, preserving its original color and background tile."""
    from PIL import Image, ImageOps

    store = str(merchant or "").strip().lower()
    is_snappshop = "snapp" in store or "اسنپ" in store
    logo = _load_retailer_logo(is_snappshop)
    if logo is None:
        return

    target_width = max(1, int(width))
    target_height = max(1, int(height))
    # Scale the full supplied artwork proportionally. The tile/background is part of
    # each official logo and must never be removed, recolored, or replaced by a redraw.
    fitted = ImageOps.contain(
        logo, (target_width, target_height), method=Image.Resampling.LANCZOS
    )
    if fitted.width < 1 or fitted.height < 1:
        return

    x = int(left)
    y = int(top) + max(0, (target_height - fitted.height) // 2)
    if image.mode == "RGBA":
        image.alpha_composite(fitted, (x, y))
    else:
        image.paste(fitted, (x, y), fitted.getchannel("A"))
