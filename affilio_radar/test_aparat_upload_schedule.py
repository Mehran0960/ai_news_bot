import unittest
from datetime import datetime, timezone

import affilio_radar as radar
from platform_registry import PLATFORM_REGISTRY, VIDEO_PLATFORMS


class AparatVideoPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def test_artificial_upload_slots_are_not_exported_to_the_dispatch_sidecar(self):
        state = {
            "youtube_next_upload_at": "2026-11-14T12:00:00+00:00",
            "aparat_next_upload_at": "2026-11-15T12:00:00+00:00",
            "filo_next_upload_at": "2026-11-16T12:00:00+00:00",
            "published": {},
        }
        sidecar = radar.build_video_upload_dispatch_state(state, now=self.now)
        for legacy_slot in (
            "youtube_next_upload_at",
            "aparat_next_upload_at",
            "filo_next_upload_at",
        ):
            self.assertNotIn(legacy_slot, sidecar)

    def test_aparat_requires_directly_verified_expiry_but_filo_does_not(self):
        self.assertFalse(radar.video_deadline_allows_upload("aparat", False))
        self.assertTrue(radar.video_deadline_allows_upload("aparat", True))
        self.assertTrue(radar.video_deadline_allows_upload("filo", False))
        self.assertTrue(radar.video_deadline_allows_upload("youtube", False))

    def test_aparat_remains_a_registered_video_destination(self):
        self.assertEqual(PLATFORM_REGISTRY["aparat"]["media"], "video")
        self.assertIn("aparat", VIDEO_PLATFORMS)

    def test_retry_policy_is_bounded(self):
        self.assertGreaterEqual(radar.MAX_VIDEO_UPLOAD_ATTEMPTS, 1)
        self.assertLessEqual(radar.MAX_VIDEO_UPLOAD_ATTEMPTS, 5)


if __name__ == "__main__":
    unittest.main()
