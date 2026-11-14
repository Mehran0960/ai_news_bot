import unittest
from unittest.mock import patch
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from io import BytesIO
from PIL import Image

from editorial_publisher import (
    _finalize_if_terminal,
    _handle_channel_destination,
    _record_failure,
    _format_message,
    queue_editorial_if_due,
    _pending_product_video_exists,
)
from editorial_video import render_editorial_poster, render_editorial_video
import affilio_radar as radar
from publisher import editorial_fifo_lock_entry
from platform_registry import PLATFORM_NAMES

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def editorial_item(editorial_id="test-guide", topic="test-topic"):
    return {
        "editorial_id": editorial_id,
        "title": "راهنمای کوتاه خرید آگاهانه",
        "body": "پیش از انتخاب، نیاز، هزینه نهایی، مشخصات و شرایط بازگشت را بررسی کن.",
        "topic": topic,
        "sources": [{"source_id": "s1", "title": "منبع رسمی راهنمای خرید", "url": "https://consumer.ftc.gov/articles/online-shopping"}],
        "claims": [{"text": "هزینه‌های جانبی را بررسی کن", "source_ids": ["s1"]}],
        "reviewed_at": (NOW - timedelta(days=1)).isoformat(),
        "review_due_at": (NOW + timedelta(days=30)).isoformat(),
    }


class EditorialPublisherTests(unittest.TestCase):
    def test_editorial_fifo_lock_is_disabled_by_default(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {"content_id": "editorial:test", "sequence_number": 4, "status": "partial"}
            }
        }
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_fifo_lock_activates_only_with_explicit_flag(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {"content_id": "editorial:test", "sequence_number": 4, "status": "partial"}
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertEqual(editorial_fifo_lock_entry(state)["sequence_number"], 4)

    def test_editorial_sequence_matches_its_actual_publication_slot(self):
        state = {"publication_sequence_counter": 12}
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertEqual(entry["sequence_number"], int(NOW.timestamp()))
        self.assertEqual(entry["content_type"], "editorial")
        self.assertEqual(entry["payload"]["content_id"], "editorial:test-guide")
        self.assertEqual(state["publication_sequence_counter"], int(NOW.timestamp()))

    def test_editorial_does_not_preempt_recent_channel_publication(self):
        state = {"last_channel_published_at": (NOW - timedelta(minutes=20)).isoformat()}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_does_not_preempt_active_due_product_photo_slot(self):
        state = {"content_delivery_queue": {
            "dkp-1": {
                "status": "queued",
                "selected_at": (NOW - timedelta(minutes=3)).isoformat(),
                "scheduled_at": (NOW - timedelta(minutes=1)).isoformat(),
            }
        }}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_editorial_fills_a_gap_before_a_future_product_slot(self):
        state = {
            "publication_mix_plan": {"cycle_id": "clean-cycle-1"},
            "content_delivery_queue": {
            "dkp-1": {
                "status": "queued",
                "attempt_count": 0,
                "selected_at": (NOW - timedelta(hours=3)).isoformat(),
                "scheduled_at": (NOW + timedelta(hours=2, minutes=33)).isoformat(),
                "publication_plan_cycle_id": "clean-cycle-1",
            }
        }}
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["content_type"], "editorial")
        self.assertEqual(entry["scheduled_at"], NOW.isoformat())

    def test_editorial_channel_fills_gap_but_video_waits_for_older_product_video(self):
        state = {"published": {
            "dkp-1": {
                "sequence_number": int(NOW.timestamp()) - 600,
                "youtube_upload_status": "retry",
                "aparat_upload_status": "uploaded",
                "filo_upload_status": "uploaded",
            }
        }}
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertGreater(entry["sequence_number"], state["published"]["dkp-1"]["sequence_number"])
        self.assertTrue(
            _pending_product_video_exists(
                state,
                before_sequence=entry["sequence_number"],
            )
        )

    def test_editorial_message_contains_sources(self):
        message = _format_message(editorial_item())
        self.assertIn("منابع:", message)
        self.assertIn("https://consumer.ftc.gov/articles/online-shopping", message)
        self.assertIn("راهنمای کوتاه خرید آگاهانه", message)

    def test_video_fifo_uses_canonical_sequence_for_timestamp_ties(self):
        same_timestamp = NOW.timestamp()
        later_sequence = (same_timestamp, "dkp-a", {"sequence_number": 12})
        earlier_sequence = (same_timestamp, "dkp-z", {"sequence_number": 11})
        ordered = sorted(
            [later_sequence, earlier_sequence],
            key=radar._video_upload_candidate_sort_key,
        )
        self.assertEqual(ordered[0][1], "dkp-z")

    def test_editorial_video_renderer_creates_mp4_file(self):
        with tempfile.TemporaryDirectory(prefix="offerchin-editorial-test-") as directory:
            target = Path(directory) / "editorial-test.mp4"
            rendered = render_editorial_video(
                editorial_item(), target, duration_seconds=6, fps=12
            )
            self.assertEqual(rendered, target)
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 1024)

    def test_video_poster_is_valid_vertical_image(self):
        poster = render_editorial_poster(editorial_item())
        image = Image.open(BytesIO(poster))
        self.assertEqual(image.size, (720, 1280))
        self.assertEqual(image.format, "PNG")

    def test_api_acceptance_without_message_id_is_manual_review(self):
        state = {}
        entry = {"content_id": "editorial:test-guide", "platforms": {}}
        with patch("editorial_publisher._destination_ready", return_value=(True, "")), \
             patch("editorial_publisher._send_bot_message", return_value={"api_accepted": True}), \
             patch("editorial_publisher._save"):
            _handle_channel_destination(
                state, entry, "telegram", b"", "editorial test", NOW
            )
        target = entry["platforms"]["telegram"]
        self.assertEqual(target["status"], "manual_review")
        self.assertEqual(
            target["last_error"],
            "api_accepted_without_public_message_id_unverified",
        )

    def test_network_timeout_is_manual_review_not_blind_retry(self):
        state = {"status": "sending", "attempts": 1}
        entry = {"platforms": {"youtube": state}}
        import requests
        _record_failure(entry, "youtube", requests.exceptions.Timeout("timed out"), NOW)
        self.assertEqual(state["status"], "manual_review")

    def test_adapter_wrapped_network_failure_is_manual_review(self):
        state = {"status": "sending", "attempts": 1}
        entry = {"platforms": {"rubika": state}}
        _record_failure(entry, "rubika", RuntimeError("Rubika sendFile: network failure"), NOW)
        self.assertEqual(state["status"], "manual_review")

    def test_queue_finalizes_only_when_every_destination_is_terminal(self):
        entry = {
            "content_id": "editorial:test-guide",
            "sequence_number": 2,
            "platforms": {name: {"status": "not_connected"} for name in PLATFORM_NAMES},
        }
        state = {"editorial_delivery_queue": {entry["content_id"]: entry}}
        self.assertTrue(_finalize_if_terminal(state, entry, NOW))
        self.assertNotIn(entry["content_id"], state["editorial_delivery_queue"])
        self.assertEqual(state["editorial_delivery_attempts"][-1]["status"], "failed")

    def test_pending_platform_prevents_finalization(self):
        entry = {
            "content_id": "editorial:test-guide",
            "sequence_number": 2,
            "platforms": {name: {"status": "not_connected"} for name in PLATFORM_NAMES},
        }
        entry["platforms"]["youtube"]["status"] = "pending"
        state = {"editorial_delivery_queue": {entry["content_id"]: entry}}
        self.assertFalse(_finalize_if_terminal(state, entry, NOW))
        self.assertIn(entry["content_id"], state["editorial_delivery_queue"])


if __name__ == "__main__":
    unittest.main()
