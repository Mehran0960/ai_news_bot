import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from relay_botapi import (
    extract_product_refs,
    make_affiliate_url,
    normalize_store_host,
    resolve_product_ref,
    clean_caption,
    extract_product_details,
    build_caption,
    CHANNEL_FOLLOW_HTML,
    photo_url_from_node,
    fill_price_fallback,
    summarize_source_description,
    is_generic_store_title,
    parse_view_count,
    classify_product_category,
    score_product_potential,
    select_next_candidate,
    extract_source_price_values,
    rank_archive_candidates,
    extract_image_price_values,
    compare_image_prices_to_product,
    select_next_price_verified_candidate,
    PUBLISH_SLOTS,
    SLOT_GRACE_MINUTES,
    ensure_price_check_version,
    MAX_PRICE_CHECK_CANDIDATES_PER_RUN,
    best_price_safe_crop_box,
    extract_product_video_url,
    safe_product_video_url,
)

class DayanRelayTests(unittest.TestCase):
    def test_lead_route_is_preserved(self):
        self.assertEqual(
            extract_product_refs("ادرس فروشگااه/lead/51366"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_fastcart_code_from_caption(self):
        self.assertEqual(
            extract_product_refs("لینک کد 39612 را در این قسمت وارد کنید"),
            [{"route": "fastcart", "code": "39612"}],
        )

    def test_route_wins_over_duplicate_labeled_code(self):
        self.assertEqual(
            extract_product_refs("لینک /lead/51366 و لینک کد 51366"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_persian_digits_are_normalized(self):
        self.assertEqual(
            extract_product_refs("لینک /lead/۵۱۳۶۶"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_make_lead_url(self):
        self.assertEqual(
            make_affiliate_url("https://seller.affdn.com", {"route": "lead", "code": "51366"}),
            "https://seller.affdn.com/lead/51366",
        )

    def test_make_fastcart_url(self):
        self.assertEqual(
            make_affiliate_url("https://seller.affdn.ir", {"route": "fastcart", "code": "39612"}),
            "https://seller.affdn.ir/fastcart/39612",
        )

    def test_rejects_unrelated_store_domain(self):
        with self.assertRaises(RuntimeError):
            normalize_store_host("https://example.com")

    def test_rejects_store_path_in_secret(self):
        with self.assertRaises(RuntimeError):
            normalize_store_host("https://seller.affdn.ir/fastcart/1234")

    def test_ambiguous_code_is_not_autoselected(self):
        item = {
            "source_message_id": 100,
            "product_refs": [
                {"route": "lead", "code": "51366"},
                {"route": "fastcart", "code": "51366"},
            ],
        }
        self.assertIsNone(resolve_product_ref(item, {}))

    def test_manual_override_route(self):
        item = {"source_message_id": 101, "product_refs": []}
        self.assertEqual(
            resolve_product_ref(item, {"101": {"route": "lead", "product_code": "51366"}}),
            {"route": "lead", "code": "51366"},
        )

    def test_store_placeholder_is_removed_from_caption(self):
        self.assertEqual(clean_caption("ادرس فروشگااه/lead/51366"), "")


    def test_extracts_product_title_and_both_prices(self):
        page = """
        <html><head><meta property="og:title" content="ایران گجت"></head>
        <body><h1>دسته های طرح PS5 بی سیم بلوتوثی به همراه دانگل اتصال</h1>
          <p>قیمت اصلی: 7,639,000 تومان</p>
          <p>قیمت با تخفیف: 5,789,000 تومان</p>
        </body></html>
        """
        details = extract_product_details(page)
        self.assertIn("PS5", details["title"])
        self.assertEqual(details["original_price"], "7,639,000 تومان")
        self.assertEqual(details["discounted_price"], "5,789,000 تومان")

    def test_caption_contains_benefits_and_strikes_original_price(self):
        caption = build_caption(
            "قیمت اصلی: 7,639,000 تومان؛ قیمت تخفیفی: 5,789,000 تومان",
            "https://seller.affdn.ir/lead/51366",
            product_details={
                "title": "دسته های PS5",
                "original_price": "7,639,000 تومان",
                "discounted_price": "5,789,000 تومان",
            },
        )
        self.assertIn("<s>7,639,000 تومان</s>", caption)
        self.assertIn("<b>5,789,000 تومان</b>", caption)
        self.assertIn("✅ پرداخت درب منزل", caption)
        self.assertIn("✅ ارسال به سراسر کشور", caption)
        self.assertIn("✅ گارانتی تعویض و برگشت", caption)
        self.assertNotIn("🧪 نمونهٔ آزمایشی انتشار خودکار", caption)
        self.assertNotIn("#اینستاگرام", caption)
        self.assertNotIn("لینک همکاری در فروش است", caption)
        self.assertTrue(caption.rstrip().endswith(CHANNEL_FOLLOW_HTML))
        self.assertIn('<a href="https://t.me/Iran_gajet">📣 ایران گجت | @Iran_gajet</a>', caption)

    def test_live_product_page_prices_are_kept_when_source_creative_is_older(self):
        caption = build_caption(
            "هدفون بلوتوثی JBL مدل 48486",
            "https://seller.affdn.ir/fastcart/48486",
            product_details={
                "title": "هدفون بلوتوثی JBL مدل 48486",
                "original_price": "1,969,000 تومان",
                "discounted_price": "1,499,000 تومان",
            },
        )
        self.assertIn("<s>1,969,000 تومان</s>", caption)
        self.assertIn("<b>1,499,000 تومان</b>", caption)

    def test_instagram_hashtag_is_removed_from_source_caption(self):
        self.assertEqual(clean_caption("ادرس فروشگااه/lead/51366 #اینستاگرام"), "")

    def test_extracts_photo_url_from_telegram_post(self):
        html = """<div class="tgme_widget_message_photo_wrap"
        style="width:640px;background-image:url('https://cdn4.telesco.pe/file/photo.jpg')"></div>"""
        node = BeautifulSoup("<div>" + html + "</div>", "html.parser").div
        self.assertEqual(
            photo_url_from_node(node),
            "https://cdn4.telesco.pe/file/photo.jpg",
        )

    def test_fallback_price_pair_from_source_caption(self):
        details = fill_price_fallback(
            "🔥 ۵.۷۸۹ میلیون ۷.۶۳۹ میلیون 🚚 ارسال سریع و ارزان",
            {"title": "گیم استیک M15 مدل 51366", "original_price": None, "discounted_price": None},
        )
        self.assertEqual(details["original_price"], "7,639,000 تومان")
        self.assertEqual(details["discounted_price"], "5,789,000 تومان")

    def test_caption_fallback_cleans_source_placeholder(self):
        caption = build_caption(
            "گیم استیک M15؛ 🔥 ۵.۷۸۹ میلیون ۷.۶۳۹ میلیون؛ ادرس دامنه/fastcart/51366 #پیامرسانیداخلی",
            "https://seller.affdn.ir/fastcart/51366",
            product_details={"title": "گیم استیک M15 مدل 51366", "original_price": None, "discounted_price": None},
        )
        self.assertIn("<s>7,639,000 تومان</s>", caption)
        self.assertIn("<b>5,789,000 تومان</b>", caption)
        self.assertNotIn("ادرس دامنه", caption)
        self.assertNotIn("#پیامرسانیداخلی", caption)
        self.assertTrue(caption.rstrip().endswith(CHANNEL_FOLLOW_HTML))

    def test_store_name_is_not_used_as_product_title(self):
        self.assertTrue(is_generic_store_title("ایران گجت"))
        self.assertFalse(is_generic_store_title("گیم استیک M15 مدل 51366"))

    def test_compact_description_extracts_useful_specs(self):
        summary = summarize_source_description(
            "😳 ۱۰,۰۰۰+ بازی توی یه کنسول؟! 🔥 فقط وصلش کن به تلویزیون! خروجی 4K | حافظه ۶۴GB | ۲ دسته بی‌سیم 👇 ببین چه بازی‌هایی داخلشه!",
            original="7,639,000 تومان",
            discounted="5,789,000 تومان",
        )
        self.assertIn("بازی", summary)
        self.assertIn("4K", summary)
        self.assertIn("حافظه 64GB", summary)
        self.assertIn("دستهٔ بی‌سیم", summary)
        self.assertLessEqual(len(summary), 150)

    def test_caption_removes_duplicate_abbreviated_prices_and_source_tags(self):
        caption = build_caption(
            "🔥 ۵.۷۸۹ میلیون ۷.۶۳۹ میلیون 🚚 ارسال سریع و ارزان | 💳 پرداخت درب منزل #پیامرسانیداخلی",
            "https://seller.affdn.ir/fastcart/51366",
            product_details={
                "title": "گیم استیک M15 مدل 51366",
                "original_price": "7,639,000 تومان",
                "discounted_price": "5,789,000 تومان",
            },
        )
        self.assertNotIn("۵.۷۸۹ میلیون", caption)
        self.assertNotIn("۷.۶۳۹ میلیون", caption)
        self.assertNotIn("#پیامرسانیداخلی", caption)
        self.assertNotIn("💳 پرداخت درب منزل", caption)
        self.assertTrue(caption.rstrip().endswith(CHANNEL_FOLLOW_HTML))

    def test_parses_telegram_view_count_suffixes(self):
        self.assertEqual(parse_view_count("12.5K"), 12500)
        self.assertEqual(parse_view_count("1.4M"), 1400000)
        self.assertEqual(parse_view_count("۱۲۳۴"), 1234)

    def test_classifies_gaming_gadget(self):
        self.assertEqual(classify_product_category("گیم استیک M15 با بیش از ۱۰٬۰۰۰ بازی"), "gaming")

    def test_classifies_power_banks_as_a_current_demand_signal(self):
        self.assertEqual(classify_product_category("پاوربانک 20000mAh با شارژ سریع"), "power_backup")

    def test_classifies_audio_and_wearables_as_high_interest_digital_goods(self):
        self.assertEqual(classify_product_category("ساعت هوشمند و هندزفری بلوتوثی"), "audio_wearables")

    def test_extracts_prices_without_confusing_game_count(self):
        self.assertEqual(
            extract_source_price_values("۱۰٬۰۰۰ بازی؛ فقط ۵.۷۸۹ میلیون تومان، قیمت قبلی ۷.۶۳۹ میلیون تومان"),
            [5789000, 7639000],
        )

    def test_product_score_uses_engagement_and_discount_signals(self):
        now = __import__("datetime").datetime.fromisoformat("2026-10-15T12:00:00+00:00")
        high_views = score_product_potential({
            "source_caption": "گیم استیک M15؛ قیمت 7,639,000 تومان و قیمت تخفیفی 5,789,000 تومان؛ خروجی 4K",
            "views": 1000,
            "source_date": "2026-10-15T11:00:00+00:00",
        }, now=now)
        low_views = score_product_potential({
            "source_caption": "گیم استیک M15؛ قیمت 7,639,000 تومان و قیمت تخفیفی 5,789,000 تومان؛ خروجی 4K",
            "views": 10,
            "source_date": "2026-10-15T11:00:00+00:00",
        }, now=now)
        self.assertEqual(high_views["category"], "gaming")
        self.assertEqual(high_views["price_toman"], 5789000)
        self.assertGreater(high_views["score"], low_views["score"])
        self.assertGreater(high_views["market_demand_score"], low_views["market_demand_score"])

    def test_video_is_absolute_priority_even_if_demand_score_is_lower(self):
        photo = {"source_message_id": 100, "media_type": "photo", "popularity_score": 74,
                 "market_demand_score": 70,
                 "product_refs": [{"route": "lead", "code": "11111"}]}
        video = {"source_message_id": 101, "media_type": "video", "popularity_score": 45,
                 "market_demand_score": 12,
                 "product_refs": [{"route": "lead", "code": "22222"}]}
        chosen, product_ref = select_next_candidate([photo, video], {})
        self.assertEqual(chosen["source_message_id"], 101)
        self.assertEqual(product_ref["code"], "22222")

    def test_video_wins_when_market_demand_ties_even_if_total_score_is_lower(self):
        photo = {"source_message_id": 110, "media_type": "photo", "popularity_score": 88,
                 "market_demand_score": 65,
                 "product_refs": [{"route": "lead", "code": "11112"}]}
        video = {"source_message_id": 111, "media_type": "video", "popularity_score": 62,
                 "market_demand_score": 65,
                 "product_refs": [{"route": "lead", "code": "22223"}]}
        chosen, _ = select_next_candidate([photo, video], {})
        self.assertEqual(chosen["source_message_id"], 111)

    def test_iran_market_demand_categories_get_higher_score(self):
        now = __import__("datetime").datetime.fromisoformat("2026-10-15T12:00:00+00:00")
        demand_product = score_product_potential({
            "source_caption": "گوشی هوشمند؛ اقتصادی با تخفیف",
            "views": 100,
            "source_date": "2026-10-15T11:00:00+00:00",
        }, now=now)
        unknown_product = score_product_potential({
            "source_caption": "وسیله متفرقه برای استفاده روزمره",
            "views": 100,
            "source_date": "2026-10-15T11:00:00+00:00",
        }, now=now)
        self.assertEqual(demand_product["category"], "smartphones")
        self.assertGreater(demand_product["market_demand_score"], unknown_product["market_demand_score"])

    def test_selector_skips_previously_published_product_code(self):
        candidate = {"source_message_id": 100, "media_type": "video", "popularity_score": 90,
                     "product_refs": [{"route": "lead", "code": "11111"}]}
        chosen, product_ref = select_next_candidate([candidate], {}, {"11111"})
        self.assertIsNone(chosen)
        self.assertIsNone(product_ref)

    def test_photo_is_fallback_when_no_video_is_queued(self):
        photo = {"source_message_id": 100, "media_type": "photo", "popularity_score": 30,
                 "product_refs": [{"route": "lead", "code": "11111"}]}
        chosen, _ = select_next_candidate([photo], {})
        self.assertEqual(chosen["source_message_id"], 100)


    def test_archive_candidate_ranking_prioritizes_video_over_demand_score(self):
        now = __import__("datetime").datetime.fromisoformat("2026-10-15T12:00:00+00:00")
        posts = [
            {
                "source_message_id": 100,
                "source_caption": "گوشی هوشمند اقتصادی با تخفیف، قیمت 3,000,000 تومان",
                "product_refs": [{"route": "lead", "code": "11111"}],
                "photo_url": "https://cdn4.telesco.pe/file/phone.jpg",
                "views": 1000,
                "source_date": "2026-10-15T11:00:00+00:00",
            },
            {
                "source_message_id": 101,
                "source_caption": "گیم استیک با تخفیف، قیمت 3,000,000 تومان",
                "product_refs": [{"route": "lead", "code": "22222"}],
                "video_url": "https://cdn4.telesco.pe/file/game.mp4",
                "views": 1000,
                "source_date": "2026-10-15T11:00:00+00:00",
            },
        ]
        ranked = rank_archive_candidates(posts, {}, now=now)
        chosen, product_ref = select_next_candidate(ranked, {})
        self.assertEqual(chosen["source_message_id"], 101)
        self.assertEqual(chosen["media_type"], "video")
        self.assertEqual(product_ref["code"], "22222")

    def test_archive_candidate_ranking_deduplicates_product_and_uses_freshest_post(self):
        posts = [
            {
                "source_message_id": 100,
                "source_caption": "گوشی هوشمند اقتصادی",
                "product_refs": [{"route": "lead", "code": "33333"}],
                "photo_url": "https://cdn4.telesco.pe/file/older.jpg",
                "views": 500,
                "source_date": "2026-10-14T11:00:00+00:00",
            },
            {
                "source_message_id": 120,
                "source_caption": "گوشی هوشمند اقتصادی",
                "product_refs": [{"route": "lead", "code": "33333"}],
                "video_url": "https://cdn4.telesco.pe/file/newer.mp4",
                "views": 500,
                "source_date": "2026-10-15T11:00:00+00:00",
            },
        ]
        ranked = rank_archive_candidates(posts, {})
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["source_message_id"], 120)
        self.assertEqual(ranked[0]["media_type"], "video")

    def test_archive_candidate_ranking_excludes_sent_products_and_source_ids(self):
        posts = [
            {
                "source_message_id": 130,
                "source_caption": "پاوربانک",
                "product_refs": [{"route": "lead", "code": "44444"}],
                "photo_url": "https://cdn4.telesco.pe/file/one.jpg",
            },
            {
                "source_message_id": 131,
                "source_caption": "پاوربانک",
                "product_refs": [{"route": "lead", "code": "55555"}],
                "video_url": "https://cdn4.telesco.pe/file/two.mp4",
            },
        ]
        ranked = rank_archive_candidates(
            posts, {}, sent_product_codes={"44444"}, sent_source_ids={131}
        )
        self.assertEqual(ranked, [])


    def test_image_price_extraction_handles_persian_and_english_digits(self):
        self.assertEqual(
            extract_image_price_values("قیمت اصلی ۱٬۹۶۹٬۰۰۰ تومان\nقیمت تخفیفی 1,499,000 تومان"),
            [1499000, 1969000],
        )

    def test_image_price_verification_accepts_prices_that_match_live_product_page(self):
        result = compare_image_prices_to_product(
            "قیمت اصلی ۱٬۹۶۹٬۰۰۰ تومان\nقیمت تخفیفی ۱٬۴۹۹٬۰۰۰ تومان",
            {"original_price": "1,969,000 تومان", "discounted_price": "1,499,000 تومان"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "match")

    def test_image_price_verification_rejects_mismatched_current_price(self):
        result = compare_image_prices_to_product(
            "قیمت تخفیفی ۱٬۲۹۹٬۰۰۰ تومان",
            {"original_price": "1,969,000 تومان", "discounted_price": "1,499,000 تومان"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["mismatched_prices"], [1299000])

    def test_image_price_verification_fails_closed_when_price_cue_is_unreadable(self):
        result = compare_image_prices_to_product(
            "قیمت تخفیفی ویژه",
            {"discounted_price": "1,499,000 تومان"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unverifiable")

    def test_media_without_visible_price_can_use_live_caption_price(self):
        result = compare_image_prices_to_product(
            "هدفون بلوتوثی JBL",
            {"discounted_price": "1,499,000 تومان"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "no_price_detected")

    @patch("relay_botapi.check_source_media_prices")
    @patch("relay_botapi.fetch_product_details")
    def test_price_rejection_skips_first_video_and_selects_next_video(self, fetch_details, check_prices):
        top = {
            "source_message_id": 201, "media_type": "video",
            "market_demand_score": 70, "popularity_score": 85,
            "product_refs": [{"route": "lead", "code": "11111"}],
        }
        next_item = {
            "source_message_id": 202, "media_type": "video",
            "market_demand_score": 60, "popularity_score": 75,
            "product_refs": [{"route": "lead", "code": "22222"}],
        }
        first_details = {"discounted_price": "1,499,000 تومان"}
        second_details = {"discounted_price": "799,000 تومان"}
        fetch_details.side_effect = [first_details, second_details]
        check_prices.side_effect = [
            {"ok": False, "status": "mismatch", "image_prices": [1299000], "page_prices": [1499000]},
            {"ok": True, "status": "match", "image_prices": [799000], "page_prices": [799000]},
        ]
        queue = [top, next_item]
        state = {}
        chosen, ref, details, safe_photo_path = select_next_price_verified_candidate(
            queue, {}, set(), "https://shop.example.affdn.ir", state
        )
        self.assertEqual(chosen["source_message_id"], 202)
        self.assertEqual(ref["code"], "22222")
        self.assertEqual(details, second_details)
        self.assertIsNone(safe_photo_path)
        self.assertEqual(state["price_rejected_source_ids"], [201])
        self.assertEqual(state["price_rejected_product_codes"], [])
        self.assertNotIn(top, queue)



    def test_scheduler_has_half_hour_publication_slots(self):
        self.assertEqual(
            PUBLISH_SLOTS,
            [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)],
        )
        self.assertEqual(SLOT_GRACE_MINUTES, 25)


    def test_image_price_extraction_recognizes_compact_thousand_prices(self):
        self.assertEqual(
            extract_image_price_values("قیمت تخفیفی ۱,۴۱۹"),
            [1419000],
        )
        self.assertEqual(
            extract_image_price_values("قیمت ویژه ۲۹ هزار تومان"),
            [29000],
        )

    def test_price_verifier_upgrade_clears_old_ocr_rejections_once(self):
        state = {
            "price_check_version": 4,
            "price_rejected_source_ids": [21268, 21574],
            "price_rejected_product_codes": ["50436", "43765"],
        }
        ensure_price_check_version(state)
        self.assertEqual(state["price_check_version"], 5)
        self.assertEqual(state["price_rejected_source_ids"], [])
        self.assertEqual(state["price_rejected_product_codes"], [])
        state["price_rejected_source_ids"] = [777]
        ensure_price_check_version(state)
        self.assertEqual(state["price_rejected_source_ids"], [777])


    def test_compact_image_price_mismatch_is_rejected(self):
        result = compare_image_prices_to_product(
            "قیمت تخفیفی ۱,۴۱۹",
            {"discounted_price": "1,059,000 تومان"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["mismatched_prices"], [1419000])


    def test_each_slot_can_check_enough_candidates_to_find_a_valid_post(self):
        self.assertEqual(MAX_PRICE_CHECK_CANDIDATES_PER_RUN, 12)


    def test_video_wins_same_product_even_when_photo_is_newer(self):
        posts = [
            {
                "source_message_id": 250,
                "source_caption": "کالای کاربردی",
                "product_refs": [{"route": "lead", "code": "67890"}],
                "video_url": "https://cdn4.telesco.pe/file/product-video.mp4",
                "source_date": "2026-10-14T10:00:00+00:00",
            },
            {
                "source_message_id": 300,
                "source_caption": "کالای کاربردی",
                "product_refs": [{"route": "lead", "code": "67890"}],
                "photo_url": "https://cdn4.telesco.pe/file/product-photo.jpg",
                "source_date": "2026-10-15T10:00:00+00:00",
            },
        ]
        ranked = rank_archive_candidates(posts, {})
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["source_message_id"], 250)
        self.assertEqual(ranked[0]["media_type"], "video")

    def test_best_price_safe_crop_box_removes_bottom_price_strip(self):
        crop = best_price_safe_crop_box(
            1000, 1000, [(40, 800, 960, 960)], min_area_ratio=0.58
        )
        self.assertIsNotNone(crop)
        left, top, right, bottom = crop
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right, 1000)
        self.assertLessEqual(bottom, 800)
        self.assertGreaterEqual((right-left)*(bottom-top), 580000)

    def test_best_price_safe_crop_returns_none_when_no_crop_preserves_enough_image(self):
        crop = best_price_safe_crop_box(
            1000, 1000, [(300, 300, 700, 700)], min_area_ratio=0.58
        )
        self.assertIsNone(crop)

    @patch("relay_botapi.prepare_price_cropped_photo")
    @patch("relay_botapi.fetch_product_details")
    def test_photo_candidate_is_only_selected_after_price_area_is_removed(self, fetch_details, crop_photo):
        photo = {
            "source_message_id": 350, "media_type": "photo",
            "market_demand_score": 70, "popularity_score": 80,
            "product_refs": [{"route": "lead", "code": "76543"}],
        }
        page_details = {"original_price": "900,000 تومان", "discounted_price": "700,000 تومان"}
        fetch_details.return_value = page_details
        crop_photo.return_value = (
            "/tmp/verified-price-free-photo.jpg",
            {"ok": True, "status": "price_removed", "image_prices": [650000], "page_prices": [700000, 900000], "crop_method": "cropped"},
        )
        chosen, ref, details, path = select_next_price_verified_candidate(
            [photo], {}, set(), "https://shop.example.affdn.ir", {}
        )
        self.assertEqual(chosen["source_message_id"], 350)
        self.assertEqual(ref["code"], "76543")
        self.assertEqual(details, page_details)
        self.assertEqual(path, "/tmp/verified-price-free-photo.jpg")
        crop_photo.assert_called_once_with(photo, page_details)



    def test_product_page_direct_video_source_is_extracted(self):
        html = """
        <html><head><title>Product</title></head><body>
          <div class="product-gallery">
            <video controls><source src="/media/item-demo.mp4" type="video/mp4"></video>
          </div>
        </body></html>
        """
        self.assertEqual(
            extract_product_video_url(html, "https://shop.example.com/fastcart/12345"),
            "https://shop.example.com/media/item-demo.mp4",
        )

    def test_product_page_video_from_same_site_cdn_is_allowed(self):
        html = """
        <html><head>
          <meta property="og:video" content="https://cdn.example.com/assets/12345-demo.mp4">
        </head></html>
        """
        self.assertEqual(
            extract_product_video_url(html, "https://shop.example.com/fastcart/12345"),
            "https://cdn.example.com/assets/12345-demo.mp4",
        )

    def test_unrelated_product_video_host_is_rejected(self):
        self.assertIsNone(
            safe_product_video_url(
                "https://unrelated-video-host.net/item.mp4",
                "https://shop.example.com/fastcart/12345",
                explicit_video_source=True,
            )
        )

    def test_relative_non_video_file_is_not_treated_as_video(self):
        self.assertIsNone(
            safe_product_video_url(
                "/images/product.jpg",
                "https://shop.example.com/fastcart/12345",
                explicit_video_source=False,
            )
        )


    def test_generic_hero_video_is_not_mistaken_for_a_product_demo(self):
        html = """
        <html><body>
          <header class="hero-banner">
            <video autoplay><source src="/assets/brand-promo.mp4" type="video/mp4"></video>
          </header>
          <h1>هدفون بی‌سیم</h1>
        </body></html>
        """
        self.assertIsNone(
            extract_product_video_url(html, "https://shop.example.com/fastcart/12345")
        )


    @patch("relay_botapi.check_source_media_prices")
    @patch("relay_botapi.fetch_product_details")
    def test_product_page_video_is_preferred_for_source_video_candidate(self, fetch_details, check_prices):
        source_video = {
            "source_message_id": 401, "media_type": "video",
            "video_url": "https://cdn4.telesco.pe/file/source.mp4",
            "market_demand_score": 60, "popularity_score": 75,
            "product_refs": [{"route": "lead", "code": "44441"}],
        }
        page_details = {
            "title": "محصول آزمایشی",
            "discounted_price": "799,000 تومان",
            "original_price": "999,000 تومان",
            "video_url": "https://shop.example.affdn.ir/media/demo.mp4",
            "video_page_url": "https://shop.example.affdn.ir/lead/44441",
        }
        fetch_details.return_value = page_details
        check_prices.return_value = {
            "ok": True, "status": "no_price_detected",
            "image_prices": [], "page_prices": [799000, 999000],
        }
        chosen, ref, details, safe_photo_path = select_next_price_verified_candidate(
            [source_video], {}, set(), "https://shop.example.affdn.ir", {}
        )
        self.assertEqual(chosen["source_message_id"], 401)
        self.assertEqual(chosen["product_video_url"], page_details["video_url"])
        self.assertEqual(ref["code"], "44441")
        self.assertEqual(details, page_details)
        self.assertIsNone(safe_photo_path)
        check_prices.assert_called_once()
        checked_item = check_prices.call_args.args[0]
        self.assertEqual(checked_item["product_video_url"], page_details["video_url"])

    @patch("relay_botapi.check_source_media_prices")
    @patch("relay_botapi.fetch_product_details")
    def test_source_video_is_fallback_when_product_page_video_fails_price_check(self, fetch_details, check_prices):
        source_video = {
            "source_message_id": 402, "media_type": "video",
            "video_url": "https://cdn4.telesco.pe/file/source-fallback.mp4",
            "market_demand_score": 60, "popularity_score": 75,
            "product_refs": [{"route": "lead", "code": "44442"}],
        }
        page_details = {
            "title": "محصول آزمایشی",
            "discounted_price": "799,000 تومان",
            "original_price": "999,000 تومان",
            "video_url": "https://shop.example.affdn.ir/media/stale-demo.mp4",
            "video_page_url": "https://shop.example.affdn.ir/lead/44442",
        }
        fetch_details.return_value = page_details
        check_prices.side_effect = [
            {"ok": False, "status": "mismatch", "image_prices": [699000], "page_prices": [799000, 999000]},
            {"ok": True, "status": "no_price_detected", "image_prices": [], "page_prices": [799000, 999000]},
        ]
        chosen, ref, details, safe_photo_path = select_next_price_verified_candidate(
            [source_video], {}, set(), "https://shop.example.affdn.ir", {}
        )
        self.assertEqual(chosen["source_message_id"], 402)
        self.assertNotIn("product_video_url", chosen)
        self.assertEqual(ref["code"], "44442")
        self.assertEqual(details, page_details)
        self.assertIsNone(safe_photo_path)
        self.assertEqual(check_prices.call_count, 2)
        self.assertNotIn("product_video_url", check_prices.call_args_list[1].args[0])



if __name__ == "__main__":
    unittest.main()
