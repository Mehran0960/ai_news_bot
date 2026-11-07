import unittest
from unittest.mock import patch
from messenger_adapters import send_eitaa_photo, send_rubika_photo


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
    def _is_valid_affilio_tracking_url(self, value):
        return value.startswith("https://aflo.ir/")
    def build_discount_image(self, image_bytes, discount, merchant=None, extra_watermarks=None):
        self.render_calls.append(extra_watermarks)
        return b"rendered-jpeg"
    def build_caption(self, item, affiliate_url, channel_label, use_unicode_strikethrough=False):
        return f"Offer [{channel_label}]({channel_label})"


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
        self.assertIn(self.affiliate, post.call_args.kwargs["json"]["text"])
        self.assertEqual(self.renderer.render_calls, [[("rubika", "روبیکا | آفِرچین")]])

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

    @patch("messenger_adapters.requests.post")
    def test_eitaa_acceptance_without_message_id_uses_receipt_not_fake_id(self, post):
        post.return_value = FakeResponse({"ok": True, "result": "success"})
        result = send_eitaa_photo(
            "test-token", "@offerchin", self.item, self.image, self.affiliate, self.renderer
        )
        self.assertEqual(result, {"delivery_receipt": "eitaayar-api-accepted"})
        self.assertNotIn("message_id", result)
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], "@offerchin")
        self.assertIn(self.affiliate, post.call_args.kwargs["data"]["caption"])

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
