import unittest
from datetime import datetime, timedelta, timezone

from affilio_radar import (
    APARAT_UPLOAD_INTERVAL_HOURS,
    _aparat_upload_slot_due,
    _initialize_aparat_upload_slot,
)


class AparatUploadScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)

    def test_first_upload_is_due_without_aparat_history(self):
        state = {}
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertFalse(_aparat_upload_slot_due(state, self.now, credentials_ready=False))
        self.assertNotIn("aparat_next_upload_at", state)

    def test_migrates_next_slot_from_latest_successful_aparat_upload(self):
        last_upload = self.now - timedelta(hours=1)
        state = {
            "published": {
                "older": {
                    "aparat_upload_status": "uploaded",
                    "aparat_uploaded_at": (self.now - timedelta(hours=9)).isoformat(),
                },
                "latest": {
                    "aparat_upload_status": "uploaded",
                    "aparat_uploaded_at": last_upload.isoformat(),
                },
                "youtube-only": {
                    "youtube_upload_status": "uploaded",
                    "youtube_uploaded_at": (self.now - timedelta(minutes=1)).isoformat(),
                },
            }
        }
        expected = last_upload + timedelta(hours=APARAT_UPLOAD_INTERVAL_HOURS)
        self.assertEqual(_initialize_aparat_upload_slot(state), expected)
        self.assertEqual(state["aparat_next_upload_at"], expected.isoformat())
        self.assertFalse(_aparat_upload_slot_due(state, self.now, credentials_ready=True))

    def test_persisted_aparat_slot_takes_precedence_and_is_due_at_boundary(self):
        next_slot = self.now + timedelta(minutes=1)
        state = {
            "aparat_next_upload_at": next_slot.isoformat(),
            "aparat_last_upload_success_at": (self.now - timedelta(days=1)).isoformat(),
        }
        self.assertFalse(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertTrue(_aparat_upload_slot_due(state, next_slot, credentials_ready=True))
        self.assertEqual(state["aparat_next_upload_at"], next_slot.isoformat())

    def test_unknown_upload_outcome_reserves_its_own_aparat_slot(self):
        unknown_at = self.now - timedelta(minutes=20)
        state = {"aparat_last_upload_outcome_unknown_at": unknown_at.isoformat()}
        expected = unknown_at + timedelta(hours=APARAT_UPLOAD_INTERVAL_HOURS)
        self.assertEqual(_initialize_aparat_upload_slot(state), expected)
        self.assertFalse(_aparat_upload_slot_due(state, self.now, credentials_ready=True))

    def test_youtube_history_and_pause_do_not_delay_first_aparat_slot(self):
        state = {
            "youtube_next_upload_at": (self.now + timedelta(days=2)).isoformat(),
            "youtube_uploads_paused_until": (self.now + timedelta(days=1)).isoformat(),
            "published": {
                "youtube-only": {
                    "youtube_upload_status": "uploaded",
                    "youtube_uploaded_at": (self.now - timedelta(minutes=10)).isoformat(),
                }
            },
        }
        self.assertTrue(_aparat_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertNotIn("aparat_next_upload_at", state)


if __name__ == "__main__":
    unittest.main()
