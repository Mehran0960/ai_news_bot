import unittest
from datetime import datetime, timedelta, timezone

import affilio_radar as radar
from video_queue_maintenance import maintain_video_queue_state


class VideoQueueMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)

    def record(self, *, age_hours=2, generation="generated", status="pending", destination="youtube"):
        return {
            "ts": (self.now - timedelta(hours=age_hours)).timestamp(),
            "distribution_queue_id": "dkp-test:selection",
            "video_dispatch_eligible": True,
            "video_generation_status": generation,
            f"{destination}_upload_status": status,
        }

    def test_old_pending_product_becomes_terminal_and_no_longer_blocks_video_fifo(self):
        record = self.record(age_hours=25, status="retry")
        state = {"published": {"dkp-old": record}}

        summary = maintain_video_queue_state(
            state, "youtube", now=self.now, max_age_hours=24, credentials_ready=True
        )

        self.assertEqual(summary["stale"], 1)
        self.assertEqual(record["youtube_upload_status"], "skipped_stale_after_freshness_window")
        self.assertFalse(radar._has_pending_video_destination(record, {"youtube"}, now=self.now))

    def test_recent_credential_skip_is_requeued_when_credentials_return(self):
        record = self.record(age_hours=3, status="skipped_unavailable")
        record["youtube_skip_reason"] = "credentials_not_configured"
        state = {"published": {"dkp-recent": record}}

        summary = maintain_video_queue_state(
            state, "youtube", now=self.now, max_age_hours=24, credentials_ready=True
        )

        self.assertEqual(summary["requeued"], 1)
        self.assertEqual(record["youtube_upload_status"], "pending")
        self.assertTrue(radar._has_pending_video_destination(record, {"youtube"}, now=self.now))

    def test_recent_credential_skip_stays_untouched_without_credentials(self):
        record = self.record(age_hours=3, status="skipped_unavailable")
        state = {"published": {"dkp-recent": record}}

        summary = maintain_video_queue_state(
            state, "youtube", now=self.now, max_age_hours=24, credentials_ready=False
        )

        self.assertEqual(summary["requeued"], 0)
        self.assertEqual(record["youtube_upload_status"], "skipped_unavailable")

    def test_missing_timestamp_pending_record_is_terminalized(self):
        record = self.record(age_hours=0, status="pending")
        record.pop("ts")
        state = {"published": {"dkp-no-time": record}}

        summary = maintain_video_queue_state(
            state, "aparat", now=self.now, max_age_hours=24, credentials_ready=True
        )

        self.assertEqual(summary["stale"], 1)
        self.assertEqual(record["aparat_upload_status"], "skipped_stale_after_freshness_window")
        self.assertEqual(record["aparat_skip_reason"], "publication_timestamp_missing")

    def test_filo_submission_waiting_for_review_is_never_retried(self):
        record = self.record(age_hours=120, destination="filo", status="submitted_pending_approval")
        record["filo_video_url"] = "https://ifilo.net/v/Example"
        state = {"published": {"dkp-submitted": record}}

        summary = maintain_video_queue_state(
            state, "filo", now=self.now, max_age_hours=24, credentials_ready=True
        )

        self.assertEqual(summary["stale"], 0)
        self.assertEqual(record["filo_upload_status"], "submitted_pending_approval")
        self.assertEqual(record["filo_video_url"], "https://ifilo.net/v/Example")

    def test_aparat_unverified_deadline_skip_ages_out_instead_of_blocking(self):
        record = self.record(
            age_hours=30,
            generation="generated",
            status="skipped_unverified_deadline",
            destination="aparat",
        )
        state = {"published": {"dkp-old": record}}

        summary = maintain_video_queue_state(
            state, "aparat", now=self.now, max_age_hours=24, credentials_ready=True
        )

        self.assertEqual(summary["stale"], 1)
        self.assertEqual(record["aparat_upload_status"], "skipped_stale_after_freshness_window")
        self.assertFalse(radar._has_pending_video_destination(record, {"aparat"}, now=self.now))


if __name__ == "__main__":
    unittest.main()
