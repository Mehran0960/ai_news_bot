import unittest
from unittest.mock import patch
import os
import re
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
    _video_description,
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
        "sources": [{"source_id": "s1", "title": "Online Shopping – Consumer Advice", "display_title_fa": "راهنمای خرید اینترنتی", "url": "https://consumer.ftc.gov/articles/online-shopping"}],
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

    def test_editorial_fifo_lock_never_blocks_product_delivery(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {"content_id": "editorial:test", "sequence_number": 4, "status": "partial"}
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_gets_shared_monotonic_sequence(self):
        state = {"publication_sequence_counter": 12}
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        expected_sequence = int(NOW.timestamp())
        self.assertEqual(entry["sequence_number"], expected_sequence)
        self.assertEqual(entry["content_type"], "editorial")
        self.assertEqual(entry["payload"]["content_id"], "editorial:test-guide")
        self.assertEqual(state["publication_sequence_counter"], expected_sequence)

    def test_editorial_does_not_preempt_recent_channel_publication(self):
        state = {"last_channel_published_at": (NOW - timedelta(minutes=20)).isoformat()}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_does_not_preempt_active_product_photo_fifo(self):
        state = {"content_delivery_queue": {
            "dkp-1": {"status": "partial", "selected_at": (NOW - timedelta(minutes=5)).isoformat()}
        }}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_channel_editorial_does_not_wait_for_product_video_backlog(self):
        state = {"published": {
            "dkp-1": {"youtube_upload_status": "retry", "aparat_upload_status": "uploaded", "filo_upload_status": "uploaded"}
        }}
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)

    def test_editorial_message_contains_sources(self):
        message = _format_message(editorial_item())
        self.assertIn("منابع:", message)
        self.assertIn("https://consumer.ftc.gov/articles/online-shopping", message)
        self.assertIn("راهنمای اینترنتی", message)
        self.assertIn("راهنمای کوتاه خرید آگاهانه", message)
        plain_copy = re.sub(r"https://\\S+", "", message)
        self.assertNotRegex(plain_copy, r"[A-Za-z]")


    def test_global_spacing_is_exactly_twenty_seven_minutes(self):
        state = {"last_channel_published_at": (NOW - timedelta(minutes=26)).isoformat()}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        state["last_channel_published_at"] = (NOW - timedelta(minutes=27)).isoformat()
        self.assertIsNotNone(queue_editorial_if_due(state, [editorial_item("exact-gap", "other-topic")], now=NOW))

    def test_due_product_preempts_even_an_active_editorial_retry(self):
        state = {
            "last_editorial_attempt_at": (NOW - timedelta(minutes=30)).isoformat(),
            "editorial_delivery_queue": {
                "editorial:older": {
                    "content_id": "editorial:older",
                    "sequence_number": 1,
                    "status": "partial",
                    "payload": editorial_item("older", "older-topic"),
                    "platforms": {name: {"status": "pending"} for name in PLATFORM_NAMES},
                }
            },
            "content_delivery_queue": {
                "dkp-due": {
                    "status": "queued",
                    "selected_at": (NOW - timedelta(minutes=5)).isoformat(),
                    "scheduled_at": NOW.isoformat(),
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                    },
                }
            },
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_future_reserved_product_leaves_current_slot_for_editorial(self):
        state = {
            "publication_mix_plan": {
                "cycle_id": "cycle-1",
                "scan_deadline_at": (NOW + timedelta(hours=5)).isoformat(),
                "product_capacity_deficit": 0,
            },
            "content_delivery_queue": {
                "dkp-future": {
                    "status": "queued",
                    "selected_at": NOW.isoformat(),
                    "scheduled_at": (NOW + timedelta(hours=1)).isoformat(),
                    "publication_plan_cycle_id": "cycle-1",
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                    },
                }
            },
        }
        self.assertIsNotNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_video_description_uses_persian_source_label_and_persian_footer(self):
        description = _video_description(editorial_item())
        plain_copy = re.sub(r"https://\\S+", "", description)
        self.assertIn("راهنمای اینترنتی", plain_copy)
        self.assertIn("برای نکته‌های بیشتر، آفِرچین را دنبال کنید", plain_copy)
        self.assertNotRegex(plain_copy, r"[A-Za-z]")

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
