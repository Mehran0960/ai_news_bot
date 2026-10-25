import unittest
from datetime import datetime, timedelta, timezone

from content_delivery import due_content, enqueue_selected_content, finish_queue_item
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

    def test_terminal_queue_item_moves_to_bounded_history(self):
        state = {}
        enqueue_selected_content(state, [self.item()], now=self.now)
        finish_queue_item(state, "dkp-123", "published", now=self.now)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["content_delivery_history"][0]["status"], "published")


if __name__ == "__main__":
    unittest.main()
