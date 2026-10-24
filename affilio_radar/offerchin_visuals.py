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




# Current DigiKala logo served by DigiKala's own static asset CDN.
# SnappShop's branded symbol is served by its Brandfetch identity record.
_RETAILER_LOGO_URLS = {
    "digikala": (
        "https://dkstatics-public.digikala.com/digikala-static/"
        "0d072059918d0c22b88320554ce4b3e07d0472f2_1746354551.svg"
    ),
    "snappshop": (
        "https://cdn.brandfetch.io/id9SrR5Y27/w/512/h/512/theme/dark/logo.png"
        "?c=1bxid64Mup7aczewSAYMX&t=1695361662415"
    ),
}


@lru_cache(maxsize=2)
def _load_retailer_logo(is_snappshop: bool):
    """Fetch and decode real retailer artwork once per process; a logo outage never blocks a deal."""
    from io import BytesIO
    import requests
    from PIL import Image

    key = "snappshop" if is_snappshop else "digikala"
    try:
        response = requests.get(
            _RETAILER_LOGO_URLS[key],
            timeout=(3.5, 6),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OfferChin/1.0)",
                "Accept": "image/png,image/webp,image/svg+xml,*/*;q=0.8",
                "Referer": "https://snappshop.ir/" if is_snappshop else "https://www.digikala.com/",
            },
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        content = response.content
        if not content or len(content) > 3_000_000:
            return None
        if "svg" in content_type or content.lstrip().startswith(b"<svg") or b"<svg" in content[:500]:
            try:
                import cairosvg
                content = cairosvg.svg2png(bytestring=content, output_width=900)
            except Exception:
                return None
        with Image.open(BytesIO(content)) as raw:
            raw.load()
            logo = raw.convert("RGBA")
        bounds = logo.getchannel("A").getbbox()
        if bounds:
            logo = logo.crop(bounds)
        if logo.width < 2 or logo.height < 2:
            return None
        return logo.copy()
    except Exception:
        # Brand asset hosts are external dependencies; their temporary failure must not stop publishing.
        return None


def draw_retailer_badge(image, left: int, top: int, width: int, height: int, merchant: str) -> None:
    """Place retailer logo artwork on a compact badge; do not fabricate brand marks."""
    from PIL import Image, ImageDraw, ImageOps

    store = str(merchant or "").strip().lower()
    is_snappshop = "snapp" in store or "اسنپ" in store
    brand_color = "#B400AE" if is_snappshop else "#E52332"
    wordmark = "Snapp! Shop" if is_snappshop else "digikala"

    width, height = max(70, int(width)), max(28, int(height))
    right, bottom = left + width, top + height
    radius = max(5, height // 5)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (left + 2, top + 3, right + 2, bottom + 3),
        radius=radius,
        fill="#17251D",
    )
    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=radius,
        fill="#FFFFFF",
        outline=brand_color,
        width=max(1, height // 24),
    )

    pad = max(4, height // 9)
    inner_width = max(1, width - 2 * pad)
    inner_height = max(1, height - 2 * pad)
    logo = _load_retailer_logo(is_snappshop)
    text_left = left + pad

    if logo is not None and logo.width / max(1, logo.height) >= 1.8:
        # A horizontal logo already contains the brand wordmark.
        fitted = ImageOps.contain(logo, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
        image.paste(
            fitted,
            (left + (width - fitted.width) // 2, top + (height - fitted.height) // 2),
            fitted,
        )
        return

    # If the asset is a square brand symbol, keep the original symbol and label it clearly.
    if logo is not None:
        icon_size = min(inner_height, max(18, height - 2 * pad))
        fitted = ImageOps.contain(logo, (icon_size, icon_size), method=Image.Resampling.LANCZOS)
        image.paste(fitted, (text_left, top + (height - fitted.height) // 2), fitted)
        text_left += icon_size + max(4, height // 8)

    available_width = max(1, right - pad - text_left)
    font_size = max(9, int(height * 0.42))
    font = _sale_font(font_size)
    try:
        while font_size > 8 and draw.textbbox((0, 0), wordmark, font=font)[2] > available_width:
            font_size -= 1
            font = _sale_font(font_size)
    except Exception:
        pass
    draw.text(
        (text_left, top + height / 2),
        wordmark,
        font=font,
        fill=brand_color,
        anchor="lm",
    )
