import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import publisher


class IndependentPhotoDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.entry = {
            "product_id": "dkp-independent",
            "platforms": {
                "telegram": {"status": "pending", "attempts": 0},
                "bale": {"status": "pending", "attempts": 0},
                "rubika": {"status": "pending", "attempts": 0},
                "eitaa": {"status": "pending", "attempts": 0},
            },
        }
        self.record = {
            "delivery_status": {
                "telegram": "pending", "bale": "pending",
                "rubika": "pending", "eitaa": "pending",
            },
            "delivery_attempts": {},
        }
        self.item = {"affiliate_url": "https://example.invalid/offer"}

    def test_one_destination_merge_preserves_sibling_statuses(self):
        local_entry = copy.deepcopy(self.entry)
        local_record = copy.deepcopy(self.record)
        local_entry["platforms"]["telegram"]["status"] = "sent"
        local_record["delivery_status"]["telegram"] = "sent"
        local_record["telegram_message_id"] = 1234

        publisher._merge_photo_destination_result(
            self.entry, self.record, "telegram", local_entry, local_record
        )

        self.assertEqual(self.entry["platforms"]["telegram"]["status"], "sent")
        self.assertEqual(self.entry["platforms"]["bale"]["status"], "pending")
        self.assertEqual(self.record["delivery_status"]["telegram"], "sent")
        self.assertEqual(self.record["delivery_status"]["bale"], "pending")
        self.assertEqual(self.record["telegram_message_id"], 1234)

    def test_one_destination_exception_does_not_skip_other_photo_destinations(self):
        def fake_sender(entry, record, item, image_bytes, destination, now):
            if destination == "eitaa":
                raise RuntimeError("test destination failure")
            local_entry = copy.deepcopy(entry)
            local_record = copy.deepcopy(record)
            local_entry["platforms"][destination]["status"] = "sent"
            local_record["delivery_status"][destination] = "sent"
            local_record[f"{destination}_posted_at"] = now.isoformat()
            return destination, local_entry, local_record

        with patch.object(
            publisher, "_deliver_photo_destination_isolated", side_effect=fake_sender
        ) as sender:
            results = publisher._deliver_photo_destinations_independently(
                self.entry, self.record, self.item, b"image", self.now
            )

        self.assertEqual(sender.call_count, len(publisher.PHOTO_PLATFORMS))
        self.assertEqual(set(results), set(publisher.PHOTO_PLATFORMS))
        self.assertEqual(results["eitaa"], "failed")
        for destination in ("telegram", "bale", "rubika"):
            self.assertEqual(results[destination], "sent")
            self.assertEqual(self.entry["platforms"][destination]["status"], "sent")
            self.assertEqual(self.record["delivery_status"][destination], "sent")
        self.assertEqual(self.record["delivery_status"]["eitaa"], "failed")
        self.assertEqual(self.entry["platforms"]["eitaa"]["status"], "pending")

    def test_isolated_sender_does_not_write_shared_state(self):
        with patch.object(publisher, "_target_ready", return_value=True), \
             patch.object(publisher.radar, "_send_platform_photo", return_value={"message_id": 77}), \
             patch.object(publisher, "_save") as save:
            destination, local_entry, local_record = publisher._deliver_photo_destination_isolated(
                self.entry, self.record, self.item, b"image", "telegram", self.now
            )

        save.assert_not_called()
        self.assertEqual(destination, "telegram")
        self.assertEqual(local_entry["platforms"]["telegram"]["status"], "sent")
        self.assertEqual(local_record["delivery_status"]["telegram"], "sent")
        self.assertEqual(self.entry["platforms"]["telegram"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
