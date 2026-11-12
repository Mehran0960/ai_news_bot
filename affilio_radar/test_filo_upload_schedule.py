import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import affilio_radar as radar
from platform_registry import PLATFORM_REGISTRY, VIDEO_PLATFORMS
from publisher import _record_from_item


class FiloSharedVideoQueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def test_filo_login_verification_is_required_and_expires_after_seven_days(self):
        self.assertFalse(radar._filo_login_verified({}, self.now))
        recent = {
            "filo_login_verification_status": "verified",
            "filo_login_verified_at": (self.now - timedelta(hours=1)).isoformat(),
        }
        self.assertTrue(radar._filo_login_verified(recent, self.now))
        self.assertFalse(radar._filo_login_verified({
            **recent,
            "filo_login_verified_at": (self.now - timedelta(days=8)).isoformat(),
        }, self.now))
        self.assertFalse(radar._filo_login_verified({
            **recent,
            "filo_login_verified_at": (self.now + timedelta(minutes=1)).isoformat(),
        }, self.now))
        self.assertFalse(radar._filo_login_verified({
            **recent,
            "filo_login_verification_status": "failed",
        }, self.now))

    def test_filo_is_registered_in_the_common_video_destinations(self):
        self.assertEqual(PLATFORM_REGISTRY["filo"]["media"], "video")
        self.assertIn("filo", VIDEO_PLATFORMS)
        self.assertEqual(set(VIDEO_PLATFORMS), {"youtube", "aparat", "filo"})

    def test_filo_uses_the_same_oldest_first_channel_sequence(self):
        newer_high_discount = (
            self.now.timestamp(), "newer",
            {"posted_discount_percent": 90, "posted_original_price": 1000, "posted_current_price": 100},
            self.now, None, False, ["filo"],
        )
        older_lower_discount = (
            (self.now - timedelta(minutes=27)).timestamp(), "older",
            {"posted_discount_percent": 20, "posted_original_price": 1000, "posted_current_price": 800},
            self.now, None, False, ["filo"],
        )
        self.assertLess(
            radar._video_upload_candidate_sort_key(older_lower_discount),
            radar._video_upload_candidate_sort_key(newer_high_discount),
        )

    def test_combined_runner_passes_all_three_destinations_and_bypasses_only_cadence(self):
        with patch("affilio_radar.load_state", side_effect=[{}, {}]), \
             patch("affilio_radar.process_pending_short_video", side_effect=[True, False]) as process:
            result = radar.run_video_fanout_only()

        self.assertEqual(result, 0)
        self.assertEqual(process.call_count, 2)
        first_kwargs = process.call_args_list[0].kwargs
        self.assertEqual(first_kwargs["destinations"], {"youtube", "aparat", "filo"})
        self.assertTrue(first_kwargs["force_due"])

    def test_filo_submission_state_is_preserved_for_same_canonical_delivery(self):
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

    def test_dispatch_sidecar_contains_filo_login_state_but_no_per_platform_slots(self):
        state = {
            "filo_login_verification_status": "verified",
            "filo_login_verified_at": self.now.isoformat(),
            "youtube_next_upload_at": (self.now + timedelta(days=2)).isoformat(),
            "aparat_next_upload_at": (self.now + timedelta(days=3)).isoformat(),
            "filo_next_upload_at": (self.now + timedelta(days=4)).isoformat(),
            "published": {},
        }
        sidecar = radar.build_video_upload_dispatch_state(state, now=self.now)
        self.assertEqual(sidecar["filo_login_verification_status"], "verified")
        self.assertEqual(sidecar["filo_login_verified_at"], self.now.isoformat())
        for legacy_slot in (
            "youtube_next_upload_at",
            "aparat_next_upload_at",
            "filo_next_upload_at",
        ):
            self.assertNotIn(legacy_slot, sidecar)

    def test_login_verification_is_persisted_to_state_and_dispatch_sidecar(self):
        state = {
            "filo_login_verification_status": "verified",
            "filo_login_verified_at": self.now.isoformat(),
            "filo_login_verification_attempted_at": self.now.isoformat(),
            "published": {},
        }
        with patch("affilio_radar.save_json") as save:
            radar._persist_filo_login_state(state, self.now)

        self.assertEqual(save.call_count, 2)
        self.assertEqual(save.call_args_list[0].args[0].name, "state.json")
        self.assertEqual(save.call_args_list[1].args[0], radar.VIDEO_DISPATCH_STATE)
        sidecar = save.call_args_list[1].args[1]
        self.assertEqual(sidecar["filo_login_verification_status"], "verified")
        self.assertEqual(sidecar["filo_login_verified_at"], self.now.isoformat())


if __name__ == "__main__":
    unittest.main()
