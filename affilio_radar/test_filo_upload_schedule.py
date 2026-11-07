import unittest
from datetime import datetime, timedelta, timezone

from affilio_radar import (
    FILO_UPLOAD_INTERVAL_HOURS,
    FILO_UPLOAD_INTERVAL_POLICY_VERSION,
    video_deadline_allows_upload,
    _filo_upload_slot_due,
    _initialize_filo_upload_slot,
    _filo_login_verified,
    build_video_upload_dispatch_state,
    _video_upload_candidate_sort_key,
)
from platform_registry import PLATFORM_REGISTRY, VIDEO_PLATFORMS
from publisher import _record_from_item


class FiloUploadScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def test_first_filo_upload_is_due_without_filo_history(self):
        state = {}
        self.assertTrue(_filo_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=False))
        self.assertNotIn("filo_next_upload_at", state)

    def test_migrates_next_slot_from_latest_accepted_filo_submission(self):
        last_submission = self.now - timedelta(minutes=10)
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
        self.assertEqual(FILO_UPLOAD_INTERVAL_HOURS, 27 / 60)
        self.assertEqual(_initialize_filo_upload_slot(state), expected)
        self.assertEqual(state["filo_next_upload_at"], expected.isoformat())
        self.assertEqual(state["filo_upload_interval_policy_version"], FILO_UPLOAD_INTERVAL_POLICY_VERSION)
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))

    def test_migrates_legacy_three_hour_filo_slot_to_27_minutes(self):
        last_success = self.now - timedelta(minutes=10)
        legacy_slot = last_success + timedelta(hours=3)
        state = {
            "filo_last_upload_success_at": last_success.isoformat(),
            "filo_next_upload_at": legacy_slot.isoformat(),
            "filo_upload_interval_policy_version": 1,
        }
        expected = last_success + timedelta(minutes=27)
        self.assertEqual(_initialize_filo_upload_slot(state), expected)
        self.assertEqual(state["filo_next_upload_at"], expected.isoformat())
        self.assertEqual(state["filo_upload_interval_policy_version"], FILO_UPLOAD_INTERVAL_POLICY_VERSION)
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))

    def test_filo_does_not_require_verified_retailer_deadline_but_aparat_does(self):
        self.assertTrue(video_deadline_allows_upload("filo", False))
        self.assertTrue(video_deadline_allows_upload("filo", True))
        self.assertFalse(video_deadline_allows_upload("aparat", False))
        self.assertTrue(video_deadline_allows_upload("aparat", True))

    def test_persisted_filo_slot_takes_precedence_and_is_due_at_boundary(self):
        next_slot = self.now + timedelta(minutes=1)
        state = {
            "filo_next_upload_at": next_slot.isoformat(),
            "filo_last_upload_success_at": (self.now - timedelta(days=1)).isoformat(),
            "filo_upload_interval_policy_version": FILO_UPLOAD_INTERVAL_POLICY_VERSION,
        }
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))
        self.assertTrue(_filo_upload_slot_due(state, next_slot, credentials_ready=True))
        self.assertEqual(state["filo_next_upload_at"], next_slot.isoformat())

    def test_unknown_submit_outcome_reserves_its_own_filo_slot(self):
        unknown_at = self.now - timedelta(minutes=20)
        state = {"filo_last_upload_outcome_unknown_at": unknown_at.isoformat()}
        expected = unknown_at + timedelta(minutes=27)
        self.assertEqual(_initialize_filo_upload_slot(state), expected)
        self.assertFalse(_filo_upload_slot_due(state, self.now, credentials_ready=True))

    def test_filo_queue_preserves_channel_publication_order(self):
        newer_high_discount = (
            self.now.timestamp(),
            "newer",
            {"posted_discount_percent": 90, "posted_original_price": 1_000, "posted_current_price": 100},
            self.now,
            None,
            False,
            ["filo"],
        )
        older_lower_discount = (
            (self.now - timedelta(minutes=27)).timestamp(),
            "older",
            {"posted_discount_percent": 20, "posted_original_price": 1_000, "posted_current_price": 800},
            self.now,
            None,
            False,
            ["filo"],
        )
        self.assertLess(
            _video_upload_candidate_sort_key(older_lower_discount),
            _video_upload_candidate_sort_key(newer_high_discount),
        )

    def test_filo_is_registered_as_a_video_destination(self):
        self.assertEqual(PLATFORM_REGISTRY["filo"]["media"], "video")
        self.assertIn("filo", VIDEO_PLATFORMS)

    def test_dispatch_sidecar_includes_filo_status_and_next_slot(self):
        state = {
            "filo_next_upload_at": (self.now + timedelta(hours=2)).isoformat(),
            "published": {
                "sample": {
                    "ts": self.now.timestamp(),
                    "delivery_status": {"telegram": "sent"},
                    "filo_upload_status": "submitted_pending_approval",
                    "filo_next_attempt_at": (self.now + timedelta(minutes=20)).isoformat(),
                    "expiry_deadline_verified_directly": True,
                }
            },
        }
        sidecar = build_video_upload_dispatch_state(state, now=self.now)
        self.assertEqual(sidecar["filo_next_upload_at"], state["filo_next_upload_at"])
        self.assertEqual(sidecar["published"]["sample"]["filo_upload_status"], "submitted_pending_approval")
        self.assertEqual(
            sidecar["published"]["sample"]["filo_next_attempt_at"],
            state["published"]["sample"]["filo_next_attempt_at"],
        )

    def test_dispatch_sidecar_accepts_rubika_and_eitaa_channel_handoffs(self):
        state = {
            "published": {
                "rubika-only": {
                    "ts": self.now.timestamp(),
                    "delivery_status": {"rubika": "sent"},
                    "filo_upload_status": "pending",
                },
                "eitaa-only": {
                    "ts": self.now.timestamp() - 10,
                    "delivery_status": {"eitaa": "sent"},
                    "filo_upload_status": "pending",
                },
                "not-sent": {
                    "ts": self.now.timestamp(),
                    "delivery_status": {"telegram": "pending"},
                    "filo_upload_status": "pending",
                },
            }
        }
        sidecar = build_video_upload_dispatch_state(state, now=self.now)
        self.assertEqual(set(sidecar["published"]), {"rubika-only", "eitaa-only"})
        self.assertEqual(sidecar["published"]["rubika-only"]["delivery_status"]["rubika"], "sent")
        self.assertEqual(sidecar["published"]["eitaa-only"]["delivery_status"]["eitaa"], "sent")

    def test_same_delivery_retry_preserves_filo_submit_status_and_link(self):
        old = {
            "distribution_queue_id": "product-1",
            "filo_upload_status": "submitted_pending_approval",
            "filo_video_url": "https://ifilo.net/v/abc123",
            "filo_submitted_at": self.now.isoformat(),
            "filo_visibility": "pending",
        }
        item = {
            "product_id": "product-1",
            "title": "محصول آزمایشی",
            "product_url": "https://www.digikala.com/product/dkp-123",
            "image_url": "https://example.com/image.jpg",
        }
        record = _record_from_item(item, old, self.now + timedelta(minutes=1), "product-1")
        self.assertEqual(record["filo_upload_status"], "submitted_pending_approval")
        self.assertEqual(record["filo_video_url"], old["filo_video_url"])
        self.assertEqual(record["filo_submitted_at"], old["filo_submitted_at"])

    def test_filo_login_verification_is_required_and_expires_after_seven_days(self):
        self.assertFalse(_filo_login_verified({}, self.now))
        recent = {
            "filo_login_verification_status": "verified",
            "filo_login_verified_at": (self.now - timedelta(hours=1)).isoformat(),
        }
        self.assertTrue(_filo_login_verified(recent, self.now))
        self.assertFalse(_filo_login_verified({
            **recent,
            "filo_login_verified_at": (self.now - timedelta(days=8)).isoformat(),
        }, self.now))
        self.assertFalse(_filo_login_verified({
            **recent,
            "filo_login_verified_at": (self.now + timedelta(minutes=1)).isoformat(),
        }, self.now))
        self.assertFalse(_filo_login_verified({
            **recent,
            "filo_login_verification_status": "failed",
        }, self.now))

    def test_dispatch_sidecar_carries_filo_login_verification(self):
        state = {
            "filo_login_verification_status": "verified",
            "filo_login_verified_at": self.now.isoformat(),
            "published": {},
        }
        sidecar = build_video_upload_dispatch_state(state, now=self.now)
        self.assertEqual(sidecar["filo_login_verified_at"], state["filo_login_verified_at"])
        self.assertEqual(sidecar["filo_login_verification_status"], "verified")

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
