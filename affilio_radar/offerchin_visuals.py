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
