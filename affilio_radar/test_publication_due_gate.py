import unittest
from datetime import datetime, timedelta, timezone

from publication_due_gate import due_publication_slot, has_active_core_channel_queue


class PublicationDueGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)

    def test_due_product_slot_skips_repeated_discovery(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({"next_channel_content_due_at": due}, now=self.now),
            (True, "channel_content_due"),
        )

    def test_due_editorial_midpoint_skips_repeated_discovery(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({"next_editorial_planning_at": due}, now=self.now),
            (True, "editorial_midpoint_due"),
        )

    def test_future_product_and_editorial_slots_do_not_skip_discovery(self):
        future = (self.now + timedelta(seconds=30)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "next_channel_content_due_at": future,
                "next_editorial_planning_at": future,
            }, now=self.now),
            (False, "no_publication_slot_due"),
        )

    def test_due_channel_slot_takes_priority_when_both_are_due(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "next_channel_content_due_at": due,
                "next_editorial_planning_at": due,
            }, now=self.now),
            (True, "channel_content_due"),
        )

    def test_missing_or_invalid_projection_fails_open(self):
        self.assertEqual(
            due_publication_slot(None, now=self.now),
            (False, "dispatch_sidecar_unavailable_fail_open"),
        )
        self.assertEqual(
            due_publication_slot({"next_channel_content_due_at": "not-a-date"}, now=self.now),
            (False, "no_publication_slot_due"),
        )

    def test_active_product_queue_blocks_discovery_even_before_next_slot_is_due(self):
        future = (self.now + timedelta(seconds=30)).isoformat()
        queue_state = {
            "content_delivery_queue": {
                "product_1": {
                    "status": "queued",
                    "scheduled_at": future,
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "pending"},
                    },
                }
            }
        }
        self.assertEqual(
            due_publication_slot(
                {"next_channel_content_due_at": future},
                queue_state=queue_state,
                now=self.now,
            ),
            (True, "active_core_channel_queue"),
        )

    def test_active_editorial_queue_blocks_discovery_until_core_destinations_resolve(self):
        queue_state = {
            "editorial_delivery_queue": {
                "editorial_1": {
                    "status": "queued",
                    "platforms": {
                        "telegram": {"status": "failed"},
                        "bale": {"status": "sent"},
                    },
                }
            }
        }
        self.assertTrue(has_active_core_channel_queue(queue_state))

    def test_terminal_product_and_editorial_receipts_allow_discovery(self):
        queue_state = {
            "content_delivery_queue": {
                "product_done": {
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "manual_review"},
                    },
                }
            },
            "editorial_delivery_queue": {
                "editorial_done": {
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "skipped_limit"},
                        "bale": {"status": "not_connected"},
                    },
                },
                "editorial_failed": {
                    "status": "failed",
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                    },
                },
            },
        }
        self.assertFalse(has_active_core_channel_queue(queue_state))

    def test_product_failed_retryable_status_keeps_discovery_deferred(self):
        queue_state = {
            "content_delivery_queue": {
                "product_retry": {
                    "status": "failed",
                    "platforms": {
                        "telegram": {"status": "failed"},
                        "bale": {"status": "pending"},
                    },
                }
            }
        }
        self.assertTrue(has_active_core_channel_queue(queue_state))

    def test_naive_timestamps_are_interpreted_as_utc(self):
        due = (self.now - timedelta(seconds=1)).replace(tzinfo=None).isoformat()
        self.assertEqual(
            due_publication_slot({"next_channel_content_due_at": due}, now=self.now),
            (True, "channel_content_due"),
        )


if __name__ == "__main__":
    unittest.main()
