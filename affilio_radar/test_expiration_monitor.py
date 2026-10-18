import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

import expiration_monitor as monitor


class ExpirationMonitorTests(unittest.TestCase):
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

    def test_probe_interval_prevents_repeated_unknown_feed_checks(self):
        now = datetime.now(timezone.utc)
        record = {"expiry_last_probed_at": now.isoformat()}
        with patch.object(monitor, "UNKNOWN_PROBE_INTERVAL_SECONDS", 900):
            self.assertFalse(monitor._should_probe(record, now))
            self.assertTrue(monitor._should_probe(record, now + timedelta(minutes=16)))



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

    def test_public_history_audit_deletes_untracked_expired_post(self):
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
        }
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        with patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion:
            result = monitor.audit_public_channel_history({}, now=now, posts={77: old_post})
        deletion.assert_called_once_with(77)
        self.assertEqual(result[1], 1)
        self.assertEqual(result[2], 0)

    def test_public_history_falls_back_to_expired_label_and_removes_purchase_button(self):
        old_post = {
            "message_id": 77,
            "caption_text": "🛍️ محصول نمونه ⏳ پایان تخفیف: شنبه ۲۵ مهر ۱۴۰۵، ساعت ۲۳:۵۹",
            "caption_html": "",
        }
        record = {"telegram_message_id": 77, "title": "محصول نمونه", "expiry_status": "tracked"}
        now = datetime(2026, 10, 18, 4, 30, tzinfo=timezone.utc)
        with (
            patch.object(monitor, "_telegram_delete", return_value="already_absent"),
            patch.object(monitor, "_telegram_mark_expired", return_value="edited") as mark,
        ):
            result = monitor.audit_public_channel_history({"dkp-123": record}, now=now, posts={77: old_post})
        mark.assert_called_once_with(77, "محصول نمونه")
        self.assertEqual(record["expiry_status"], "expired_marked")
        self.assertEqual(result[2], 1)

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
        with patch.object(monitor, "_telegram_edit_caption", return_value="edited") as edit:
            result = monitor.audit_public_channel_history({}, now=now, posts={88: legacy})
        edit.assert_called_once()
        edited_caption = edit.call_args.args[1]
        self.assertIn("<b><u>💚 قیمت ویژه: 💰 ۱۱۴٬۰۰۰ تومان</u></b>", edited_caption)
        self.assertIn("<b><u>⚡️ ۸۹٪ تخفیف</u></b>", edited_caption)
        self.assertIn('<a href="https://telegram.me/OfferChin">عضویت در کانال OfferChin</a>', edited_caption)
        self.assertIn("زمان باقی‌مانده", edited_caption)
        self.assertEqual(result[3], 1)


    def test_confirmed_deadline_does_not_need_another_network_probe(self):
        now = datetime.now(timezone.utc)
        record = {
            "telegram_message_id": 77,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "expiry_estimated": False,
        }
        self.assertFalse(monitor._should_probe(record, now))

    def test_expired_posts_are_deleted_before_a_failing_live_feed_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "published": {
                    "dkp-12345": {
                        "telegram_message_id": 77,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                        "expiry_source": "digikala_live_deals_feed",
                        "expiry_estimated": False,
                        "expiry_status": "tracked",
                    },
                    "dkp-67890": {
                        "telegram_message_id": 88,
                        "product_url": "https://www.digikala.com/product/dkp-67890/",
                        "expires_at": "",
                    },
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(monitor, "STATE_PATH", state_path),
                patch.object(monitor, "BOT_TOKEN", "test-token"),
                patch.object(monitor, "audit_public_channel_history", return_value=(False, 0, 0, 0, 0)),
                patch.object(monitor, "fetch_offer_expiries", side_effect=RuntimeError("feed unavailable")),
                patch.object(monitor, "fetch_live_product_status", return_value={}),
                patch.object(monitor, "_telegram_delete", return_value="deleted") as deletion,
            ):
                self.assertEqual(monitor.run(), 0)
            deletion.assert_called_once_with(77)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["published"]["dkp-12345"]["expiry_status"], "deleted")
            self.assertIn("expired_deleted_at", saved["published"]["dkp-12345"])


    def test_expired_post_is_deleted_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "published": {
                    "dkp-12345": {
                        "telegram_message_id": 77,
                        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
                        "expiry_source": "test",
                        "expiry_status": "tracked",
                    }
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                patch.object(monitor, "STATE_PATH", state_path),
                patch.object(monitor, "BOT_TOKEN", "test-token"),
                patch.object(monitor, "audit_public_channel_history", return_value=(False, 0, 0, 0, 0)),
                patch.object(monitor, "fetch_offer_expiries", return_value={}),
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
                        "expiry_source": "test",
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
                patch.object(monitor, "fetch_offer_expiries", return_value={}),
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


if __name__ == "__main__":
    unittest.main()
