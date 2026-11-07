import unittest
from datetime import datetime, timedelta, timezone

from affilio_radar import (
    FILO_UPLOAD_INTERVAL_HOURS,
    _filo_upload_slot_due,
    _initialize_filo_upload_slot,
)


class FiloUploadScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def test_first_filo_upload_is_due_without_filo_history(self):
        state = {}
        self.assertTrue(_filo_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=False))
        self.assertNotIn("filo_next_upload_at", state)

    def test_migrates_next_slot_from_latest_accepted_filo_submission(self):
        last_submission = self.now - timedelta(hours=1)
        state = {
            "published": {
                "older": {
                    "filo_upload_status": "published",
                    "filo_submitted_at": (self.now - timedelta(hours=9)).isoformat(),
                },
                "latest": {
                    "filo_upload_status": "submitted_pending_approval",
                    "filo_submitted_at": last_submission.isoformat(),
                },
                "youtube-only": {
                    "youtube_upload_status": "uploaded",
                    "youtube_uploaded_at": (self.now - timedelta(minutes=1)).isoformat(),
                },
            }
        }
        expected = last_submission + timedelta(hours=FILO_UPLOAD_INTERVAL_HOURS)
        self.assertEqual(_initialize_filo_upload_slot(state), expected)
        self.assertEqual(state["filo_next_upload_at"], expected.isoformat())
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))

    def test_persisted_filo_slot_takes_precedence_and_is_due_at_boundary(self):
        next_slot = self.now + timedelta(minutes=1)
        state = {
            "filo_next_upload_at": next_slot.isoformat(),
            "filo_last_upload_success_at": (self.now - timedelta(days=1)).isoformat(),
        }
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertTrue(_filo_upload_slot_due(state, next_slot, credentials_ready=True))
        self.assertEqual(state["filo_next_upload_at"], next_slot.isoformat())

    def test_unknown_submit_outcome_reserves_its_own_filo_slot(self):
        unknown_at = self.now - timedelta(minutes=20)
        state = {"filo_last_upload_outcome_unknown_at": unknown_at.isoformat()}
        expected = unknown_at + timedelta(hours=FILO_UPLOAD_INTERVAL_HOURS)
        self.assertEqual(_initialize_filo_upload_slot(state), expected)
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))

    def test_aparat_and_youtube_schedules_do_not_delay_first_filo_slot(self):
        state = {
            "youtube_next_upload_at": (self.now + timedelta(days=2)).isoformat(),
            "youtube_uploads_paused_until": (self.now + timedelta(days=1)).isoformat(),
            "aparat_next_upload_at": (self.now + timedelta(days=3)).isoformat(),
        }
        self.assertTrue(_filo_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertNotIn("filo_next_upload_at", state)


if __name__ == "__main__":
    unittest.main()
