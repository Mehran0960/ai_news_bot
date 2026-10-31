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


def _badge_font(size: int):
    """Load the bundled Vazirmatn ExtraBold font, with safe system fallbacks."""
    from PIL import ImageFont, features

    try:
        use_raqm = bool(features.check("raqm"))
    except Exception:
        use_raqm = False
    layout = ImageFont.Layout.RAQM if use_raqm else ImageFont.Layout.BASIC
    bundled_font = Path(__file__).resolve().parent / "assets" / "fonts" / "Vazirmatn-ExtraBold.ttf"
    candidates = (
        str(bundled_font),
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for font_path in candidates:
        if Path(font_path).is_file():
            try:
                return ImageFont.truetype(font_path, size=max(10, int(size)), layout_engine=layout), use_raqm
            except OSError:
                pass
    return ImageFont.load_default(), False


def _prepare_persian_badge_text(text: str, use_raqm: bool | None = None):
    """Return text plus Pillow options that keep the Persian word shaped and right-to-left.

    Native RAQM must receive logical Unicode text; the fallback reshapes and applies
    bidi exactly once. If neither path is available, return an empty label rather than
    draw broken Persian glyphs.
    """
    if use_raqm is None:
        try:
            from PIL import features
            use_raqm = bool(features.check("raqm"))
        except Exception:
            use_raqm = False
    if use_raqm:
        return str(text or ""), {"direction": "rtl", "language": "fa"}
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        shaped = get_display(arabic_reshaper.reshape(str(text or "")), base_dir="R")
        return shaped, {}
    except Exception:
        return "", {}


def _persian_digits(value: object) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _discount_badge_color(merchant: str) -> tuple[int, int, int]:
    """Use the corresponding retailer's signature color while keeping one shared style."""
    store = str(merchant or "").strip().lower()
    if "snapp" in store or "اسنپ" in store:
        return (170, 0, 181)  # SnappShop purple
    return (237, 23, 69)  # DigiKala red


def discount_badge_dimensions_for_reference_height(reference_height: int) -> tuple[int, int]:
    """Size the two-line discount tile to visually align with the retailer badge height.

    The 150:112 ratio preserves the compact OfferChin discount tile's typography.
    A 55px minimum height keeps Persian text readable on small source images.
    """
    try:
        target_height = int(reference_height)
    except (TypeError, ValueError, OverflowError):
        target_height = 88
    height = max(55, min(88, target_height))
    width = max(74, int(round(height * 150 / 112)))
    return width, height


def discount_badge_dimensions_for_reference_bounds(reference_width: int, reference_height: int) -> tuple[int, int]:
    """Match the retailer badge's exact target bounds for a visually consistent pair."""
    return max(1, int(reference_width)), max(1, int(reference_height))


def draw_discount_burst(
    draw,
    left: int,
    top: int,
    width: int,
    height: int,
    discount: int,
    merchant: str = "دیجی‌کالا",
) -> None:
    """Draw a retailer-colored discount tile inside the exact supplied bounds."""
    width, height = int(width), int(height)
    if width < 70 or height < 44 or not 0 < int(discount) <= 100:
        return

    left, top = int(left), int(top)
    # Pillow rectangle endpoints are inclusive, so subtract one to keep the
    # rendered tile exactly `width` by `height` pixels.
    right, bottom = left + width - 1, top + height - 1
    radius = max(10, min(24, int(height * 0.22)))
    shadow = max(2, int(height * 0.035))
    brand = _discount_badge_color(merchant)

    # Keep every painted pixel inside the supplied bounds, so this element can
    # match the retailer badge dimensions exactly, including its shadow.
    draw.rounded_rectangle(
        (left + shadow, top + shadow * 2, right, bottom),
        radius=radius,
        fill=(24, 15, 24),
    )
    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=radius,
        fill=brand,
        outline=(255, 255, 255),
        width=max(2, min(width, height) // 42),
    )

    percentage = f"{_persian_digits(int(discount))}٪"
    percent_font_size = max(15, int(height * 0.40))
    percent_font, use_raqm = _badge_font(percent_font_size)
    percent_layout = {"direction": "ltr", "language": "fa"} if use_raqm else {}

    # A wide tile (the production layout) uses one horizontal line: percentage
    # on the right and the Persian descriptor on the left. This fills the shared
    # logo-sized frame more naturally than a small two-line label in a wide box.
    if width >= height * 1.65:
        percent_font_size = max(15, min(int(height * 0.52), int(width * 0.20)))
        label_size = max(11, int(height * 0.28))
        percent_font, use_raqm = _badge_font(percent_font_size)
        percent_layout = {"direction": "ltr", "language": "fa"} if use_raqm else {}
        label_font, label_raqm = _badge_font(label_size)
        label, label_layout = _prepare_persian_badge_text("تخفیف", use_raqm=label_raqm)
        if not label:
            print("DISCOUNT_BADGE_PERSIAN_LABEL_SKIPPED: no safe RTL shaping backend available")
            return

        gap = max(4, int(height * 0.07))
        min_percent_size = max(13, int(height * 0.27))
        min_label_size = max(10, int(height * 0.18))
        for _ in range(40):
            try:
                percent_box = draw.textbbox((0, 0), percentage, font=percent_font, **percent_layout)
            except (TypeError, ValueError):
                percent_box = draw.textbbox((0, 0), percentage, font=percent_font)
            try:
                label_box = draw.textbbox((0, 0), label, font=label_font, **label_layout)
            except (TypeError, ValueError):
                label_box = draw.textbbox((0, 0), label, font=label_font)
            percent_width = percent_box[2] - percent_box[0]
            label_width = label_box[2] - label_box[0]
            if percent_width + gap + label_width <= width * 0.84:
                break
            if percent_font_size > min_percent_size:
                percent_font_size -= 1
                percent_font, use_raqm = _badge_font(percent_font_size)
                percent_layout = {"direction": "ltr", "language": "fa"} if use_raqm else {}
            elif label_size > min_label_size:
                label_size -= 1
                label_font, label_raqm = _badge_font(label_size)
                label, label_layout = _prepare_persian_badge_text("تخفیف", use_raqm=label_raqm)
                if not label:
                    print("DISCOUNT_BADGE_PERSIAN_LABEL_SKIPPED: no safe RTL shaping backend available")
                    return
            else:
                break

        combined_width = percent_width + gap + label_width
        center_y = round(top + height * 0.52)
        # In Persian reading order, the percentage comes first on the right,
        # followed by the descriptor on the left.
        label_center_x = left + (width - combined_width) / 2 + label_width / 2
        percent_center_x = left + (width + combined_width) / 2 - percent_width / 2
        draw.text(
            (round(percent_center_x), center_y),
            percentage,
            font=percent_font,
            fill=(255, 255, 255),
            anchor="mm",
            stroke_width=1,
            stroke_fill=tuple(max(0, channel - 70) for channel in brand),
            **percent_layout,
        )
        draw.text(
            (round(label_center_x), center_y),
            label,
            font=label_font,
            fill=(255, 255, 255),
            anchor="mm",
            stroke_width=0,
            **label_layout,
        )
        return

    # Keep compact, near-square tiles on the original two-line treatment.
    font_size = max(15, int(height * 0.40))
    while font_size > max(13, int(height * 0.25)):
        percent_font, use_raqm = _badge_font(font_size)
        percent_layout = {"direction": "ltr", "language": "fa"} if use_raqm else {}
        try:
            box = draw.textbbox((0, 0), percentage, font=percent_font, **percent_layout)
        except (TypeError, ValueError):
            box = draw.textbbox((0, 0), percentage, font=percent_font)
        if box[2] - box[0] <= width * 0.82:
            break
        font_size -= 2

    draw.text(
        (round(left + width / 2), round(top + height * 0.345)),
        percentage,
        font=percent_font,
        fill=(255, 255, 255),
        anchor="mm",
        stroke_width=1,
        stroke_fill=tuple(max(0, channel - 70) for channel in brand),
        **percent_layout,
    )

    label_size = max(13, int(height * 0.255))
    label_font, label_raqm = _badge_font(label_size)
    label, label_layout = _prepare_persian_badge_text("تخفیف", use_raqm=label_raqm)
    if not label:
        print("DISCOUNT_BADGE_PERSIAN_LABEL_SKIPPED: no safe RTL shaping backend available")
        return

    while label_size > max(11, int(height * 0.19)):
        try:
            label_box = draw.textbbox((0, 0), label, font=label_font, **label_layout)
        except (TypeError, ValueError):
            label_box = draw.textbbox((0, 0), label, font=label_font)
        if label_box[2] - label_box[0] <= width * 0.84:
            break
        label_size -= 1
        label_font, label_raqm = _badge_font(label_size)
        label, label_layout = _prepare_persian_badge_text("تخفیف", use_raqm=label_raqm)
        if not label:
            print("DISCOUNT_BADGE_PERSIAN_LABEL_SKIPPED: no safe RTL shaping backend available")
            return

    draw.text(
        (round(left + width / 2), round(top + height * 0.775)),
        label,
        font=label_font,
        fill=(255, 255, 255),
        anchor="mm",
        stroke_width=0,
        **label_layout,
    )



# Official first-party retailer assets are stored in the repository. Normal rendering
# reads these local files only: a temporary CDN outage can never remove a logo.
_RETAILER_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "retailer-logos"
_LOCAL_LOGO_PATHS = {
    "digikala": _RETAILER_LOGO_DIR / "digikala-official.webp",
    "snappshop": _RETAILER_LOGO_DIR / "snappshop-official.webp",
}
_DIGIPAY_LOGO_PATH = _RETAILER_LOGO_DIR / "digipay-official.svg"


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



@lru_cache(maxsize=1)
def _load_digipay_logo():
    """Load the official current DigiPay brand mark staged from MyDigiPay by CI."""
    try:
        if _DIGIPAY_LOGO_PATH.is_file():
            return _decode_retailer_logo(_DIGIPAY_LOGO_PATH.read_bytes(), False)
    except Exception as exc:
        print(f"DIGIPAY_LOGO_LOCAL_READ_FAILED error={type(exc).__name__}")
    print(f"DIGIPAY_LOGO_LOCAL_ASSET_UNAVAILABLE path={_DIGIPAY_LOGO_PATH.name}")
    return None


def _draw_uniform_logo_frame(image, logo, left: int, top: int, width: int, height: int) -> None:
    """Draw a fixed-size, visible frame and center the untouched logo artwork inside it.

    Every brand mark receives exactly the same outer width and height. The source
    artwork is only scaled proportionally; it is never stretched, cropped, or recolored.
    """
    from PIL import Image, ImageDraw, ImageOps

    target_width = max(1, int(width))
    target_height = max(1, int(height))
    if logo is None or target_width < 3 or target_height < 3:
        return

    frame = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    min_dimension = min(target_width, target_height)
    radius = max(3, min(12, int(min_dimension * 0.16)))
    border_width = max(1, min(2, int(min_dimension * 0.02)))
    draw.rounded_rectangle(
        (0, 0, target_width - 1, target_height - 1),
        radius=radius,
        fill=(255, 255, 255, 255),
        outline=(220, 224, 230, 255),
        width=border_width,
    )

    padding = max(3, min(10, int(min_dimension * 0.08)))
    inner_width = max(1, target_width - 2 * padding)
    inner_height = max(1, target_height - 2 * padding)
    fitted = ImageOps.contain(
        logo,
        (inner_width, inner_height),
        method=Image.Resampling.LANCZOS,
    )
    if fitted.width < 1 or fitted.height < 1:
        return

    frame.alpha_composite(
        fitted,
        ((target_width - fitted.width) // 2, (target_height - fitted.height) // 2),
    )
    position = (int(left), int(top))
    if image.mode == "RGBA":
        image.alpha_composite(frame, position)
    else:
        image.paste(frame.convert("RGB"), position, frame.getchannel("A"))


def draw_digipay_badge(image, left: int, top: int, width: int, height: int) -> None:
    """Draw DigiPay inside the same exact-size frame used for retailer logos."""
    _draw_uniform_logo_frame(image, _load_digipay_logo(), left, top, width, height)


def draw_retailer_badge(image, left: int, top: int, width: int, height: int, merchant: str) -> None:
    """Draw the full official retailer artwork inside the shared fixed-size logo frame."""
    store = str(merchant or "").strip().lower()
    is_snappshop = "snapp" in store or "اسنپ" in store
    _draw_uniform_logo_frame(
        image,
        _load_retailer_logo(is_snappshop),
        left,
        top,
        width,
        height,
    )
