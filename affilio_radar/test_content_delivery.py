import unittest
from datetime import datetime, timedelta, timezone

from content_delivery import (
    due_content, due_unpublished_selection, enqueue_selected_content,
    finish_queue_item, refresh_unpublished_selections,
)
from platform_registry import PLATFORM_NAMES


class ContentDeliveryQueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    def item(self, product_id="dkp-123", price=100_000, demand=50, deadline=None):
        return {
            "product_id": product_id,
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


    def test_terminal_queue_item_moves_to_bounded_history(self):
        state = {}
        enqueue_selected_content(state, [self.item()], now=self.now)
        finish_queue_item(state, "dkp-123", "published", now=self.now)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["content_delivery_history"][0]["status"], "published")


if __name__ == "__main__":
    unittest.main()
