import unittest
from datetime import datetime, timedelta, timezone

from publication_due_gate import due_publication_slot


class PublicationDueGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)

    def test_due_product_slot_skips_repeated_discovery(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_channel_content_due_at": due,
            }, now=self.now),
            (True, "channel_content_due"),
        )

    def test_due_editorial_midpoint_skips_repeated_discovery(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_editorial_planning_at": due,
            }, now=self.now),
            (True, "editorial_midpoint_due"),
        )

    def test_future_product_and_editorial_slots_do_not_skip_discovery(self):
        future = (self.now + timedelta(seconds=30)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_channel_content_due_at": future,
                "next_editorial_planning_at": future,
            }, now=self.now),
            (False, "no_publication_slot_due"),
        )

    def test_due_channel_slot_takes_priority_when_both_are_due(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_channel_content_due_at": due,
                "next_editorial_planning_at": due,
            }, now=self.now),
            (True, "channel_content_due"),
        )

    def test_stale_due_timestamps_do_not_block_discovery_when_queues_are_empty(self):
        stale = (self.now - timedelta(hours=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 0,
                "editorial_channel_queue": [],
                "next_channel_content_due_at": stale,
                "next_editorial_planning_at": stale,
            }, now=self.now),
            (False, "no_active_publication_queue"),
        )

    def test_stale_editorial_midpoint_before_last_channel_post_does_not_skip_discovery(self):
        stale_editorial = (self.now - timedelta(days=1)).isoformat()
        last_channel_post = (self.now - timedelta(minutes=5)).isoformat()
        future_product = (self.now + timedelta(minutes=25)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "last_channel_published_at": last_channel_post,
                "next_channel_content_due_at": future_product,
                "next_editorial_planning_at": stale_editorial,
            }, now=self.now),
            (False, "no_publication_slot_due"),
        )

    def test_editorial_midpoint_after_last_channel_post_remains_due(self):
        last_channel_post = (self.now - timedelta(minutes=20)).isoformat()
        due_editorial = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "last_channel_published_at": last_channel_post,
                "next_editorial_planning_at": due_editorial,
            }, now=self.now),
            (True, "editorial_midpoint_due"),
        )

    def test_editorial_recovery_queue_keeps_a_due_editorial_slot_valid(self):
        due = (self.now - timedelta(seconds=1)).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 0,
                "editorial_channel_queue": [{"content_id": "editorial:retry"}],
                "next_editorial_planning_at": due,
            }, now=self.now),
            (True, "editorial_midpoint_due"),
        )

    def test_missing_or_invalid_projection_fails_open(self):
        self.assertEqual(
            due_publication_slot(None, now=self.now),
            (False, "dispatch_sidecar_unavailable_fail_open"),
        )
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_channel_content_due_at": "not-a-date",
            }, now=self.now),
            (False, "no_publication_slot_due"),
        )

    def test_naive_timestamps_are_interpreted_as_utc(self):
        due = (self.now - timedelta(seconds=1)).replace(tzinfo=None).isoformat()
        self.assertEqual(
            due_publication_slot({
                "pending_product_queue_count": 1,
                "next_channel_content_due_at": due,
            }, now=self.now),
            (True, "channel_content_due"),
        )


    def test_due_gate_runs_before_runtime_setup_and_expensive_validation(self):
        from pathlib import Path
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "offerchin-publisher.yml"
        ).read_text(encoding="utf-8")
        gate = workflow.index("name: Detect due product or editorial slots")
        setup = workflow.index("name: Set up Python")
        discovery = workflow.index("name: Discover and queue the next verified selection")
        delivery = workflow.index("name: Publish due selections to Telegram and Bale only")
        self.assertLess(gate, setup)
        self.assertLess(gate, discovery)
        self.assertLess(gate, delivery)
        self.assertIn("if: steps.publication_due.outputs.has_due_slot != 'true'", workflow)
        self.assertEqual(
            workflow.count("if: steps.publication_due.outputs.has_due_slot != 'true'"),
            4,
        )

if __name__ == "__main__":
    unittest.main()
