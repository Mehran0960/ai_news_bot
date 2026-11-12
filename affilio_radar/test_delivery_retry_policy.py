import unittest
from datetime import datetime, timezone

from publisher import (
    MAX_PLATFORM_DELIVERY_ATTEMPTS,
    _target_retry,
)


class PlatformDeliveryRetryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def test_failed_photo_destination_becomes_terminal_after_bounded_attempts(self):
        self.assertEqual(MAX_PLATFORM_DELIVERY_ATTEMPTS, 3)
        entry = {"platforms": {"telegram": {"status": "sending", "attempts": 1}}}

        _target_retry(entry, "telegram", self.now, "first failure")
        target = entry["platforms"]["telegram"]
        self.assertEqual(target["status"], "failed")
        self.assertEqual(target["attempts"], 1)
        self.assertIn("next_attempt_at", target)

        # The sender increments attempts before each network side effect.
        target["status"] = "sending"
        target["attempts"] += 1
        _target_retry(entry, "telegram", self.now, "second failure")
        self.assertEqual(target["status"], "failed")
        self.assertEqual(target["attempts"], 2)

        target["status"] = "sending"
        target["attempts"] += 1
        _target_retry(entry, "telegram", self.now, "third failure")
        self.assertEqual(target["status"], "manual_review")
        self.assertEqual(target["attempts"], 3)
        self.assertEqual(target["skip_reason"], "max_delivery_attempts_reached")
        self.assertNotIn("next_attempt_at", target)

    def test_revalidation_failure_consumes_a_retry_even_without_a_send_marker(self):
        entry = {"platforms": {"bale": {"status": "pending", "attempts": 0}}}
        _target_retry(entry, "bale", self.now, "live price revalidation unavailable")
        target = entry["platforms"]["bale"]
        self.assertEqual(target["attempts"], 1)
        self.assertEqual(target["status"], "failed")

    def test_exhausting_one_destination_does_not_skip_other_destinations(self):
        entry = {
            "platforms": {
                "telegram": {"status": "sending", "attempts": 2},
                "bale": {"status": "pending", "attempts": 0},
            }
        }
        _target_retry(entry, "telegram", self.now, "third failure")
        self.assertEqual(entry["platforms"]["telegram"]["status"], "manual_review")
        self.assertEqual(entry["platforms"]["bale"]["status"], "pending")
        self.assertEqual(entry["platforms"]["bale"]["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
