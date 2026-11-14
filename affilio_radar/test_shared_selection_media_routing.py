import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

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

    def test_pending_video_helper_filters_by_destination_and_terminal_status(self):
        pending = {
            "video_generation_status": "pending",
            "youtube_upload_status": "uploaded",
            "filo_upload_status": "retry",
        }
        self.assertTrue(radar._has_pending_video_destination(pending, {"filo"}))
        self.assertFalse(radar._has_pending_video_destination(pending, {"youtube"}))
        self.assertFalse(radar._has_pending_video_destination({
            "video_generation_status": "pending",
            "youtube_upload_status": "skipped_platform_limit",
        }, {"youtube"}))

    def test_expired_legacy_video_pending_status_does_not_block_editorial_fifo(self):
        now = datetime(2026, 11, 14, 14, 30, tzinfo=timezone.utc)
        record = {
            "video_generation_status": "skipped_expiring_soon",
            "youtube_upload_status": "skipped_expiring_soon",
            "aparat_upload_status": "pending",
            "expires_at": (now - timedelta(days=4)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        self.assertFalse(radar._has_pending_video_destination(record, now=now))

    def test_legacy_record_without_actionable_video_state_does_not_block_fifo(self):
        # The old uploader cannot process a record that has no generation state or
        # explicit destination status; do not let its implicit defaults block editorial.
        record = {
            "distribution_queue_id": "dkp-legacy",
            "video_dispatch_eligible": True,
            "expires_at": "2026-10-27T09:57:25+00:00",
        }
        self.assertFalse(
            radar._has_pending_video_destination(
                record,
                now=datetime(2026, 11, 14, 14, 30, tzinfo=timezone.utc),
            )
        )

    def test_future_verified_expiry_keeps_skipped_video_requeueable(self):
        now = datetime(2026, 11, 14, 14, 30, tzinfo=timezone.utc)
        record = {
            "video_generation_status": "skipped_expiring_soon",
            "youtube_upload_status": "pending",
            "expires_at": (now + timedelta(hours=3)).isoformat(),
            "expiry_source": "digikala_live_deals_feed",
            "expiry_deadline_verified_directly": True,
            "expiry_estimated": False,
        }
        self.assertTrue(radar._has_pending_video_destination(record, {"youtube"}, now=now))

    def test_dispatch_sidecar_keeps_oldest_pending_canonical_products_and_drops_terminal_ones(self):
        state = {
            "published": {
                "newer_terminal": {
                    "ts": 300,
                    "distribution_queue_id": "newer-terminal",
                    "youtube_upload_status": "uploaded",
                    "aparat_upload_status": "skipped_unverified_deadline",
                    "filo_upload_status": "skipped_after_retries",
                },
                "newer_pending": {
                    "ts": 200,
                    "distribution_queue_id": "newer-pending",
                    "video_generation_status": "pending",
                    "youtube_upload_status": "pending",
                },
                "oldest_pending": {
                    "ts": 100,
                    "distribution_queue_id": "oldest-pending",
                    "video_generation_status": "pending",
                    "aparat_upload_status": "pending",
                },
            }
        }
        sidecar = radar.build_video_upload_dispatch_state(state)
        self.assertEqual(list(sidecar["published"]), ["oldest_pending", "newer_pending"])
        self.assertEqual(sidecar["published"]["oldest_pending"]["ts"], 100)
        self.assertEqual(sidecar["published"]["newer_pending"]["ts"], 200)

    def test_unified_video_run_fans_out_each_product_before_advancing(self):
        calls = []
        outcomes = iter([True, False])
        with (
            patch.object(radar, "load_state", return_value={"published": {}}),
            patch.object(
                radar,
                "process_pending_short_video",
                side_effect=lambda state, **kwargs: calls.append(kwargs) or next(outcomes),
            ),
        ):
            self.assertEqual(radar.run_all_video_uploads_only(), 0)
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call["destinations"], {"youtube", "aparat", "filo"})
            self.assertIsNone(call["max_age_hours"])

    def test_unified_runner_uses_a_bounded_fifo_batch(self):
        calls = []
        with (
            patch.object(radar, "load_state", return_value={"published": {}}),
            patch.object(
                radar,
                "process_pending_short_video",
                side_effect=lambda state, **kwargs: calls.append(kwargs) or True,
            ),
            patch.object(radar, "MAX_SHORT_VIDEOS_PER_RUN", 3),
        ):
            self.assertEqual(radar.run_all_video_uploads_only(), 0)
        self.assertEqual(len(calls), 3)

    def test_video_retry_budget_is_bounded(self):
        self.assertEqual(radar.MAX_VIDEO_UPLOAD_ATTEMPTS, 3)

    def test_video_sorting_uses_shared_selection_timestamp_and_product_id_tiebreak(self):
        later = self.row(100, "dkp-b", 90, {"filo"})
        earlier = self.row(100, "dkp-a", 5, {"youtube"})
        self.assertEqual(
            [row[1] for row in sorted([later, earlier], key=radar._video_upload_candidate_sort_key)],
            ["dkp-a", "dkp-b"],
        )


if __name__ == "__main__":
    unittest.main()
