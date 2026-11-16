import unittest
import json
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
    _send_bot_photo,
    _video_description,
    _load_bank,
    _cancel_stale_unapproved_editorials,
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
        "sources": [{"source_id": "s1", "title": "راهنمای دیجی‌کالا مگ درباره خرید", "url": "https://www.digikala.com/mag/digikala-delivery-time/"}],
        "claims": [{"text": "هزینه‌های جانبی را بررسی کن", "source_ids": ["s1"]}],
        "reviewed_at": (NOW - timedelta(days=1)).isoformat(),
        "review_due_at": (NOW + timedelta(days=30)).isoformat(),
    }


class EditorialPublisherTests(unittest.TestCase):
    def test_load_bank_merges_manually_approved_source_items(self):
        base = editorial_item(editorial_id="base-guide", topic="purchase-planning")
        approved = editorial_item(editorial_id="digikala-delivery", topic="delivery")
        approved["priority"] = "high"
        approved["sources"] = [{
            "source_id": "digikala-mag-delivery",
            "publisher": "دیجی‌کالا مگ",
            "title": "راهنمای زمان تحویل",
            "url": "https://www.digikala.com/mag/digikala-delivery-time/",
        }]
        approved["claims"] = [{
            "text": "بازه تحویل هر سفارش را در صفحه سفارش بررسی کن",
            "source_ids": ["digikala-mag-delivery"],
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bank_path = root / "editorial_bank.json"
            approved_path = root / "editorial_approved_items.json"
            bank_path.write_text(json.dumps([base], ensure_ascii=False), encoding="utf-8")
            approved_path.write_text(json.dumps([approved], ensure_ascii=False), encoding="utf-8")
            with patch("editorial_publisher.EDITORIAL_BANK", bank_path), patch(
                "editorial_publisher.EDITORIAL_APPROVED_ITEMS", approved_path
            ):
                loaded = _load_bank()

        self.assertEqual({item["editorial_id"] for item in loaded}, {"base-guide", "digikala-delivery"})
        chosen = __import__("editorial_content").select_editorial_fallback(
            loaded, {}, now=NOW, related_product={}
        )
        self.assertEqual(chosen["editorial_id"], "digikala-delivery")
        self.assertEqual(chosen["sources"][0]["publisher"], "دیجی‌کالا مگ")

    def test_legacy_foreign_source_queue_item_is_cancelled_before_delivery(self):
        approved = editorial_item()
        legacy = editorial_item()
        legacy["sources"] = [{
            "source_id": "old-ftc-source",
            "title": "راهنمای عمومی خارجی",
            "url": "https://consumer.ftc.gov/articles/online-shopping",
        }]
        entry = {
            "content_id": "editorial:test-guide",
            "content_type": "editorial",
            "status": "queued",
            "payload": legacy,
            "platforms": {name: {"status": "pending"} for name in PLATFORM_NAMES},
        }
        state = {"editorial_delivery_queue": {entry["content_id"]: entry}}

        cancelled = _cancel_stale_unapproved_editorials(state, [approved], now=NOW)

        self.assertEqual(cancelled, 1)
        self.assertEqual(entry["status"], "cancelled")
        self.assertEqual(
            entry["last_detail"],
            "editorial_payload_not_in_current_reviewed_local_source_bank",
        )
        self.assertIn(entry["content_id"], state["editorial_delivery_queue"])

    def test_current_local_queue_item_is_preserved(self):
        approved = editorial_item()
        entry = {
            "content_id": "editorial:test-guide",
            "content_type": "editorial",
            "status": "queued",
            "payload": dict(approved),
            "platforms": {name: {"status": "pending"} for name in PLATFORM_NAMES},
        }
        state = {"editorial_delivery_queue": {entry["content_id"]: entry}}
        self.assertEqual(_cancel_stale_unapproved_editorials(state, [approved], now=NOW), 0)
        self.assertEqual(entry["status"], "queued")

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

    def test_short_but_feasible_gap_moves_editorial_to_latest_safe_dispatch_start(self):
        product_at = NOW + timedelta(minutes=2)
        state = {
            "last_channel_published_at": NOW.isoformat(),
            "content_delivery_queue": {
                "dkp-short-gap": {
                    "content_type": "product",
                    "status": "queued",
                    "scheduled_at": product_at.isoformat(),
                    "payload": {"product_id": "dkp-short-gap", "title": "گوشی موبایل"},
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        with patch.dict(os.environ, {
            "OFFERCHIN_EDITORIAL_DISPATCH_POLL_SECONDS": "60",
            "OFFERCHIN_EDITORIAL_DEFAULT_DELIVERY_SECONDS": "30",
        }, clear=True):
            entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)

        self.assertIsNotNone(entry)
        self.assertEqual(
            datetime.fromisoformat(entry["scheduled_at"]),
            NOW + timedelta(seconds=30),
        )
        self.assertEqual(
            datetime.fromisoformat(entry["window_closes_at"]),
            NOW + timedelta(seconds=90),
        )
        self.assertEqual(entry["dispatch_runway_seconds"], 90)

    def test_missed_midpoint_starts_now_when_the_remaining_delivery_runway_fits(self):
        product_at = NOW + timedelta(minutes=2)
        state = {
            "last_channel_published_at": (NOW - timedelta(minutes=2)).isoformat(),
            "content_delivery_queue": {
                "dkp-late-wakeup": {
                    "content_type": "product",
                    "status": "queued",
                    "scheduled_at": product_at.isoformat(),
                    "payload": {"product_id": "dkp-late-wakeup", "title": "گوشی موبایل"},
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        with patch.dict(os.environ, {
            "OFFERCHIN_EDITORIAL_DISPATCH_POLL_SECONDS": "60",
            "OFFERCHIN_EDITORIAL_DEFAULT_DELIVERY_SECONDS": "30",
        }, clear=True):
            entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)

        self.assertIsNotNone(entry)
        self.assertEqual(datetime.fromisoformat(entry["scheduled_at"]), NOW)
        self.assertEqual(
            datetime.fromisoformat(entry["window_closes_at"]),
            NOW + timedelta(seconds=90),
        )
        self.assertEqual(entry["delivery_runway_seconds"], 30)

    def test_editorial_is_skipped_when_real_send_runway_does_not_fit(self):
        product_at = NOW + timedelta(seconds=75)
        state = {
            "last_channel_published_at": NOW.isoformat(),
            "content_delivery_queue": {
                "dkp-no-runway": {
                    "content_type": "product",
                    "status": "queued",
                    "scheduled_at": product_at.isoformat(),
                    "payload": {"product_id": "dkp-no-runway", "title": "گوشی موبایل"},
                    "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
                }
            },
        }
        with patch.dict(os.environ, {
            "OFFERCHIN_EDITORIAL_DISPATCH_POLL_SECONDS": "60",
            "OFFERCHIN_EDITORIAL_DEFAULT_DELIVERY_SECONDS": "30",
        }, clear=True):
            entry = queue_editorial_if_due(state, [editorial_item()], now=NOW)

        self.assertIsNone(entry)
        self.assertFalse(state.get("editorial_delivery_queue"))

    def test_active_editorial_is_cancelled_when_only_delivery_time_remains(self):
        editorial = {
            "content_id": "editorial:window-closed",
            "sequence_number": 31,
            "status": "queued",
            "scheduled_at": (NOW - timedelta(seconds=5)).isoformat(),
            "next_attempt_at": (NOW - timedelta(seconds=5)).isoformat(),
            "related_product_id": "dkp-product-soon",
            "payload": editorial_item(),
            "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
        }
        product = {
            "content_type": "product",
            "status": "queued",
            "scheduled_at": (NOW + timedelta(seconds=20)).isoformat(),
            "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
        }
        state = {
            "editorial_delivery_queue": {editorial["content_id"]: editorial},
            "content_delivery_queue": {"dkp-product-soon": product},
        }
        with patch.dict(os.environ, {
            "OFFERCHIN_EDITORIAL_DISPATCH_POLL_SECONDS": "60",
            "OFFERCHIN_EDITORIAL_DEFAULT_DELIVERY_SECONDS": "30",
        }, clear=True):
            self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))

        self.assertNotIn(editorial["content_id"], state["editorial_delivery_queue"])
        self.assertEqual(editorial["status"], "cancelled")
        self.assertEqual(editorial["last_detail"], "editorial_dispatch_window_closed_before_product")

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

    def test_active_editorial_is_cancelled_after_related_product_was_publicly_sent(self):
        editorial = {
            "content_id": "editorial:late-midpoint",
            "sequence_number": 20,
            "status": "queued",
            "scheduled_at": (NOW - timedelta(minutes=1)).isoformat(),
            "next_attempt_at": (NOW - timedelta(minutes=1)).isoformat(),
            "related_product_id": "dkp-already-posted",
            "payload": editorial_item(),
            "platforms": {},
        }
        product = {
            "content_type": "product",
            "status": "partial",
            "scheduled_at": (NOW - timedelta(seconds=30)).isoformat(),
            "platforms": {
                "telegram": {"status": "sent"},
                "bale": {"status": "sent"},
                "rubika": {"status": "pending"},
            },
        }
        state = {
            "editorial_delivery_queue": {editorial["content_id"]: editorial},
            "content_delivery_queue": {"dkp-already-posted": product},
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertNotIn(editorial["content_id"], state["editorial_delivery_queue"])
        self.assertEqual(editorial["status"], "cancelled")

    def test_active_editorial_is_cancelled_when_related_product_slot_becomes_due(self):
        editorial = {
            "content_id": "editorial:expired-midpoint",
            "sequence_number": 21,
            "status": "partial",
            "scheduled_at": (NOW - timedelta(minutes=2)).isoformat(),
            "next_attempt_at": (NOW - timedelta(minutes=2)).isoformat(),
            "related_product_id": "dkp-due-now",
            "payload": editorial_item(),
            "platforms": {"telegram": {"status": "sent", "attempts": 1}},
        }
        product = {
            "content_type": "product",
            "status": "queued",
            "selected_at": (NOW - timedelta(minutes=5)).isoformat(),
            "scheduled_at": (NOW - timedelta(seconds=5)).isoformat(),
            "platforms": {
                "telegram": {"status": "pending"},
                "bale": {"status": "pending"},
            },
        }
        state = {
            "editorial_delivery_queue": {editorial["content_id"]: editorial},
            "content_delivery_queue": {"dkp-due-now": product},
        }
        self.assertIsNone(queue_editorial_if_due(state, [editorial_item()], now=NOW))
        self.assertNotIn(editorial["content_id"], state["editorial_delivery_queue"])
        self.assertEqual(editorial["status"], "cancelled")
        self.assertEqual(editorial["last_detail"], "editorial_midpoint_passed_related_product_due")

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
        self.assertNotIn("related_product_image_url", entry["payload"])
        self.assertNotIn("related_product_title", entry["payload"])
        self.assertEqual(
            datetime.fromisoformat(entry["scheduled_at"]),
            NOW + timedelta(hours=1),
        )

    def test_editorial_message_shows_source_and_related_affiliate_cta_without_self_membership(self):
        item = editorial_item()
        item["topic"] = "device-compatibility"
        item["related_product_affiliate_url"] = radar.build_affilio_tracking_link(
            "https://www.digikala.com/product/dkp-123/"
        )
        message = _format_message(item, html_mode=True, platform="telegram")
        self.assertIn("دیجی‌کالا مگ", message)
        self.assertIn('href="https://www.digikala.com/mag/digikala-delivery-time/"', message)
        self.assertIn("🔌", message)
        self.assertIn("💡", message)
        self.assertIn("پیوند همکاری در فروش", message)
        self.assertIn("https://aflo.ir/QekEYTRg?p=", message)
        self.assertNotIn("راهنمای کاربردی آفِرچین", message)
        self.assertNotIn("<b>آفِرچین</b>", message)
        self.assertNotIn("t.me/OfferChin", message)
        self.assertNotIn("عضویت در کانال", message)

        bale = _format_message(item, html_mode=True, platform="bale")
        self.assertIn("دکمهٔ خرید پایین پست", bale)
        self.assertNotIn("ble.ir/OfferChin", bale)
        self.assertNotIn("عضویت در کانال", bale)

        plain = _format_message(item, html_mode=False, platform="rubika")
        self.assertIn("www.digikala.com/mag/digikala-delivery-time/", plain)
        self.assertIn("https://aflo.ir/QekEYTRg?p=", plain)
        self.assertNotIn("rubika.ir/offerchin", plain)

    def test_editorial_without_verified_affiliate_url_has_no_commercial_cta(self):
        item = editorial_item()
        item["related_product_affiliate_url"] = "https://www.digikala.com/best-selling/"
        message = _format_message(item, html_mode=True, platform="telegram")
        self.assertNotIn("پیوند همکاری در فروش", message)
        self.assertNotIn("aflo.ir", message)

    def test_bale_editorial_photo_has_a_real_related_product_affiliate_button(self):
        item = editorial_item()
        item["related_product_affiliate_url"] = radar.build_affilio_tracking_link(
            "https://www.digikala.com/product/dkp-123/"
        )
        caption = _format_message(item, html_mode=True, platform="bale")
        with patch("editorial_publisher.radar.BALE_BOT_TOKEN", "test-token"), \
             patch("editorial_publisher.radar.BALE_CHANNEL_ID", "@OfferChin"), \
             patch("editorial_publisher.requests.post") as post:
            post.return_value.json.return_value = {
                "ok": True, "result": {"message_id": 77}
            }
            receipt = _send_bot_photo("bale", b"png-bytes", caption, item=item)

        self.assertEqual(receipt, {"message_id": "77"})
        payload = post.call_args.kwargs["data"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("consumer.ftc.gov/articles/online-shopping", payload["caption"])
        markup = json.loads(payload["reply_markup"])
        button = markup["inline_keyboard"][0][0]
        self.assertEqual(button["text"], "🛒 مشاهدهٔ پیشنهاد مرتبط")
        self.assertEqual(
            button["url"],
            "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-123%2F",
        )

    def test_video_description_has_sources_and_only_related_affiliate_link(self):
        item = editorial_item()
        item["related_product_affiliate_url"] = radar.build_affilio_tracking_link(
            "https://www.digikala.com/product/dkp-123/"
        )
        description = _video_description(item)
        self.assertIn("FTC", description)
        self.assertIn("consumer.ftc.gov/articles/online-shopping", description)
        self.assertIn("پیوند همکاری در فروش", description)
        self.assertIn("https://aflo.ir/QekEYTRg?p=", description)
        self.assertNotIn("t.me/OfferChin", description)
        self.assertNotIn("ble.ir/OfferChin", description)

    def test_editorial_body_sentences_and_list_items_render_as_separate_paragraphs(self):
        item = editorial_item()
        item["body"] = "جملهٔ اول کامل است. جملهٔ دوم پرسشی است؟\nنکتهٔ سوم هم جداست."
        html_message = _format_message(item, html_mode=True, platform="telegram")
        self.assertIn(
            "💡 جملهٔ اول کامل است.\n📌 جملهٔ دوم پرسشی است؟\n✅ نکتهٔ سوم هم جداست.",
            html_message,
        )
        self.assertIn('href="https://consumer.ftc.gov/articles/online-shopping"', html_message)

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

    def test_video_poster_is_topic_led_and_ignores_related_product_photos(self):
        item = editorial_item()
        item["related_product_image_url"] = "https://dkstatics-public.digikala.com/digikala-products/product.jpg"
        with patch("editorial_video._load_related_product_image",
                   side_effect=AssertionError("product photography must not be requested"),
                   create=True):
            poster = render_editorial_poster(item)
        image = Image.open(BytesIO(poster))
        self.assertEqual(image.size, (720, 1280))
        self.assertEqual(image.format, "PNG")
        self.assertNotEqual(image.getpixel((360, 310)), (14, 25, 43))

    def test_telegram_and_bale_editorial_photo_paths_use_send_photo(self):
        state = {}
        entry = {
            "content_id": "editorial:test-guide",
            "payload": {
                "content_id": "editorial:test-guide",
                "editorial_id": "test-guide",
                "topic": "test-topic",
            },
            "platforms": {},
        }
        with patch("editorial_publisher._destination_ready", return_value=(True, "")), \
             patch("editorial_publisher._send_bot_photo", return_value={"message_id": "12345"}) as sender, \
             patch("editorial_publisher._save"):
            _handle_channel_destination(
                state, entry, "telegram", b"png-bytes", "editorial test", NOW
            )
        sender.assert_called_once_with(
            "telegram", b"png-bytes", "editorial test", item=entry["payload"]
        )
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
