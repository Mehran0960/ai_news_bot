#!/usr/bin/env python3
"""Temporary diagnostics: validate recency extraction, buyer CTA filters, stock signals."""
from datetime import datetime, timezone
import time
import memarket_deal_radar as radar


def base_post(text, links=None, age_hours=1):
    now = time.time()
    return {
        "id": "test",
        "key": "memarket/test",
        "url": "https://t.me/memarket/test",
        "text": text,
        "links": links or ["https://l.memarket.me/lp/614/4116"],
        "image": "https://cdn.example.test/photo.jpg",
        "published_ts": now - age_hours * 3600,
    }


def check(label, condition):
    print(f"UNIT_TEST {label}={'PASS' if condition else 'FAIL'}")
    if not condition:
        raise AssertionError(label)


def main():
    now = time.time()
    sample_page = radar.fetch(radar.CHANNEL_URL)
    posts = radar.extract_posts(sample_page)
    dated = [p for p in posts if p.get("published_ts") is not None]
    recent = [p for p in posts if radar.post_is_recent(p, now)]
    print(f"LIVE_FEED posts={len(posts)} dated={len(dated)} recent_72h={len(recent)}")
    for p in posts[-8:]:
        ts = p.get("published_ts")
        age = round((now - ts) / 3600, 1) if ts else "UNKNOWN"
        checked = radar.score_post(p)
        print(
            f"LIVE_POST id={p['id']} age_hours={age} score={checked['score']} "
            f"qualified={checked['qualifies']} buyer_cta={radar.has_buyer_cta(p['text'])} "
            f"marketer_reason={checked.get('filtered_reason') or '-'} "
            f"images={1 if p.get('image') else 0} aff_links={len(checked['affiliate_links'])}"
        )

    shop_html = radar.fetch("https://t.me/s/shop_memarketbiz")
    shop_posts = radar.extract_posts(shop_html)
    shop_dated = [p for p in shop_posts if p.get("published_ts") is not None]
    shop_recent = [p for p in shop_posts if radar.post_is_recent(p, now)]
    print(
        f"SHOP_FEED posts={len(shop_posts)} dated={len(shop_dated)} "
        f"recent_72h={len(shop_recent)}"
    )
    for p in shop_posts[-12:]:
        ts = p.get("published_ts")
        age = round((now - ts) / 3600, 1) if ts else "UNKNOWN"
        links = []
        for raw in p["links"]:
            try:
                host = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(raw).hostname or ""
                if host.endswith("memarket24.ir") or host == "l.memarket.me":
                    links.append(host)
            except Exception:
                pass
        print(
            f"SHOP_POST id={p['id']} age_hours={age} text={p['text'][:160]!r} "
            f"links={len(links)} image={'yes' if p.get('image') else 'no'} "
            f"codes={','.join(__import__('re').findall(r'\\b[a-z]{1,3}-[a-z0-9]{3,}\\b', p['text'], __import__('re').I)[:3])}"
        )

    print("STOREFRONT_SCAN_BEGIN")
    for url in (
        "https://memarket24.ir/",
        "https://memarket24.ir/shop",
        "https://aff.memarket24.ir/login",
    ):
        try:
            status_code, final_url, content_type, html_page = radar.fetch_page(url)
            meta = radar._meta_values(html_page)
            product_urls = radar._product_urls_in_page(html_page, final_url)
            internal = []
            for raw in __import__("re").findall(
                r'(?is)<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', html_page
            ):
                abs_url = __import__("urllib.parse", fromlist=["urljoin"]).urljoin(final_url, raw)
                parts = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(abs_url)
                host = parts.hostname or ""
                if host == "memarket24.ir" or host.endswith(".memarket24.ir"):
                    internal.append(abs_url)
            print(
                f"STORE_PAGE url={url} status={status_code} final={final_url} "
                f"bytes={len(html_page)} type={content_type} title={meta.get('og:title') or meta.get('title','')!r} "
                f"products={len(product_urls)} internal_links={len(set(internal))} "
                f"product_urls={product_urls[:4]}"
            )
            print("STORE_INTERNAL_LINKS", list(dict.fromkeys(internal))[:12])
            scripts = __import__("re").findall(
                r'(?is)<script[^>]+src=["\']([^"\']+)["\']', html_page
            )
            print("STORE_SCRIPTS", scripts[:10])
        except Exception as exc:
            print(f"STORE_PAGE_FAIL url={url} error={type(exc).__name__}: {exc}")
    print("STOREFRONT_SCAN_END")

    promo = base_post(
        "بیش از ۵۰٪ تخفیف روی محصولات منتخب. برای خرید بزن رو لینک 👇",
    )
    promo_result = radar.score_post(promo)
    check("buyer_discount_cta_qualifies", promo_result["qualifies"])

    marketer = base_post(
        "هفته طلایی وبمسترها؛ تارگت فروش و پورسانت اضافه بگیر. https://l.memarket.me/lp/614/4116"
    )
    marketer_result = radar.score_post(marketer)
    check("marketer_campaign_rejected", not marketer_result["qualifies"] and bool(marketer_result["filtered_reason"]))

    commission_with_shop_cta = base_post(
        "۵۰٪ تخفیف روی محصولات منتخب؛ پورسانت هم برای شما. برای دیدن محصولات تخفیفی بزن رو لینک."
    )
    commission_result = radar.score_post(commission_with_shop_cta)
    check("commission_word_alone_not_blocking", commission_result["qualifies"])

    no_cta = base_post("حراج استثنایی با تخفیف ۵۰٪ روی محصولات منتخب.")
    no_cta_result = radar.score_post(no_cta)
    check("no_buyer_cta_rejected", not no_cta_result["qualifies"])

    check("fresh_post_accepted", radar.post_is_recent(promo, now))
    check("old_post_rejected", not radar.post_is_recent(base_post("خرید کن", age_hours=100), now))

    check(
        "persian_out_of_stock_detected",
        radar._stock_signals("<html><body>این محصول ناموجود است</body></html>") == "OUT_OF_STOCK",
    )
    check(
        "english_in_stock_detected",
        radar._stock_signals("<html><body><div>In stock</div></body></html>") == "IN_STOCK",
    )
    print("DIAGNOSTIC_COMPLETE=true")


if __name__ == "__main__":
    main()
