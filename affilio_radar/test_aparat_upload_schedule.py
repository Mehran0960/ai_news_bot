import unittest
from datetime import datetime, timedelta, timezone

from affilio_radar import (
    APARAT_UPLOAD_INTERVAL_HOURS,
    _aparat_upload_slot_due,
    _initialize_aparat_upload_slot,
)


class AparatUploadScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def test_aparat_interval_is_disabled_and_first_upload_is_immediately_due(self):
        self.assertEqual(APARAT_UPLOAD_INTERVAL_HOURS, 0)
        state = {}
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertFalse(_aparat_upload_slot_due(state, self.now, credentials_ready=False))
        self.assertIsNone(_initialize_aparat_upload_slot(state))
        self.assertNotIn("aparat_next_upload_at", state)

    def test_legacy_three_hour_slot_and_upload_history_do_not_delay_aparat(self):
        last_upload = self.now - timedelta(minutes=1)
        state = {
            "aparat_next_upload_at": (self.now + timedelta(days=2)).isoformat(),
            "published": {
                "older": {
                    "aparat_upload_status": "uploaded",
                    "aparat_uploaded_at": (self.now - timedelta(days=2)).isoformat(),
                },
                "latest": {
                    "aparat_upload_status": "uploaded",
                    "aparat_uploaded_at": last_upload.isoformat(),
                },
            },
        }
        self.assertIsNone(_initialize_aparat_upload_slot(state))
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertNotIn("aparat_next_upload_at", state)

    def test_unknown_outcome_does_not_create_an_artificial_aparat_wait(self):
        state = {
            "aparat_last_upload_outcome_unknown_at":
                (self.now - timedelta(seconds=5)).isoformat(),
            "aparat_next_upload_at": (self.now + timedelta(hours=8)).isoformat(),
        }
        self.assertIsNone(_initialize_aparat_upload_slot(state))
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertNotIn("aparat_next_upload_at", state)

    def test_youtube_pause_and_legacy_slot_do_not_delay_aparat(self):
        state = {
            "youtube_next_upload_at": (self.now + timedelta(days=2)).isoformat(),
            "youtube_uploads_paused_until": (self.now + timedelta(days=1)).isoformat(),
            "aparat_next_upload_at": (self.now + timedelta(days=3)).isoformat(),
        }
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertNotIn("aparat_next_upload_at", state)


if __name__ == "__main__":
    unittest.main()
