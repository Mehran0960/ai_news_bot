from __future__ import annotations

import json
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import campaign_publisher as publisher


class CampaignPublisherTests(unittest.TestCase):
    def valid_config(self):
        return {
            "campaign_id": "digikala-digitalchoices-1405-aban",
            "title": "تخفیف آبان",
            "affiliate_url": "https://aflo.ir/Dwndykmy",
            "landing_url": "https://www.digikala.com/landing/digitalchoices/",
            "deadline_label": "۳۰ آبان ۱۴۰۵",
            "expires_through_local_date": "2026-11-21",
        }

    def test_exact_campaign_link_is_allowlisted(self):
        publisher.validate_campaign(self.valid_config())

    def test_non_campaign_or_modified_affiliate_url_is_rejected(self):
        for changed in (
            "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2F",
            "https://aflo.ir/Dwndykmy?x=1",
            "http://aflo.ir/Dwndykmy",
            "https://example.com/Dwndykmy",
            "https://aflo.ir/another-link",
        ):
            config = self.valid_config()
            config["affiliate_url"] = changed
            with self.subTest(url=changed), self.assertRaises(ValueError):
                publisher.validate_campaign(config)

    def test_destination_cannot_be_changed(self):
        config = self.valid_config()
        config["landing_url"] = "https://www.digikala.com/"
        with self.assertRaisesRegex(ValueError, "destination"):
            publisher.validate_campaign(config)

    def test_campaign_is_active_through_local_deadline(self):
        config = self.valid_config()
        before_midnight = datetime(2026, 11, 21, 23, 59, tzinfo=ZoneInfo("Asia/Tehran"))
        after_midnight = datetime(2026, 11, 22, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))
        self.assertFalse(publisher.campaign_is_expired(config, before_midnight))
        self.assertTrue(publisher.campaign_is_expired(config, after_midnight))

    def test_message_discloses_selected_products_and_deadline(self):
        message = publisher.campaign_message(self.valid_config())
        self.assertIn("تا سقف ۱۵ میلیون تومان", message)
        self.assertIn("کالاهای دیجیتال منتخب", message)
        self.assertIn("۳۰ آبان ۱۴۰۵", message)
        self.assertIn("شرایط استفاده", message)

    @patch("campaign_publisher.urlopen")
    def test_api_post_requires_success_and_returns_message_id(self, mock_urlopen):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"ok": True, "result": {"message_id": 123}}).encode()

        mock_urlopen.return_value = FakeResponse()
        message_id = publisher._api_post(
            "telegram", "not-a-real-token", "@OfferChin",
            "test message", "https://aflo.ir/Dwndykmy",
        )
        self.assertEqual(message_id, 123)
        request = mock_urlopen.call_args.args[0]
        self.assertIn("/sendMessage", request.full_url)
        self.assertNotIn("not-a-real-token", request.data.decode())


if __name__ == "__main__":
    unittest.main()
