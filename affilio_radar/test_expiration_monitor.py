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
