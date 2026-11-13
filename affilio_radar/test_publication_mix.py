import unittest
from datetime import datetime, timedelta, timezone

from publication_mix import (
    estimate_next_clean_scan_deadline,
    spread_product_slots,
)

NOW = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)


class PublicationMixTests(unittest.TestCase):
    def test_ten_products_are_spread_across_thirty_hour_scan_window(self):
        products = [f"dkp-{index}" for index in range(1, 11)]
        plan = spread_product_slots(
            products,
            start_at=NOW,
            scan_deadline=NOW + timedelta(hours=30),
            interval_minutes=27,
            safety_slots=1,
            max_items=100,
        )
        self.assertEqual(plan["planned_count"], 10)
        self.assertEqual(plan["available_slots"], 66)
        times = [datetime.fromisoformat(row["scheduled_at"]) for row in plan["items"]]
        gaps = [(right - left).total_seconds() / 60 for left, right in zip(times, times[1:])]
        self.assertTrue(all(gap >= 27 for gap in gaps))
        self.assertGreater(min(gaps), 150)
        self.assertLess(max(gaps), 210)
        self.assertLess(times[-1], NOW + timedelta(hours=30) - timedelta(minutes=27))
        self.assertEqual(plan["deferred_ids"], [])

    def test_every_slot_remains_at_least_twenty_seven_minutes_apart(self):
        for count in range(1, 67):
            ids = [f"dkp-{index}" for index in range(count)]
            plan = spread_product_slots(
                ids,
                start_at=NOW,
                scan_deadline=NOW + timedelta(hours=30),
                interval_minutes=27,
                safety_slots=1,
                max_items=100,
            )
            times = [datetime.fromisoformat(row["scheduled_at"]) for row in plan["items"]]
            self.assertEqual(len(times), count)
            self.assertTrue(all(
                (right - left).total_seconds() >= 27 * 60
                for left, right in zip(times, times[1:])
            ))

    def test_over_capacity_candidates_are_reported_not_silently_planned(self):
        ids = [f"dkp-{index}" for index in range(1, 101)]
        plan = spread_product_slots(
            ids,
            start_at=NOW,
            scan_deadline=NOW + timedelta(hours=2),
            interval_minutes=27,
            safety_slots=1,
            max_items=100,
        )
        self.assertEqual(plan["planned_count"], 4)
        self.assertEqual(len(plan["deferred_ids"]), 96)
        self.assertEqual([row["product_id"] for row in plan["items"]], ids[:4])

    def test_scan_deadline_uses_recent_clean_cycle_duration(self):
        status = {
            "last_clean_cycle_started_at": "2026-11-09T00:00:00+00:00",
            "last_clean_cycle_completed_at": "2026-11-10T06:00:00+00:00",
            "current_cycle_started_at": "2026-11-11T00:00:00+00:00",
        }
        deadline, source = estimate_next_clean_scan_deadline(
            status,
            now=datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(source, "previous_clean_cycle_duration")
        self.assertEqual(deadline, datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc))

    def test_overdue_or_stalled_scan_uses_rolling_fallback(self):
        status = {
            "last_clean_cycle_started_at": "2026-11-09T00:00:00+00:00",
            "last_clean_cycle_completed_at": "2026-11-10T06:00:00+00:00",
            "current_cycle_started_at": "2026-11-10T12:00:00+00:00",
        }
        deadline, source = estimate_next_clean_scan_deadline(
            status, now=NOW, fallback_hours=30
        )
        self.assertEqual(source, "rolling_fallback")
        self.assertEqual(deadline, NOW + timedelta(hours=30))


if __name__ == "__main__":
    unittest.main()
