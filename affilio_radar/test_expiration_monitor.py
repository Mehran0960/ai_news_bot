# Operational trigger for a one-time duplicate cleanup; no test behavior changed.
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs
from pathlib import Path
from unittest.mock import MagicMock, patch

import expiration_monitor as monitor
from affilio_radar import build_caption, format_remaining_time
from bs4 import BeautifulSoup


# [deadline-audit-only] Marker to run one live deadline audit and refresh active channel captions.

class ExpirationMonitorTests(unittest.TestCase):
    def setUp(self):
        # Unit tests mock sleeping so rate-limit protection doesn't slow the suite.
        self.sleep_patcher = patch.object(monitor.time, "sleep")
        self.sleep_mock = self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

    def test_bot_api_pacer_waits_before_mutation(self):
        monitor._pace_bot_api()
        self.sleep_mock.assert_called_once_with(monitor.BOT_API_MIN_GAP_SECONDS)

    def test_parse_iso_deadline_normalizes_to_utc(self):
        value = monitor.parse_expiry("2026-10-16T20:30:00+03:30")
        self.assertEqual(value, "2026-10-16T17:00:00+00:00")

    def test_parse_epoch_deadline(self):
        epoch = datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(monitor.parse_expiry(epoch), "2026-10-16T17:00:00+00:00")

    def test_expiry_extractor_reads_nested_countdown(self):
        before = datetime.now(timezone.utc)
        value = monitor.extract_expiry({"product_id": 123, "campaign": {"ends_in_seconds": 90}})
        parsed = datetime.fromisoformat(value)
        after = datetime.now(timezone.utc)
        self.assertGreaterEqual(parsed, before + timedelta(seconds=89))
        self.assertLessEqual(parsed, after + timedelta(seconds=91))

    def test_product_detail_api_exposes_site_campaign_deadline_for_verification(self):
        payload = {
            "data": {
                "product": {
                    "id": 123,
                    "title_fa": "محصول تخفیف‌دار",
                    "campaign": {"ends_at": "2026-10-23T18:00:00+00:00"},
                    "default_variant": {
                        "id": 123,
                        "marketable": True,
                        "price": {
                            "selling_price_toman": 100_000,
                            "rrp_price_toman": 200_000,
                        },
                    },
                }
            }
        }
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.object(monitor, "urlopen", return_value=response):
            result = monitor.fetch_live_product_status("dkp-123")
        self.assertEqual(result["deal_expires_at"], "2026-10-23T18:00:00+00:00")
        self.assertTrue(result["expiry_verified_directly"])
        self.assertEqual(result["current_price"], 100_000)
        self.assertTrue(result["in_stock"])

    def test_expiry_cleanup_prefers_direct_feed_and_fills_only_missing_ids_from_live_offer_cards(self):
        direct = {
            "dkp-1": "2026-10-20T20:00:00+00:00",
            "dkp-2": "2026-10-20T21:00:00+00:00",
        }
        mcp = {
            "dkp-1": "2026-10-20T22:30:00+00:00",
            "dkp-3": "2026-10-20T23:00:00+00:00",
            "dkp-not-required": "2026-10-24T23:00:00+00:00",
        }
        with (
            patch.object(monitor, "fetch_direct_api_offer_expiries", return_value=direct),
            patch.object(monitor, "fetch_mcp_offer_candidates", return_value=(mcp, [])) as fallback,
        ):
            deadlines, sources = monitor.fetch_offer_deadlines(required_product_ids=["dkp-1", "dkp-2", "dkp-3"])
        self.assertEqual(deadlines["dkp-1"], direct["dkp-1"])
        self.assertEqual(deadlines["dkp-2"], direct["dkp-2"])
        self.assertEqual(deadlines["dkp-3"], mcp["dkp-3"])
        self.assertEqual(sources["dkp-1"], "digikala_live_deals_feed")
        self.assertEqual(sources["dkp-3"], "digikala_mcp_offer_card")
        self.assertNotIn("dkp-not-required", deadlines)
        fallback.assert_called_once_with(page_numbers=[1])

        with (
            patch.object(monitor, "fetch_direct_api_offer_expiries", return_value={}),
            patch.object(monitor, "fetch_mcp_offer_candidates", return_value=({"dkp-1": "2026-10-20T23:00:00+00:00"}, [])),
        ):
            deadlines, sources = monitor.fetch_offer_deadlines(required_product_ids=["dkp-1"])
        self.assertIn("dkp-1", deadlines)
        self.assertEqual(sources["dkp-1"], "digikala_mcp_offer_card")
    def test_live_deadline_sync_corrects_stale_deadline_before_cleanup(self):
        now = datetime(2026, 10, 20, 17, 40, tzinfo=timezone.utc)
        published = {
            "dkp-123": {
                "expires_at": "2026-10-20T20:30:00+00:00",
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "telegram_message_id": 61,
                "bale_message_id": 27,
                "expiry_status": "tracked",
                "bale_expiry_status": "tracked",
            }
        }
        summary = monitor.sync_live_offer_deadlines(
            published, {"dkp-123": "2026-10-20T22:00:00+00:00"}, now
        )
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(published["dkp-123"]["expires_at"], "2026-10-20T22:00:00+00:00")
        self.assertEqual(published["dkp-123"]["expiry_last_live_sync_at"], now.isoformat())
        self.assertTrue(published["dkp-123"]["deadline_caption_refresh_required"])


    def test_live_card_deadline_sync_preserves_its_distinct_verified_source(self):
        now = datetime(2026, 10, 20, 17, 40, tzinfo=timezone.utc)
        published = {
            "dkp-456": {
                "expires_at": "",
                "expiry_source": "unavailable",
                "expiry_estimated": False,
                "telegram_message_id": 91,
                "expiry_status": "unknown",
            }
        }
        summary = monitor.sync_live_offer_deadlines(
            published,
            {"dkp-456": "2026-10-20T22:00:00+00:00"},
            now,
            live_sources={"dkp-456": "digikala_mcp_offer_card"},
        )
        rec = published["dkp-456"]
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(rec["expiry_source"], "digikala_mcp_offer_card")
        self.assertTrue(rec["expiry_deadline_verified_from_site_card"])
        self.assertFalse(rec["expiry_deadline_verified_directly"])
        self.assertTrue(monitor._has_verified_deadline(rec))

    def test_live_deadline_sync_does_not_apply_current_campaign_to_post_history(self):
        now = datetime(2026, 10, 20, 17, 40, tzinfo=timezone.utc)
        old_deadline = "2026-10-20T20:30:00+00:00"
        published = {
            "dkp-123": {
                "expires_at": old_deadline,
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "telegram_message_id": 61,
                "expiry_status": "tracked",
                "post_history": [{
                    "expires_at": "2026-10-20T18:00:00+00:00",
                    "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                    "telegram_message_id": 51,
                    "expiry_status": "tracked",
                }],
            }
        }
        summary = monitor.sync_live_offer_deadlines(
            published, {"dkp-123": "2026-10-20T22:00:00+00:00"}, now
        )
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(published["dkp-123"]["expires_at"], "2026-10-20T22:00:00+00:00")
        self.assertEqual(published["dkp-123"]["post_history"][0]["expires_at"], "2026-10-20T18:00:00+00:00")
        self.assertNotIn("deadline_caption_refresh_required", published["dkp-123"]["post_history"][0])

    def test_unchanged_direct_deadline_refreshes_direct_verification_timestamp(self):
        now = datetime(2026, 10, 20, 17, 40, tzinfo=timezone.utc)
        deadline = (now + timedelta(hours=2)).isoformat()
        published = {
            "dkp-123": {
                "expires_at": deadline,
                "expiry_source": "digikala_live_deals_feed",
                "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "telegram_message_id": 61,
                "expiry_status": "tracked",
            }
        }
        summary = monitor.sync_live_offer_deadlines(
            published, {"dkp-123": deadline}, now,
            live_sources={"dkp-123": "digikala_live_deals_feed"},
        )
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(published["dkp-123"]["expiry_last_direct_verification_at"], now.isoformat())

    def test_live_deadline_sync_does_not_resurrect_deleted_messages(self):
        published = {
            "dkp-deleted": {
                "expires_at": "2026-10-20T20:30:00+00:00",
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "telegram_message_id": 61,
                "expiry_status": "deleted",
                "bale_message_id": 27,
                "bale_expiry_status": "already_absent",
            }
        }
        summary = monitor.sync_live_offer_deadlines(
            published, {"dkp-deleted": "2026-10-20T22:00:00+00:00"},
            datetime(2026, 10, 20, 17, 40, tzinfo=timezone.utc)
        )
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(published["dkp-deleted"]["expires_at"], "2026-10-20T20:30:00+00:00")

    def test_expiry_extractor_prioritizes_site_timer_over_nested_variant_timestamp(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        card = {
            "id": 123,
            "title_fa": "محصول تخفیف‌دار",
            "campaign": {"remaining_seconds": 3 * 3600 + 24 * 60},
            "default_variant": {"ends_at": "2026-10-22T18:00:00+03:30"},
        }
        self.assertEqual(
            monitor.extract_expiry(card, now=now),
            (now + timedelta(hours=3, minutes=24)).isoformat(),
        )

    def test_expiry_extractor_parses_human_readable_persian_site_countdown(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        card = {
            "title_fa": "محصول تخفیف‌دار",
            "campaign": {"remaining_time": "۳ ساعت و ۲۴ دقیقه"},
        }
        self.assertEqual(
            monitor.extract_expiry(card, now=now),
            (now + timedelta(hours=3, minutes=24)).isoformat(),
        )

    def test_expiry_extractor_prefers_card_campaign_over_nested_variant(self):
        card = {
            "id": 123,
            "title_fa": "محصول تخفیف‌دار",
            "url": {"uri": "/product/dkp-123/"},
            "campaign": {"ends_at": "2026-10-20T12:00:00+03:30"},
            "default_variant": {
                "id": 123,
                "title": "variant",
                "campaign": {"ends_at": "2026-10-20T16:00:00+03:30"},
            },
        }
        self.assertEqual(
            monitor.extract_expiry(card),
            "2026-10-20T08:30:00+00:00",
        )

    def test_expiry_extractor_parses_two_part_site_timer_as_hours_and_minutes(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        card = {
            "title_fa": "محصول تخفیف‌دار",
            "campaign": {"remaining_time": "03:24"},
        }
        self.assertEqual(
            monitor.extract_expiry(card, now=now),
            (now + timedelta(hours=3, minutes=24)).isoformat(),
        )

    def test_mcp_feed_does_not_let_nested_variant_override_offer_card_countdown(self):
        before = datetime.now(timezone.utc)
        payload = {
            "products": [{
                "id": 123,
                "title_fa": "هدفون تخفیف‌دار",
                "url": {"uri": "/product/dkp-123/"},
                "is_incredible": True,
                "campaign": {"remaining_time": "3 hours 24 minutes"},
                "default_variant": {
                    "id": 123,
                    "title": "variant",
                    "status": "marketable",
                    "price": {"selling_price": 199000},
                    "ends_at": "2026-10-22T18:00:00+03:30",
                    "stock": 30,
                    "sku": "sku-123",
                    "seller": {"id": 1, "name": "seller"},
                    "images": ["one", "two"],
                    "specifications": [{"name": "a", "value": "b"}],
                    "nested": {"foo": "bar", "baz": 3},
                },
            }]
        }
        with patch.object(monitor, "DEAL_LIST_PAGES", 1), patch.object(
            monitor, "_mcp_call_incredible_offers_page", return_value=payload
        ):
            deadlines, candidates = monitor.fetch_mcp_offer_candidates(page_numbers=[1])
        after = datetime.now(timezone.utc)
        deadline = datetime.fromisoformat(deadlines["dkp-123"])
        self.assertGreaterEqual(deadline, before + timedelta(hours=3, minutes=24))
        self.assertLessEqual(deadline, after + timedelta(hours=3, minutes=24))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title_fa"], "هدفون تخفیف‌دار")

    def test_mcp_feed_returns_offer_cards_and_deadlines_together(self):
        payload = {
            "products": [{
                "id": 123,
                "title_fa": "هدفون تخفیف‌دار آزمایشی",
                "url": {"uri": "/product/dkp-123/"},
                "is_incredible": True,
                "price": {"discount_percent": 35},
                "campaign": {"ends_at": "2026-10-20T12:00:00+03:30"},
            }]
        }
        with patch.object(monitor, "DEAL_LIST_PAGES", 1), patch.object(
            monitor, "_mcp_call_incredible_offers_page", return_value=payload
        ):
            deadlines, candidates = monitor.fetch_mcp_offer_candidates()

        self.assertEqual(deadlines["dkp-123"], "2026-10-20T08:30:00+00:00")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title_fa"], "هدفون تخفیف‌دار آزمایشی")
        self.assertEqual(candidates[0]["deal_expires_at"], deadlines["dkp-123"])


    def test_mcp_feed_can_scan_only_the_requested_rotating_page_subset(self):
        payload = {"products": []}
        with patch.object(monitor, "DEAL_LIST_PAGES", 5), patch.object(
            monitor, "_mcp_call_incredible_offers_page", return_value=payload
        ) as fetch:
            deadlines, candidates = monitor.fetch_mcp_offer_candidates(page_numbers=[4, 5, 4])

        self.assertEqual(deadlines, {})
        self.assertEqual(candidates, [])
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [4, 5])

    def test_unverified_cached_deadline_still_needs_direct_product_probe(self):
        now = datetime.now(timezone.utc)
        record = {
            "telegram_message_id": 77,
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "direct_verification_pending",
            "expiry_deadline_verified_directly": False,
            "expiry_estimated": False,
        }
        self.assertTrue(monitor._should_probe(record, now))

    def test_probe_interval_prevents_repeated_unknown_feed_checks(self):
        now = datetime.now(timezone.utc)
        record = {"expiry_last_probed_at": now.isoformat()}
        with patch.object(monitor, "UNKNOWN_PROBE_INTERVAL_SECONDS", 900):
            self.assertFalse(monitor._should_probe(record, now))
            self.assertTrue(monitor._should_probe(record, now + timedelta(minutes=16)))



    def test_telegram_caption_edit_treats_message_not_modified_as_success(self):
        url = monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123/")
        error = HTTPError(
            "https://api.telegram.org/botredacted/editMessageCaption",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"ok":false,"description":"Bad Request: message is not modified"}'),
        )
        with patch.object(monitor, "BOT_TOKEN", "test-token"), patch.object(
            monitor, "urlopen", side_effect=error
        ), patch.object(monitor.time, "sleep"):
            result = monitor._telegram_edit_caption(77, "same caption", affiliate_url=url)
        self.assertEqual(result, "edited")

    def test_telegram_caption_edit_explicitly_restores_affilio_purchase_button(self):
        url = monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123/")
        self.assertTrue(monitor._is_valid_affilio_tracking_url(url))
        with (
            patch.object(monitor, "BOT_TOKEN", "test-token"),
            patch.object(monitor, "urlopen", return_value=BytesIO(b'{"ok":true,"result":{"message_id":77}}')) as request,
            patch.object(monitor.time, "sleep"),
        ):
            self.assertEqual(monitor._telegram_edit_caption(77, "updated caption", affiliate_url=url), "edited")
        payload = parse_qs(request.call_args.args[0].data.decode("utf-8"))
        keyboard = json.loads(payload["reply_markup"][0])
        self.assertEqual(keyboard["inline_keyboard"][0][0]["text"], "🛍️ مشاهده و خرید از دیجی‌کالا")
        self.assertEqual(keyboard["inline_keyboard"][0][0]["url"], url)

    def test_caption_edit_refuses_to_remove_purchase_button_or_edit_without_verified_link(self):
        with (
            patch.object(monitor, "BOT_TOKEN", "test-token"),
            patch.object(monitor, "urlopen") as request,
        ):
            with self.assertRaisesRegex(RuntimeError, "remove the purchase button"):
                monitor._telegram_edit_caption(77, "caption", remove_purchase_button=True)
            with self.assertRaisesRegex(RuntimeError, "verified Affilio purchase button"):
                monitor._telegram_edit_caption(77, "caption")
        request.assert_not_called()

    def test_build_affilio_tracking_url_rejects_non_product_destinations(self):
        self.assertEqual(monitor._build_affilio_tracking_url("https://example.com/product/dkp-123/"), "")
        self.assertEqual(monitor._build_affilio_tracking_url("https://www.digikala.com/category/phones/"), "")

    def test_snappshop_affilio_link_is_supported_for_caption_repair(self):
        product = "https://snappshop.ir/product/snp-25751584"
        affiliate = monitor._build_affilio_tracking_url(product)
        self.assertTrue(monitor._is_valid_affilio_tracking_url(affiliate))
        self.assertEqual(monitor._product_id_from_public_url(affiliate), "snp-25751584")

    def test_delete_http_error_includes_provider_reason(self):
        error = HTTPError(
            "https://api.telegram.org/botredacted/deleteMessage",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"ok":false,"description":"Bad Request: message cant be deleted"}'),
        )
        with patch.object(monitor, "BOT_TOKEN", "test-token"), patch.object(monitor, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "message cant be deleted"):
                monitor._telegram_delete(77)



    def test_jalali_to_gregorian_and_legacy_deadline_conversion(self):
        self.assertEqual(monitor.jalali_to_gregorian(1405, 7, 25), (2026, 10, 17))
        value = monitor.extract_jalali_deadline(
            "⏳ پایان تخفیف: شنبه ۲۵ مهر ۱۴۰۵، ساعت ۲۳:۵۹"
        )
        self.assertEqual(value, datetime(2026, 10, 17, 20, 29, tzinfo=timezone.utc))

    def test_public_history_page_parser_extracts_ids_and_legacy_caption(self):
        sample = """
        <div class="tgme_widget_message_wrap">
          <div class="tgme_widget_message" data-post="OfferChin/44">
            <div class="tgme_widget_message_text js-message_text">
              <b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b><br>
              <b>🛍️ محصول نمونه</b><br>
              <b>💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان</b><br>
              <b>⚡️ ۸۹٪ تخفیف</b><br>
              <b>⏳ پایان تخفیف: شنبه ۲۵ مهر ۱۴۰۵، ساعت ۲۳:۵۹</b><br>
              <a href="https://t.me/OfferChin">عضویت در کانال: t.me/OfferChin</a>
            </div>
          </div>
        </div>
        """.encode("utf-8")
        with patch.object(monitor, "urlopen", return_value=BytesIO(sample)):
            result = monitor._fetch_public_channel_page()
        self.assertIn(44, result)
        self.assertIn("پایان تخفیف", result[44]["caption_text"])
        self.assertIn("💚 قیمت ویژه", result[44]["caption_text"])

    def test_public_history_parser_extracts_purchase_destination_for_deduplication(self):
        sample = """
        <div class="tgme_widget_message_wrap">
          <div class="tgme_widget_message" data-post="OfferChin/44">
            <div class="tgme_widget_message_text">
              <b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b><br>
              <b>🛍️ ژل آبرسان گلاما مدل Limited</b><br>
              <b>💚 قیمت ویژه: ۱۰۰٬۰۰۰ تومان</b>
            </div>
            <a class="tgme_widget_message_inline_button" href="https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-123%2F">خرید</a>
          </div>
        </div>
        """.encode("utf-8")
        with patch.object(monitor, "urlopen", return_value=BytesIO(sample)):
            posts = monitor._fetch_public_channel_page()
        self.assertEqual(posts[44]["product_ids"], ["dkp-123"])
        self.assertTrue(posts[44]["purchase_button_visible"])

    def test_duplicate_cleanup_groups_same_product_and_keeps_purchase_button_copy(self):
        state = {
            "published": {
                "dkp-123": {
                    "title": "ژل آبرسان گلاما مدل Limited",
                    "telegram_message_id": 44,
                    "delivery_status": {"telegram": "sent"},
                    "expiry_status": "tracked",
                    "post_history": [
                        {"telegram_message_id": 43, "expiry_status": "tracked"}
                    ],
                }
            }
        }
        posts = {
            43: {
                "message_id": 43,
                "caption_text": "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا 🛍️ ژل آبرسان گلاما مدل Limited 💚 قیمت ویژه: ۱۰۰٬۰۰۰ تومان",
                "title": "ژل آبرسان گلاما مدل Limited",
                "product_ids": ["dkp-123"],
                "purchase_button_visible": False,
            },
            44: {
                "message_id": 44,
                "caption_text": "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا 🛍️ ژل آبرسان گلاما مدل Limited 💚 قیمت ویژه: ۱۰۰٬۰۰۰ تومان",
                "title": "ژل آبرسان گلاما مدل Limited",
                "product_ids": ["dkp-123"],
                "purchase_button_visible": True,
            },
        }
        with (
            patch.object(monitor, "BOT_TOKEN", "test-token"),
            patch.object(monitor, "fetch_public_channel_posts", return_value=posts),
            patch.object(monitor, "_telegram_delete", return_value="deleted") as delete,
            patch.object(monitor, "_write_state") as write_state,
        ):
            status = monitor._run_duplicate_cleanup(state, apply=True)
        self.assertEqual(status, 0)
        delete.assert_called_once_with(43)
        self.assertEqual(state["published"]["dkp-123"]["expiry_status"], "tracked")
        self.assertEqual(state["published"]["dkp-123"]["post_history"][0]["expiry_status"], "deleted")
        write_state.assert_called_once_with(state)

    def test_public_history_paginates_past_a_repeated_pinned_message(self):
        pinned = {1: {"message_id": 1, "caption_text": "پست سنجاق‌شده", "caption_html": ""}}
        page_one = {**pinned, 525: {"message_id": 525, "caption_text": "آفر 525", "caption_html": ""}, 524: {"message_id": 524, "caption_text": "آفر 524", "caption_html": ""}}
        page_two = {**pinned, 523: {"message_id": 523, "caption_text": "آفر 523", "caption_html": ""}, 522: {"message_id": 522, "caption_text": "آفر 522", "caption_html": ""}}
        page_three = {**pinned, 521: {"message_id": 521, "caption_text": "آفر 521", "caption_html": ""}}
        with (
            patch.object(monitor, "_fetch_public_channel_page", side_effect=[page_one, page_two, page_three, {}]) as fetch,
            patch.object(monitor.time, "sleep"),
        ):
            posts = monitor.fetch_public_channel_posts(max_pages=5)
        self.assertEqual(set(posts), {1, 521, 522, 523, 524, 525})
        self.assertEqual(fetch.call_count, 4)
        self.assertEqual([call.args[0] if call.args else None for call in fetch.call_args_list], [None, 524, 522, 521])

    def test_public_history_paginates_backwards_without_duplicate_ids(self):
        page_one = {
            40: {"message_id": 40, "caption_text": "post 40", "caption_html": ""},
            39: {"message_id": 39, "caption_text": "post 39", "caption_html": ""},
        }
        page_two = {
            39: {"message_id": 39, "caption_text": "post 39", "caption_html": ""},
            20: {"message_id": 20, "caption_text": "post 20", "caption_html": ""},
        }
        with (
            patch.object(monitor, "_fetch_public_channel_page", side_effect=[page_one, page_two, page_two]) as fetch,
            patch.object(monitor.time, "sleep"),
        ):
            posts = monitor.fetch_public_channel_posts(max_pages=5)
        self.assertEqual(set(posts), {20, 39, 40})
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(fetch.call_args_list[1].args[0], 39)

    def test_public_history_deletes_untracked_offer_without_purchase_button(self):
        old_post = {
            "message_id": 77,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                "🛍️ محصول نمونه "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان "
                "⚡️ ۸۹٪ تخفیف "
                "⏳ پایان تخفیف: شنبه ۲۵ مهر ۱۴۰۵، ساعت ۲۳:۵۹"
            ),
            "caption_html": "",
            "product_ids": [],
            "purchase_button_visible": False,
        }
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        with patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion:
            result = monitor.audit_public_channel_history({}, now=now, posts={77: old_post})
        deletion.assert_called_once_with(77)
        self.assertEqual(result[1], 1)
        self.assertEqual(result[2], 0)

    def test_public_history_does_not_expire_a_post_using_caption_text_alone(self):
        old_post = {
            "message_id": 77,
            "caption_text": "🛍️ محصول نمونه ⏳ پایان تخفیف: شنبه ۲۵ مهر ۱۴۰۵، ساعت ۲۳:۵۹",
            "caption_html": "",
        }
        record = {
            "telegram_message_id": 77,
            "title": "محصول نمونه",
            "expiry_source": "unavailable",
            "expiry_estimated": True,
            "expiry_status": "tracked_estimated",
        }
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        with (
            patch.object(monitor, "_telegram_delete") as deletion,
            patch.object(monitor, "_telegram_mark_expired") as mark,
        ):
            result = monitor.audit_public_channel_history({"dkp-123": record}, now=now, posts={77: old_post})
        deletion.assert_not_called()
        mark.assert_not_called()
        self.assertEqual(record["expiry_status"], "tracked_estimated")
        self.assertEqual(result[1], 0)

    def test_public_history_repairs_untracked_active_legacy_caption(self):
        legacy = {
            "message_id": 88,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                "🛍️ کپسول نمونه "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان "
                "⚡️ ۸۹٪ تخفیف ویژه "
                "🏷️ قیمت اصلی: ۱٬۰۵۶٬۰۰۰ تومان "
                "⏳ پایان تخفیف: یکشنبه ۲۶ مهر ۱۴۰۵، ساعت ۲۳:۵۹ "
                "📣 عضویت در کانال: t.me/OfferChin"
            ),
            "caption_html": "<b>💚 قیمت ویژه: 💰 <u>۱۱۴٬۰۰۰</u> تومان</b>",
        }
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        published = {
            "dkp-123": {
                "telegram_message_id": 88,
                "product_url": "https://www.digikala.com/product/dkp-123/",
                "expires_at": "2026-10-18T20:29:00+00:00",
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            }
        }
        with patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit:
            result = monitor.audit_public_channel_history(published, now=now, posts={88: legacy})
        edit.assert_called_once()
        edited_caption = edit.call_args.args[1]
        self.assertIn("<b>💚 قیمت ویژه: ۱۱۴٬۰۰۰ تومان</b>", edited_caption)
        self.assertIn("────────────", edited_caption)
        self.assertIn("<b>⚡️ ۸۹٪ تخفیف</b>", edited_caption)
        self.assertNotIn("قیمت اصلی", edited_caption)
        self.assertNotIn("۱٬۰۵۶٬۰۰۰", edited_caption)
        self.assertNotIn("<u>", edited_caption)
        self.assertIn('<a href="https://t.me/OfferChin">عضویت در کانال OfferChin</a>', edited_caption)
        self.assertIn("برای خرید از دیجی‌کالا، دکمهٔ زیر رو بزن.", edited_caption)
        self.assertNotIn("⏳", edited_caption)
        self.assertNotIn("مانده به پایان تخفیف", edited_caption)
        self.assertNotIn("📅 پایان تخفیف:", edited_caption)
        self.assertEqual(published["dkp-123"]["caption_deadline_format_version"], monitor.CAPTION_FORMAT_VERSION)
        self.assertIn("caption_static_migrated_at", published["dkp-123"])
        expected_affiliate = monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123/")
        edit.assert_called_once()
        self.assertEqual(edit.call_args.kwargs["affiliate_url"], expected_affiliate)
        self.assertEqual(result[3], 1)



    def test_canonical_caption_layout_is_not_rewritten_by_expiry_audit(self):
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        affiliate = monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123/")
        product = {
            "title": "محصول نمونه",
            "current_price": 114000,
            "original_price": 1056000,
            "discount_percent": 89,
        }
        canonical = build_caption(product, affiliate, "https://t.me/OfferChin")
        soup = BeautifulSoup(canonical, "html.parser")
        record = {
            "telegram_message_id": 88,
            "product_url": "https://www.digikala.com/product/dkp-123/",
            "title": "محصول نمونه",
            "posted_current_price": 114000,
            "posted_original_price": 1056000,
            "posted_discount_percent": 89,
            "expires_at": "2026-10-18T20:29:00+00:00",
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "expiry_status": "tracked",
            "caption_deadline_format_version": monitor.CAPTION_FORMAT_VERSION,
        }
        post = {
            "message_id": 88,
            "caption_text": soup.get_text(" ", strip=True),
            "caption_html": canonical,
            "product_ids": ["dkp-123"],
            "purchase_button_visible": True,
        }
        with patch.object(monitor, "_telegram_edit_caption") as edit:
            result = monitor.audit_public_channel_history(
                {"dkp-123": record}, now=now, posts={88: post}
            )
        edit.assert_not_called()
        self.assertEqual(result[3], 0)
        self.assertEqual(record["caption_deadline_format_version"], monitor.CAPTION_FORMAT_VERSION)

    def test_legacy_caption_without_dividers_is_rebuilt_to_canonical_layout(self):
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        affiliate = monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123/")
        record = {
            "telegram_message_id": 88,
            "product_url": "https://www.digikala.com/product/dkp-123/",
            "title": "محصول نمونه",
            "posted_current_price": 114000,
            "posted_original_price": 1056000,
            "posted_discount_percent": 89,
            "expires_at": "2026-10-18T20:29:00+00:00",
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "expiry_status": "tracked",
            "caption_deadline_format_version": monitor.CAPTION_FORMAT_VERSION,
        }
        legacy = {
            "message_id": 88,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا 🛍️ محصول نمونه "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان ⚡️ ۸۹٪ تخفیف "
                "🏷️ قیمت اصلی: ۱٬۰۵۶٬۰۰۰ تومان عضویت در کانال OfferChin "
                "👇 برای خرید از دیجی‌کالا، دکمهٔ زیر رو بزن."
            ),
            "caption_html": (
                "<b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b>"
                "<b>🛍️ محصول نمونه</b>"
                "<b>💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان</b>"
                "<b>⚡️ ۸۹٪ تخفیف</b>"
                "<b>🏷️ قیمت اصلی: <s>۱٬۰۵۶٬۰۰۰ تومان</s></b>"
                '<a href="https://t.me/OfferChin">عضویت در کانال OfferChin</a>'
                "<b>👇 برای خرید از دیجی‌کالا، دکمهٔ زیر رو بزن.</b>"
            ),
            "product_ids": ["dkp-123"],
            "purchase_button_visible": True,
        }
        with patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit:
            result = monitor.audit_public_channel_history(
                {"dkp-123": record}, now=now, posts={88: legacy}
            )
        edit.assert_called_once()
        updated = edit.call_args.args[1]
        self.assertEqual(updated.count("────────────"), 2)
        self.assertNotIn("⏳", updated)
        self.assertNotIn("قیمت اصلی", updated)
        self.assertNotIn("۱٬۰۵۶٬۰۰۰", updated)
        self.assertTrue(monitor._is_valid_affilio_tracking_url(edit.call_args.kwargs["affiliate_url"]))
        self.assertEqual(result[3], 1)

    def test_public_history_restores_button_after_delete_failure(self):
        caption = {
            "message_id": 88,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا 🛍️ محصول نمونه "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان ⚡️ ۸۹٪ تخفیف "
                "🏷️ قیمت اصلی: ۱٬۰۵۶٬۰۰۰ تومان 📣 عضویت در کانال OfferChin"
            ),
            "caption_html": "<b>💚 قیمت ویژه: ۱۱۴٬۰۰۰ تومان</b>",
        }
        record = {
            "telegram_message_id": 88,
            "product_url": "https://www.digikala.com/product/dkp-123/",
            "title": "محصول نمونه",
            "posted_current_price": 114000,
            "posted_original_price": 1056000,
            "posted_discount_percent": 89,
            "expires_at": "2026-10-18T20:29:00+00:00",
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "expiry_status": "delete_failed",
            "caption_deadline_format_version": monitor.CAPTION_FORMAT_VERSION,
        }
        with patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit:
            result = monitor.audit_public_channel_history(
                {"dkp-123": record},
                now=datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc),
                posts={88: caption},
            )
        edit.assert_called_once()
        self.assertTrue(monitor._is_valid_affilio_tracking_url(edit.call_args.kwargs["affiliate_url"]))
        self.assertNotIn("مانده به پایان تخفیف", edit.call_args.args[1])
        self.assertNotIn("⏳", edit.call_args.args[1])
        self.assertNotIn("قیمت اصلی", edit.call_args.args[1])
        self.assertNotIn("۱٬۰۵۶٬۰۰۰", edit.call_args.args[1])
        self.assertEqual(result[3], 1)

    def test_public_history_removes_stale_countdown_and_absolute_deadline_from_caption(self):
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        stale_caption = {
            "message_id": 89,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                "🛍️ محصول نمونه 💚 قیمت ویژه: ۱۱۴٬۰۰۰ تومان "
                "⚡️ ۸۹٪ تخفیف 🏷️ قیمت اصلی: ۱٬۰۵۶٬۰۰۰ تومان "
                "⏳ ۲۴ ساعت و ۱۵ دقیقه مانده به پایان تخفیف "
                "📅 پایان تخفیف: یکشنبه ۲۶ مهر ۱۴۰۵، ساعت ۲۳:۵۹"
            ),
            "caption_html": (
                "<b>💚 قیمت ویژه: 💰 <u>۱۱۴٬۰۰۰ تومان</u></b> "
                "<b>⚡️ <u>۸۹٪ تخفیف</u></b>"
            ),
        }
        deadline = monitor.extract_jalali_deadline(stale_caption["caption_text"])
        published = {
            "dkp-legacy-89": {
                "telegram_message_id": 89,
                "product_url": "https://www.digikala.com/product/dkp-123/",
                "expires_at": deadline.isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            }
        }
        with patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit:
            monitor.audit_public_channel_history(published, now=now, posts={89: stale_caption})
        edit.assert_called_once()
        updated = edit.call_args.args[1]
        self.assertNotIn("⏳", updated)
        self.assertNotIn("مانده به پایان تخفیف", updated)
        self.assertNotIn("📅 پایان تخفیف:", updated)
        self.assertNotIn("قیمت اصلی", updated)
        self.assertNotIn("۱٬۰۵۶٬۰۰۰", updated)
        self.assertEqual(published["dkp-legacy-89"]["caption_deadline_format_version"], monitor.CAPTION_FORMAT_VERSION)
        self.assertEqual(published["dkp-legacy-89"]["expires_at"], deadline.isoformat())

    def test_posts_are_deleted_ten_minutes_before_deadline_on_both_channels(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        published = {
            "at_cutoff": {
                "telegram_message_id": 101,
                "bale_message_id": 201,
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_last_direct_verification_at": now.isoformat(),
                "expiry_status": "tracked",
                "bale_expiry_status": "tracked",
            },
            "just_before_cutoff": {
                "telegram_message_id": 102,
                "expires_at": (now + timedelta(minutes=10, seconds=1)).isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            },
        }
        with (
            patch.object(monitor, "_telegram_delete", return_value="deleted") as tg_delete,
            patch.object(monitor, "_bale_delete", return_value="deleted") as bale_delete,
        ):
            changed, deleted = monitor._delete_expired_posts(published, now)
        self.assertTrue(changed)
        self.assertEqual(deleted, 2)
        tg_delete.assert_called_once_with(101)
        bale_delete.assert_called_once_with(201)
        self.assertEqual(published["at_cutoff"]["expiry_status"], "deleted")
        self.assertEqual(published["at_cutoff"]["bale_expiry_status"], "deleted")
        self.assertEqual(published["just_before_cutoff"]["expiry_status"], "tracked")

    def test_stale_site_card_cutoff_is_rechecked_directly_and_extended_deadline_is_kept(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        fresh_deadline = now + timedelta(hours=2)
        record = {
            "telegram_message_id": 701,
            "bale_message_id": 801,
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
            "expiry_status": "tracked",
            "bale_expiry_status": "tracked",
            "posted_current_price": 900_000,
        }
        published = {"dkp-123": record}
        with (
            patch.object(monitor, "fetch_live_product_status", return_value={
                "deal_expires_at": fresh_deadline.isoformat(),
                "expiry_verified_directly": True,
                "current_price": 900_000,
                "original_price": 1_500_000,
                "in_stock": True,
            }) as direct_check,
            patch.object(monitor, "_telegram_delete") as tg_delete,
            patch.object(monitor, "_bale_delete") as bale_delete,
        ):
            changed, deleted = monitor._delete_expired_posts(
                published, now, direct_confirm=monitor._confirm_expiry_for_deletion
            )
        direct_check.assert_called_once_with("dkp-123")
        self.assertTrue(changed)
        self.assertEqual(deleted, 0)
        tg_delete.assert_not_called()
        bale_delete.assert_not_called()
        self.assertEqual(record["expiry_source"], "digikala_product_detail_api")
        self.assertEqual(record["expires_at"], fresh_deadline.isoformat())
        self.assertEqual(record["expiry_last_direct_verification_at"], now.isoformat())
        self.assertEqual(record["expiry_status"], "tracked")
        self.assertEqual(record["bale_expiry_status"], "tracked")

    def test_inconclusive_direct_check_preserves_post_and_purchase_button(self):
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        record = {
            "telegram_message_id": 702,
            "bale_message_id": 802,
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
            "expiry_status": "tracked",
            "bale_expiry_status": "tracked",
        }
        published = {"dkp-124": record}
        with (
            patch.object(monitor, "fetch_live_product_status", return_value={}) as direct_check,
            patch.object(monitor, "_telegram_delete") as tg_delete,
            patch.object(monitor, "_bale_delete") as bale_delete,
        ):
            changed, deleted = monitor._delete_expired_posts(
                published, now, direct_confirm=monitor._confirm_expiry_for_deletion
            )
        direct_check.assert_called_once_with("dkp-124")
        self.assertTrue(changed)
        self.assertEqual(deleted, 0)
        tg_delete.assert_not_called()
        bale_delete.assert_not_called()
        self.assertEqual(record["expiry_last_removal_check_result"], "inconclusive")
        self.assertEqual(record["expiry_status"], "tracked")
        self.assertEqual(record["bale_expiry_status"], "tracked")

    def test_estimated_deadline_never_authorizes_channel_post_deletion(self):
        now = datetime.now(timezone.utc)
        published = {
            "dkp-estimated": {
                "telegram_message_id": 707,
                "bale_message_id": 808,
                "expires_at": (now - timedelta(minutes=1)).isoformat(),
                "expiry_source": "unavailable",
                "expiry_estimated": True,
                "expiry_status": "tracked_estimated",
                "bale_expiry_status": "tracked_estimated",
            }
        }
        with (
            patch.object(monitor, "_telegram_delete") as tg_delete,
            patch.object(monitor, "_bale_delete") as bale_delete,
        ):
            changed, deleted = monitor._delete_expired_posts(published, now)
        self.assertFalse(changed)
        self.assertEqual(deleted, 0)
        tg_delete.assert_not_called()
        bale_delete.assert_not_called()
        self.assertEqual(published["dkp-estimated"]["expiry_status"], "tracked_estimated")
        self.assertNotIn("expiry_estimate_cutoff_preserved_at", published["dkp-estimated"])

    def test_caption_countdown_zero_matches_exact_post_deletion_cutoff(self):
        deadline = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)
        now = deadline - timedelta(minutes=monitor.POST_REMOVAL_BUFFER_MINUTES)
        caption_remaining = format_remaining_time(
            deadline,
            now=now,
            safety_buffer_minutes=monitor.POST_REMOVAL_BUFFER_MINUTES,
        )
        self.assertEqual(caption_remaining, "مهلت آفر به پایان رسیده")

        published = {
            "cutoff": {
                "telegram_message_id": 909,
                "expires_at": deadline.isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            }
        }
        with patch.object(monitor, "_telegram_delete", return_value="deleted") as delete:
            changed, deleted = monitor._delete_expired_posts(published, now)
        self.assertTrue(changed)
        self.assertEqual(deleted, 1)
        delete.assert_called_once_with(909)

    def test_repaired_legacy_countdown_uses_same_ten_minute_cutoff_as_deletion(self):
        deadline = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        before_cutoff = deadline - timedelta(minutes=12)
        at_cutoff = deadline - timedelta(minutes=10)
        self.assertEqual(monitor._remaining_label(deadline, before_cutoff), "۲ دقیقه")
        self.assertEqual(monitor._remaining_label(deadline, at_cutoff), "مهلت آفر به پایان رسیده")

    def test_confirmed_deadline_does_not_need_another_network_probe(self):
        now = datetime.now(timezone.utc)
        record = {
            "telegram_message_id": 77,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        self.assertFalse(monitor._should_probe(record, now))

    def test_expired_posts_are_removed_but_unknown_posts_are_preserved_when_feed_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "published": {
                    "dkp-12345": {
                        "telegram_message_id": 77,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                        "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                        "expiry_estimated": False,
                        "expiry_last_direct_verification_at": datetime.now(timezone.utc).isoformat(),
                        "expiry_status": "tracked",
                    },
                    "dkp-67890": {
                        "telegram_message_id": 88,
                        "product_url": "https://www.digikala.com/product/dkp-67890/",
                        "expires_at": "",
                        "expiry_source": "unavailable",
                        "expiry_status": "unknown",
                    },
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(monitor, "STATE_PATH", state_path),
                patch.object(monitor, "BOT_TOKEN", "test-token"),
                patch.object(monitor, "audit_public_channel_history", return_value=(False, 0, 0, 0, 0)),
                patch.object(monitor, "fetch_offer_deadlines", side_effect=RuntimeError("feed unavailable")) as fetch,
                patch.object(monitor, "fetch_live_product_status", return_value={}) as product_check,
                patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion,
            ):
                self.assertEqual(monitor.run(), 0)
            self.assertEqual([call.args[0] for call in deletion.call_args_list], [77])
            fetch.assert_called_once()
            product_check.assert_called_once_with("dkp-67890")
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["published"]["dkp-12345"]["expiry_status"], "deleted")
            self.assertIn("expired_deleted_at", saved["published"]["dkp-12345"])
            self.assertEqual(saved["published"]["dkp-67890"]["expiry_status"], "unknown")
            self.assertIn("telegram_unverified_deadline_preserved_at", saved["published"]["dkp-67890"])
            self.assertNotIn("deadline_unavailable_deleted_at", saved["published"]["dkp-67890"])


    def test_expired_history_posts_are_deleted_after_product_record_is_replaced(self):
        now = datetime(2026, 10, 19, 16, 45, tzinfo=timezone.utc)
        published = {
            "dkp-22104577": {
                "title": "شارژر فندکی وونک VC-50",
                "telegram_message_id": 106,
                "bale_message_id": 90,
                "expires_at": (now + timedelta(hours=4)).isoformat(),
                "expiry_status": "tracked",
                "bale_expiry_status": "tracked",
                "expiry_estimated": False,
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "post_history": [{
                    "title": "شارژر فندکی وونک VC-50",
                    "telegram_message_id": 97,
                    "bale_message_id": 76,
                    "expires_at": (now - timedelta(minutes=45)).isoformat(),
                    "expiry_status": "tracked",
                    "bale_expiry_status": "tracked",
                    "expiry_estimated": False,
                    "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                }],
            }
        }
        with patch.object(monitor, "_telegram_delete", return_value="deleted") as tg_delete, patch.object(
            monitor, "_bale_delete", return_value="deleted"
        ) as bale_delete:
            changed, deleted = monitor._delete_expired_posts(published, now)
        self.assertTrue(changed)
        self.assertEqual(deleted, 2)
        tg_delete.assert_called_once_with(97)
        bale_delete.assert_called_once_with(76)
        self.assertEqual(published["dkp-22104577"]["post_history"][0]["expiry_status"], "deleted")
        self.assertEqual(published["dkp-22104577"]["post_history"][0]["bale_expiry_status"], "deleted")


    def test_expired_post_delete_failure_preserves_button_and_retries_deletion(self):
        now = datetime.now(timezone.utc)
        published = {
            "dkp-expired": {
                "title": "محصول منقضی",
                "telegram_message_id": 991,
                "expires_at": (now - timedelta(minutes=5)).isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            }
        }
        with (
            patch.object(
                monitor, "_telegram_delete",
                side_effect=[RuntimeError("temporary delete failure"), "deleted"],
            ) as deletion,
            patch.object(monitor, "_telegram_mark_expired") as mark,
        ):
            changed, deleted = monitor._delete_expired_posts(published, now)
            self.assertTrue(changed)
            self.assertEqual(deleted, 0)
            self.assertEqual(published["dkp-expired"]["expiry_status"], "delete_failed")
            mark.assert_not_called()
            changed, deleted = monitor._delete_expired_posts(
                published, now + timedelta(minutes=5)
            )
        self.assertEqual(deletion.call_count, 2)
        self.assertEqual(deleted, 1)
        self.assertEqual(published["dkp-expired"]["expiry_status"], "deleted")


    def test_expired_post_delete_failure_preserves_button_and_retries_deletion(self):
        now = datetime.now(timezone.utc)
        published = {
            "dkp-expired": {
                "title": "محصول منقضی",
                "telegram_message_id": 991,
                "expires_at": (now - timedelta(minutes=5)).isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            }
        }
        with (
            patch.object(
                monitor, "_telegram_delete",
                side_effect=[RuntimeError("temporary delete failure"), "deleted"],
            ) as deletion,
            patch.object(monitor, "_telegram_mark_expired") as mark,
        ):
            changed, deleted = monitor._delete_expired_posts(published, now)
            self.assertTrue(changed)
            self.assertEqual(deleted, 0)
            self.assertEqual(published["dkp-expired"]["expiry_status"], "delete_failed")
            mark.assert_not_called()
            changed, deleted = monitor._delete_expired_posts(
                published, now + timedelta(minutes=5)
            )
        self.assertEqual(deletion.call_count, 2)
        self.assertEqual(deleted, 1)
        self.assertEqual(published["dkp-expired"]["expiry_status"], "deleted")

    def test_expired_post_is_deleted_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "published": {
                    "dkp-12345": {
                        "telegram_message_id": 77,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
                        "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                        "expiry_estimated": False,
                        "expiry_last_direct_verification_at": datetime.now(timezone.utc).isoformat(),
                        "expiry_status": "tracked",
                    }
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(monitor, "STATE_PATH", state_path),
                patch.object(monitor, "BOT_TOKEN", "test-token"),
                patch.object(monitor, "audit_public_channel_history", return_value=(False, 0, 0, 0, 0)),
                patch.object(monitor, "fetch_offer_deadlines", return_value=({}, {})),
                patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion,
            ):
                self.assertEqual(monitor.run(), 0)
            deletion.assert_called_once_with(77)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            record = saved["published"]["dkp-12345"]
            self.assertEqual(record["expiry_status"], "deleted")
            self.assertIn("expired_deleted_at", record)

    def test_expired_post_is_deleted_from_both_platforms(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "published": {
                    "dkp-98765": {
                        "telegram_message_id": 101,
                        "bale_message_id": 202,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
                        "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                        "expiry_estimated": False,
                        "expiry_last_direct_verification_at": datetime.now(timezone.utc).isoformat(),
                        "expiry_status": "tracked",
                        "bale_expiry_status": "tracked",
                    }
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(monitor, "STATE_PATH", state_path),
                patch.object(monitor, "BOT_TOKEN", "test-token"),
                patch.object(monitor, "BALE_BOT_TOKEN", "bale-test-token"),
                patch.object(monitor, "BALE_CHANNEL_ID", "-10012345"),
                patch.object(monitor, "audit_public_channel_history", return_value=(False, 0, 0, 0, 0)),
                patch.object(monitor, "fetch_offer_deadlines", return_value=({}, {})),
                patch.object(monitor, "_telegram_delete", return_value="deleted") as telegram_delete,
                patch.object(monitor, "_bale_delete", return_value="deleted") as bale_delete,
            ):
                self.assertEqual(monitor.run(), 0)
            telegram_delete.assert_called_once_with(101)
            bale_delete.assert_called_once_with(202)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            record = saved["published"]["dkp-98765"]
            self.assertEqual(record["expiry_status"], "deleted")
            self.assertEqual(record["bale_expiry_status"], "deleted")
            self.assertIn("expired_deleted_at", record)
            self.assertIn("bale_expired_deleted_at", record)


    def test_missing_or_unverified_deadline_posts_are_preserved_on_both_channels(self):
        now = datetime.now(timezone.utc)
        state = {
            "unknown": {
                "title": "زمان نامعلوم",
                "telegram_message_id": 71,
                "bale_message_id": 81,
                "expires_at": "",
                "expiry_source": "unavailable",
                "expiry_status": "unknown",
                "bale_expiry_status": "unknown",
            },
            "estimated": {
                "title": "زمان تخمینی",
                "telegram_message_id": 72,
                "expires_at": (now + timedelta(hours=2)).isoformat(),
                "expiry_source": "estimated",
                "expiry_estimated": True,
            },
            "verified": {
                "title": "زمان تأییدشده",
                "telegram_message_id": 73,
                "bale_message_id": 83,
                "expires_at": (now + timedelta(hours=2)).isoformat(),
                "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
                "expiry_estimated": False,
                "expiry_status": "tracked",
            },
        }
        with (
            patch.object(monitor, "_telegram_delete") as telegram_delete,
            patch.object(monitor, "_bale_delete") as bale_delete,
        ):
            changed, deleted, marked = monitor._delete_posts_without_verified_deadline(state, now)
        self.assertTrue(changed)
        self.assertEqual((deleted, marked), (0, 0))
        telegram_delete.assert_not_called()
        bale_delete.assert_not_called()
        self.assertEqual(state["unknown"]["expiry_status"], "unknown")
        self.assertEqual(state["unknown"]["bale_expiry_status"], "unknown")
        self.assertIn("telegram_unverified_deadline_preserved_at", state["unknown"])
        self.assertIn("bale_unverified_deadline_preserved_at", state["unknown"])
        self.assertIn("telegram_unverified_deadline_preserved_at", state["estimated"])
        self.assertEqual(state["verified"]["expiry_status"], "tracked")
        self.assertNotIn("bale_expiry_status", state["verified"])

    def test_unverifiable_deadline_preserves_post_without_deleting_or_disabling_button(self):
        now = datetime.now(timezone.utc)
        state = {
            "dkp-123": {
                "title": "پیشنهاد بدون زمان",
                "telegram_message_id": 74,
                "expires_at": "",
                "expiry_source": "unavailable",
            }
        }
        with (
            patch.object(monitor, "_telegram_delete") as deletion,
            patch.object(monitor, "_telegram_mark_deadline_unavailable") as mark,
        ):
            changed, deleted, marked = monitor._delete_posts_without_verified_deadline(state, now)
        self.assertEqual((changed, deleted, marked), (True, 0, 0))
        self.assertEqual(state["dkp-123"].get("expiry_status"), None)
        self.assertIn("telegram_unverified_deadline_preserved_at", state["dkp-123"])
        deletion.assert_not_called()
        mark.assert_not_called()

    def test_public_history_preserves_buttoned_incomplete_offer_for_direct_deadline_recheck(self):
        post = {
            "message_id": 80,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                "🛍️ محصول با اطلاعات ناقص "
                "⏳ ۲ ساعت و ۲۰ دقیقه مانده به پایان تخفیف"
            ),
            "caption_html": "",
            "product_ids": ["dkp-15970076"],
            "purchase_button_visible": True,
        }
        published = {}
        with (
            patch.object(monitor, "_telegram_delete") as deletion,
            patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit,
        ):
            result = monitor.audit_public_channel_history(
                published, now=datetime.now(timezone.utc), posts={80: post}
            )
        deletion.assert_not_called()
        edit.assert_called_once()
        self.assertEqual(result[1], 0)
        self.assertEqual(result[3], 1)
        self.assertEqual(published["dkp-15970076"]["telegram_message_id"], 80)
        self.assertEqual(published["dkp-15970076"]["expires_at"], "")
        self.assertNotIn("مانده به پایان تخفیف", edit.call_args.args[1])

    def test_public_history_does_not_delete_non_offer_announcement_without_deadline(self):
        post = {
            "message_id": 81,
            "caption_text": "اطلاعیهٔ کانال دربارهٔ برنامهٔ فردا",
            "caption_html": "",
        }
        with patch.object(monitor, "_telegram_delete") as deletion:
            result = monitor.audit_public_channel_history(
                {}, now=datetime.now(timezone.utc), posts={81: post}
            )
        deletion.assert_not_called()
        self.assertEqual(result[1], 0)

    def test_public_history_removes_untracked_offer_without_purchase_button(self):
        post = {
            "message_id": 79,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                "🛍️ محصول بدون دکمه خرید "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان "
                "⚡️ ۸۹٪ تخفیف "
                "⏳ ۲ ساعت و ۲۰ دقیقه مانده به پایان تخفیف"
            ),
            "caption_html": "",
            "product_ids": [],
            "purchase_button_visible": False,
        }
        with patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion:
            result = monitor.audit_public_channel_history(
                {}, now=datetime.now(timezone.utc), posts={79: post}
            )
        deletion.assert_called_once_with(79)
        self.assertEqual(result[1], 1)

    def test_public_history_repairs_tracked_post_when_purchase_button_is_missing(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        title = "هدفون بلوتوثی نمونه"
        caption = (
            "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
            f"🛍️ {title} "
            "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان "
            "⚡️ ۸۹٪ تخفیف "
        )
        record = {
            "title": title,
            "telegram_message_id": 92,
            "expires_at": (now + timedelta(hours=2)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "expiry_status": "deleted",
            "caption_deadline_format_version": monitor.CAPTION_FORMAT_VERSION,
        }
        post = {
            "message_id": 92,
            "caption_text": caption,
            "caption_html": "<b>💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان</b>",
            "product_ids": ["dkp-15970077"],
            "purchase_button_visible": False,
        }
        with patch.object(
            monitor, "_telegram_edit_caption", return_value="edited"
        ) as edit, patch.object(monitor, "_telegram_delete") as delete:
            result = monitor.audit_public_channel_history(
                {"dkp-15970077": record}, now=now, posts={92: post}
            )
        edit.assert_called_once()
        delete.assert_not_called()
        self.assertEqual(result[3], 1)
        self.assertEqual(record["expiry_status"], "tracked")
        self.assertNotIn("پایان تخفیف", edit.call_args.args[1])
        self.assertTrue(edit.call_args.kwargs["affiliate_url"].startswith("https://aflo.ir/"))

    def test_public_history_adopts_buttoned_untracked_offer_without_countdown(self):
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        title = "هدفون بلوتوثی نمونه"
        post = {
            "message_id": 91,
            "caption_text": (
                "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا "
                f"🛍️ {title} "
                "💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان "
                "⚡️ ۸۹٪ تخفیف "
                "⏳ ۲ ساعت و ۲۰ دقیقه مانده به پایان تخفیف"
            ),
            "caption_html": "",
            "product_ids": ["dkp-123456"],
            "purchase_button_visible": True,
        }
        with patch.object(
            monitor, "_telegram_edit_caption", return_value="edited"
        ) as edit:
            changed, deleted, marked, repaired, expired = monitor.audit_public_channel_history(
                {}, now=now, posts={91: post}
            )
        self.assertTrue(changed)
        self.assertEqual((deleted, repaired, expired), (0, 1, 0))
        edit.assert_called_once()
        self.assertEqual(edit.call_args.args[0], 91)
        self.assertNotIn("مانده به پایان تخفیف", edit.call_args.args[1])
        self.assertEqual(
            edit.call_args.kwargs["affiliate_url"],
            monitor._build_affilio_tracking_url("https://www.digikala.com/product/dkp-123456/")
        )


    def test_one_time_specific_product_removal_cleans_ids_and_preserves_normal_cooldown(self):
        title = "ژل آبرسان صورت گلاما مدل Limited مناسب برای انواع پوست حجم 50 میلی‌لیتر"
        unrelated = {
            "message_id": 700,
            "caption_text": "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا محصول دیگری",
            "caption_html": "",
            "product_ids": ["dkp-12345678"],
        }
        target_by_id = {
            501: {
                "message_id": 501,
                "caption_text": "🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا محصول با عنوان دیگر",
                "caption_html": "",
                "product_ids": ["dkp-20917779"],
            },
            499: {
                "message_id": 499,
                "caption_text": f"🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا {title}",
                "caption_html": "",
                "product_ids": [],
            },
            700: unrelated,
        }
        state = {
            "published": {},
            "pending_queue": {"dkp-20917779": {"product_id": "dkp-20917779"}},
            "discovery_queue": {"dkp-20917779": {"product_id": "dkp-20917779"}},
        }
        with (
            patch.object(monitor, "BOT_TOKEN", "telegram-test-token"),
            patch.object(monitor, "BALE_BOT_TOKEN", "bale-test-token"),
            patch.object(monitor, "BALE_CHANNEL_ID", "-10012345"),
            patch.object(monitor, "fetch_public_channel_posts", return_value=target_by_id),
            patch.object(monitor, "_telegram_delete", return_value="deleted") as tg_delete,
            patch.object(monitor, "_bale_delete", return_value="deleted") as bale_delete,
            patch.object(monitor, "_write_state") as write_state,
            patch.object(monitor.time, "sleep"),
        ):
            result = monitor._delete_one_specific_product(
                state, "dkp-20917779", title,
                "499,500,501", "598,599,600",
            )
        self.assertEqual(result, 0)
        self.assertCountEqual([call.args[0] for call in tg_delete.call_args_list], [499, 500, 501])
        self.assertCountEqual([call.args[0] for call in bale_delete.call_args_list], [598, 599, 600])
        self.assertNotIn(700, [call.args[0] for call in tg_delete.call_args_list])
        record = state["published"]["dkp-20917779"]
        self.assertEqual(record["expiry_status"], "deleted")
        self.assertEqual(record["bale_expiry_status"], "deleted")
        self.assertEqual(state["publication_ledger"]["dkp-20917779"]["ts"], record["ts"])
        self.assertNotIn("product_suppressions", state)
        self.assertEqual(state["publication_ledger"]["dkp-20917779"]["one_time_removal_reason"], "user_requested_product_cleanup")
        self.assertFalse(state["pending_queue"].get("dkp-20917779"))
        self.assertFalse(state["discovery_queue"].get("dkp-20917779"))
        self.assertEqual(write_state.call_count, 1)

    def test_youtube_expired_short_is_deleted(self):
        now = datetime.now(timezone.utc)
        record = {
            "youtube_video_id": "yt_expired",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("short_video.youtube_credentials_available", return_value=True), patch(
            "short_video.delete_youtube_video", return_value="deleted"
        ) as delete_video:
            changed = monitor._delete_expired_youtube_videos({"dkp-expired": record}, now)
        self.assertTrue(changed)
        delete_video.assert_called_once_with("yt_expired")
        self.assertEqual(record["youtube_expiry_status"], "deleted")

    def test_youtube_estimated_deadline_does_not_delete_video(self):
        now = datetime.now(timezone.utc)
        record = {
            "youtube_video_id": "yt_estimated",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_estimated": True,
        }
        with patch("short_video.youtube_credentials_available", return_value=True), patch(
            "short_video.delete_youtube_video"
        ) as delete_video:
            changed = monitor._delete_expired_youtube_videos({"dkp-estimated": record}, now)
        self.assertFalse(changed)
        delete_video.assert_not_called()
        self.assertNotIn("youtube_expiry_status", record)

    def test_youtube_delete_failure_privatises_as_fallback_and_retries(self):
        now = datetime.now(timezone.utc)
        record = {
            "youtube_video_id": "yt_retry",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("short_video.youtube_credentials_available", return_value=True), patch(
            "short_video.delete_youtube_video", side_effect=RuntimeError("delete failed")
        ), patch("short_video.set_youtube_video_private", return_value=True) as fallback:
            changed = monitor._delete_expired_youtube_videos({"dkp-retry": record}, now)
        self.assertTrue(changed)
        fallback.assert_called_once_with("yt_retry")
        self.assertEqual(record["youtube_expiry_status"], "delete_retry")
        self.assertIn("youtube_expiry_next_attempt_at", record)

    def test_expired_youtube_video_waits_for_credentials(self):
        now = datetime.now(timezone.utc)
        record = {
            "youtube_video_id": "yt_pending",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("short_video.youtube_credentials_available", return_value=False), patch(
            "short_video.delete_youtube_video"
        ) as delete_video:
            changed = monitor._delete_expired_youtube_videos({"dkp-pending": record}, now)
        self.assertTrue(changed)
        delete_video.assert_not_called()
        self.assertEqual(record["youtube_expiry_status"], "pending_credentials")

    def test_aparat_expired_video_is_deleted(self):
        now = datetime.now(timezone.utc)
        record = {
            "aparat_video_hash": "aparat_expired",
            "aparat_visibility": "public",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("aparat_uploader.aparat_credentials_available", return_value=True), patch(
            "aparat_uploader.delete_aparat_video", return_value="deleted"
        ) as delete_video:
            changed = monitor._delete_expired_aparat_videos({"dkp-aparat": record}, now)
        self.assertTrue(changed)
        delete_video.assert_called_once_with("aparat_expired")
        self.assertEqual(record["aparat_expiry_status"], "deleted")

    def test_aparat_estimated_deadline_does_not_delete_video(self):
        now = datetime.now(timezone.utc)
        record = {
            "aparat_video_hash": "aparat_estimated",
            "aparat_visibility": "public",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_estimated": True,
        }
        with patch("aparat_uploader.aparat_credentials_available", return_value=True), patch(
            "aparat_uploader.delete_aparat_video"
        ) as delete_video:
            changed = monitor._delete_expired_aparat_videos({"dkp-aparat-estimated": record}, now)
        self.assertFalse(changed)
        delete_video.assert_not_called()
        self.assertNotIn("aparat_expiry_status", record)

    def test_aparat_delete_failure_privatises_as_fallback_and_retries(self):
        now = datetime.now(timezone.utc)
        record = {
            "aparat_video_hash": "aparat_retry",
            "aparat_visibility": "public",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("aparat_uploader.aparat_credentials_available", return_value=True), patch(
            "aparat_uploader.delete_aparat_video", side_effect=RuntimeError("delete failed")
        ), patch("aparat_uploader.set_aparat_video_private", return_value=True) as fallback:
            changed = monitor._delete_expired_aparat_videos({"dkp-aparat-retry": record}, now)
        self.assertTrue(changed)
        fallback.assert_called_once_with("aparat_retry")
        self.assertEqual(record["aparat_expiry_status"], "delete_retry")
        self.assertIn("aparat_expiry_next_attempt_at", record)

    def test_expired_video_deletion_waits_for_aparat_credentials(self):
        now = datetime.now(timezone.utc)
        record = {
            "aparat_video_hash": "aparat_pending",
            "aparat_visibility": "public",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
                        "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        with patch("aparat_uploader.aparat_credentials_available", return_value=False), patch(
            "aparat_uploader.delete_aparat_video"
        ) as delete_video:
            changed = monitor._delete_expired_aparat_videos({"dkp-aparat-pending": record}, now)
        self.assertTrue(changed)
        delete_video.assert_not_called()
        self.assertEqual(record["aparat_expiry_status"], "pending_credentials")


    def test_live_price_audit_invalidates_exact_price_mismatch(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "posted_current_price": 100_000,
            "expires_at": "2026-10-25T18:00:00+00:00",
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_estimated": False,
            "telegram_message_id": 101,
            "bale_message_id": 202,
            "expiry_status": "tracked",
            "bale_expiry_status": "tracked",
        }
        snapshot = {
            "current_price": 120_000,
            "in_stock": True,
            "deal_expires_at": "",
            "expiry_verified_directly": False,
        }
        with patch.object(monitor, "fetch_live_product_status", return_value=snapshot):
            changed, summary = monitor._audit_live_prices(
                {"dkp-123": record}, now=now, batch_size=1,
                interval_seconds=3600, retry_seconds=900,
            )
        self.assertTrue(changed)
        self.assertEqual(summary["products_checked"], 1)
        self.assertEqual(summary["price_mismatches"], 1)
        self.assertEqual(record["price_audit_status"], "invalidated")
        self.assertEqual(record["price_audit_reason"], "price_mismatch")
        self.assertEqual(record["expiry_source"], "live_product_stock_or_price")
        self.assertEqual(record["expires_at"], now.isoformat())
        self.assertTrue(monitor._has_verified_deadline(record))

    def test_live_price_audit_invalidates_out_of_stock_product(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "posted_current_price": 100_000,
            "telegram_message_id": 101,
            "expiry_status": "tracked",
        }
        with patch.object(
            monitor, "fetch_live_product_status",
            return_value={"current_price": None, "in_stock": False},
        ):
            changed, summary = monitor._audit_live_prices(
                {"dkp-124": record}, now=now, batch_size=1,
            )
        self.assertTrue(changed)
        self.assertEqual(summary["out_of_stock_posts"], 1)
        self.assertEqual(record["price_audit_reason"], "out_of_stock")
        self.assertEqual(record["price_audit_status"], "invalidated")

    def test_live_price_audit_keeps_posts_when_direct_lookup_is_inconclusive(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "posted_current_price": 100_000,
            "expires_at": "2026-10-25T18:00:00+00:00",
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
            "telegram_message_id": 101,
            "expiry_status": "tracked",
        }
        with patch.object(monitor, "fetch_live_product_status", return_value={}):
            changed, summary = monitor._audit_live_prices(
                {"dkp-125": record}, now=now, batch_size=1,
            )
        self.assertTrue(changed)
        self.assertEqual(summary["unconfirmed"], 1)
        self.assertEqual(record["price_audit_status"], "unconfirmed")
        self.assertNotEqual(record.get("expiry_source"), "live_product_stock_or_price")
        self.assertNotEqual(record.get("expiry_reason"), "price_mismatch")

    def test_live_price_audit_refreshes_current_deadline_but_not_history_deadline(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        current_deadline = "2026-10-25T19:00:00+00:00"
        old_deadline = "2026-10-25T17:00:00+00:00"
        current = {
            "posted_current_price": 100_000,
            "expires_at": old_deadline,
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_estimated": False,
            "telegram_message_id": 101,
            "expiry_status": "tracked",
            "post_history": [{
                "posted_current_price": 100_000,
                "expires_at": old_deadline,
                "expiry_source": "digikala_mcp_offer_card",
                "expiry_estimated": False,
                "telegram_message_id": 99,
                "expiry_status": "tracked",
            }],
        }
        with patch.object(
            monitor, "fetch_live_product_status",
            return_value={
                "current_price": 100_000,
                "in_stock": True,
                "deal_expires_at": current_deadline,
                "expiry_verified_directly": True,
            },
        ):
            changed, summary = monitor._audit_live_prices(
                {"dkp-126": current}, now=now, batch_size=1,
            )
        self.assertTrue(changed)
        self.assertEqual(summary["price_mismatches"], 0)
        self.assertEqual(current["expires_at"], current_deadline)
        self.assertEqual(current["post_history"][0]["expires_at"], old_deadline)
        self.assertEqual(current["price_audit_status"], "match")
        self.assertEqual(current["post_history"][0]["price_audit_status"], "match")


    def test_live_price_audit_marks_mismatched_publication_for_deletion(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "telegram_message_id": 901,
            "bale_message_id": 902,
            "expiry_status": "tracked",
            "bale_expiry_status": "tracked",
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "posted_discount_percent": 50,
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
        }
        live = {
            "current_price": 125_000,
            "original_price": 200_000,
            "in_stock": True,
            "deal_expires_at": "",
            "expiry_verified_directly": False,
        }
        with patch.object(monitor, "fetch_live_product_status", return_value=live):
            result = monitor.audit_live_post_prices({"dkp-123": record}, now=now, max_products=1)
        self.assertEqual(result[1:4], (1, 1, 0))
        self.assertEqual(record["price_audit_status"], "mismatch_confirmed")
        self.assertEqual(record["price_audit_reason"], "price_mismatch")
        self.assertEqual(record["price_audit_mismatch_fields"], ["current_price"])
        self.assertEqual(record["expiry_reason"], "price_mismatch")
        self.assertEqual(record["expiry_source"], "live_product_stock_or_price")
        self.assertEqual(record["expires_at"], now.isoformat())
        self.assertTrue(monitor._has_verified_deadline(record))

    def test_live_price_audit_keeps_publication_when_prices_match(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "telegram_message_id": 903,
            "expiry_status": "tracked",
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
        }
        live = {
            "current_price": 100_000,
            "original_price": 200_000,
            "in_stock": True,
            "deal_expires_at": "",
            "expiry_verified_directly": False,
        }
        with patch.object(monitor, "fetch_live_product_status", return_value=live):
            result = monitor.audit_live_post_prices({"dkp-124": record}, now=now, max_products=1)
        self.assertTrue(result[0])
        self.assertEqual(result[1:4], (1, 0, 0))
        self.assertEqual(record["price_audit_status"], "matched")
        self.assertEqual(record["expires_at"], (now + timedelta(hours=1)).isoformat())
        self.assertNotIn("expiry_reason", record)

    def test_live_price_audit_api_failure_never_authorizes_deletion(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "telegram_message_id": 904,
            "expiry_status": "tracked",
            "posted_current_price": 100_000,
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
        }
        with patch.object(monitor, "fetch_live_product_status", return_value={}):
            result = monitor.audit_live_post_prices({"dkp-125": record}, now=now, max_products=1)
        self.assertEqual(result[1:4], (1, 0, 1))
        self.assertEqual(record["price_audit_status"], "inconclusive")
        self.assertNotIn("expiry_reason", record)
        self.assertTrue(monitor._has_verified_deadline(record))

    def test_verified_site_card_deadline_can_expire_when_live_product_has_no_active_timer(self):
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        record = {
            "posted_current_price": 100_000,
            "expires_at": (now - timedelta(minutes=11)).isoformat(),
            "expiry_source": "digikala_mcp_offer_card",
            "expiry_deadline_verified_from_site_card": True,
            "expiry_estimated": False,
            "expiry_status": "tracked",
        }
        live = {
            "current_price": 100_000,
            "original_price": 200_000,
            "in_stock": True,
            "deal_expires_at": "",
            "expiry_verified_directly": False,
        }
        with patch.object(monitor, "fetch_live_product_status", return_value=live):
            decision, changed = monitor._confirm_expiry_for_deletion(
                "dkp-126", record, now, budget={"remaining": 1}
            )
        self.assertEqual(decision, "confirmed")
        self.assertTrue(changed)
        self.assertEqual(record["expiry_last_removal_check_result"], "confirmed")


if __name__ == "__main__":
    unittest.main()
