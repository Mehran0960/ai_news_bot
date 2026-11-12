import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import affilio_radar as radar
import publisher as offerchin_publisher


class SharedSelectionMediaRoutingTests(unittest.TestCase):
    def row(self, timestamp, product_id, discount, destinations):
        return (
            float(timestamp),
            product_id,
            {"posted_discount_percent": discount, "posted_original_price": 1_000_000,
             "posted_current_price": 1_000_000 - discount * 1_000},
            None,
            None,
            False,
            list(destinations),
        )

    def test_youtube_keeps_channel_selection_order_not_discount_order(self):
        older = self.row(100, "dkp-older", 12, {"youtube"})
        newer = self.row(200, "dkp-newer", 85, {"youtube"})
        self.assertEqual(
            [row[1] for row in sorted([newer, older], key=radar._video_upload_candidate_sort_key)],
            ["dkp-older", "dkp-newer"],
        )

    def test_aparat_keeps_channel_selection_order_not_discount_order(self):
        older = self.row(100, "dkp-older", 5, {"aparat"})
        newer = self.row(200, "dkp-newer", 90, {"aparat"})
        self.assertEqual(
            [row[1] for row in sorted([newer, older], key=radar._video_upload_candidate_sort_key)],
            ["dkp-older", "dkp-newer"],
        )

    def test_filo_keeps_channel_selection_order(self):
        older = self.row(100, "dkp-older", 10, {"filo"})
        newer = self.row(200, "dkp-newer", 95, {"filo"})
        self.assertEqual(
            [row[1] for row in sorted([newer, older], key=radar._video_upload_candidate_sort_key)],
            ["dkp-older", "dkp-newer"],
        )

    def test_combined_video_destinations_share_one_fifo_order(self):
        older = self.row(100, "dkp-older", 10, {"youtube", "aparat", "filo"})
        newer = self.row(200, "dkp-newer", 95, {"youtube", "aparat", "filo"})
        self.assertEqual(
            [row[1] for row in sorted([newer, older], key=radar._video_upload_candidate_sort_key)],
            ["dkp-older", "dkp-newer"],
        )

    def test_selected_product_video_dispatch_does_not_wait_for_photo_channel_success(self):
        selected = {
            "distribution_queue_id": "dkp-selected:2026-11-11T20:00:00Z",
            "delivery_status": {
                "telegram": "pending", "bale": "pending",
                "rubika": "pending", "eitaa": "pending",
            },
        }
        self.assertTrue(radar._has_video_dispatch_eligibility(selected))
        self.assertFalse(radar._has_video_dispatch_eligibility({
            "delivery_status": {"telegram": "failed", "bale": "not_connected"}
        }))
        # Legacy published records stay eligible when a photo platform has a real receipt.
        self.assertTrue(radar._has_video_dispatch_eligibility({
            "delivery_status": {"telegram": "sent"}
        }))
        self.assertTrue(radar._has_video_dispatch_eligibility({
            "delivery_status": {"bale": "failed"},
            "telegram_message_id": 12345,
        }))
        self.assertTrue(radar._has_video_dispatch_eligibility({
            "delivery_status": {"rubika": "sent"}
        }))

    def test_video_sorting_uses_shared_selection_timestamp_and_product_id_tiebreak(self):
        later = self.row(100, "dkp-b", 90, {"filo"})
        earlier = self.row(100, "dkp-a", 5, {"youtube"})
        self.assertEqual(
            [row[1] for row in sorted([later, earlier], key=radar._video_upload_candidate_sort_key)],
            ["dkp-a", "dkp-b"],
        )


    def test_video_fanout_dispatches_same_product_to_all_video_outlets_and_retries_only_the_failed_one(self):
        now = datetime.now(timezone.utc)
        entry = {
            "product_id": "dkp-selected",
            "platforms": {
                "telegram": {"status": "failed", "attempts": 1},
                "bale": {"status": "sent", "attempts": 1},
            },
        }
        record = {
            "distribution_queue_id": "dkp-selected:selection-1",
            "delivery_status": {"telegram": "failed", "bale": "sent"},
            "youtube_upload_status": "pending",
            "aparat_upload_status": "pending",
            "filo_upload_status": "pending",
            "video_generation_status": "pending",
        }
        state = {"published": {"dkp-selected": record}}
        calls = []

        def fake_process(_state, *, destinations, retry_immediately, **kwargs):
            calls.append((set(destinations), retry_immediately, kwargs.get("only_product_id")))
            if not retry_immediately:
                record["youtube_upload_status"] = "retry"
                record["aparat_upload_status"] = "uploaded"
                record["filo_upload_status"] = "submitted_pending_approval"
            else:
                record["youtube_upload_status"] = "skipped_after_retries"
            return True

        with (
            patch.object(offerchin_publisher, "_target_ready", return_value=True),
            patch.object(offerchin_publisher.radar, "process_pending_short_video", side_effect=fake_process),
            patch.object(offerchin_publisher, "_save"),
        ):
            offerchin_publisher._process_video_destinations(state, entry, record, now)

        self.assertEqual(calls[0][0], {"youtube", "aparat", "filo"})
        self.assertFalse(calls[0][1])
        self.assertEqual(calls[0][2], "dkp-selected")
        self.assertEqual(calls[1][0], {"youtube"})
        self.assertTrue(calls[1][1])
        self.assertEqual(entry["platforms"]["youtube"]["status"], "skipped")
        self.assertEqual(entry["platforms"]["aparat"]["status"], "sent")
        self.assertEqual(entry["platforms"]["filo"]["status"], "sent")
        self.assertEqual(record["youtube_upload_status"], "skipped_after_retries")

    def test_video_upload_outcome_unknown_is_not_retried_and_other_outlets_continue(self):
        now = datetime.now(timezone.utc)
        entry = {"product_id": "dkp-unknown", "platforms": {}}
        record = {
            "distribution_queue_id": "dkp-unknown:selection-2",
            "youtube_upload_status": "upload_result_unknown",
            "aparat_upload_status": "uploaded",
            "filo_upload_status": "published",
            "youtube_last_error": "timeout_after_submit",
        }
        state = {"published": {"dkp-unknown": record}}
        calls = []

        def fake_process(_state, *, destinations, **kwargs):
            calls.append(set(destinations))
            return True

        with (
            patch.object(offerchin_publisher, "_target_ready", return_value=True),
            patch.object(offerchin_publisher.radar, "process_pending_short_video", side_effect=fake_process),
            patch.object(offerchin_publisher, "_save"),
        ):
            offerchin_publisher._process_video_destinations(state, entry, record, now)

        self.assertEqual(calls, [])
        self.assertEqual(entry["platforms"]["youtube"]["status"], "manual_review")
        self.assertEqual(entry["platforms"]["aparat"]["status"], "sent")
        self.assertEqual(entry["platforms"]["filo"]["status"], "sent")


if __name__ == "__main__":
    unittest.main()
