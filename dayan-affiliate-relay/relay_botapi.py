import csv
import html as html_lib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import shutil
from datetime import datetime, time, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from PIL import Image, ImageFilter
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
STATE_FILE = ROOT / "state.json"
OVERRIDES_FILE = CONFIG / "post_overrides.json"

SOURCE_CHANNEL = "Dayan_video"
TARGET_CHANNEL = "@Iran_gajet"
CHANNEL_FOLLOW_HTML = '<a href="https://t.me/Iran_gajet">📣 ایران گجت | @Iran_gajet</a>'
SOURCE_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
TIMEZONE = ZoneInfo("Asia/Tehran")
PUBLISH_SLOTS = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]
SLOT_GRACE_MINUTES = 25
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000
MAX_VIDEO_BYTES = 49 * 1024 * 1024
MAX_PHOTO_BYTES = 9 * 1024 * 1024
MAX_POLL_PAGES = 28
MAX_ARCHIVE_POSTS = 500
MAX_PRICE_CHECK_CANDIDATES_PER_RUN = 20
PRICE_CHECK_VERSION = 4
HTTP_TIMEOUT = 25

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Only extract codes explicitly labeled as a product code; do not mistake
# four-digit prices, model numbers, or sizes for product IDs.
CODE_RE = re.compile(r"(?:کد(?:\s+محصول)?|product\s*code)\s*[:#\-]?\s*(\d{4,8})", re.IGNORECASE)
PATH_CODE_RE = re.compile(r"/(lead|fastcart)/(\d{4,8})", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}")
SKIP_LINE_TERMS = [
    "کد دریافت محتوا", "نحوه دریافت محتوا", "دیگر محصولات",
    "ربات تلگرامی همکار", "dayanpartnerbot", "dayanaff_pr",
    "dayan_video", "dayanaffiliate.com", "کدهای دریافت",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DayanAffiliateRelay/1.0; +https://github.com/Mehran0960/ai_news_bot)"
})



def ensure_price_check_version(state):
    """Recheck prior OCR rejections when price-reading rules materially improve."""
    if state.get("price_check_version") != PRICE_CHECK_VERSION:
        state["price_rejected_source_ids"] = []
        state["price_rejected_product_codes"] = []
        state["price_check_version"] = PRICE_CHECK_VERSION
        print(f"Price verifier upgraded to v{PRICE_CHECK_VERSION}; prior OCR exclusions cleared for recheck.")
    return state


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc

def write_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def normalize_digits(text):
    return (text or "").translate(DIGIT_TRANSLATION)

def extract_product_refs(caption):
    text = normalize_digits(caption)
    refs = []
    seen = set()
    route_codes = set()

    for route, code in PATH_CODE_RE.findall(text):
        route = route.lower()
        route_codes.add(code)
        key = (route, code)
        if key not in seen:
            refs.append({"route": route, "code": code})
            seen.add(key)

    for code in CODE_RE.findall(text):
        if code in route_codes:
            continue
        key = ("fastcart", code)
        if key not in seen:
            refs.append({"route": "fastcart", "code": code})
            seen.add(key)
    return refs

def clean_caption(text):
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if any(term in low for term in SKIP_LINE_TERMS):
            continue
        # Do not carry over platform-specific promotional tags from Dayan.
        line = re.sub(r"#(?:اینستاگرام|پیامرسانیداخلی)", "", line, flags=re.IGNORECASE)
        line = URL_RE.sub("", line)
        line = re.sub(
            r"(?:آدرس|ادرس)\s*(?:فروشگا\S*|دامنه)\s*/\s*(?:lead|fastcart)/\d+",
            "",
            line,
            flags=re.IGNORECASE,
        )
        line = HANDLE_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip(" \t|،;:")
        if line and line not in lines:
            lines.append(line)
    return "\n".join(lines).strip()

def direct_video_url(element):
    for attr in ("src", "data-src", "data-video"):
        value = (element.get(attr) or "").strip()
        if urlparse(value).scheme in ("http", "https"):
            return value
    return None

def photo_url_from_node(node):
    """Return Telegram's public photo URL from a channel preview message."""
    wrap = node.select_one(".tgme_widget_message_photo_wrap")
    if not wrap:
        return None
    style = wrap.get("style", "")
    match = re.search(r"""(https://[^)'" ]+)""", style, re.IGNORECASE)
    if match:
        value = match.group(1)
        if urlparse(value).scheme == "https":
            return value
    return None

def video_url_from_node(node):
    # Do not confuse a thumbnail/image with a playable video.
    selectors = [
        "video.tgme_widget_message_video",
        ".tgme_widget_message_video video",
        ".js-video-player video",
        ".tgme_widget_message_video_player video",
        "video[src]",
        "video[data-src]",
    ]
    for selector in selectors:
        element = node.select_one(selector)
        if element:
            url = direct_video_url(element)
            if url:
                return url

    for element in node.select("[data-video]"):
        url = direct_video_url(element)
        if url and any(part in url.lower() for part in (".mp4", "video", "stream")):
            return url
    return None

def parse_preview(html):
    soup = BeautifulSoup(html, "html.parser")
    parsed = []
    seen = set()
    for node in soup.select(".tgme_widget_message"):
        post_ref = node.get("data-post")
        if not post_ref:
            parent = node.find_parent(attrs={"data-post": True})
            post_ref = parent.get("data-post") if parent else None
        if not post_ref:
            for parent in node.parents:
                post_ref = parent.get("data-post")
                if post_ref:
                    break
        if not post_ref or "/" not in post_ref:
            continue
        try:
            _, raw_id = post_ref.rsplit("/", 1)
            message_id = int(raw_id)
        except (ValueError, TypeError):
            continue
        if message_id in seen:
            continue
        seen.add(message_id)

        text_node = node.select_one(".tgme_widget_message_text")
        caption = text_node.get_text("\n", strip=True) if text_node else ""
        media_url = video_url_from_node(node)
        time_node = node.select_one(".tgme_widget_message_date time[datetime]")
        views_node = node.select_one(".tgme_widget_message_views")
        parsed.append({
            "source_message_id": message_id,
            "source_url": f"https://t.me/{SOURCE_CHANNEL}/{message_id}",
            "source_caption": caption,
            "product_refs": extract_product_refs(caption),
            "video_url": media_url,
            "photo_url": photo_url_from_node(node),
            "source_date": time_node.get("datetime") if time_node else None,
            "views": parse_view_count(views_node.get_text(" ", strip=True)) if views_node else None,
        })
    return sorted(parsed, key=lambda item: item["source_message_id"])

def parse_view_count(raw_value):
    """Parse Telegram public-preview view labels such as 1.2K, 345K, or 1.4M."""
    if not raw_value:
        return None
    value = normalize_digits(str(raw_value)).strip().lower()
    value = value.replace(",", "").replace("٬", "").replace("٫", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k|m|هزار|میلیون)?", value)
    if not match:
        return None
    try:
        count = float(match.group(1))
    except ValueError:
        return None
    unit = match.group(2) or ""
    if unit in ("k", "هزار"):
        count *= 1_000
    elif unit in ("m", "میلیون"):
        count *= 1_000_000
    return max(0, int(count))


def classify_product_category(text):
    """Classify products by Iranian online-market demand signals, not media format."""
    value = normalize_digits(text or "").lower()
    patterns = [
        ("power_backup", r"پاور\s*بانک|پاوربانک|شارژر|باتری|موتور\s*برق|پنل\s*خورشیدی|برق\s*اضطراری|چراغ\s*اضطراری|\bups\b"),
        ("smartphones", r"گوشی(?:\s*هوشمند)?|موبایل|تلفن\s*همراه|آیفون|iphone|\bsmartphone\b"),
        ("audio_wearables", r"ایرپاد|هندزفری|هدفون|هدست|اسپیکر|ساعت\s*هوشمند|اسمارت\s*واچ|smartwatch|earbuds"),
        ("computer_network", r"لپ\s*تاپ|لپ‌تاپ|لپتاپ|کامپیوتر|تبلت|مودم|روتر|مسیریاب|مانیتور|پروژکتور|تلویزیون|\blaptop\b|\brouter\b"),
        ("gaming", r"گیم|بازی|کنسول|پلی\s*استیشن|پلی‌استیشن|ایکس\s*باکس|xbox|ps[345]|گیم\s*استیک|دسته\s*(?:بازی|بی\s*سیم)"),
        ("digital_accessories", r"کابل|مبدل|تبدیل\s*usb|کیبورد|ماوس|موس|فلش|حافظه|کارت\s*حافظه|پایه\s*موبایل|قاب\s*گوشی|محافظ\s*صفحه|بلوتوث"),
        ("home", r"آشپزخانه|خانه|نظافت|جارو|سرخ\s*کن|خردکن|قهوه\s*ساز|چای\s*ساز|ظرف\s*شویی|لامپ|چراغ|دکور|سازماندهی|ارگانایزر"),
        ("automotive", r"خودرو|ماشین|موتور\s*سیکلت|داشبورد|کارواش|کمپرسور\s*باد|پمپ\s*باد|دوربین\s*ثبت"),
        ("tools", r"ابزار|دریل|پیچ\s*گوشتی|جوش|متر\s*لیزری|آچار|تراز\s*لیزری"),
        ("personal_care", r"آرایش|پوست|مو\b|ریش|اصلاح|ماساژ|فشار\s*خون|دندان|بهداشت|عطر|ادکلن"),
        ("kids_sports", r"کودک|نوزاد|اسباب\s*بازی|ورزشی|پیاده\s*روی|سفر|کمپینگ|کوهنوردی"),
        ("fashion", r"لباس|کفش|کیف|ساعت\b|عینک|گردنبند|دستبند"),
    ]
    for category, pattern in patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return category
    return "other"


def extract_source_price_values(text):
    """Extract likely prices from explicit toman or million-toman price mentions."""
    value = normalize_digits(text or "").replace("٬", ",").replace("،", ",")
    amounts = set()
    for match in re.finditer(r"(?<!\d)(\d{1,2})[.,٫](\d{3})\s*میلیون(?:\s*تومان)?", value):
        try:
            amount = int(match.group(1)) * 1_000_000 + int(match.group(2)) * 1_000
            if amount >= 100_000:
                amounts.add(amount)
        except ValueError:
            pass
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:,\d{3}){1,2})(?!\d)", value):
        start, end = match.span()
        context = value[max(0, start - 24):min(len(value), end + 18)]
        if "تومان" not in context and not re.search(r"قیمت|فقط|تخفیف|اصلی|قبلی|فروش ویژه", context):
            continue
        digits = re.sub(r"\D", "", match.group(1))
        if digits:
            amount = int(digits)
            if amount >= 100_000:
                amounts.add(amount)
    return sorted(amounts)



IMAGE_PRICE_CUE_RE = re.compile(r"تومان|ریال|قیمت|ق[^\s‌]{0,3}مت|میلیون|هزار|فروش\s*ویژه|تخفیف\s*(?:ویژه|تا|\d)", re.IGNORECASE)
INSTALLMENT_CUE_RE = re.compile(r"قسط|اقساط|پیش[\s‌-]*پرداخت|ماهانه|در\s*\d+\s*ماه", re.IGNORECASE)


def extract_image_price_values(text):
    """Extract plausible toman prices recognized by OCR from a product creative."""
    value = normalize_digits(text or "")
    value = value.replace("٬", ",").replace("،", ",").replace("٫", ".").replace("\u00a0", " ")
    amounts = set()
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:[,. ]\d{3}){1,2})(?!\d)", value):
        start, end = match.span()
        line_start = value.rfind("\n", 0, start) + 1
        line_end = value.find("\n", end)
        if line_end < 0:
            line_end = len(value)
        context = value[max(line_start, start - 28):min(line_end, end + 28)]
        if INSTALLMENT_CUE_RE.search(context):
            continue
        digits = re.sub(r"\D", "", match.group(1))
        if digits and int(digits) >= 100_000:
            amounts.add(int(digits))
    # OCR sometimes reads "۱,۴۱۹" instead of "۱,۴۱۹,۰۰۰".
    # Expand the short form only near a price-related cue to avoid treating model specs as prices.
    for match in re.finditer(r"(?<!\d)(\d{1,3}[,.]\d{3})(?!\d)", value):
        start, end = match.span()
        context = value[max(0, start - 36):min(len(value), end + 36)]
        digits = re.sub(r"\D", "", match.group(1))
        if digits and int(digits) < 100_000 and IMAGE_PRICE_CUE_RE.search(context):
            amount = int(digits) * 1_000
            if amount >= 10_000 and not INSTALLMENT_CUE_RE.search(context):
                amounts.add(amount)

    # Compact prices such as "۲۹ هزار تومان" or "۱,۴۱۹ هزار تومان".
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:[,. ]\d{3})?)\s*هزار\s*(?:تومان)?", value):
        digits = re.sub(r"\D", "", match.group(1))
        context = value[max(0, match.start() - 24):min(len(value), match.end() + 18)]
        if digits and not INSTALLMENT_CUE_RE.search(context):
            amount = int(digits) * 1_000
            if amount >= 10_000:
                amounts.add(amount)

    for match in re.finditer(r"(?<!\d)(\d{6,9})(?!\d)", value):
        start, end = match.span()
        context = value[max(0, start - 32):min(len(value), end + 32)]
        if IMAGE_PRICE_CUE_RE.search(context) and not INSTALLMENT_CUE_RE.search(context):
            amount = int(match.group(1))
            if amount >= 100_000:
                amounts.add(amount)
    for match in re.finditer(r"(?<!\d)(\d{1,2})[.,](\d{3})\s*میلیون(?:\s*تومان)?", value):
        amount = int(match.group(1)) * 1_000_000 + int(match.group(2)) * 1_000
        if amount >= 100_000:
            amounts.add(amount)
    return sorted(amounts)


def _price_to_integer(raw_value):
    if not raw_value:
        return None
    digits = re.sub(r"\D", "", normalize_digits(str(raw_value)))
    if not digits:
        return None
    try:
        amount = int(digits)
    except ValueError:
        return None
    return amount if amount >= 100_000 else None


def compare_image_prices_to_product(image_text, product_details):
    """Compare detected creative prices to current/original prices from the live product page."""
    text = normalize_digits(image_text or "")
    image_prices = extract_image_price_values(text)
    page_prices = sorted({
        amount for amount in (
            _price_to_integer((product_details or {}).get("discounted_price")),
            _price_to_integer((product_details or {}).get("original_price")),
        ) if amount is not None
    })
    if not image_prices:
        return {
            "ok": False, "status": "unverifiable",
            "reason": "OCR did not reliably recover a numeric price; refusing to assume the creative is price-free",
            "image_prices": [], "page_prices": page_prices,
        }
    if not page_prices:
        return {"ok": False, "status": "unverifiable", "reason": "live product page did not expose a comparable price", "image_prices": image_prices, "page_prices": []}
    mismatched = [amount for amount in image_prices if amount not in page_prices]
    if mismatched:
        return {"ok": False, "status": "mismatch", "reason": "creative price differs from live product page", "image_prices": image_prices, "page_prices": page_prices, "mismatched_prices": mismatched}
    return {"ok": True, "status": "match", "reason": "all detected prices match the live product page", "image_prices": image_prices, "page_prices": page_prices}


# Demand profile based on published Iranian online-market reports.
# Digikala's 1403 report highlighted mobile phones, audio and wearables among
# its most-searched products. Its 1404 report showed faster growth in searches
# for "cheap" (+44%) and "discount" (+31%), plus a shift during the reported
# crisis period toward power banks, chargers and batteries. These are directional
# market signals, not a guarantee of sales for any individual affiliate product.
# Sources: https://dmboard.media/news/digikala-annual-report-1404/
#          https://digiato.com/iran-technology-news/digikala1403-report-has-been-published
CATEGORY_PRIORS = {
    "smartphones": 35,
    "audio_wearables": 34,
    "digital_accessories": 33,
    "power_backup": 32,
    "computer_network": 30,
    "gaming": 28,
    "home": 24,
    "automotive": 20,
    "tools": 18,
    "personal_care": 17,
    "kids_sports": 16,
    "fashion": 12,
    "other": 9,
}

# A limited trend premium follows observed market movement in published reports.
# It is intentionally smaller than the direct market-demand and engagement scores.
CATEGORY_TREND_POINTS = {
    "power_backup": 10,
    "smartphones": 7,
    "audio_wearables": 9,
    "digital_accessories": 8,
    "computer_network": 5,
    "gaming": 5,
    "home": 4,
    "automotive": 3,
    "tools": 2,
    "personal_care": 3,
    "kids_sports": 2,
    "fashion": 1,
    "other": 1,
}


def score_product_potential(item, now=None):
    """
    Explainable 0-100 estimate. The primary 75 points score likely market demand:
    category demand, observed Telegram view velocity, and reported market trends.
    Remaining points score purchase fit (affordability/discount), content clarity,
    and freshness. This is a ranking heuristic, not a sales guarantee.
    """
    now = now or datetime.now(timezone.utc)
    caption = str(item.get("source_caption") or "")
    category = classify_product_category(caption)
    category_points = CATEGORY_PRIORS.get(category, CATEGORY_PRIORS["other"])

    view_count = item.get("views")
    age_hours = None
    try:
        published = datetime.fromisoformat(str(item.get("source_date") or "").replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age_hours = max(0.25, (now.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600)
    except (ValueError, TypeError):
        pass
    if view_count is None or age_hours is None:
        # Unknown engagement is neutral; it must not punish an item solely
        # because Telegram did not expose its view count/date in the preview.
        view_points = 10
    else:
        views_per_hour = max(0, float(view_count)) / max(age_hours, 0.25)
        view_points = min(25, round(25 * math.log1p(views_per_hour) / math.log1p(1000)))

    trend_points = CATEGORY_TREND_POINTS.get(category, CATEGORY_TREND_POINTS["other"])
    normalized_caption = normalize_digits(caption).lower()
    # Price sensitivity and discounts are unusually strong current search signals
    # in Iran; reward explicit value messaging, without letting it outweigh demand.
    if re.search(r"ارزان|اقتصادی|مقرون\s*به\s*صرفه|قیمت\s*مناسب", normalized_caption):
        trend_points += 3
    if re.search(r"تخفیف|حراج|فروش\s*ویژه|قیمت\s*استثنایی", normalized_caption):
        trend_points += 2
    trend_points = min(15, trend_points)
    market_demand_score = min(75, category_points + view_points + trend_points)

    prices = extract_source_price_values(caption)
    price = min(prices) if prices else None
    if price is None:
        affordability_points = 5
    elif price <= 2_000_000:
        affordability_points = 10
    elif price <= 5_000_000:
        affordability_points = 9
    elif price <= 10_000_000:
        affordability_points = 7
    elif price <= 20_000_000:
        affordability_points = 5
    elif price <= 40_000_000:
        affordability_points = 3
    else:
        affordability_points = 1

    discount_points = 0
    percent_match = re.search(r"(?<!\d)(\d{1,2})\s*(?:٪|%)\s*(?:تخفیف)?", normalized_caption)
    if percent_match:
        discount_points = min(10, round(int(percent_match.group(1)) * 0.35))
    elif len(prices) >= 2:
        original, discounted = max(prices), min(prices)
        if original > discounted:
            discount_points = min(10, round(10 * (original - discounted) / original))
    if discount_points == 0 and re.search(r"تخفیف|حراج|فروش\s*ویژه|قیمت\s*استثنایی", normalized_caption):
        discount_points = 3

    content_points = 0
    if len(caption.strip()) >= 50:
        content_points += 1
    if re.search(r"\d|ویژگی|قابلیت|ضد\s*آب|بی\s*سیم|هوشمند|چندکاره|قابل\s*حمل|4k|8k", caption, re.IGNORECASE):
        content_points += 1
    if re.search(r"[!?؟❗🔥😳🤯✨]", caption):
        content_points += 1

    if age_hours is None:
        freshness_points = 1
    else:
        age_days = max(0, age_hours / 24)
        freshness_points = 2 if age_days <= 1 else 1 if age_days <= 7 else 0

    total = min(100, market_demand_score + affordability_points + discount_points + content_points + freshness_points)
    return {
        "score": int(total),
        "market_demand_score": int(market_demand_score),
        "category": category,
        "category_demand_points": int(category_points),
        "view_points": int(view_points),
        "trend_points": int(trend_points),
        "affordability_points": int(affordability_points),
        "discount_points": int(discount_points),
        "price_toman": price,
    }


def select_next_candidate(queue, overrides, sent_product_codes=None):
    """Always prefer eligible videos; market-demand ranking orders candidates within each media type."""
    sent_codes = {str(code) for code in (sent_product_codes or [])}
    candidates = []
    for item in queue:
        product_ref = resolve_product_ref(item, overrides)
        if not product_ref or str(product_ref.get("code")) in sent_codes:
            continue
        media_type = item.get("media_type") or ("video" if item.get("video_url") else "photo")
        if media_type not in ("video", "photo"):
            continue
        demand_score = int(item.get("market_demand_score", item.get("popularity_score", 0)) or 0)
        total_score = int(item.get("popularity_score", 0) or 0)
        message_id = int(item.get("source_message_id", 0) or 0)
        # Video is an absolute format priority. Only after video/photo class is
        # chosen do demand, commercial fit, and recency order the candidates.
        candidates.append((0 if media_type == "video" else 1, -demand_score, -total_score, -message_id, item, product_ref))
    if not candidates:
        return None, None
    candidates.sort(key=lambda candidate: candidate[:4])
    return candidates[0][4], candidates[0][5]


def rank_archive_candidates(posts, overrides, sent_product_codes=None, sent_source_ids=None, now=None,
                            rejected_product_codes=None, rejected_source_ids=None):
    """Score recent archive posts, excluding creatives rejected by the price verifier."""
    sent_codes = {str(code) for code in (sent_product_codes or [])}
    sent_ids = {int(value) for value in (sent_source_ids or [])}
    rejected_codes = {str(code) for code in (rejected_product_codes or [])}
    rejected_ids = {int(value) for value in (rejected_source_ids or [])}
    used_codes = set(sent_codes) | rejected_codes
    prepared_posts = []
    # A video for a product outranks every photo of the same product, even if
    # the photo post is newer. Recency ranks candidates within each media class.
    for item in sorted(
        posts,
        key=lambda post: (
            0 if post.get("video_url") else 1,
            -int(post.get("source_message_id", 0) or 0),
        ),
    ):
        message_id = int(item.get("source_message_id", 0) or 0)
        if message_id in sent_ids or message_id in rejected_ids:
            continue
        media_type = "video" if item.get("video_url") else "photo" if item.get("photo_url") else None
        if media_type is None:
            continue
        product_ref = resolve_product_ref(item, overrides)
        if not product_ref:
            continue
        code = str(product_ref.get("code"))
        if code in used_codes:
            continue
        used_codes.add(code)
        ranking = score_product_potential(item, now=now)
        candidate = dict(item)
        candidate["media_type"] = media_type
        candidate["popularity_score"] = ranking["score"]
        candidate["market_demand_score"] = ranking["market_demand_score"]
        candidate["product_category"] = ranking["category"]
        prepared_posts.append(candidate)
    return prepared_posts


def select_next_price_verified_candidate(queue, overrides, sent_product_codes, store_base, state):
    """Try every eligible video before any photo; crop price text off photo fallbacks."""
    rejected_ids = {int(value) for value in state.get("price_rejected_source_ids", [])}
    rejected_codes = {str(value) for value in state.get("price_rejected_product_codes", [])}
    checks_this_run = 0

    while True:
        if checks_this_run >= MAX_PRICE_CHECK_CANDIDATES_PER_RUN:
            queue[:] = [
                item for item in queue
                if int(item.get("source_message_id", 0) or 0) not in rejected_ids
                and str((resolve_product_ref(item, overrides) or {}).get("code", "")) not in rejected_codes
            ]
            state["price_rejected_source_ids"] = sorted(rejected_ids)[-MAX_SENT_IDS:]
            state["price_rejected_product_codes"] = sorted(rejected_codes)[-MAX_SENT_IDS:]
            print(
                f"::warning::Checked {checks_this_run} candidates without finding a publishable item; "
                "remaining candidates will be assessed on a later scheduled run."
            )
            return None, None, None, None

        eligible = []
        for item in queue:
            source_id = int(item.get("source_message_id", 0) or 0)
            product_ref = resolve_product_ref(item, overrides)
            code = str(product_ref.get("code")) if product_ref else ""
            if source_id in rejected_ids or code in rejected_codes:
                continue
            eligible.append(item)

        chosen, product_ref = select_next_candidate(
            eligible, overrides, set(sent_product_codes or set()) | rejected_codes
        )
        if not chosen or not product_ref:
            queue[:] = [
                item for item in queue
                if int(item.get("source_message_id", 0) or 0) not in rejected_ids
                and str((resolve_product_ref(item, overrides) or {}).get("code", "")) not in rejected_codes
            ]
            state["price_rejected_source_ids"] = sorted(rejected_ids)[-MAX_SENT_IDS:]
            state["price_rejected_product_codes"] = sorted(rejected_codes)[-MAX_SENT_IDS:]
            return None, None, None, None

        checks_this_run += 1
        affiliate_url = make_affiliate_url(store_base, product_ref)
        sanitized_photo_path = None
        try:
            product_details = fetch_product_details(affiliate_url)
            media_type = chosen.get("media_type") or ("video" if chosen.get("video_url") else "photo")
            if media_type == "video":
                check = check_source_media_prices(chosen, product_details)
            else:
                sanitized_photo_path, check = prepare_price_cropped_photo(chosen, product_details)
        except Exception as exc:
            product_details = None
            check = {
                "ok": False, "status": "unverifiable",
                "reason": f"publication verification raised {type(exc).__name__}",
                "image_prices": [], "page_prices": [],
            }

        source_id = int(chosen.get("source_message_id", 0) or 0)
        if check.get("ok"):
            print(
                f"Pre-publication check passed source={source_id} "
                f"media={chosen.get('media_type')} status={check.get('status')} "
                f"image_prices={check.get('image_prices', [])} "
                f"page_prices={check.get('page_prices', [])} "
                f"photo_price_crop={bool(sanitized_photo_path)}."
            )
            state["price_rejected_source_ids"] = sorted(rejected_ids)[-MAX_SENT_IDS:]
            state["price_rejected_product_codes"] = sorted(rejected_codes)[-MAX_SENT_IDS:]
            return chosen, product_ref, product_details, sanitized_photo_path

        if sanitized_photo_path and os.path.exists(sanitized_photo_path):
            os.remove(sanitized_photo_path)
        rejected_ids.add(source_id)
        # Reject only this creative, not its product code: a video with a stale
        # price may fail, while a later photo of that same product can be cropped.
        queue[:] = [
            item for item in queue
            if int(item.get("source_message_id", 0) or 0) != source_id
        ]
        state["price_rejected_source_ids"] = sorted(rejected_ids)[-MAX_SENT_IDS:]
        state["price_rejected_product_codes"] = sorted(rejected_codes)[-MAX_SENT_IDS:]
        print(
            f"::warning::Skipping source={source_id}, product_code={product_ref['code']}: "
            f"price_check={check.get('status', 'unverifiable')}; "
            f"image_prices={check.get('image_prices', [])}; page_prices={check.get('page_prices', [])}. "
            "Trying the next candidate; other media for this product remain eligible."
        )


def fetch_preview(before_id=None):
    url = SOURCE_URL
    if before_id is not None:
        url += f"?before={int(before_id)}"
    response = SESSION.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    if "tgme_widget_message" not in response.text:
        raise RuntimeError("Telegram preview did not contain expected public-channel message markup.")
    return parse_preview(response.text)

def normalize_store_host(value):
    raw = (value or "").strip()
    if not raw:
        raise RuntimeError("Missing DAYAN_STORE_HOST secret. Add your personal Dayan store host from your affiliate panel.")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    supported = host.endswith(".affdn.ir") or host.endswith(".affdn.com")
    if parsed.scheme != "https" or not supported or host in ("affdn.ir", "affdn.com"):
        raise RuntimeError("DAYAN_STORE_HOST must be your personal HTTPS subdomain ending in .affdn.ir or .affdn.com.")
    if parsed.username or parsed.password or parsed.port or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RuntimeError("DAYAN_STORE_HOST must contain only your personal hostname, without credentials, a path, query, or port.")
    return f"https://{host}"

def make_affiliate_url(store_base, product_ref):
    if isinstance(product_ref, str):
        product_ref = {"route": "fastcart", "code": product_ref}
    route = str(product_ref.get("route", "fastcart")).lower()
    code = str(product_ref.get("code", "")).strip()
    if route not in ("fastcart", "lead") or not re.fullmatch(r"\d{4,8}", code):
        raise RuntimeError("Refusing to create an affiliate URL from an invalid route or product code.")
    return f"{store_base}/{route}/{code}"

def resolve_product_ref(item, overrides):
    override = overrides.get(str(item["source_message_id"]))
    if isinstance(override, dict):
        code = str(override.get("product_code", override.get("code", ""))).strip()
        route = str(override.get("route", "fastcart")).strip().lower()
        if route in ("fastcart", "lead") and re.fullmatch(r"\d{4,8}", code):
            return {"route": route, "code": code}
        return None
    if override:
        code = str(override).strip()
        if re.fullmatch(r"\d{4,8}", code):
            matches = [ref for ref in item.get("product_refs", []) if str(ref.get("code")) == code]
            if len(matches) == 1:
                return matches[0]
            if not matches:
                return {"route": "fastcart", "code": code}
        return None
    refs = item.get("product_refs", [])
    unique = {(str(ref.get("route", "fastcart")).lower(), str(ref.get("code", ""))) for ref in refs}
    if len(unique) != 1:
        return None
    route, code = next(iter(unique))
    if route not in ("fastcart", "lead") or not re.fullmatch(r"\d{4,8}", code):
        return None
    return {"route": route, "code": code}

def due_slot(now, published_slots):
    today = now.date().isoformat()
    for slot in PUBLISH_SLOTS:
        key = f"{today}|{slot}"
        if key in published_slots:
            continue
        hour, minute = map(int, slot.split(":"))
        slot_time = datetime.combine(now.date(), time(hour, minute), tzinfo=TIMEZONE)
        elapsed = (now - slot_time).total_seconds()
        if 0 <= elapsed <= SLOT_GRACE_MINUTES * 60:
            return key
    return None

PRODUCT_BENEFITS = [
    "✅ پرداخت درب منزل",
    "✅ ارسال به سراسر کشور",
    "✅ گارانتی تعویض و برگشت",
]
PRICE_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[,٬،]\d{3})+|\d{4,})(?!\d)")

def _format_price(raw_value):
    if raw_value is None:
        return None
    normalized = normalize_digits(str(raw_value)).replace("٬", ",").replace("،", ",")
    digits = re.sub(r"\D", "", normalized)
    if not digits:
        return None
    try:
        amount = int(digits)
    except ValueError:
        return None
    if amount < 1000:
        return None
    return f"{amount:,} تومان"

def _price_from_text(text):
    normalized = normalize_digits(text or "")
    match = PRICE_NUMBER_RE.search(normalized)
    return _format_price(match.group(1)) if match else None

def _iter_jsonld(value):
    if isinstance(value, list):
        for child in value:
            yield from _iter_jsonld(child)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in value:
                yield from _iter_jsonld(value[key])

def _price_after_label(text, labels):
    normalized = normalize_digits(text or "").replace("٬", ",").replace("،", ",")
    for label in labels:
        for match in re.finditer(re.escape(label), normalized, re.IGNORECASE):
            excerpt = normalized[match.end():match.end() + 100]
            price_match = PRICE_NUMBER_RE.search(excerpt)
            if price_match:
                formatted = _format_price(price_match.group(1))
                if formatted:
                    return formatted
    return None

def extract_product_details(page_html):
    """Extract product title/prices from visible HTML and Product JSON-LD."""
    soup = BeautifulSoup(page_html or "", "html.parser")
    visible_text = soup.get_text(" ", strip=True)
    details = {"title": None, "original_price": None, "discounted_price": None, "page_found": bool(page_html)}

    # Product H1 should outrank Open Graph metadata, which is often only the store name.
    node = soup.select_one("h1")
    if node:
        details["title"] = node.get_text(" ", strip=True)
    if not details["title"]:
        for selector in (
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
        ):
            node = soup.select_one(selector)
            if node and node.get("content", "").strip():
                details["title"] = node["content"].strip()
                break
    if not details["title"] and soup.title:
        details["title"] = soup.title.get_text(" ", strip=True)

    original_labels = (
        "قیمت اصلی", "قیمت قبل از تخفیف", "قیمت اولیه",
        "قیمت بدون تخفیف", "قیمت قبل تخفیف",
    )
    discounted_labels = (
        "قیمت با تخفیف", "قیمت پس از تخفیف", "قیمت بعد از تخفیف",
        "قیمت تخفیف خورده", "قیمت نهایی", "قیمت فروش ویژه",
    )
    details["original_price"] = _price_after_label(visible_text, original_labels)
    details["discounted_price"] = _price_after_label(visible_text, discounted_labels)

    # Generic product themes often put the original price in <del>/<s> and
    # the live price in a sale/current-price element.
    if not details["original_price"]:
        for node in soup.select("del, s, strike, .old-price, .old_price, .regular-price, [class*='old-price'], [class*='old_price']"):
            value = _price_from_text(node.get_text(" ", strip=True))
            if value:
                details["original_price"] = value
                break
    if not details["discounted_price"]:
        for node in soup.select(".sale-price, .special-price, .current-price, .current_price, .new-price, [class*='sale-price'], [class*='special-price'], [class*='current-price'], [itemprop='price']"):
            value = _price_from_text(node.get("content", "") or node.get_text(" ", strip=True))
            if value:
                details["discounted_price"] = value
                break

    # Prefer a valid Schema.org Product name/offer when visible selectors fail.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for entry in _iter_jsonld(data):
            types = entry.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "Product" not in types:
                continue
            if not details["title"] and isinstance(entry.get("name"), str):
                details["title"] = entry["name"].strip()
            offers = entry.get("offers", [])
            if isinstance(offers, dict):
                offers = [offers]
            for offer in offers if isinstance(offers, list) else []:
                price = offer.get("price") or offer.get("lowPrice")
                if price and not details["discounted_price"]:
                    details["discounted_price"] = _format_price(price)
                for spec in offer.get("priceSpecification", []) if isinstance(offer.get("priceSpecification", []), list) else [offer.get("priceSpecification")]:
                    if not isinstance(spec, dict):
                        continue
                    raw = spec.get("price")
                    price_type = str(spec.get("priceType", "")).lower()
                    formatted = _format_price(raw)
                    if formatted and ("strike" in price_type or "list" in price_type or "regular" in price_type) and not details["original_price"]:
                        details["original_price"] = formatted
                    elif formatted and not details["discounted_price"]:
                        details["discounted_price"] = formatted

    if details["title"]:
        details["title"] = re.sub(r"\s+", " ", details["title"]).strip()[:180]
    if details["original_price"] == details["discounted_price"]:
        details["original_price"] = None
    return details

def is_generic_store_title(title):
    normalized = re.sub(r"[\s|·\-—_]+", "", str(title or "").lower())
    return normalized in {"ایرانگجت", "irangadget", "iran-gadget", "ایرانگجتفروشگاه"}

def fetch_product_details(affiliate_url):
    try:
        response = SESSION.get(affiliate_url, timeout=(15, 25), allow_redirects=True)
        response.raise_for_status()
        details = extract_product_details(response.text)

        # Some FastCart pages expose only the store heading. For metadata only,
        # try the matching Lead route for the same product code; keep the user's
        # original affiliate route for purchase/conversion tracking.
        if not details.get("title") or is_generic_store_title(details.get("title")):
            parsed = urlparse(affiliate_url)
            match = re.fullmatch(r"/(fastcart|lead)/(\d{4,8})/?", parsed.path or "")
            if match and parsed.scheme == "https" and parsed.hostname:
                current_route, code = match.groups()
                alternate_route = "lead" if current_route == "fastcart" else "fastcart"
                metadata_url = f"{parsed.scheme}://{parsed.netloc}/{alternate_route}/{code}"
                try:
                    alternate_response = SESSION.get(metadata_url, timeout=(12, 20), allow_redirects=True)
                    alternate_response.raise_for_status()
                    alternate = extract_product_details(alternate_response.text)
                    if alternate.get("title") and not is_generic_store_title(alternate["title"]):
                        details["title"] = alternate["title"]
                    for price_key in ("original_price", "discounted_price"):
                        if not details.get(price_key) and alternate.get(price_key):
                            details[price_key] = alternate[price_key]
                except Exception as exc:
                    print(f"Alternate product metadata unavailable ({type(exc).__name__}); continuing with available details.")

        if is_generic_store_title(details.get("title")):
            details["title"] = None
        found = bool(details.get("title") or details.get("original_price") or details.get("discounted_price"))
        print(
            "Product-page enrichment: "
            f"title={'yes' if details.get('title') else 'no'}, "
            f"original_price={'yes' if details.get('original_price') else 'no'}, "
            f"discounted_price={'yes' if details.get('discounted_price') else 'no'}"
        )
        if not found:
            print("Product page loaded but no product-specific title/price fields were recognized; safe fallback caption will be used.")
        return details
    except Exception as exc:
        # Avoid logging the full exception because request exceptions can expose
        # the personal store URL.
        print(f"Product-page enrichment unavailable ({type(exc).__name__}); safe fallback caption will be used.")
        return {"title": None, "original_price": None, "discounted_price": None, "page_found": False}


def fill_price_fallback(source_caption, product_details):
    """Use explicit source-caption price pairs only when the product page lacks prices."""
    details = dict(product_details or {})
    if details.get("original_price") and details.get("discounted_price"):
        return details

    text = normalize_digits(source_caption or "")
    amounts = []
    for match in re.finditer(r"(?<!\d)(\d{1,2})[.,٫٬](\d{3})\s*میلیون(?:\s*تومان)?", text):
        amount = int(match.group(1)) * 1_000_000 + int(match.group(2)) * 1_000
        if amount >= 100_000:
            amounts.append(amount)

    # Also handle fully formatted prices such as 7,639,000, but not
    # unrelated one-separator quantities such as "10,000+ games".
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:[,٬،]\d{3}){2})(?!\d)", text):
        digits = re.sub(r"\D", "", match.group(1))
        if digits:
            amount = int(digits)
            if amount >= 100_000:
                amounts.append(amount)

    unique = sorted(set(amounts))
    sale_cue = "🔥" in text or "تخفیف" in text or "قیمت" in text
    if len(unique) >= 2 and sale_cue:
        if not details.get("original_price"):
            details["original_price"] = _format_price(max(unique))
        if not details.get("discounted_price"):
            details["discounted_price"] = _format_price(min(unique))
    return details


def summarize_source_description(source_caption, original=None, discounted=None, max_chars=150):
    """Return at most one concise feature line rather than repeating sales copy."""
    text = normalize_digits(clean_caption(source_caption))
    if not text:
        return ""

    # Remove source price values when they are already shown in the price block.
    if original and discounted:
        text = re.sub(r"(?<!\w)\d{1,2}[.,٫٬]\d{3}\s*میلیون(?:\s*تومان)?", "", text)
        text = re.sub(r"(?<!\w)\d{1,3}(?:[,٬،]\d{3})+\s*تومان", "", text)
    else:
        # When numeric prices are withheld, do not leak source price claims into
        # the compact descriptive line either.
        text = re.sub(r"(?im)^.*(?:قیمت(?:\s*(?:اصلی|تخفیفی|نهایی))?|تومان|میلیون|\d{1,3}(?:[,٬،]\d{3}){2}).*$", "", text)
        text = re.sub(r"\s*🔥\s*تخفیف[^\n]*", "", text)

    # Highlight a few concrete product specifications, when present.
    features = []
    patterns = [
        (r"(?<!\d)(\d{1,3}(?:[,٬.]\d{3})*\+?)\s*بازی", lambda m: f"🎮 {m.group(1).replace(',', '٬')} بازی"),
        (r"(?:خروجی|رزولوشن)\s*(4k|8k|full\s*hd|1080p|720p)", lambda m: f"📺 خروجی {m.group(1).upper().replace('FULL HD', 'Full HD')}"),
        (r"حافظه\s*(\d+)\s*(gb|tb|گیگابایت|ترابایت)", lambda m: f"💾 حافظه {m.group(1)}{m.group(2).upper() if m.group(2).lower() in ('gb','tb') else m.group(2)}"),
        (r"(\d+)\s*دسته\s*بی[\u200c\s-]*سیم", lambda m: f"🎮 {m.group(1)} دستهٔ بی‌سیم"),
    ]
    for pattern, formatter in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            feature = formatter(match)
            if feature not in features:
                features.append(feature)
        if len(features) >= 4:
            break
    if features:
        return " | ".join(features)[:max_chars]

    # Generic fallback: strip call-to-action and repeated delivery/payment claims,
    # then retain only a short excerpt, never an entire promotional paragraph.
    text = re.sub(r"(?:👇|⬇️?).*$", "", text)
    text = re.sub(r"پرداخت\s*درب\s*منزل|ارسال(?:\s+\S+){0,4}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip(" |،;:-")
    if not text:
        return ""
    first = re.split(r"[.!؟\n]", text, maxsplit=1)[0].strip()
    if len(first) > max_chars:
        first = first[:max_chars - 1].rstrip() + "…"
    return first

def build_caption(source_caption, affiliate_url, product_details=None, allow_source_price_fallback=True):
    # The affiliate product page is the current price source of truth.
    # Source creative/caption may be older than the live product listing.
    details = (
        fill_price_fallback(source_caption, product_details)
        if allow_source_price_fallback else dict(product_details or {})
    )
    chunks = []

    title = re.sub(r"\s+", " ", str(details.get("title") or "")).strip()
    if title and not is_generic_store_title(title):
        chunks.append("🛍 " + html_lib.escape(title))

    original = details.get("original_price")
    discounted = details.get("discounted_price")
    if original and discounted and original != discounted:
        chunks.append(f"💸 قیمت اصلی: <s>{html_lib.escape(original)}</s>\n🔥 قیمت تخفیفی: <b>{html_lib.escape(discounted)}</b>")
    elif discounted:
        chunks.append(f"💰 قیمت: <b>{html_lib.escape(str(discounted))}</b>")
    elif original:
        chunks.append(f"💰 قیمت اعلام‌شده: <b>{html_lib.escape(str(original))}</b>")

    intro = summarize_source_description(source_caption, original=original, discounted=discounted)
    if intro:
        chunks.append(html_lib.escape(intro))

    chunks.append("\n".join(PRODUCT_BENEFITS))
    chunks.append("🛍 مشاهده و خرید:\n" + html_lib.escape(affiliate_url, quote=True))
    chunks.append(CHANNEL_FOLLOW_HTML)

    caption = "\n\n".join(chunks)
    if len(caption) > 1024:
        # Preserve product title, price, benefits, purchase URL and channel link.
        fixed_tail = "\n".join(PRODUCT_BENEFITS) + "\n\n🛍 مشاهده و خرید:\n" + html_lib.escape(affiliate_url, quote=True) + "\n\n" + CHANNEL_FOLLOW_HTML
        title_part = ("🛍 " + html_lib.escape(title) + "\n\n") if title and not is_generic_store_title(title) else ""
        price_part = ""
        if original and discounted and original != discounted:
            price_part = f"💸 قیمت اصلی: <s>{html_lib.escape(original)}</s>\n🔥 قیمت تخفیفی: <b>{html_lib.escape(discounted)}</b>\n\n"
        elif discounted:
            price_part = f"💰 قیمت: <b>{html_lib.escape(str(discounted))}</b>\n\n"
        room = max(0, 1024 - len(fixed_tail) - len(title_part) - len(price_part) - 8)
        intro = intro[:room].rstrip()
        caption = title_part + price_part + ((html_lib.escape(intro) + "\n\n") if intro else "") + fixed_tail
        if len(caption) > 1024:
            overflow = len(caption) - 1024
            caption = caption[:max(0, 1024 - overflow - 1)].rstrip() + "…"
    return caption

def refresh_video_url(source_message_id):
    # Telegram CDN URLs may expire; fetch current public preview near publication.
    try:
        current = fetch_preview()
        fresh = next((p for p in current if p["source_message_id"] == source_message_id), None)
    except Exception as exc:
        print(f"Current preview refresh failed: {type(exc).__name__}: {exc}")
        fresh = None

    if fresh is None:
        try:
            older = fetch_preview(before_id=source_message_id + 1)
            fresh = next((p for p in older if p["source_message_id"] == source_message_id), None)
        except Exception as exc:
            print(f"Historical preview refresh failed: {type(exc).__name__}: {exc}")

    media_url = fresh.get("video_url") if fresh else None
    parsed = urlparse(media_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "telesco.pe" or host.endswith(".telesco.pe")):
        raise RuntimeError("Refusing to download media from an unexpected host; only HTTPS Telegram telesco.pe media URLs are accepted.")
    return media_url

def send_video(bot_token, item, affiliate_url, product_details=None):
    media_url = refresh_video_url(int(item["source_message_id"]))
    product_details = product_details if product_details is not None else fetch_product_details(affiliate_url)
    caption = build_caption(
        item.get("source_caption", ""), affiliate_url,
        product_details=product_details, allow_source_price_fallback=False
    )
    payload = {
        "chat_id": TARGET_CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "supports_streaming": "true",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }

    # Download to a temporary file, then upload through Bot API. This avoids
    # depending on Telegram's URL-fetch size/format limitations and never saves
    # the expiring CDN URL in the repository.
    temp_path = None
    try:
        with SESSION.get(media_url, stream=True, timeout=(15, 120)) as media_response:
            media_response.raise_for_status()
            content_type = (media_response.headers.get("Content-Type") or "").lower()
            if "video" not in content_type and "octet-stream" not in content_type:
                raise RuntimeError(f"Source media is not a recognized video (Content-Type={content_type or 'missing'}).")
            length_header = media_response.headers.get("Content-Length")
            if length_header and int(length_header) > MAX_VIDEO_BYTES:
                raise RuntimeError(f"Video exceeds the configured upload limit of {MAX_VIDEO_BYTES // (1024 * 1024)} MiB.")
            total = 0
            with tempfile.NamedTemporaryFile(prefix="dayan-", suffix=".mp4", delete=False) as temp_file:
                temp_path = temp_file.name
                for chunk in media_response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_VIDEO_BYTES:
                        raise RuntimeError(f"Video exceeds the configured upload limit of {MAX_VIDEO_BYTES // (1024 * 1024)} MiB.")
                    temp_file.write(chunk)
        if not temp_path or os.path.getsize(temp_path) < 1024:
            raise RuntimeError("Downloaded video is empty or unexpectedly small; refusing to publish.")
        with open(temp_path, "rb") as media_file:
            files = {"video": (f"dayan-{item['source_message_id']}.mp4", media_file, "video/mp4")}
            response = SESSION.post(
                f"https://api.telegram.org/bot{bot_token}/sendVideo",
                data=payload,
                files=files,
                timeout=(20, 180),
            )
        try:
            result = response.json()
        except ValueError:
            result = {"description": response.text[:300]}
        if response.status_code != 200 or not result.get("ok"):
            raise RuntimeError(f"Telegram sendVideo failed ({response.status_code}): {result.get('description', 'unknown error')}")
        return result["result"]["message_id"]
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def refresh_photo_url(source_message_id):
    try:
        current = fetch_preview()
        fresh = next((p for p in current if p["source_message_id"] == source_message_id), None)
    except Exception as exc:
        print(f"Current photo preview refresh failed: {type(exc).__name__}")
        fresh = None
    if fresh is None or not fresh.get("photo_url"):
        try:
            older = fetch_preview(before_id=source_message_id + 1)
            fresh = next((p for p in older if p["source_message_id"] == source_message_id), None)
        except Exception as exc:
            print(f"Historical photo preview refresh failed: {type(exc).__name__}")
            fresh = None
    photo_url = fresh.get("photo_url") if fresh else None
    parsed = urlparse(photo_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "telesco.pe" or host.endswith(".telesco.pe")):
        raise RuntimeError("Refusing to download photo from an unexpected host; only HTTPS Telegram telesco.pe media URLs are accepted.")
    return photo_url


def _run_tesseract(image_path):
    """OCR the original and a contrast-enhanced/upscaled variant in multiple layouts."""
    texts = []
    errors = []

    def run_layouts(path, layouts):
        output = []
        for psm in layouts:
            try:
                result = subprocess.run(
                    ["tesseract", str(path), "stdout", "-l", "fas+eng", "--psm", psm],
                    capture_output=True, text=True, timeout=25, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(type(exc).__name__)
                continue
            if result.returncode == 0 and result.stdout and result.stdout.strip():
                output.append(result.stdout)
        return "\n".join(output)

    original_text = run_layouts(image_path, ("11", "6"))
    if original_text:
        texts.append(original_text)

    # Dayan creatives often use small, low-contrast price overlays. Enhance only
    # after the original OCR, so ordinary images don't pay for unnecessary work.
    source_path = Path(image_path)
    enhanced_path = source_path.with_name(source_path.stem + "-ocr-enhanced.png")
    try:
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source_path),
                    "-vf", "scale=iw*2:ih*2:flags=lanczos,format=gray,eq=contrast=1.4:brightness=0.02,unsharp=5:5:1.0:5:5:0.0",
                    "-frames:v", "1", str(enhanced_path),
                ],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode == 0 and enhanced_path.exists() and enhanced_path.stat().st_size > 512:
                enhanced_text = run_layouts(enhanced_path, ("11", "6"))
                if enhanced_text:
                    texts.append(enhanced_text)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(type(exc).__name__)
    finally:
        if enhanced_path.exists():
            enhanced_path.unlink()

    if not texts:
        raise RuntimeError("Tesseract could not recover text from the source creative.")
    return "\n".join(texts)


def _ocr_video_frames(video_path):
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Video-frame inspection unavailable ({type(exc).__name__}).") from None
    try:
        duration = float((probe.stdout or "").strip()) if probe.returncode == 0 else 0.0
    except ValueError:
        duration = 0.0
    if duration <= 0:
        raise RuntimeError("Could not determine video duration for price verification.")

    texts = []
    with tempfile.TemporaryDirectory(prefix="dayan-price-frames-") as frame_dir:
        for index, fraction in enumerate((0.05, 0.25, 0.5, 0.75, 0.95)):
            timestamp = min(duration * fraction, max(0.0, duration - 0.12))
            frame_path = Path(frame_dir) / f"frame-{index}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error",
                     "-ss", f"{timestamp:.3f}", "-i", str(video_path),
                     "-frames:v", "1", "-vf", "scale=1600:-1", "-q:v", "3",
                     "-y", str(frame_path)],
                    capture_output=True, text=True, timeout=25, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(f"Video frame extraction unavailable ({type(exc).__name__}).") from None
            if result.returncode == 0 and frame_path.exists() and frame_path.stat().st_size > 512:
                texts.append(_run_tesseract(frame_path))
    if not texts:
        raise RuntimeError("No readable frames could be extracted for price verification.")
    return "\n".join(texts)


def read_source_media_ocr_text(item):
    """Download current source media and OCR the photo or three representative video frames."""
    source_id = int(item["source_message_id"])
    media_type = item.get("media_type") or ("video" if item.get("video_url") else "photo")
    if media_type == "video":
        media_url = refresh_video_url(source_id)
        suffix, max_bytes, allowed_type = ".mp4", MAX_VIDEO_BYTES, ("video/", "application/octet-stream")
        timeout = (15, 120)
    else:
        media_url = refresh_photo_url(source_id)
        suffix, max_bytes, allowed_type = ".jpg", MAX_PHOTO_BYTES, ("image/", "application/octet-stream")
        timeout = (15, 60)

    temp_path = None
    try:
        with SESSION.get(media_url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if not any(content_type.startswith(prefix) for prefix in allowed_type):
                raise RuntimeError("Source media has an unexpected content type for price verification.")
            length_header = response.headers.get("Content-Length")
            if length_header and int(length_header) > max_bytes:
                raise RuntimeError("Source media exceeds the configured size limit for price verification.")
            total = 0
            with tempfile.NamedTemporaryFile(prefix="dayan-price-check-", suffix=suffix, delete=False) as temp_file:
                temp_path = temp_file.name
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("Source media exceeded the configured size limit during download.")
                    temp_file.write(chunk)

        if not temp_path or os.path.getsize(temp_path) < 512:
            raise RuntimeError("Downloaded source creative is empty or too small for price verification.")
        if media_type == "video":
            return _ocr_video_frames(temp_path)
        return _run_tesseract(temp_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def check_source_media_prices(item, product_details):
    """Verify OCR-visible photo/video prices against current prices on the affiliate product page."""
    ocr_text = read_source_media_ocr_text(item)
    ocr_preview = re.sub(r"\s+", " ", ocr_text or "").strip()[:420]
    print(f"Creative OCR source={item.get('source_message_id')}: {ocr_preview or '[no text recovered]'}")
    if not ocr_text.strip():
        return {
            "ok": False, "status": "unverifiable",
            "reason": "OCR returned no readable text; the creative price cannot be safely checked",
            "image_prices": [],
            "page_prices": sorted({
                amount for amount in (
                    _price_to_integer((product_details or {}).get("discounted_price")),
                    _price_to_integer((product_details or {}).get("original_price")),
                ) if amount is not None
            }),
        }
    return compare_image_prices_to_product(ocr_text, product_details)



PRICE_REGION_CUE_RE = re.compile(
    r"تومان|ریال|قیمت|میلیون|هزار|تخفیف|فروش\s*ویژه",
    re.IGNORECASE,
)


def _tesseract_text_and_price_boxes(image_path):
    """Read OCR text and locate lines likely to contain a displayed price."""
    lines_by_key = {}
    all_text = []
    for psm in ("11", "6"):
        try:
            result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", "fas+eng", "--psm", psm, "tsv"],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            reader = csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
            rows = list(reader)
        except Exception:
            continue

        grouped = {}
        for row in rows:
            if row.get("level") != "5":
                continue
            word = (row.get("text") or "").strip()
            if not word:
                continue
            try:
                x, y = int(row["left"]), int(row["top"])
                width, height = int(row["width"]), int(row["height"])
            except (KeyError, TypeError, ValueError):
                continue
            key = (row.get("page_num"), row.get("block_num"), row.get("par_num"), row.get("line_num"))
            item = grouped.setdefault(key, {"words": [], "boxes": []})
            item["words"].append((x, word))
            item["boxes"].append((x, y, x + width, y + height))

        for key, data in grouped.items():
            text = " ".join(word for _, word in sorted(data["words"]))
            boxes = data["boxes"]
            box = (
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            )
            entry = {
                "text": text,
                "box": box,
                "height": max(1, box[3] - box[1]),
                "has_digits": bool(re.search(r"\d", normalize_digits(text))),
                "price_cue": bool(PRICE_REGION_CUE_RE.search(text)),
                "prices": extract_image_price_values(text),
            }
            all_text.append(text)
            # PSM layouts often report the same text with slightly different boxes.
            existing = next((
                line for line in lines_by_key.values()
                if line["text"] == text
                and abs(line["box"][0] - box[0]) <= 18
                and abs(line["box"][1] - box[1]) <= 18
            ), None)
            if existing is None:
                lines_by_key[(psm, key)] = entry
            else:
                existing["box"] = (
                    min(existing["box"][0], box[0]), min(existing["box"][1], box[1]),
                    max(existing["box"][2], box[2]), max(existing["box"][3], box[3]),
                )
                existing["height"] = max(existing["height"], entry["height"])
                existing["price_cue"] = existing["price_cue"] or entry["price_cue"]
                existing["prices"] = sorted(set(existing["prices"] + entry["prices"]))

    lines = list(lines_by_key.values())
    selected = set()
    for index, line in enumerate(lines):
        if line["price_cue"] or line["prices"]:
            selected.add(index)

    # A price number and its "price/toman" label may be separate OCR lines.
    for i, cue_line in enumerate(lines):
        if not cue_line["price_cue"]:
            continue
        x0, y0, x1, y1 = cue_line["box"]
        for j, number_line in enumerate(lines):
            if not number_line["has_digits"] or j in selected:
                continue
            nx0, ny0, nx1, ny1 = number_line["box"]
            vertical_gap = max(0, max(y0, ny0) - min(y1, ny1))
            horizontal_gap = max(0, max(x0, nx0) - min(x1, nx1))
            max_height = max(cue_line["height"], number_line["height"])
            if vertical_gap <= max_height * 2.4 and horizontal_gap <= 0.35 * max(x1, nx1, 1):
                selected.add(j)

    boxes = [lines[index]["box"] for index in selected]
    full_text = "\n".join(all_text)
    return full_text, boxes


def _merge_price_boxes(boxes, width, height):
    margin = max(8, int(min(width, height) * 0.012))
    prepared = []
    for x0, y0, x1, y1 in boxes:
        box = (
            max(0, int(x0) - margin), max(0, int(y0) - margin),
            min(width, int(x1) + margin), min(height, int(y1) + margin),
        )
        if box[2] > box[0] and box[3] > box[1]:
            prepared.append(box)

    merged = []
    while prepared:
        current = prepared.pop(0)
        changed = True
        while changed:
            changed = False
            kept = []
            for other in prepared:
                near = not (
                    current[2] + 10 < other[0] or other[2] + 10 < current[0]
                    or current[3] + 10 < other[1] or other[3] + 10 < current[1]
                )
                if near:
                    current = (
                        min(current[0], other[0]), min(current[1], other[1]),
                        max(current[2], other[2]), max(current[3], other[3]),
                    )
                    changed = True
                else:
                    kept.append(other)
            prepared = kept
        merged.append(current)
    return merged


def best_price_safe_crop_box(width, height, boxes, min_area_ratio=0.58):
    """Find the largest rectangular crop that excludes every price-text box."""
    if width <= 0 or height <= 0 or not boxes:
        return None
    xs, ys = {0, width}, {0, height}
    for x0, y0, x1, y1 in boxes:
        xs.update((max(0, x0), min(width, x1)))
        ys.update((max(0, y0), min(height, y1)))
    xs, ys = sorted(xs), sorted(ys)
    best, best_area = None, 0
    for left_i, left in enumerate(xs[:-1]):
        for right in xs[left_i + 1:]:
            crop_width = right - left
            if crop_width < width * 0.52:
                continue
            for top_i, top in enumerate(ys[:-1]):
                for bottom in ys[top_i + 1:]:
                    crop_height = bottom - top
                    area = crop_width * crop_height
                    if crop_height < height * 0.52 or area < width * height * min_area_ratio:
                        continue
                    if any(not (right <= x0 or left >= x1 or bottom <= y0 or top >= y1)
                           for x0, y0, x1, y1 in boxes):
                        continue
                    if area > best_area:
                        best, best_area = (left, top, right, bottom), area
    return best


def _remove_price_boxes(input_path, output_path, boxes, force_blur=False):
    """Crop price text out where possible; otherwise blur those exact regions."""
    with Image.open(input_path) as opened:
        source = opened.convert("RGB")
    width, height = source.size
    boxes = _merge_price_boxes(boxes, width, height)
    if not boxes:
        source.save(output_path, format="JPEG", quality=93, optimize=True)
        return "unchanged"

    crop_box = None if force_blur else best_price_safe_crop_box(width, height, boxes)
    if crop_box is not None:
        source.crop(crop_box).save(output_path, format="JPEG", quality=93, optimize=True)
        return "cropped"

    for x0, y0, x1, y1 in boxes:
        region = source.crop((x0, y0, x1, y1))
        blur_radius = max(12, int(min(width, height) * 0.022))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        source.paste(blurred, (x0, y0, x1, y1))
    source.save(output_path, format="JPEG", quality=93, optimize=True)
    return "blurred"


def prepare_price_cropped_photo(item, product_details):
    """Create and verify a price-free photo fallback. Returns (path, check)."""
    page_prices = sorted({
        amount for amount in (
            _price_to_integer((product_details or {}).get("discounted_price")),
            _price_to_integer((product_details or {}).get("original_price")),
        ) if amount is not None
    })
    if not page_prices:
        return None, {
            "ok": False, "status": "unverifiable",
            "reason": "live product page did not expose a price for the photo caption",
            "image_prices": [], "page_prices": [],
        }

    photo_url = refresh_photo_url(int(item["source_message_id"]))
    input_path = output_path = None
    keep_output_path = False
    try:
        with SESSION.get(photo_url, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "image/" not in content_type and "octet-stream" not in content_type:
                raise RuntimeError("Source media is not a recognized image for price cropping.")
            length_header = response.headers.get("Content-Length")
            if length_header and int(length_header) > MAX_PHOTO_BYTES:
                raise RuntimeError("Source image exceeds the configured size limit.")
            total = 0
            with tempfile.NamedTemporaryFile(prefix="dayan-photo-original-", suffix=".jpg", delete=False) as file:
                input_path = file.name
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_PHOTO_BYTES:
                        raise RuntimeError("Source image exceeds the configured size limit.")
                    file.write(chunk)
        if not input_path or os.path.getsize(input_path) < 512:
            raise RuntimeError("Downloaded source image is empty or too small.")

        try:
            ocr_text = _run_tesseract(input_path)
        except Exception as exc:
            return None, {
                "ok": False, "status": "unverifiable",
                "reason": f"image OCR failed ({type(exc).__name__})",
                "image_prices": [], "page_prices": page_prices,
            }
        raw_prices = extract_image_price_values(ocr_text)
        _, boxes = _tesseract_text_and_price_boxes(input_path)
        price_cue = bool(PRICE_REGION_CUE_RE.search(ocr_text))
        if not boxes:
            # Only leave the original alone if OCR can actually read the image
            # and found no displayed-price cue or plausible price amount.
            if not ocr_text.strip() or price_cue or raw_prices:
                return None, {
                    "ok": False, "status": "unverifiable",
                    "reason": "could not locate a price region to safely crop from the photo",
                    "image_prices": raw_prices, "page_prices": page_prices,
                }
            output_file = tempfile.NamedTemporaryFile(prefix="dayan-photo-clean-", suffix=".jpg", delete=False)
            output_path = output_file.name
            output_file.close()
            shutil.copyfile(input_path, output_path)
            keep_output_path = True
            return output_path, {
                "ok": True, "status": "no_price_detected",
                "reason": "OCR found no displayed price; original photo retained",
                "image_prices": [], "page_prices": page_prices, "crop_method": "none",
            }

        output_file = tempfile.NamedTemporaryFile(prefix="dayan-photo-clean-", suffix=".jpg", delete=False)
        output_path = output_file.name
        output_file.close()
        method = _remove_price_boxes(input_path, output_path, boxes)
        try:
            final_ocr = _run_tesseract(output_path)
            remaining_prices = extract_image_price_values(final_ocr)
        except Exception:
            remaining_prices = raw_prices or [1]
        if remaining_prices:
            # If a crop cannot remove an interior price overlay, blur just the
            # detected region and re-run OCR; never publish if a price remains readable.
            method = _remove_price_boxes(input_path, output_path, boxes, force_blur=True)
            try:
                final_ocr = _run_tesseract(output_path)
                remaining_prices = extract_image_price_values(final_ocr)
            except Exception:
                remaining_prices = raw_prices or [1]
        if remaining_prices:
            return None, {
                "ok": False, "status": "unverifiable",
                "reason": "price digits remain readable after cropping/redaction",
                "image_prices": remaining_prices, "page_prices": page_prices,
            }
        keep_output_path = True
        return output_path, {
            "ok": True, "status": "price_removed",
            "reason": "price region was cropped or obscured and post-checked",
            "image_prices": raw_prices, "page_prices": page_prices, "crop_method": method,
        }
    finally:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)
        if not keep_output_path and output_path and os.path.exists(output_path):
            os.remove(output_path)


def send_photo(bot_token, item, affiliate_url, product_details=None, sanitized_photo_path=None):
    product_details = product_details if product_details is not None else fetch_product_details(affiliate_url)
    owns_temp_path = False
    temp_path = sanitized_photo_path
    if not temp_path:
        temp_path, price_check = prepare_price_cropped_photo(item, product_details)
        owns_temp_path = True
        if not price_check.get("ok") or not temp_path:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            raise RuntimeError(
                f"Refusing photo publication: safe price cropping failed ({price_check.get('status', 'unverifiable')})."
            )
    if not os.path.exists(temp_path):
        raise RuntimeError("Verified/cropped photo file no longer exists; refusing publication.")

    caption = build_caption(
        item.get("source_caption", ""), affiliate_url,
        product_details=product_details, allow_source_price_fallback=False
    )
    payload = {
        "chat_id": TARGET_CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }

    try:
        with open(temp_path, "rb") as media_file:
            files = {"photo": (f"dayan-{item['source_message_id']}.jpg", media_file, "image/jpeg")}
            response = SESSION.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                data=payload,
                files=files,
                timeout=(20, 120),
            )
        try:
            result = response.json()
        except ValueError:
            result = {"description": response.text[:300]}
        if response.status_code != 200 or not result.get("ok"):
            raise RuntimeError(f"Telegram sendPhoto failed ({response.status_code}): {result.get('description', 'unknown error')}")
        print(
            f"Photo price handling source={item['source_message_id']}: "
            f"sent price-cropped image (media file verified before upload)."
        )
        return result["result"]["message_id"]
    finally:
        if owns_temp_path and temp_path and os.path.exists(temp_path):
            os.remove(temp_path)



def fetch_posts_since(last_seen_id, max_pages=MAX_POLL_PAGES):
    """Fetch all preview pages newer than the cursor, up to a safe page cap."""
    first_page = fetch_preview()
    collected = {int(item["source_message_id"]): item for item in first_page}
    if last_seen_id is None or not first_page:
        return sorted(collected.values(), key=lambda item: item["source_message_id"])

    page = first_page
    pages = 1
    while page and pages < max_pages:
        oldest_id = min(int(item["source_message_id"]) for item in page)
        if oldest_id <= int(last_seen_id):
            break
        next_page = fetch_preview(before_id=oldest_id)
        new_items = []
        for item in next_page:
            item_id = int(item["source_message_id"])
            if item_id not in collected:
                collected[item_id] = item
                new_items.append(item)
        if not new_items:
            break
        page = next_page
        pages += 1
    if pages >= max_pages:
        print(f"Warning: reached MAX_POLL_PAGES={max_pages}; unusually high source volume may require a larger page cap.")
    return sorted(collected.values(), key=lambda item: item["source_message_id"])


def fetch_recent_archive(max_pages=MAX_POLL_PAGES, max_posts=MAX_ARCHIVE_POSTS):
    """Fetch at most the newest 500 posts from the public archive."""
    page = fetch_preview()
    collected = {int(item["source_message_id"]): item for item in page}
    pages = 1
    while page and pages < max_pages and len(collected) < max_posts:
        oldest_id = min(int(item["source_message_id"]) for item in page)
        next_page = fetch_preview(before_id=oldest_id)
        new_items = []
        for item in next_page:
            item_id = int(item["source_message_id"])
            if item_id not in collected:
                collected[item_id] = item
                new_items.append(item)
        if not new_items:
            break
        collected.update({int(item["source_message_id"]): item for item in new_items})
        page = next_page
        pages += 1
    ordered = sorted(collected.values(), key=lambda item: item["source_message_id"])
    if len(ordered) > max_posts:
        ordered = ordered[-max_posts:]
    print(f"Archive scan: collected {len(ordered)} posts across {pages} page(s), max_posts={max_posts}.")
    return ordered


def inspect_source_message(source_message_id):
    response = SESSION.get(SOURCE_URL, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.select(".tgme_widget_message"):
        post_ref = node.get("data-post")
        if not post_ref:
            parent = node.find_parent(attrs={"data-post": True})
            post_ref = parent.get("data-post") if parent else None
        if not post_ref:
            for parent in node.parents:
                post_ref = parent.get("data-post")
                if post_ref:
                    break
        if not post_ref or not post_ref.endswith("/" + str(source_message_id)):
            continue

        text_node = node.select_one(".tgme_widget_message_text")
        caption = text_node.get_text("\n", strip=True) if text_node else ""
        short_caption = re.sub(r"\s+", " ", caption)[:500]
        print(f"Source post: https://t.me/{SOURCE_CHANNEL}/{source_message_id}")
        print("Caption: " + (short_caption or "(empty)"))
        print(f"Message classes: {node.get('class', [])}")
        media_count = 0
        for element in node.select("video, source, img, .tgme_widget_message_photo_wrap, a.tgme_widget_message_document_wrap"):
            attrs = {}
            for attr in ("src", "data-src", "href", "type", "class", "style"):
                value = element.get(attr)
                if value:
                    attrs[attr] = value[:400] if isinstance(value, str) else value
            if attrs:
                print("Media element: " + json.dumps(attrs, ensure_ascii=False))
                media_count += 1
                if media_count >= 12:
                    break
        print(f"Media elements found: {media_count}")
        return
    # Historical archive posts are not necessarily included in the newest page.
    historical = fetch_preview(before_id=int(source_message_id) + 1)
    item = next((p for p in historical if int(p["source_message_id"]) == int(source_message_id)), None)
    if item:
        print(f"Source post: {item['source_url']}")
        short_caption = re.sub(r"\\s+", " ", item.get("source_caption", ""))[:500]
        print("Caption: " + (short_caption or "(empty)"))
        print(f"Photo URL available: {'yes' if item.get('photo_url') else 'no'}")
        print(f"Video URL available: {'yes' if item.get('video_url') else 'no'}")
        print(f"Product refs: {item.get('product_refs', [])}")
        return
    raise RuntimeError(f"Source message {source_message_id} was not found in the current or historical public preview.")


def inspect_product_page(route_and_code):
    match = re.fullmatch(r"(lead|fastcart):(\d{4,8})", route_and_code.strip().lower())
    if not match:
        raise RuntimeError("Usage: relay_botapi.py --inspect-product <lead|fastcart>:<product_code>")
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    affiliate_url = make_affiliate_url(store_base, {"route": match.group(1), "code": match.group(2)})
    details = fetch_product_details(affiliate_url)
    print("Product-page inspection — no Telegram message was sent.")
    print(f"Title: {details.get('title') or 'NOT FOUND'}")
    print(f"Original price: {details.get('original_price') or 'NOT FOUND'}")
    print(f"Discounted/current price: {details.get('discounted_price') or 'NOT FOUND'}")
    if not any(details.get(key) for key in ("title", "original_price", "discounted_price")):
        sys.exit(4)


def edit_existing_caption(source_message_id, destination_message_id):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.")
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    posts = fetch_preview()
    item = next((p for p in posts if int(p["source_message_id"]) == int(source_message_id)), None)
    if item is None:
        posts = fetch_preview(before_id=int(source_message_id) + 1)
        item = next((p for p in posts if int(p["source_message_id"]) == int(source_message_id)), None)
    if item is None:
        raise RuntimeError(f"Source post {source_message_id} was not found in the current or historical public preview.")
    overrides = read_json(OVERRIDES_FILE, {})
    product_ref = resolve_product_ref(item, overrides)
    if not product_ref:
        raise RuntimeError(f"Source post {source_message_id} has no unambiguous product route/code.")
    affiliate_url = make_affiliate_url(store_base, product_ref)
    product_details = fetch_product_details(affiliate_url)
    caption = build_caption(item.get("source_caption", ""), affiliate_url, product_details=product_details)
    payload = {
        "chat_id": TARGET_CHANNEL,
        "message_id": int(destination_message_id),
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }
    response = SESSION.post(
        f"https://api.telegram.org/bot{bot_token}/editMessageCaption",
        data=payload,
        timeout=(15, 45),
    )
    try:
        result = response.json()
    except ValueError:
        result = {"description": response.text[:300]}
    if response.status_code != 200 or not result.get("ok"):
        raise RuntimeError(f"Telegram editMessageCaption failed ({response.status_code}): {result.get('description', 'unknown error')}")
    print(
        f"TEST CAPTION UPDATED source={item['source_url']} target={TARGET_CHANNEL} "
        f"destination_message_id={destination_message_id} route={product_ref['route']} "
        f"product_code={product_ref['code']}"
    )


def run_test_post(source_message_id):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.")
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    posts = fetch_preview()
    item = next((p for p in posts if int(p["source_message_id"]) == int(source_message_id)), None)
    if item is None:
        raise RuntimeError(f"Test source post {source_message_id} was not found in the current public preview.")
    if not item.get("video_url") and not item.get("photo_url"):
        raise RuntimeError(f"Test source post {source_message_id} has no direct video or photo URL; refusing to publish.")
    overrides = read_json(OVERRIDES_FILE, {})
    product_ref = resolve_product_ref(item, overrides)
    if not product_ref:
        raise RuntimeError(f"Test source post {source_message_id} has no unambiguous product code/route; refusing to publish.")
    affiliate_url = make_affiliate_url(store_base, product_ref)
    product_details = fetch_product_details(affiliate_url)
    sanitized_photo_path = None
    if item.get("video_url"):
        price_check = check_source_media_prices(item, product_details)
        if not price_check.get("ok"):
            raise RuntimeError(
                f"Refusing test video because price verification failed: {price_check.get('status')}."
            )
        destination_message_id = send_video(bot_token, item, affiliate_url, product_details=product_details)
        media_type = "video"
    else:
        sanitized_photo_path, price_check = prepare_price_cropped_photo(item, product_details)
        print(f"Test photo price handling: status={price_check.get('status')}, image_prices={price_check.get('image_prices', [])}, page_prices={price_check.get('page_prices', [])}, crop_method={price_check.get('crop_method', 'none')}.")
        if not price_check.get("ok") or not sanitized_photo_path:
            if sanitized_photo_path and os.path.exists(sanitized_photo_path):
                os.remove(sanitized_photo_path)
            raise RuntimeError(
                f"Refusing test photo because price removal could not be verified: {price_check.get('status')}."
            )
        try:
            destination_message_id = send_photo(
                bot_token, item, affiliate_url, product_details=product_details,
                sanitized_photo_path=sanitized_photo_path
            )
        finally:
            if os.path.exists(sanitized_photo_path):
                os.remove(sanitized_photo_path)
        media_type = "photo"
    print(
        f"TEST POST SENT source={item['source_url']} target={TARGET_CHANNEL} "
        f"destination_message_id={destination_message_id} media={media_type} "
        f"route={product_ref['route']} product_code={product_ref['code']}"
    )


def publish_best_archive_post():
    """Publish the highest-scoring eligible product from up to 500 recent archive posts."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.")
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    state = read_json(STATE_FILE, {
        "initialized": False, "last_seen_id": 0, "queue": [],
        "published_slots": [], "sent_source_ids": [], "sent_product_codes": []
    })
    state = ensure_price_check_version(state)
    overrides = read_json(OVERRIDES_FILE, {})
    now = datetime.now(TIMEZONE)
    archive_posts = fetch_recent_archive(max_pages=MAX_POLL_PAGES)
    sent_codes = {str(code) for code in state.get("sent_product_codes", [])}
    sent_ids = {int(value) for value in state.get("sent_source_ids", [])}
    for queued in state.get("queue", []):
        queued_ref = resolve_product_ref(queued, overrides)
        if queued_ref:
            sent_codes.add(str(queued_ref["code"]))
    candidates = rank_archive_candidates(
        archive_posts, overrides, sent_product_codes=sent_codes,
        sent_source_ids=sent_ids, now=now,
        rejected_product_codes=state.get("price_rejected_product_codes", []),
        rejected_source_ids=state.get("price_rejected_source_ids", []),
    )
    chosen, product_ref, product_details, sanitized_photo_path = select_next_price_verified_candidate(
        candidates, overrides, sent_codes, store_base, state
    )
    if not chosen or not product_ref:
        write_state(state)
        raise RuntimeError("No unpublished product passed the media-specific price checks.")
    affiliate_url = make_affiliate_url(store_base, product_ref)
    media_type = chosen["media_type"]
    try:
        if media_type == "video":
            destination_message_id = send_video(bot_token, chosen, affiliate_url, product_details=product_details)
        else:
            destination_message_id = send_photo(
                bot_token, chosen, affiliate_url, product_details=product_details,
                sanitized_photo_path=sanitized_photo_path
            )
    finally:
        if sanitized_photo_path and os.path.exists(sanitized_photo_path):
            os.remove(sanitized_photo_path)

    state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
    state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
    state.setdefault("sent_product_codes", []).append(str(product_ref["code"]))
    state["sent_product_codes"] = state["sent_product_codes"][-MAX_SENT_IDS:]
    # Count this immediate post against the current half-hour slot when due.
    # The routine scheduler will then avoid posting twice in the same slot.
    slot_key = due_slot(now, state.get("published_slots", []))
    if slot_key:
        state.setdefault("published_slots", []).append(slot_key)
        state["published_slots"] = list(dict.fromkeys(state["published_slots"]))[-60:]
    state["last_published_at"] = now.isoformat()
    state["last_destination_message_id"] = str(destination_message_id)
    state.pop("last_publish_error", None)
    write_state(state)
    print(
        f"ARCHIVE BEST POST SENT source={chosen['source_url']} target={TARGET_CHANNEL} "
        f"destination_message_id={destination_message_id} media={media_type} "
        f"market_demand={chosen.get('market_demand_score', 0)}/75 "
        f"total={chosen.get('popularity_score', 0)}/100 "
        f"category={chosen.get('product_category', 'unknown')} product_code={product_ref['code']}"
    )


def main():
    if "--edit-caption" in sys.argv:
        index = sys.argv.index("--edit-caption")
        if index + 2 >= len(sys.argv) or not re.fullmatch(r"\d{1,8}", sys.argv[index + 1]) or not re.fullmatch(r"\d{1,8}", sys.argv[index + 2]):
            raise RuntimeError("Usage: relay_botapi.py --edit-caption <source_message_id> <destination_message_id>")
        edit_existing_caption(int(sys.argv[index + 1]), int(sys.argv[index + 2]))
        return

    if "--inspect-message" in sys.argv:
        index = sys.argv.index("--inspect-message")
        if index + 1 >= len(sys.argv) or not re.fullmatch(r"\d{1,8}", sys.argv[index + 1]):
            raise RuntimeError("Usage: relay_botapi.py --inspect-message <source_message_id>")
        inspect_source_message(int(sys.argv[index + 1]))
        return

    if "--inspect-product" in sys.argv:
        index = sys.argv.index("--inspect-product")
        if index + 1 >= len(sys.argv):
            raise RuntimeError("Usage: relay_botapi.py --inspect-product <lead|fastcart>:<product_code>")
        inspect_product_page(sys.argv[index + 1])
        return

    if "--test-post" in sys.argv:
        index = sys.argv.index("--test-post")
        if index + 1 >= len(sys.argv) or not re.fullmatch(r"\d{1,8}", sys.argv[index + 1]):
            raise RuntimeError("Usage: relay_botapi.py --test-post <source_message_id>")
        run_test_post(int(sys.argv[index + 1]))
        return

    if "--publish-best-archive" in sys.argv:
        publish_best_archive_post()
        return

    if "--check" in sys.argv:
        posts = fetch_posts_since(None)
        video_posts = [item for item in posts if item.get("video_url")]
        latest = max(posts, key=lambda item: int(item["source_message_id"])) if posts else None
        print("Public Telegram preview diagnostic — no publishing occurs.")
        print(f"Parsed channel messages in current preview: {len(posts)}")
        print(f"Messages with direct video sources: {len(video_posts)}")
        if latest:
            print(f"Newest source post: {latest['source_url']}")
            print(f"Newest source post date: {latest.get('source_date') or 'not exposed'}")
        print("Recent source entries (newest first):")
        for item in list(reversed(posts))[:20]:
            snippet = re.sub(r"\s+", " ", item.get("source_caption", "")).strip()[:110]
            media_type = "video-url" if item.get("video_url") else "no-video-url"
            print(f"- id={item['source_message_id']} date={item.get('source_date') or '?'} media={media_type} refs={item.get('product_refs', [])} caption={snippet!r}")
        if not video_posts:
            print("No direct video URLs were extracted from the current public preview.")
            sys.exit(3)
        for item in video_posts[:2]:
            try:
                media_response = SESSION.get(
                    item["video_url"], headers={"Range": "bytes=0-1"},
                    timeout=15, stream=True
                )
                print(
                    f"Media check id={item['source_message_id']}: "
                    f"HTTP {media_response.status_code}; "
                    f"type={media_response.headers.get('Content-Type', 'unknown')}; "
                    f"length={media_response.headers.get('Content-Length', 'unknown')}"
                )
                media_response.close()
            except requests.RequestException as exc:
                print(f"Media check id={item['source_message_id']} failed: {type(exc).__name__}")
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    if not bot_token:
        print("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        sys.exit(2)

    state = read_json(STATE_FILE, {
        "initialized": False, "last_seen_id": 0, "queue": [],
        "published_slots": [], "sent_source_ids": []
    })
    state = ensure_price_check_version(state)
    overrides = read_json(OVERRIDES_FILE, {})
    now = datetime.now(TIMEZONE)
    # On every scheduled run, re-rank the accessible archive, not just new source IDs.
    # The first run still establishes a baseline and never backfills old content by surprise.
    if state.get("initialized"):
        posts = fetch_recent_archive(max_pages=MAX_POLL_PAGES)
    else:
        posts = fetch_posts_since(None)
    if not posts:
        raise RuntimeError("No channel messages were parsed from the public Telegram preview.")

    latest_id = max(int(p["source_message_id"]) for p in posts)
    if not state.get("initialized"):
        state["initialized"] = True
        state["last_seen_id"] = latest_id
        write_state(state)
        print(f"Baseline established at source message {latest_id}. Old posts will not be republished.")
        return

    last_seen = int(state.get("last_seen_id", 0))
    queue = state.setdefault("queue", [])
    sent_ids = {int(x) for x in state.get("sent_source_ids", [])}
    sent_product_codes = {str(x) for x in state.get("sent_product_codes", [])}
    rejected_price_source_ids = {int(x) for x in state.get("price_rejected_source_ids", [])}
    rejected_price_product_codes = {str(x) for x in state.get("price_rejected_product_codes", [])}
    archive_video_codes = set()
    for source_item in posts:
        if not source_item.get("video_url"):
            continue
        source_id = int(source_item.get("source_message_id", 0) or 0)
        source_ref = resolve_product_ref(source_item, overrides)
        if source_ref and source_id not in sent_ids and source_id not in rejected_price_source_ids:
            if str(source_ref["code"]) not in sent_product_codes and str(source_ref["code"]) not in rejected_price_product_codes:
                archive_video_codes.add(str(source_ref["code"]))
    if archive_video_codes:
        before_queue_count = len(queue)
        queue[:] = [
            queued for queued in queue
            if not (
                (queued.get("media_type") or ("video" if queued.get("video_url") else "photo")) == "photo"
                and str((resolve_product_ref(queued, overrides) or {}).get("code", "")) in archive_video_codes
            )
        ]
        if len(queue) != before_queue_count:
            print(f"Removed {before_queue_count - len(queue)} queued photo(s) superseded by available videos.")
    queued_ids = {int(x["source_message_id"]) for x in queue}
    queued_product_codes = set()
    for queued_item in queue:
        queued_ref = resolve_product_ref(queued_item, overrides)
        if queued_ref:
            queued_product_codes.add(str(queued_ref["code"]))
    new_ids = []

    for item in sorted(
        posts,
        key=lambda post: (
            0 if post.get("video_url") else 1,
            -int(post.get("source_message_id", 0) or 0),
        ),
    ):
        mid = int(item["source_message_id"])
        if mid > last_seen:
            new_ids.append(mid)
        if mid in queued_ids or mid in sent_ids or mid in rejected_price_source_ids:
            continue
        media_type = "video" if item.get("video_url") else "photo" if item.get("photo_url") else None
        if media_type is None:
            continue
        product_ref = resolve_product_ref(item, overrides)
        if not product_ref:
            print(f"Skipping source {mid}: no unambiguous product route/code.")
            continue
        product_code = str(product_ref["code"])
        if product_code in sent_product_codes or product_code in queued_product_codes or product_code in rejected_price_product_codes:
            print(f"Skipping source {mid}: product code {product_code} was already published, queued, or rejected by the price check.")
            continue

        ranking = score_product_potential(item, now=now)
        item["status"] = "queued"
        item["queued_at"] = now.isoformat()
        item["media_type"] = media_type
        item["popularity_score"] = ranking["score"]
        item["market_demand_score"] = ranking["market_demand_score"]
        item["product_category"] = ranking["category"]
        item.pop("video_url", None)
        item.pop("photo_url", None)
        queue.append(item)
        queued_ids.add(mid)
        queued_product_codes.add(product_code)
        print(
            f"Queued source {mid}: media={media_type}, market_demand={ranking['market_demand_score']}/75, "
            f"total={ranking['score']}/100, category={ranking['category']}, "
            f"views={item.get('views') if item.get('views') is not None else 'unknown'}, "
            f"price={ranking['price_toman'] if ranking['price_toman'] is not None else 'unknown'}."
        )

    if new_ids:
        state["last_seen_id"] = max([last_seen] + new_ids)
    if len(queue) > MAX_QUEUE_ITEMS:
        queue[:] = queue[-MAX_QUEUE_ITEMS:]

    slot_key = due_slot(now, state.get("published_slots", []))
    if slot_key:
        chosen, chosen_ref, product_details, sanitized_photo_path = select_next_price_verified_candidate(
            queue, overrides, sent_product_codes, store_base, state
        )
        if chosen:
            affiliate_url = make_affiliate_url(store_base, chosen_ref)
            media_type = chosen.get("media_type") or "video"
            try:
                if media_type == "video":
                    telegram_message_id = send_video(bot_token, chosen, affiliate_url, product_details=product_details)
                else:
                    telegram_message_id = send_photo(
                        bot_token, chosen, affiliate_url, product_details=product_details,
                        sanitized_photo_path=sanitized_photo_path
                    )
            except Exception as exc:
                # Persist the cursor and queue before the next scheduled retry.
                # Never persist exception text because HTTP exceptions may contain URLs/tokens.
                state["last_publish_error"] = {
                    "source_message_id": int(chosen["source_message_id"]),
                    "error_type": type(exc).__name__,
                    "attempted_at": now.isoformat(),
                }
                write_state(state)
                print(f"::warning::Publish attempt for source {chosen['source_message_id']} failed ({type(exc).__name__}); item remains queued for retry.")
                return
            finally:
                if sanitized_photo_path and os.path.exists(sanitized_photo_path):
                    os.remove(sanitized_photo_path)
            queue.remove(chosen)
            state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
            state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
            state.setdefault("sent_product_codes", []).append(str(chosen_ref["code"]))
            state["sent_product_codes"] = state["sent_product_codes"][-MAX_SENT_IDS:]
            state.setdefault("published_slots", []).append(slot_key)
            state["published_slots"] = state["published_slots"][-60:]
            state["last_published_at"] = now.isoformat()
            state["last_destination_message_id"] = str(telegram_message_id)
            state.pop("last_publish_error", None)
            print(
                f"Published source {chosen['source_message_id']} to {TARGET_CHANNEL}: "
                f"media={media_type}, market_demand={chosen.get('market_demand_score', 0)}/75, "
                f"total={chosen.get('popularity_score', 0)}/100, "
                f"category={chosen.get('product_category', 'unknown')}, "
                f"product_code={chosen_ref['code']}."
            )
        else:
            print(f"No price-verified, unpublished photo/video candidate with a valid product link was available for slot {slot_key}; nothing published.")

    write_state(state)
    print(f"Completed. Parsed {len(posts)} source messages; queued={len(queue)}; newest source ID={state['last_seen_id']}")

if __name__ == "__main__":
    main()
