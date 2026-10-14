import html as html_lib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, time
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
SOURCE_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
TIMEZONE = ZoneInfo("Asia/Tehran")
PUBLISH_SLOTS = ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "20:30", "22:00"]
SLOT_GRACE_MINUTES = 55
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000
MAX_VIDEO_BYTES = 49 * 1024 * 1024
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
        line = re.sub(r"#اینستاگرام", "", line, flags=re.IGNORECASE)
        line = URL_RE.sub("", line)
        if re.search(r"(?:آدرس|ادرس)\s*فروشگا\S*\s*/\s*(?:lead|fastcart)/\d+", line, re.IGNORECASE):
            continue
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
        parsed.append({
            "source_message_id": message_id,
            "source_url": f"https://t.me/{SOURCE_CHANNEL}/{message_id}",
            "source_caption": caption,
            "product_refs": extract_product_refs(caption),
            "video_url": media_url,
            "source_date": time_node.get("datetime") if time_node else None,
        })
    return sorted(parsed, key=lambda item: item["source_message_id"])

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

def fetch_product_details(affiliate_url):
    try:
        response = SESSION.get(affiliate_url, timeout=(15, 25), allow_redirects=True)
        response.raise_for_status()
        details = extract_product_details(response.text)
        found = bool(details.get("title") or details.get("original_price") or details.get("discounted_price"))
        print(
            "Product-page enrichment: "
            f"title={'yes' if details.get('title') else 'no'}, "
            f"original_price={'yes' if details.get('original_price') else 'no'}, "
            f"discounted_price={'yes' if details.get('discounted_price') else 'no'}"
        )
        if not found:
            print("Product page loaded but no structured title/price fields were recognized; safe fallback caption will be used.")
        return details
    except Exception as exc:
        # Avoid logging the full exception because request exceptions can expose
        # the personal store URL.
        print(f"Product-page enrichment unavailable ({type(exc).__name__}); safe fallback caption will be used.")
        return {"title": None, "original_price": None, "discounted_price": None, "page_found": False}

def build_caption(source_caption, affiliate_url, product_details=None, prefix=""):
    details = product_details or {}
    chunks = []
    prefix = (prefix or "").strip()
    if prefix:
        chunks.append(prefix)

    title = re.sub(r"\s+", " ", str(details.get("title") or "")).strip()
    if title:
        chunks.append("🛍 " + title)

    original = details.get("original_price")
    discounted = details.get("discounted_price")
    if original and discounted and original != discounted:
        chunks.append(f"💸 قیمت اصلی: <s>{html_lib.escape(original)}</s>\n🔥 قیمت با تخفیف: <b>{html_lib.escape(discounted)}</b>")
    elif discounted:
        chunks.append(f"💰 قیمت: <b>{html_lib.escape(str(discounted))}</b>")
    elif original:
        chunks.append(f"💰 قیمت اعلام‌شده: <b>{html_lib.escape(str(original))}</b>")

    intro = clean_caption(source_caption)
    if intro:
        chunks.append(intro)

    # These buyer-facing guarantees are intentionally shown on every post,
    # per the channel owner's request.
    chunks.append("\n".join(PRODUCT_BENEFITS))
    chunks.append(
        "🛍 مشاهده و خرید:\n" + html_lib.escape(affiliate_url, quote=True)

    )

    caption = "\n\n".join(chunks)
    if len(caption) > 1024:
        # Preserve the fixed buyer benefits, link, and disclosure even when a
        # source caption or product title is unexpectedly long.
        fixed_tail = "\n".join(PRODUCT_BENEFITS) + "\n\n🛍 مشاهده و خرید:\n" + html_lib.escape(affiliate_url, quote=True)
        title_part = ("🛍 " + title + "\n\n") if title else ""
        price_part = ""
        if original and discounted and original != discounted:
            price_part = f"💸 قیمت اصلی: <s>{html_lib.escape(original)}</s>\n🔥 قیمت با تخفیف: <b>{html_lib.escape(discounted)}</b>\n\n"
        elif discounted:
            price_part = f"💰 قیمت: <b>{html_lib.escape(str(discounted))}</b>\n\n"
        prefix_part = (prefix + "\n\n") if prefix else ""
        room = max(0, 1024 - len(fixed_tail) - len(title_part) - len(price_part) - len(prefix_part) - 8)
        intro = clean_caption(source_caption)[:room].rstrip()
        caption = prefix_part + title_part + price_part + ((intro + "\n\n") if intro else "") + fixed_tail
        if len(caption) > 1024:
            # The title remains useful; trim it only as a last resort.
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


def run_test_post(source_message_id):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.")
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    posts = fetch_preview()
    item = next((p for p in posts if int(p["source_message_id"]) == int(source_message_id)), None)
    if item is None:
        raise RuntimeError(f"Test source post {source_message_id} was not found in the current public preview.")
    if not item.get("video_url"):
        raise RuntimeError(f"Test source post {source_message_id} has no direct video URL; refusing to publish.")
    overrides = read_json(OVERRIDES_FILE, {})
    product_ref = resolve_product_ref(item, overrides)
    if not product_ref:
        raise RuntimeError(f"Test source post {source_message_id} has no unambiguous product code/route; refusing to publish.")
    affiliate_url = make_affiliate_url(store_base, product_ref)
    destination_message_id = send_video(bot_token, item, affiliate_url)
    print(
        f"TEST POST SENT source={item['source_url']} target={TARGET_CHANNEL} "
        f"destination_message_id={destination_message_id} "
        f"route={product_ref['route']} product_code={product_ref['code']}"
    )


def main():
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
    posts = fetch_posts_since(int(state.get("last_seen_id", 0)) if state.get("initialized") else None)
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
    new_ids = []

    for item in posts:
        mid = int(item["source_message_id"])
        if mid <= last_seen:
            continue
        new_ids.append(mid)
        if mid in queued_ids or mid in sent_ids or not item.get("video_url"):
            continue
        item["status"] = "queued"
        item["queued_at"] = now.isoformat()
        # Do not persist expiring media URLs or affiliate URLs in the public repo.
        item.pop("video_url", None)
        queue.append(item)
        queued_ids.add(mid)

    if new_ids:
        state["last_seen_id"] = max([last_seen] + new_ids)
    if len(queue) > MAX_QUEUE_ITEMS:
        queue[:] = queue[-MAX_QUEUE_ITEMS:]

    slot_key = due_slot(now, state.get("published_slots", []))
    if slot_key:
        chosen = None
        chosen_ref = None
        for item in queue:
            product_ref = resolve_product_ref(item, overrides)
            if product_ref:
                chosen, chosen_ref = item, product_ref
                break
        if chosen:
            affiliate_url = make_affiliate_url(store_base, chosen_ref)
            try:
                telegram_message_id = send_video(bot_token, chosen, affiliate_url)
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
            state.setdefault("published_slots", []).append(slot_key)
            state["published_slots"] = state["published_slots"][-60:]
            state["last_published_at"] = now.isoformat()
            state["last_destination_message_id"] = str(telegram_message_id)
            state.pop("last_publish_error", None)
            print(f"Published source {chosen['source_message_id']} to {TARGET_CHANNEL} with {chosen_ref['route']} code {chosen_ref['code']}.")
        else:
            print(f"No new video with one unambiguous product route/code for slot {slot_key}; nothing published.")

    write_state(state)
    print(f"Completed. Parsed {len(posts)} source messages; queued={len(queue)}; newest source ID={state['last_seen_id']}")

if __name__ == "__main__":
    main()
