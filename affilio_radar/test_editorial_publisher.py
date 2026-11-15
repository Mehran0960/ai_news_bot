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
                "editorial:test": {
                    "content_id": "editorial:test", "sequence_number": 4, "status": "partial",
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "pending"},
                    },
                }
            }
        }
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_never_locks_or_delays_a_product(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {
                    "content_id": "editorial:test", "sequence_number": 4, "status": "partial",
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "pending"},
                    },
                }
            },
            "content_delivery_queue": {
                "dkp-product": {"content_type": "product", "status": "queued",
                    "scheduled_at": (NOW + timedelta(seconds=1)).isoformat()}
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_lock_releases_after_core_photo_channels_are_terminal(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {
                    "content_id": "editorial:test",
                    "sequence_number": 4,
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "sent"},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "retry"},
                        "filo": {"status": "pending"},
                    },
                }
            }
        }
        with patch.dict(os.environ, {"OFFERCHIN_EDITORIAL_PUBLISH_ENABLED": "true"}, clear=True):
            self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_photo_retry_does_not_block_due_product_slot(self):
        state = {
            "editorial_delivery_queue": {
                "editorial:test": {
                    "content_id": "editorial:test",
                    "sequence_number": 4,
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "uploaded"},
                        "aparat": {"status": "uploaded"},
                        "filo": {"status": "uploaded"},
                    },
                }
            },
            "content_delivery_queue": {
                "dkp-product": {"content_type": "product", "status": "queued",
                    "scheduled_at": NOW.isoformat()}
            }
        }
        self.assertIsNone(editorial_fifo_lock_entry(state))

    def test_editorial_never_publishes_without_a_selected_product_slot(self):
        state = {
            "publication_sequence_counter": 12,
            "last_channel_published_at": (NOW - timedelta(days=10)).isoformat(),
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNone(entry)
        self.assertFalse(state.get("editorial_delivery_queue"))
        self.assertEqual(state["publication_sequence_counter"], 12)

    def test_editorial_fallback_obeys_shared_daily_channel_post_cap(self):
        state = {}
        with patch("editorial_publisher._pending_product_video_exists", return_value=False), \
             patch("editorial_publisher.radar.daily_channel_posts_count", return_value=72), \
             patch("editorial_publisher.radar.MAX_DAILY_CHANNEL_POSTS", 72):
            self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_editorial_midpoint_is_based_on_scan_slot_not_a_minute_floor(self):
        product_at = NOW + timedelta(hours=2)
        state = {
            "last_channel_published_at": (NOW - timedelta(minutes=20)).isoformat(),
            "content_delivery_queue": {
                "dkp-next": {
                    "content_type": "product",
                    "status": "queued",
                    "scheduled_at": product_at.isoformat(),
                    "payload": {"product_id": "dkp-next", "title": "گوشی هوشمند"},
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(
            datetime.fromisoformat(entry["scheduled_at"]),
            NOW + timedelta(minutes=50),
        )

    def test_editorial_does_not_preempt_a_due_product_slot(self):
        state = {
            "last_channel_published_at": (NOW - timedelta(hours=2)).isoformat(),
            "content_delivery_queue": {
                "dkp-1": {
                    "content_type": "product",
                    "status": "queued",
                    "selected_at": (NOW - timedelta(minutes=5)).isoformat(),
                    "scheduled_at": (NOW - timedelta(minutes=1)).isoformat(),
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

    def test_pending_product_video_does_not_hold_back_editorial_channel_post(self):
        state = {
            "last_channel_published_at": (NOW - timedelta(minutes=60)).isoformat(),
            "published": {
                "dkp-1": {
                    "video_generation_status": "pending",
                    "youtube_upload_status": "retry",
                    "aparat_upload_status": "uploaded",
                    "filo_upload_status": "uploaded",
                }
            },
            "content_delivery_queue": {
                "dkp-next": {
                    "content_type": "product",
                    "status": "queued",
                    "scheduled_at": (NOW + timedelta(hours=2)).isoformat(),
                    "payload": {"product_id": "dkp-next", "title": "گوشی هوشمند"},
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "queued")

    def test_related_editorial_is_scheduled_midway_before_its_product(self):
        product_at = NOW + timedelta(hours=2)
        product = {
            "product_id": "dkp-related",
            "title": "گوشی هوشمند",
            "image_url": "https://dkstatics-public.digikala.com/digikala-products/test.jpg",
            "offerchin_four_factor": {"generality_group": "mobile_productivity"},
        }
        state = {
            "last_channel_published_at": NOW.isoformat(),
            "content_delivery_queue": {
                "dkp-related": {
                    "content_type": "product",
                    "status": "queued",
                    "selected_at": NOW.isoformat(),
                    "scheduled_at": product_at.isoformat(),
                    "payload": product,
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        bank = [
            editorial_item("fashion-fit", "fit-and-size"),
            editorial_item("device-fit", "device-compatibility"),
        ]
        entry = queue_editorial_if_due(state, bank, now=NOW)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["related_product_id"], "dkp-related")
        self.assertEqual(entry["payload"]["editorial_id"], "device-fit")
        self.assertEqual(
            entry["payload"]["related_product_image_url"],
            "https://dkstatics-public.digikala.com/digikala-products/test.jpg",
        )
        self.assertEqual(
            datetime.fromisoformat(entry["scheduled_at"]),
            NOW + timedelta(hours=1),
        )

    def test_editorial_message_has_separated_attributed_clickable_sources_and_cta(self):
        message = _format_message(editorial_item(), html_mode=True, platform="telegram")
        self.assertIn("<b>منابع:</b>", message)
        self.assertIn("کمیسیون تجارت فدرال آمریکا (FTC)", message)
        self.assertIn("«منبع رسمی راهنمای خرید»:", message)
        self.assertIn('href="https://consumer.ftc.gov/articles/online-shopping"', message)
        self.assertIn('href="https://t.me/OfferChin">عضویت در کانال آفِرچین</a>', message)
        plain = _format_message(editorial_item(), html_mode=False, platform="bale")
        self.assertIn("منابع:\n• کمیسیون تجارت فدرال آمریکا (FTC)", plain)
        self.assertIn("\nhttps://consumer.ftc.gov/articles/online-shopping", plain)
        self.assertIn("https://ble.ir/OfferChin", plain)

    def test_known_ftc_sources_are_labeled_in_persian_with_clear_organization(self):
        item = editorial_item()
        item["sources"] = [{
            "source_id": "ftc-online-shopping",
            "title": "Online Shopping – Consumer Advice",
            "url": "https://consumer.ftc.gov/articles/online-shopping",
        }]
        message = _format_message(item, html_mode=True, platform="telegram")
        self.assertIn("کمیسیون تجارت فدرال آمریکا (FTC) — «راهنمای خرید اینترنتی»:", message)
        self.assertIn('href="https://consumer.ftc.gov/articles/online-shopping"', message)
        self.assertIn('href="https://t.me/OfferChin">عضویت در کانال آفِرچین</a>', message)

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

    def test_telegram_and_bale_editorial_photo_paths_use_send_photo(self):
        state = {}
        entry = {"content_id": "editorial:test-guide", "payload": {"editorial_id": "test-guide"}, "platforms": {}}
        with patch("editorial_publisher._destination_ready", return_value=(True, "")), \
             patch("editorial_publisher._send_bot_photo", return_value={"message_id": "12345"}) as sender, \
             patch("editorial_publisher._save"):
            _handle_channel_destination(
                state, entry, "telegram", b"png-bytes", "editorial test", NOW
            )
        sender.assert_called_once_with("telegram", b"png-bytes", "editorial test")
        self.assertEqual(entry["platforms"]["telegram"]["status"], "sent")

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
