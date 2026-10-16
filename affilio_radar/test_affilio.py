import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from affilio_radar import (
    safe_product_url,
    product_id,
    build_affilio_tracking_link,
    parse_product_page,
    score_product,
    is_publish_eligible,
    build_caption,
    _money_to_toman,
    api_search_product_urls,
    api_incredible_offer_product_urls,
    api_incredible_offer_product_candidates,
    parse_product_api,
    is_discount_publish_eligible,
    deal_sort_key,
    build_promo_video,
    parse_price_history,
    apply_snapshot_price_history,
    is_historically_discount_eligible,
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

    def test_discount_first_sort_prefers_larger_discount_over_higher_demand(self):
        popular_small_discount = score_product({
            "title": "پاوربانک محبوب",
            "current_price": 8_000_000,
            "original_price": 10_000_000,
            "rating": 4.6,
            "review_count": 50000,
            "image_url": "https://example.com/popular.jpg",
        })
        bigger_discount = score_product({
            "title": "کالای پرتخفیف",
            "current_price": 1_000_000,
            "original_price": 3_000_000,
            "rating": 4.0,
            "review_count": 100,
            "image_url": "https://example.com/deal.jpg",
        })
        self.assertLess(popular_small_discount["discount_percent"], bigger_discount["discount_percent"])
        self.assertGreater(deal_sort_key(bigger_discount), deal_sort_key(popular_small_discount))

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

    def test_score_rewards_relevant_category_and_reviews(self):
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

    def test_caption_contains_tracked_link_and_price_caveat(self):
        caption = build_caption({
            "title": "گجت نمونه",
            "current_price": 500_000,
            "original_price": 700_000,
            "discount_percent": 29,
            "rating": 4.1,
        }, "https://affilio.example/tracked")
        self.assertIn("https://affilio.example/tracked", caption)
        self.assertIn("قیمت و موجودی ممکن است تغییر کند", caption)
        self.assertIn("کمیسیون", caption)

    def test_promo_video_renders_as_playable_mp4(self):
        image_bytes = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(image_bytes, format="JPEG")
        with TemporaryDirectory(prefix="affilio-test-video-") as td:
            output = Path(td) / "preview.mp4"
            build_promo_video({
                "title": "پاوربانک کاربردی آزمایشی",
                "current_price": 950_000,
                "original_price": 1_250_000,
                "discount_percent": 24,
            }, image_bytes.getvalue(), output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 20_000)


    def test_price_history_uses_matching_variant_and_converts_rials_to_toman(self):
        toman_prices = [100_000, 95_000, 92_000, 88_000, 90_000, 110_000, 100_000]
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
        self.assertEqual(history["history_median_toman"], 95_000)
        self.assertEqual(history["discount_vs_30d_median_pct"], 5)
        self.assertTrue(history["historical_deal_eligible"])

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


if __name__ == "__main__":
    unittest.main()
