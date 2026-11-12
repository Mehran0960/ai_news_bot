import unittest

import affilio_radar as radar


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

    def test_video_sorting_preserves_insertion_order_when_selection_timestamps_tie(self):
        later = self.row(100, "dkp-b", 90, {"filo"})
        earlier = self.row(100, "dkp-a", 5, {"youtube"})
        self.assertEqual(
            [row[1] for row in sorted([later, earlier], key=radar._video_upload_candidate_sort_key)],
            ["dkp-b", "dkp-a"],
        )


if __name__ == "__main__":
    unittest.main()
