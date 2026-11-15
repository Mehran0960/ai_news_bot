import unittest
from datetime import datetime, timedelta, timezone

from publication_due_gate import due_publication_slot


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

    def test_naive_timestamps_are_interpreted_as_utc(self):
        due = (self.now - timedelta(seconds=1)).replace(tzinfo=None).isoformat()
        self.assertEqual(
            due_publication_slot({"next_channel_content_due_at": due}, now=self.now),
            (True, "channel_content_due"),
        )


if __name__ == "__main__":
    unittest.main()
