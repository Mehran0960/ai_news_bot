import unittest
from datetime import datetime, timedelta, timezone

from aparat_shorts_migration import migrate_recent_regular_uploads


class AparatShortsMigrationTests(unittest.TestCase):
    def test_withdraws_recent_public_regular_uploads_and_never_resurrects_expired_offers(self):
        now = datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)
        published = {
            "recent-active": {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "public",
                "aparat_uploaded_at": (cutoff + timedelta(minutes=10)).isoformat(),
                "aparat_video_hash": "vid-active",
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
            "recent-expired": {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "public",
                "aparat_uploaded_at": (cutoff + timedelta(minutes=20)).isoformat(),
                "aparat_video_hash": "vid-expired",
                "expires_at": (now - timedelta(minutes=10)).isoformat(),
            },
            "old-public": {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "public",
                "aparat_uploaded_at": (cutoff - timedelta(minutes=1)).isoformat(),
                "aparat_video_hash": "vid-old",
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
            "private-test": {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "non_public_test",
                "aparat_uploaded_at": (cutoff + timedelta(minutes=30)).isoformat(),
                "aparat_video_hash": "vid-test",
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
            "missing-hash": {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "public",
                "aparat_uploaded_at": (cutoff + timedelta(minutes=30)).isoformat(),
                "aparat_video_hash": "",
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            },
        }
        calls = []

        def make_private(video_hash):
            calls.append(video_hash)
            return True

        result = migrate_recent_regular_uploads(
            published,
            private_video=make_private,
            now=now,
            cutoff=cutoff,
            max_items=10,
            sleep_fn=lambda _: None,
        )

        self.assertEqual(calls, ["vid-active", "vid-expired"])
        self.assertEqual(result["hidden"], 2)
        self.assertEqual(result["eligible"], 2)
        self.assertEqual(published["recent-active"]["aparat_visibility"], "private_waiting_for_shorts")
        self.assertEqual(
            published["recent-active"]["aparat_shorts_migration_status"],
            "withdrawn_waiting_for_shorts_upload",
        )
        self.assertEqual(
            published["recent-expired"]["aparat_shorts_migration_status"],
            "withdrawn_expired_or_unverified_offer",
        )
        self.assertEqual(published["old-public"]["aparat_visibility"], "public")
        self.assertEqual(published["private-test"]["aparat_visibility"], "non_public_test")

    def test_failed_private_update_is_recorded_for_retry_without_blocking_other_videos(self):
        now = datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)
        published = {}
        for product_id, video_hash in (("bad", "hash-bad"), ("good", "hash-good")):
            published[product_id] = {
                "aparat_upload_status": "uploaded",
                "aparat_visibility": "public",
                "aparat_uploaded_at": (cutoff + timedelta(minutes=20)).isoformat(),
                "aparat_video_hash": video_hash,
                "expires_at": (now + timedelta(hours=2)).isoformat(),
            }
        calls = []

        def make_private(video_hash):
            calls.append(video_hash)
            if video_hash == "hash-bad":
                raise TimeoutError("test timeout")
            return True

        result = migrate_recent_regular_uploads(
            published,
            private_video=make_private,
            now=now,
            cutoff=cutoff,
            max_items=10,
            sleep_fn=lambda _: None,
        )

        self.assertEqual(calls, ["hash-bad", "hash-good"])
        self.assertEqual(result["retry"], 1)
        self.assertEqual(result["hidden"], 1)
        self.assertEqual(published["bad"]["aparat_shorts_migration_status"], "retry")
        self.assertTrue(published["bad"].get("aparat_shorts_migration_next_attempt_at"))
        self.assertEqual(published["good"]["aparat_visibility"], "private_waiting_for_shorts")


if __name__ == "__main__":
    unittest.main()
