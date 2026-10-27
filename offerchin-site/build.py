#!/usr/bin/env python3
"""Build a static, SEO-friendly OfferChin catalog from the existing radar state."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "dist"
BUFFER = timedelta(minutes=10)
SITE_URL = "https://offerchin-storefront.pages.dev"
CHANNEL_TELEGRAM = "https://t.me/OfferChin"
CHANNEL_BALE = "https://ble.ir/OfferChin"


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required data source missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def script_json(value) -> str:
    # Prevent titles or URLs from terminating a script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def money(value) -> int:
    try:
        return max(0, int(round(float(value))))
    except (ValueError, TypeError, OverflowError):
        return 0


def safe_https(value: str) -> bool:
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and bool(parsed.hostname)
    except ValueError:
        return False


def valid_product_id(value: object) -> bool:
    """Accept retailer-neutral IDs without allowing path traversal or HTML delimiters."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,99}", str(value or "")))


def retailer_info(product_id: str, product_url: str, merchant: object = "") -> tuple[str, str]:
    """Resolve a user-facing retailer label from the validated product source."""
    try:
        host = (urlparse(str(product_url or "").strip()).hostname or "").casefold()
    except ValueError:
        host = ""
    identifier = str(product_id or "").casefold()
    if identifier.startswith("snp-") or host == "snappshop.ir" or host.endswith(".snappshop.ir"):
        return "snappshop", "اسنپ‌شاپ"
    if identifier.startswith("dkp-") or host == "digikala.com" or host.endswith(".digikala.com"):
        return "digikala", "دیجی‌کالا"
    label = re.sub(r"\s+", " ", str(merchant or "").strip())[:80]
    return "other", label or "فروشگاه"


def build_products(candidates: dict, state: dict, now: datetime) -> list[dict]:
    """Build a safe retailer-neutral feed only from live-eligible published offers."""
    published = state.get("published", {})
    result = []
    seen = set()

    for source in candidates.get("products", []):
        if not isinstance(source, dict):
            continue
        product_id = str(source.get("product_id") or "").strip()
        if not valid_product_id(product_id) or product_id in seen:
            continue
        record = published.get(product_id)
        if not isinstance(record, dict):
            continue

        # Mirror only offers successfully delivered to at least one public channel.
        delivery = record.get("delivery_status") or {}
        if not any(status == "sent" for status in delivery.values()):
            continue
        if record.get("expiry_status") != "tracked":
            continue
        if source.get("qualifies_as_deal") is not True or source.get("availability") != "in_stock":
            continue

        current_price = money(source.get("current_price"))
        original_price = money(source.get("original_price"))
        if current_price <= 0 or original_price <= current_price:
            continue

        calculated_discount = round(100 * (original_price - current_price) / original_price)
        supplied_discount = money(source.get("discount_percent"))
        # Avoid advertising a feed discount that materially conflicts with the prices.
        if not 1 <= calculated_discount <= 100:
            continue
        if supplied_discount > 0 and abs(supplied_discount - calculated_discount) > 5:
            continue
        discount_percent = calculated_discount
        savings = original_price - current_price

        affiliate_url = str(source.get("affiliate_url") or "")
        product_url = str(source.get("product_url") or "")
        image_url = str(source.get("image_url") or "")
        if not safe_https(affiliate_url) or not safe_https(product_url) or not safe_https(image_url):
            continue
        try:
            product_path = urlparse(product_url).path.casefold()
        except ValueError:
            continue
        if product_id.casefold() not in product_path:
            continue

        retailer_key, retailer_name = retailer_info(product_id, product_url, source.get("merchant"))
        category = re.sub(r"\s+", " ", str(source.get("category") or "سایر").strip())[:100] or "سایر"

        feed_deadline = parse_date(source.get("deal_expires_at"))
        post_deadline = parse_date(record.get("expires_at"))
        # Never guess missing deadlines; when sources disagree, use the earlier one.
        if not feed_deadline or not post_deadline:
            continue
        deadline = min(feed_deadline, post_deadline)
        active_until = deadline - BUFFER
        if active_until <= now:
            continue

        title = str(source.get("title") or record.get("title") or "").strip()
        if len(title) < 5:
            continue

        product = {
            "product_id": product_id,
            "title": title,
            "retailer_key": retailer_key,
            "retailer_name": retailer_name,
            "category": category,
            "current_price": current_price,
            "original_price": original_price,
            "discount_percent": discount_percent,
            "savings_toman": savings,
            "image_url": image_url,
            "affiliate_url": affiliate_url,
            "product_url": product_url,
            "deal_expires_at": iso(deadline),
            "active_until": iso(active_until),
            "availability": "in_stock",
            "promo_score": float(source.get("promo_score") or 0),
            "demand_score": float(source.get("demand_score") or 0),
            "click_count_30d": money(source.get("click_count_30d")),
            "review_count": money(source.get("review_count")),
            "rating": source.get("rating"),
            "published_at": datetime.fromtimestamp(float(record.get("ts") or 0), timezone.utc).isoformat()
            if record.get("ts") else "",
        }
        result.append(product)
        seen.add(product_id)

    # Demand/popularity leads; deal appeal is a secondary signal.
    result.sort(
        key=lambda p: (p["demand_score"], p["click_count_30d"], p["promo_score"], p["review_count"]),
        reverse=True,
    )
    return result


def card_html(p: dict) -> str:
    pid, title = esc(p["product_id"]), esc(p["title"])
    retailer_key = esc(p.get("retailer_key") or "other")
    retailer_name = esc(p.get("retailer_name") or "فروشگاه")
    category = esc(p.get("category") or "سایر")
    return f"""
    <article class="deal-card" data-product-id="{pid}" data-category="{category}" data-retailer="{retailer_key}" data-active-until="{esc(p['active_until'])}">
      <a class="product-media" href="/products/{pid}/" aria-label="جزئیات {title}">
        <img src="{esc(p['image_url'])}" alt="{title}" loading="lazy" decoding="async"
             onerror="this.style.display='none';this.parentElement.classList.add('image-missing')">
        <span class="discount-badge">{money(p['discount_percent'])}٪ تخفیف</span>
      </a>
      <div class="product-body">
        <div class="product-meta"><span class="retailer-tag">{retailer_name}</span><span class="category-tag">{category}</span></div>
        <h3 class="product-title"><a href="/products/{pid}/">{title}</a></h3>
        <div class="price-block">
          <div class="price-now">{money(p['current_price']):,} <span class="currency">تومان</span></div>
          <div class="price-old">قیمت قبلی: <s>{money(p['original_price']):,} تومان</s></div>
          <div class="saving">اختلاف با قیمت قبلی {money(p['savings_toman']):,} تومان</div>
        </div>
        <div class="deadline"><span aria-hidden="true">◷</span><span>مهلت امن خرید: <strong data-countdown="{esc(p['active_until'])}">در حال محاسبه…</strong></span></div>
        <div class="card-actions">
          <a class="buy-link" href="{esc(p['affiliate_url'])}" target="_blank" rel="sponsored nofollow noopener noreferrer">مشاهده و خرید در {retailer_name} ↗</a>
          <button class="share-link" type="button" data-share-product="{pid}" aria-label="اشتراک‌گذاری {title}">اشتراک‌گذاری</button>
          <a class="details-link" href="/products/{pid}/">جزئیات</a>
        </div>
      </div>
    </article>"""


def shared_head(title: str, description: str, canonical: str, image: str = "") -> str:
    og_image = f'<meta property="og:image" content="{esc(image)}">' if image else ""
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#102a43">
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{esc(canonical)}">
<link rel="stylesheet" href="/assets/site.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='10' fill='%23b8f34a'/%3E%3Ctext x='20' y='28' font-size='25' text-anchor='middle' font-family='sans-serif' fill='%23102a43'%3Eآ%3C/text%3E%3C/svg%3E">
<title>{esc(title)}</title>
<meta property="og:locale" content="fa_IR">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
{og_image}
<script defer src="/assets/site.js"></script>
</head>"""


def site_header() -> str:
    return f"""<header class="site-header"><div class="container header-inner">
<a class="brand" href="/" aria-label="آفِرچین، صفحه اصلی"><span class="brand-mark">آ</span><span>آفِرچین</span></a>
<nav class="nav" aria-label="ناوبری اصلی"><a href="/#offers">پیشنهادها</a><a class="nav-about" href="/#about">روش کار</a><a href="{CHANNEL_TELEGRAM}" target="_blank" rel="noopener noreferrer">تلگرام ↗</a><a href="{CHANNEL_BALE}" target="_blank" rel="noopener noreferrer">بله ↗</a></nav>
</div></header>"""


def site_footer() -> str:
    return f"""<footer class="site-footer"><div class="container footer-inner">
<p>آفِرچین، شکارچی تخفیف‌های ناب دیجی‌کالا. قیمت و موجودی ممکن است تغییر کند؛ پیش از خرید، اطلاعات نهایی را در صفحه دیجی‌کالا بررسی کنید. برخی پیوندهای خرید ممکن است شامل همکاری در فروش باشند.</p>
<div class="footer-links"><a href="{CHANNEL_TELEGRAM}" target="_blank" rel="noopener noreferrer">کانال تلگرام</a><a href="{CHANNEL_BALE}" target="_blank" rel="noopener noreferrer">کانال بله</a></div>
</div></footer>"""


def build_index(products: list[dict]) -> str:
    title = "آفِرچین | پیشنهادهای معتبر دیجی‌کالا"
    description = "پیشنهادهای تخفیفی آفِرچین با لینک خرید، قیمت و مهلت معتبر. پیشنهادهای منقضی‌شده به‌طور خودکار از فهرست حذف می‌شوند."
    cards = "".join(card_html(p) for p in products)
    if not cards:
        cards = '<div class="empty-state"><strong>فعلاً پیشنهاد فعالی نداریم</strong>پیشنهادهای واجد شرایط به‌صورت خودکار در همین صفحه ظاهر می‌شوند.</div>'
    itemlist = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": title,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": f"{SITE_URL}/products/{p['product_id']}/", "name": p["title"]}
            for i, p in enumerate(products)
        ],
    }
    return f"""{shared_head(title, description, SITE_URL + "/")}
<body>
{site_header()}
<section class="hero"><div class="container hero-grid">
<div><p class="eyebrow">● پیشنهادهایی با مهلت معتبر</p><h1>خرید هوشمندانه‌تر،<br>با تخفیف‌های قابل بررسی</h1>
<p>پیشنهادهای دیجی‌کالا که از فیلترهای قیمت، موجودی، لینک خرید و مهلت معتبر آفِرچین عبور کرده‌اند.</p>
<p class="hero-note">برای جلوگیری از معرفی دیرهنگام، پیشنهادها ۱۰ دقیقه پیش از مهلت ثبت‌شده از فهرست کنار می‌روند.</p></div>
<div class="hero-stat"><div><div class="stat-number" id="offerCount">{len(products)}</div><div class="stat-label">پیشنهاد قابل خرید</div></div><div aria-hidden="true" style="font-size:2.4rem">↘</div></div>
</div></section>
<main class="container catalog" id="offers">
<div class="section-head"><div><h2>پیشنهادهای فعال</h2><p>فقط محصولاتی که قبلاً در یکی از کانال‌های آفِرچین منتشر شده‌اند.</p></div></div>
<div class="toolbar">
<label class="search-wrap"><span class="search-icon" aria-hidden="true">⌕</span><input id="offerSearch" class="search-input" type="search" autocomplete="off" placeholder="جست‌وجوی نام محصول…" aria-label="جست‌وجوی نام محصول"></label>
<label><span style="position:absolute;clip:rect(0,0,0,0)">مرتب‌سازی</span><select id="offerSort" class="sort-select" aria-label="مرتب‌سازی پیشنهادها"><option value="score">بهترین پیشنهادها</option><option value="discount">بیشترین تخفیف</option><option value="saving">بیشترین صرفه‌جویی</option></select></label>
</div>
<p class="status-line" id="feedStatus" aria-live="polite">در حال آماده‌سازی فهرست…</p>
<div class="grid" id="offerGrid">{cards}</div>
<section class="policy" id="about"><h2>پیشنهادها چطور انتخاب می‌شوند؟</h2>
<p>محصول باید قبلاً در یکی از کانال‌های آفِرچین منتشر شده باشد و همچنان موجودی، لینک خرید و مهلت پایان قابل‌اعتماد داشته باشد. در صورت رسیدن به مهلت امن یا تأیید نامعتبر بودن پیشنهاد، محصول از فهرست حذف یا خرید آن غیرفعال می‌شود.</p>
<p>ممکن است دیجی‌کالا قیمت یا موجودی را پیش از موعد تغییر دهد؛ صفحه فروشنده مرجع نهایی معامله است.</p></section>
</main>
{site_footer()}
<script type="application/ld+json">{script_json(itemlist)}</script>
<script type="application/json" id="initialProducts">{script_json(products)}</script>
</body></html>"""


def build_detail(p: dict) -> str:
    title = p["title"]
    canonical = f"{SITE_URL}/products/{p['product_id']}/"
    description = f"{title} با {money(p['discount_percent'])} درصد تخفیف. قیمت فعلی ثبت‌شده {money(p['current_price']):,} تومان؛ مهلت نمایش پیشنهاد به‌صورت خودکار کنترل می‌شود."
    product_schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": [p["image_url"]],
        "description": description,
        "url": canonical,
        "sku": p["product_id"],
    }
    return f"""{shared_head(title + " | آفِرچین", description, canonical, image=p['image_url'])}
<body data-product-id="{esc(p['product_id'])}">
{site_header()}
<main class="container detail-wrap">
<p class="breadcrumb"><a href="/">آفِرچین</a> ← <a href="/#offers">پیشنهادهای فعال</a> ← جزئیات محصول</p>
<div class="expired-notice" id="expiredNotice" hidden><h2>این پیشنهاد دیگر فعال نیست</h2><p>برای جلوگیری از خرید با تخفیف منقضی، لینک خرید این صفحه غیرفعال شده است.</p><a href="/#offers">دیدن پیشنهادهای فعال ←</a></div>
<section class="detail-card" id="detailContent">
<div class="detail-image"><img id="detailImage" src="{esc(p['image_url'])}" alt="{esc(title)}" decoding="async" onerror="this.style.display='none'"></div>
<div><p class="eyebrow" style="color:#5e7c20">پیشنهاد بررسی‌شده آفِرچین</p><span class="discount-badge" id="detailDiscount">{money(p['discount_percent'])}٪ تخفیف</span>
<h1 class="detail-title" id="detailTitle">{esc(title)}</h1>
<div class="detail-price"><div class="price-now" id="detailCurrentPrice">{money(p['current_price']):,} تومان</div><div class="price-old">قیمت قبلی: <s id="detailOldPrice">{money(p['original_price']):,} تومان</s></div></div>
<p class="detail-savings" id="detailSaving">صرفه‌جویی {money(p['savings_toman']):,} تومان</p>
<p class="deadline">فرصت امن خرید: <strong data-countdown="{esc(p['active_until'])}" id="detailCountdown">در حال محاسبه…</strong></p>
<a class="buy-link detail-buy" id="detailBuy" href="{esc(p['affiliate_url'])}" target="_blank" rel="sponsored nofollow noopener noreferrer">مشاهده و خرید در دیجی‌کالا ↗</a>
<p class="notice">قیمت و موجودی در دیجی‌کالا ممکن است تغییر کند. پیش از نهایی‌کردن خرید، قیمت و شرایط فعلی را در صفحه فروشنده بررسی کنید.</p></div>
</section>
</main>
{site_footer()}
<script type="application/ld+json">{script_json(product_schema)}</script>
<script type="application/json" id="initialProducts">{script_json([p])}</script>
</body></html>"""


def main() -> None:
    now = datetime.now(timezone.utc)
    candidates = read_json(ROOT / "affilio_radar" / "candidates.json")
    state = read_json(ROOT / "affilio_radar" / "state.json")
    products = build_products(candidates, state, now)

    if OUT.exists():
        import shutil
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    (OUT / "products").mkdir(parents=True)
    for asset in ("site.css", "site.js"):
        (OUT / "assets" / asset).write_text((HERE / "assets" / asset).read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "index.html").write_text(build_index(products), encoding="utf-8")
    (OUT / "products.json").write_text(
        json.dumps({"built_at": iso(now), "generated_at": candidates.get("generated_at", ""), "products": products}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for product in products:
        folder = OUT / "products" / product["product_id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(build_detail(product), encoding="utf-8")

    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    urlset = ET.Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for url in [SITE_URL + "/"] + [f"{SITE_URL}/products/{p['product_id']}/" for p in products]:
        node = ET.SubElement(urlset, "url")
        ET.SubElement(node, "loc").text = url
        ET.SubElement(node, "lastmod").text = iso(now)[:10]
    ET.ElementTree(urlset).write(OUT / "sitemap.xml", encoding="utf-8", xml_declaration=True)

    print(f"Built {len(products)} active, published, deadline-verified products at {OUT}")
    print(f"Candidate snapshot: {candidates.get('generated_at', 'unknown')}")


if __name__ == "__main__":
    main()
