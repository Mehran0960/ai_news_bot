import json
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from affilio_radar import (
    safe_product_url,
    product_id,
    build_affilio_tracking_link,
    build_click_tracking_link,
    enrich_click_statistics,
    deal_sort_key,
    is_offer_expired,
    has_verified_deal_deadline,
    has_minimum_publication_runway,
    is_urgent_priority_deal,
    is_deadline_critical_deal,
    is_materially_improved_offer,
    is_preferred_publication_time,
    preferred_publication_window,
    pending_queue_sort_key,
    refresh_pending_queue,
    select_queued_records_for_recheck,
    merge_discovery_queue,
    select_discovery_records_for_check,
    mark_discovery_candidate_checked,
    defer_pending_publication,
    select_publish_candidates,
    parse_product_page,
    score_product,
    is_publish_eligible,
    build_caption,
    format_remaining_time,
    unicode_underline,
    refresh_active_countdowns,
    _send_photo,
    _send_bale_photo,
    _edit_bale_caption,
    _edit_telegram_caption,
    repair_all_published_captions,
    _delivery_retry_platforms,
    unicode_strikethrough,
    _money_to_toman,
    api_search_product_urls,
    api_incredible_offer_product_urls,
    api_incredible_offer_product_candidates,
    parse_product_api,
    is_discount_publish_eligible,
    is_prohibited_product_title,
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
    verify_live_page_price,
    previous_publication_posts_removed,
    is_manual_publication_quarantine_active,
    MIN_POST_INTERVAL_HOURS,
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

    def test_incredible_offer_candidates_exclude_medicines_before_fetching_details(self):
        payload = {
            "data": {
                "products": [
                    {
                        "id": 123,
                        "title_fa": "قرص ویتامین ب2 بسته 60 عددی",
                        "url": "/product/dkp-123/",
                        "status": "marketable",
                        "default_variant": {"price": {"selling_price": 1000000, "rrp_price": 10000000}},
                    },
                    {
                        "id": 456,
                        "title_fa": "پاوربانک محبوب",
                        "url": "/product/dkp-456/",
                        "status": "marketable",
                        "default_variant": {"price": {"selling_price": 1000000, "rrp_price": 10000000}},
                    },
                ]
            }
        }
        candidates = api_incredible_offer_product_candidates(payload)
        titles = [candidate.get("title") for candidate in candidates]
        self.assertNotIn("قرص ویتامین ب2 بسته 60 عددی", titles)
        self.assertIn("پاوربانک محبوب", titles)

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

    def test_audience_demand_outranks_an_extreme_listed_discount(self):
        popular_gadget = score_product({
            "title": "پاوربانک محبوب",
            "current_price": 8_000_000,
            "original_price": 10_000_000,
            "rating": 4.6,
            "review_count": 50000,
            "image_url": "https://example.com/popular.jpg",
        })
        weaker_demand_deal = score_product({
            "title": "گجت کم‌نظر با تخفیف درج‌شده بیشتر",
            "current_price": 1_000_000,
            "original_price": 3_000_000,
            "rating": 4.0,
            "review_count": 100,
            "image_url": "https://example.com/deal.jpg",
        })
        self.assertLess(popular_gadget["discount_percent"], weaker_demand_deal["discount_percent"])
        self.assertGreater(deal_sort_key(popular_gadget), deal_sort_key(weaker_demand_deal))

    def test_medicines_and_supplements_are_rejected(self):
        for title in [
            "قرص زینک پلاس یوروویتال",
            "کپسول ب کمپلکس",
            "مکمل غذایی منیزیم",
            "ویال خوراکی ال-کارنیتین",
            "پودر پروتئین وی",
            "Chlorophyll supplement",
        ]:
            self.assertTrue(is_prohibited_product_title(title), title)
        for title in [
            "پاوربانک 20000",
            "هندزفری بلوتوث",
            "ژل آبرسان صورت",
            "ماوس بی سیم",
        ]:
            self.assertFalse(is_prohibited_product_title(title), title)

    def test_discount_publish_eligibility_rejects_medicines_even_if_discount_is_huge(self):
        product = {
            "title": "قرص زینک پلاس یوروویتال",
            "availability": "in_stock",
            "current_price": 100_000,
            "original_price": 1_000_000,
            "discount_percent": 90,
            "savings_toman": 900_000,
            "image_url": "https://example.com/image.jpg",
            "affiliate_url": "https://example.com/tracked-link",
        }
        self.assertFalse(is_discount_publish_eligible(product))

    def test_preferred_posting_windows_use_iran_local_time(self):
        self.assertEqual(
            preferred_publication_window(datetime(2026, 10, 18, 5, 30, tzinfo=timezone.utc)),
            "morning",
        )
        self.assertEqual(
            preferred_publication_window(datetime(2026, 10, 18, 10, 30, tzinfo=timezone.utc)),
            "afternoon",
        )
        self.assertEqual(
            preferred_publication_window(datetime(2026, 10, 18, 16, 30, tzinfo=timezone.utc)),
            "evening",
        )
        self.assertTrue(is_preferred_publication_time(datetime(2026, 10, 18, 5, 30, tzinfo=timezone.utc)))
        self.assertFalse(is_preferred_publication_time(datetime(2026, 10, 18, 7, 30, tzinfo=timezone.utc)))
        self.assertEqual(
            preferred_publication_window(datetime(2026, 10, 18, 19, 30, tzinfo=timezone.utc)),
            "quiet_hours",
        )

    def test_publication_requires_minimum_verified_runway(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        too_short = {"deal_expires_at": (now + timedelta(minutes=59, seconds=59)).isoformat()}
        exactly_minimum = {"deal_expires_at": (now + timedelta(minutes=60)).isoformat()}
        comfortably_long = {"deal_expires_at": (now + timedelta(hours=4)).isoformat()}
        unknown = {"deal_expires_at": ""}
        expired = {"deal_expires_at": (now - timedelta(seconds=1)).isoformat()}

        self.assertFalse(has_minimum_publication_runway(too_short, now))
        self.assertTrue(has_minimum_publication_runway(exactly_minimum, now))
        self.assertTrue(has_minimum_publication_runway(comfortably_long, now))
        self.assertFalse(has_minimum_publication_runway(unknown, now))
        self.assertFalse(has_minimum_publication_runway(expired, now))

    def test_urgent_priority_is_limited_to_strong_offers_with_safe_runway(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        item = {
            "product_id": "dkp-123",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=150)).isoformat(),
        }
        self.assertTrue(is_urgent_priority_deal(item, now))
        self.assertTrue(has_minimum_publication_runway(item, now))
        self.assertFalse(is_offer_expired(item, now))

        too_far = {**item, "deal_expires_at": (now + timedelta(minutes=181)).isoformat()}
        self.assertFalse(is_urgent_priority_deal(too_far, now))
        too_weak = {**item, "savings_toman": 499_999}
        self.assertFalse(is_urgent_priority_deal(too_weak, now))
        too_soon = {**item, "deal_expires_at": (now + timedelta(minutes=45)).isoformat()}
        self.assertFalse(has_minimum_publication_runway(too_soon, now))
        self.assertFalse(is_urgent_priority_deal(too_soon, now))
        expired = {**item, "deal_expires_at": (now - timedelta(seconds=1)).isoformat()}
        self.assertTrue(is_offer_expired(expired, now))
        self.assertFalse(is_urgent_priority_deal(expired, now))

    def test_deadline_critical_priority_never_overrides_runway_floor(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        close_but_safe = {
            "discount_percent": 35,
            "savings_toman": 150_000,
            "deal_expires_at": (now + timedelta(minutes=110)).isoformat(),
        }
        self.assertTrue(is_deadline_critical_deal(close_but_safe, now))
        too_far = {**close_but_safe, "deal_expires_at": (now + timedelta(minutes=121)).isoformat()}
        self.assertFalse(is_deadline_critical_deal(too_far, now))
        too_soon = {**close_but_safe, "deal_expires_at": (now + timedelta(minutes=45)).isoformat()}
        self.assertFalse(is_deadline_critical_deal(too_soon, now))
        self.assertFalse(is_deadline_critical_deal({**close_but_safe, "deal_expires_at": ""}, now))

    def test_new_offer_cycle_or_real_price_drop_can_bypass_product_cooldown(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        previous = {
            "posted_current_price": 1_000_000,
            "expires_at": (now - timedelta(minutes=5)).isoformat(),
        }
        same_price_new_campaign = {
            "current_price": 1_000_000,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
        }
        materially_cheaper = {
            "current_price": 890_000,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
        }
        unchanged = {
            "current_price": 1_000_000,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
        }
        self.assertTrue(is_materially_improved_offer(previous, same_price_new_campaign, now))
        self.assertTrue(is_materially_improved_offer({**previous, "expires_at": (now + timedelta(hours=2)).isoformat()}, materially_cheaper, now))
        self.assertFalse(is_materially_improved_offer({**previous, "expires_at": (now + timedelta(hours=2)).isoformat()}, unchanged, now))

    def test_unobserved_queued_deal_is_retained_until_rechecked_or_expiry(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        queued = {
            "product_id": "dkp-999",
            "product_url": "https://www.digikala.com/product/dkp-999/",
            "title": "پیشنهاد آزمایشی dkp-999",
            "first_seen_at": (now - timedelta(minutes=30)).isoformat(),
            "deal_expires_at": (now + timedelta(hours=2)).isoformat(),
            "discount_percent": 40,
            "savings_toman": 200_000,
            "demand_score": 50,
            "promo_score": 40,
            "current_price": 300_000,
            "original_price": 500_000,
            "urgent": False,
        }
        state = {"published": {}, "pending_queue": {"dkp-999": queued}}
        kept = refresh_pending_queue(state, [], now, observed_product_ids=set())
        self.assertIn("dkp-999", kept)
        self.assertEqual(kept["dkp-999"]["first_seen_at"], queued["first_seen_at"])
        dropped_after_failed_recheck = refresh_pending_queue(
            state, [], now, observed_product_ids={"dkp-999"}
        )
        self.assertNotIn("dkp-999", dropped_after_failed_recheck)

    def test_live_page_price_verification_rejects_mismatched_site_price(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
            "original_price": 17_500_000,
        }
        live_page = {
            "product_id": "dkp-22104577",
            "current_price": 2_500_000,
            "original_price": 17_500_000,
        }
        with patch("affilio_radar.SESSION.get", side_effect=RuntimeError("API unavailable")), patch(
            "affilio_radar.fetch_page", return_value=(product["product_url"], "<html></html>")
        ), patch("affilio_radar.parse_product_page", return_value=live_page):
            result = verify_live_page_price(product)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "live_page_price_mismatch")
        self.assertEqual(result["page_price"], 2_500_000)

    def test_live_page_price_verification_accepts_matching_live_price(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
            "original_price": 17_500_000,
        }
        live_page = {
            "product_id": "dkp-22104577",
            "current_price": 1_924_990,
            "original_price": 17_500_000,
        }
        with patch("affilio_radar.SESSION.get", side_effect=RuntimeError("API unavailable")), patch(
            "affilio_radar.fetch_page", return_value=(product["product_url"], "<html></html>")
        ), patch("affilio_radar.parse_product_page", return_value=live_page):
            result = verify_live_page_price(product)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "verified")

    def test_live_api_price_is_verified_without_requiring_html_price(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
            "original_price": 17_500_000,
        }
        live_api = {
            "product_id": "dkp-22104577",
            "product_url": product["product_url"],
            "current_price": 1_924_990,
            "original_price": 17_500_000,
            "availability": "in_stock",
        }
        response = SimpleNamespace(ok=True, status_code=200, json=lambda: {"product": "fresh"})
        with patch("affilio_radar.SESSION.get", return_value=response), patch(
            "affilio_radar.parse_product_api", return_value=live_api
        ), patch("affilio_radar.fetch_page") as html_fetch:
            result = verify_live_page_price(product)
        self.assertTrue(result["ok"])
        self.assertEqual(result["price_source"], "digikala_live_api")
        html_fetch.assert_not_called()

    def test_live_api_price_mismatch_blocks_even_when_html_is_unavailable(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
        }
        live_api = {
            "product_id": "dkp-22104577",
            "product_url": product["product_url"],
            "current_price": 2_500_000,
            "availability": "in_stock",
        }
        response = SimpleNamespace(ok=True, status_code=200, json=lambda: {"product": "fresh"})
        with patch("affilio_radar.SESSION.get", return_value=response), patch(
            "affilio_radar.parse_product_api", return_value=live_api
        ), patch("affilio_radar.fetch_page") as html_fetch:
            result = verify_live_page_price(product)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "live_page_price_mismatch")
        self.assertEqual(result["page_price"], 2_500_000)
        html_fetch.assert_not_called()

    def test_live_api_explicit_out_of_stock_blocks_publication(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
        }
        live_api = {
            "product_id": "dkp-22104577",
            "product_url": product["product_url"],
            "current_price": 1_924_990,
            "availability": "out_of_stock",
        }
        response = SimpleNamespace(ok=True, status_code=200, json=lambda: {"product": "fresh"})
        with patch("affilio_radar.SESSION.get", return_value=response), patch(
            "affilio_radar.parse_product_api", return_value=live_api
        ):
            result = verify_live_page_price(product)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "live_product_out_of_stock")

    def test_page_price_unavailable_fails_closed(self):
        product = {
            "product_id": "dkp-22104577",
            "product_url": "https://www.digikala.com/product/dkp-22104577/",
            "current_price": 1_924_990,
        }
        with patch("affilio_radar.SESSION.get", side_effect=RuntimeError("API unavailable")), patch(
            "affilio_radar.fetch_page", return_value=(product["product_url"], "<html></html>")
        ), patch("affilio_radar.parse_product_page", return_value={"product_id": "dkp-22104577"}):
            result = verify_live_page_price(product)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "live_price_unverified")

    def test_manual_safety_quarantine_blocks_republication_until_its_deadline(self):
        now = datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc)
        record = {"manual_quarantine_until": (now + timedelta(hours=24)).isoformat()}
        self.assertTrue(is_manual_publication_quarantine_active(record, now))
        self.assertFalse(is_manual_publication_quarantine_active(record, now + timedelta(hours=24)))
        self.assertFalse(is_manual_publication_quarantine_active({}, now))

    def test_same_product_is_blocked_until_all_prior_messages_are_removed(self):
        previous = {
            "telegram_message_id": 106,
            "expiry_status": "tracked",
            "bale_message_id": 90,
            "bale_expiry_status": "tracked",
            "post_history": [{
                "telegram_message_id": 97,
                "expiry_status": "deleted",
                "bale_message_id": 76,
                "bale_expiry_status": "already_absent",
            }],
        }
        self.assertFalse(previous_publication_posts_removed(previous))
        previous["expiry_status"] = "deleted"
        previous["bale_expiry_status"] = "deleted"
        self.assertTrue(previous_publication_posts_removed(previous))

    def test_near_expiry_offer_outranks_larger_discount_with_later_deadline(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        near = {
            "discount_percent": 35, "savings_toman": 150_000,
            "demand_score": 40, "promo_score": 25,
            "deal_expires_at": (now + timedelta(minutes=70)).isoformat(),
        }
        later = {
            "discount_percent": 90, "savings_toman": 2_000_000,
            "demand_score": 95, "promo_score": 90,
            "deal_expires_at": (now + timedelta(hours=3)).isoformat(),
        }
        self.assertGreater(
            pending_queue_sort_key(near, {"first_seen_at": now.isoformat()}, now),
            pending_queue_sort_key(later, {"first_seen_at": now.isoformat()}, now),
        )

    def test_urgent_deadline_ranks_a_qualified_offer_ahead_of_larger_listed_discount(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        urgent = {
            "product_id": "dkp-123",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=45)).isoformat(),
        }
        larger_but_not_urgent = {
            "product_id": "dkp-456",
            "discount_percent": 95,
            "savings_toman": 5_000_000,
            "demand_score": 80,
            "deal_expires_at": "",
        }
        self.assertGreater(
            pending_queue_sort_key(urgent, {"first_seen_at": now.isoformat()}, now),
            pending_queue_sort_key(larger_but_not_urgent, {"first_seen_at": now.isoformat()}, now),
        )

    def test_queued_offer_rechecks_rotate_after_a_fixed_priority_head(self):
        start = datetime(2026, 10, 17, 12, 3, tzinfo=timezone.utc)
        records = {}
        for i in range(12):
            pid = f"dkp-{1000+i}"
            records[pid] = {
                "product_id": pid,
                "product_url": f"https://www.digikala.com/product/{pid}/",
                "title": f"پیشنهاد آزمایشی {i}",
                "first_seen_at": (start - timedelta(minutes=i)).isoformat(),
                "deal_expires_at": (start + timedelta(hours=3)).isoformat(),
                "discount_percent": 40,
                "savings_toman": 200_000,
                "demand_score": 60,
                "promo_score": 50,
                "current_price": 300_000,
                "original_price": 500_000,
            }

        first = select_queued_records_for_recheck(records, start, max_count=4)
        second = select_queued_records_for_recheck(
            records, start + timedelta(minutes=5), max_count=4
        )
        first_ids = [pid for pid, _ in first]
        second_ids = [pid for pid, _ in second]

        self.assertEqual(len(first_ids), 4)
        self.assertEqual(len(second_ids), 4)
        self.assertEqual(first_ids[:2], second_ids[:2])
        self.assertNotEqual(first_ids[2:], second_ids[2:])
        self.assertEqual(len(set(first_ids) | set(second_ids)), 6)

    def test_pending_queue_preserves_first_seen_and_drops_missing_expired_or_recently_posted_items(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        first_seen = (now - timedelta(minutes=20)).isoformat()

        def offer(pid, discount=50, saving=200_000, deadline=""):
            return {
                "product_id": pid,
                "product_url": f"https://www.digikala.com/product/{pid}/",
                "title": f"پیشنهاد آزمایشی {pid}",
                "discount_percent": discount,
                "savings_toman": saving,
                "demand_score": 60,
                "promo_score": 70,
                "current_price": 300_000,
                "original_price": 500_000,
                "deal_expires_at": deadline,
                "market_status": "unavailable",
                "click_count_30d": 0,
                "review_count": 100,
            }

        state = {
            "published": {"dkp-777": {"ts": now.timestamp() - 60}},
            "pending_queue": {
                "dkp-123": {"first_seen_at": first_seen},
                "dkp-999": {"first_seen_at": first_seen},
            },
        }
        current = [
            offer("dkp-123"),
            offer("dkp-456"),
            offer("dkp-777"),
            offer("dkp-888", deadline=(now - timedelta(seconds=5)).isoformat()),
        ]
        queue = refresh_pending_queue(state, current, now)

        self.assertEqual(set(queue), {"dkp-123", "dkp-456"})
        self.assertEqual(queue["dkp-123"]["first_seen_at"], first_seen)
        self.assertNotIn("dkp-999", queue)
        self.assertNotIn("dkp-777", queue)
        self.assertNotIn("dkp-888", queue)
        self.assertEqual(state["pending_queue"], queue)

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
            "deal_expires_at": "2026-12-16T20:30:00+00:00",
            "rating": 4.4,
            "review_count": 1243,
        }, "https://www.digikala.com/product/dkp-15970075/?utm_source=19166")
        self.assertIn("<b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b>", caption)
        self.assertIn("<b>🛍️ گجت نمونه ۶۰</b>", caption)
        self.assertIn("<b>💚 قیمت ویژه: ۵۰۰٬۰۰۰ تومان</b>", caption)
        self.assertIn("<b>⚡️ ۲۹٪ تخفیف</b>", caption)
        self.assertEqual(caption.count("────────────"), 2)
        self.assertNotIn("💰", caption)
        self.assertNotIn("<u>", caption)
        self.assertIn("<b>🏷️ قیمت اصلی: <s>۷۰۰٬۰۰۰ تومان</s></b>", caption)
        self.assertIn("<b>⏳ ", caption)
        self.assertIn("مانده به پایان تخفیف</b>", caption)
        self.assertIn("<b>👇 برای مشاهدهٔ قیمت و خرید از دیجی‌کالا، دکمهٔ زیر رو بزن.</b>", caption)
        self.assertIn('<a href="https://t.me/OfferChin">عضویت در کانال OfferChin</a>', caption)
        self.assertLess(caption.index("عضویت در کانال"), caption.index("برای مشاهدهٔ قیمت و خرید از دیجی‌کالا"))
        self.assertNotRegex(caption, r"[0-9]")
        self.assertNotIn("قیمت امروز", caption)
        self.assertNotIn("صرفه‌جویی", caption)
        self.assertNotIn("امتیاز کاربران", caption)
        self.assertNotIn("نظر", caption)
        self.assertNotIn("پشتیبانی کانال", caption)
        self.assertNotIn("لینک خرید همکاری در فروش است", caption)
        self.assertLess(caption.index("💚 قیمت ویژه"), caption.index("⚡️"))
        self.assertLess(caption.index("────────────"), caption.index("⚡️"))
        self.assertLess(caption.index("⚡️"), caption.index("🏷️ قیمت اصلی"))
        self.assertLess(caption.index("🏷️ قیمت اصلی"), caption.index("⏳ "))
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
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "🛍️ مشاهده و خرید از دیجی‌کالا")
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], direct_affiliate_url)
        self.assertEqual(urlsplit(markup["inline_keyboard"][0][0]["url"]).netloc, "www.digikala.com")

    def test_send_bale_photo_adds_channel_and_purchase_button(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True, "result": {"message_id": 88}}
        direct_affiliate_url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.requests.post", return_value=response) as post,
        ):
            result = _send_bale_photo(b"photo-bytes", "bale caption", direct_affiliate_url)
        endpoint = post.call_args.args[0]
        data = post.call_args.kwargs["data"]
        markup = json.loads(data["reply_markup"])
        self.assertEqual(endpoint, "https://tapi.bale.ai/botbale-test-token/sendPhoto")
        self.assertEqual(data["chat_id"], "-10012345")
        self.assertEqual(data["caption"], "bale caption")
        self.assertNotIn("parse_mode", data)
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "🛍️ مشاهده و خرید از دیجی‌کالا")
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], direct_affiliate_url)
        self.assertEqual(result["message_id"], 88)

    def test_bale_caption_uses_unicode_strikethrough_for_original_price(self):
        product = {"title": "محصول نمونه", "current_price": 123_200, "original_price": 1_108_800, "discount_percent": 89}
        link = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        bale_caption = build_caption(product, link, "https://ble.ir/OfferChin", use_unicode_strikethrough=True)
        telegram_caption = build_caption(product, link)
        expected_amount = unicode_strikethrough("۱٬۱۰۸٬۸۰۰")
        self.assertIn(expected_amount, bale_caption)
        self.assertIn("*🏷️ قیمت اصلی:", bale_caption)
        self.assertIn("*💚 قیمت ویژه: ۱۲۳٬۲۰۰ تومان*", bale_caption)
        self.assertIn("*⚡️ ۸۹٪ تخفیف*", bale_caption)
        self.assertEqual(bale_caption.count("────────────"), 2)
        self.assertNotIn("💰", bale_caption)
        self.assertNotIn("\u0332", bale_caption)
        self.assertNotIn("<s>", bale_caption)
        self.assertIn("<s>۱٬۱۰۸٬۸۰۰ تومان</s>", telegram_caption)
        self.assertIn("[عضویت در کانال OfferChin](https://ble.ir/OfferChin)", bale_caption)
        self.assertIn('<a href="https://t.me/OfferChin">عضویت در کانال OfferChin</a>', telegram_caption)
        self.assertLess(bale_caption.index("عضویت در کانال"), bale_caption.index("برای مشاهدهٔ قیمت و خرید از دیجی‌کالا"))
        self.assertNotIn("<b>", bale_caption)
        self.assertNotIn("@OfferChin", bale_caption)
        self.assertNotIn("@OfferChin", telegram_caption)


    def test_countdown_formats_hours_minutes_and_expired_deadlines(self):
        now = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(
            format_remaining_time("2026-10-18T12:17:20+00:00", now),
            "۲ ساعت و ۱۳ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T10:00:15+00:00", now),
            "حداکثر ۵ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T11:00:00+00:00", now),
            "۵۵ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T10:43:20+00:00", now),
            "۳۹ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(format_remaining_time("2026-10-18T09:59:59+00:00", now), "مهلت آفر به پایان رسیده")
        self.assertEqual(format_remaining_time("2026-10-18T10:05:00+00:00", now), "حداکثر ۵ دقیقه مانده به پایان تخفیف")
        self.assertEqual(format_remaining_time("", now), "")

    def test_publication_requires_an_explicit_future_deadline_for_countdown(self):
        now = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(has_verified_deal_deadline({
            "deal_expires_at": "2026-10-18T12:17:20+00:00"
        }, now))
        self.assertFalse(has_verified_deal_deadline({}, now))
        self.assertFalse(has_verified_deal_deadline({
            "deal_expires_at": "2026-10-18T09:59:59+00:00"
        }, now))

    def test_unicode_underline_marks_visible_characters(self):
        self.assertEqual(unicode_underline("۱۲۳"), "۱\u0332۲\u0332۳\u0332")

    def test_refresh_active_countdowns_updates_verified_posts_in_place(self):
        expiry = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=17)).isoformat()
        state = {
            "published": {
                "dkp-15970075": {
                    "ts": 1, "title": "محصول نمونه",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 39, "bale_message_id": 2,
                    "posted_current_price": 123_200, "posted_original_price": 1_108_800,
                    "posted_discount_percent": 89, "expires_at": expiry,
                    "expiry_source": "digikala_live_deals_feed", "expiry_estimated": False,
                },
                "dkp-expired": {
                    "ts": 2, "title": "پیشنهاد تمام‌شده",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 40, "posted_current_price": 100_000,
                    "posted_original_price": 200_000, "posted_discount_percent": 50,
                    "expires_at": "2026-10-17T20:30:00+00:00",
                    "expiry_source": "digikala_live_deals_feed", "expiry_estimated": False,
                },
            }
        }
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.load_state", return_value=state),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption", return_value={"message_id": 39}) as edit_telegram,
            patch("affilio_radar._edit_bale_caption", return_value={"message_id": 2}) as edit_bale,
            patch("affilio_radar.save_json") as save_state,
            patch("affilio_radar.time.sleep"),
        ):
            result = refresh_active_countdowns()
        self.assertEqual(result, 0)
        self.assertEqual(edit_telegram.call_count, 1)
        self.assertEqual(edit_bale.call_count, 1)
        self.assertIn("مانده به پایان تخفیف", edit_telegram.call_args.args[1])
        self.assertIn("مانده به پایان تخفیف", edit_bale.call_args.args[1])
        self.assertIn("عضویت در کانال OfferChin", edit_telegram.call_args.args[1])
        self.assertIn("عضویت در کانال OfferChin", edit_bale.call_args.args[1])
        self.assertTrue(save_state.called)


    def test_unicode_strikethrough_marks_each_visible_character(self):
        self.assertEqual(unicode_strikethrough("۱۲۳"), "۱\u0336۲\u0336۳\u0336")
        self.assertEqual(unicode_strikethrough("۱۲۳  تومان"), "۱\u0336۲\u0336۳\u0336  ت\u0336و\u0336م\u0336ا\u0336ن\u0336")



    def test_edit_telegram_caption_retries_after_api_rate_limit(self):
        rate_limited = unittest.mock.Mock()
        rate_limited.status_code = 429
        rate_limited.json.return_value = {
            "ok": False, "error_code": 429,
            "description": "Too Many Requests: retry after 13",
            "parameters": {"retry_after": 13},
        }
        ok = unittest.mock.Mock()
        ok.status_code = 200
        ok.json.return_value = {"ok": True, "result": {"message_id": 39}}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.requests.post", side_effect=[rate_limited, ok]) as post,
            patch("affilio_radar.time.sleep") as sleep,
        ):
            result = _edit_telegram_caption(39, "updated caption", url)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(14)
        self.assertEqual(result["message_id"], 39)


    def test_edit_telegram_caption_preserves_affiliate_purchase_button(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True, "result": {"message_id": 39}}
        direct_affiliate_url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.TARGET_CHAT", "@OfferChin"),
            patch("affilio_radar.requests.post", return_value=response) as post,
        ):
            result = _edit_telegram_caption(39, "updated caption", direct_affiliate_url)
        self.assertEqual(post.call_args.args[0], "https://api.telegram.org/bottelegram-test-token/editMessageCaption")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["chat_id"], "@OfferChin")
        self.assertEqual(data["message_id"], 39)
        self.assertEqual(data["caption"], "updated caption")
        self.assertEqual(data["parse_mode"], "HTML")
        markup = json.loads(data["reply_markup"])
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "🛍️ مشاهده و خرید از دیجی‌کالا")
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], direct_affiliate_url)
        self.assertEqual(result["message_id"], 39)

    def test_repair_all_published_captions_edits_in_place_on_both_platforms(self):
        state = {
            "published": {
                "dkp-15970075": {
                    "ts": 1,
                    "title": "محصول نمونه",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 39,
                    "bale_message_id": 2,
                    "posted_current_price": 123_200,
                    "posted_original_price": 1_108_800,
                    "posted_discount_percent": 89,
                    "expires_at": "",
                },
                "dkp-no-bale": {
                    "ts": 2,
                    "title": "محصول تلگرام",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 40,
                    "posted_current_price": 100_000,
                    "posted_original_price": 200_000,
                    "posted_discount_percent": 50,
                    "expires_at": "",
                },
            }
        }
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.load_state", return_value=state),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption") as edit_telegram,
            patch("affilio_radar._edit_bale_caption") as edit_bale,
            patch("affilio_radar._send_photo") as send_telegram,
            patch("affilio_radar._send_bale_photo") as send_bale,
            patch("affilio_radar.time.sleep"),
        ):
            result = repair_all_published_captions()
        self.assertEqual(result, 0)
        self.assertEqual(edit_telegram.call_count, 2)
        self.assertEqual(edit_bale.call_count, 1)
        self.assertFalse(send_telegram.called)
        self.assertFalse(send_bale.called)
        telegram_caption = edit_telegram.call_args_list[0].args[1]
        bale_caption = edit_bale.call_args_list[0].args[1]
        self.assertIn('<a href="https://t.me/OfferChin">عضویت در کانال OfferChin</a>', telegram_caption)
        self.assertIn("[عضویت در کانال OfferChin](https://ble.ir/OfferChin)", bale_caption)
        self.assertLess(telegram_caption.index("عضویت در کانال"), telegram_caption.index("برای مشاهدهٔ قیمت و خرید از دیجی‌کالا"))
        self.assertLess(bale_caption.index("عضویت در کانال"), bale_caption.index("برای مشاهدهٔ قیمت و خرید از دیجی‌کالا"))



    def test_caption_edit_treats_unchanged_telegram_caption_as_success(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": False, "description": "Bad Request: message is not modified"}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.requests.post", return_value=response),
        ):
            result = _edit_telegram_caption(39, "same caption", url)
        self.assertEqual(result["message_id"], 39)
        self.assertTrue(result["not_modified"])

    def test_caption_edit_treats_unchanged_bale_caption_as_success(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": False, "description": "Bad Request: message is not modified"}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.requests.post", return_value=response),
        ):
            result = _edit_bale_caption(2, "same caption", url)
        self.assertEqual(result["message_id"], 2)
        self.assertTrue(result["not_modified"])



    def test_caption_edit_reports_missing_telegram_message_without_leaking_token(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": False, "description": "Bad Request: message to edit not found"}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.requests.post", return_value=response),
        ):
            result = _edit_telegram_caption(18, "updated caption", url)
        self.assertEqual(result["message_id"], 18)
        self.assertTrue(result["not_found"])

    def test_caption_edit_reports_missing_bale_message(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": False, "description": "Bad Request: message to edit not found"}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.requests.post", return_value=response),
        ):
            result = _edit_bale_caption(2, "updated caption", url)
        self.assertEqual(result["message_id"], 2)
        self.assertTrue(result["not_found"])


    def test_edit_bale_caption_preserves_purchase_button(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True, "result": {"message_id": 2}}
        direct_affiliate_url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        with (
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.requests.post", return_value=response) as post,
        ):
            result = _edit_bale_caption(2, "fixed caption", direct_affiliate_url)
        self.assertEqual(post.call_args.args[0], "https://tapi.bale.ai/botbale-test-token/editMessageCaption")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["chat_id"], "-10012345")
        self.assertEqual(data["message_id"], 2)
        self.assertEqual(data["caption"], "fixed caption")
        self.assertNotIn("parse_mode", data)
        markup = json.loads(data["reply_markup"])
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], direct_affiliate_url)
        self.assertEqual(result["message_id"], 2)

    def test_failed_bale_delivery_is_retried_without_reposting_to_telegram(self):
        record = {"delivery_version": 1, "delivery_status": {"telegram": "sent", "bale": "failed"}}
        with patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"), patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"):
            self.assertEqual(_delivery_retry_platforms(record), ["bale"])
        with patch("affilio_radar.BALE_BOT_TOKEN", ""), patch("affilio_radar.BALE_CHANNEL_ID", ""):
            self.assertEqual(_delivery_retry_platforms(record), [])

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

    def test_channel_watermarks_use_platform_specific_compact_links(self):
        image_bytes = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(image_bytes, format="JPEG")
        source = image_bytes.getvalue()

        default_telegram = build_discount_image(source, None)
        canonical_telegram = build_discount_image(source, None, watermark="T.me/OfferChin")
        legacy_telegram = build_discount_image(source, None, watermark="Telegram.me/OfferChin")
        bale = build_discount_image(source, None, watermark="ble.ir/OfferChin")

        self.assertEqual(default_telegram, canonical_telegram)
        self.assertEqual(legacy_telegram, canonical_telegram)
        self.assertNotEqual(bale, canonical_telegram)

    def test_normal_publication_gap_is_fifteen_minutes(self):
        self.assertEqual(MIN_POST_INTERVAL_HOURS, 0.25)

    def test_mcp_offer_card_fields_are_normalized_as_live_deal_candidates(self):
        rows = api_incredible_offer_product_candidates([{
            "id": 123,
            "title_fa": "هدفون تخفیف‌دار آزمایشی",
            "url": {"uri": "/product/dkp-123/"},
            "is_incredible": True,
            "default_variant": {
                "marketable": True,
                "price": {
                    "discount_percent": 35,
                    "selling_price_toman": 650_000,
                    "rrp_price_toman": 1_000_000,
                },
            },
        }])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_url"], "https://www.digikala.com/product/dkp-123/")
        self.assertEqual(rows[0]["discount_percent"], 35)
        self.assertEqual(rows[0]["savings_toman"], 350_000)

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



    def test_discovery_queue_records_all_candidates_before_detail_check_budget(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        queue = {}
        candidates = [
            {
                "product_url": "https://www.digikala.com/product/dkp-91001/",
                "title": "هدفون پیشنهادی با مهلت نزدیک",
                "deal_expires_at": (now + timedelta(minutes=5)).isoformat(),
                "discount_percent": 35,
                "savings_toman": 350_000,
                "current_price": 650_000,
                "original_price": 1_000_000,
            },
            {
                "product_url": "https://www.digikala.com/product/dkp-91002/",
                "title": "چراغ کاربردی با مهلت دیرتر",
                "deal_expires_at": (now + timedelta(minutes=30)).isoformat(),
                "discount_percent": 30,
                "savings_toman": 300_000,
                "current_price": 700_000,
                "original_price": 1_000_000,
            },
            {
                "product_url": "https://www.digikala.com/product/dkp-91003/",
                "title": "گجت با مهلت نامشخص",
                "discount_percent": 80,
                "savings_toman": 1_000_000,
                "current_price": 250_000,
                "original_price": 1_250_000,
            },
        ]

        merge_discovery_queue(queue, candidates, now)
        self.assertEqual(set(queue), {"dkp-91001", "dkp-91002", "dkp-91003"})
        self.assertEqual(queue["dkp-91001"]["first_seen_at"], now.isoformat())
        self.assertEqual(queue["dkp-91003"]["deal_expires_at"], "")
        self.assertEqual(queue["dkp-91001"]["last_check_status"], "discovered")

        selected = select_discovery_records_for_check(queue, now, max_count=2)
        self.assertEqual([pid for pid, _ in selected], ["dkp-91001", "dkp-91002"])

    def test_discovery_queue_check_results_schedule_fast_retry_for_near_expiry(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        queue = {}
        merge_discovery_queue(queue, [{
            "product_url": "https://www.digikala.com/product/dkp-91011/",
            "title": "محصول نزدیک به پایان",
            "deal_expires_at": (now + timedelta(minutes=20)).isoformat(),
            "discount_percent": 40,
            "savings_toman": 400_000,
        }], now)

        mark_discovery_candidate_checked(queue, "dkp-91011", "eligible", now)
        self.assertEqual(queue["dkp-91011"]["check_count"], 1)
        self.assertEqual(queue["dkp-91011"]["last_check_status"], "eligible")
        self.assertEqual(
            datetime.fromisoformat(queue["dkp-91011"]["next_check_at"]),
            now + timedelta(minutes=5),
        )
        self.assertEqual(select_discovery_records_for_check(queue, now, max_count=5), [])
        self.assertEqual(
            [pid for pid, _ in select_discovery_records_for_check(queue, now + timedelta(minutes=5), max_count=5)],
            ["dkp-91011"],
        )

    def test_discovery_queue_prunes_expired_deadlines_and_stale_unknown_deadlines(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        queue = {
            "dkp-91021": {
                "product_id": "dkp-91021",
                "product_url": "https://www.digikala.com/product/dkp-91021/",
                "title": "پیشنهاد منقضی",
                "first_seen_at": (now - timedelta(hours=1)).isoformat(),
                "last_seen_at": (now - timedelta(hours=1)).isoformat(),
                "deal_expires_at": (now - timedelta(minutes=1)).isoformat(),
            },
            "dkp-91022": {
                "product_id": "dkp-91022",
                "product_url": "https://www.digikala.com/product/dkp-91022/",
                "title": "نامزد قدیمی با مهلت نامعلوم",
                "first_seen_at": (now - timedelta(hours=30)).isoformat(),
                "last_seen_at": (now - timedelta(hours=25)).isoformat(),
                "deal_expires_at": "",
            },
        }
        merge_discovery_queue(queue, [], now)
        self.assertEqual(queue, {})


    def test_failed_publish_candidate_is_backed_off_and_next_candidate_is_selected(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        state = {
            "pending_queue": {
                "dkp-92001": {
                    "product_id": "dkp-92001",
                    "product_url": "https://www.digikala.com/product/dkp-92001/",
                },
                "dkp-92002": {
                    "product_id": "dkp-92002",
                    "product_url": "https://www.digikala.com/product/dkp-92002/",
                },
            }
        }
        eligible = {
            "dkp-92001": {"product_id": "dkp-92001", "title": "اولین نامزد خراب"},
            "dkp-92002": {"product_id": "dkp-92002", "title": "نامزد بعدی"},
        }

        failed = defer_pending_publication(state, "dkp-92001", "image_fetch_failed", now)
        self.assertEqual(failed["publish_failure_count"], 1)
        self.assertEqual(failed["last_publish_failure"], "image_fetch_failed")
        self.assertEqual(
            datetime.fromisoformat(failed["next_publish_attempt_at"]),
            now + timedelta(minutes=5),
        )
        selected = select_publish_candidates(state["pending_queue"], eligible, now)
        self.assertEqual([item["product_id"] for item in selected], ["dkp-92002"])
        # Deferral does not delete the candidate; it returns after its retry window.
        selected_later = select_publish_candidates(
            state["pending_queue"], eligible, now + timedelta(minutes=5)
        )
        self.assertEqual([item["product_id"] for item in selected_later], ["dkp-92001", "dkp-92002"])

    def test_repeated_publish_failures_use_bounded_exponential_backoff(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        state = {"pending_queue": {"dkp-92011": {"product_id": "dkp-92011"}}}
        delays = []
        current = now
        for _ in range(6):
            record = defer_pending_publication(state, "dkp-92011", "all_platforms_failed", current)
            retry = datetime.fromisoformat(record["next_publish_attempt_at"])
            delays.append(int((retry - current).total_seconds() / 60))
            current = retry
        self.assertEqual(delays, [5, 10, 20, 40, 60, 60])

if __name__ == "__main__":
    unittest.main()
