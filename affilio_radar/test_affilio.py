import json
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import affilio_radar as radar_module
from PIL import Image

from affilio_radar import (
    safe_product_url,
    product_id,
    build_affilio_tracking_link,
    build_click_tracking_link,
    tracked_affiliate_button_url,
    enrich_click_statistics,
    deal_sort_key,
    is_offer_expired,
    has_verified_deal_deadline,
    has_minimum_publication_runway,
    has_publishable_expiry_or_open_offer,
    parse_snappshop_product_api,
    fetch_product_record,
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
    mcp_scan_pages_for_cursor,
    discovery_queue_sort_key,
    has_meaningful_discount,
    mark_discovery_candidate_checked,
    defer_pending_publication,
    select_publish_candidates,
    select_urgent_publication_candidate,
    parse_product_page,
    score_product,
    classify_category,
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
    discover_product_urls,
    SEARCH_TERMS,
    _discovery_candidate_budgets,
    _discovery_early_source_candidate_limit,
    _snappshop_retry_cooldown_minutes,
    _rotating_search_terms,
    parse_product_api,
    is_discount_publish_eligible,
    is_prohibited_product_title,
    is_publishable_product_title,
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
    ensure_publication_ledger,
    ensure_recent_publications,
    _recent_publication_diversity,
    build_publication_diversity_report,
    _diversify_ranked_records,
    is_product_repeat_blocked,
    is_fresh_selection_candidate,
    delete_previous_channel_posts,
    process_pending_short_video,
    _delete_superseded_youtube_video,
    VIDEO_STYLE_VERSION,
    YOUTUBE_UPLOAD_INTERVAL_HOURS,
    MIN_POST_INTERVAL_HOURS,
    effective_posts_per_run,
    daily_channel_posts_count,
    ensure_telegram_source_invites,
    build_video_channel_description,
    tracked_telegram_invite_url,
    record_daily_member_count_snapshot,
)


def _with_verified_current_demand(product, now=None, growth=5, window_hours=48):
    observed = now or datetime.now(timezone.utc)
    product.update({
        "current_demand_verified": True,
        "current_demand_score": 55,
        "demand_score": 55,
        "recent_review_growth_7d": growth,
        "demand_window_hours": window_hours,
        "demand_observed_at": observed.isoformat(),
        "demand_signal_source": (
            "snappshop_recent_review_growth"
            if str(product.get("product_id", "")).startswith("snp-")
            else "digikala_recent_review_growth"
        ),
    })
    return product


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
    def setUp(self):
        # Never make live HTTP requests from unit tests; deployed Worker health is smoke-tested separately.
        self._click_tracker_health_patch = patch("affilio_radar._click_tracker_is_healthy", return_value=False)
        self._click_tracker_health_patch.start()
        self.addCleanup(self._click_tracker_health_patch.stop)

    def test_diversity_selection_keeps_leader_when_all_discounts_below_floor(self):
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        records = [
            {
                "product_id": "dkp-101",
                "title": "محصول آزمون اول",
                "discount_percent": 35,
                "demand_score": 90,
                "click_count_30d": 5,
            },
            {
                "product_id": "dkp-102",
                "title": "محصول آزمون دوم",
                "discount_percent": 40,
                "demand_score": 89,
                "click_count_30d": 5,
            },
        ]
        recent = [{
            "product_id": "dkp-old",
            "title": "کالای منتشرشده قبلی",
            "ts": now.timestamp() - 3600,
        }]

        selected = _diversify_ranked_records(
            records,
            limit=1,
            published={},
            recent_publications=recent,
            now=now,
        )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-101"])

    def test_product_url_accepts_only_digikala_product_pages(self):
        self.assertEqual(
            safe_product_url("https://www.digikala.com/product/dkp-1234567/some-slug/?ref=x"),
            "https://www.digikala.com/product/dkp-1234567/",
        )
        self.assertEqual(safe_product_url("https://evil-digikala.com/product/dkp-1234567/"), "")
        self.assertEqual(safe_product_url("https://www.digikala.com/category/mobile/"), "")

    def test_incomplete_product_titles_are_rejected_but_complete_model_titles_pass(self):
        self.assertFalse(is_publishable_product_title("هندزفری بلوتوثی مدل"))
        self.assertTrue(is_publishable_product_title(
            "پاوربانک ۳۳ وات شیائومی مدل Integrated Cable ظرفیت ۲۰۰۰۰ میلی‌آمپر ساعت"
        ))
        self.assertTrue(is_publishable_product_title("کوله پشتی سفری مدل Koo-1"))

    def test_product_id_extraction(self):
        self.assertEqual(product_id("https://www.digikala.com/product/dkp-9876/"), "dkp-9876")
        self.assertEqual(product_id("https://www.digikala.com/search/?q=phone"), "")

    def test_snappshop_product_urls_and_affilio_destination(self):
        product = "https://snappshop.ir/product/snp-2097083854?utm_source=ignored"
        canonical = "https://snappshop.ir/product/snp-2097083854"
        self.assertEqual(safe_product_url(product), canonical)
        self.assertEqual(product_id(canonical), "snp-2097083854")
        self.assertEqual(safe_product_url("https://snappshop.ir/search?q=earbuds"), "")
        self.assertEqual(safe_product_url("https://evil-snappshop.ir/product/snp-2097083854"), "")
        affiliate = build_affilio_tracking_link(product)
        self.assertEqual(parse_qs(urlsplit(affiliate).query).get("p"), [canonical])
        tracked = build_click_tracking_link(canonical, affiliate, "https://tracker.example", source="bale")
        parsed = urlsplit(tracked)
        self.assertEqual(parsed.path, "/p/snp-2097083854")
        self.assertEqual(parse_qs(parsed.query).get("u"), [affiliate])
        self.assertEqual(parse_qs(parsed.query).get("src"), ["bale"])

    def test_fetch_product_record_uses_snappshop_internal_api_id_mapping(self):
        url = "https://snappshop.ir/product/snp-25751584"
        payload = {
            "data": {
                "id": "42yeLw",
                "content": {"title_fa": "گوشی نمونه"},
                "images": ["https://cdn.snappshop.ir/products/phone-main.webp"],
                "variants": [{
                    "vendor": [{
                        "price": 49_000_000,
                        "special_price": 33_980_000,
                        "stock": 2,
                        "is_available_in_vendor_inventory": True,
                    }],
                }],
            }
        }
        response = SimpleNamespace(
            content=json.dumps(payload).encode("utf-8"),
            json=lambda: payload,
            raise_for_status=lambda: None,
        )
        with (
            patch("affilio_radar.SNAPPSHOP_API_IDS_BY_URL", {url: "42yeLw"}),
            patch("affilio_radar.SNAPPSHOP_SEARCH_CARDS_BY_URL", {}),
            patch("affilio_radar.SESSION.get", return_value=response) as get,
        ):
            record = fetch_product_record(url)
        self.assertEqual(record["availability"], "in_stock")
        self.assertEqual(record["product_id"], "snp-25751584")
        self.assertEqual(get.call_args.args[0], "https://apix.snappshop.ir/products/v2/42yeLw")
        self.assertEqual(get.call_args.kwargs["headers"]["Origin"], "https://snappshop.ir")

    def test_snappshop_caption_uses_correct_store_name(self):
        product_url = "https://snappshop.ir/product/snp-2097083854"
        affiliate = build_affilio_tracking_link(product_url)
        caption = build_caption({
            "title": "ایرفون نمونه",
            "product_url": product_url,
            "merchant": "اسنپ‌شاپ",
            "current_price": 1_065_000,
            "original_price": 2_250_000,
            "discount_percent": 53,
        }, affiliate)
        self.assertIn("🔥 فروش ویژه اسنپ‌شاپ 🟣", caption)
        self.assertNotIn("دیجی‌کالا", caption)

    def test_snappshop_without_confirmed_expiry_can_publish_when_live_deal_is_verified(self):
        now = datetime.now(timezone.utc)
        product = {
            "expiry_source": "snappshop_no_confirmed_expiry",
            "deal_expires_at": "",
            "expiry_deadline_verified_directly": False,
            "availability": "in_stock",
            "availability_source": "snappshop_product_api",
            "current_price": 3_398_000,
            "original_price": 4_900_000,
        }
        self.assertFalse(has_verified_deal_deadline(product, now=now))
        self.assertFalse(has_minimum_publication_runway(product, now=now))
        self.assertTrue(has_publishable_expiry_or_open_offer(product, now=now))

    def test_open_ended_offer_still_requires_confirmed_in_stock_and_real_discount(self):
        base = {
            "expiry_source": "snappshop_no_confirmed_expiry",
            "deal_expires_at": "",
            "availability_source": "snappshop_product_api",
            "current_price": 3_398_000,
            "original_price": 4_900_000,
        }
        self.assertFalse(has_publishable_expiry_or_open_offer({**base, "availability": "unknown"}))
        self.assertFalse(has_publishable_expiry_or_open_offer({**base, "availability": "in_stock", "original_price": 3_398_000}))
        self.assertTrue(has_publishable_expiry_or_open_offer({**base, "availability": "in_stock"}))

    def test_urgent_selection_never_bypasses_recent_family_cooldown(self):
        now = datetime(2026, 10, 24, 19, 0, tzinfo=timezone.utc)
        published = {
            "dkp-previous-eyewear": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "ts": (now - timedelta(minutes=15)).timestamp(),
                "telegram_message_id": 100,
                "delivery_status": {"telegram": "sent", "bale": "sent"},
            }
        }
        repeated_family = {
            "product_id": "dkp-eyewear-urgent",
            "title": "عینک آفتابی ورزشی مدل تازه",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=150)).isoformat(),
        }
        different_family_alternative = {
            "product_id": "dkp-skincare-alternative",
            "title": "کرم آبرسان صورت مدل تازه",
            "discount_percent": 35,
            "savings_toman": 150_000,
            "demand_score": 55,
        }

        chosen = select_urgent_publication_candidate(
            [repeated_family, different_family_alternative],
            now=now,
            published=published,
        )

        self.assertIsNone(chosen)

    def test_urgent_selection_prefers_available_candidate_from_different_family(self):
        now = datetime(2026, 10, 24, 19, 0, tzinfo=timezone.utc)
        published = {
            "dkp-previous-eyewear": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "ts": (now - timedelta(minutes=15)).timestamp(),
                "telegram_message_id": 100,
                "delivery_status": {"telegram": "sent", "bale": "sent"},
            }
        }
        same_family = {
            "product_id": "dkp-eyewear-urgent",
            "title": "عینک آفتابی ورزشی مدل تازه",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=150)).isoformat(),
        }
        different_family = {
            "product_id": "dkp-skincare-urgent",
            "title": "کرم آبرسان صورت مدل تازه",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=150)).isoformat(),
        }

        chosen = select_urgent_publication_candidate(
            [same_family, different_family],
            now=now,
            published=published,
        )

        self.assertEqual(chosen["product_id"], "dkp-skincare-urgent")

    def test_urgent_selection_defers_when_only_candidate_is_in_recent_family(self):
        now = datetime(2026, 10, 24, 19, 0, tzinfo=timezone.utc)
        only_choice = {
            "product_id": "dkp-eyewear-only",
            "title": "عینک آفتابی اسپرت مدل تازه",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=150)).isoformat(),
        }
        published = {
            "dkp-previous-eyewear": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "ts": (now - timedelta(minutes=15)).timestamp(),
                "telegram_message_id": 100,
            }
        }

        chosen = select_urgent_publication_candidate(
            [only_choice],
            now=now,
            published=published,
        )

        self.assertIsNone(chosen)

    def test_parse_snappshop_product_api_uses_live_vendor_stock_and_rial_prices(self):
        url = "https://snappshop.ir/product/snp-25751584"
        payload = {
            "data": {
                "id": "42yeLw",
                "content": {"title_fa": "گوشی نمونه"},
                "images": ["https://cdn.snappshop.ir/products/phone-main.webp"],
                "variants": [{
                    "variation_id": "v1",
                    "vendor": [{
                        "vendor_product_info_id": "offer-1",
                        "vendor_id": "seller-1",
                        "price": 49_000_000,
                        "special_price": 33_980_000,
                        "stock": 2,
                        "is_available_in_vendor_inventory": True,
                    }],
                }],
            }
        }
        parsed = parse_snappshop_product_api(payload, url)
        self.assertEqual(parsed["product_id"], "snp-25751584")
        self.assertEqual(parsed["current_price"], 3_398_000)
        self.assertEqual(parsed["original_price"], 4_900_000)
        self.assertEqual(parsed["availability"], "in_stock")
        self.assertIn("cdn.snappshop.ir", parsed["image_url"])
        self.assertEqual(parsed["expiry_source"], "snappshop_no_confirmed_expiry")

    def test_parse_snappshop_product_api_does_not_infer_stock_from_price_only(self):
        url = "https://snappshop.ir/product/snp-25751584"
        parsed = parse_snappshop_product_api({
            "data": {
                "id": "42yeLw",
                "content": {"title_fa": "گوشی نمونه"},
                "variants": [{"vendor": [{"price": 49_000_000, "special_price": 33_980_000}]}],
            }
        }, url)
        self.assertEqual(parsed["availability"], "unknown")
        self.assertIsNone(parsed["current_price"])
        self.assertIsNone(parsed["original_price"])

    def test_affilio_product_link_uses_only_publishers_public_template(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        linked = build_affilio_tracking_link(product)
        self.assertTrue(linked.startswith("https://aflo.ir/QekEYTRg?p="))
        self.assertEqual(
            parse_qs(urlsplit(linked).query).get("p"),
            ["https://www.digikala.com/product/dkp-1234567/"],
        )
        self.assertNotIn("{redirect_to}", linked)

    def test_legacy_migmig_template_is_rejected(self):
        product = "https://www.digikala.com/product/dkp-1234567/"
        template = "https://migmig.affilio.ir/api/v1/Click/b/media-code?b64={YOUR_BASE64_ENCODED_URL}"
        self.assertEqual(build_affilio_tracking_link(product, template), "")

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
        template = "https://aflo.ir/QekEYTRg?p={redirect_to}"
        affiliate = build_affilio_tracking_link(product, template)
        tracked = build_click_tracking_link(product, affiliate, "https://tracker.example")
        self.assertTrue(tracked.startswith("https://tracker.example/p/dkp-1234567?u="))

    def test_click_tracker_supports_channel_attribution_and_rejects_unknown_source_names(self):
        product = "https://www.digikala.com/product/dkp-15970075/"
        affiliate = build_affilio_tracking_link(product)
        telegram = build_click_tracking_link(product, affiliate, "https://tracker.example", source="telegram")
        bale = build_click_tracking_link(product, affiliate, "https://tracker.example", source="bale")
        self.assertNotEqual(telegram, bale)
        self.assertEqual(parse_qs(urlsplit(telegram).query).get("src"), ["telegram"])
        self.assertEqual(parse_qs(urlsplit(bale).query).get("src"), ["bale"])
        unsafe = build_click_tracking_link(product, affiliate, "https://tracker.example", source="unknown-user-input")
        self.assertEqual(parse_qs(urlsplit(unsafe).query).get("src"), ["unknown"])

    def test_purchase_button_always_uses_direct_affilio_url_without_tracker_probe(self):
        product = "https://snappshop.ir/product/snp-2097083854"
        affiliate = build_affilio_tracking_link(product)
        with patch(
            "affilio_radar._click_tracker_is_healthy",
            side_effect=AssertionError("purchase path must not contact the click tracker"),
        ) as health_probe:
            self.assertEqual(tracked_affiliate_button_url(affiliate, "bale"), affiliate)
            self.assertEqual(tracked_affiliate_button_url(affiliate, "telegram"), affiliate)
            health_probe.assert_not_called()
        self.assertEqual(tracked_affiliate_button_url("https://example.com/not-affiliate", "bale"), "")

    def test_click_statistics_include_aggregate_counts_for_both_stores(self):
        payload = {
            "ok": True, "complete": True, "days": 30, "totalClicks": 18,
            "products": {"dkp-15970075": 12, "snp-2097083854": 6, "bad-id": 99},
        }
        products = [
            {"product_id": "dkp-15970075", "product_url": "https://www.digikala.com/product/dkp-15970075/"},
            {"product_id": "snp-2097083854", "product_url": "https://snappshop.ir/product/snp-2097083854"},
        ]
        with patch("affilio_radar.fetch_click_statistics", return_value={"dkp-15970075": 12, "snp-2097083854": 6}):
            enrich_click_statistics(products)
        self.assertEqual(products[0]["click_count_30d"], 12)
        self.assertEqual(products[1]["click_count_30d"], 6)
        self.assertNotIn("click_counts_30d_by_source", products[0])

    def test_default_affilio_link_uses_publishers_public_link_template(self):
        product = "https://www.digikala.com/product/dkp-15970075/?old_tracking=remove"
        linked = build_affilio_tracking_link(product)
        parsed = urlsplit(linked)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "aflo.ir")
        self.assertEqual(parsed.path, "/QekEYTRg")
        self.assertEqual(params.get("p"), ["https://www.digikala.com/product/dkp-15970075/"])
        self.assertIn("p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-15970075%2F", linked)
        self.assertNotIn("old_tracking", linked)

    def test_aflo_redirect_to_template_is_encoded_and_keeps_exact_product(self):
        product = "https://www.digikala.com/product/dkp-1234567/?utm_source=should-not-leak"
        template = "https://aflo.ir/QekEYTRg?p={redirect_to}"
        linked = build_affilio_tracking_link(product, template)
        self.assertEqual(urlsplit(linked).netloc, "aflo.ir")
        self.assertEqual(urlsplit(linked).path, "/QekEYTRg")
        self.assertEqual(
            parse_qs(urlsplit(linked).query).get("p"),
            ["https://www.digikala.com/product/dkp-1234567/"],
        )
        self.assertNotIn("{redirect_to}", linked)

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
        self.assertEqual(
            build_affilio_tracking_link(product, "https://evil.example/x?p={redirect_to}"),
            "",
        )
        self.assertEqual(
            build_affilio_tracking_link(product, "https://aflo.ir/another-link?p={redirect_to}"),
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

    def test_incredible_offer_candidate_merge_preserves_deadline_from_other_node(self):
        payload = [
            {
                "id": 123,
                "title_fa": "هدفون تخفیف‌دار آزمایشی",
                "url": {"uri": "/product/dkp-123/"},
                "is_incredible": True,
                "campaign": {"ends_in_seconds": 7200},
                "default_variant": {
                    "price": {"discount_percent": 35, "selling_price_toman": 650000, "rrp_price_toman": 1000000}
                },
            },
            {
                "id": 123,
                "title_fa": "هدفون تخفیف‌دار آزمایشی",
                "url": {"uri": "/product/dkp-123/"},
                "is_incredible": True,
                "default_variant": {
                    "price": {"discount_percent": 80, "selling_price_toman": 200000, "rrp_price_toman": 1000000}
                },
            },
        ]
        rows = api_incredible_offer_product_candidates(payload, now=datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["discount_percent"], 80)
        self.assertEqual(rows[0]["deal_expires_at"], "2026-10-23T11:00:00+00:00")


    def test_product_detail_parser_marks_only_explicit_product_deadline_as_direct(self):
        now = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)
        payload = {
            "data": {"product": {
                "id": 123,
                "title_fa": "هدفون نمونه",
                "url": {"uri": "/product/dkp-123/"},
                "campaign": {"ends_at": "2026-10-23T14:30:00+03:30"},
                "default_variant": {
                    "marketable": True,
                    "price": {
                        "selling_price_toman": 650000,
                        "rrp_price_toman": 1000000,
                        "discount_percent": 35,
                    },
                },
            }}
        }
        parsed = parse_product_api(payload, "https://www.digikala.com/product/dkp-123/", now=now)
        self.assertEqual(parsed["deal_expires_at"], "2026-10-23T11:00:00+00:00")
        self.assertEqual(parsed["expiry_source"], "digikala_product_detail_api")
        self.assertTrue(parsed["expiry_deadline_verified_directly"])


    def test_verified_recent_demand_outranks_an_extreme_listed_discount(self):
        now = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
        popular_gadget = _with_verified_current_demand(score_product({
            "title": "پاوربانک محبوب",
            "current_price": 8_000_000,
            "original_price": 10_000_000,
            "rating": 4.6,
            "review_count": 50000,
            "image_url": "https://example.com/popular.jpg",
        }), now=now, growth=15)
        popular_gadget.update({"current_demand_score": 90, "demand_score": 90})
        weaker_demand_deal = _with_verified_current_demand(score_product({
            "title": "گجت کم‌نظر با تخفیف درج‌شده بیشتر",
            "current_price": 1_000_000,
            "original_price": 3_000_000,
            "rating": 4.0,
            "review_count": 100,
            "image_url": "https://example.com/deal.jpg",
        }), now=now, growth=3)
        weaker_demand_deal.update({"current_demand_score": 20, "demand_score": 20})
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
            "discount_percent": 50,
            "savings_toman": 150_000,
            "deal_expires_at": (now + timedelta(minutes=110)).isoformat(),
        }
        self.assertTrue(is_deadline_critical_deal(close_but_safe, now))
        too_far = {**close_but_safe, "deal_expires_at": (now + timedelta(minutes=121)).isoformat()}
        self.assertFalse(is_deadline_critical_deal(too_far, now))
        too_soon = {**close_but_safe, "deal_expires_at": (now + timedelta(minutes=45)).isoformat()}
        self.assertFalse(is_deadline_critical_deal(too_soon, now))
        self.assertFalse(is_deadline_critical_deal({**close_but_safe, "deal_expires_at": ""}, now))

    def test_regular_and_sport_eyewear_share_one_global_family(self):
        regular_category, regular_family, _ = radar_module._publication_diversity_group(
            "عینک آفتابی زنانه مدل معمولی"
        )
        sport_category, sport_family, _ = radar_module._publication_diversity_group(
            "عینک آفتابی ورزشی مدل اسپرت"
        )

        self.assertNotEqual(regular_category, sport_category)
        self.assertEqual(regular_family, "fashion:eyewear")
        self.assertEqual(sport_family, regular_family)


    def test_category_classifier_recognizes_everyday_merchandise(self):
        self.assertEqual(classify_category("تیشرت یقه گرد مردانه ایزی دو"), "fashion")
        self.assertEqual(classify_category("کتاب جوجوتسو کایسن سه جلدی"), "books_stationery")
        self.assertEqual(classify_category("گوشواره نقره زنانه پرسته"), "jewelry")
        self.assertEqual(classify_category("عطر زنانه مدل نمونه"), "beauty_fragrance")
        self.assertEqual(classify_category("ادو تویلت مردانه فالکون مدل Chromium حجم 100 میلی لیتر"), "beauty_fragrance")
        self.assertEqual(classify_category("هدفون بلوتوثی مدل نمونه"), "audio_wearables")
        self.assertEqual(classify_category("گوشی موبایل سامسونگ مدل Galaxy نمونه"), "mobile_devices")
        self.assertEqual(classify_category("لپ تاپ گیمینگ مدل نمونه"), "computer_network")
        self.assertEqual(classify_category("تلویزیون هوشمند ۵۵ اینچ مدل نمونه"), "tv_audio_video")
        self.assertEqual(classify_category("یخچال فریزر مدل نمونه"), "large_appliances")
        self.assertEqual(classify_category("باتری قلمی قابل شارژ"), "power_backup")
        self.assertEqual(classify_category("بادی نوزادی نیل کوک مدل Winter Teddy مجموعه 5 عددی"), "kids_sports")
        self.assertEqual(classify_category("سنگ پا برقی مدل M100"), "personal_care")
        self.assertEqual(classify_category("پولوشرت آستین کوتاه مردانه مدل نمونه"), "fashion")
        self.assertEqual(classify_category("چراغ پیشانی شارژی مدل نمونه"), "lighting")
        self.assertEqual(classify_category("غذای گربه مدل نمونه"), "pet_supplies")
        self.assertEqual(classify_category("جارو شارژی مدل نمونه"), "home_cleaning")
        self.assertEqual(classify_category("بازی فکری کودک مدل نمونه"), "kids_sports")
        self.assertEqual(classify_category("توپ فوتبال مدل نمونه"), "sports_outdoor")
        self.assertEqual(classify_category("لیزر پوینتر ارائه مدل نمونه"), "presentation_tools")
        self.assertEqual(classify_category("لوازم نقاشی و طراحی مدل نمونه"), "arts_crafts")

    def test_discovery_budget_protects_rotating_category_search_slots(self):
        self.assertEqual(_discovery_candidate_budgets(60), (40, 20))
        self.assertEqual(_discovery_candidate_budgets(40), (27, 13))
        self.assertEqual(_discovery_candidate_budgets(12), (8, 4))
        self.assertEqual(_discovery_candidate_budgets(1), (1, 0))
        self.assertEqual(len(SEARCH_TERMS), 90)
        for term in (
            "گوشی موبایل", "گوشی سامسونگ و شیائومی", "آیفون اپل", "لپ تاپ",
            "لپ تاپ گیمینگ", "تبلت و آیپد", "کارت گرافیک و پردازنده",
            "تلویزیون هوشمند", "یخچال فریزر", "ماشین لباسشویی",
            "ماشین ظرفشویی", "سرخ کن بدون روغن", "لوازم حیوانات خانگی",
            "ابزار دستی و ابزارآلات", "لوازم نظافت و شستشوی خانه",
            "چراغ مطالعه و لوازم روشنایی", "لوازم هنری و نقاشی",
            "لوازم مراقبت و نگهداری خودرو", "لوازم حمام و سرویس بهداشتی",
            "لوازم باغبانی و گلدان", "مواد غذایی و خواربار", "چای و دمنوش",
            "آجیل و خشکبار", "فرش و قالیچه", "چمدان و ساک مسافرتی",
            "لوازم موسیقی و ساز", "دوربین مداربسته", "لوازم ماهیگیری",
            "لاستیک خودرو", "گیاه آپارتمانی و گلدان",
        ):
            self.assertIn(term, SEARCH_TERMS)

    def test_snappshop_source_backoff_is_bounded_and_exponential(self):
        self.assertEqual(_snappshop_retry_cooldown_minutes(0), 360)
        self.assertEqual(_snappshop_retry_cooldown_minutes(1), 360)
        self.assertEqual(_snappshop_retry_cooldown_minutes(2), 720)
        self.assertEqual(_snappshop_retry_cooldown_minutes(3), 1440)
        self.assertEqual(_snappshop_retry_cooldown_minutes(20), 1440)


    def test_unavailable_optional_retailer_releases_its_reserved_discovery_budget(self):
        # At 90 checks, 70 slots are available before category-search slots.
        # Hold 12 provisionally, then return every unused slot to DigiKala.
        self.assertEqual(_discovery_early_source_candidate_limit(70, 12, 0), 58)
        self.assertEqual(_discovery_early_source_candidate_limit(70, 12, 4), 62)
        self.assertEqual(_discovery_early_source_candidate_limit(70, 12, 12), 70)
        self.assertEqual(_discovery_early_source_candidate_limit(40, 0, 0), 40)


    def test_rotating_search_batches_cover_all_terms_without_one_term_per_scan(self):
        batch_size = 12
        batch_count = (len(SEARCH_TERMS) + batch_size - 1) // batch_size
        batches = [_rotating_search_terms(slot, batch_size)[:batch_size] for slot in range(batch_count)]
        for slot, batch in enumerate(batches):
            offset = slot * batch_size
            expected = (SEARCH_TERMS[offset:] + SEARCH_TERMS[:offset])[:batch_size]
            self.assertEqual(batch, expected)
        self.assertEqual({term for batch in batches for term in batch}, set(SEARCH_TERMS))
        snapp_batch_size = 4
        snapp_batch_count = (len(SEARCH_TERMS) + snapp_batch_size - 1) // snapp_batch_size
        snapp_batches = [
            _rotating_search_terms(slot, snapp_batch_size)[:snapp_batch_size]
            for slot in range(snapp_batch_count)
        ]
        self.assertEqual({term for batch in snapp_batches for term in batch}, set(SEARCH_TERMS))

    def test_calcium_and_arginine_supplements_are_excluded(self):
        self.assertTrue(is_prohibited_product_title("شربت کلسی کید جویس یوروویتال"))
        self.assertTrue(is_prohibited_product_title("شربت ال آرژنین پلاس فیشر کیندر"))
        self.assertTrue(is_prohibited_product_title("مکمل کلسیم کودکان"))

    def test_publish_selection_softly_reorders_repetitive_categories_for_diversity(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        published = {}
        for index in range(6):
            published[f"dkp-old-audio-{index}"] = {
                "title": f"هدفون بلوتوثی موزیک آپولو مدل {index}",
                "telegram_message_id": 100 + index,
                "ts": now.timestamp() - (60 * (6 - index)),
            }
        for index in range(3):
            published[f"dkp-old-power-{index}"] = {
                "title": f"شارژر سریع وونک مدل {index}",
                "telegram_message_id": 200 + index,
                "ts": now.timestamp() - (60 * (3 - index)),
            }
        candidates = [
            {"product_id": "dkp-audio-new", "title": "هدفون بلوتوثی موزیک آپولو مدل جدید"},
            {"product_id": "dkp-audio-2", "title": "هدفون بلوتوثی ریولینک مدل جدید"},
            {"product_id": "dkp-power-new", "title": "باتری قلمی قابل شارژ"},
            {"product_id": "dkp-fashion-new", "title": "تیشرت یقه گرد مردانه مدل جدید"},
        ]
        queue = {p["product_id"]: {} for p in candidates}
        eligible = {p["product_id"]: p for p in candidates}
        selected = select_publish_candidates(queue, eligible, now, published)
        self.assertEqual(selected[0]["product_id"], "dkp-fashion-new")
        self.assertEqual(
            {p["product_id"] for p in selected},
            {"dkp-power-new", "dkp-fashion-new"},
        )


    def test_publication_diversity_history_uses_a_rolling_24_hour_window(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-old-fashion": {
                "title": "تیشرت مردانه مدل قدیمی",
                "telegram_message_id": 701,
                "ts": (now - timedelta(hours=25)).timestamp(),
            },
            "dkp-in-window": {
                "title": "هدفون بلوتوثی مدل تازه",
                "telegram_message_id": 702,
                "ts": (now - timedelta(hours=23)).timestamp(),
            },
        }
        recent = _recent_publication_diversity(published, limit=2000, now=now)
        self.assertEqual([item["product_id"] for item in recent], ["dkp-in-window"])

    def test_discovery_selection_skips_recent_eyewear_family_and_uses_other_category(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        recent = [{
            "product_id": "dkp-old-eyewear",
            "title": "عینک آفتابی مردانه مدل قدیمی",
            "ts": (now - timedelta(minutes=20)).timestamp(),
        }]
        candidates = [
            {"product_id": "dkp-new-eyewear", "title": "عینک طبی زنانه مدل جدید", "demand_score": 90},
            {"product_id": "dkp-new-charger", "title": "شارژر سریع دیواری مدل جدید", "demand_score": 55},
        ]

        selected = _diversify_ranked_records(
            candidates, limit=2, published={}, recent_publications=recent, now=now,
        )

        self.assertEqual([row["product_id"] for row in selected], ["dkp-new-charger"])

    def test_publish_selection_does_not_fallback_to_recent_eyewear_family(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-old-eyewear": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "telegram_message_id": 1501,
                "ts": (now - timedelta(minutes=20)).timestamp(),
            }
        }
        candidates = [
            {"product_id": "dkp-eyewear-repeat", "title": "عینک طبی مردانه مدل جدید", "demand_score": 90},
            {"product_id": "dkp-new-charger", "title": "شارژر سریع دیواری مدل جدید", "demand_score": 55},
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual([item["product_id"] for item in selected], ["dkp-new-charger"])

    def test_recent_similar_product_family_is_spaced_when_demand_is_comparable(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-headphones": {
                "title": "هدفون بلوتوثی ریولینک مدل قبلی",
                "telegram_message_id": 811,
                "ts": (now - timedelta(hours=2)).timestamp(),
            }
        }
        candidates = [
            {
                "product_id": "dkp-headphones-new",
                "title": "هدفون بلوتوثی ریولینک مدل جدید",
                "click_count_30d": 100, "demand_score": 60, "review_count": 500,
            },
            {
                "product_id": "dkp-desk-light",
                "title": "چراغ مطالعه رومیزی مدل جدید",
                "click_count_30d": 98, "demand_score": 59, "review_count": 480,
            },
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}
        selected = select_publish_candidates(queue, eligible, now, published)
        # A matching family inside the four-hour cooldown is not publishable yet.
        self.assertEqual([row["product_id"] for row in selected], ["dkp-desk-light"])


    def test_publish_selection_avoids_categories_seen_in_the_last_four_posts(self):
        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        recent_posts = [
            ("dkp-recent-fashion", "تیشرت مردانه مدل نمونه", 4),
            ("dkp-recent-home", "باکس نظم دهنده مدل نمونه", 3),
            ("dkp-recent-audio", "هدفون بلوتوثی مدل نمونه", 2),
            ("dkp-recent-power", "شارژر سریع مدل نمونه", 1),
        ]
        published = {
            product_id: {
                "title": title,
                "telegram_message_id": 900 + index,
                "ts": now.timestamp() - minutes * 60,
            }
            for index, (product_id, title, minutes) in enumerate(recent_posts)
        }
        candidates = [
            {"product_id": "dkp-audio-new", "title": "هدفون بلوتوثی مدل تازه"},
            {"product_id": "dkp-fragrance-new", "title": "ادوپرفیوم زنانه مدل تازه"},
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual([item["product_id"] for item in selected], ["dkp-fragrance-new"])


    def test_publish_selection_skips_recent_specific_family_even_when_its_demand_is_higher(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-skincare": {
                "title": "سرم آبرسان پوست مدل قبلی",
                "telegram_message_id": 889,
                "ts": now.timestamp() - 10 * 60,
            }
        }
        candidates = [
            {
                "product_id": f"dkp-skincare-{index}",
                "title": f"کرم مراقبت پوست مدل {index}",
                "demand_score": score,
                "review_count": 500,
            }
            for index, score in enumerate((64, 63, 62, 61, 60, 59), start=1)
        ]
        # The alternate category is valid, but its much weaker market demand must not win.
        candidates.append({
            "product_id": "dkp-diverse-charger",
            "title": "شارژر دیواری سریع مدل جدید",
            "demand_score": 40,
            "review_count": 450,
        })
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual([item["product_id"] for item in selected], ["dkp-diverse-charger"])


    def test_publish_selection_accepts_diversity_within_75_percent_demand_band(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-skincare": {
                "title": "سرم آبرسان پوست مدل قبلی",
                "telegram_message_id": 990,
                "ts": now.timestamp() - 10 * 60,
            }
        }
        candidates = [
            {
                "product_id": "dkp-skincare-top",
                "title": "کرم مراقبت پوست مدل برتر",
                "demand_score": 64,
                "review_count": 500,
            },
            {
                "product_id": "dkp-power-comparable",
                "title": "شارژر دیواری سریع مدل تازه",
                "demand_score": 49,
                "review_count": 450,
            },
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual(selected[0]["product_id"], "dkp-power-comparable")
        self.assertEqual([item["product_id"] for item in selected], ["dkp-power-comparable"])


    def test_publish_selection_balances_retailers_when_comparable_products_exist(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-skincare": {
                "title": "سرم آبرسان پوست مدل قبلی",
                "telegram_message_id": 995,
                "ts": now.timestamp() - 10 * 60,
            }
        }
        candidates = [
            {
                "product_id": "dkp-book-comparable",
                "title": "کتاب داستان نوجوان چاپ جدید",
                "demand_score": 60,
                "review_count": 500,
            },
            {
                "product_id": "snp-book-comparable",
                "title": "کتاب داستان نوجوان چاپ تازه",
                "demand_score": 58,
                "review_count": 480,
            },
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual(selected[0]["product_id"], "snp-book-comparable")
        self.assertEqual({item["product_id"] for item in selected}, {item["product_id"] for item in candidates})


    def test_publish_selection_prioritizes_underrepresented_category_for_close_demand(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-skincare": {
                "title": "سرم آبرسان پوست مدل قبلی",
                "telegram_message_id": 991,
                "ts": now.timestamp() - 10 * 60,
            }
        }
        candidates = [
            {
                "product_id": "dkp-skincare-close",
                "title": "کرم مراقبت پوست مدل جدید",
                "demand_score": 64,
                "click_count_30d": 100,
                "discount_percent": 60,
                "review_count": 500,
            },
            {
                "product_id": "dkp-power-close",
                "title": "شارژر دیواری سریع مدل جدید",
                "demand_score": 60,
                "click_count_30d": 98,
                "discount_percent": 58,
                "review_count": 480,
            },
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertEqual(selected[0]["product_id"], "dkp-power-close")


    def test_publish_lookahead_checks_beyond_first_48_candidates(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-recent-apparel": {
                "title": "تیشرت مردانه مدل قبلی",
                "telegram_message_id": 1510,
                "ts": (now - timedelta(minutes=20)).timestamp(),
            }
        }
        candidates = [
            {
                "product_id": f"dkp-eyewear-{index}",
                "title": f"عینک آفتابی مدل {index}",
                "demand_score": 90,
                "click_count_30d": 1000,
                "discount_percent": 60,
                "review_count": 1000,
            }
            for index in range(49)
        ]
        candidates.append({
            "product_id": "dkp-late-fragrance",
            "title": "ادوپرفیوم زنانه مدل تازه",
            "demand_score": 75,
            "click_count_30d": 900,
            "discount_percent": 55,
            "review_count": 900,
        })
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(queue, eligible, now, published)

        self.assertTrue(selected)
        self.assertEqual(selected[0]["product_id"], "dkp-late-fragrance")


    def test_single_repeated_category_candidate_is_recorded_as_diversity_fallback(self):
        now = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)
        published = {
            "dkp-old-audio": {
                "title": "هدفون بلوتوثی مدل قبلی",
                "telegram_message_id": 1201,
                "ts": now.timestamp() - 60,
            }
        }
        candidate = {
            "product_id": "dkp-only-audio",
            "title": "اسپیکر بلوتوثی مدل فعلی",
            "demand_score": 60,
            "discount_percent": 55,
            "review_count": 500,
        }
        selected = select_publish_candidates(
            {candidate["product_id"]: {}},
            {candidate["product_id"]: candidate},
            now,
            published,
        )
        diagnostics = radar_module._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS

        self.assertEqual([row["product_id"] for row in selected], ["dkp-only-audio"])
        self.assertEqual(len(diagnostics["fallback_events"]), 1)
        self.assertEqual(diagnostics["fallback_events"][0]["category"], "audio_wearables")
        self.assertEqual(
            diagnostics["fallback_events"][0]["reason"],
            "no_comparable_other_category_in_lookahead",
        )


    def test_publication_diversity_report_measures_category_share_brand_repeats_and_fallbacks(self):
        now = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)
        history = [
            {
                "product_id": "dkp-audio-1",
                "title": "هدفون بلوتوثی موزیک آپولو مدل یک",
                "telegram_message_id": 1101,
                "ts": now.timestamp() - 60,
            },
            {
                "product_id": "dkp-audio-2",
                "title": "هدفون بلوتوثی موزیک آپولو مدل دو",
                "telegram_message_id": 1102,
                "ts": now.timestamp() - 120,
            },
            {
                "product_id": "dkp-fashion-1",
                "title": "تیشرت یقه گرد مردانه مدل سه",
                "telegram_message_id": 1103,
                "ts": now.timestamp() - 180,
            },
        ]
        fallback_history = [
            {
                "at": (now - timedelta(hours=2)).isoformat(),
                "category": "audio_wearables",
                "family": "audio_wearables:headphones",
                "reason": "no_comparable_other_category_in_lookahead",
            }
        ]
        report = build_publication_diversity_report(
            published={},
            recent_publications=history,
            now=now,
            fallback_events=fallback_history,
            fallback_total=4,
        )

        day = report["last_24_hours"]
        self.assertEqual(day["posts"], 3)
        self.assertEqual(day["distinct_categories"], 2)
        self.assertEqual(day["distinct_families"], 2)
        self.assertEqual(day["category_post_counts"]["audio_wearables"], 2)
        self.assertEqual(day["category_share_percent"]["audio_wearables"], 66.7)
        self.assertEqual(day["category_share_percent"]["fashion"], 33.3)
        self.assertEqual(day["repeated_brand_count"], 1)
        self.assertEqual(day["repeated_brands"], {"muzik_apollo": 2})
        self.assertEqual(report["fallbacks"]["all_time_count"], 4)
        self.assertEqual(report["fallbacks"]["last_7_days_count"], 1)


    def test_publish_selection_avoids_a_brand_seen_twelve_publications_ago(self):
        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        recent_titles = [
            "باتری قلمی قابل شارژ موزیک آپولو مدل قدیمی",
            "کفش چرم زنانه مدل نمونه",
            "فلاسک استیل مدل نمونه",
            "گوشواره نقره زنانه پرسته مدل نمونه",
            "بادی نوزادی نیل کوک مدل نمونه",
            "ادوپرفیوم زنانه مدل نمونه",
            "کتاب داستان نوجوان مدل نمونه",
            "قاب گوشی مدل نمونه",
            "چراغ مطالعه رومیزی مدل نمونه",
            "عینک آفتابی مدل نمونه",
            "قمقمه ورزشی مدل نمونه",
            "تیشرت زنانه مدل نمونه",
        ]
        recent_publications = [
            {
                "product_id": f"dkp-history-{index}",
                "title": title,
                "ts": now.timestamp() - (60 * (len(recent_titles) - index)),
            }
            for index, title in enumerate(recent_titles)
        ]
        candidates = [
            {"product_id": "dkp-muzik-audio-repeat", "title": "هدفون بلوتوثی موزیک آپولو مدل تازه"},
            {"product_id": "dkp-speaker-new-family", "title": "اسپیکر بلوتوثی مدل تازه"},
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}
        selected = select_publish_candidates(
            queue, eligible, now, published={}, recent_publications=recent_publications
        )
        self.assertEqual(selected[0]["product_id"], "dkp-speaker-new-family")
        self.assertEqual({item["product_id"] for item in selected}, {item["product_id"] for item in candidates})


    def test_publish_selection_uses_durable_history_after_channel_posts_are_deleted(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        recent_publications = [
            {
                "product_id": f"dkp-old-audio-{index}",
                "title": f"هدفون بلوتوثی موزیک آپولو مدل {index}",
                "ts": now.timestamp() - (60 * (6 - index)),
            }
            for index in range(6)
        ]
        candidates = [
            {"product_id": "dkp-audio-new", "title": "هدفون بلوتوثی موزیک آپولو مدل جدید"},
            {"product_id": "dkp-power-new", "title": "باتری قلمی قابل شارژ"},
            {"product_id": "dkp-fashion-new", "title": "تیشرت یقه گرد مردانه مدل جدید"},
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}

        selected = select_publish_candidates(
            queue, eligible, now, published={}, recent_publications=recent_publications
        )

        # The leading choice must leave the overrepresented audio family;
        # either of the other categories is a valid diversity improvement.
        self.assertNotEqual(selected[0]["product_id"], "dkp-audio-new")
        self.assertEqual(
            {item["product_id"] for item in selected},
            {"dkp-power-new", "dkp-fashion-new"},
        )


    def test_recent_publication_diversity_deduplicates_same_message_ids_across_timestamps(self):
        first_at = datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc).timestamp()
        history = [
            {
                "ts": first_at,
                "product_id": "dkp-same-post",
                "title": "هدفون بلوتوثی مدل تست",
                "telegram_message_id": 681,
                "bale_message_id": 835,
            },
            {
                # A maintenance/countdown snapshot changed ts but not the actual messages.
                "ts": first_at + 600,
                "product_id": "dkp-same-post",
                "title": "هدفون بلوتوثی مدل تست",
                "telegram_message_id": 681,
                "bale_message_id": 835,
            },
            {
                "ts": first_at + 1200,
                "product_id": "dkp-different-post",
                "title": "چراغ مطالعه رومیزی مدل تست",
                "telegram_message_id": 682,
                "bale_message_id": 836,
            },
        ]

        recent = _recent_publication_diversity(
            published={}, limit=10, durable_history=history
        )

        self.assertEqual(len(recent), 2)
        same_post = next(item for item in recent if item["product_id"] == "dkp-same-post")
        self.assertEqual(same_post["order"], first_at)
        self.assertEqual(same_post["telegram_message_id"], 681)
        self.assertEqual(same_post["bale_message_id"], 835)

    def test_ensure_recent_publications_normalizes_same_message_history(self):
        first_at = datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc).timestamp()
        state = {
            "recent_publications": [
                {
                    "ts": first_at,
                    "product_id": "dkp-same-post",
                    "title": "هدفون بلوتوثی مدل تست",
                    "telegram_message_id": 681,
                    "bale_message_id": 835,
                },
                {
                    "ts": first_at + 600,
                    "product_id": "dkp-same-post",
                    "title": "هدفون بلوتوثی مدل تست",
                    "telegram_message_id": 681,
                    "bale_message_id": 835,
                },
                {
                    "ts": first_at + 1200,
                    "product_id": "dkp-different-post",
                    "title": "چراغ مطالعه رومیزی مدل تست",
                    "telegram_message_id": 682,
                    "bale_message_id": 836,
                },
            ],
            "publication_ledger": {},
            "published": {},
        }

        self.assertTrue(ensure_recent_publications(state))
        history = state["recent_publications"]
        self.assertEqual(len(history), 2)
        same_post = next(item for item in history if item["product_id"] == "dkp-same-post")
        self.assertEqual(same_post["ts"], first_at)

    def test_repeat_product_requires_real_price_drop_to_bypass_product_cooldown(self):
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
        self.assertFalse(is_materially_improved_offer(previous, same_price_new_campaign, now))
        self.assertTrue(is_materially_improved_offer({**previous, "expires_at": (now + timedelta(hours=2)).isoformat()}, materially_cheaper, now))
        self.assertFalse(is_materially_improved_offer({**previous, "expires_at": (now + timedelta(hours=2)).isoformat()}, unchanged, now))

    def test_active_publications_and_delivery_retries_do_not_block_fresh_selection(self):
        now = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
        future_deadline = (now + timedelta(hours=5)).isoformat()
        active = {
            "product_id": "dkp-1001",
            "product_url": "https://www.digikala.com/product/dkp-1001/",
            "title": "محصول منتشرشده",
            "current_price": 800_000,
            "original_price": 1_000_000,
            "discount_percent": 20,
            "deal_expires_at": future_deadline,
        }
        queue_retry = {
            "product_id": "dkp-1002",
            "product_url": "https://www.digikala.com/product/dkp-1002/",
            "title": "محصول در صف ویدئو",
            "current_price": 700_000,
            "original_price": 1_000_000,
            "discount_percent": 30,
            "deal_expires_at": future_deadline,
        }
        fresh = {
            "product_id": "dkp-1003",
            "product_url": "https://www.digikala.com/product/dkp-1003/",
            "title": "محصول تازه",
            "current_price": 600_000,
            "original_price": 1_000_000,
            "discount_percent": 40,
            "deal_expires_at": future_deadline,
        }
        state = {
            "published": {
                "dkp-1001": {
                    "ts": now.timestamp() - 2 * 86400,
                    "title": active["title"],
                    "posted_current_price": 1_000_000,
                    "telegram_message_id": 101,
                    "bale_message_id": 201,
                    "expiry_status": "tracked",
                    "bale_expiry_status": "tracked",
                    "delivery_status": {"telegram": "sent", "bale": "sent"},
                },
            },
            "content_delivery_queue": {
                "dkp-1002": {
                    "product_id": "dkp-1002",
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "sent"},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "pending"},
                    },
                },
            },
        }

        # Even a 20% better price must not create a duplicate while the previous
        # Telegram/Bale post is still live. A queued video retry is not new content.
        self.assertFalse(is_fresh_selection_candidate(state, "dkp-1001", active, now))
        self.assertFalse(is_fresh_selection_candidate(state, "dkp-1002", queue_retry, now))
        self.assertTrue(is_fresh_selection_candidate(state, "dkp-1003", fresh, now))

        pending = refresh_pending_queue(
            state,
            [active, queue_retry, fresh],
            now,
            observed_product_ids={"dkp-1001", "dkp-1002", "dkp-1003"},
        )
        self.assertEqual(set(pending), {"dkp-1003"})


    def test_same_product_is_blocked_for_24_hours_even_when_price_improves(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        previous = {
            "ts": now.timestamp() - 300,
            "title": "ژل آبرسان نمونه",
            "posted_current_price": 1_000_000,
        }
        cheaper = {"current_price": 800_000}
        self.assertTrue(is_product_repeat_blocked(previous, cheaper, now))

        older = {**previous, "ts": now.timestamp() - 25 * 3600}
        self.assertFalse(is_product_repeat_blocked(older, cheaper, now))
        self.assertTrue(is_product_repeat_blocked(older, {"current_price": 1_000_000}, now))

    def test_publication_ledger_keeps_cooldown_if_published_record_is_lost(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        state = {
            "published": {
                "dkp-123": {
                    "ts": now.timestamp() - 5 * 60,
                    "title": "ژل آبرسان نمونه",
                    "product_url": "https://www.digikala.com/product/dkp-123/",
                    "posted_current_price": 290_000,
                    "posted_original_price": 1_450_000,
                    "posted_discount_percent": 80,
                    "telegram_message_id": 496,
                    "bale_message_id": 594,
                    "expiry_status": "deleted",
                    "bale_expiry_status": "deleted",
                }
            },
            "pending_queue": {},
        }
        self.assertTrue(ensure_publication_ledger(state))
        state["published"].pop("dkp-123")
        candidate = {
            "product_id": "dkp-123",
            "product_url": "https://www.digikala.com/product/dkp-123/",
            "title": "ژل آبرسان نمونه",
            "deal_expires_at": (now + timedelta(hours=8)).isoformat(),
            "current_price": 290_000,
            "original_price": 1_450_000,
            "discount_percent": 80,
            "savings_toman": 1_160_000,
            "demand_score": 60,
            "promo_score": 50,
        }
        queue = refresh_pending_queue(
            state, [candidate], now, observed_product_ids={"dkp-123"}
        )
        self.assertNotIn("dkp-123", queue)
        self.assertIn("dkp-123", state["publication_ledger"])

    def test_channel_cleanup_preserves_product_record_and_last_post_cooldown(self):
        now = datetime.now(timezone.utc)
        record = {
            "ts": now.timestamp() - 60,
            "title": "ژل آبرسان نمونه",
            "product_url": "https://www.digikala.com/product/dkp-123/",
            "posted_current_price": 290_000,
            "telegram_message_id": 496,
            "bale_message_id": 594,
            "expiry_status": "tracked",
        }
        state = {
            "published": {"dkp-123": record},
            "last_published_at": now.isoformat(),
        }
        mock_response = SimpleNamespace(ok=True, status_code=200, json=lambda: {"ok": True})
        with (
            patch("affilio_radar.BOT_TOKEN", "test-token"),
            patch("affilio_radar._discover_public_channel_message_ids", return_value={496}),
            patch("affilio_radar.requests.post", return_value=mock_response),
            patch("affilio_radar.time.sleep"),
            patch("affilio_radar.save_json"),
        ):
            delete_previous_channel_posts(state)
        self.assertIn("dkp-123", state["published"])
        self.assertEqual(state["published"]["dkp-123"]["expiry_status"], "deleted")
        self.assertEqual(state["published"]["dkp-123"]["bale_message_id"], 594)
        self.assertTrue(state["last_published_at"])
        self.assertIn("dkp-123", state["publication_ledger"])

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

    def test_high_demand_offer_outranks_shorter_deadline_offer(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        near_but_lower_demand = {
            "discount_percent": 35, "savings_toman": 150_000,
            "demand_score": 40, "promo_score": 25,
            "deal_expires_at": (now + timedelta(minutes=70)).isoformat(),
        }
        popular_with_more_time = {
            "discount_percent": 90, "savings_toman": 2_000_000,
            "demand_score": 95, "promo_score": 90,
            "deal_expires_at": (now + timedelta(hours=3)).isoformat(),
        }
        self.assertGreater(
            pending_queue_sort_key(popular_with_more_time, {"first_seen_at": now.isoformat()}, now),
            pending_queue_sort_key(near_but_lower_demand, {"first_seen_at": now.isoformat()}, now),
        )

    def test_deadline_urgency_is_only_a_tiebreaker_after_demand_and_deal_value(self):
        now = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
        urgent_but_less_popular = {
            "product_id": "dkp-123",
            "discount_percent": 82,
            "savings_toman": 600_000,
            "demand_score": 58,
            "deal_expires_at": (now + timedelta(minutes=90)).isoformat(),
        }
        popular_and_valid = {
            "product_id": "dkp-456",
            "discount_percent": 50,
            "savings_toman": 300_000,
            "demand_score": 80,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
        }
        self.assertTrue(is_urgent_priority_deal(urgent_but_less_popular, now))
        self.assertGreater(
            pending_queue_sort_key(popular_and_valid, {"first_seen_at": now.isoformat()}, now),
            pending_queue_sort_key(urgent_but_less_popular, {"first_seen_at": now.isoformat()}, now),
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

    def test_discount_publishing_requires_a_valuable_deal(self):
        base = {
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 900_000,
            "original_price": 1_000_000,
            "image_url": "https://example.com/image.jpg",
            "affiliate_url": "https://www.digikala.com/product/dkp-1234567/?utm_source=19166",
        }
        ten_percent = score_product(dict(base))
        self.assertEqual(ten_percent["discount_percent"], 10)
        self.assertFalse(is_discount_publish_eligible(ten_percent))

        just_below_floor = score_product({**base, "current_price": 510_000})
        self.assertEqual(just_below_floor["discount_percent"], 49)
        self.assertFalse(is_discount_publish_eligible(just_below_floor))

        strong_discount = _with_verified_current_demand(
            score_product({**base, "current_price": 500_000})
        )
        self.assertEqual(strong_discount["discount_percent"], 50)
        self.assertGreaterEqual(strong_discount["savings_toman"], 100_000)
        self.assertTrue(is_discount_publish_eligible(strong_discount))

        small_saving = score_product({**base, "current_price": 990_000})
        self.assertEqual(small_saving["discount_percent"], 1)
        self.assertFalse(is_discount_publish_eligible(small_saving))
        no_real_drop = score_product({**base, "current_price": 1_000_000})
        self.assertFalse(is_discount_publish_eligible(no_real_drop))
        missing_stock = dict(strong_discount, availability="unknown")
        self.assertFalse(is_discount_publish_eligible(missing_stock))


    def test_high_ticket_products_have_no_discount_floor_exception(self):
        high_ticket_11_percent = score_product({
            "title": "گوشی موبایل پرتقاضا مدل آزمایشی",
            "availability": "in_stock",
            "current_price": 16_000_000,
            "original_price": 18_000_000,
            "rating": 4.7,
            "review_count": 20_000,
            "image_url": "https://example.com/phone.jpg",
            "affiliate_url": "https://www.digikala.com/product/dkp-1234567/?utm_source=19166",
        })
        self.assertEqual(high_ticket_11_percent["discount_percent"], 11)
        self.assertEqual(high_ticket_11_percent["savings_toman"], 2_000_000)
        self.assertFalse(is_discount_publish_eligible(high_ticket_11_percent))

        high_ticket_50_percent = _with_verified_current_demand(
            score_product({
                **high_ticket_11_percent,
                "current_price": 9_000_000,
                "original_price": 18_000_000,
            })
        )
        self.assertEqual(high_ticket_50_percent["discount_percent"], 50)
        self.assertGreaterEqual(high_ticket_50_percent["savings_toman"], 100_000)
        self.assertTrue(is_discount_publish_eligible(high_ticket_50_percent))

    def test_discount_fallback_ladder_prefers_50_then_45_40_and_35_percent(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

        def product(pid, title, discount, demand):
            current_price = 1_000_000
            original_price = int(round(current_price / (1 - discount / 100)))
            return _with_verified_current_demand({
                "product_id": pid,
                "title": title,
                "availability": "in_stock",
                "availability_source": "digikala_api",
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount,
                "savings_toman": original_price - current_price,
                "image_url": "https://example.com/product.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2F" + pid + "%2F",
                "has_affiliate_link": True,
                "demand_score": demand,
                "review_count": 1000,
                "rating": 4.5,
                "deal_expires_at": "",
                "expiry_source": "unavailable",
            }, now)

        candidates = [
            product("dkp-95001", "هدفون بلوتوثی مدل برتر", 50, 55),
            product("dkp-95002", "شارژر سریع مدل پرفروش", 45, 99),
            product("dkp-95003", "کوله پشتی مسافرتی مدل تازه", 44, 80),
            product("dkp-95004", "ماوس بی سیم مدل کاربردی", 40, 70),
            product("dkp-95005", "اسپیکر بلوتوثی مدل کوچک", 35, 65),
            product("dkp-95006", "چراغ مطالعه شارژی مدل جدید", 34, 99),
        ]
        selected, floor, quality = radar_module.select_discount_fallback_candidates(
            candidates, {"published": {}}, now
        )
        self.assertEqual(floor, 50)
        self.assertEqual(selected[0]["selection_discount_floor"], 50)
        self.assertEqual([item["product_id"] for item in selected], ["dkp-95001"])
        self.assertEqual(
            {item["product_id"] for item in quality},
            {"dkp-95001", "dkp-95002", "dkp-95003", "dkp-95004", "dkp-95005"},
        )

        # The hand-off carries all backups with their own strict floor.
        backup_pool, backup_floor, _ = radar_module.select_discount_fallback_candidates(
            candidates, {"published": {}}, now, include_fallback_bands=True
        )
        self.assertEqual(backup_floor, 50)
        self.assertEqual(
            [(item["product_id"], item["selection_discount_floor"]) for item in backup_pool],
            [
                ("dkp-95001", 50),
                ("dkp-95002", 45),
                ("dkp-95003", 40),
                ("dkp-95004", 40),
                ("dkp-95005", 35),
            ],
        )

    def test_publish_ranking_keeps_higher_discount_tier_ahead_of_stronger_lower_tier_demand(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        preferred = {
            "product_id": "dkp-95110", "title": "هدفون بلوتوثی مدل اول",
            "selection_discount_floor": 50, "discount_percent": 50, "demand_score": 55,
        }
        fallback = {
            "product_id": "dkp-95111", "title": "شارژر سریع مدل دوم",
            "selection_discount_floor": 45, "discount_percent": 45, "demand_score": 99,
        }
        ranked = radar_module.select_publish_candidates(
            {"dkp-95110": {}, "dkp-95111": {}},
            {"dkp-95110": preferred, "dkp-95111": fallback},
            now,
        )
        self.assertEqual(
            [item["product_id"] for item in ranked],
            ["dkp-95110", "dkp-95111"],
        )

    def test_49_percent_candidate_uses_45_percent_band_when_no_50_percent_offer_exists(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        price = 1_000_000
        original = 1_960_784
        candidate = _with_verified_current_demand({
            "product_id": "dkp-95004",
            "title": "شارژر سریع دیواری مدل پرفروش",
            "availability": "in_stock",
            "availability_source": "digikala_api",
            "current_price": price,
            "original_price": original,
            "discount_percent": 49,
            "savings_toman": original - price,
            "image_url": "https://example.com/charger.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95004%2F",
            "has_affiliate_link": True,
            "demand_score": 99,
            "review_count": 1200,
            "rating": 4.6,
            "deal_expires_at": "",
            "expiry_source": "unavailable",
        }, now)

        tiered, floor, quality = radar_module.select_discount_fallback_candidates(
            [candidate], {"published": {}}, now, include_fallback_bands=True
        )
        self.assertEqual(floor, 45)
        self.assertEqual([item['product_id'] for item in tiered], ['dkp-95004'])
        self.assertEqual(tiered[0]['selection_discount_floor'], 45)
        self.assertEqual([item['product_id'] for item in quality], ['dkp-95004'])

    def test_recent_family_cooldown_does_not_trigger_a_lower_discount_fallback(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-95101": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "telegram_message_id": 1511,
                "ts": (now - timedelta(minutes=20)).timestamp(),
            }
        }
        candidates = [
            _with_verified_current_demand({
                "product_id": "dkp-95102",
                "title": "عینک آفتابی ورزشی مدل تازه",
                "availability": "in_stock", "availability_source": "digikala_api",
                "current_price": 1_000_000, "original_price": 2_000_000,
                "discount_percent": 50, "savings_toman": 1_000_000,
                "image_url": "https://example.com/eyewear.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95102%2F",
                "has_affiliate_link": True, "demand_score": 95, "review_count": 2000,
                "rating": 4.7, "deal_expires_at": "",
            }, now),
            _with_verified_current_demand({
                "product_id": "dkp-95103",
                "title": "شارژر سریع دیواری مدل جدید",
                "availability": "in_stock", "availability_source": "digikala_api",
                "current_price": 1_000_000, "original_price": 1_818_182,
                "discount_percent": 45, "savings_toman": 818_182,
                "image_url": "https://example.com/charger.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95103%2F",
                "has_affiliate_link": True, "demand_score": 65, "review_count": 1200,
                "rating": 4.6, "deal_expires_at": "",
            }, now),
        ]
        selected, floor, _ = radar_module.select_discount_fallback_candidates(
            candidates, {"published": published}, now
        )
        self.assertIsNone(floor)
        self.assertEqual(selected, [])

    def test_lower_discount_bands_never_replace_50_percent_candidates_blocked_by_cooldown(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        published = {
            "dkp-95201": {
                "title": "عینک آفتابی زنانه مدل قبلی",
                "telegram_message_id": 1521,
                "ts": (now - timedelta(minutes=20)).timestamp(),
            },
            "dkp-95202": {
                "title": "شارژر سریع مدل قبلی",
                "telegram_message_id": 1522,
                "ts": (now - timedelta(minutes=15)).timestamp(),
            },
        }
        candidates = [
            _with_verified_current_demand({
                "product_id": "dkp-95203",
                "title": "عینک آفتابی ورزشی مدل تازه",
                "availability": "in_stock", "availability_source": "digikala_api",
                "current_price": 1_000_000, "original_price": 2_000_000,
                "discount_percent": 50, "savings_toman": 1_000_000,
                "image_url": "https://example.com/a.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fexample.com%2Fa",
                "has_affiliate_link": True, "deal_expires_at": "",
            }, now),
            _with_verified_current_demand({
                "product_id": "dkp-95204",
                "title": "شارژر سریع دیواری مدل تازه",
                "availability": "in_stock", "availability_source": "digikala_api",
                "current_price": 1_000_000, "original_price": 1_818_182,
                "discount_percent": 45, "savings_toman": 818_182,
                "image_url": "https://example.com/b.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fexample.com%2Fb",
                "has_affiliate_link": True, "deal_expires_at": "",
            }, now),
            _with_verified_current_demand({
                "product_id": "dkp-95205",
                "title": "ادوپرفیوم زنانه مدل تازه",
                "availability": "in_stock", "availability_source": "digikala_api",
                "current_price": 1_000_000, "original_price": 1_666_667,
                "discount_percent": 40, "savings_toman": 666_667,
                "image_url": "https://example.com/c.webp",
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fexample.com%2Fc",
                "has_affiliate_link": True, "deal_expires_at": "",
            }, now),
        ]
        selected, floor, _ = radar_module.select_discount_fallback_candidates(
            candidates, {"published": published}, now
        )
        self.assertIsNone(floor)
        self.assertEqual(selected, [])

    def test_market_price_and_savings_hard_gates_still_apply_above_50_percent(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        high_discount = _with_verified_current_demand({
            "product_id": "dkp-95301",
            "title": "گوشی موبایل پرتقاضا مدل نمونه",
            "availability": "in_stock", "availability_source": "digikala_api",
            "current_price": 1_000_000, "original_price": 2_000_000,
            "discount_percent": 60, "savings_toman": 1_000_000,
            "image_url": "https://example.com/a.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fexample.com%2Fa",
            "has_affiliate_link": True, "deal_expires_at": "",
            "market_status": "verified", "market_reference_kind": "seller_median",
            "market_price_advantage_pct": -8,
        }, now)
        lower_discount = _with_verified_current_demand({
            "product_id": "dkp-95302",
            "title": "ادوپرفیوم زنانه مدل تازه",
            "availability": "in_stock", "availability_source": "digikala_api",
            "current_price": 1_000_000, "original_price": 1_538_462,
            "discount_percent": 35, "savings_toman": 538_462,
            "image_url": "https://example.com/b.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fexample.com%2Fb",
            "has_affiliate_link": True, "deal_expires_at": "",
        }, now)
        small_saving = _with_verified_current_demand({
            **lower_discount,
            "product_id": "dkp-95303",
            "discount_percent": 60,
            "savings_toman": 50_000,
        }, now)
        selected, floor, quality = radar_module.select_discount_fallback_candidates(
            [high_discount, lower_discount, small_saving], {"published": {}}, now
        )
        self.assertEqual(floor, 35)
        self.assertEqual([item["product_id"] for item in selected], ["dkp-95302"])
        self.assertEqual(
            {item["product_id"] for item in quality},
            {"dkp-95302"},
        )

    def test_diversity_comparison_uses_recent_activity_signal_and_not_a_discount_fallback(self):
        stronger = {
            "current_demand_verified": True, "demand_score": 60,
            "click_count_30d": 100, "discount_percent": 49,
        }
        comparable = {
            "current_demand_verified": True, "demand_score": 50,
            "click_count_30d": 90, "discount_percent": 45,
        }
        self.assertTrue(
            radar_module._candidate_demand_comparable_for_diversity(comparable, stronger)
        )


    def test_open_ended_discovery_candidates_are_not_rejected_before_live_detail_check(self):
        now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        queue = {
            "dkp-95401": {
                "product_id": "dkp-95401",
                "product_url": "https://www.digikala.com/product/dkp-95401/",
                "title": "کالای پرفروش با آفر باز",
                "deal_expires_at": "",
                "discount_percent": 45,
                "savings_toman": 400_000,
                "demand_score": 80,
                "next_check_at": "",
            }
        }
        selected = select_discovery_records_for_check(queue, now, max_count=1)
        self.assertEqual([pid for pid, _ in selected], ["dkp-95401"])
        queued_rechecks = radar_module.select_queued_records_for_recheck(
            {"dkp-95401": queue["dkp-95401"]}, now, max_count=1
        )
        self.assertEqual([pid for pid, _ in queued_rechecks], ["dkp-95401"])


    def test_fifteen_percent_discount_is_rejected_by_fifty_percent_floor(self):
        product = {
            "title": "چراغ مطالعه مدل تست",
            "current_price": 850_000,
            "original_price": 1_000_000,
            "availability": "in_stock",
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-12345%2F",
            "review_count": 100,
            "rating": 4.5,
        }
        scored = score_product(product)
        self.assertEqual(scored["discount_percent"], 15)
        self.assertEqual(scored["savings_toman"], 150_000)
        self.assertFalse(is_discount_publish_eligible(scored))


    def test_discovery_ranks_demand_before_discount_size(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        popular_regular_discount = {
            "click_count_30d": 900, "demand_score": 78, "review_count": 2_000,
            "rating": 4.6, "discount_percent": 25, "savings_toman": 200_000,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
            "first_seen_at": (now - timedelta(minutes=2)).isoformat(),
        }
        low_demand_huge_discount = {
            "click_count_30d": 4, "demand_score": 18, "review_count": 25,
            "rating": 3.8, "discount_percent": 75, "savings_toman": 1_500_000,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
            "first_seen_at": (now - timedelta(minutes=1)).isoformat(),
        }
        self.assertGreater(
            discovery_queue_sort_key(popular_regular_discount, now),
            discovery_queue_sort_key(low_demand_huge_discount, now),
        )

    def test_selection_uses_market_demand_first_and_discount_percentage_second(self):
        now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        popular_lower_discount = {
            "demand_score": 82, "review_count": 12_000, "rating": 4.7,
            "discount_percent": 25, "savings_toman": 500_000,
            "click_count_30d": 0, "market_status": "not_checked",
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
            "first_seen_at": now.isoformat(),
        }
        weak_demand_higher_discount = {
            "demand_score": 52, "review_count": 300, "rating": 4.1,
            "discount_percent": 85, "savings_toman": 8_000_000,
            "click_count_30d": 0, "market_status": "verified",
            "market_reference_kind": "seller_median", "market_price_advantage_pct": 25,
            "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
            "first_seen_at": now.isoformat(),
        }
        self.assertGreater(deal_sort_key(popular_lower_discount), deal_sort_key(weak_demand_higher_discount))
        self.assertGreater(
            discovery_queue_sort_key(popular_lower_discount, now),
            discovery_queue_sort_key(weak_demand_higher_discount, now),
        )

        same_demand_higher_pct = {
            **popular_lower_discount,
            "demand_score": 70, "review_count": 3_000, "rating": 4.5,
            "discount_percent": 75, "savings_toman": 150_000,
            "market_status": "not_checked",
        }
        same_demand_lower_pct = {
            **same_demand_higher_pct,
            "discount_percent": 30, "savings_toman": 2_000_000,
            "market_status": "verified",
            "market_reference_kind": "seller_median", "market_price_advantage_pct": 30,
        }
        self.assertGreater(deal_sort_key(same_demand_higher_pct), deal_sort_key(same_demand_lower_pct))
        self.assertGreater(
            discovery_queue_sort_key(same_demand_higher_pct, now),
            discovery_queue_sort_key(same_demand_lower_pct, now),
        )

        candidates = [
            {"product_id": "dkp-popular", "title": "کرم مراقبت پوست مدل پرتقاضا", **popular_lower_discount},
            {"product_id": "dkp-less-popular", "title": "شارژر مدل تخفیف خیلی بالا", **weak_demand_higher_discount},
        ]
        queue = {item["product_id"]: {} for item in candidates}
        eligible = {item["product_id"]: item for item in candidates}
        selected = select_publish_candidates(queue, eligible, now)
        self.assertEqual(selected[0]["product_id"], "dkp-popular")

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

    def test_channel_click_counts_do_not_masquerade_as_market_demand(self):
        low_clicks = {
            "current_demand_verified": False,
            "discount_percent": 60,
            "savings_toman": 900_000,
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 7,
            "click_count_30d": 2,
        }
        high_clicks = {**low_clicks, "click_count_30d": 11}
        self.assertEqual(deal_sort_key(high_clicks), deal_sort_key(low_clicks))
        weaker_discount = {**high_clicks, "discount_percent": 59}
        self.assertGreater(deal_sort_key(high_clicks), deal_sort_key(weaker_discount))

    def test_lifetime_reviews_change_historical_popularity_not_current_demand(self):
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
        self.assertGreater(high["historical_popularity_score"], low["historical_popularity_score"])
        self.assertEqual(high["demand_score"], 0)
        self.assertFalse(high["current_demand_verified"])
        self.assertEqual(high["discount_percent"], 20)

    def test_current_demand_requires_measurable_recent_review_growth(self):
        start = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
        state = {}
        product = {
            "product_id": "dkp-demand-test",
            "product_url": "https://www.digikala.com/product/dkp-12345/",
            "review_count": 50_000,
        }

        radar_module.update_current_demand_signals(state, [product], now=start)
        self.assertFalse(product["current_demand_verified"])
        self.assertEqual(product["demand_score"], 0)

        product["review_count"] = 50_002
        radar_module.update_current_demand_signals(
            state, [product], now=start + timedelta(hours=23)
        )
        self.assertFalse(product["current_demand_verified"])

        product["review_count"] = 50_003
        radar_module.update_current_demand_signals(
            state, [product], now=start + timedelta(hours=25)
        )
        self.assertTrue(product["current_demand_verified"])
        self.assertEqual(product["recent_review_growth_7d"], 3)
        self.assertGreater(product["demand_score"], 0)
        self.assertTrue(
            radar_module.has_current_demand_signal(
                product, now=start + timedelta(hours=25)
            )
        )

        stale = dict(product)
        self.assertFalse(
            radar_module.has_current_demand_signal(
                stale, now=start + timedelta(hours=25 + radar_module.CURRENT_DEMAND_MAX_SIGNAL_AGE_HOURS + 1)
            )
        )

    def test_large_lifetime_review_count_without_recent_growth_is_not_demand(self):
        start = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
        state = {}
        product = {"product_id": "dkp-static-reviews", "review_count": 250_000}
        radar_module.update_current_demand_signals(state, [product], now=start)
        radar_module.update_current_demand_signals(
            state, [product], now=start + timedelta(hours=36)
        )
        self.assertEqual(product["recent_review_growth_7d"], 0)
        self.assertFalse(product["current_demand_verified"])
        self.assertEqual(product["demand_score"], 0)

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
        self.assertEqual(digital["historical_popularity_score"], unrelated["historical_popularity_score"])
        self.assertEqual(digital["demand_score"], 0)
        self.assertEqual(unrelated["demand_score"], 0)
        self.assertEqual(digital["promo_score"], unrelated["promo_score"])

    def test_price_band_does_not_change_demand_score(self):
        low_price = score_product({
            "title": "گوشی موبایل مدل اقتصادی",
            "current_price": 300_000,
            "original_price": 400_000,
            "rating": 4.2,
            "review_count": 280,
            "image_url": "https://example.com/image.jpg",
        })
        high_price = score_product({
            "title": "گوشی موبایل مدل پرچمدار",
            "current_price": 40_000_000,
            "original_price": 50_000_000,
            "rating": 4.2,
            "review_count": 280,
            "image_url": "https://example.com/image.jpg",
        })
        self.assertEqual(low_price["historical_popularity_score"], high_price["historical_popularity_score"])
        self.assertEqual(low_price["demand_score"], 0)
        self.assertEqual(high_price["demand_score"], 0)
        common = {
            "discount_percent": 25, "savings_toman": 100_000,
            "demand_score": 35, "review_count": 280,
            "first_seen_at": "2026-10-19T00:00:00+00:00",
        }
        self.assertEqual(
            discovery_queue_sort_key({**common, "current_price": 300_000}, now=datetime(2026, 10, 20, tzinfo=timezone.utc)),
            discovery_queue_sort_key({**common, "current_price": 40_000_000}, now=datetime(2026, 10, 20, tzinfo=timezone.utc)),
        )

    def test_lifetime_review_volume_is_popularity_not_current_demand(self):
        broad_popularity = score_product({
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
        self.assertGreater(
            broad_popularity["historical_popularity_score"],
            lower_volume["historical_popularity_score"],
        )
        self.assertFalse(broad_popularity["current_demand_verified"])
        self.assertEqual(broad_popularity["demand_score"], 0)
        self.assertEqual(lower_volume["demand_score"], 0)

    def test_last_mile_photo_sender_rejects_a_49_percent_offer_even_with_recent_demand(self):
        now = datetime.now(timezone.utc)
        item = {
            "title": "شارژر سریع دیواری مدل نمونه",
            "availability": "in_stock",
            "current_price": 550_000,
            "original_price": 1_000_000,
            "discount_percent": 49,
            "savings_toman": 450_000,
            "image_url": "https://example.com/charger.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95045%2F",
            "current_demand_verified": True,
            "current_demand_score": 60,
            "demand_score": 60,
            "recent_review_growth_7d": 5,
            "demand_window_hours": 48,
            "demand_observed_at": now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        with patch("affilio_radar.build_discount_image") as build_image:
            with self.assertRaisesRegex(RuntimeError, "hard discount/current-demand gate"):
                radar_module._send_platform_photo("telegram", item, b"image", item["affiliate_url"])
        build_image.assert_not_called()

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
            "_countdown_now": datetime(2026, 10, 16, 20, 30, tzinfo=timezone.utc),
            "rating": 4.4,
            "review_count": 1243,
        }, "https://www.digikala.com/product/dkp-15970075/?utm_source=19166")
        self.assertIn("🔥 فروش ویژه دیجی‌کالا 🔴", caption)
        self.assertIn("🛍️ گجت نمونه ۶۰", caption)
        self.assertNotIn("<b>🔥 فروش ویژه دیجی‌کالا</b>", caption)
        self.assertIn("<b>💚 قیمت فعلی: ۵۰۰٬۰۰۰ تومان</b>", caption)
        self.assertIn("<b>⚡️ ۲۹٪ تخفیف</b>", caption)
        self.assertEqual(caption.count("────────────"), 2)
        self.assertNotIn("💰", caption)
        self.assertNotIn("<u>", caption)
        self.assertNotIn("قیمت اصلی", caption)  # A 29% discount keeps the caption focused on two key numbers.
        self.assertNotIn("مانده به پایان تخفیف", caption)
        self.assertNotIn("📅 پایان تخفیف:", caption)
        self.assertNotIn("⏳", caption)
        self.assertNotIn("دکمهٔ زیر رو بزن", caption)
        self.assertNotIn("برای خرید از دیجی‌کالا", caption)
        self.assertIn('<a href="https://t.me/OfferChin">➕ عضویت در کانال آفِرچین</a>', caption)
        self.assertLess(caption.index("⚡️"), caption.index("عضویت در کانال آفِرچین"))
        self.assertNotRegex(caption, r"[0-9]")
        self.assertNotIn("قیمت امروز", caption)
        self.assertNotIn("صرفه‌جویی", caption)
        self.assertNotIn("امتیاز کاربران", caption)
        self.assertNotIn("نظر", caption)
        self.assertNotIn("پشتیبانی کانال", caption)
        self.assertNotIn("لینک خرید همکاری در فروش است", caption)
        self.assertLess(caption.index("💚 قیمت فعلی"), caption.index("⚡️"))
        self.assertLess(caption.index("────────────"), caption.index("💚 قیمت فعلی"))
        self.assertLess(caption.index("⚡️"), caption.index("عضویت در کانال آفِرچین"))
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

    def test_caption_never_displays_deadline_even_when_source_has_one(self):
        caption = build_caption({
            "title": "محصول دارای مهلت معتبر",
            "current_price": 100_000,
            "original_price": 200_000,
            "discount_percent": 50,
            "deal_expires_at": "2026-12-16T20:30:00+00:00",
            "_countdown_now": datetime(2026, 10, 16, 20, 30, tzinfo=timezone.utc),
        }, "https://www.digikala.com/product/dkp-15970075/?utm_source=19166")
        self.assertNotIn("مانده به پایان تخفیف", caption)
        self.assertNotIn("📅 پایان تخفیف:", caption)
        self.assertNotIn("⏳", caption)

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
        self.assertEqual(urlsplit(markup["inline_keyboard"][0][0]["url"]).netloc, "aflo.ir")

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

    def test_snappshop_bale_purchase_button_uses_correct_store_name(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True, "result": {"message_id": 89}}
        link = build_affilio_tracking_link("https://snappshop.ir/product/snp-25751584")
        with (
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.requests.post", return_value=response) as post,
        ):
            _send_bale_photo(b"photo-bytes", "caption", link)
        markup = json.loads(post.call_args.kwargs["data"]["reply_markup"])
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "🛍️ مشاهده و خرید از اسنپ‌شاپ")
        self.assertEqual(markup["inline_keyboard"][0][0]["url"], link)

    def test_original_price_is_never_shown_in_telegram_or_bale_caption(self):
        product = {"title": "محصول نمونه", "current_price": 123_200, "original_price": 1_108_800, "discount_percent": 89}
        link = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        bale_caption = build_caption(product, link, "https://ble.ir/OfferChin", use_unicode_strikethrough=True)
        telegram_caption = build_caption(product, link)
        self.assertNotIn("قیمت اصلی", bale_caption)
        self.assertNotIn("۱٬۱۰۸٬۸۰۰", bale_caption)
        self.assertIn("*💚 قیمت فعلی: ۱۲۳٬۲۰۰ تومان*", bale_caption)
        self.assertIn("*⚡️ ۸۹٪ تخفیف*", bale_caption)
        self.assertEqual(bale_caption.count("────────────"), 2)
        self.assertNotIn("💰", bale_caption)
        self.assertNotIn("\u0332", bale_caption)
        self.assertNotIn("<s>", bale_caption)
        self.assertNotIn("قیمت اصلی", telegram_caption)
        self.assertNotIn("۱٬۱۰۸٬۸۰۰", telegram_caption)
        self.assertIn("[➕ عضویت در کانال آفِرچین](https://ble.ir/OfferChin)", bale_caption)
        self.assertIn('<a href="https://t.me/OfferChin">➕ عضویت در کانال آفِرچین</a>', telegram_caption)
        self.assertNotIn("دکمهٔ زیر رو بزن", bale_caption)
        self.assertNotIn("دکمهٔ زیر رو بزن", telegram_caption)
        self.assertLess(bale_caption.index("⚡️"), bale_caption.index("عضویت در کانال آفِرچین"))
        self.assertNotIn("<b>", bale_caption)
        self.assertNotIn("@OfferChin", bale_caption)
        self.assertNotIn("@OfferChin", telegram_caption)


    def test_source_visible_countdown_is_reduced_by_exactly_ten_minutes(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        source_card = {
            "id": 123,
            "title_fa": "محصول نمونه",
            "campaign": {"remaining_seconds": 3 * 3600 + 24 * 60},
            # This nested variant timestamp is unrelated to the card's visible timer.
            "default_variant": {"ends_at": "2026-10-22T18:00:00+03:30"},
        }
        deadline = extract_deal_expiry(source_card, now=now)
        self.assertEqual(
            deadline,
            (now + timedelta(hours=3, minutes=24)).isoformat(),
        )
        self.assertEqual(
            format_remaining_time(deadline, now, safety_buffer_minutes=10),
            "۳ ساعت و ۱۴ دقیقه مانده به پایان تخفیف",
        )

    def test_countdown_formats_hours_minutes_and_expired_deadlines(self):
        now = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(
            format_remaining_time("2026-10-18T12:17:20+00:00", now),
            "۲ ساعت و ۱۷ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T10:00:15+00:00", now),
            "کمتر از ۱ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T11:00:00+00:00", now),
            "۱ ساعت مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T10:43:20+00:00", now),
            "۴۳ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(format_remaining_time("2026-10-18T09:59:59+00:00", now), "مهلت آفر به پایان رسیده")
        self.assertEqual(format_remaining_time("2026-10-18T10:05:00+00:00", now), "۵ دقیقه مانده به پایان تخفیف")
        self.assertEqual(format_remaining_time("2026-10-18T10:05:01+00:00", now), "۵ دقیقه مانده به پایان تخفیف")
        self.assertEqual(format_remaining_time("", now), "")
        # Captions deliberately stop ten minutes before DigiKala's site deadline.
        self.assertEqual(
            format_remaining_time("2026-10-18T12:17:20+00:00", now, safety_buffer_minutes=10),
            "۲ ساعت و ۷ دقیقه مانده به پایان تخفیف",
        )
        self.assertEqual(
            format_remaining_time("2026-10-18T10:05:00+00:00", now, safety_buffer_minutes=10),
            "مهلت آفر به پایان رسیده",
        )

    def test_publication_requires_a_directly_verified_future_deadline(self):
        now = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
        verified = {
            "deal_expires_at": "2026-10-18T12:17:20+00:00",
            "expiry_source": "digikala_product_detail_api",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        self.assertTrue(has_verified_deal_deadline(verified, now))
        self.assertTrue(has_verified_deal_deadline({
            "deal_expires_at": "2026-10-18T12:17:20+00:00",
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_directly": False,
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
        }, now))
        self.assertFalse(has_verified_deal_deadline({
            "deal_expires_at": "2026-10-18T12:17:20+00:00",
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": False,
            "expiry_estimated": False,
        }, now))
        self.assertFalse(has_verified_deal_deadline({
            "deal_expires_at": "2026-10-18T12:17:20+00:00",
            "expiry_source": "mcp_unverified",
            "expiry_deadline_verified_directly": False,
        }, now))
        self.assertFalse(has_verified_deal_deadline({}, now))
        self.assertFalse(has_verified_deal_deadline({
            **verified,
            "deal_expires_at": "2026-10-18T09:59:59+00:00",
        }, now))

    def test_build_caption_never_displays_countdown_with_verified_deadline(self):
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/")
        product = {
            "title": "محصول نمونه",
            "current_price": 100_000,
            "original_price": 200_000,
            "discount_percent": 50,
            "deal_expires_at": "2026-10-23T12:00:00+00:00",
            "expiry_estimated": False,
        }
        with patch("affilio_radar.format_remaining_time", return_value="۵۰ دقیقه مانده به پایان تخفیف") as countdown:
            caption = build_caption(product, url, "https://t.me/OfferChin")
        countdown.assert_not_called()
        self.assertNotIn("⏳", caption)
        self.assertNotIn("مانده به پایان تخفیف", caption)
        self.assertNotIn("📅 پایان تخفیف:", caption)

    def test_unicode_underline_marks_visible_characters(self):
        self.assertEqual(unicode_underline("۱۲۳"), "۱\u0332۲\u0332۳\u0332")

    def test_refresh_active_countdowns_migrates_tracked_captions_without_deadlines(self):
        stale_expiry = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        state = {
            "published": {
                "dkp-15970075": {
                    "ts": 1, "title": "محصول نمونه",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 39, "bale_message_id": 2,
                    "posted_current_price": 123_200, "posted_original_price": 1_108_800,
                    "posted_discount_percent": 89, "expires_at": stale_expiry,
                    "expiry_source": "digikala_live_deals_feed", "expiry_estimated": False,
                    "caption_deadline_format_version": 3,
                },
                "dkp-expired": {
                    "ts": 2, "title": "پیشنهاد تمام‌شده",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 40, "posted_current_price": 100_000,
                    "posted_original_price": 200_000, "posted_discount_percent": 50,
                    "expires_at": "2026-10-17T20:30:00+00:00",
                    "expiry_source": "digikala_live_deals_feed", "expiry_estimated": False,
                    "expiry_deadline_verified_directly": True,
                    "caption_deadline_format_version": 3,
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
        self.assertEqual(state["published"]["dkp-15970075"]["expires_at"], stale_expiry)
        self.assertEqual(edit_telegram.call_count, 1)
        self.assertEqual(edit_bale.call_count, 1)
        self.assertNotIn("مانده به پایان تخفیف", edit_telegram.call_args.args[1])
        self.assertNotIn("مانده به پایان تخفیف", edit_bale.call_args.args[1])
        self.assertNotIn("⏳", edit_telegram.call_args.args[1])
        self.assertNotIn("⏳", edit_bale.call_args.args[1])
        self.assertNotIn("📅 پایان تخفیف:", edit_telegram.call_args.args[1])
        self.assertNotIn("📅 پایان تخفیف:", edit_bale.call_args.args[1])
        self.assertEqual(state["published"]["dkp-15970075"]["caption_deadline_format_version"], 14)
        self.assertIn("caption_countdown_refreshed_at", state["published"]["dkp-15970075"])
        self.assertEqual(edit_telegram.call_args.args[2], url)
        self.assertEqual(edit_bale.call_args.args[2], url)
        self.assertNotIn("deadline_caption_refresh_required", state["published"]["dkp-15970075"])
        self.assertIn("عضویت در کانال آفِرچین", edit_telegram.call_args.args[1])
        self.assertIn("عضویت در کانال آفِرچین", edit_bale.call_args.args[1])
        self.assertTrue(save_state.called)



    def test_caption_migration_does_not_require_deadline_feed_presence(self):
        now = datetime.now(timezone.utc)
        live_expiry = (now + timedelta(hours=3)).isoformat()
        state = {
            "published": {
                "dkp-live": {
                    "title": "پیشنهاد قابل تأیید",
                    "product_url": "https://www.digikala.com/product/dkp-1001/",
                    "telegram_message_id": 501,
                    "posted_current_price": 100_000,
                    "posted_original_price": 200_000,
                    "posted_discount_percent": 50,
                    "expires_at": live_expiry,
                    "expiry_source": "digikala_live_deals_feed",
                    "expiry_estimated": False,
                    "caption_deadline_format_version": 3,
                },
                "dkp-missing": {
                    "title": "پیشنهادی که مهلتش فعلاً تأیید نشده",
                    "product_url": "https://www.digikala.com/product/dkp-1002/",
                    "telegram_message_id": 502,
                    "posted_current_price": 100_000,
                    "posted_original_price": 200_000,
                    "posted_discount_percent": 50,
                    "expires_at": (now + timedelta(hours=4)).isoformat(),
                    "expiry_source": "unavailable",
                    "expiry_estimated": True,
                    "caption_deadline_format_version": 3,
                },
            }
        }
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-1001/")
        with (
            patch("affilio_radar.load_state", return_value=state),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption", side_effect=lambda mid, *args: {"message_id": mid}) as edit_telegram,
            patch("affilio_radar.save_json") as save_state,
            patch("affilio_radar.time.sleep"),
        ):
            result = refresh_active_countdowns()

        self.assertEqual(result, 0)
        self.assertEqual(state["published"]["dkp-missing"]["expiry_source"], "unavailable")
        self.assertTrue(state["published"]["dkp-missing"]["expiry_estimated"])
        self.assertEqual([call.args[0] for call in edit_telegram.call_args_list], [501, 502])
        self.assertEqual(state["published"]["dkp-live"]["caption_deadline_format_version"], 14)
        self.assertEqual(state["published"]["dkp-missing"]["caption_deadline_format_version"], 14)
        self.assertNotIn("مانده به پایان تخفیف", edit_telegram.call_args_list[0].args[1])
        self.assertNotIn("مانده به پایان تخفیف", edit_telegram.call_args_list[1].args[1])
        self.assertNotIn("⏳", edit_telegram.call_args_list[0].args[1])
        self.assertNotIn("⏳", edit_telegram.call_args_list[1].args[1])
        self.assertEqual(edit_telegram.call_args_list[0].args[2], url)
        self.assertEqual(edit_telegram.call_args_list[1].args[2], url)
        self.assertTrue(save_state.called)

    def test_refresh_restores_button_after_verified_delete_failure(self):
        now = datetime.now(timezone.utc)
        expired = (now - timedelta(minutes=2)).isoformat()
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-9001/")
        record = {
            "title": "محصولی که حذفش موقتاً خطا داده",
            "product_url": "https://www.digikala.com/product/dkp-9001/",
            "telegram_message_id": 901,
            "bale_message_id": 902,
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "posted_discount_percent": 50,
            "expires_at": expired,
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "expiry_status": "delete_failed",
            "bale_expiry_status": "delete_failed",
            "caption_deadline_format_version": 8,
        }
        state = {"published": {"dkp-9001": record}}
        with (
            patch("affilio_radar.load_state", return_value=state),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption", return_value={"message_id": 901}) as edit_telegram,
            patch("affilio_radar._edit_bale_caption", return_value={"message_id": 902}) as edit_bale,
            patch("affilio_radar.save_json"),
            patch("affilio_radar.time.sleep"),
        ):
            result = refresh_active_countdowns()
        self.assertEqual(result, 0)
        self.assertEqual(edit_telegram.call_args.args[0], 901)
        self.assertEqual(edit_bale.call_args.args[0], 902)
        for caption in (edit_telegram.call_args.args[1], edit_bale.call_args.args[1]):
            self.assertNotIn("مانده به پایان تخفیف", caption)
            self.assertNotIn("⏳", caption)
        self.assertEqual(edit_telegram.call_args.args[2], url)
        self.assertEqual(edit_bale.call_args.args[2], url)
        self.assertEqual(record["caption_deadline_format_version"], 14)

    def test_refresh_active_countdowns_caps_batch_and_rotates_fairly(self):
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(hours=3)).isoformat()
        published = {}
        for index in range(10):
            published[f"dkp-{1000 + index}"] = {
                "ts": index + 1,
                "caption_deadline_format_version": 3,
                "title": f"محصول نمونه {index}",
                "product_url": f"https://www.digikala.com/product/dkp-{1000 + index}/",
                "telegram_message_id": 200 + index,
                "bale_message_id": 400 + index,
                "posted_current_price": 100_000,
                "posted_original_price": 200_000,
                "posted_discount_percent": 50,
                "expires_at": expiry,
                "expiry_source": "digikala_live_deals_feed",
                "expiry_estimated": False,
            }
        state = {"published": published}
        url = build_affilio_tracking_link("https://www.digikala.com/product/dkp-1000/")
        with (
            patch.dict("os.environ", {"AFFILIO_COUNTDOWN_REFRESH_MAX_RECORDS": "2"}),
            patch("affilio_radar.load_state", return_value=state),
            patch("expiration_monitor.fetch_offer_expiries", return_value={product_key: expiry for product_key in published}),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption", side_effect=lambda message_id, *args: {"message_id": message_id}) as edit_telegram,
            patch("affilio_radar._edit_bale_caption", side_effect=lambda message_id, *args: {"message_id": message_id}) as edit_bale,
            patch("affilio_radar.save_json") as save_state,
            patch("affilio_radar.time.sleep"),
        ):
            result = refresh_active_countdowns()

        self.assertEqual(result, 0)
        self.assertEqual([call.args[0] for call in edit_telegram.call_args_list], [200, 201])
        self.assertEqual([call.args[0] for call in edit_bale.call_args_list], [400, 401])
        self.assertEqual(published["dkp-1000"]["caption_deadline_format_version"], 14)
        self.assertEqual(published["dkp-1001"]["caption_deadline_format_version"], 14)
        self.assertEqual(published["dkp-1002"]["caption_deadline_format_version"], 3)
        self.assertNotIn("caption_countdown_refreshed_at", published["dkp-1002"])
        self.assertEqual(edit_telegram.call_args_list[0].args[2], url)
        self.assertEqual(edit_telegram.call_args_list[1].args[2], url)
        self.assertEqual(edit_bale.call_args_list[0].args[2], url)
        self.assertEqual(edit_bale.call_args_list[1].args[2], url)
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
                    "expiry_status": "delete_failed",
                    "bale_expiry_status": "delete_failed",
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
            # Keep the synthetic unit-test repair report out of the repository.
            patch("affilio_radar.ROOT", Path("/tmp")),
            patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
            patch("affilio_radar.BALE_BOT_TOKEN", "bale-test-token"),
            patch("affilio_radar.BALE_CHANNEL_ID", "-10012345"),
            patch("affilio_radar.build_affilio_tracking_link", return_value=url),
            patch("affilio_radar._edit_telegram_caption") as edit_telegram,
            patch("affilio_radar._edit_bale_caption") as edit_bale,
            patch("affilio_radar._send_photo") as send_telegram,
            patch("affilio_radar._send_bale_photo") as send_bale,
            patch("affilio_radar.time.sleep"),
            patch("affilio_radar.save_json") as save_state,
        ):
            result = repair_all_published_captions()
        self.assertEqual(result, 0)
        self.assertEqual(edit_telegram.call_count, 2)
        self.assertEqual(edit_bale.call_count, 1)
        self.assertEqual(edit_telegram.call_args_list[0].args[2], url)
        self.assertEqual(edit_bale.call_args_list[0].args[2], url)
        self.assertFalse(send_telegram.called)
        self.assertFalse(send_bale.called)
        save_state.assert_called_once()
        telegram_caption = edit_telegram.call_args_list[0].args[1]
        bale_caption = edit_bale.call_args_list[0].args[1]
        self.assertIn('<a href="https://t.me/OfferChin">➕ عضویت در کانال آفِرچین</a>', telegram_caption)
        self.assertIn("[➕ عضویت در کانال آفِرچین](https://ble.ir/OfferChin)", bale_caption)
        self.assertLess(telegram_caption.index("⚡️"), telegram_caption.index("عضویت در کانال آفِرچین"))
        self.assertLess(bale_caption.index("⚡️"), bale_caption.index("عضویت در کانال آفِرچین"))


    def test_repair_does_not_reactivate_unknown_deadline_post(self):
        state = {
            "published": {
                "dkp-unknown-deadline": {
                    "ts": 1,
                    "title": "پیشنهاد بدون مهلت معتبر",
                    "product_url": "https://www.digikala.com/product/dkp-15970075/",
                    "telegram_message_id": 88,
                    "expires_at": "",
                    "expiry_status": "deadline_unavailable_marked",
                    "posted_current_price": 100_000,
                    "posted_original_price": 200_000,
                    "posted_discount_percent": 50,
                }
            }
        }
        with TemporaryDirectory() as temp:
            with (
                patch("affilio_radar.load_state", return_value=state),
                patch("affilio_radar.ROOT", Path(temp)),
                patch("affilio_radar.BOT_TOKEN", "telegram-test-token"),
                patch("affilio_radar.BALE_BOT_TOKEN", ""),
                patch("affilio_radar.BALE_CHANNEL_ID", ""),
                patch("affilio_radar._edit_telegram_caption") as edit_telegram,
                patch("affilio_radar.time.sleep"),
            ):
                result = repair_all_published_captions()
            self.assertEqual(result, 0)  # active post caption and purchase button were repaired
            edit_telegram.assert_called_once()
            self.assertEqual(edit_telegram.call_args.args[2], build_affilio_tracking_link("https://www.digikala.com/product/dkp-15970075/"))
            self.assertEqual(state["published"]["dkp-unknown-deadline"]["expiry_status"], "unknown")
            report = json.loads((Path(temp) / "affiliate_link_repair_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["targets"], 1)
            self.assertEqual(report["telegram_updated"], 1)



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

    def test_discount_badge_uses_persian_label_and_numerals(self):
        self.assertEqual(format_discount_badge(81), "۸۱٪ تخفیف")
        self.assertEqual(format_discount_badge("24"), "۲۴٪ تخفیف")
        self.assertEqual(format_discount_badge(0), "")
        self.assertEqual(format_discount_badge("not-a-number"), "")

    def test_persian_discount_word_uses_right_to_left_shaping_not_raw_pillow_text(self):
        import offerchin_visuals as visuals

        prepared, options = visuals._prepare_persian_badge_text("تخفیف", use_raqm=True)
        self.assertEqual(prepared, "تخفیف")
        self.assertEqual(options, {"direction": "rtl", "language": "fa"})

        # Explicitly exercise the non-RAQM fallback too; it must reshape letters and
        # bidi-reorder once rather than handing isolated Persian characters to Pillow.
        fallback, fallback_options = visuals._prepare_persian_badge_text("تخفیف", use_raqm=False)
        self.assertTrue(fallback)
        self.assertNotEqual(fallback, "تخفیف")
        self.assertEqual(fallback_options, {})
        self.assertTrue(any(0xFB50 <= ord(char) <= 0xFDFF or 0xFE70 <= ord(char) <= 0xFEFF for char in fallback))

    def test_discount_badge_uses_bundled_vazirmatn_extrabold_font(self):
        import offerchin_visuals as visuals
        from pathlib import Path

        font_path = Path(visuals.__file__).resolve().parent / "assets" / "fonts" / "Vazirmatn-ExtraBold.ttf"
        self.assertTrue(font_path.is_file(), "bundled font must be present in the repository")
        font, _use_raqm = visuals._badge_font(32)
        self.assertIn("vazirmatn", font.getname()[0].casefold())
        self.assertIsNotNone(font.getmask("تخفیف").getbbox())

    def test_discount_badge_uses_store_brand_color_and_persian_wordmark(self):
        import offerchin_visuals as visuals
        from PIL import ImageDraw

        for merchant, predicate in (
            ("دیجی‌کالا", lambda red, green, blue: red > 150 and red > green * 1.7 and red > blue * 1.4),
            ("اسنپ‌شاپ", lambda red, green, blue: red > 100 and blue > 100 and red > green * 1.6 and blue > green * 1.6),
        ):
            canvas = Image.new("RGB", (260, 160), (246, 246, 246))
            visuals.draw_discount_burst(ImageDraw.Draw(canvas), 25, 15, 210, 125, 45, merchant=merchant)
            crop = list(canvas.crop((25, 15, 235, 140)).getdata())
            brand_pixels = sum(1 for red, green, blue in crop if predicate(red, green, blue))
            white_pixels = sum(1 for red, green, blue in crop if red > 230 and green > 230 and blue > 230)
            yellow_pixels = sum(1 for red, green, blue in crop if red > 180 and green > 150 and blue < 100)
            self.assertGreater(brand_pixels, 12000, f"{merchant} badge should use its brand color")
            self.assertGreater(white_pixels, 300, "the Persian label and percentage should be visible in white")
            self.assertLess(yellow_pixels, 100, "the old yellow burst treatment should be gone")

    def test_discount_image_returns_photo_with_badge(self):
        image_bytes = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(image_bytes, format="JPEG")
        rendered = build_discount_image(image_bytes.getvalue(), 24)
        with Image.open(BytesIO(rendered)) as preview:
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.size, (480, 640))
        self.assertNotEqual(rendered, image_bytes.getvalue())

        # A clean, brand-colored rounded badge remains in the upper-right of channel photos.
        with Image.open(BytesIO(rendered)).convert("RGB") as preview:
            crop = preview.crop((300, 0, 480, 150))
            red_pixels = sum(
                1 for red, green, blue in crop.getdata()
                if red > 120 and red > green * 1.6 and red > blue * 1.5
            )
            self.assertGreater(red_pixels, 500)

        snapp_rendered = build_discount_image(image_bytes.getvalue(), 24, merchant="اسنپ‌شاپ")
        with Image.open(BytesIO(snapp_rendered)).convert("RGB") as preview:
            crop = preview.crop((300, 0, 480, 150))
            purple_pixels = sum(
                1 for red, green, blue in crop.getdata()
                if red > 100 and blue > 100 and red > green * 1.6 and blue > green * 1.6
            )
            self.assertGreater(purple_pixels, 500, "SnappShop badge should use SnappShop purple")

        # Channel watermark must still render when a discount badge is unavailable.
        rendered_without_badge = build_discount_image(image_bytes.getvalue(), None)
        with Image.open(BytesIO(rendered_without_badge)) as preview:
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.size, (480, 640))
        self.assertNotEqual(rendered_without_badge, image_bytes.getvalue())

    def test_adaptive_text_colors_switch_for_light_and_dark_backgrounds(self):
        from offerchin_visuals import adaptive_text_colors

        light = Image.new("RGB", (80, 40), (250, 250, 250))
        dark = Image.new("RGB", (80, 40), (20, 22, 25))
        light_fill, light_stroke = adaptive_text_colors(light, (0, 0, 80, 40))
        dark_fill, dark_stroke = adaptive_text_colors(dark, (0, 0, 80, 40))
        self.assertLess(sum(light_fill), sum(light_stroke))
        self.assertGreater(sum(dark_fill), sum(dark_stroke))
        self.assertEqual(light_fill, (18, 23, 28))
        self.assertEqual(dark_fill, (255, 255, 255))

    def test_retailer_logo_assets_are_stored_locally(self):
        import offerchin_visuals as visuals

        self.assertEqual(visuals._LOCAL_LOGO_PATHS["digikala"].suffix, ".webp")
        self.assertEqual(visuals._LOCAL_LOGO_PATHS["snappshop"].suffix, ".webp")
        for path in visuals._LOCAL_LOGO_PATHS.values():
            self.assertTrue(path.is_file())
            with Image.open(path) as asset:
                self.assertGreater(asset.width, 100)
                self.assertGreater(asset.height, 100)
                self.assertEqual(asset.format, "WEBP")

        # Preserve the full supplied wordmark canvas: DigiKala is landscape; SnappShop is square.
        with Image.open(visuals._LOCAL_LOGO_PATHS["digikala"]) as asset:
            self.assertAlmostEqual(asset.width / asset.height, 1.58, delta=0.03)
        with Image.open(visuals._LOCAL_LOGO_PATHS["snappshop"]) as asset:
            self.assertAlmostEqual(asset.width / asset.height, 1.0, delta=0.01)

    def test_committed_retailer_logo_assets_load_without_network(self):
        import offerchin_visuals as visuals

        visuals._load_retailer_logo.cache_clear()
        try:
            with patch("requests.get", side_effect=AssertionError("committed retailer logos must not use the network")):
                self.assertTrue(visuals._LOCAL_LOGO_PATHS["digikala"].is_file())
                self.assertTrue(visuals._LOCAL_LOGO_PATHS["snappshop"].is_file())
                self.assertIsNotNone(visuals._load_retailer_logo(False))
                self.assertIsNotNone(visuals._load_retailer_logo(True))
        finally:
            visuals._load_retailer_logo.cache_clear()

    def test_local_retailer_logo_assets_load_without_network(self):
        import offerchin_visuals as visuals

        with TemporaryDirectory() as asset_dir:
            directory = Path(asset_dir)
            digikala_path = directory / "digikala.svg"
            snappshop_path = directory / "snappshop.png"
            digikala_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                '<path d="M16 36 Q32 52 48 36" fill="none" stroke="#E52332" stroke-width="6"/>'
                '</svg>',
                encoding="utf-8",
            )
            from PIL import ImageDraw
            snapp_icon = Image.new("RGB", (64, 64), (180, 0, 174))
            ImageDraw.Draw(snapp_icon).text((5, 20), "Shop!", fill=(255, 255, 255))
            snapp_icon.save(snappshop_path, format="PNG")

            with patch.dict(
                visuals._LOCAL_LOGO_PATHS,
                {"digikala": digikala_path, "snappshop": snappshop_path},
            ):
                visuals._load_retailer_logo.cache_clear()
                try:
                    with patch("requests.get", side_effect=AssertionError("network must not be used for saved logos")):
                        self.assertIsNotNone(visuals._load_retailer_logo(False))
                        self.assertIsNotNone(visuals._load_retailer_logo(True))
                finally:
                    visuals._load_retailer_logo.cache_clear()

    def test_retailer_badge_preserves_official_color_background_and_wordmark(self):
        import offerchin_visuals as visuals

        for merchant, box, brand in (
            ("دیجی‌کالا", (10, 10, 86, 58), "red"),
            ("اسنپ‌شاپ", (10, 10, 58, 58), "purple"),
        ):
            artwork = Image.new("RGB", (240, 90), (250, 250, 250))
            visuals.draw_retailer_badge(artwork, 10, 10, 180, 48, merchant)
            pixels = list(artwork.crop(box).getdata())
            if brand == "red":
                brand_pixels = sum(
                    1 for r, g, b in pixels
                    if r > 150 and r > g * 1.7 and r > b * 1.5
                )
            else:
                brand_pixels = sum(
                    1 for r, g, b in pixels
                    if r > 100 and b > 100 and r > g * 1.6 and b > g * 1.6
                )
            white_pixels = sum(1 for r, g, b in pixels if r > 220 and g > 220 and b > 220)
            self.assertGreater(brand_pixels, 500, f"{merchant} official background must remain visible")
            self.assertGreater(white_pixels, 100, f"{merchant} official white wordmark must remain visible")

    def test_fetch_image_retries_transient_connect_timeout_once(self):
        import requests
        from unittest.mock import patch
        from affilio_radar import _fetch_image

        image_buffer = BytesIO()
        Image.new("RGB", (16, 16), (240, 240, 240)).save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()

        class FakeResponse:
            headers = {"Content-Type": "image/png"}
            status_code = 200
            def __init__(self, data):
                self.data = data
                self.closed = False
            def raise_for_status(self):
                return None
            def iter_content(self, chunk_size):
                yield self.data
            def close(self):
                self.closed = True

        response = FakeResponse(image_bytes)
        class FakeSession:
            def __init__(self):
                self.calls = 0
                self.last_kwargs = {}
            def get(self, url, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise requests.exceptions.ConnectTimeout("temporary image CDN timeout")
                self.last_kwargs = kwargs
                return response

        session = FakeSession()
        with patch("affilio_radar.SESSION", session), patch("affilio_radar.time.sleep"):
            result = _fetch_image("https://images.example.test/product.png")

        self.assertEqual(result, image_bytes)
        self.assertEqual(session.calls, 2)
        self.assertEqual(session.last_kwargs["timeout"], (8, 18))
        self.assertTrue(response.closed)

    def test_store_badge_is_visible_in_upper_left_and_changes_by_retailer(self):
        image_bytes = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(image_bytes, format="JPEG")
        source = image_bytes.getvalue()
        digikala = build_discount_image(source, None, merchant="دیجی‌کالا")
        snappshop = build_discount_image(source, None, merchant="اسنپ‌شاپ")
        self.assertNotEqual(digikala, snappshop)

        with Image.open(BytesIO(digikala)).convert("RGB") as preview:
            crop = preview.crop((0, 0, 185, 90))
            red_pixels = sum(1 for red, green, blue in crop.getdata() if red > 150 and red > green * 1.7 and red > blue * 1.5)
            self.assertGreater(red_pixels, 1500, "official DigiKala red tile must remain clearly visible")
        with Image.open(BytesIO(snappshop)).convert("RGB") as preview:
            crop = preview.crop((0, 0, 185, 90))
            purple_pixels = sum(1 for red, green, blue in crop.getdata() if blue > 90 and red > green * 1.6 and blue > green * 1.6)
            self.assertGreater(purple_pixels, 1500, "official SnappShop purple tile must remain clearly visible")

    def test_channel_discount_badge_matches_retailer_badge_bounds(self):
        source_image = BytesIO()
        Image.new("RGB", (480, 640), (238, 241, 246)).save(source_image, format="JPEG")
        rendered = build_discount_image(source_image.getvalue(), 76, merchant="دیجی‌کالا")
        with Image.open(BytesIO(rendered)).convert("RGB") as poster:
            min_dim = min(poster.size)
            brand_margin = max(10, int(min_dim * 0.025))
            expected_width = min(
                poster.width - 2 * brand_margin,
                max(124, min(320, int(min_dim * 0.38))),
            )
            expected_height = max(48, min(88, int(min_dim * 0.14)))
            expected_left = poster.width - brand_margin - expected_width
            # The discount tile's target rectangle matches the logo's exact bounds.
            red_points = [
                (x, y)
                for y in range(brand_margin, brand_margin + expected_height + 2)
                for x in range(expected_left, poster.width - brand_margin + 1)
                if (lambda p: p[0] > 120 and p[0] > p[1] * 1.6 and p[0] > p[2] * 1.5)(
                    poster.getpixel((x, y))
                )
            ]
            self.assertTrue(red_points)
            xs = [point[0] for point in red_points]
            ys = [point[1] for point in red_points]
            self.assertLessEqual(max(xs) - min(xs) + 1, expected_width)
            self.assertGreaterEqual(max(xs) - min(xs) + 1, expected_width - 6)
            self.assertLessEqual(max(ys) - min(ys) + 1, expected_height)
            self.assertGreaterEqual(max(ys) - min(ys) + 1, expected_height - 4)

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
        # Both channel photos intentionally include both platform IDs, so artwork is identical.
        self.assertEqual(bale, canonical_telegram)

    def test_telegram_growth_invites_are_created_once_per_source_and_reused(self):
        class FakeResponse:
            def __init__(self, url):
                self.url = url
            def raise_for_status(self):
                return None
            def json(self):
                return {"ok": True, "result": {"invite_link": self.url}}

        class FakeSession:
            def __init__(self):
                self.calls = []
            def post(self, url, data=None, timeout=None):
                self.calls.append({"url": url, "data": dict(data or {}), "timeout": timeout})
                source = str(data.get("name", "")).split("-")[-1].lower()
                return FakeResponse(f"https://t.me/+test_{source}")

        state = {}
        session = FakeSession()
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertTrue(ensure_telegram_source_invites(
            state, session=session, token="test-token", chat_id="@OfferChin", now=now
        ))
        self.assertEqual(len(session.calls), 3)
        links = state["growth_tracking"]["telegram_invite_links"]
        self.assertEqual(links["aparat"]["url"], "https://t.me/+test_aparat")
        self.assertEqual(links["bale"]["url"], "https://t.me/+test_bale")
        self.assertEqual(links["youtube"]["url"], "https://t.me/+test_youtube")
        self.assertFalse(ensure_telegram_source_invites(
            state, session=FakeSession(), token="test-token", chat_id="@OfferChin", now=now
        ))

    def test_daily_member_count_snapshot_collects_each_channel_once_per_day(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []
            def post(self, url, data=None, timeout=None):
                self.calls.append((url, dict(data or {})))
                if "api.telegram.org" in url:
                    return FakeResponse({"ok": True, "result": 123})
                if url.endswith("/getChatMemberCount"):
                    return FakeResponse({"ok": False, "description": "method not found"})
                return FakeResponse({"ok": True, "result": 45})

        state = {}
        session = FakeSession()
        now = datetime(2026, 10, 20, 16, 30, tzinfo=timezone.utc)
        self.assertTrue(record_daily_member_count_snapshot(
            state,
            session=session,
            now=now,
            telegram_token="tg-token",
            telegram_chat_id="@OfferChin",
            bale_token="bale-token",
            bale_chat_id="@OfferChinBale",
        ))
        daily = state["growth_tracking"]["daily_member_counts"]["2026-10-20"]
        self.assertEqual(daily["telegram"]["count"], 123)
        self.assertEqual(daily["bale"]["count"], 45)
        calls_before = len(session.calls)
        self.assertFalse(record_daily_member_count_snapshot(
            state,
            session=session,
            now=now + timedelta(hours=1),
            telegram_token="tg-token",
            telegram_chat_id="@OfferChin",
            bale_token="bale-token",
            bale_chat_id="@OfferChinBale",
        ))
        self.assertEqual(len(session.calls), calls_before)

    def test_replaced_youtube_video_is_deleted_only_after_new_upload_is_confirmed(self):
        from affilio_radar import PERSIAN_TEXT_RENDERER_VERSION

        now = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
        record = {
            "youtube_previous_video_id": "oldBrokenShort",
            "youtube_video_id": "newReadableShort",
            "youtube_upload_status": "uploaded",
            "video_repair_priority": True,
        }
        with patch("affilio_radar.delete_youtube_video", return_value="deleted", create=True) as delete:
            changed = _delete_superseded_youtube_video(
                record, "dkp-19336870", delete, now
            )
        self.assertTrue(changed)
        delete.assert_called_once_with("oldBrokenShort")
        self.assertNotIn("youtube_previous_video_id", record)
        self.assertNotIn("video_repair_priority", record)
        self.assertEqual(record["youtube_video_renderer_version"], PERSIAN_TEXT_RENDERER_VERSION)
        self.assertEqual(record["youtube_previous_video_deleted_at"], now.isoformat())

    def test_failed_old_video_deletion_keeps_id_for_retry_without_losing_new_video(self):
        now = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
        record = {
            "youtube_previous_video_id": "oldBrokenShort",
            "youtube_video_id": "newReadableShort",
            "youtube_upload_status": "uploaded",
            "video_repair_priority": True,
        }
        with patch(
            "affilio_radar.delete_youtube_video",
            side_effect=RuntimeError("temporary YouTube delete failure"),
            create=True,
        ) as delete:
            changed = _delete_superseded_youtube_video(
                record, "dkp-19336870", delete, now
            )
        self.assertTrue(changed)
        delete.assert_called_once_with("oldBrokenShort")
        self.assertEqual(record["youtube_previous_video_id"], "oldBrokenShort")
        self.assertEqual(record["youtube_video_id"], "newReadableShort")
        self.assertIn("youtube_previous_video_delete_next_attempt_at", record)

    def test_youtube_description_uses_clean_public_channel_links(self):
        state = {
            "growth_tracking": {
                "telegram_invite_links": {
                    "aparat": {"url": "https://t.me/+from_aparat"},
                    "youtube": {"url": "https://t.me/+from_youtube"},
                }
            }
        }
        aparat_description = build_video_channel_description(state, "aparat")
        youtube_description = build_video_channel_description(state, "youtube")
        # Aparat retains its own attribution link, while YouTube uses the requested public handle.
        self.assertIn("https://t.me/+from_aparat", aparat_description)
        self.assertNotIn("https://t.me/+from_youtube", youtube_description)
        self.assertIn("کانال تلگرام:\nhttps://t.me/OfferChin", youtube_description)
        self.assertIn("کانال بله:\nhttps://ble.ir/OfferChin", youtube_description)
        self.assertIn("آپارات:\nhttps://www.aparat.com/OfferChin", youtube_description)
        self.assertNotIn("قیمت، موجودی و شرایط تخفیف", youtube_description)
        self.assertIn("https://ble.ir/OfferChin", aparat_description)
        self.assertEqual(tracked_telegram_invite_url(state, "bale"), "https://t.me/OfferChin")

    def test_video_descriptions_include_verified_product_purchase_link_when_record_is_available(self):
        state = {"growth_tracking": {"telegram_invite_links": {"aparat": {"url": "https://t.me/+from_aparat"}}}}
        record = {"product_url": "https://www.digikala.com/product/dkp-15970075/"}
        expected_affiliate = build_affilio_tracking_link(record["product_url"])
        with patch("affilio_radar._click_tracker_is_healthy", return_value=False):
            aparat_description = build_video_channel_description(state, "aparat", record=record)
            youtube_description = build_video_channel_description(state, "youtube", record=record)
        self.assertIn("لینک خرید محصول:", aparat_description)
        self.assertIn(expected_affiliate, aparat_description)
        self.assertIn(expected_affiliate, youtube_description)
        self.assertIn("https://t.me/+from_aparat", aparat_description)
        self.assertIn("https://t.me/OfferChin", youtube_description)

    def test_publication_cooldown_leaves_room_for_five_minute_scan_cadence(self):
        self.assertEqual(MIN_POST_INTERVAL_HOURS, 2 / 60)

    def test_publication_capacity_bursts_only_when_publish_queue_is_large(self):
        self.assertEqual(effective_posts_per_run(0, configured_limit=2), 1)
        self.assertEqual(effective_posts_per_run(7, configured_limit=2), 1)
        self.assertEqual(effective_posts_per_run(8, configured_limit=2), 2)
        self.assertEqual(effective_posts_per_run(17, configured_limit=2), 2)
        self.assertEqual(effective_posts_per_run(17, configured_limit=2, force_full_batch=True), 2)
        self.assertEqual(effective_posts_per_run(17, configured_limit=10, force_full_batch=True), 10)

    def test_daily_channel_count_uses_iran_calendar_day_not_youtube_quota_day(self):
        # Both posts fall on October 23 in Los Angeles, but only one falls on October 24 in Iran.
        now = datetime(2026, 10, 24, 2, 54, tzinfo=timezone.utc)
        current_iran_day = datetime(2026, 10, 23, 22, 4, tzinfo=timezone.utc).timestamp()
        previous_iran_day = datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc).timestamp()
        state = {
            "published": {
                "current-iran-day": {
                    "ts": current_iran_day,
                    "delivery_status": {"telegram": "sent", "bale": "sent"},
                },
                "previous-iran-day": {
                    "ts": previous_iran_day,
                    "delivery_status": {"telegram": "sent", "bale": "sent"},
                },
            }
        }

        self.assertEqual(daily_channel_posts_count(state, now), 1)

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



    def test_discover_product_urls_handles_due_persisted_queue_without_scope_error(self):
        now = datetime.now(timezone.utc)
        queued = {
            "dkp-91001": {
                "product_url": "https://www.digikala.com/product/dkp-91001/",
                "deal_expires_at": (now + timedelta(hours=3)).isoformat(),
            }
        }
        response = SimpleNamespace(
            status_code=200,
            content=b"{}",
            raise_for_status=lambda: None,
            json=lambda: {},
        )
        with (
            patch("affilio_radar.MAX_PRODUCT_CHECKS", 1),
            patch("affilio_radar.DEAL_LIST_PAGES", 1),
            patch("affilio_radar.SEARCH_TERMS", ("test-term",)),
            patch("affilio_radar.select_queued_records_for_recheck", return_value=[
                ("dkp-91001", queued["dkp-91001"])
            ]),
            patch("affilio_radar.SESSION.get", return_value=response),
            patch("affilio_radar.api_incredible_offer_product_candidates", return_value=[]),
            patch("expiration_monitor.fetch_mcp_offer_candidates", return_value=({}, [])),
        ):
            urls, diagnostics, expiries, direct_expiries, mcp_expiries = discover_product_urls(
                queued_records=queued,
                discovery_queue={},
                state_to_persist=None,
            )

        self.assertIn("https://www.digikala.com/product/dkp-91001/", urls)
        self.assertEqual(expiries["dkp-91001"], queued["dkp-91001"]["deal_expires_at"])
        self.assertEqual(diagnostics[0]["term"], "incredible_offers_page_1")

    def test_discovery_queue_records_all_candidates_before_detail_check_budget(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        queue = {}
        candidates = [
            {
                "product_url": "https://www.digikala.com/product/dkp-91001/",
                "title": "هدفون پیشنهادی با مهلت نزدیک",
                "deal_expires_at": (now + timedelta(hours=2)).isoformat(),
                "discount_percent": 35,
                "savings_toman": 350_000,
                "current_price": 650_000,
                "original_price": 1_000_000,
            },
            {
                "product_url": "https://www.digikala.com/product/dkp-91002/",
                "title": "چراغ کاربردی با مهلت دیرتر",
                "deal_expires_at": (now + timedelta(hours=3)).isoformat(),
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
        self.assertEqual([pid for pid, _ in selected], ["dkp-91003", "dkp-91001"])

    def test_mcp_scan_always_reads_page_one_and_rotates_supplemental_pages(self):
        self.assertEqual(mcp_scan_pages_for_cursor(5, 1, 2), ([1, 2], 3))
        self.assertEqual(mcp_scan_pages_for_cursor(5, 3, 2), ([1, 3], 4))
        self.assertEqual(mcp_scan_pages_for_cursor(5, 4, 2), ([1, 4], 5))
        self.assertEqual(mcp_scan_pages_for_cursor(5, 5, 2), ([1, 5], 2))
        self.assertEqual(mcp_scan_pages_for_cursor(1, 5, 2), ([1], 1))

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
        # A known deal inside the minimum publication runway must not consume one
        # of the limited detail-check slots; the queue will prune it at expiry.
        self.assertEqual(select_discovery_records_for_check(queue, now, max_count=5), [])
        self.assertEqual(
            select_discovery_records_for_check(queue, now + timedelta(minutes=5), max_count=5),
            [],
        )
        merge_discovery_queue(queue, [], now + timedelta(minutes=20))
        self.assertNotIn("dkp-91011", queue)

    def test_discovery_check_budget_ranks_demand_before_category_diversity(self):
        now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        recent = [
            {"product_id": f"dkp-recent-audio-{i}", "title": f"هدفون بلوتوثی نمونه {i}",
             "ts": now.timestamp() - 60 * (6 - i)}
            for i in range(6)
        ]
        queue = {}
        for pid, title, demand in [
            ("dkp-93031", "هدفون بلوتوثی مدل برتر", 95),
            ("dkp-93032", "اسپیکر بلوتوثی مدل جدید", 80),
            ("dkp-93033", "تیشرت یقه گرد مردانه مدل جدید", 25),
        ]:
            queue[pid] = {
                "product_id": pid,
                "product_url": f"https://www.digikala.com/product/{pid}/",
                "title": title,
                "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
                "demand_score": demand,
                "discount_percent": 55,
                "savings_toman": 400_000,
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "next_check_at": "",
            }
        selected = select_discovery_records_for_check(
            queue, now, max_count=2, published={}, recent_publications=recent
        )
        # The recently published headphone family is skipped. The speaker stays
        # first by demand; the lower-demand fashion candidate fills the remaining
        # bounded detail-check slot instead of starving the discovery pipeline.
        self.assertEqual([pid for pid, _ in selected], ["dkp-93032", "dkp-93033"])

    def test_discovery_checks_prioritize_demand_over_deadline_urgency(self):
        now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        queue = {
            "dkp-93021": {
                "product_id": "dkp-93021",
                "product_url": "https://www.digikala.com/product/dkp-93021/",
                "title": "popular item with longer deadline",
                "deal_expires_at": (now + timedelta(hours=4)).isoformat(),
                "demand_score": 88,
                "review_count": 2400,
                "discount_percent": 45,
                "savings_toman": 300_000,
            },
            "dkp-93022": {
                "product_id": "dkp-93022",
                "product_url": "https://www.digikala.com/product/dkp-93022/",
                "title": "less popular item with nearer deadline",
                "deal_expires_at": (now + timedelta(hours=2)).isoformat(),
                "demand_score": 28,
                "review_count": 35,
                "discount_percent": 65,
                "savings_toman": 500_000,
            },
            "dkp-93023": {
                "product_id": "dkp-93023",
                "product_url": "https://www.digikala.com/product/dkp-93023/",
                "title": "too close to expiry",
                "deal_expires_at": (now + timedelta(minutes=45)).isoformat(),
                "demand_score": 99,
                "discount_percent": 90,
                "savings_toman": 2_000_000,
            },
            "dkp-93024": {
                "product_id": "dkp-93024",
                "product_url": "https://www.digikala.com/product/dkp-93024/",
                "title": "unknown deadline",
                "deal_expires_at": "",
                "demand_score": 100,
            },
        }
        selected = select_discovery_records_for_check(queue, now, max_count=10)
        self.assertEqual([pid for pid, _ in selected], ["dkp-93024", "dkp-93021", "dkp-93022"])
        self.assertGreater(
            discovery_queue_sort_key(queue["dkp-93021"], now),
            discovery_queue_sort_key(queue["dkp-93022"], now),
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


    def test_previous_generated_short_is_rebuilt_for_current_style_version(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-old-style"
        record = {
            "ts": now.timestamp(),
            "title": "محصول قدیمی نمونه",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=3)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 55,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "generated",
            "video_style_version": 1,
            "youtube_upload_status": "pending_credentials",
            "video_file_name": f"offerchin-{pid}.mp4",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"new-style-mp4")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render) as render,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))

        render.assert_called_once()
        self.assertEqual(record["video_generation_status"], "generated")
        self.assertEqual(record["video_style_version"], VIDEO_STYLE_VERSION)
        self.assertGreater(VIDEO_STYLE_VERSION, 1)

    def test_posted_short_is_not_rejected_by_extra_twenty_minute_video_cutoff(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-video-with-fifteen-minutes-left"
        record = {
            "ts": now.timestamp(),
            "title": "محصول منتشرشده با مهلت نزدیک",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"new-short-mp4")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("aparat_uploader.aparat_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))

        self.assertEqual(record["video_generation_status"], "generated")
        self.assertNotEqual(record["video_generation_status"], "skipped_expiring_soon")

    def test_previously_skipped_video_is_requeued_if_deadline_is_still_active(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-video-previously-skipped"
        record = {
            "ts": now.timestamp(),
            "title": "پیشنهاد قبلاً ردشده اما هنوز فعال",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 40,
            "delivery_status": {"telegram": "sent"},
            "video_generation_status": "skipped_expiring_soon",
            "youtube_upload_status": "skipped_expiring_soon",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"requeued-short-mp4")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("aparat_uploader.aparat_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))

        self.assertEqual(record["video_generation_status"], "generated")
        self.assertNotEqual(record["video_generation_status"], "skipped_expiring_soon")

    def test_short_video_without_youtube_oauth_exports_manual_aparat_artifact(self):
        import short_video

        now = datetime.now(timezone.utc)
        pid = "dkp-92031"
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"fake-mp4-video")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
            patch("short_video.upload_youtube_video") as upload,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))
            self.assertEqual(record["video_generation_status"], "generated")
            self.assertEqual(record["youtube_upload_status"], "pending_credentials")
            self.assertEqual(record["video_style_version"], VIDEO_STYLE_VERSION)
            self.assertTrue((Path(output_dir) / f"offerchin-{pid}.mp4").is_file())
            upload.assert_not_called()

    def test_aparat_short_only_mode_queues_vertical_video_without_regular_upload(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-92033"
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه برای شورتس",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"fake-mp4-video")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("affilio_radar.APARAT_SHORTS_ONLY", True),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
            patch("aparat_uploader.aparat_credentials_available", return_value=True),
            patch("aparat_uploader.upload_aparat_video") as upload_aparat,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))
            self.assertTrue((Path(output_dir) / f"offerchin-{pid}.mp4").is_file())

        self.assertEqual(record["video_generation_status"], "generated")
        self.assertEqual(record["aparat_upload_status"], "waiting_shorts_uploader")
        self.assertEqual(record["aparat_shorts_upload_status"], "queued")
        upload_aparat.assert_not_called()

    def test_aparat_auto_upload_is_enabled_for_public_vertical_video(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-92034"
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه برای انتشار خودکار آپارات",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"fake-vertical-mp4")
            return output

        aparat_result = {
            "video_id": "73819999",
            "video_hash": "shorttestuid",
            "url": "https://www.aparat.com/v/shorttestuid",
            "visibility": "public",
        }
        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("affilio_radar.APARAT_SHORTS_ONLY", False),
            patch("short_video.youtube_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
            patch("aparat_uploader.aparat_credentials_available", return_value=True),
            patch("aparat_uploader.upload_aparat_video", return_value=aparat_result) as upload_aparat,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))
            self.assertTrue((Path(output_dir) / f"offerchin-{pid}.mp4").is_file())
            upload_aparat.assert_called_once()

        self.assertEqual(record["video_generation_status"], "generated")
        self.assertEqual(record["aparat_upload_status"], "uploaded")
        self.assertEqual(record["aparat_visibility"], "public")
        self.assertEqual(record["aparat_video_url"], "https://www.aparat.com/v/shorttestuid")

    def test_short_video_upload_uses_youtube_when_oauth_is_configured(self):
        import short_video

        now = datetime.now(timezone.utc)
        pid = "dkp-92032"
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه دوم",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 60,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"fake-mp4-video")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=True),
            patch("short_video.render_short_video", side_effect=fake_render),
            patch("short_video.upload_youtube_video", return_value={
                "video_id": "yt_test_123",
                "url": "https://www.youtube.com/shorts/yt_test_123",
            }) as upload,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))
            upload.assert_called_once()
            self.assertEqual(record["video_generation_status"], "generated")
            self.assertEqual(record["youtube_upload_status"], "uploaded")
            self.assertEqual(record["youtube_video_id"], "yt_test_123")
            self.assertEqual(record["youtube_video_url"], "https://www.youtube.com/shorts/yt_test_123")
            uploaded_at = datetime.fromisoformat(record["youtube_uploaded_at"])
            next_upload_at = datetime.fromisoformat(state["youtube_next_upload_at"])
            self.assertEqual(
                next_upload_at,
                uploaded_at + timedelta(hours=YOUTUBE_UPLOAD_INTERVAL_HOURS),
            )
            self.assertEqual(state["youtube_last_upload_success_at"], record["youtube_uploaded_at"])



    def test_youtube_upload_waits_three_hours_after_previous_success_and_selects_late(self):
        now = datetime.now(timezone.utc)
        prior_uploaded_at = now - timedelta(hours=1)
        prior_id = "dkp-previous-youtube-success"
        pending_id = "dkp-youtube-waiting-slot"
        prior = {
            "title": "ویدئوی قبلی",
            "youtube_upload_status": "uploaded",
            "youtube_uploaded_at": prior_uploaded_at.isoformat(),
            "video_generation_status": "generated",
            "delivery_status": {"telegram": "sent"},
        }
        pending = {
            "ts": now.timestamp(),
            "title": "پیشنهاد بهتر برای اسلات بعدی",
            "product_url": f"https://www.digikala.com/product/{pending_id}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=4)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 80,
            "demand_score": 90,
            "promo_score": 80,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {prior_id: prior, pending_id: pending}}
        expected_next = prior_uploaded_at + timedelta(hours=YOUTUBE_UPLOAD_INTERVAL_HOURS)

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image") as fetch_image,
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=True),
            patch("aparat_uploader.aparat_credentials_available", return_value=False),
            patch("short_video.telegram_video_review_available", return_value=False),
            patch("short_video.render_short_video") as render,
            patch("short_video.upload_youtube_video") as upload,
        ):
            self.assertFalse(process_pending_short_video(state, now=now, output_dir=output_dir))

        self.assertEqual(state["youtube_next_upload_at"], expected_next.isoformat())
        fetch_image.assert_not_called()
        render.assert_not_called()
        upload.assert_not_called()

    def test_youtube_upload_failure_preserves_http_diagnostic_for_retry(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-youtube-http-diagnostic"
        diagnostic = (
            "YouTube video content upload HTTP 429 reason=rateLimitExceeded "
            "message=Quota exceeded for Video Uploads per day."
        )
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه برای تشخیص خطای یوتیوب",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=3)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent", "bale": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        state = {"published": {pid: record}}

        def fake_render(image_bytes, discount, path, **kwargs):
            output = Path(path)
            output.write_bytes(b"diagnostic-test-mp4")
            return output

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image", return_value=b"fake-image"),
            patch("affilio_radar.save_json"),
            patch("short_video.youtube_credentials_available", return_value=True),
            patch("aparat_uploader.aparat_credentials_available", return_value=False),
            patch("short_video.render_short_video", side_effect=fake_render),
            patch("short_video.upload_youtube_video", side_effect=RuntimeError(diagnostic)),
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))

        self.assertEqual(record["youtube_upload_status"], "retry")
        self.assertIn("HTTP 429", record["youtube_last_error"])
        self.assertIn("rateLimitExceeded", record["youtube_last_error"])
        self.assertIn("Video Uploads per day", record["youtube_last_error"])
        self.assertIsNotNone(record.get("youtube_next_attempt_at"))
        retry_at = datetime.fromisoformat(record["youtube_next_attempt_at"])
        self.assertGreaterEqual(retry_at, now + timedelta(hours=24))
        self.assertLess(retry_at, now + timedelta(hours=25))
        self.assertEqual(state["youtube_uploads_paused_until"], record["youtube_next_attempt_at"])
        self.assertEqual(state["youtube_upload_pause_reason"], "daily_upload_limit")

    def test_youtube_daily_limit_pause_does_not_block_aparat_shorts_queue(self):
        now = datetime.now(timezone.utc)
        pid = "dkp-youtube-daily-pause"
        record = {
            "ts": now.timestamp(),
            "title": "گجت نمونه در زمان توقف سهمیه",
            "product_url": f"https://www.digikala.com/product/{pid}/",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/sample.jpg",
            "expires_at": (now + timedelta(hours=3)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "posted_discount_percent": 45,
            "delivery_status": {"telegram": "sent"},
            "video_generation_status": "pending",
            "youtube_upload_status": "pending",
        }
        record["youtube_last_error"] = (
            "HTTPError: YouTube resumable upload initialization HTTP 400 "
            "reason=uploadLimitExceeded message=The user has exceeded the number of videos they may upload."
        )
        record["youtube_upload_attempts"] = 1
        pause_until = (now + timedelta(hours=24, minutes=15)).isoformat()
        # Simulate persisted state written by the old code before the global pause existed.
        state = {"published": {pid: record}}

        with (
            TemporaryDirectory() as output_dir,
            patch("affilio_radar._fetch_image") as fetch_image,
            patch("affilio_radar.save_json"),
            patch("affilio_radar.APARAT_SHORTS_ONLY", True),
            patch("short_video.youtube_credentials_available", return_value=True),
            patch("aparat_uploader.aparat_credentials_available", return_value=True),
            patch("short_video.render_short_video") as render,
            patch("short_video.upload_youtube_video") as upload,
        ):
            self.assertTrue(process_pending_short_video(state, now=now, output_dir=output_dir))

        # YouTube remains paused, but the independent Aparat Shorts queue still advances.
        fetch_image.assert_called_once()
        render.assert_called_once()
        upload.assert_not_called()
        self.assertEqual(record["aparat_upload_status"], "waiting_shorts_uploader")
        self.assertEqual(record["aparat_shorts_upload_status"], "queued")
        self.assertEqual(state["youtube_uploads_paused_until"], pause_until)
        self.assertEqual(state["youtube_upload_pause_reason"], "daily_upload_limit")
        self.assertTrue(state["youtube_upload_pause_diagnostic_migrated"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is installed by the publishing workflow")
    def test_real_short_video_renderer_creates_vertical_mp4(self):
        import short_video

        image_buffer = BytesIO()
        Image.new("RGB", (480, 480), (30, 140, 90)).save(image_buffer, format="JPEG")
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "renderer-smoke-test.mp4"
            rendered = short_video.render_short_video(
                image_buffer.getvalue(),
                discount_percent=35,
                output_path=output_path,
                duration_seconds=5,
                fps=12,
            )
            self.assertTrue(rendered.is_file())
            self.assertGreater(rendered.stat().st_size, 1024)

            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name,channels",
                    "-of", "json", str(rendered),
                ],
                check=True, capture_output=True, text=True, timeout=30,
            )
            audio_streams = json.loads(probe.stdout).get("streams", [])
            self.assertTrue(audio_streams, "rendered short should contain a music track")
            self.assertEqual(audio_streams[0].get("codec_name"), "aac")

if __name__ == "__main__":
    unittest.main()
