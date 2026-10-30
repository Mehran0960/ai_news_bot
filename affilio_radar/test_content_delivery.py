import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from content_delivery import (
    due_content, due_unpublished_selection, enqueue_selected_content,
    finish_queue_item, get_last_channel_published_at, has_fresh_unpublished_selection,
    refresh_unpublished_selections, selection_cadence_anchor,
)
from platform_registry import PLATFORM_NAMES
from publisher import publish_due_queue, _fresh_selected_item


class ContentDeliveryQueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    def item(self, product_id="dkp-123", price=100_000, demand=50, deadline=None):
        return {
            "product_id": product_id,
            "title": f"Test product {product_id}",
            "product_url": f"https://www.digikala.com/product/{product_id}/",
            "affiliate_url": f"https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2F{product_id}%2F",
            "current_price": price,
            "original_price": 200_000,
            "discount_percent": 50,
            "demand_score": demand,
            "deal_expires_at": deadline.isoformat() if deadline else "",
        }

    def test_enqueue_persists_platform_neutral_payload_without_delivery(self):
        state = {}
        summary = enqueue_selected_content(
            state, [self.item()], now=self.now, interval_seconds=1200, max_items=1
        )
        self.assertEqual(summary["added"], 1)
        entry = state["content_delivery_queue"]["dkp-123"]
        self.assertEqual(entry["status"], "queued")
        self.assertIn("payload", entry)
        self.assertEqual(
            set(entry["platforms"]),
            set(PLATFORM_NAMES),
        )
        self.assertEqual(entry["platforms"]["telegram"]["status"], "pending")

    def test_legacy_media_retry_clock_is_recovered_from_actual_channel_send_times(self):
        actual_channel_send = self.now - timedelta(minutes=25)
        latest_channel_send = actual_channel_send + timedelta(seconds=1)
        state = {
            # Older partial-media retries incorrectly moved this into the future.
            "last_published_at": (self.now + timedelta(minutes=15)).isoformat(),
            "content_delivery_queue": {
                "dkp-partial": {
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent", "updated_at": actual_channel_send.isoformat()},
                        "bale": {"status": "sent", "updated_at": latest_channel_send.isoformat()},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "pending"},
                    },
                }
            },
        }

        anchor = get_last_channel_published_at(state)
        self.assertEqual(anchor, latest_channel_send)
        self.assertEqual(state["last_channel_published_at"], latest_channel_send.isoformat())
        self.assertEqual(state["last_published_at"], latest_channel_send.isoformat())

        # The stale future retry time must not delay a fresh queue hand-off.
        summary = enqueue_selected_content(
            state, [self.item("dkp-fresh")], now=self.now,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=0,
        )
        self.assertEqual(summary["added"], 1)
        self.assertEqual(
            datetime.fromisoformat(state["content_delivery_queue"]["dkp-fresh"]["scheduled_at"]),
            self.now,
        )

    def test_partial_media_retry_does_not_advance_channel_publication_clock(self):
        from unittest.mock import patch
        import publisher

        actual_channel_send = self.now - timedelta(minutes=30)
        latest_channel_send = actual_channel_send + timedelta(seconds=1)
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-video-pending")], now=actual_channel_send,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=0,
        )
        entry = state["content_delivery_queue"]["dkp-video-pending"]
        entry["status"] = "partial"
        entry["next_attempt_at"] = (self.now - timedelta(minutes=1)).isoformat()
        entry["platforms"]["telegram"].update(
            status="sent", updated_at=actual_channel_send.isoformat(), attempts=1
        )
        entry["platforms"]["bale"].update(
            status="sent", updated_at=latest_channel_send.isoformat(), attempts=1
        )
        entry["platforms"]["youtube"]["status"] = "pending"
        entry["platforms"]["aparat"]["status"] = "pending"
        state["last_published_at"] = latest_channel_send.isoformat()
        state["last_channel_published_at"] = latest_channel_send.isoformat()

        with (
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher._save"),
            patch("publisher._now", return_value=self.now),
            patch("publisher._fresh_selected_item", return_value=(self.item("dkp-video-pending"), "")),
            patch("publisher.radar._fetch_image", return_value=b"image"),
            patch("publisher._process_photo_destination") as send_photo,
            patch("publisher._process_video_destinations"),
        ):
            publisher.publish_due_queue()

        self.assertEqual(state["last_published_at"], latest_channel_send.isoformat())
        self.assertEqual(state["last_channel_published_at"], latest_channel_send.isoformat())
        self.assertEqual(send_photo.call_count, 2)
        # Because both channels were already sent, this retry must not reset either clock.

    def test_publisher_rejects_legacy_queued_supplement_before_any_delivery(self):
        entry = {
            "product_id": "dkp-8478740",
            "payload": {
                "product_id": "dkp-8478740",
                "product_url": "https://www.digikala.com/product/dkp-8478740/",
                "current_price": 79000,
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-8478740%2F",
            },
        }
        with patch("publisher.radar.fetch_product_record", return_value={
            "title": "شربت ال آرژنین پلاس فیشر کیندر -200 میلی لیتر",
            "image_url": "https://example.invalid/product.jpg",
        }):
            fresh, reason = _fresh_selected_item(entry, self.now)

        self.assertIsNone(fresh)
        self.assertEqual(reason, "live_product_prohibited_title")

    def test_publisher_honors_selected_fallback_floor_and_keeps_legacy_50_percent_default(self):
        from unittest.mock import patch

        product_id = "dkp-95045"
        product_url = f"https://www.digikala.com/product/{product_id}/"
        affiliate_url = (
            "https://aflo.ir/QekEYTRg?p="
            "https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95045%2F"
        )
        payload = {
            "product_id": product_id,
            "product_url": product_url,
            "title": "شارژر سریع دیواری مدل تست",
            "current_price": 550_000,
            "original_price": 1_000_000,
            "discount_percent": 45,
            "savings_toman": 450_000,
            "affiliate_url": affiliate_url,
            "selection_discount_floor": 45,
            "deal_expires_at": "",
        }
        fresh_record = {
            "title": "شارژر سریع دیواری مدل تست",
            "image_url": "https://example.com/product.webp",
            "current_price": 550_000,
            "original_price": 1_000_000,
            "discount_percent": 45,
            "savings_toman": 450_000,
            "availability": "in_stock",
            "deal_expires_at": "",
        }

        def discount_gate(record, minimum_discount_percent=None):
            floor = 50 if minimum_discount_percent is None else minimum_discount_percent
            return (
                int(record.get("discount_percent") or 0) >= floor
                and int(record.get("savings_toman") or 0) >= 100_000
            )

        patches = (
            patch("publisher.radar.fetch_product_record", return_value=dict(fresh_record)),
            patch("publisher.radar.is_prohibited_product_title", return_value=False),
            patch("publisher.radar.is_publishable_product_title", return_value=True),
            patch("publisher.radar._is_valid_affilio_tracking_url", return_value=True),
            patch("publisher.radar.score_product", side_effect=lambda item: item),
            patch(
                "publisher.radar.verify_live_page_price",
                return_value={"ok": True, "page_price": 550_000},
            ),
            patch("publisher.radar.is_discount_publish_eligible", side_effect=discount_gate),
            patch("publisher.radar.is_market_value_publish_eligible", return_value=True),
            patch("publisher.radar.has_publishable_expiry_or_open_offer", return_value=True),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as discount_check, patches[7], patches[8]:
            entry = {"product_id": product_id, "payload": dict(payload)}
            fresh, reason = _fresh_selected_item(entry, self.now)
            self.assertIsNotNone(fresh)
            self.assertEqual(reason, "")
            discount_check.assert_called_once()
            self.assertEqual(
                discount_check.call_args.kwargs["minimum_discount_percent"], 45
            )

            # Old queued items have no selected floor: keep their original 50% rule.
            discount_check.reset_mock()
            legacy_payload = dict(payload)
            legacy_payload.pop("selection_discount_floor")
            legacy_entry = {"product_id": product_id, "payload": legacy_payload}
            fresh, reason = _fresh_selected_item(legacy_entry, self.now)
            self.assertIsNone(fresh)
            self.assertEqual(reason, "live_discount_no_longer_eligible")
            discount_check.assert_called_once()
            self.assertIsNone(
                discount_check.call_args.kwargs["minimum_discount_percent"]
            )

    def test_publisher_rejects_invalid_selected_discount_floor(self):
        entry = {
            "product_id": "dkp-95045",
            "payload": {
                "product_id": "dkp-95045",
                "product_url": "https://www.digikala.com/product/dkp-95045/",
                "selection_discount_floor": 44,
            },
        }
        fresh, reason = _fresh_selected_item(entry, self.now)
        self.assertIsNone(fresh)
        self.assertEqual(reason, "invalid_selection_discount_floor")

    def test_only_a_fresh_active_unpublished_selection_reserves_next_channel_slot(self):
        last_channel_send = self.now - timedelta(minutes=30)
        failed_selection = self.now - timedelta(minutes=3)
        state = {
            "content_delivery_queue": {
                "dkp-failed-image": {
                    "status": "queued",
                    "selected_at": failed_selection.isoformat(),
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "pending"},
                    },
                }
            }
        }

        self.assertTrue(has_fresh_unpublished_selection(state, now=self.now, stale_after_minutes=8))
        self.assertEqual(
            selection_cadence_anchor(
                failed_selection, last_channel_send,
                has_fresh_unpublished_selection=True,
            ),
            failed_selection,
        )

        # A previously failed selection may already have been marked stale by an older
        # workflow revision. The next run still sees no fresh active selection and must
        # use the real channel clock rather than the stale last-selection timestamp.
        state["content_delivery_queue"].pop("dkp-failed-image")
        state["content_delivery_history"] = [{
            "product_id": "dkp-failed-image",
            "status": "stale_selection",
            "selected_at": failed_selection.isoformat(),
            "platforms": {
                "telegram": {"status": "pending"},
                "bale": {"status": "pending"},
            },
        }]
        self.assertFalse(has_fresh_unpublished_selection(state, now=self.now, stale_after_minutes=8))
        self.assertEqual(
            selection_cadence_anchor(
                failed_selection, last_channel_send,
                has_fresh_unpublished_selection=False,
            ),
            last_channel_send,
        )

    def test_queue_enforces_spacing_and_dedupes_active_content(self):
        state = {}
        items = [self.item("dkp-1"), self.item("dkp-2")]
        enqueue_selected_content(state, items, now=self.now, interval_seconds=1200, max_items=2)
        queue = state["content_delivery_queue"]
        self.assertEqual(
            datetime.fromisoformat(queue["dkp-2"]["scheduled_at"])
            - datetime.fromisoformat(queue["dkp-1"]["scheduled_at"]),
            timedelta(seconds=1200),
        )
        again = enqueue_selected_content(state, items, now=self.now, interval_seconds=1200, max_items=2)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["queue_size"], 2)

    def test_enqueue_rejects_incomplete_product_title(self):
        state = {}
        item = self.item()
        item["title"] = "هندزفری بلوتوثی مدل"

        summary = enqueue_selected_content(state, [item], now=self.now)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(state["content_delivery_queue"], {})

    def test_new_selection_does_not_stack_behind_partial_retry(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-old-partial")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        old = state["content_delivery_queue"]["dkp-old-partial"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["bale"]["status"] = "failed"
        next_slot = self.now + timedelta(minutes=20)
        old["scheduled_at"] = next_slot.isoformat()
        old["next_attempt_at"] = next_slot.isoformat()
        state["last_published_at"] = self.now.isoformat()

        summary = enqueue_selected_content(
            state, [self.item("dkp-fresh")], now=self.now + timedelta(minutes=5),
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(summary["added"], 1)
        self.assertEqual(
            datetime.fromisoformat(state["content_delivery_queue"]["dkp-fresh"]["scheduled_at"]),
            next_slot,
        )

    def test_retry_queue_is_bounded_and_prefers_fresh_selections(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-1")], now=self.now,
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        enqueue_selected_content(
            state, [self.item("dkp-2")], now=self.now + timedelta(minutes=1),
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        result = enqueue_selected_content(
            state, [self.item("dkp-3")], now=self.now + timedelta(minutes=2),
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        self.assertEqual(result["queue_size"], 2)
        self.assertEqual(set(state["content_delivery_queue"]), {"dkp-2", "dkp-3"})
        self.assertEqual(state["content_delivery_history"][0]["product_id"], "dkp-1")
        self.assertEqual(state["content_delivery_history"][0]["status"], "cancelled")
        self.assertIn("bounded_retry_queue_eviction", state["content_delivery_history"][0]["last_detail"])

    def test_queue_rejects_past_minimum_runway(self):
        state = {}
        deadline = self.now + timedelta(minutes=45)
        result = enqueue_selected_content(
            state, [self.item(deadline=deadline)], now=self.now,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=60,
        )
        self.assertEqual(result["added"], 0)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])

    def test_active_publication_cannot_be_queued_again(self):
        state = {
            "published": {
                "dkp-123": {
                    "telegram_message_id": 55,
                    "expiry_status": "tracked",
                }
            }
        }
        result = enqueue_selected_content(state, [self.item()], now=self.now)
        self.assertEqual(result["added"], 0)

    def test_due_items_obey_schedule_and_retry_time(self):
        state = {}
        enqueue_selected_content(state, [self.item("dkp-1"), self.item("dkp-2")],
                                 now=self.now, interval_seconds=1200, max_items=2)
        due_now = due_content(state, now=self.now, limit=5)
        self.assertEqual([pid for pid, _entry in due_now], ["dkp-1"])
        later = due_content(state, now=self.now + timedelta(minutes=21), limit=5)
        self.assertEqual({pid for pid, _entry in later}, {"dkp-1", "dkp-2"})


    def test_future_selection_is_replaced_by_live_scan(self):
        state = {"last_published_at": self.now.isoformat()}
        enqueue_selected_content(
            state, [self.item("dkp-old")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        old = state["content_delivery_queue"]["dkp-old"]
        self.assertGreater(datetime.fromisoformat(old["scheduled_at"]), self.now)

        replaced = refresh_unpublished_selections(state, now=self.now)
        self.assertEqual(replaced, 1)
        self.assertNotIn("dkp-old", state["content_delivery_queue"])
        self.assertEqual(
            state["content_delivery_history"][-1]["status"], "stale_selection"
        )

    def test_partial_delivery_does_not_prevent_fresh_content_selection(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-video-pending")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        old = state["content_delivery_queue"]["dkp-video-pending"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["youtube"]["status"] = "pending"
        state["last_published_at"] = self.now.isoformat()

        next_time = self.now + timedelta(minutes=20)
        summary = enqueue_selected_content(
            state, [self.item("dkp-new")], now=next_time,
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(summary["added"], 1)
        self.assertEqual(
            datetime.fromisoformat(
                state["content_delivery_queue"]["dkp-new"]["scheduled_at"]
            ),
            next_time,
        )
        self.assertIn("dkp-video-pending", state["content_delivery_queue"])

    def test_due_unpublished_selection_is_visible_until_a_destination_succeeds(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-pending")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(
            due_unpublished_selection(state, now=self.now), "dkp-pending"
        )
        state["content_delivery_queue"]["dkp-pending"]["platforms"]["telegram"]["status"] = "sent"
        self.assertIsNone(due_unpublished_selection(state, now=self.now))


    def test_fresh_unpublished_content_outranks_old_partial_delivery(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-old-partial", demand=90)],
            now=self.now - timedelta(minutes=30), interval_seconds=1200,
        )
        old = state["content_delivery_queue"]["dkp-old-partial"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["youtube"]["status"] = "pending"
        enqueue_selected_content(
            state, [self.item("dkp-fresh", demand=45)],
            now=self.now, interval_seconds=1200,
        )

        due = due_content(state, now=self.now, limit=1)
        self.assertEqual([pid for pid, _entry in due], ["dkp-fresh"])


    def test_publisher_blocks_stale_queued_copy_when_current_publication_is_active(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-123")],
            now=self.now - timedelta(minutes=10), interval_seconds=1200, max_items=1,
        )
        state["published"] = {
            "dkp-123": {
                "telegram_message_id": 55,
                "expiry_status": "tracked",
                "distribution_queue_id": "dkp-123:previous-selection",
            }
        }
        with (
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher._save"),
            patch("publisher._fresh_selected_item") as revalidate,
        ):
            self.assertEqual(publish_due_queue(), 0)

        revalidate.assert_not_called()
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["published"]["dkp-123"]["telegram_message_id"], 55)
        self.assertEqual(
            state["content_delivery_history"][0]["last_detail"],
            "active_publication_exists",
        )

    def test_terminal_queue_item_moves_to_bounded_history(self):
        state = {}
        enqueue_selected_content(state, [self.item()], now=self.now)
        finish_queue_item(state, "dkp-123", "published", now=self.now)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["content_delivery_history"][0]["status"], "published")


if __name__ == "__main__":
    unittest.main()
