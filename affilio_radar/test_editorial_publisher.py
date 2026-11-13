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
    _record_success,
    _pending_product_video_exists,
    _format_message,
    queue_editorial_if_due,
)
from editorial_video import render_editorial_poster, render_editorial_video
import affilio_radar as radar
from publisher import (
    editorial_fifo_lock_entry,
    _record_product_channel_publication_for_editorial,
)
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

    def test_editorial_fifo_lock_activates_only_while_core_channel_targets_are_pending(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {
                    "content_id": "editorial:test",
                    "sequence_number": 4,
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "pending"},
                    },
                }
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertEqual(editorial_fifo_lock_entry(state)["sequence_number"], 4)

    def test_older_editorial_video_blocks_only_newer_product_video_sequences(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:guide": {
                    "sequence_number": 5,
                    "status": "partial",
                    "platforms": {
                        "youtube": {"status": "sent"},
                        "aparat": {"status": "pending"},
                        "filo": {"status": "not_connected"},
                    },
                }
            }
        }
        barrier = radar._oldest_pending_editorial_video_sequence(state)
        self.assertEqual(barrier, 5)
        self.assertIsNone(radar._oldest_pending_editorial_video_sequence(
            state, {"youtube"}
        ))
        self.assertFalse(radar._product_video_blocked_by_editorial_sequence(
            {"sequence_number": 3}, barrier
        ))
        self.assertTrue(radar._product_video_blocked_by_editorial_sequence(
            {"sequence_number": 8}, barrier
        ))
        # A legacy product record with no sequence is drained before the barrier.
        self.assertFalse(radar._product_video_blocked_by_editorial_sequence({}, barrier))

    def test_editorial_video_backlog_does_not_lock_product_channel_publisher(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {
                    "content_id": "editorial:test",
                    "sequence_number": 4,
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "skipped_limit"},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "retry"},
                        "filo": {"status": "pending"},
                    },
                }
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_product_publication_counter_counts_once_per_confirmed_delivery(self):
        state = {"product_channel_posts_since_editorial": 3}
        entry = {"content_id": "dkp-counter-test"}
        self.assertTrue(_record_product_channel_publication_for_editorial(
            state, entry, new_public_delivery=True
        ))
        self.assertEqual(state["product_channel_posts_since_editorial"], 4)
        self.assertTrue(entry["counted_for_editorial_cadence"])
        self.assertFalse(_record_product_channel_publication_for_editorial(
            state, entry, new_public_delivery=True
        ))
        self.assertEqual(state["product_channel_posts_since_editorial"], 4)
        self.assertFalse(_record_product_channel_publication_for_editorial(
            state, {}, new_public_delivery=False
        ))

    def test_editorial_gets_shared_monotonic_sequence(self):
        state = {
            "publication_sequence_counter": 12,
            "product_channel_posts_since_editorial": 4,
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertEqual(entry["sequence_number"], 13)
        self.assertEqual(entry["content_type"], "editorial")
        self.assertEqual(entry["payload"]["content_id"], "editorial:test-guide")
        self.assertEqual(state["publication_sequence_counter"], 13)

    def test_editorial_waits_until_four_confirmed_product_posts(self):
        state = {
            "product_channel_posts_since_editorial": 3,
            "last_channel_published_at": (NOW - timedelta(hours=2)).isoformat(),
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_queues_after_four_products_when_channel_slot_is_free(self):
        state = {
            "product_channel_posts_since_editorial": 4,
            "last_channel_published_at": (NOW - timedelta(minutes=30)).isoformat(),
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["content_type"], "editorial")
        self.assertEqual(entry["payload"]["editorial_id"], "test-guide")

    def test_editorial_respects_minimum_channel_spacing(self):
        state = {
            "product_channel_posts_since_editorial": 4,
            "last_channel_published_at": (NOW - timedelta(minutes=26)).isoformat(),
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_does_not_preempt_recent_channel_publication(self):
        state = {
            "product_channel_posts_since_editorial": 4,
            "last_channel_published_at": (NOW - timedelta(minutes=20)).isoformat(),
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_does_not_preempt_active_product_photo_fifo(self):
        state = {"content_delivery_queue": {
            "dkp-1": {"status": "partial", "selected_at": (NOW - timedelta(minutes=5)).isoformat()}
        }}
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_editorial_photo_slot_is_not_blocked_by_older_product_video(self):
        state = {
            "product_channel_posts_since_editorial": 4,
            "last_channel_published_at": (NOW - timedelta(minutes=30)).isoformat(),
            "published": {
                "dkp-1": {
                    "sequence_number": 2,
                    "youtube_upload_status": "retry",
                    "aparat_upload_status": "uploaded",
                    "filo_upload_status": "uploaded",
                }
            },
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["content_type"], "editorial")

    def test_editorial_video_waits_only_for_older_product_sequences(self):
        state = {"published": {
            "dkp-older": {"sequence_number": 2, "youtube_upload_status": "retry"},
            "dkp-newer": {"sequence_number": 9, "youtube_upload_status": "pending"},
        }}
        self.assertTrue(_pending_product_video_exists(state, before_sequence_number=5))
        self.assertFalse(_pending_product_video_exists(state, before_sequence_number=2))
        self.assertTrue(_pending_product_video_exists(state, before_sequence_number=12))

    def test_confirmed_editorial_channel_delivery_resets_product_counter(self):
        item = editorial_item()
        item.update({"content_id": "editorial:test-guide", "sequence_number": 5})
        state = {"product_channel_posts_since_editorial": 4}
        entry = {
            "content_id": "editorial:test-guide",
            "sequence_number": 5,
            "payload": item,
            "platforms": {"telegram": {"status": "sent"}},
        }
        with patch("editorial_publisher._save"):
            _record_success(state, entry, "telegram", {"message_id": "12345"}, NOW)
        self.assertEqual(state["product_channel_posts_since_editorial"], 0)
        self.assertEqual(state["last_editorial_channel_published_at"], NOW.isoformat())

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

    def test_unconfirmed_editorial_channel_error_does_not_retry_after_newer_fifo_slot(self):
        state = {}
        entry = {
            "content_id": "editorial:test-guide",
            "platforms": {"telegram": {"status": "pending", "attempts": 0}},
        }
        with (
            patch("editorial_publisher._destination_ready", return_value=(True, "")),
            patch("editorial_publisher._send_bot_message", side_effect=RuntimeError("bad request")),
            patch("editorial_publisher._save"),
        ):
            _handle_channel_destination(
                state, entry, "telegram", b"", "editorial test", NOW
            )
        self.assertEqual(entry["platforms"]["telegram"]["status"], "manual_review")
        self.assertIn(
            "editorial_delivery_not_confirmed_no_late_retry",
            entry["platforms"]["telegram"]["last_error"],
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
