import unittest
from pathlib import Path
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

    def test_empty_video_projection_releases_shared_publisher_lock_before_setup(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "offerchin-video-publisher.yml"
        ).read_text(encoding="utf-8")
        gate_index = workflow.index("Skip immediately when the canonical video queue is empty")
        python_index = workflow.index("- name: Set up Python")
        self.assertLess(gate_index, python_index)
        self.assertIn("id: video_queue", workflow)
        self.assertIn(
            "jq -e '.published | type == \"object\" and length > 0'",
            workflow,
        )
        self.assertIn('echo "has_video_records=false" >> "$GITHUB_OUTPUT"', workflow)
        gated_steps = (
            "Set up Python",
            "Install project dependencies",
            "Install Playwright Chromium for the Filo adapter",
            "Stage official DigiPay logo for matching video cards",
            "Validate the shared FIFO and video upload adapters",
            "Verify Filo login without publishing",
            "Publish the active editorial video before newer product videos",
            "Fan out the same FIFO to YouTube, Aparat and Filo",
        )
        for name in gated_steps:
            start = workflow.index(f"- name: {name}")
            end = workflow.find("\n      - name:", start + 1)
            section = workflow[start:end if end >= 0 else len(workflow)]
            self.assertIn(
                "if: steps.video_queue.outputs.has_video_records == 'true'",
                section,
                msg=f"{name} must not run when the canonical queue is empty",
            )
        self.assertIn(
            "always() && steps.video_queue.outputs.has_video_records == 'true'",
            workflow,
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

    def test_youtube_upload_workflows_share_global_lock_and_interval(self):
        root = Path(__file__).resolve().parents[1]
        workflow_paths = (
            root / ".github" / "workflows" / "youtube-video-upload.yml",
            root / ".github" / "workflows" / "offerchin-video-publisher.yml",
        )
        groups = []
        for workflow_path in workflow_paths:
            source = workflow_path.read_text(encoding="utf-8")
            match = re.search(r"(?m)^\s*group:\s*([^\s#]+)", source)
            self.assertIsNotNone(match, workflow_path.name)
            groups.append(match.group(1))
            self.assertIn('AFFILIO_YOUTUBE_UPLOAD_INTERVAL_HOURS: "8.25"', source)
        self.assertEqual(len(set(groups)), 1)
        self.assertEqual(groups[0], "offerchin-youtube-global-upload")

    def test_youtube_upload_interval_has_a_three_per_rolling_day_floor(self):
        self.assertEqual(radar.YOUTUBE_UPLOAD_INTERVAL_HOURS, 8.25)
        self.assertEqual(radar.YOUTUBE_UPLOAD_INTERVAL_SECONDS, 8 * 3600 + 15 * 60)

    def test_youtube_global_upload_slot_enforces_even_rolling_24h_cadence(self):
        now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        state = {"youtube_last_upload_success_at": now.isoformat()}
        expected = now + timedelta(hours=8, minutes=15)

        slot = radar._youtube_next_upload_slot_at(state, now=now)
        self.assertEqual(slot, expected)
        self.assertEqual(state["youtube_next_upload_at"], expected.isoformat())

        # The next upload is blocked for the full 8h15m gap.
        self.assertEqual(
            radar._youtube_next_upload_slot_at(
                state, now=now + timedelta(hours=8, minutes=14, seconds=59)
            ),
            expected,
        )
        # At the exact saved slot it becomes due; the expired slot is cleared.
        self.assertIsNone(
            radar._youtube_next_upload_slot_at(state, now=expected)
        )
        self.assertNotIn("youtube_next_upload_at", state)

    def test_video_dispatch_projection_carries_youtube_global_slot(self):
        now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        expected = now + timedelta(hours=8, minutes=15)
        state = {"youtube_last_upload_success_at": now.isoformat()}
        sidecar = radar.build_video_upload_dispatch_state(state, now=now)
        self.assertEqual(sidecar["youtube_next_upload_at"], expected.isoformat())

    def test_youtube_daily_quota_skip_remains_pending_in_dispatch_projection(self):
        now = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)
        record = {
            "ts": now.timestamp(),
            "video_generation_status": "generated",
            "distribution_queue_id": "youtube-quota-retry",
            "youtube_upload_status": "skipped_platform_limit",
            "youtube_skip_reason": "youtube_daily_quota_pause",
            "youtube_next_attempt_at": (now + timedelta(hours=24)).isoformat(),
        }
        self.assertTrue(radar._has_pending_video_destination(record, {"youtube"}, now=now))
        sidecar = radar.build_video_upload_dispatch_state({
            "published": {"item": record},
            "youtube_uploads_paused_until": (now + timedelta(hours=24)).isoformat(),
        })
        self.assertIn("item", sidecar["published"])
        self.assertEqual(sidecar["youtube_uploads_paused_until"], (now + timedelta(hours=24)).isoformat())

    def test_aparat_unverified_deadline_skip_is_requeued_independently(self):
        now = datetime(2026, 11, 14, 14, 30, tzinfo=timezone.utc)
        record = {
            "video_generation_status": "pending",
            "distribution_queue_id": "aparat-no-deadline",
            "aparat_upload_status": "skipped_unverified_deadline",
        }
        self.assertTrue(radar._has_pending_video_destination(record, {"aparat"}, now=now))
        sidecar = radar.build_video_upload_dispatch_state({"published": {"item": {
            **record, "ts": now.timestamp(),
        }}})
        self.assertIn("item", sidecar["published"])

    def test_dispatch_sidecar_exposes_pending_editorial_photo_channels_independently(self):
        now = datetime(2026, 11, 18, 5, 0, tzinfo=timezone.utc)
        state = {
            "editorial_delivery_queue": {
                "editorial:channel-guide": {
                    "content_id": "editorial:channel-guide",
                    "sequence_number": 43,
                    "status": "partial",
                    "scheduled_at": (now - timedelta(minutes=2)).isoformat(),
                    "platforms": {
                        "telegram": {"status": "sent", "message_id": "tg-43"},
                        "bale": {"status": "pending"},
                        "rubika": {"status": "retry", "next_attempt_at": (now + timedelta(minutes=15)).isoformat()},
                        "eitaa": {"status": "manual_review"},
                        "youtube": {"status": "pending"},
                    },
                },
            }
        }
        sidecar = radar.build_video_upload_dispatch_state(state, now=now)
        self.assertEqual(len(sidecar["editorial_channel_queue"]), 1)
        item = sidecar["editorial_channel_queue"][0]
        self.assertEqual(item["content_id"], "editorial:channel-guide")
        self.assertEqual(set(item["platforms"]), {"bale", "rubika"})
        self.assertNotIn("telegram", item["platforms"])
        self.assertNotIn("youtube", item["platforms"])

    def test_dispatch_sidecar_exposes_pending_editorial_video_destinations_independently(self):
        now = datetime(2026, 11, 18, 5, 0, tzinfo=timezone.utc)
        state = {
            "editorial_delivery_queue": {
                "editorial:delivery-guide": {
                    "content_id": "editorial:delivery-guide",
                    "sequence_number": 42,
                    "status": "partial",
                    "scheduled_at": (now - timedelta(minutes=2)).isoformat(),
                    "platforms": {
                        "telegram": {"status": "sent", "message_id": "tg-42"},
                        "bale": {"status": "sent", "message_id": "ba-42"},
                        "youtube": {"status": "retry", "next_attempt_at": (now + timedelta(hours=3)).isoformat()},
                        "aparat": {"status": "pending"},
                        "filo": {"status": "manual_review"},
                    },
                },
                "editorial:complete": {
                    "content_id": "editorial:complete",
                    "sequence_number": 41,
                    "status": "completed",
                    "platforms": {"youtube": {"status": "pending"}},
                },
            }
        }
        sidecar = radar.build_video_upload_dispatch_state(state, now=now)
        self.assertEqual(len(sidecar["editorial_video_queue"]), 1)
        item = sidecar["editorial_video_queue"][0]
        self.assertEqual(item["content_id"], "editorial:delivery-guide")
        self.assertEqual(item["sequence_number"], 42)
        self.assertEqual(set(item["platforms"]), {"youtube", "aparat"})
        self.assertEqual(item["platforms"]["youtube"]["status"], "retry")
        self.assertNotIn("telegram", item["platforms"])

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
