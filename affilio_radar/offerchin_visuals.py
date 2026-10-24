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




# The source files below are official, first-party retailer assets. They are bootstrapped
# once, then committed into the repository so scheduled publishers never need a network
# request to display them.
_RETAILER_LOGO_URLS = {
    "digikala": (
        "https://dkstatics-public.digikala.com/digikala-static/"
        "0d072059918d0c22b88320554ce4b3e07d0472f2_1746354551.svg"
    ),
    "snappshop": (
        "https://cdn.snappshop.ir/customer-production-assets/public/assets/images/"
        "application/icon-72x72.png?q=75&w=96"
    ),
}
_RETAILER_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "retailer-logos"
_LOCAL_LOGO_PATHS = {
    "digikala": _RETAILER_LOGO_DIR / "digikala.svg",
    "snappshop": _RETAILER_LOGO_DIR / "snappshop.png",
}


def _decode_retailer_logo(content: bytes, is_snappshop: bool):
    """Decode a local or downloaded official logo and keep only its brand mark."""
    from io import BytesIO
    from PIL import Image

    if not content or len(content) > 3_000_000:
        return None

    image_bytes = content
    if content.lstrip().startswith(b"<svg") or b"<svg" in content[:500]:
        try:
            import cairosvg
            image_bytes = cairosvg.svg2png(bytestring=content, output_width=900)
        except Exception:
            return None

    try:
        with Image.open(BytesIO(image_bytes)) as raw:
            raw.load()
            logo = raw.convert("RGBA")
    except Exception:
        return None

    bounds = logo.getchannel("A").getbbox()
    if bounds:
        logo = logo.crop(bounds)

    # DigiKala's first-party source is a horizontal wordmark. Keep its official
    # symbol on the left; do not add another textual brand label to the artwork.
    if not is_snappshop and logo.width / max(1, logo.height) >= 1.8:
        mark_width = max(1, min(logo.width, round(logo.height * 1.08)))
        logo = logo.crop((0, 0, mark_width, logo.height))
        bounds = logo.getchannel("A").getbbox()
        if bounds:
            logo = logo.crop(bounds)

    if logo.width < 2 or logo.height < 2:
        return None
    return logo.copy()


@lru_cache(maxsize=2)
def _load_retailer_logo(is_snappshop: bool):
    """Read the persistent local asset first; download only to bootstrap a missing asset."""
    import requests

    key = "snappshop" if is_snappshop else "digikala"
    local_path = _LOCAL_LOGO_PATHS[key]

    # Normal publication path: no external request when the committed file exists.
    try:
        if local_path.is_file():
            logo = _decode_retailer_logo(local_path.read_bytes(), is_snappshop)
            if logo is not None:
                return logo
    except Exception:
        pass

    # One-time bootstrap for a checkout where the asset has not been saved yet.
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
        content = response.content
        logo = _decode_retailer_logo(content, is_snappshop)
        if logo is None:
            return None

        # Saving is best-effort: logo download failures must never block a post.
        # The main workflow stages these files so future scheduled runs read them offline.
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = local_path.with_suffix(local_path.suffix + ".tmp")
            temp_path.write_bytes(content)
            temp_path.replace(local_path)
        except Exception:
            pass
        return logo
    except Exception:
        return None


def draw_retailer_badge(image, left: int, top: int, width: int, height: int, merchant: str) -> None:
    """Draw the official retailer symbol only, with no added platform-name wordmark."""
    from PIL import Image, ImageDraw, ImageOps

    store = str(merchant or "").strip().lower()
    is_snappshop = "snapp" in store or "اسنپ" in store
    brand_color = "#B400AE" if is_snappshop else "#E52332"

    # Use a compact icon tile so neither wordmarks nor labels compete with the product.
    side = max(28, min(int(width), int(height)))
    right, bottom = left + side, top + side
    radius = max(5, side // 5)
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
        width=max(2, side // 14),
    )

    logo = _load_retailer_logo(is_snappshop)
    if logo is None:
        # Retain only a brand-color frame, rather than inventing a substitute mark.
        return

    pad = max(3, side // 10)
    inner_side = max(1, side - 2 * pad)
    fitted = ImageOps.contain(logo, (inner_side, inner_side), method=Image.Resampling.LANCZOS)
    image.paste(
        fitted,
        (left + (side - fitted.width) // 2, top + (side - fitted.height) // 2),
        fitted,
    )
