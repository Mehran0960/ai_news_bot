import html as html_lib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, time, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

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
PUBLISH_SLOTS = [f"{hour:02d}:00" for hour in range(24)]
SLOT_GRACE_MINUTES = 55
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000
MAX_VIDEO_BYTES = 49 * 1024 * 1024
MAX_PHOTO_BYTES = 9 * 1024 * 1024
MAX_POLL_PAGES = 25
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
    """Rank market demand first; use video format only as a secondary preference."""
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
        # Sort by market demand first, then overall commercial fit, then video.
        candidates.append((-demand_score, -total_score, 0 if media_type == "video" else 1, -message_id, item, product_ref))
    if not candidates:
        return None, None
    candidates.sort(key=lambda candidate: candidate[:4])
    return candidates[0][4], candidates[0][5]


def rank_archive_candidates(posts, overrides, sent_product_codes=None, sent_source_ids=None, now=None):
    """Score recent archive posts; market demand leads and video breaks ties."""
    sent_codes = {str(code) for code in (sent_product_codes or [])}
    sent_ids = {int(value) for value in (sent_source_ids or [])}
    used_codes = set(sent_codes)
    prepared_posts = []
    # Start with newest posts so a repeated product is represented by its freshest post.
    for item in sorted(posts, key=lambda post: int(post.get("source_message_id", 0) or 0), reverse=True):
        message_id = int(item.get("source_message_id", 0) or 0)
        if message_id in sent_ids:
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

def build_caption(source_caption, affiliate_url, product_details=None):
    details = fill_price_fallback(source_caption, product_details)
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

def send_video(bot_token, item, affiliate_url):
    media_url = refresh_video_url(int(item["source_message_id"]))
    product_details = fetch_product_details(affiliate_url)
    caption = build_caption(
        item.get("source_caption", ""), affiliate_url,
        product_details=product_details
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


def send_photo(bot_token, item, affiliate_url):
    photo_url = refresh_photo_url(int(item["source_message_id"]))
    product_details = fetch_product_details(affiliate_url)
    caption = build_caption(
        item.get("source_caption", ""), affiliate_url,
        product_details=product_details
    )
    payload = {
        "chat_id": TARGET_CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }

    temp_path = None
    try:
        with SESSION.get(photo_url, stream=True, timeout=(15, 45)) as media_response:
            media_response.raise_for_status()
            content_type = (media_response.headers.get("Content-Type") or "").lower()
            if "image/" not in content_type and "octet-stream" not in content_type:
                raise RuntimeError(f"Source media is not a recognized image (Content-Type={content_type or 'missing'}).")
            length_header = media_response.headers.get("Content-Length")
            if length_header and int(length_header) > MAX_PHOTO_BYTES:
                raise RuntimeError("Source photo exceeds the configured Telegram upload limit.")
            total = 0
            with tempfile.NamedTemporaryFile(prefix="dayan-", suffix=".jpg", delete=False) as temp_file:
                temp_path = temp_file.name
                for chunk in media_response.iter_content(chunk_size=512 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_PHOTO_BYTES:
                        raise RuntimeError("Source photo exceeds the configured Telegram upload limit.")
                    temp_file.write(chunk)
        if not temp_path or os.path.getsize(temp_path) < 512:
            raise RuntimeError("Downloaded photo is empty or unexpectedly small; refusing to publish.")
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
        return result["result"]["message_id"]
    finally:
        if temp_path and os.path.exists(temp_path):
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


def fetch_recent_archive(max_pages=MAX_POLL_PAGES):
    """Fetch up to MAX_POLL_PAGES of the public archive even when posts are old."""
    page = fetch_preview()
    collected = {int(item["source_message_id"]): item for item in page}
    pages = 1
    while page and pages < max_pages:
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
    print(f"Archive scan: collected {len(collected)} posts across {pages} page(s), cap={max_pages}.")
    return sorted(collected.values(), key=lambda item: item["source_message_id"])


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
    raise RuntimeError(f"Source message {source_message_id} was not found in the current public preview.")


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
        raise RuntimeError(f"Source post {source_message_id} was not found in the current public preview.")
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
    if item.get("video_url"):
        destination_message_id = send_video(bot_token, item, affiliate_url)
        media_type = "video"
    else:
        destination_message_id = send_photo(bot_token, item, affiliate_url)
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
        sent_source_ids=sent_ids, now=now
    )
    chosen, product_ref = select_next_candidate(candidates, overrides, sent_codes)
    if not chosen or not product_ref:
        raise RuntimeError("No eligible unpublished product with accessible photo/video and product link was found in the scanned archive.")
    affiliate_url = make_affiliate_url(store_base, product_ref)
    media_type = chosen["media_type"]
    if media_type == "video":
        destination_message_id = send_video(bot_token, chosen, affiliate_url)
    else:
        destination_message_id = send_photo(bot_token, chosen, affiliate_url)

    state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
    state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
    state.setdefault("sent_product_codes", []).append(str(product_ref["code"]))
    state["sent_product_codes"] = state["sent_product_codes"][-MAX_SENT_IDS:]
    # Count this immediate post against the current hourly slot when still within
    # the normal publication grace window, so the scheduled job won't double-post.
    if now.minute <= SLOT_GRACE_MINUTES:
        slot_key = f"{now.date().isoformat()}|{now.hour:02d}:00"
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
    overrides = read_json(OVERRIDES_FILE, {})
    now = datetime.now(TIMEZONE)
    # On every hourly run, re-rank the accessible archive, not just new source IDs.
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
    queued_ids = {int(x["source_message_id"]) for x in queue}
    sent_ids = {int(x) for x in state.get("sent_source_ids", [])}
    sent_product_codes = {str(x) for x in state.get("sent_product_codes", [])}
    queued_product_codes = set()
    for queued_item in queue:
        queued_ref = resolve_product_ref(queued_item, overrides)
        if queued_ref:
            queued_product_codes.add(str(queued_ref["code"]))
    new_ids = []

    for item in sorted(posts, key=lambda post: int(post["source_message_id"]), reverse=True):
        mid = int(item["source_message_id"])
        if mid > last_seen:
            new_ids.append(mid)
        if mid in queued_ids or mid in sent_ids:
            continue
        media_type = "video" if item.get("video_url") else "photo" if item.get("photo_url") else None
        if media_type is None:
            continue
        product_ref = resolve_product_ref(item, overrides)
        if not product_ref:
            print(f"Skipping source {mid}: no unambiguous product route/code.")
            continue
        product_code = str(product_ref["code"])
        if product_code in sent_product_codes or product_code in queued_product_codes:
            print(f"Skipping source {mid}: product code {product_code} was already published or queued.")
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
        chosen, chosen_ref = select_next_candidate(queue, overrides, sent_product_codes)
        if chosen:
            affiliate_url = make_affiliate_url(store_base, chosen_ref)
            media_type = chosen.get("media_type") or "video"
            try:
                if media_type == "video":
                    telegram_message_id = send_video(bot_token, chosen, affiliate_url)
                else:
                    telegram_message_id = send_photo(bot_token, chosen, affiliate_url)
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
            print(f"No valid new video/photo candidate with a product route/code for slot {slot_key}; nothing published.")

    write_state(state)
    print(f"Completed. Parsed {len(posts)} source messages; queued={len(queue)}; newest source ID={state['last_seen_id']}")

if __name__ == "__main__":
    main()
