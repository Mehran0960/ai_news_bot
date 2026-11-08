import unittest
from unittest.mock import patch
from messenger_adapters import (
    RUBIKA_CHANNEL_URL,
    RUBIKA_MEMBERSHIP_BUTTON_TEXT,
    _rubika_data,
    send_eitaa_photo,
    send_rubika_photo,
)
from offerchin_copy import MEMBERSHIP_BUTTON_TEXT, purchase_action_label


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError("HTTP failure")
    def json(self):
        return self.payload


class FakeRenderer:
    def __init__(self):
        self.render_calls = []
        self.destinations = []
        self.caption_calls = []
    def _is_valid_affilio_tracking_url(self, value):
        return value.startswith("https://aflo.ir/")
    def build_discount_image(
        self, image_bytes, discount, merchant=None, extra_watermarks=None,
        destination_platform=None,
    ):
        self.render_calls.append(extra_watermarks)
        self.destinations.append(destination_platform)
        return b"rendered-jpeg"
    def build_caption(self, item, affiliate_url, channel_label, use_unicode_strikethrough=False):
        self.caption_calls.append({
            "channel_label": channel_label,
            "use_unicode_strikethrough": use_unicode_strikethrough,
        })
        return (
            "*🔥 فروش ویژه دیجی‌کالا 🔴*\n\n"
            "🛍️ محصول آزمایشی\n\n"
            "────────────\n\n"
            "*💚 قیمت فعلی: ۱٬۰۰۰ تومان*\n\n"
            "*⚡️ ۳۰٪ تخفیف*\n\n"
            "*💳 با امکان خرید اقساطی (دیجی پی)*\n"
            "────────────\n\n"
            f"[➕ عضویت در کانال آفِرچین]({channel_label})"
        )
    def purchase_button_label(self, affiliate_url):
        return "🛍️ مشاهده و خرید از دیجی‌کالا"


class MessengerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.renderer = FakeRenderer()
        self.item = {"title": "محصول آزمایشی", "discount_percent": 30, "merchant": "دیجی‌کالا"}
        self.image = b"source-image"
        self.affiliate = (
            "https://aflo.ir/QekEYTRg?p="
            "https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1%2F"
        )

    @patch("messenger_adapters.requests.post")
    def test_rubika_uploads_then_sends_photo_and_returns_message_id(self, post):
        post.side_effect = [
            FakeResponse({"status": "OK", "data": {"upload_url": "https://upload.rubika.ir/upload/abc"}}),
            FakeResponse({"status": "OK", "data": {"file_id": "FILE-1"}}),
            FakeResponse({"status": "OK", "data": {"message_id": "MESSAGE-9"}}),
        ]
        result = send_rubika_photo(
            "test-token", "test-channel", self.item, self.image, self.affiliate, self.renderer
        )
        self.assertEqual(result, {"message_id": "MESSAGE-9"})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args.kwargs["json"]["file_id"], "FILE-1")
        payload = post.call_args.kwargs["json"]
        self.assertNotIn(self.affiliate, payload["text"], "purchase URL belongs in its own direct button")
        self.assertIn("فروش ویژه دیجی‌کالا", payload["text"])
        self.assertIn("💚 قیمت فعلی: ۱٬۰۰۰ تومان", payload["text"])
        self.assertIn("۳۰٪ تخفیف", payload["text"])
        self.assertIn("با امکان خرید اقساطی (دیجی پی)", payload["text"])
        self.assertNotIn("[➕ عضویت", payload["text"], "Rubika renders membership as a clickable button")
        self.assertEqual(self.renderer.caption_calls, [{
            "channel_label": RUBIKA_CHANNEL_URL,
            "use_unicode_strikethrough": True,
        }])
        keypad = payload["inline_keypad"]
        self.assertEqual(len(keypad["rows"]), 2)
        buy_button = keypad["rows"][0]["buttons"][0]
        join_button = keypad["rows"][1]["buttons"][0]
        self.assertEqual(buy_button["type"], "Link")
        self.assertEqual(buy_button["button_text"], purchase_action_label("دیجی‌کالا"))
        self.assertEqual(buy_button["button_link"], {
            "type": "url",
            "link_url": self.affiliate,
        })
        self.assertEqual(join_button["type"], "Link")
        self.assertEqual(join_button["button_text"], RUBIKA_MEMBERSHIP_BUTTON_TEXT)
        self.assertEqual(join_button["button_text"], MEMBERSHIP_BUTTON_TEXT)
        self.assertEqual(join_button["button_link"], {
            "type": "url",
            "link_url": RUBIKA_CHANNEL_URL,
        })
        self.assertEqual(self.renderer.render_calls, [None])
        self.assertEqual(self.renderer.destinations, ["rubika"])

    @patch("messenger_adapters.requests.post")
    def test_rubika_invalid_keypad_input_falls_back_to_plain_caption_links(self, post):
        post.side_effect = [
            FakeResponse({"status": "OK", "data": {"upload_url": "https://upload.rubika.ir/upload/abc"}}),
            FakeResponse({"status": "OK", "data": {"file_id": "FILE-1"}}),
            FakeResponse({"status": "ERROR", "error_code": "INVALID_INPUT"}),
            FakeResponse({"status": "OK", "data": {"message_id": "MESSAGE-FALLBACK"}}),
        ]
        result = send_rubika_photo(
            "test-token", "test-channel", self.item, self.image, self.affiliate, self.renderer
        )
        self.assertEqual(result, {"message_id": "MESSAGE-FALLBACK"})
        self.assertEqual(post.call_count, 4)
        first_send = post.call_args_list[2].kwargs["json"]
        fallback_send = post.call_args_list[3].kwargs["json"]
        self.assertIn("inline_keypad", first_send)
        self.assertNotIn("inline_keypad", fallback_send)
        self.assertIn(self.affiliate, fallback_send["text"])
        self.assertIn(RUBIKA_CHANNEL_URL, fallback_send["text"])
        self.assertIn(purchase_action_label("دیجی‌کالا"), fallback_send["text"])
        self.assertIn(RUBIKA_MEMBERSHIP_BUTTON_TEXT, fallback_send["text"])

    @patch("messenger_adapters.requests.post")
    def test_rubika_does_not_retry_ambiguous_or_non_validation_errors(self, post):
        post.side_effect = [
            FakeResponse({"status": "OK", "data": {"upload_url": "https://upload.rubika.ir/upload/abc"}}),
            FakeResponse({"status": "OK", "data": {"file_id": "FILE-1"}}),
            FakeResponse({"status": "ERROR", "error_code": "SERVER_ERROR"}),
        ]
        with self.assertRaisesRegex(RuntimeError, "SERVER_ERROR"):
            send_rubika_photo(
                "test-token", "test-channel", self.item, self.image, self.affiliate, self.renderer
            )
        self.assertEqual(post.call_count, 3)

    @patch("messenger_adapters.requests.post")
    def test_rubika_rejects_non_https_upload_url(self, post):
        post.return_value = FakeResponse(
            {"status": "OK", "data": {"upload_url": "http://unsafe.invalid/upload"}}
        )
        with self.assertRaisesRegex(RuntimeError, "invalid upload URL"):
            send_rubika_photo(
                "test-token", "test-channel", self.item, self.image, self.affiliate, self.renderer
            )
        self.assertEqual(post.call_count, 1)

    def test_rubika_api_rejection_reports_safe_code_and_redacted_message(self):
        with self.assertRaises(RuntimeError) as raised:
            _rubika_data({
                "status": "ERROR",
                "error": {
                    "code": "CHAT_NOT_FOUND",
                    "message": "channel rejected https://private.invalid/path token=do-not-log-this",
                },
            }, "sendFile")
        message = str(raised.exception)
        self.assertIn("CHAT_NOT_FOUND", message)
        self.assertIn("[redacted-url]", message)
        self.assertIn("token=[redacted]", message)
        self.assertNotIn("do-not-log-this", message)
        self.assertIn("status=ERROR", message)

    @patch("messenger_adapters.requests.post")
    def test_eitaa_acceptance_without_message_id_uses_receipt_not_fake_id(self, post):
        post.return_value = FakeResponse({"ok": True, "result": "success"})
        result = send_eitaa_photo(
            "test-token", "@offerchin", self.item, self.image, self.affiliate, self.renderer
        )
        self.assertEqual(result, {"delivery_receipt": "eitaayar-api-accepted"})
        self.assertNotIn("message_id", result)
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "@offerchin")
        caption = post.call_args.kwargs["data"]["caption"]
        self.assertIn(self.affiliate, caption)
        self.assertIn("🛍️ مشاهده و خرید از دیجی‌کالا\n" + self.affiliate, caption)
        self.assertNotIn("در ایتا", caption)
        self.assertNotIn("https://eitaa.com", caption)
        self.assertNotIn(f"[{MEMBERSHIP_BUTTON_TEXT}]", caption)
        self.assertEqual(self.renderer.destinations, ["eitaa"])

    
    @patch("messenger_adapters.EITAA_CHANNEL_URL", "https://eitaa.com/offerchin")
    @patch("messenger_adapters.requests.post")
    def test_eitaa_uses_the_shared_membership_label_only_with_a_configured_public_url(self, post):
        post.return_value = FakeResponse({"ok": True, "result": "success"})
        send_eitaa_photo(
            "test-token", "@offerchin", self.item, self.image, self.affiliate, self.renderer
        )
        caption = post.call_args.kwargs["data"]["caption"]
        self.assertIn(f"{MEMBERSHIP_BUTTON_TEXT}\nhttps://eitaa.com/offerchin", caption)
        self.assertNotIn(f"[{MEMBERSHIP_BUTTON_TEXT}]", caption)
        self.assertIn("🛍️ مشاهده و خرید از دیجی‌کالا\n" + self.affiliate, caption)

    @patch("messenger_adapters.requests.post")
    def test_eitaa_rejection_is_not_marked_as_success(self, post):
        post.return_value = FakeResponse({"ok": False, "result": "error"})
        with self.assertRaisesRegex(RuntimeError, "did not confirm acceptance"):
            send_eitaa_photo(
                "test-token", "@offerchin", self.item, self.image, self.affiliate, self.renderer
            )

    @patch("messenger_adapters.requests.post")
    def test_invalid_affiliate_link_blocks_both_adapters(self, post):
        self.renderer._is_valid_affilio_tracking_url = lambda _value: False
        with self.assertRaisesRegex(RuntimeError, "verified affiliate URL"):
            send_rubika_photo(
                "test-token", "test-channel", self.item, self.image, "https://bad.invalid/", self.renderer
            )
        with self.assertRaisesRegex(RuntimeError, "verified affiliate URL"):
            send_eitaa_photo(
                "test-token", "test-channel", self.item, self.image, "https://bad.invalid/", self.renderer
            )
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
