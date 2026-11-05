import json
import tempfile
import unittest
from pathlib import Path

from export_video_dispatch_state import build_dispatch_state, export_dispatch_state


class VideoDispatchStateTests(unittest.TestCase):
    def test_snapshot_is_small_deterministic_and_keeps_only_latest_six_records(self):
        published = {
            f"dkp-{index}": {
                "ts": index,
                "title": "must not be copied",
                "posted_current_price": 123,
                "telegram_message_id": index,
                "delivery_status": {"telegram": "sent", "bale": "sent", "youtube": "ignored"},
                "youtube_upload_status": "pending",
                "aparat_upload_status": "pending",
                "video_generation_status": "generated",
                "expires_at": "2030-01-01T00:00:00Z",
                "extra_large_blob": "x" * 5000,
            }
            for index in range(1, 10)
        }
        state = {
            "youtube_next_upload_at": "2026-11-05T18:00:00Z",
            "youtube_uploads_paused_until": None,
            "aparat_next_upload_at": "2026-11-05T19:00:00Z",
            "published": published,
            "discovery_queue": {"large": "not copied"},
        }

        snapshot = build_dispatch_state(state)
        self.assertEqual(snapshot["schemaVersion"], 1)
        self.assertEqual(list(snapshot["published"]), [f"dkp-{i}" for i in range(9, 3, -1)])
        self.assertEqual(snapshot["published"]["dkp-9"]["delivery_status"], {
            "telegram": "sent", "bale": "sent"
        })
        self.assertNotIn("title", snapshot["published"]["dkp-9"])
        self.assertNotIn("extra_large_blob", snapshot["published"]["dkp-9"])
        self.assertNotIn("discovery_queue", snapshot)
        self.assertLess(len(json.dumps(snapshot)), 5000)

    def test_export_writes_valid_snapshot_and_does_not_mutate_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "state.json"
            destination = root / "video_dispatch_state.json"
            source_state = {
                "youtube_next_upload_at": "2026-11-05T18:00:00Z",
                "published": {"dkp-1": {"ts": 10, "youtube_upload_status": "pending"}},
            }
            source.write_text(json.dumps(source_state), encoding="utf-8")
            result = export_dispatch_state(source, destination)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), result)
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), source_state)

    def test_malformed_source_does_not_overwrite_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "state.json"
            destination = root / "video_dispatch_state.json"
            source.write_text("{broken", encoding="utf-8")
            destination.write_text('{"schemaVersion":1}\n', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                export_dispatch_state(source, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"schemaVersion":1}\n')


if __name__ == "__main__":
    unittest.main()
