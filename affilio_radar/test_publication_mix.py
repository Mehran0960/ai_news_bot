import unittest
from datetime import datetime, timedelta, timezone

from publication_mix import (
    apply_product_publication_schedule,
    estimate_next_clean_scan_deadline,
    next_product_start_at,
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
        self.assertLess(max(gaps), 220)
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

    def test_existing_future_plan_keeps_its_anchor_on_repeated_replanning(self):
        first = NOW + timedelta(hours=3)
        state = {
            "content_delivery_queue": {
                "dkp-1": {
                    "status": "queued",
                    "attempt_count": 0,
                    "scheduled_at": first.isoformat(),
                    "publication_plan_cycle_id": "cycle-1",
                    "platforms": {},
                }
            }
        }
        self.assertEqual(
            next_product_start_at(state, now=NOW + timedelta(minutes=27)),
            first,
        )

    def test_product_sequences_follow_actual_distributed_slots(self):
        state = {
            "content_delivery_queue": {
                f"dkp-{index}": {
                    "status": "queued",
                    "attempt_count": 0,
                    "sequence_number": index,
                    "payload": {"product_id": f"dkp-{index}", "sequence_number": index},
                    "platforms": {},
                }
                for index in range(1, 4)
            }
        }
        deadline = NOW + timedelta(hours=30)
        plan = apply_product_publication_schedule(
            state,
            now=NOW,
            scan_deadline=deadline,
            cycle_id="cycle-sequence",
            interval_minutes=27,
            safety_slots=1,
            max_items=100,
        )
        rows = sorted(
            state["content_delivery_queue"].values(),
            key=lambda row: row["scheduled_at"],
        )
        self.assertEqual(len(rows), 3)
        for row in rows:
            expected = int(datetime.fromisoformat(row["scheduled_at"]).timestamp())
            self.assertEqual(row["sequence_number"], expected)
            self.assertEqual(row["payload"]["sequence_number"], expected)
        self.assertEqual(plan["product_count"], 3)

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

    def test_scan_deadline_stays_fixed_for_repeated_runs_in_same_cycle(self):
        deadline = NOW + timedelta(hours=19)
        status = {
            "current_cycle_started_at": "2026-11-11T00:00:00+00:00",
            "completed_candidates_cycle_at": "2026-11-10T06:00:00+00:00",
        }
        cycle = __import__("publication_mix").catalog_cycle_id(status)
        previous_plan = {
            "cycle_id": cycle,
            "scan_deadline_at": deadline.isoformat(),
        }
        next_run_now = NOW + timedelta(minutes=27)
        projected, source = estimate_next_clean_scan_deadline(
            status,
            now=next_run_now,
            fallback_hours=30,
            previous_plan=previous_plan,
            cycle_id=cycle,
        )
        self.assertEqual(source, "persisted_cycle_deadline")
        self.assertEqual(projected, deadline)

    def test_new_scan_attempt_gets_a_new_cycle_identity(self):
        from publication_mix import catalog_cycle_id
        first = {
            "current_cycle_started_at": "2026-11-11T00:00:00+00:00",
            "completed_candidates_cycle_at": "2026-11-10T06:00:00+00:00",
        }
        second = {
            **first,
            "current_cycle_started_at": "2026-11-13T09:00:00+00:00",
        }
        self.assertNotEqual(catalog_cycle_id(first), catalog_cycle_id(second))

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
