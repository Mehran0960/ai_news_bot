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
