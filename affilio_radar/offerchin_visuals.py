"""Shared OfferChin artwork primitives for image posts and animated shorts."""
from __future__ import annotations

import math
from pathlib import Path


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



def draw_retailer_badge(draw, left: int, top: int, width: int, height: int, merchant: str) -> None:
    """Draw a compact, self-contained storefront badge without network/font-asset dependencies.

    Brand-colored marks and wordmarks make the seller source visible without covering
    the discount burst or depending on remote logo hosting at publication time.
    """
    store = str(merchant or "").strip().lower()
    is_snappshop = "snapp" in store or "اسنپ" in store
    brand_color = "#B400AE" if is_snappshop else "#E52332"
    wordmark = "Snapp! Shop" if is_snappshop else "digikala"

    width, height = max(70, int(width)), max(28, int(height))
    right, bottom = left + width, top + height
    radius = max(5, height // 5)
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
    icon_size = max(20, height - 2 * pad)
    icon_left = left + pad
    icon_top = top + (height - icon_size) // 2
    icon_right = icon_left + icon_size
    icon_bottom = icon_top + icon_size
    draw.rounded_rectangle(
        (icon_left, icon_top, icon_right, icon_bottom),
        radius=max(4, icon_size // 5),
        fill=brand_color,
    )
    if is_snappshop:
        icon_font = _sale_font(max(11, int(icon_size * 0.46)))
        draw.text(
            (icon_left + icon_size / 2, icon_top + icon_size / 2),
            "S!",
            font=icon_font,
            fill="#FFFFFF",
            anchor="mm",
        )
    else:
        # A white smile gives the small red mark a distinctive DigiKala-like shape.
        inset = max(5, icon_size // 5)
        draw.arc(
            (icon_left + inset, icon_top + inset, icon_right - inset, icon_bottom - inset),
            start=20,
            end=160,
            fill="#FFFFFF",
            width=max(2, icon_size // 10),
        )

    text_left = icon_right + max(5, height // 8)
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
