import json
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from affilio_radar import (
    safe_product_url,
    product_id,
    build_affilio_tracking_link,
    build_click_tracking_link,
    enrich_click_statistics,
    deal_sort_key,
    parse_product_page,
    score_product,
    is_publish_eligible,
    build_caption,
    _send_photo,
    _money_to_toman,
    api_search_product_urls,
    api_incredible_offer_product_urls,
    api_incredible_offer_product_candidates,
    parse_product_api,
    is_discount_publish_eligible,
    deal_sort_key,
    build_discount_image,
    _latin_font,
    extract_deal_expiry,
    gregorian_to_jalali,
    format_deal_expiry,
    format_discount_badge,
    is_market_value_publish_eligible,
    parse_price_history,
    apply_snapshot_price_history,
    is_historically_discount_eligible,
    market_query_from_title,
    market_query_variants,
    market_name_match_score,
    apply_market_price_comparison,
    is_market_price_uncompetitive,
)


IN_STOCK_HTML = """
<html><head>
<meta property="og:title" content="پاوربانک کاربردی مدل تست">
<meta property="og:image" content="https://dkstatics-public.digikala.com/digikala-products/test.jpg">
<script type="application/ld+json">
{
  "@context":"https://schema.org",
  "@type":"Product",
  "name":"پاوربانک کاربردی مدل تست",
  "image":"https://dkstatics-public.digikala.com/digikala-products/test.jpg",
  "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.4","reviewCount":"120"},
  "offers":{"@type":"Offer","price":"1290000","priceCurrency":"IRT","availability":"https://schema.org/InStock"}
}
</script></head><body><h1>پاوربانک کاربردی مدل تست</h1><p>موجود در انبار</p></body></html>
"""

OUT_OF_STOCK_HTML = """
<html><head><script type="application/ld+json">
{
  "@context":"https://schema.org",
  "@type":"Product",
  "name":"کالای ناموجود",
  "image":"https://dkstatics-public.digikala.com/digikala-products/test.jpg",
  "offers":{"@type":"Offer","price":"850000","priceCurrency":"IRT","availability":"https://schema.org/OutOfStock"}
}
</script></head><body><p>ناموجود</p></body></html>
"""

UNKNOWN_STOCK_HTML = """
<html><head><meta property="og:title" content="گجت نمونه">
<meta property="og:image" content="https://dkstatics-public.digikala.com/digikala-products/test.jpg">
<meta property="product:price:amount" content="450000">
</head><body><h1>گجت نمونه</h1><p>توضیحات محصول</p></body></html>
"""


class AffilioRadarTests(unittest.TestCase):
    def test_product_url_accepts_only_digikala_product_pages(self):
        self.assertEqual(
            safe_product_url("https://www.digikala.com/product/dkp-1234567/some-slug/?ref=x"),
            "https://www.digikala.com/product/dkp-1234567/",
        )
        self.assertEqual(safe_product_url("https://evil-digikala.com/product/dkp-1234567/"), "")
        self.assertEqual(safe_product_url("https://www.digikala.com/category/mobile/"), "")

    def test_product_id_extraction(self):
        self.assertEqual(product_id("https://www.digikala.com/product/dkp-9876/"), "dkp-9876")
        self.assertEqual(product_id("https://www.digikala.com/search/?q=phone"), "")

    def test_affilio_product_link_uses_one_reusable_template(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        template = "https://migmig.affilio.ir/api/v1/Click/b/channel-token/{YOUR_BASE64_ENCODED_URL}"
        linked = build_affilio_tracking_link(product, template)
        import base64
        encoded = base64.b64encode(product.encode("utf-8")).decode("ascii")
        self.assertEqual(linked, template.replace("{YOUR_BASE64_ENCODED_URL}", encoded))
        self.assertNotIn("{YOUR_BASE64_ENCODED_URL}", linked)
        self.assertEqual(linked.split("/api/v1/Click/")[0], "https://migmig.affilio.ir")

    def test_affilio_query_parameter_template_is_supported(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        template = "https://migmig.affilio.ir/api/v1/Click/b/media-code?b64={YOUR_BASE64_ENCODED_URL}"
        linked = build_affilio_tracking_link(product, template)
        self.assertTrue(linked.startswith("https://migmig.affilio.ir/api/v1/Click/b/media-code?b64="))
        self.assertNotIn("{YOUR_BASE64_ENCODED_URL}", linked)

    def test_click_tracker_wraps_only_same_product_affiliate_destinations(self):
        product = "https://www.digikala.com/product/dkp-15970075/"
        affiliate = build_affilio_tracking_link(product)
        tracked = build_click_tracking_link(product, affiliate, "https://tracker.example")
        parsed = urlsplit(tracked)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "tracker.example")
        self.assertEqual(parsed.path, "/p/dkp-15970075")
        self.assertEqual(parse_qs(parsed.query).get("u"), [affiliate])

        wrong_product = build_click_tracking_link(
            "https://www.digikala.com/product/dkp-999/",
            affiliate,
            "https://tracker.example",
        )
        self.assertEqual(wrong_product, affiliate)

    def test_click_tracker_preserves_supported_affilio_template(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        template = "https://migmig.affilio.ir/api/v1/Click/b/media-code?b64={YOUR_BASE64_ENCODED_URL}"
        affiliate = build_affilio_tracking_link(product, template)
        tracked = build_click_tracking_link(product, affiliate, "https://tracker.example")
        self.assertTrue(tracked.startswith("https://tracker.example/p/dkp-1234567?u="))

    def test_direct_affilio_link_uses_user_provided_digikala_parameters(self):
        product = "https://www.digikala.com/product/dkp-15970075/?old_tracking=remove"
        linked = build_affilio_tracking_link(product)
        parsed = urlsplit(linked)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "www.digikala.com")
        self.assertEqual(parsed.path, "/product/dkp-15970075/")
        self.assertEqual(params.get("utm_source"), ["19166"])
        self.assertEqual(params.get("utm_medium"), ["Affilio"])
        self.assertEqual(params.get("utm_id"), ["14657"])
        self.assertEqual(params.get("affid"), ["OTgxYTY0OTAtODJhNS00MDNkLTg0NDItMWE0MGVkOGI1Yjhj"])
        self.assertNotIn("old_tracking", params)

    def test_affilio_link_builder_rejects_invalid_template_or_product(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        self.assertEqual(
            build_affilio_tracking_link(product, "https://evil.example/api/v1/Click/b/x/{YOUR_BASE64_ENCODED_URL}"),
            "",
        )
        self.assertEqual(
            build_affilio_tracking_link(product, "https://migmig.affilio.ir/api/v1/Click/b/x/no-placeholder"),
            "",
        )
        self.assertEqual(
            build_affilio_tracking_link("https://evil.example/product/dkp-1234567/", "https://migmig.affilio.ir/api/v1/Click/b/x/{YOUR_BASE64_ENCODED_URL}"),
            "",
        )

    def test_search_api_uses_only_product_array_not_category_filter_ids(self):
        payload = {
            "data": {
                "filters": {
                    "categories": {"options": [{"id": 77, "title_fa": "پاوربانک"}]},
                    "color_palettes": {"options": [{"id": 1, "title": "صورتی"}]},
                },
                "products": [
                    {
                        "id": 12345,
                        "title_fa": "پاوربانک آزمایشی",
                        "url": "/product/dkp-12345/powerbank/",
                        "status": "marketable",
                        "product_type": "product",
                        "images": {},
                        "default_variant": {},
                    },
                    {
                        "id": 67890,
                        "title_fa": "هدفون آزمایشی",
                        "status": "marketable",
                        "product_type": "product",
                        "images": {},
                    },
                    {"id": 999, "title_fa": "یک رکورد معمولی"},
                ],
            }
        }
        self.assertEqual(
            api_search_product_urls(payload),
            [
                "https://www.digikala.com/product/dkp-12345/",
                "https://www.digikala.com/product/dkp-67890/",
            ],
        )

    def test_incredible_offers_parser_keeps_discounted_product_urls_only(self):
        payload = {
            "data": {
                "products": [
                    {
                        "id": 12345,
                        "title_fa": "پاوربانک تخفیف‌دار",
                        "url": "/product/dkp-12345/powerbank/",
                        "status": "marketable",
                        "price": {
                            "selling_price": 1_000_000,
                            "rrp_price": 2_000_000,
                            "discount_percent": 50,
                        },
                    },
                    {
                        "id": 12348,
                        "title_fa": "پاوربانک با تخفیف بیشتر",
                        "url": "/product/dkp-12348/high-discount/",
                        "status": "marketable",
                        "price": {
                            "selling_price": 200_000,
                            "rrp_price": 2_000_000,
                            "discount_percent": 90,
                        },
                    },
                    {
                        "id": 12346,
                        "title_fa": "کالای بدون تخفیف",
                        "url": "/product/dkp-12346/ordinary/",
                        "status": "marketable",
                        "price": {
                            "selling_price": 1_000_000,
                            "rrp_price": 1_000_000,
                            "discount_percent": 0,
                        },
                    },
                    {
                        "id": 12349,
                        "title_fa": "جوراب ساق بلند مردانه پرتخفیف",
                        "url": "/product/dkp-12349/socks/",
                        "status": "marketable",
                        "price": {
                            "selling_price": 10_000,
                            "rrp_price": 1_000_000,
                            "discount_percent": 99,
                        },
                    },
                    {
                        "id": 12347,
                        "title_fa": "کالای ناموجود",
                        "url": "/product/dkp-12347/out/",
                        "status": "out_of_stock",
                        "price": {
                            "selling_price": 1_000_000,
                            "rrp_price": 2_000_000,
                            "discount_percent": 50,
                        },
                    },
                ]
            }
        }
        self.assertEqual(
            api_incredible_offer_product_urls(payload),
            [
                "https://www.digikala.com/product/dkp-12349/",
                "https://www.digikala.com/product/dkp-12348/",
                "https://www.digikala.com/product/dkp-12345/",
            ],
        )
        candidates = api_incredible_offer_product_candidates(payload)
        self.assertEqual(
            [row["discount_percent"] for row in candidates],
            [99, 90, 50],
        )
        # The highest-discount item is a clothing product; no category filter is applied.
        self.assertEqual(candidates[0]["discount_percent"], 99)

    def test_extreme_discount_ranks_first_regardless_of_product_category(self):
        popular_gadget = score_product({
            "title": "پاوربانک محبوب",
            "current_price": 8_000_000,
            "original_price": 10_000_000,
            "rating": 4.6,
            "review_count": 50000,
            "image_url": "https://example.com/popular.jpg",
        })
        unrelated_extreme_discount = score_product({
            "title": "کپسول مکمل غذایی پرتخفیف",
            "current_price": 1_000_000,
            "original_price": 3_000_000,
            "rating": 4.0,
            "review_count": 100,
            "image_url": "https://example.com/deal.jpg",
        })
        self.assertLess(popular_gadget["discount_percent"], unrelated_extreme_discount["discount_percent"])
        self.assertGreater(deal_sort_key(unrelated_extreme_discount), deal_sort_key(popular_gadget))

    def test_discount_publishing_requires_minimum_percentage_and_saving(self):
        base = {
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 900_000,
            "original_price": 1_000_000,
            "image_url": "https://example.com/image.jpg",
            "affiliate_url": "https://www.digikala.com/product/dkp-1234567/?utm_source=19166",
        }
        ten_percent = score_product(dict(base))
        self.assertFalse(is_discount_publish_eligible(ten_percent))
        strong_discount = score_product({
            **base,
            "current_price": 700_000,
            "original_price": 1_000_000,
        })
        self.assertTrue(is_discount_publish_eligible(strong_discount))
        missing_stock = dict(strong_discount, availability="unknown")
        self.assertFalse(is_discount_publish_eligible(missing_stock))


    def test_irr_prices_are_converted_to_toman(self):
        self.assertEqual(_money_to_toman("12900000", "IRR"), 1_290_000)
        self.assertEqual(_money_to_toman("1290000", "IRT"), 1_290_000)

    def test_parser_reads_schema_stock_price_image_and_reviews(self):
        p = parse_product_page("https://www.digikala.com/product/dkp-1/", IN_STOCK_HTML)
        self.assertEqual(p["availability"], "in_stock")
        self.assertEqual(p["availability_source"], "schema.org")
        self.assertEqual(p["current_price"], 1_290_000)
        self.assertEqual(p["rating"], 4.4)
        self.assertEqual(p["review_count"], 120)
        self.assertIn("digikala-products/test.jpg", p["image_url"])

    def test_parser_recognizes_out_of_stock(self):
        p = parse_product_page("https://www.digikala.com/product/dkp-2/", OUT_OF_STOCK_HTML)
        self.assertEqual(p["availability"], "out_of_stock")

    def test_product_api_normalizes_rating_to_five_star_scale(self):
        payload = {
            "status": 200,
            "data": {
                "product": {
                    "id": 12345,
                    "title_fa": "کابل شارژ آزمایشی",
                    "url": {
                        "base": None,
                        "uri": "/product/dkp-12345/کابل-شارژ",
                        "params": [{"variant_id": 678}],
                    },
                    "status": "marketable",
                    "product_type": "product",
                    "images": {"main": "https://dkstatics-public.digikala.com/digikala-products/test.jpg"},
                    "rating": {"rate": 68.12, "count": 120},
                    "default_variant": {
                        "id": 678,
                        "status": "marketable",
                        "price": {
                            "selling_price": 4_850_000,
                            "rrp_price": 9_000_000,
                            "discount_percent": 46,
                            "marketable_stock": 10,
                        },
                    },
                }
            },
        }
        p = parse_product_api(payload, "https://www.digikala.com/product/dkp-12345/")
        self.assertEqual(p["availability"], "in_stock")
        self.assertEqual(p["current_price"], 485_000)
        self.assertEqual(p["original_price"], 900_000)
        self.assertEqual(p["rating"], 3.41)
        self.assertEqual(p["review_count"], 120)
        self.assertTrue(p["image_url"].startswith("https://"))

    def test_parser_fails_closed_when_stock_is_unknown(self):
        p = parse_product_page("https://www.digikala.com/product/dkp-3/", UNKNOWN_STOCK_HTML)
        self.assertEqual(p["availability"], "unknown")

    def test_click_counts_are_attached_and_missing_data_fails_open(self):
        products = [
            {"product_id": "dkp-123", "title": "Offer A"},
            {"product_id": "dkp-456", "title": "Offer B"},
        ]
        response = unittest.mock.Mock()
        response.json.return_value = {
            "ok": True,
            "complete": True,
            "days": 30,
            "totalClicks": 12,
            "updatedAt": "2026-10-16T00:00:00Z",
            "products": {"dkp-123": 12, "unsafe-key": 999},
        }
        with patch("affilio_radar.SESSION.get", return_value=response):
            enrich_click_statistics(products)
        self.assertEqual(products[0]["click_count_30d"], 12)
        self.assertEqual(products[1]["click_count_30d"], 0)

        incomplete = unittest.mock.Mock()
        incomplete.json.return_value = {
            "ok": True, "complete": False, "products": {"dkp-456": 900}
        }
        products = [{"product_id": "dkp-456"}]
        with patch("affilio_radar.SESSION.get", return_value=incomplete):
            enrich_click_statistics(products)
        self.assertEqual(products[0]["click_count_30d"], 0)

    def test_clicks_break_ties_only_after_discount_saving_and_verified_market(self):
        low_clicks = {
            "discount_percent": 60,
            "savings_toman": 900_000,
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 7,
            "click_count_30d": 2,
        }
        high_clicks = {**low_clicks, "click_count_30d": 11}
        self.assertGreater(deal_sort_key(high_clicks), deal_sort_key(low_clicks))
        weaker_discount = {**high_clicks, "discount_percent": 59}
        self.assertGreater(deal_sort_key(high_clicks), deal_sort_key(weaker_discount))

    def test_score_rewards_reviews_without_category_priority(self):
        high = score_product({
            "title": "پاوربانک سریع",
            "current_price": 1_200_000,
            "original_price": 1_500_000,
            "rating": 4.5,
            "review_count": 1000,
            "image_url": "https://example.com/image.jpg",
        })
        low = score_product({
            "title": "کالای معمولی",
            "current_price": 25_000_000,
            "rating": 3.0,
            "review_count": 0,
            "image_url": "",
        })
        self.assertGreater(high["demand_score"], low["demand_score"])
        self.assertEqual(high["discount_percent"], 20)

    def test_same_offer_signals_get_same_score_across_categories(self):
        shared = {
            "current_price": 790_000,
            "original_price": 1_490_000,
            "rating": 4.5,
            "review_count": 800,
            "image_url": "https://example.com/image.jpg",
        }
        digital = score_product({**shared, "title": "پاوربانک سریع"})
        unrelated = score_product({**shared, "title": "مکمل غذایی"})
        self.assertEqual(digital["demand_score"], unrelated["demand_score"])
        self.assertEqual(digital["promo_score"], unrelated["promo_score"])

    def test_high_review_volume_can_outweigh_price_band_for_demand_ranking(self):
        broad_demand = score_product({
            "title": "پاوربانک 20000",
            "current_price": 3_300_000,
            "original_price": 4_700_000,
            "rating": 4.2,
            "review_count": 21_821,
            "image_url": "https://example.com/image.jpg",
        })
        lower_volume = score_product({
            "title": "پاوربانک 20000 مدل اقتصادی",
            "current_price": 3_300_000,
            "original_price": 4_700_000,
            "rating": 4.2,
            "review_count": 280,
            "image_url": "https://example.com/image.jpg",
        })
        self.assertGreater(broad_demand["demand_score"], lower_volume["demand_score"])

    def test_publish_requires_stock_price_image_and_https_affiliate_link(self):
        base = {
            "availability": "in_stock",
            "current_price": 500_000,
            "image_url": "https://example.com/image.jpg",
            "affiliate_url": "https://example.com/tracked-link",
        }
        self.assertTrue(is_publish_eligible(base))
        for key, value in [
            ("availability", "unknown"),
            ("availability", "out_of_stock"),
            ("current_price", None),
            ("image_url", ""),
            ("affiliate_url", ""),
            ("affiliate_url", "http://example.com/tracked-link"),
        ]:
            candidate = dict(base)
            candidate[key] = value
            self.assertFalse(is_publish_eligible(candidate), key)

    def test_caption_uses_approved_compact_format_and_persian_numerals(self):
        caption = build_caption({
            "title": "گجت نمونه 60",
            "current_price": 500_000,
            "original_price": 700_000,
            "discount_percent": 29,
            "deal_expires_at": "2026-10-16T20:30:00+00:00",
            "rating": 4.4,
            "review_count": 1243,
        }, "https://www.digikala.com/product/dkp-15970075/?utm_source=19166")
        self.assertIn("<b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b>", caption)
        self.assertIn("<b>🛍️ گجت نمونه ۶۰</b>", caption)
        self.assertIn("<b>💚 قیمت ویژه: 💰 ۵۰۰٬۰۰۰ تومان</b>", caption)
        self.assertIn("<b>⚡️ ۲۹٪ تخفیف ویژه</b>", caption)
        self.assertIn("<b>🏷️ قیمت اصلی: <s>۷۰۰٬۰۰۰ تومان</s></b>", caption)
        self.assertIn("<b>⏳ پایان تخفیف: جمعه ۲۴ مهر ۱۴۰۵، ساعت ۲۳:۵۹</b>", caption)
        self.assertIn("<b>👇 برای دیدن جزئیات، دکمهٔ زیر رو بزن.</b>", caption)
        self.assertTrue(caption.endswith("<b>📣</b> @OfferChin"))
        self.assertNotRegex(caption, r"[0-9]")
        self.assertNotIn("قیمت امروز", caption)
        self.assertNotIn("صرفه‌جویی", caption)
        self.assertNotIn("امتیاز کاربران", caption)
        self.assertNotIn("نظر", caption)
        self.assertNotIn("پشتیبانی کانال", caption)
        self.assertNotIn("لینک خرید همکاری در فروش است", caption)
        self.assertLess(caption.index("💚 قیمت ویژه"), caption.index("⚡️"))
        self.assertLess(caption.index("💰 ۵۰۰٬۰۰۰ تومان"), caption.index("⚡️"))
        self.assertLess(caption.index("⚡️"), caption.index("🏷️ قیمت اصلی"))
        self.assertLess(caption.index("🏷️ قیمت اصلی"), caption.index("⏳ پایان تخفیف"))
        self.assertLessEqual(len(caption), 1024)
        self.assertNotIn("کمیسیون", caption)
        self.assertNotIn("تاریخچه", caption)


    def test_midnight_expiry_displays_previous_day_at_2359(self):
        self.assertEqual(
            format_deal_expiry("2026-10-16T20:30:00+00:00"),
            "جمعه ۲۴ مهر ۱۴۰۵، ساعت ۲۳:۵۹",
        )

    def test_non_midnight_expiry_keeps_the_actual_calendar_day_and_time(self):
        self.assertEqual(
            format_deal_expiry("2026-10-17T09:00:00+00:00"),
            "شنبه ۲۵ مهر ۱۴۰۵، ساعت ۱۲:۳۰",
        )

    def test_gregorian_to_jalali_conversion_across_calendar_boundaries(self):
        self.assertEqual(gregorian_to_jalali(2026, 10, 17), (1405, 7, 25))
        self.assertEqual(gregorian_to_jalali(2026, 3, 21), (1405, 1, 1))
        self.assertEqual(gregorian_to_jalali(2025, 3, 20), (1403, 12, 30))

    def test_caption_omits_deadline_when_source_has_no_confirmed_expiry(self):
        caption = build_caption({
            "title": "محصول بی‌زمان پایان",
            "current_price": 100_000,
            "original_price": 200_000,
            "discount_percent": 50,
        }, "https://www.digikala.com/product/dkp-15970075/?utm_source=19166")
        self.assertNotIn("پایان تخفیف", caption)

    def test_send_photo_adds_one_direct_affiliate_purchase_button(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True, "result": {"message_id": 9}}
        direct_affiliate_url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with patch("affilio_radar.BOT_TOKEN", "test-token"), patch("affilio_radar.requests.post", return_value=response) as post:
            _send_photo(b"photo-bytes", "caption", direct_affiliate_url)
        data = post.call_args.kwargs["data"]
        markup = json.loads(data["reply_markup"])
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "🛍️ مشاهده تخفیف و خرید")
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], direct_affiliate_url)
        self.assertEqual(urlsplit(markup["inline_keyboard"][0][0]["url"]).netloc, "www.digikala.com")

    def test_discount_badge_uses_short_english_label(self):
        self.assertEqual(format_discount_badge(81), "81% OFF")
        self.assertEqual(format_discount_badge("24"), "24% OFF")
        self.assertEqual(format_discount_badge(0), "")
        self.assertEqual(format_discount_badge("not-a-number"), "")

    def test_badge_font_supports_latin_percent_and_letters(self):
        font = _latin_font(32)
        # The badge is ASCII-only; do not reuse the Arabic-only font used for Persian text.
        self.assertGreater(font.getlength("89% OFF"), font.getlength("89"))
        self.assertGreater(font.getlength("% OFF"), 0)

    def test_discount_image_returns_photo_with_badge(self):
        image_bytes = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(image_bytes, format="JPEG")
        rendered = build_discount_image(image_bytes.getvalue(), 24)
        with Image.open(BytesIO(rendered)) as preview:
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.size, (480, 640))
        self.assertNotEqual(rendered, image_bytes.getvalue())
        # Channel watermark must still render when a discount badge is unavailable.
        rendered_without_badge = build_discount_image(image_bytes.getvalue(), None)
        with Image.open(BytesIO(rendered_without_badge)) as preview:
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.size, (480, 640))
        self.assertNotEqual(rendered_without_badge, image_bytes.getvalue())

    def test_incredible_offer_expiry_supports_absolute_deadline(self):
        value = extract_deal_expiry({
            "id": 123,
            "title_fa": "محصول تست",
            "ends_at": "2026-10-16T20:30:00+03:30",
        })
        self.assertEqual(value, "2026-10-16T17:00:00+00:00")

    def test_incredible_offer_expiry_supports_nested_countdown_seconds(self):
        before = datetime.now(timezone.utc)
        value = extract_deal_expiry({
            "id": 123,
            "title_fa": "محصول تست",
            "campaign": {"ends_in_seconds": 3600},
        })
        parsed = datetime.fromisoformat(value)
        after = datetime.now(timezone.utc)
        self.assertGreaterEqual(parsed, before + timedelta(seconds=3599))
        self.assertLessEqual(parsed, after + timedelta(seconds=3601))

    def test_incredible_offer_without_expiry_is_not_guessed(self):
        self.assertEqual(extract_deal_expiry({"id": 123, "title_fa": "بدون زمان پایان"}), "")

    def test_missing_market_data_does_not_block_publication(self):
        base = {
            "availability": "in_stock",
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_match_score": 90,
            "market_available_offer_count": 3,
            "market_price_advantage_pct": 8,
        }
        self.assertTrue(is_market_value_publish_eligible(base))
        for key, value in [
            ("market_status", "limited"),
            ("market_status", "unavailable"),
            ("market_status", "not_checked"),
            ("market_reference_kind", "lowest_torob_offer"),
            ("market_available_offer_count", 2),
            ("market_match_score", 60),
            ("market_price_advantage_pct", 4),
            ("market_price_advantage_pct", None),
        ]:
            candidate = dict(base)
            candidate[key] = value
            self.assertTrue(is_market_value_publish_eligible(candidate), key)

    def test_only_confirmed_uncompetitive_market_price_blocks_publication(self):
        candidate = {
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_match_score": 90,
            "market_available_offer_count": 3,
            "market_price_advantage_pct": -8,
        }
        self.assertFalse(is_market_value_publish_eligible(candidate))
        candidate["market_price_advantage_pct"] = 8
        self.assertTrue(is_market_value_publish_eligible(candidate))

    def test_price_history_uses_matching_variant_and_converts_rials_to_toman(self):
        toman_prices = [120_000, 110_000, 100_000, 88_000, 90_000, 130_000, 110_000]
        payload = {
            "status": 200,
            "data": {
                "price_chart": [{
                    "title": "مدل اصلی",
                    "history": [
                        {
                            "day": f"1405/07/{day:02d}",
                            "selling_price": price * 10,
                            "is_marketable": True,
                        }
                        for day, price in enumerate(toman_prices, start=1)
                    ],
                }]
            },
        }
        history = parse_price_history(payload, current_price=90_000)
        self.assertEqual(history["history_status"], "verified")
        self.assertEqual(history["history_days"], 7)
        self.assertEqual(history["history_low_toman"], 88_000)
        self.assertEqual(history["history_stable_low_toman"], 90_000)
        self.assertEqual(history["history_median_toman"], 110_000)
        self.assertEqual(history["discount_vs_30d_median_pct"], 18)
        self.assertTrue(history["historical_deal_eligible"])

    def test_price_history_prefers_matching_variant_for_a_large_price_drop(self):
        def chart(title, prices):
            return {
                "title": title,
                "history": [
                    {
                        "day": f"1405/07/{day:02d}",
                        "selling_price": price * 10,
                        "is_marketable": True,
                    }
                    for day, price in enumerate(prices, start=1)
                ],
            }

        payload = {
            "status": 200,
            "data": {
                "price_chart": [
                    chart("سفید", [300_000] * 7),
                    chart("مشکی", [100_000, 105_000, 100_000, 98_000, 100_000, 100_000, 100_000]),
                ]
            },
        }
        matched = parse_price_history(payload, current_price=70_000, variant_label="مشکی")
        self.assertEqual(matched["history_status"], "verified")
        self.assertEqual(matched["history_variant"], "مشکی")
        self.assertEqual(matched["history_variant_match"], "label")
        self.assertEqual(matched["discount_vs_30d_median_pct"], 30)
        self.assertTrue(matched["historical_deal_eligible"])

        ambiguous = parse_price_history(payload, current_price=70_000)
        self.assertEqual(ambiguous["history_status"], "variant_mismatch")

    def test_history_gate_rejects_an_inflated_list_price_without_real_price_edge(self):
        product = {
            "current_price": 200_000,
            "original_price": 1_000_000,
            "discount_percent": 80,
            "history_status": "verified",
            "history_days": 30,
            "history_median_toman": 205_000,
            "history_stable_low_toman": 190_000,
        }
        self.assertFalse(is_historically_discount_eligible(product))
        product["history_status"] = "pending_history"
        self.assertFalse(is_historically_discount_eligible(product))

        # A product sitting at the same price all month is not a deal just because
        # that unchanged price is also its observed historical low.
        flat_price = {
            "current_price": 1_490_000,
            "history_status": "verified",
            "history_days": 15,
            "history_median_toman": 1_490_000,
            "history_stable_low_toman": 1_490_000,
        }
        self.assertFalse(is_historically_discount_eligible(flat_price))

    def test_saved_daily_snapshots_can_verify_a_deal_when_public_chart_fails(self):
        product = {
            "product_id": "dkp-42",
            "product_url": "https://www.digikala.com/product/dkp-42/",
            "current_price": 900_000,
        }
        state = {
            "price_history": {
                "dkp-42": {
                    "snapshots": [
                        {"day": f"2026-10-{day:02d}", "price": 1_000_000}
                        for day in range(1, 8)
                    ],
                    "last_seen_day": "2026-10-07",
                }
            }
        }
        result = apply_snapshot_price_history(product, state)
        self.assertEqual(result["history_status"], "verified")
        self.assertEqual(result["history_source"], "radar_daily_snapshots")
        self.assertEqual(result["history_days"], 7)
        self.assertEqual(result["discount_vs_30d_median_pct"], 10)
        self.assertTrue(result["historical_deal_eligible"])


    def test_market_query_variants_adds_short_identity_fallback(self):
        variants = market_query_variants("کپسول ژلاتینی نرم زینک پلاس فلکسان بسته 60 عددی")
        self.assertEqual(variants[0], "کپسول ژلاتینی نرم زینک پلاس فلکسان بسته 60 عددی")
        self.assertIn("زینک پلاس فلکسان", variants)
        self.assertNotIn("60", variants[-1])

    def test_market_query_keeps_model_identity_and_folds_persian_variants(self):
        query = market_query_from_title("هندزفری بی‌سیم کیو سی وای مدل T13 ANC2، نویز کنسلینگ و شارژ USB-C")
        self.assertEqual(query, "هندزفری بی‌سیم کیو سی وای مدل T13 ANC2")
        score = market_name_match_score(
            query,
            "هندزفری بلوتوثی QCY T13 ANC2 مدل بی سیم",
        )
        self.assertGreaterEqual(score, 60)

    def test_market_matching_rejects_shared_generic_words_without_brand_match(self):
        score = market_name_match_score(
            "زینک پلاس فلکسان",
            "قرص جوشان اوریکس پلاس ۱۰ عددی زینک های هلث",
        )
        self.assertLess(score, 85)

    def test_market_matching_rejects_same_brand_but_different_ingredient_and_strength(self):
        query = "قرص زینک پلاس یوروویتال 15 میلی گرم بسته 60 عددی"
        wrong_product = "قرص ویتامین B3 یوروویتال 250 میلی گرم 60 عددی"
        exact_product = "قرص زینک پلاس یوروویتال 15 میلی گرم 60 عددی"
        self.assertEqual(market_name_match_score(query, wrong_product), 0)
        self.assertGreaterEqual(market_name_match_score(query, exact_product), 80)

    def test_market_matching_rejects_a_generic_speaker_with_a_different_model(self):
        query = "اسپیکر بلوتوثی قابل حمل مدل Luxe"
        wrong_model = "اسپیکر بلوتوثی جی بی ال مدل Mini M8 قابل حمل"
        self.assertEqual(market_name_match_score(query, wrong_model), 0)

    def test_market_median_is_calculated_from_multiple_reliable_seller_offers(self):
        product = {"current_price": 1_800_000}
        card = {
            "prk": "prk-example",
            "name_fa": "اسپیکر بلوتوثی مدل نمونه X1",
            "price_toman": 1_900_000,
            "available": True,
            "url": "https://torob.com/p/prk-example/",
        }
        details = {
            "available": True,
            "offer_count": 3,
            "offers": [
                {"price_toman": 2_000_000, "available": True, "price_unreliable": False},
                {"price_toman": 2_100_000, "available": True, "price_unreliable": False},
                {"price_toman": 2_200_000, "available": True, "price_unreliable": False},
                {"price_toman": 9_999_000, "available": True, "price_unreliable": True},
                {"price_toman": 1_700_000, "available": False, "price_unreliable": False},
            ],
        }
        result = apply_market_price_comparison(product, card, details, 85, "اسپیکر بلوتوثی مدل نمونه X1")
        self.assertEqual(result["market_status"], "verified")
        self.assertEqual(result["market_reference_price_toman"], 2_100_000)
        self.assertEqual(result["market_available_offer_count"], 3)
        self.assertGreater(result["market_price_advantage_pct"], 0)
        self.assertFalse(is_market_price_uncompetitive(result))

    def test_reliable_market_comparison_blocks_only_if_digikala_is_materially_dearer(self):
        product = {"current_price": 2_350_000}
        card = {
            "prk": "prk-example",
            "name_fa": "کالای یکسان مدل X1",
            "price_toman": 2_000_000,
            "available": True,
            "url": "https://torob.com/p/prk-example/",
        }
        details = {
            "available": True,
            "offer_count": 3,
            "offers": [
                {"price_toman": 2_000_000, "available": True, "price_unreliable": False},
                {"price_toman": 2_100_000, "available": True, "price_unreliable": False},
                {"price_toman": 2_200_000, "available": True, "price_unreliable": False},
            ],
        }
        result = apply_market_price_comparison(product, card, details, 90, "کالای یکسان مدل X1")
        self.assertLessEqual(result["market_price_advantage_pct"], -5)
        self.assertTrue(is_market_price_uncompetitive(result))

    def test_missing_market_data_never_blocks_an_otherwise_valid_product(self):
        product = {"current_price": 1_000_000, "market_status": "unavailable"}
        self.assertFalse(is_market_price_uncompetitive(product))
        product["market_status"] = "limited"
        product["market_price_advantage_pct"] = -45
        self.assertFalse(is_market_price_uncompetitive(product))


if __name__ == "__main__":
    unittest.main()
