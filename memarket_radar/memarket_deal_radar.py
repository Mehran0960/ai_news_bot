#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import mimetypes
import os
import re
import subprocess
import uuid
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

CHANNEL = os.getenv("MEMARKET_CHANNEL", "memarket").strip()
CHANNEL_URL = f"https://t.me/s/{CHANNEL}"
STATE = Path("memarket_radar/state.json")

AFF = os.getenv("MEMARKET_AFFILIATE_CODE", "").strip()
BOT = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MIN_PERCENT = float(os.getenv("MIN_DISCOUNT", "30"))
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "3"))
COOLDOWN = float(os.getenv("COOLDOWN_HOURS", "6")) * 3600
BOOTSTRAP_SILENT = os.getenv("BOOTSTRAP_SILENT", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
STATE_COMMIT = os.getenv("STATE_COMMIT", "true").lower() == "true"
MAX_SEEN = int(os.getenv("MAX_SEEN_POSTS", "500"))
MAX_POST_AGE_HOURS = float(os.getenv("MAX_POST_AGE_HOURS", "72"))
PENDING_RETRY_HOURS = float(os.getenv("PENDING_RETRY_HOURS", "6"))

if not DRY_RUN:
    for n, v in {
        "MEMARKET_AFFILIATE_CODE": AFF,
        "TELEGRAM_BOT_TOKEN": BOT,
        "TELEGRAM_CHAT_ID": CHAT,
    }.items():
        if not v:
            raise SystemExit(f"Missing required secret: {n}")


def fetch(url, timeout=30):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 MeMarketDealRadar/2.0",
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def fa_to_en(s: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,.")
    return s.translate(table)


def clean_text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t]+", " ", fragment)
    fragment = re.sub(r"\n[ \t]+", "\n", fragment)
    return fragment.strip()


def extract_posts(page: str):
    posts = []

    # Telegram's public HTML is intentionally kept simple here: find every
    # message wrapper and then extract its visible text/links from inside.
    wrapper_re = re.compile(
        r'<div[^>]+data-post="([^"]+)"[^>]*>(.*?)(?=<div[^>]+data-post="[^"]+"[^>]*>|</main>|\Z)',
        re.S | re.I,
    )

    for m in wrapper_re.finditer(page):
        post_key, block = m.group(1), m.group(2)

        tm = re.search(
            r'<div[^>]+class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            block,
            re.S | re.I,
        )
        if not tm:
            continue

        text_value = clean_text(tm.group(1))
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', tm.group(1), re.I)
        links += re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', block, re.I)

        # Telegram post artwork is often stored as a CSS background, not an <img>.
        images = re.findall(
            r'background-image\s*:\s*url\((?:&quot;|["\']?)(https?://[^"\')]+)',
            block,
            re.I,
        )
        images += re.findall(
            r'<img[^>]+(?:src|data-src)=["\'](https?://[^"\']+)["\']',
            block,
            re.I,
        )

        published_ts = None
        date_match = re.search(r'<time\b[^>]*datetime=["\']([^"\']+)["\']', block, re.I)
        if date_match:
            try:
                published_ts = dt.datetime.fromisoformat(
                    date_match.group(1).strip().replace("Z", "+00:00")
                ).timestamp()
            except (ValueError, OverflowError):
                published_ts = None

        post_id = post_key.rsplit("/", 1)[-1]
        posts.append({
            "id": post_id,
            "key": post_key,
            "url": f"https://t.me/{post_key}",
            "text": text_value,
            "links": list(dict.fromkeys(links)),
            "image": images[0] if images else "",
            "published_ts": published_ts,
        })

    return posts


def affiliate_link(url: str) -> str:
    try:
        p = urlsplit(url)
    except Exception:
        return ""

    host = (p.hostname or "").lower()

    # MeMarket has announced that memarketshop/mmkt domains are retired.
    # Never send buyers to that legacy domain, including custom subdomains.
    if host == "memarketshop.ir" or host.endswith(".memarketshop.ir") or host == "mmkt.ir" or host.endswith(".mmkt.ir"):
        return ""

    is_memarket24 = host == "memarket24.ir" or host.endswith(".memarket24.ir")
    is_shortlink = host == "l.memarket.me"
    if not (is_memarket24 or is_shortlink):
        return ""

    # Current MeMarket short links encode the affiliate code in /lp/{id}/{code}.
    parts = [x for x in p.path.split("/") if x]
    if is_shortlink and len(parts) >= 3 and parts[-1].isdigit():
        parts[-1] = AFF
        return urlunsplit((p.scheme, p.netloc, "/" + "/".join(parts), p.query, p.fragment))

    # Replace an existing seller-code path segment such as /landing/foo/4116.
    if "landing" in [x.lower() for x in parts] and parts:
        if parts[-1].isdigit():
            parts[-1] = AFF
            return urlunsplit((p.scheme, p.netloc, "/" + "/".join(parts), p.query, p.fragment))
        return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/") + "/" + AFF, p.query, p.fragment))

    # Replace an existing ?s=code / &s=code, otherwise append it.
    query = parse_qsl(p.query, keep_blank_values=True)
    replaced = False
    new_query = []
    for k, v in query:
        if k.lower() == "s":
            new_query.append((k, AFF))
            replaced = True
        else:
            new_query.append((k, v))
    if not replaced:
        new_query.append(("s", AFF))

    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(new_query), p.fragment))


def extract_percent(text: str):
    nums = []
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:٪|%)", fa_to_en(text)):
        try:
            nums.append(float(m.group(1).replace(",", "")))
        except Exception:
            pass
    return max(nums) if nums else 0.0


MARKETER_ONLY_PATTERNS = [
    ("وبمستر/بازاریاب", r"وب\s*مستر|بازاریاب"),
    ("تارگت فروش همکاران", r"تارگت"),
    ("جذب یا ثبت‌نام همکار", r"جذب.{0,20}(?:همکار|بازاریاب)|ثبت\s*نام.{0,25}(?:همکاری|بازاریاب)"),
    ("پیام مخصوص همکاران", r"همکاران\s+(?:عزیز|محترم)|بات\s+همکار"),
    ("تبلیغ و جذب سفارش", r"تبلیغ\s+کن(?:ی)?\s+و\s+سفارش\s+بگیر|مخاطبات|مشتریهات"),
    ("دریافت محتوای تبلیغاتی", r"دریافت\s+کاور|کاور\s+تبلیغی|ویدئوی?\s+هر\s+محصول"),
    ("اطلاعیه پنل یا تسویه همکاران", r"پشتیبان\s+اختصاصی|شماره\s+شبای?\s+خود|تغییر\s+آدرس.{0,20}پنل"),
    ("پاداش وابسته به عملکرد فروش", r"(?:پاداش|جایزه).{0,50}(?:فروش|همکار|سفارش)|(?:فروش|همکار|سفارش).{0,50}(?:پاداش|جایزه)"),
    ("دعوت به کسب درآمد", r"اولین\s+درآمد|درآمد\s+آنلاین|کسب\s+درآمد"),
]


def marketing_only_reason(text: str) -> str:
    normalized = text.replace("ي", "ی").replace("ك", "ک")
    normalized = re.sub(r"[\u200c\u200d]", " ", normalized)
    for reason, pattern in MARKETER_ONLY_PATTERNS:
        if re.search(pattern, normalized, flags=re.I):
            return reason
    return ""


def score_post(post):
    text_value = post["text"]
    low = text_value.lower()
    percent = extract_percent(text_value)

    aff_links = []
    for u in post["links"]:
        x = affiliate_link(u)
        if x:
            aff_links.append(x)
    aff_links = list(dict.fromkeys(aff_links))

    # Do not send affiliate recruitment, commission, dashboard, or marketer-instruction
    # messages to the buyer-facing deal feed, even if they mention discounts or links.
    filtered_reason = marketing_only_reason(text_value)
    if filtered_reason:
        return {
            **post,
            "score": 0,
            "percent": percent,
            "reasons": [],
            "affiliate_links": aff_links,
            "qualifies": False,
            "filtered_reason": filtered_reason,
        }

    score = 0
    reasons = []

    if percent >= MIN_PERCENT:
        score += 4
        reasons.append(f"تخفیف {percent:.0f}%")
        if percent >= 50:
            score += 2
    elif any(k in low for k in ("تخفیف", "حراج", "آفر", "کاهش قیمت")):
        score += 2
        reasons.append("آفر/تخفیف")

    if any(k in low for k in ("فقط", "ویژه", "شگفت", "استثنایی", "پولساز")):
        score += 1

    if aff_links:
        score += 4

    # Qualification is now buyer-oriented: posts explicitly aimed at marketers
    # are removed before scoring, and a real offer/link is still required.
    deal_words = (
        "تخفیف", "حراج", "آفر", "کاهش قیمت", "قیمت ویژه",
        "کمپین", "فقط", "شگفت", "استثنایی"
    )
    # Require a shopper-directed CTA, not just discount/commission talk.
    qualifies = (
        score >= 7
        and bool(aff_links)
        and (percent >= MIN_PERCENT or any(k in low for k in deal_words))
        and any(k in low for k in deal_words)
        and has_buyer_cta(text_value)
    )

    return {
        **post,
        "score": score,
        "percent": percent,
        "reasons": reasons,
        "affiliate_links": aff_links,
        "qualifies": qualifies,
        "filtered_reason": "",
    }

def short_copy(post) -> str:
    lines = [x.strip() for x in post["text"].splitlines() if x.strip()]
    filtered = []
    for line in lines:
        normalized = line.replace("ي", "ی").replace("ك", "ک").lower()
        # Remove affiliate-specific code instructions and channel footers from customer copy.
        if re.search(
            r"به\s*جای\s*کد|جای\s*کد.{0,30}(?:خودتون|خودتان|همکاری)|"
            r"کد\s*همکاری\s*(?:خودتون|خودتان)|"
            r"لطفا.{0,30}(?:کد\s*4116|کد\s*همکاری)",
            normalized,
            re.I,
        ):
            continue
        if any(x in normalized for x in (
            "@memarket", "@shop_memarketbiz", "@memarket_content",
            "@memarketcobot", "@sup_memarket"
        )):
            continue
        filtered.append(line)
    return "\n".join(filtered)[:550].strip()


BUYER_CTA_PATTERNS = [
    r"برای\s+(?:دیدن|مشاهده|خرید)\s+(?:محصولات?|این|همین|محصولات?\s+تخفیفی)?",
    r"برای\s+خرید\s+بزن",
    r"بزن\s+رو\s+لینک",
    r"همین\s+(?:الان|حالا)\s+(?:ببین|خرید|سفارش|مشاهده)",
    r"(?:همین\s+الان\s+)?خرید\s+کن(?:ید)?",
    r"مشاهده\s+(?:محصول|محصولات|قیمت)",
    r"لینک\s+خرید",
    r"سفارش\s+(?:بده|بدید|ثبت\s+کن)",
    r"این\s+(?:تخفیف|محصول)\s+(?:مال\s+تو|رو\s+از\s+دست\s+نده)",
]


def has_buyer_cta(text_value: str) -> bool:
    normalized = text_value.replace("ي", "ی").replace("ك", "ک")
    normalized = re.sub(r"[\u200c\u200d]", " ", normalized)
    return any(re.search(pattern, normalized, re.I) for pattern in BUYER_CTA_PATTERNS)


def post_is_recent(post: dict, now: float) -> bool:
    published_ts = post.get("published_ts")
    if not isinstance(published_ts, (int, float)):
        return False
    age_hours = (now - float(published_ts)) / 3600
    return -0.25 <= age_hours <= MAX_POST_AGE_HOURS



def fetch_page(url: str, timeout: int = 25):
    """Fetch a public product/landing page and retain redirect/HTTP metadata."""
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        body = r.read(3_000_001)
        if len(body) > 3_000_000:
            raise RuntimeError("page too large")
        return r.status, r.geturl(), r.headers.get("Content-Type", ""), body.decode("utf-8", "ignore")


def _meta_values(page: str):
    values = {}
    for tag in re.findall(r"(?is)<meta\b[^>]*>", page):
        attrs = {}
        for m in re.finditer(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag):
            attrs[m.group(1).lower()] = next((g for g in m.groups()[1:] if g is not None), "")
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key and attrs.get("content"):
            values[key] = html.unescape(attrs["content"])
    return values


def _stock_signals(page: str):
    """Return IN_STOCK, OUT_OF_STOCK, or UNKNOWN; fail closed on ambiguity."""
    structured_statuses = []
    for chunk in re.findall(
        r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page,
    ):
        try:
            obj = json.loads(html.unescape(chunk))
        except Exception:
            continue

        def walk(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if str(k).lower() == "availability":
                        structured_statuses.append(str(v).lower())
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
        walk(obj)

    joined_status = " ".join(structured_statuses)
    if any(x in joined_status for x in ("outofstock", "soldout", "discontinued", "preorder")):
        return "OUT_OF_STOCK"
    if any(x in joined_status for x in ("instock", "limitedavailability", "onlineonly")):
        return "IN_STOCK"

    visible_html = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", page)
    visible = clean_text(visible_html).lower()
    visible = visible.replace("ي", "ی").replace("ك", "ک")
    negative = (
        r"ناموجود",
        r"اتمام\s*موجودی",
        r"موجودی\s+(?:ندارد|تمام\s*شده|به\s*پایان\s*رسیده)",
        r"در\s*حال\s*حاضر.{0,30}(?:موجود\s*نیست|قابل\s*سفارش\s*نیست)",
        r"قابل\s*سفارش\s*نیست",
        r"موقتا.{0,20}ناموجود",
        r"out\s*of\s*stock",
        r"sold\s*out",
    )
    if any(re.search(p, visible, re.I) for p in negative):
        return "OUT_OF_STOCK"

    positive = (
        r"موجود\s*در\s*انبار",
        r"در\s*انبار\s*موجود\s*است",
        r"\bin\s*stock\b",
    )
    if any(re.search(p, visible, re.I) for p in positive):
        return "IN_STOCK"

    visible_source_lower = html.unescape(visible_html).lower()
    if re.search(r'"(?:isAvailable|available)"\s*:\s*true', visible_source_lower):
        return "IN_STOCK"
    if re.search(r'"(?:isAvailable|available)"\s*:\s*false', visible_source_lower):
        return "OUT_OF_STOCK"
    if re.search(r'"(?:stockQuantity|quantity|inventory)"\s*:\s*0(?:\D|$)', visible_source_lower):
        return "OUT_OF_STOCK"
    return "UNKNOWN"


def _product_urls_in_page(page: str, base_url: str):
    urls = []
    for raw in re.findall(r'(?is)<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', page):
        u = urljoin(base_url, html.unescape(raw))
        try:
            p = urlsplit(u)
        except Exception:
            continue
        host = (p.hostname or "").lower()
        if (host == "memarket24.ir" or host.endswith(".memarket24.ir")) and re.search(r"/product/\d+", p.path, re.I):
            normalized = affiliate_link(u)
            urls.append(normalized or u)
    return list(dict.fromkeys(urls))


def _product_image_and_title(page: str, base_url: str):
    meta = _meta_values(page)
    image = meta.get("og:image") or meta.get("twitter:image") or meta.get("twitter:image:src") or ""
    title = meta.get("og:title") or meta.get("twitter:title") or meta.get("title") or ""

    if not title:
        hm = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", page)
        if hm:
            title = clean_text(hm.group(1))[:140]

    image_candidates = [image]
    for tag in re.findall(r"(?is)<img\b[^>]*>", page):
        attrs = {}
        for m in re.finditer(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag):
            attrs[m.group(1).lower()] = next((g for g in m.groups()[1:] if g is not None), "")
        candidate = attrs.get("data-zoom-image") or attrs.get("data-src") or attrs.get("src") or ""
        hint = (candidate + " " + attrs.get("alt", "") + " " + attrs.get("class", "")).lower()
        if candidate and not any(x in hint for x in ("logo", "avatar", "icon", "placeholder", "payment", "banner-logo")):
            image_candidates.append(candidate)

    for candidate in image_candidates:
        if not candidate:
            continue
        candidate = urljoin(base_url, html.unescape(candidate))
        if candidate.startswith(("https://", "http://")):
            return candidate, html.unescape(title).strip()[:140]
    return "", html.unescape(title).strip()[:140]


def verify_offer_stock(post: dict):
    """Resolve a deal to a public product page; only return sendable if stock is explicit."""
    product_urls = []
    for raw in post.get("links", []):
        try:
            p = urlsplit(raw)
        except Exception:
            continue
        host = (p.hostname or "").lower()
        if (host == "memarket24.ir" or host.endswith(".memarket24.ir")) and re.search(r"/product/\d+", p.path, re.I):
            product_urls.append(affiliate_link(raw) or raw)

    if not product_urls:
        for landing in post.get("affiliate_links", [])[:2]:
            try:
                _, final_url, _, landing_html = fetch_page(landing)
                if re.search(r"/product/\d+", urlsplit(final_url).path, re.I):
                    product_urls.append(affiliate_link(final_url) or final_url)
                product_urls.extend(_product_urls_in_page(landing_html, final_url))
            except Exception as exc:
                print(f"LANDING_CHECK_FAILED url={landing.split('?')[0]} error={type(exc).__name__}")

    product_urls = list(dict.fromkeys(product_urls))[:5]
    if not product_urls:
        return {"ok": False, "status": "UNKNOWN", "reason": "no concrete product page found"}

    saw_out = False
    saw_unknown = False
    last_reason = "no product with a verifiable in-stock signal"
    last_image = ""
    last_title = ""

    for product_url in product_urls:
        try:
            status_code, final_url, _, page = fetch_page(product_url)
        except HTTPError as exc:
            if exc.code in (404, 410):
                saw_out = True
                last_reason = f"product page unavailable: HTTP_{exc.code}"
                print(f"PRODUCT_STATUS url={product_url.split('?')[0]} result=HTTP_{exc.code}")
            else:
                saw_unknown = True
                last_reason = f"stock status unavailable: HTTP_{exc.code}"
                print(f"PRODUCT_STATUS url={product_url.split('?')[0]} result=UNKNOWN_HTTP_{exc.code}")
            continue
        except Exception as exc:
            saw_unknown = True
            last_reason = f"product page check failed: {type(exc).__name__}"
            print(f"PRODUCT_CHECK_FAILED url={product_url.split('?')[0]} error={type(exc).__name__}")
            continue

        if status_code == 404 or status_code == 410:
            saw_out = True
            last_reason = f"product page unavailable: HTTP_{status_code}"
            print(f"PRODUCT_STATUS url={final_url.split('?')[0]} result=HTTP_{status_code}")
            continue
        if status_code < 200 or status_code >= 300:
            saw_unknown = True
            last_reason = f"stock status unavailable: HTTP_{status_code}"
            print(f"PRODUCT_STATUS url={final_url.split('?')[0]} result=UNKNOWN_HTTP_{status_code}")
            continue

        product_image, title = _product_image_and_title(page, final_url)
        if product_image:
            last_image = product_image
        if title:
            last_title = title

        stock = _stock_signals(page)
        if stock == "OUT_OF_STOCK":
            saw_out = True
            last_reason = "explicit out-of-stock signal on product page"
            print(f"PRODUCT_STATUS url={final_url.split('?')[0]} result=OUT_OF_STOCK")
            continue
        if stock != "IN_STOCK":
            saw_unknown = True
            last_reason = "page does not expose an explicit in-stock signal"
            print(f"PRODUCT_STATUS url={final_url.split('?')[0]} result=UNKNOWN")
            continue

        buyer_link = affiliate_link(final_url) or affiliate_link(product_url) or product_url
        return {
            "ok": True,
            "status": "IN_STOCK",
            "product_url": buyer_link,
            "product_image": product_image or post.get("image", ""),
            "product_title": title,
            "reason": "explicit in-stock signal",
        }

    final_status = "OUT_OF_STOCK" if saw_out and not saw_unknown else "UNKNOWN"
    return {
        "ok": False,
        "status": final_status,
        "reason": last_reason,
        "product_image": last_image or post.get("image", ""),
        "product_title": last_title,
    }


def upload_telegram_photo(image_url: str, caption: str):
    """Download the picture on the runner and upload bytes; Telegram URL-fetch often fails."""
    image_req = Request(
        image_url,
        headers={
            "User-Agent": "Mozilla/5.0 MeMarketDealRadar/2.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    with urlopen(image_req, timeout=30) as r:
        mime = (r.headers.get("Content-Type") or "image/jpeg").split(";", 1)[0].strip().lower()
        data = r.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise RuntimeError("image larger than Telegram photo limit")
    if not mime.startswith("image/") or not data:
        raise RuntimeError(f"image URL did not return image bytes (content-type={mime})")

    boundary = "----MeMarketRadar" + uuid.uuid4().hex
    fields = {"chat_id": CHAT, "caption": caption, "parse_mode": "HTML"}
    chunks = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    ext = mimetypes.guess_extension(mime) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(f'Content-Disposition: form-data; name="photo"; filename="memarket-product{ext}"\r\n'.encode())
    chunks.append(f"Content-Type: {mime}\r\n\r\n".encode())
    chunks.append(data)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    request = Request(
        f"https://api.telegram.org/bot{BOT}/sendPhoto",
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "MeMarketDealRadar/2.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Telegram sendPhoto upload HTTP {exc.code}: {detail[:700]}") from exc


def telegram_request(method: str, data: dict):
    url = f"https://api.telegram.org/bot{BOT}/{method}"
    body = urlencode(data).encode()
    req = Request(
        url,
        data=body,
        headers={"User-Agent": "MeMarketDealRadar/2.0", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Telegram {method} HTTP {exc.code}: {detail[:700]}") from exc


def send_telegram(post):
    body = html.escape(short_copy(post)[:430])
    link = post.get("product_url") or post["affiliate_links"][0]
    source = html.escape(post["url"], quote=True)
    product_title = html.escape((post.get("product_title") or "").strip())

    parts = ["🔥 <b>آفر داغ می‌مارکت</b>"]
    if product_title:
        parts += ["", f"🛍️ <b>{product_title}</b>"]
    parts += ["", body]
    if post["reasons"]:
        parts += ["", "📌 " + " • ".join(html.escape(x) for x in post["reasons"])]
    parts += [
        "",
        f'🛒 <a href="{html.escape(link, quote=True)}">مشاهده / خرید با لینک همکاری</a>',
        f'🔗 <a href="{source}">منبع اصلی</a>',
    ]
    message = "\n".join(parts)

    photo_candidates = list(dict.fromkeys([
        post.get("product_image") or "",
        post.get("image") or "",
    ]))
    for photo in photo_candidates:
        if not photo:
            continue
        host = (urlsplit(photo).hostname or "").lower()
        if (
            host == "mmkt.ir" or host.endswith(".mmkt.ir")
            or host == "memarketshop.ir" or host.endswith(".memarketshop.ir")
        ):
            print("photo_source_skipped_retired_host=" + host, file=sys.stderr)
            continue
        try:
            result = upload_telegram_photo(photo, message)
            if isinstance(result, dict) and result.get("ok") is False:
                raise RuntimeError("Telegram returned ok=false for sendPhoto")
            return result
        except Exception as exc:
            host = urlsplit(photo).hostname or "unknown-host"
            print(
                f"photo_upload_failed host={host} error={type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    # If neither image source can be uploaded, preserve a clickable preview but never fake success.
    return telegram_request(
        "sendMessage",
        {"chat_id": CHAT, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "false"},
    )


def load_state():
    if not STATE.exists():
        return {"seen": [], "alerts": {}}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("seen", [])
            data.setdefault("alerts", {})
            return data
    except Exception:
        pass
    return {"seen": [], "alerts": {}}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def commit_state():
    if not STATE_COMMIT or DRY_RUN:
        return

    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", str(STATE)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not changed:
        return

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", str(STATE)], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", "chore: update MeMarket radar state [skip ci]"], check=True)
    subprocess.run(["git", "push"], check=True)


def main():
    state = load_state()
    state.setdefault("pending_stock", {})
    if not isinstance(state["pending_stock"], dict):
        state["pending_stock"] = {}

    page = fetch(CHANNEL_URL)
    posts = extract_posts(page)
    if not posts:
        raise SystemExit("No Telegram channel posts parsed.")

    now = time.time()
    print(f"channel={CHANNEL} posts={len(posts)}")
    print("stock_verification=fail_closed_explicit_signal_required")

    seen = set(str(x) for x in state.get("seen", []))
    pending = state["pending_stock"]
    current_ids = {str(p["id"]) for p in posts}

    for pid in list(pending):
        entry = pending.get(pid, {})
        first_seen = float(entry.get("first_seen", now))
        if pid not in current_ids or now - first_seen > MAX_POST_AGE_HOURS * 3600:
            pending.pop(pid, None)

    eligible_posts = []
    for p in posts:
        pid = str(p["id"])
        if not post_is_recent(p, now):
            if pid not in seen:
                print(f"SKIP_STALE_OR_UNDATED id={pid}")
            pending.pop(pid, None)
            continue

        if pid in pending:
            last_checked = float(pending[pid].get("last_checked", 0))
            if now - last_checked >= PENDING_RETRY_HOURS * 3600:
                eligible_posts.append(p)
        elif pid not in seen:
            eligible_posts.append(p)

    print(f"new_or_due_posts={len(eligible_posts)} pending_stock={len(pending)}")

    scored_posts = [score_post(p) for p in eligible_posts]
    for p in scored_posts:
        if p.get("filtered_reason"):
            print(f"FILTERED_MARKETER_POST id={p['id']} reason={p['filtered_reason']}")
        elif not has_buyer_cta(p["text"]):
            print(f"FILTERED_NO_BUYER_CTA id={p['id']}")

    candidates = [p for p in scored_posts if p["qualifies"]]
    candidates.sort(key=lambda p: (p["score"], p["percent"]), reverse=True)

    for p in candidates[:10]:
        age = (now - float(p["published_ts"])) / 3600
        print(
            f"CANDIDATE id={p['id']} age_hours={age:.1f} score={p['score']} "
            f"percent={p['percent']:.0f} links={len(p['affiliate_links'])} "
            f"reasons={' | '.join(p['reasons'])} text={short_copy(p)[:350]!r}"
        )

    if not BOOTSTRAP_SILENT or seen:
        sent = 0
        for p in candidates:
            if sent >= MAX_ALERTS:
                break

            pid = str(p["id"])
            old = state["alerts"].get(pid, {})
            last_alert = float(old.get("ts", 0))
            if now - last_alert < COOLDOWN:
                pending.pop(pid, None)
                continue

            product_check = verify_offer_stock(p)
            if not product_check.get("ok"):
                print(
                    f"SKIP_STOCK id={pid} status={product_check['status']} "
                    f"reason={product_check['reason']}"
                )
                pending[pid] = {
                    "first_seen": float(pending.get(pid, {}).get("first_seen", now)),
                    "last_checked": now,
                    "last_status": product_check["status"],
                    "last_reason": product_check["reason"],
                }
                continue

            p.update(product_check)
            if not p.get("product_image"):
                print(f"SKIP_NO_IMAGE id={pid}; will retry while offer is fresh")
                pending[pid] = {
                    "first_seen": float(pending.get(pid, {}).get("first_seen", now)),
                    "last_checked": now,
                    "last_status": "IN_STOCK_NO_IMAGE",
                    "last_reason": "no usable product/offer image",
                }
                continue

            if DRY_RUN:
                print(
                    f"DRY_RUN would_send id={pid} stock={p['status']} "
                    f"product={p.get('product_title', '')!r} image=yes"
                )
            else:
                result = send_telegram(p)
                if isinstance(result, dict) and result.get("ok") is False:
                    raise RuntimeError("Telegram returned ok=false for an alert")
                print(
                    f"SENT id={pid} stock={p['status']} "
                    f"product={p.get('product_title', '')!r} image=yes"
                )

            state["alerts"][pid] = {"ts": now, "score": p["score"]}
            pending.pop(pid, None)
            sent += 1

        print(f"alerts_sent={sent}")
    else:
        print("bootstrap=quiet")

    state["seen"] = list(dict.fromkeys([*state.get("seen", []), *[str(p["id"]) for p in posts]]))[-MAX_SEEN:]
    save_state(state)
    commit_state()


if __name__ == "__main__":
    main()
