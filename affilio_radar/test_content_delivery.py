import unittest
import os
from pathlib import Path
from unittest.mock import patch
import math
from datetime import datetime, timedelta, timezone

from content_delivery import (
    calculate_product_publication_cadence,
    channel_publication_wait_seconds, next_channel_publication_at,
    due_content, due_unpublished_selection, enqueue_selected_content,
    finish_queue_item, get_last_channel_published_at, get_last_product_channel_published_at,
    has_fresh_unpublished_selection, allocate_publication_sequence, promote_fallback_selection,
    refresh_unpublished_selections, selection_cadence_anchor, reschedule_product_queue_evenly,
    reflow_product_queue_after_delivery,
)
from platform_registry import CORE_PHOTO_PLATFORMS, PHOTO_PLATFORMS, PLATFORM_NAMES
from publication_policy import (
    MIN_CHANNEL_POST_INTERVAL_SECONDS,
    MAX_CHANNEL_POST_INTERVAL_SECONDS,
    channel_post_interval_seconds,
)
from publisher import (
    publish_due_queue, _fresh_selected_item, _eligible_fallback_candidates,
    MAX_ITEMS_PER_RUN, _due_editorial_precedes_product, _target_ready,
)


class ContentDeliveryQueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


    def test_eitaa_is_disabled_by_default_when_credentials_are_present(self):
        with patch.dict(os.environ, {
            "EITAA_BOT_TOKEN": "test-token",
            "EITAA_CHANNEL_ID": "test-channel",
        }, clear=True):
            self.assertFalse(_target_ready("eitaa"))

    def test_eitaa_requires_explicit_opt_in_when_credentials_are_present(self):
        with patch.dict(os.environ, {
            "EITAA_ENABLE_PUBLISHING": "true",
            "EITAA_BOT_TOKEN": "test-token",
            "EITAA_CHANNEL_ID": "test-channel",
        }, clear=True):
            self.assertTrue(_target_ready("eitaa"))

    def test_eitaa_can_still_be_explicitly_disabled(self):
        with patch.dict(os.environ, {
            "EITAA_ENABLE_PUBLISHING": "false",
            "EITAA_BOT_TOKEN": "test-token",
            "EITAA_CHANNEL_ID": "test-channel",
        }, clear=True):
            self.assertFalse(_target_ready("eitaa"))

    def test_eitaa_missing_credentials_only_disables_eitaa(self):
        with patch.dict(os.environ, {"EITAA_ENABLE_PUBLISHING": "true"}, clear=True):
            self.assertFalse(_target_ready("eitaa"))

    def test_publication_workflow_has_no_fixed_post_interval_setting(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "affilio-radar.yml"
        )
        self.assertTrue(workflow.is_file())
        self.assertNotIn("AFFILIO_MIN_POST_INTERVAL_HOURS", workflow.read_text(encoding="utf-8"))

    def item(self, product_id="dkp-123", price=100_000, demand=50, deadline=None):
        return {
            "product_id": product_id,
            "title": f"Test product {product_id}",
            "product_url": f"https://www.digikala.com/product/{product_id}/",
            "affiliate_url": f"https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2F{product_id}%2F",
            "current_price": price,
            "original_price": 200_000,
            "discount_percent": 50,
            "savings_toman": 100_000,
            "availability": "in_stock",
            "image_url": f"https://example.com/{product_id}.webp",
            "demand_score": demand,
            "current_demand_verified": True,
            "current_demand_score": demand,
            "recent_review_growth_7d": 5,
            "demand_window_hours": 24,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_reference_price_toman": int(round(price * 100 / 90)),
            "market_available_offer_count": 3,
            "market_match_score": 85,
            "market_price_advantage_pct": 10,
            "market_price_checked_at": self.now.isoformat(),
            "selection_discount_floor": 50,
            "deal_expires_at": deadline.isoformat() if deadline else "",
        }


    def test_product_and_editorial_share_one_monotonic_sequence(self):
        state = {}
        summary = enqueue_selected_content(
            state, [self.item("dkp-sequence")], now=self.now,
            minimum_runway_minutes=0,
        )
        self.assertEqual(summary["added"], 1)
        product_entry = state["content_delivery_queue"]["dkp-sequence"]
        self.assertEqual(product_entry["content_type"], "product")
        self.assertEqual(product_entry["sequence_number"], 1)
        self.assertEqual(product_entry["payload"]["sequence_number"], 1)
        self.assertEqual(product_entry["content_id"], "dkp-sequence")
        self.assertEqual(allocate_publication_sequence(state), 2)

    def test_shared_channel_wait_applies_to_all_content_types(self):
        state = {
            "last_channel_published_at": (self.now - timedelta(minutes=20)).isoformat()
        }
        self.assertEqual(channel_publication_wait_seconds(state, now=self.now), MIN_CHANNEL_POST_INTERVAL_SECONDS - 20 * 60)
        next_slot = next_channel_publication_at(state)
        self.assertEqual(
            next_slot,
            self.now + timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS - 20 * 60),
        )
        after_gap = self.now + timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS - 20 * 60)
        self.assertEqual(channel_publication_wait_seconds(state, now=after_gap), 0)

    def test_sequence_allocator_recovers_from_failed_editorial_attempt_ledger(self):
        state = {
            "publication_sequence_counter": 2,
            "editorial_delivery_attempts": [
                {"content_id": "editorial:failed-first", "sequence_number": 7}
            ],
        }
        self.assertEqual(allocate_publication_sequence(state), 8)

    def test_last_mile_product_fallback_inherits_failed_slot_sequence(self):
        state = {
            "content_delivery_history": [{
                "content_id": "dkp-primary",
                "status": "stale_selection",
                "sequence_number": 9,
                "last_detail": "live_product_details_incomplete",
            }]
        }
        backup = self.item("dkp-1234")
        promoted = promote_fallback_selection(
            state, [backup], now=self.now, reason="live_product_details_incomplete"
        )
        self.assertEqual(promoted, "dkp-1234")
        entry = state["content_delivery_queue"]["dkp-1234"]
        self.assertEqual(entry["sequence_number"], 9)
        self.assertEqual(entry["payload"]["sequence_number"], 9)
        self.assertEqual(entry["content_type"], "product")

    def test_initial_product_slot_has_no_fixed_offset_and_later_slots_use_planned_interval(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-first")], now=self.now,
            interval_seconds=1200, minimum_runway_minutes=0,
        )
        first = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-first"]["scheduled_at"]
        )
        self.assertEqual(first, self.now)

        state["last_channel_published_at"] = self.now.isoformat()
        state["editorial_delivery_history"] = [{"content_id": "editorial:sample"}]
        enqueue_selected_content(
            state, [self.item("dkp-second")],
            now=self.now + timedelta(minutes=1),
            interval_seconds=1200, minimum_runway_minutes=0,
        )
        second = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-second"]["scheduled_at"]
        )
        self.assertEqual(
            second,
            self.now + timedelta(
                seconds=channel_post_interval_seconds(
                    f"product:{state['content_delivery_queue']['dkp-second']['sequence_number']}:dkp-second"
                )
            ),
        )
        self.assertGreaterEqual(
            (second - self.now).total_seconds(), MIN_CHANNEL_POST_INTERVAL_SECONDS
        )
        self.assertLessEqual(
            (second - self.now).total_seconds(), MAX_CHANNEL_POST_INTERVAL_SECONDS
        )


    def test_enqueue_persists_platform_neutral_payload_without_delivery(self):
        state = {}
        summary = enqueue_selected_content(
            state, [self.item()], now=self.now, interval_seconds=1200, max_items=1
        )
        self.assertEqual(summary["added"], 1)
        entry = state["content_delivery_queue"]["dkp-123"]
        self.assertEqual(entry["status"], "queued")
        self.assertIn("payload", entry)
        self.assertEqual(
            set(entry["platforms"]),
            set(PLATFORM_NAMES),
        )
        self.assertEqual(entry["platforms"]["telegram"]["status"], "pending")

    def test_legacy_media_retry_clock_is_recovered_from_actual_channel_send_times(self):
        actual_channel_send = self.now - timedelta(minutes=25)
        latest_channel_send = actual_channel_send + timedelta(seconds=1)
        state = {
            # Older partial-media retries incorrectly moved this into the future.
            "last_published_at": (self.now + timedelta(minutes=15)).isoformat(),
            "content_delivery_queue": {
                "dkp-partial": {
                    "status": "partial",
                    "platforms": {
                        "telegram": {"status": "sent", "updated_at": actual_channel_send.isoformat()},
                        "bale": {"status": "sent", "updated_at": latest_channel_send.isoformat()},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "pending"},
                    },
                }
            },
        }

        anchor = get_last_channel_published_at(state)
        self.assertEqual(anchor, latest_channel_send)
        self.assertEqual(state["last_channel_published_at"], latest_channel_send.isoformat())
        self.assertEqual(state["last_published_at"], latest_channel_send.isoformat())

        # The stale future retry time must not delay a fresh hand-off; only the
        # actual confirmed Telegram/Bale receipt plus the shared channel gap applies.
        summary = enqueue_selected_content(
            state, [self.item("dkp-fresh")], now=self.now,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=0,
        )
        self.assertEqual(summary["added"], 1)
        expected_slot = max(
            self.now,
            latest_channel_send + timedelta(
                seconds=channel_post_interval_seconds("product:1:dkp-fresh")
            ),
        )
        self.assertEqual(
            datetime.fromisoformat(state["content_delivery_queue"]["dkp-fresh"]["scheduled_at"]),
            expected_slot,
        )
        self.assertLess(
            datetime.fromisoformat(state["content_delivery_queue"]["dkp-fresh"]["scheduled_at"]),
            self.now + timedelta(minutes=15 + 47),
        )

    def test_partial_media_retry_does_not_advance_channel_publication_clock(self):
        from unittest.mock import patch
        import publisher

        actual_channel_send = self.now - timedelta(minutes=40)
        latest_channel_send = actual_channel_send + timedelta(seconds=1)
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-video-pending")], now=actual_channel_send,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=0,
        )
        entry = state["content_delivery_queue"]["dkp-video-pending"]
        entry["status"] = "partial"
        entry["next_attempt_at"] = (self.now - timedelta(minutes=1)).isoformat()
        entry["platforms"]["telegram"].update(
            status="sent", updated_at=actual_channel_send.isoformat(), attempts=1
        )
        entry["platforms"]["bale"].update(
            status="sent", updated_at=latest_channel_send.isoformat(), attempts=1
        )
        entry["platforms"]["youtube"]["status"] = "pending"
        entry["platforms"]["aparat"]["status"] = "pending"
        state["last_published_at"] = latest_channel_send.isoformat()
        state["last_channel_published_at"] = latest_channel_send.isoformat()

        with (
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher._save"),
            patch("publisher._now", return_value=self.now),
            patch("publisher._fresh_selected_item", return_value=(self.item("dkp-video-pending"), "")),
            patch("publisher.radar._fetch_image", return_value=b"image"),
            patch("publisher._process_photo_destination") as send_photo,
            patch("publisher._process_video_destinations"),
        ):
            publisher.publish_due_queue()

        self.assertEqual(state["last_published_at"], latest_channel_send.isoformat())
        self.assertEqual(state["last_channel_published_at"], latest_channel_send.isoformat())
        self.assertEqual(send_photo.call_count, len(PHOTO_PLATFORMS))
        # Because both channels were already sent, this retry must not reset either clock.

    def test_publisher_rejects_legacy_queued_supplement_before_any_delivery(self):
        entry = {
            "product_id": "dkp-8478740",
            "payload": {
                "product_id": "dkp-8478740",
                "product_url": "https://www.digikala.com/product/dkp-8478740/",
                "current_price": 79000,
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-8478740%2F",
                "current_demand_verified": True,
                "current_demand_score": 55,
                "demand_score": 55,
                "recent_review_growth_7d": 5,
                "demand_window_hours": 24,
                "demand_observed_at": self.now.isoformat(),
                "demand_signal_source": "digikala_recent_review_growth",
            },
        }
        with patch("publisher.radar.fetch_product_record", return_value={
            "title": "شربت ال آرژنین پلاس فیشر کیندر -200 میلی لیتر",
            "image_url": "https://example.invalid/product.jpg",
        }):
            fresh, reason = _fresh_selected_item(entry, self.now)

        self.assertIsNone(fresh)
        self.assertEqual(reason, "live_product_prohibited_title")

    def test_publisher_normalizes_legacy_discount_floors_to_any_real_markdown(self):
        from unittest.mock import patch

        product_id = "dkp-95045"
        product_url = f"https://www.digikala.com/product/{product_id}/"
        affiliate_url = (
            "https://aflo.ir/QekEYTRg?p="
            "https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95045%2F"
        )
        demand = {
            "current_demand_verified": True,
            "current_demand_score": 55,
            "demand_score": 55,
            "recent_review_growth_7d": 5,
            "demand_window_hours": 24,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        payload = {
            "product_id": product_id,
            "product_url": product_url,
            "title": "شارژر سریع دیواری مدل تست",
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "review_count": 1200,
            "affiliate_url": affiliate_url,
            "selection_discount_floor": 50,
            "deal_expires_at": "",
            **demand,
        }
        fresh_record = {
            "title": "شارژر سریع دیواری مدل تست",
            "image_url": "https://example.com/product.webp",
            "current_price": 500_000,
            "original_price": 1_000_000,
            "discount_percent": 50,
            "savings_toman": 500_000,
            "review_count": 1200,
            "availability": "in_stock",
            "deal_expires_at": "",
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 6,
            "market_price_checked_at": self.now.isoformat(),
        }

        def discount_gate(record, minimum_discount_percent=None, now=None):
            floor = 1 if minimum_discount_percent is None else minimum_discount_percent
            return (
                int(record.get("discount_percent") or 0) >= floor
                and int(record.get("savings_toman") or 0) > 0
            )

        patches = (
            patch("publisher.radar.fetch_product_record", return_value=dict(fresh_record)),
            patch("publisher.radar.is_prohibited_product_title", return_value=False),
            patch("publisher.radar.is_publishable_product_title", return_value=True),
            patch("publisher.radar._is_valid_affilio_tracking_url", return_value=True),
            patch("publisher.radar.score_product", side_effect=lambda item: item),
            patch(
                "publisher.radar.verify_live_page_price",
                return_value={"ok": True, "page_price": 500_000},
            ),
            patch("publisher.radar.is_discount_publish_eligible", side_effect=discount_gate),
            patch("publisher.radar.is_market_value_publish_eligible", return_value=True),
            patch("publisher.radar.has_publishable_expiry_or_open_offer", return_value=True),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as discount_check, patches[7], patches[8]:
            entry = {"product_id": product_id, "payload": dict(payload)}
            fresh, reason = _fresh_selected_item(entry, self.now)
            self.assertIsNotNone(fresh)
            self.assertEqual(reason, "")
            discount_check.assert_called_once()
            self.assertEqual(
                discount_check.call_args.kwargs["minimum_discount_percent"], 1
            )

            # Older queued selections without a stored floor are normalized too.
            discount_check.reset_mock()
            legacy_payload = dict(payload)
            legacy_payload.pop("selection_discount_floor")
            legacy_entry = {"product_id": product_id, "payload": legacy_payload}
            fresh, reason = _fresh_selected_item(legacy_entry, self.now)
            self.assertIsNotNone(fresh)
            self.assertEqual(reason, "")
            discount_check.assert_called_once()
            self.assertEqual(
                discount_check.call_args.kwargs["minimum_discount_percent"], 1
            )

    def test_publisher_accepts_any_real_discount_from_a_legacy_45_percent_queue_item(self):
        product_id = "dkp-95045"
        product_url = f"https://www.digikala.com/product/{product_id}/"
        affiliate_url = (
            "https://aflo.ir/QekEYTRg?p="
            "https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95045%2F"
        )
        demand = {
            "current_demand_verified": True,
            "current_demand_score": 55,
            "demand_score": 55,
            "recent_review_growth_7d": 5,
            "demand_window_hours": 24,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        payload = {
            "product_id": product_id,
            "product_url": product_url,
            "title": "شارژر سریع دیواری مدل تست",
            "current_price": 500_000,
            "original_price": 909_091,
            "discount_percent": 45,
            "savings_toman": 409_091,
            "review_count": 1200,
            "affiliate_url": affiliate_url,
            "selection_discount_floor": 45,
            "selection_discount_band": "45%–49%",
            "deal_expires_at": "",
            **demand,
        }
        fresh_record = {
            "title": "شارژر سریع دیواری مدل تست",
            "image_url": "https://example.com/product.webp",
            "current_price": 500_000,
            "original_price": 909_091,
            "discount_percent": 45,
            "savings_toman": 409_091,
            "review_count": 1200,
            "availability": "in_stock",
            "deal_expires_at": "",
            "market_status": "verified",
            "market_reference_kind": "seller_median",
            "market_price_advantage_pct": 6,
            "market_price_checked_at": self.now.isoformat(),
        }

        patches = (
            patch("publisher.radar.fetch_product_record", return_value=dict(fresh_record)),
            patch("publisher.radar.is_prohibited_product_title", return_value=False),
            patch("publisher.radar.is_publishable_product_title", return_value=True),
            patch("publisher.radar._is_valid_affilio_tracking_url", return_value=True),
            patch("publisher.radar.score_product", side_effect=lambda item: item),
            patch(
                "publisher.radar.verify_live_page_price",
                return_value={"ok": True, "page_price": 500_000},
            ),
            patch("publisher.radar.is_discount_publish_eligible", return_value=True),
            patch("publisher.radar.is_market_value_publish_eligible", return_value=True),
            patch("publisher.radar.has_publishable_expiry_or_open_offer", return_value=True),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            fresh, reason = _fresh_selected_item(
                {"product_id": product_id, "payload": payload}, self.now
            )

        self.assertIsNotNone(fresh)
        self.assertEqual(reason, "")
        self.assertEqual(fresh["selection_discount_floor"], 1)
        self.assertEqual(fresh["selection_discount_band"], "1%+")

    def test_publisher_rejects_old_queue_item_without_fresh_demand_evidence(self):
        entry = {
            "product_id": "dkp-95045",
            "payload": {
                "product_id": "dkp-95045",
                "product_url": "https://www.digikala.com/product/dkp-95045/",
                "selection_discount_floor": 44,
                "current_price": 500_000,
                "original_price": 520_000,
                "discount_percent": 4,
                "savings_toman": 20_000,
                "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-95045%2F",
            },
        }
        fresh, reason = _fresh_selected_item(entry, self.now)
        self.assertIsNone(fresh)
        self.assertEqual(reason, "selection_demand_evidence_missing_or_stale")

    def test_final_publisher_gate_requires_demand_but_allows_partial_delivery_resume(self):
        from unittest.mock import patch

        base = self.item("dkp-990101")
        product_url = base["product_url"]
        affiliate_url = base["affiliate_url"]

        def evaluate(payload, platforms=None):
            fresh_record = {
                "title": payload["title"],
                "image_url": payload["image_url"],
                "current_price": payload["current_price"],
                "original_price": payload["original_price"],
                "discount_percent": payload["discount_percent"],
                "savings_toman": payload["savings_toman"],
                "review_count": payload.get("review_count", 0),
                "availability": "in_stock",
                "deal_expires_at": "",
                "market_status": payload.get("market_status", ""),
                "market_reference_kind": payload.get("market_reference_kind", ""),
                "market_price_advantage_pct": payload.get("market_price_advantage_pct"),
                "market_price_checked_at": payload.get("market_price_checked_at", ""),
            }
            entry = {
                "product_id": payload["product_id"],
                "payload": payload,
                "platforms": platforms or {},
            }
            with (
                patch("publisher.radar.fetch_product_record", return_value=fresh_record),
                patch("publisher.radar.is_prohibited_product_title", return_value=False),
                patch("publisher.radar.is_publishable_product_title", return_value=True),
                patch("publisher.radar._is_valid_affilio_tracking_url", return_value=True),
                patch("publisher.radar.score_product", side_effect=lambda item: item),
                patch("publisher.radar.verify_live_page_price", return_value={"ok": True, "page_price": payload["current_price"]}),
                patch("publisher.radar.is_discount_publish_eligible", return_value=True),
                patch("publisher.radar.is_market_value_publish_eligible", return_value=True),
                patch("publisher.radar.has_publishable_expiry_or_open_offer", return_value=True),
            ):
                return _fresh_selected_item(entry, self.now)

        no_demand = {
            **base,
            "product_id": "dkp-990102",
            "product_url": "https://www.digikala.com/product/dkp-990102/",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-990102%2F",
            "current_demand_verified": False,
            "current_demand_score": 0,
            "demand_score": 0,
            "recent_review_growth_7d": 0,
            "demand_window_hours": 0,
            "demand_observed_at": "",
            "demand_signal_source": "",
            "publication_policy": "discount_first_catalog_v2",
            "market_status": "not_checked",
            "market_reference_kind": "",
            "market_price_checked_at": "",
        }
        fresh, reason = evaluate(no_demand)
        self.assertIsNone(fresh)
        self.assertEqual(reason, "selection_demand_evidence_missing_or_stale")

        weak_value = {
            **base,
            "product_id": "dkp-990103",
            "product_url": "https://www.digikala.com/product/dkp-990103/",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-990103%2F",
            "discount_percent": 10,
            "savings_toman": 10_000,
            "market_status": "not_checked",
            "market_reference_kind": "",
            "market_price_checked_at": "",
        }
        fresh, reason = evaluate({**weak_value, "publication_policy": "discount_first_catalog_v2"})
        self.assertIsNotNone(fresh)
        self.assertEqual(reason, "")

        # A partial delivery may finish already-started destinations even
        # after demand evidence ages out; this is not a new product selection.
        partial_retry = {
            **weak_value,
            "product_id": "dkp-990104",
            "product_url": "https://www.digikala.com/product/dkp-990104/",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-990104%2F",
            "current_demand_verified": False,
            "recent_review_growth_7d": 0,
            "demand_window_hours": 0,
            "demand_observed_at": "",
            "demand_signal_source": "",
            "discount_percent": 5,
        }
        fresh, reason = evaluate(
            partial_retry,
            {"telegram": {"status": "sent"}, "bale": {"status": "pending"}},
        )
        self.assertIsNotNone(fresh)
        self.assertEqual(reason, "")

    def test_only_a_fresh_active_unpublished_selection_reserves_next_channel_slot(self):
        last_channel_send = self.now - timedelta(minutes=30)
        failed_selection = self.now - timedelta(minutes=3)
        state = {
            "content_delivery_queue": {
                "dkp-failed-image": {
                    "status": "queued",
                    "selected_at": failed_selection.isoformat(),
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                        "youtube": {"status": "pending"},
                        "aparat": {"status": "pending"},
                    },
                }
            }
        }

        self.assertTrue(has_fresh_unpublished_selection(state, now=self.now, stale_after_minutes=8))
        self.assertEqual(
            selection_cadence_anchor(
                failed_selection, last_channel_send,
                has_fresh_unpublished_selection=True,
            ),
            failed_selection,
        )

        # A previously failed selection may already have been marked stale by an older
        # workflow revision. The next run still sees no fresh active selection and must
        # use the real channel clock rather than the stale last-selection timestamp.
        state["content_delivery_queue"].pop("dkp-failed-image")
        state["content_delivery_history"] = [{
            "product_id": "dkp-failed-image",
            "status": "stale_selection",
            "selected_at": failed_selection.isoformat(),
            "platforms": {
                "telegram": {"status": "pending"},
                "bale": {"status": "pending"},
            },
        }]
        self.assertFalse(has_fresh_unpublished_selection(state, now=self.now, stale_after_minutes=8))
        self.assertEqual(
            selection_cadence_anchor(
                failed_selection, last_channel_send,
                has_fresh_unpublished_selection=False,
            ),
            last_channel_send,
        )

    def test_queue_enforces_spacing_and_dedupes_active_content(self):
        state = {}
        items = [self.item("dkp-1"), self.item("dkp-2")]
        enqueue_selected_content(state, items, now=self.now, interval_seconds=1200, max_items=2)
        queue = state["content_delivery_queue"]
        first = queue["dkp-1"]
        second = queue["dkp-2"]
        actual_gap = (
            datetime.fromisoformat(second["scheduled_at"])
            - datetime.fromisoformat(first["scheduled_at"])
        )
        self.assertEqual(
            actual_gap,
            timedelta(seconds=channel_post_interval_seconds(
                f"product:{first['sequence_number']}:dkp-1"
            )),
        )
        self.assertGreaterEqual(actual_gap.total_seconds(), MIN_CHANNEL_POST_INTERVAL_SECONDS)
        self.assertLessEqual(actual_gap.total_seconds(), MAX_CHANNEL_POST_INTERVAL_SECONDS)
        again = enqueue_selected_content(state, items, now=self.now, interval_seconds=1200, max_items=2)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["queue_size"], 2)

    def test_enqueue_rejects_incomplete_product_title(self):
        state = {}
        item = self.item()
        item["title"] = "هندزفری بلوتوثی مدل"

        summary = enqueue_selected_content(state, [item], now=self.now)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(state["content_delivery_queue"], {})

    def test_new_selection_does_not_stack_behind_partial_retry(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-old-partial")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        old = state["content_delivery_queue"]["dkp-old-partial"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["bale"]["status"] = "failed"
        next_slot = self.now + timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS)
        old["scheduled_at"] = next_slot.isoformat()
        old["next_attempt_at"] = next_slot.isoformat()
        state["last_published_at"] = self.now.isoformat()

        summary = enqueue_selected_content(
            state, [self.item("dkp-fresh")], now=self.now + timedelta(minutes=5),
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(summary["added"], 1)
        fresh = state["content_delivery_queue"]["dkp-fresh"]
        fresh_at = datetime.fromisoformat(fresh["scheduled_at"])
        self.assertEqual(
            fresh_at,
            self.now + timedelta(
                seconds=channel_post_interval_seconds(
                    f"product:{fresh['sequence_number']}:dkp-fresh"
                )
            ),
        )

    def test_retry_queue_is_bounded_and_prefers_fresh_selections(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-1")], now=self.now,
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        enqueue_selected_content(
            state, [self.item("dkp-2")], now=self.now + timedelta(minutes=1),
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        result = enqueue_selected_content(
            state, [self.item("dkp-3")], now=self.now + timedelta(minutes=2),
            interval_seconds=1200, max_items=1, max_active_items=2,
        )
        self.assertEqual(result["queue_size"], 2)
        self.assertEqual(set(state["content_delivery_queue"]), {"dkp-2", "dkp-3"})
        self.assertEqual(state["content_delivery_history"][0]["product_id"], "dkp-1")
        self.assertEqual(state["content_delivery_history"][0]["status"], "cancelled")
        self.assertIn("bounded_retry_queue_eviction", state["content_delivery_history"][0]["last_detail"])

    def test_queue_rejects_past_minimum_runway(self):
        state = {}
        deadline = self.now + timedelta(minutes=45)
        result = enqueue_selected_content(
            state, [self.item(deadline=deadline)], now=self.now,
            interval_seconds=1200, max_items=1, minimum_runway_minutes=60,
        )
        self.assertEqual(result["added"], 0)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])

    def test_active_publication_cannot_be_queued_again(self):
        state = {
            "published": {
                "dkp-123": {
                    "telegram_message_id": 55,
                    "expiry_status": "tracked",
                }
            }
        }
        result = enqueue_selected_content(state, [self.item()], now=self.now)
        self.assertEqual(result["added"], 0)

    def test_due_items_obey_schedule_and_retry_time(self):
        state = {}
        enqueue_selected_content(state, [self.item("dkp-1"), self.item("dkp-2")],
                                 now=self.now, interval_seconds=1200, max_items=2)
        due_now = due_content(state, now=self.now, limit=5)
        self.assertEqual([pid for pid, _entry in due_now], ["dkp-1"])
        second_slot = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-2"]["scheduled_at"]
        )
        later = due_content(state, now=second_slot, limit=5)
        self.assertEqual({pid for pid, _entry in later}, {"dkp-1", "dkp-2"})


    def test_due_queue_keeps_selector_order_and_ignores_demand_scores(self):
        state = {}
        enqueue_selected_content(
            state,
            [self.item("dkp-100", demand=0), self.item("dkp-200", demand=999)],
            now=self.now,
            interval_seconds=1200,
            max_items=2,
        )
        # Force an exact schedule tie; stable insertion order is the original
        # selector order and must not be replaced by a demand/popularity score.
        same_slot = self.now.isoformat()
        state["content_delivery_queue"]["dkp-100"]["scheduled_at"] = same_slot
        state["content_delivery_queue"]["dkp-200"]["scheduled_at"] = same_slot
        state["content_delivery_queue"]["dkp-100"]["next_attempt_at"] = same_slot
        state["content_delivery_queue"]["dkp-200"]["next_attempt_at"] = same_slot
        due = due_content(state, now=self.now, limit=2)
        self.assertEqual([pid for pid, _entry in due], ["dkp-100", "dkp-200"])

    def test_future_product_slot_is_retained_by_live_scan(self):
        last_product = self.now - timedelta(minutes=5)
        state = {"last_product_channel_published_at": last_product.isoformat()}
        enqueue_selected_content(
            state, [self.item("dkp-future")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        future = state["content_delivery_queue"]["dkp-future"]
        expected_slot = max(
            self.now,
            last_product + timedelta(
                seconds=channel_post_interval_seconds("product:1:dkp-future")
            ),
        )
        self.assertEqual(datetime.fromisoformat(future["scheduled_at"]), expected_slot)
        self.assertGreater(datetime.fromisoformat(future["scheduled_at"]), self.now)

        replaced = refresh_unpublished_selections(state, now=self.now)
        self.assertEqual(replaced, 0)
        self.assertIn("dkp-future", state["content_delivery_queue"])
        self.assertEqual(state.get("content_delivery_history"), [])

    def test_partial_delivery_does_not_prevent_fresh_content_selection(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-video-pending")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        old = state["content_delivery_queue"]["dkp-video-pending"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["youtube"]["status"] = "pending"
        state["last_published_at"] = self.now.isoformat()

        next_time = self.now + timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS)
        summary = enqueue_selected_content(
            state, [self.item("dkp-new")], now=next_time,
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(summary["added"], 1)
        expected_slot = max(
            next_time,
            self.now + timedelta(seconds=channel_post_interval_seconds("product:2:dkp-new")),
        )
        self.assertEqual(
            datetime.fromisoformat(
                state["content_delivery_queue"]["dkp-new"]["scheduled_at"]
            ),
            expected_slot,
        )
        self.assertIn("dkp-video-pending", state["content_delivery_queue"])

    def test_due_unpublished_selection_is_visible_until_a_destination_succeeds(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-pending")], now=self.now,
            interval_seconds=1200, max_items=1,
        )
        self.assertEqual(
            due_unpublished_selection(state, now=self.now), "dkp-pending"
        )
        state["content_delivery_queue"]["dkp-pending"]["platforms"]["telegram"]["status"] = "sent"
        self.assertIsNone(due_unpublished_selection(state, now=self.now))


    def test_fresh_unpublished_content_outranks_old_partial_delivery(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-old-partial", demand=90)],
            now=self.now - timedelta(minutes=30), interval_seconds=1200,
        )
        old = state["content_delivery_queue"]["dkp-old-partial"]
        old["status"] = "partial"
        old["platforms"]["telegram"]["status"] = "sent"
        old["platforms"]["youtube"]["status"] = "pending"
        enqueue_selected_content(
            state, [self.item("dkp-fresh", demand=45)],
            now=self.now, interval_seconds=1200,
        )

        due = due_content(state, now=self.now, limit=1)
        self.assertEqual([pid for pid, _entry in due], ["dkp-fresh"])


    def test_publisher_blocks_stale_queued_copy_when_current_publication_is_active(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-123")],
            now=self.now - timedelta(minutes=10), interval_seconds=1200, max_items=1,
        )
        state["published"] = {
            "dkp-123": {
                "telegram_message_id": 55,
                "expiry_status": "tracked",
                "distribution_queue_id": "dkp-123:previous-selection",
            }
        }
        with (
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher._save"),
            patch("publisher._fresh_selected_item") as revalidate,
        ):
            self.assertEqual(publish_due_queue(), 0)

        revalidate.assert_not_called()
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["published"]["dkp-123"]["telegram_message_id"], 55)
        self.assertEqual(
            state["content_delivery_history"][0]["last_detail"],
            "active_publication_exists",
        )

    def test_fallback_filter_requires_demand_and_normalizes_legacy_discount_tiers(self):
        low_discount = self.item("dkp-99008", price=110_000, demand=95)
        low_discount.update({
            "current_price": 110_000,
            "original_price": 200_000,
            "discount_percent": 45,
            "savings_toman": 90_000,
            "selection_discount_floor": 45,
        })
        no_current_demand = self.item("dkp-99009", demand=95)
        no_current_demand["current_demand_verified"] = False
        valid = self.item("dkp-99010", demand=45)
        unsupported_floor = self.item("dkp-99011", price=132_000, demand=99)
        unsupported_floor.update({
            "current_price": 132_000,
            "original_price": 200_000,
            "discount_percent": 34,
            "savings_toman": 68_000,
            "selection_discount_floor": 35,
        })

        filtered = _eligible_fallback_candidates(
            [low_discount, no_current_demand, valid, unsupported_floor], self.now
        )

        self.assertEqual(
            {item["product_id"] for item in filtered},
            {"dkp-99008", "dkp-99010", "dkp-99011"},
        )
        self.assertTrue(all(item["selection_discount_floor"] == 1 for item in filtered))

    def test_stale_primary_promotes_next_backup_as_immediately_due(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-99001")], now=self.now, interval_seconds=1200,
        )
        primary = state["content_delivery_queue"]["dkp-99001"]
        primary["fallback_candidates"] = [
            {
                **self.item("dkp-99002", price=110_000, demand=45),
                "discount_percent": 45,
                "selection_discount_floor": 45,
                "selection_discount_band": "45%–49%",
            },
            {
                **self.item("dkp-99003", demand=40),
                "discount_percent": 40,
                "selection_discount_floor": 40,
                "selection_discount_band": "40%–44%",
            },
        ]
        fallback_candidates = list(primary["fallback_candidates"])

        finish_queue_item(
            state, "dkp-99001", "stale_selection",
            now=self.now, detail="live_discount_no_longer_eligible",
        )
        promoted = promote_fallback_selection(
            state, fallback_candidates, now=self.now,
            reason="live_discount_no_longer_eligible",
        )

        self.assertEqual(promoted, "dkp-99002")
        due = due_content(state, now=self.now, limit=1)
        self.assertEqual([pid for pid, _entry in due], ["dkp-99002"])
        self.assertEqual(
            [item["product_id"] for item in due[0][1]["fallback_candidates"]],
            ["dkp-99003"],
        )
        self.assertEqual(
            due[0][1]["fallback_promoted_after"],
            "live_discount_no_longer_eligible",
        )


    def test_publisher_uses_backup_in_same_run_after_primary_fails_live_check(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-99001")], now=self.now, interval_seconds=1200,
        )
        fallback_candidate = {
            **self.item("dkp-99002", price=110_000, demand=45),
            "current_price": 110_000,
            "original_price": 200_000,
            "discount_percent": 45,
            "savings_toman": 90_000,
            "selection_discount_floor": 45,
            "selection_discount_band": "45%–49%",
        }
        state["content_delivery_queue"]["dkp-99001"]["fallback_candidates"] = [
            fallback_candidate
        ]
        backup = {
            **fallback_candidate,
            "image_url": "https://example.com/backup.jpg",
            "merchant": "دیجی‌کالا",
        }

        def fake_photo(state_arg, entry, record, item, image_bytes, destination, now, *, persist=True):
            entry["platforms"][destination]["status"] = "sent"
            entry["platforms"][destination]["updated_at"] = now.isoformat()
            record.setdefault("delivery_status", {})[destination] = "sent"
            record[f"{destination}_message_id"] = 100 + len(destination)

        def fake_video(state_arg, entry, record, now):
            for destination in ("youtube", "aparat"):
                entry["platforms"][destination]["status"] = "not_connected"
                record.setdefault("delivery_status", {})[destination] = "not_connected"

        with (
            patch("publisher._now", return_value=self.now),
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher.radar.publication_catalog_context", return_value={"mode": "initial_warmup", "snapshot": None}),
            patch("publisher._save"),
            patch(
                "publisher._fresh_selected_item",
                side_effect=[
                    (None, "live_discount_no_longer_eligible"),
                    (backup, ""),
                ],
            ) as revalidate,
            patch("publisher.radar._fetch_image", return_value=b"image"),
            patch("publisher._process_photo_destination", side_effect=fake_photo),
            patch("publisher._process_video_destinations", side_effect=fake_video),
        ):
            self.assertEqual(publish_due_queue(), 0)

        self.assertEqual(revalidate.call_count, 2)
        self.assertNotIn("dkp-99001", state["content_delivery_queue"])
        self.assertNotIn("dkp-99002", state["content_delivery_queue"])
        self.assertEqual(
            [item["product_id"] for item in state["content_delivery_history"]],
            ["dkp-99001", "dkp-99002"],
        )
        self.assertEqual(state["content_delivery_history"][0]["status"], "stale_selection")
        self.assertEqual(state["content_delivery_history"][1]["status"], "published")
        self.assertIn("dkp-99001", state["selection_rejections"])
        self.assertIn("dkp-99002", state["published"])

    
    def test_already_selected_product_revalidates_live_when_catalog_snapshot_is_unavailable(self):
        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-99004")], now=self.now, interval_seconds=1200,
        )
        with (
            patch("publisher._now", return_value=self.now),
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher.radar.publication_catalog_context", return_value={"mode": "blocked", "snapshot": None}),
            patch("publisher._save"),
            patch("publisher.radar.mark_selection_candidate_rejected"),
            patch("publisher._fresh_selected_item", return_value=(None, "live_stock_not_confirmed")) as revalidate,
            patch("publisher._process_photo_destination") as send_photo,
        ):
            self.assertEqual(publish_due_queue(), 0)

        revalidate.assert_called_once()
        self.assertFalse(revalidate.call_args.kwargs["require_catalog_membership"])
        send_photo.assert_not_called()
        self.assertNotIn("dkp-99004", state["content_delivery_queue"])
        self.assertNotIn("dkp-99004", state.get("pending_queue", {}))


    def test_rubika_failure_is_optional_after_telegram_and_bale_delivery(self):
        import publisher

        state = {}
        enqueue_selected_content(
            state, [self.item("dkp-rubika-retry")], now=self.now,
            interval_seconds=1200, max_items=1,
        )

        def fake_photo(state_arg, entry, record, item, image_bytes, destination, now, *, persist=True):
            target = entry["platforms"][destination]
            if destination in CORE_PHOTO_PLATFORMS:
                target.update(status="sent", attempts=1, updated_at=now.isoformat())
                record.setdefault("delivery_status", {})[destination] = "sent"
                record[f"{destination}_message_id"] = 100 + len(destination)
            elif destination == "rubika":
                target.update(
                    status="failed", attempts=1,
                    next_attempt_at=(now + timedelta(minutes=30)).isoformat(),
                )
                record.setdefault("delivery_status", {})[destination] = "failed"
            else:
                target.update(status="not_connected", attempts=0)
                record.setdefault("delivery_status", {})[destination] = "not_connected"

        with (
            patch("publisher._now", return_value=self.now),
            patch("publisher.radar.load_state", return_value=state),
            patch("publisher.radar.publication_catalog_context", return_value={"mode": "initial_warmup", "snapshot": None}),
            patch("publisher._save"),
            patch("publisher._fresh_selected_item", return_value=(self.item("dkp-rubika-retry"), "")),
            patch("publisher.radar._fetch_image", return_value=b"image"),
            patch("publisher._process_photo_destination", side_effect=fake_photo),
            patch("publisher._process_video_destinations"),
        ):
            self.assertEqual(publisher.publish_due_queue(), 0)

        entry = state["content_delivery_queue"]["dkp-rubika-retry"]
        self.assertEqual(entry["status"], "partial")
        self.assertIn("optional_unresolved=rubika", entry["last_detail"])
        self.assertEqual(entry["platforms"]["telegram"]["status"], "sent")
        self.assertEqual(entry["platforms"]["bale"]["status"], "sent")
        self.assertEqual(entry["platforms"]["rubika"]["status"], "failed")
        self.assertNotIn("dkp-rubika-retry", state.get("pending_queue", {}))
        self.assertEqual(state["last_channel_published_at"], self.now.isoformat())

        # The partial optional retry remains bounded but does not stop a new selection.
        fresh = enqueue_selected_content(
            state, [self.item("dkp-after-rubika")],
            now=self.now + timedelta(minutes=1), interval_seconds=1200,
            max_items=1,
        )
        self.assertEqual(fresh["added"], 1)
        fresh_slot = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-after-rubika"]["scheduled_at"]
        )
        self.assertGreaterEqual(
            fresh_slot - self.now,
            timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS),
        )
        due = due_content(state, now=fresh_slot, limit=1)
        self.assertEqual([product_id for product_id, _entry in due], ["dkp-after-rubika"])

    def test_terminal_queue_item_moves_to_bounded_history(self):
        state = {}
        enqueue_selected_content(state, [self.item()], now=self.now)
        finish_queue_item(state, "dkp-123", "published", now=self.now)
        self.assertNotIn("dkp-123", state["content_delivery_queue"])
        self.assertEqual(state["content_delivery_history"][0]["status"], "published")


    def test_product_publication_clock_is_independent_from_editorial_posts(self):
        product_at = self.now - timedelta(hours=3)
        editorial_at = self.now - timedelta(minutes=12)
        state = {
            "last_product_channel_published_at": product_at.isoformat(),
            "last_channel_published_at": editorial_at.isoformat(),
            "editorial_delivery_history": [{
                "content_id": "editorial:buying-guide",
                "published_at": editorial_at.isoformat(),
                "destinations": {"telegram": {"status": "sent"}},
            }],
        }
        self.assertEqual(get_last_product_channel_published_at(state), product_at)

    def test_legacy_product_clock_migrates_from_product_receipt_not_editorial_clock(self):
        product_at = self.now - timedelta(hours=4)
        editorial_at = self.now - timedelta(minutes=8)
        state = {
            "last_channel_published_at": editorial_at.isoformat(),
            "editorial_delivery_history": [{
                "content_id": "editorial:legacy-guide",
                "published_at": editorial_at.isoformat(),
                "destinations": {"bale": {"status": "sent"}},
            }],
            "published": {
                "dkp-123456": {
                    "ts": product_at.timestamp(),
                    "delivery_status": {"telegram": "sent", "bale": "sent"},
                }
            },
        }
        self.assertEqual(get_last_product_channel_published_at(state), product_at)
        self.assertEqual(state["last_product_channel_published_at"], product_at.isoformat())

    def test_publisher_never_batches_multiple_public_content_items(self):
        self.assertEqual(MAX_ITEMS_PER_RUN, 1)
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "offerchin-publisher.yml"
        )
        self.assertNotIn("AFFILIO_PUBLISHER_BATCH_SIZE", workflow.read_text(encoding="utf-8"))

    def test_delivery_reflow_evenly_redistributes_pending_products_to_next_scan(self):
        next_scan = self.now + timedelta(minutes=10)
        state = {
            "last_product_channel_published_at": self.now.isoformat(),
            "product_publication_plan_anchor_at": (self.now - timedelta(minutes=2)).isoformat(),
            "product_publication_plan_anchor_kind": "cycle_start",
            "product_publication_cadence": {
                "catalog_cycle_id": "cycle-2026-10-25",
                "last_clean_cycle_completed_at": (self.now - timedelta(hours=8)).isoformat(),
                "current_cycle_started_at": (self.now - timedelta(minutes=5)).isoformat(),
                "estimated_next_clean_scan_at": next_scan.isoformat(),
                "candidate_count": 3,
                "planned_product_slots": 3,
                "interval_seconds": 67.0,
                "daily_post_limit": 72,
            },
            "content_delivery_queue": {
                "dkp-already-sent": {
                    "content_type": "product",
                    "status": "partial",
                    "sequence_number": 1,
                    "platforms": {
                        "telegram": {"status": "sent"},
                        "bale": {"status": "sent"},
                    },
                },
                "dkp-next-a": {
                    "content_type": "product",
                    "status": "queued",
                    "sequence_number": 2,
                    "scheduled_at": (self.now + timedelta(seconds=2)).isoformat(),
                    "next_attempt_at": (self.now + timedelta(seconds=2)).isoformat(),
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                    },
                },
                "dkp-next-b": {
                    "content_type": "product",
                    "status": "queued",
                    "sequence_number": 3,
                    "scheduled_at": (self.now + timedelta(seconds=3)).isoformat(),
                    "next_attempt_at": (self.now + timedelta(seconds=3)).isoformat(),
                    "platforms": {
                        "telegram": {"status": "pending"},
                        "bale": {"status": "pending"},
                    },
                },
            },
        }
        result = reflow_product_queue_after_delivery(state, now=self.now)
        self.assertEqual(result["pending_products"], 2)
        self.assertEqual(result["scheduled"], 2)
        self.assertGreaterEqual(result["interval_seconds"], MIN_CHANNEL_POST_INTERVAL_SECONDS)
        first = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-next-a"]["scheduled_at"]
        )
        second = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-next-b"]["scheduled_at"]
        )
        first_gap = (first - self.now).total_seconds()
        second_gap = (second - first).total_seconds()
        self.assertEqual(
            first_gap,
            channel_post_interval_seconds("product:2:dkp-next-a"),
        )
        self.assertEqual(
            second_gap,
            channel_post_interval_seconds("product:3:dkp-next-b"),
        )
        for gap in (first_gap, second_gap):
            self.assertGreaterEqual(gap, MIN_CHANNEL_POST_INTERVAL_SECONDS)
            self.assertLessEqual(gap, MAX_CHANNEL_POST_INTERVAL_SECONDS)

    def test_due_editorial_midpoint_precedes_later_product_slot_even_with_higher_sequence(self):
        editorial_at = self.now - timedelta(seconds=40)
        product_at = self.now - timedelta(seconds=5)
        product = {
            "content_type": "product",
            "status": "queued",
            "sequence_number": 4,
            "scheduled_at": product_at.isoformat(),
            "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
        }
        editorial = {
            "content_id": "editorial:midpoint",
            "content_type": "editorial",
            "status": "queued",
            "sequence_number": 100,
            "scheduled_at": editorial_at.isoformat(),
            "next_attempt_at": editorial_at.isoformat(),
            "related_product_id": "dkp-related",
        }
        state = {
            "content_delivery_queue": {"dkp-related": product},
            "editorial_delivery_queue": {"editorial:midpoint": editorial},
        }
        selected = _due_editorial_precedes_product(
            state, self.now, [("dkp-related", product)]
        )
        self.assertIs(selected, editorial)

    def test_editorial_photo_retry_never_preempts_its_related_due_product(self):
        editorial_at = self.now - timedelta(seconds=40)
        product_at = self.now - timedelta(seconds=5)
        product = {
            "content_type": "product",
            "status": "queued",
            "scheduled_at": product_at.isoformat(),
            "platforms": {
                "telegram": {"status": "pending"},
                "bale": {"status": "pending"},
            },
        }
        editorial = {
            "content_id": "editorial:midpoint-retry",
            "content_type": "editorial",
            "status": "partial",
            "scheduled_at": editorial_at.isoformat(),
            "next_attempt_at": editorial_at.isoformat(),
            "related_product_id": "dkp-related",
            "platforms": {
                "telegram": {"status": "sent", "attempts": 1},
                "bale": {"status": "pending", "attempts": 0},
                "youtube": {"status": "pending", "attempts": 0},
            },
        }
        state = {
            "content_delivery_queue": {"dkp-related": product},
            "editorial_delivery_queue": {"editorial:midpoint-retry": editorial},
        }
        self.assertIsNone(
            _due_editorial_precedes_product(state, self.now, [("dkp-related", product)])
        )

        # A render failure before any network send must also consume the one-time slot.
        editorial["platforms"] = {}
        editorial["photo_slot_attempted_at"] = editorial_at.isoformat()
        self.assertIsNone(
            _due_editorial_precedes_product(state, self.now, [("dkp-related", product)])
        )

    def test_due_editorial_does_not_precede_earlier_product_or_repeat_after_product_sent(self):
        earlier_product_at = self.now - timedelta(seconds=50)
        editorial_at = self.now - timedelta(seconds=30)
        product = {
            "content_type": "product",
            "status": "queued",
            "scheduled_at": earlier_product_at.isoformat(),
            "platforms": {"telegram": {"status": "pending"}, "bale": {"status": "pending"}},
        }
        editorial = {
            "content_id": "editorial:midpoint",
            "status": "queued",
            "scheduled_at": editorial_at.isoformat(),
            "next_attempt_at": editorial_at.isoformat(),
            "related_product_id": "dkp-related",
        }
        state = {
            "content_delivery_queue": {"dkp-related": product},
            "editorial_delivery_queue": {"editorial:midpoint": editorial},
        }
        self.assertIsNone(
            _due_editorial_precedes_product(state, self.now, [("dkp-related", product)])
        )
        product["platforms"]["telegram"]["status"] = "sent"
        self.assertIsNone(
            _due_editorial_precedes_product(state, self.now, [])
        )

    def test_product_cadence_spreads_candidates_over_the_next_clean_scan_window(self):
        clean_started = self.now - timedelta(hours=42)
        clean_completed = self.now - timedelta(hours=8)
        current_scan_started = self.now - timedelta(minutes=10)
        cycle_seconds = int((clean_completed - clean_started).total_seconds())
        status = {
            "last_clean_cycle_started_at": clean_started.isoformat(),
            "last_clean_cycle_completed_at": clean_completed.isoformat(),
            "current_cycle_started_at": current_scan_started.isoformat(),
            "last_cycle_status": "in_progress",
        }

        sparse_state = {}
        sparse = calculate_product_publication_cadence(
            sparse_state, status, 5, now=self.now, max_daily_posts=72
        )
        dense = calculate_product_publication_cadence(
            {}, status, 60, now=self.now, max_daily_posts=72
        )
        self.assertEqual(sparse["estimated_clean_cycle_seconds"], cycle_seconds)
        self.assertLess(dense["interval_seconds"], sparse["interval_seconds"])
        self.assertGreater(dense["interval_seconds"], 0)
        self.assertGreater(sparse["interval_seconds"], 0)
        self.assertEqual(sparse["interval_seconds"], 57 * 60)
        self.assertEqual(sparse["maximum_product_interval_seconds"], 57 * 60)
        self.assertTrue(sparse["first_slot_due_now"])
        expected_scan = current_scan_started + timedelta(seconds=cycle_seconds)
        self.assertEqual(
            sparse["estimated_next_clean_scan_at"],
            expected_scan.isoformat(),
        )
        self.assertEqual(
            sparse_state["product_publication_interval_seconds"],
            sparse["interval_seconds"],
        )

    def test_product_cadence_has_no_default_interval_when_no_product_or_scan_eta_exists(self):
        result = calculate_product_publication_cadence(
            {}, {}, 0, now=self.now, max_daily_posts=72
        )
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["planned_product_slots"], 0)
        self.assertEqual(result["interval_seconds"], 0)


    def test_expired_scan_eta_uses_provisional_57_minute_product_window(self):
        status = {
            "estimated_next_clean_scan_at": (self.now - timedelta(minutes=1)).isoformat(),
        }
        result = calculate_product_publication_cadence(
            {}, status, 3, now=self.now, max_daily_posts=72
        )
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["planned_product_slots"], 3)
        self.assertTrue(result["scan_eta_is_provisional"])
        self.assertEqual(result["estimated_next_clean_scan_at"], "")
        self.assertEqual(result["interval_seconds"], 57 * 60)
        self.assertTrue(result["first_slot_due_now"])

    def test_missing_scan_eta_uses_provisional_57_minute_product_window(self):
        result = calculate_product_publication_cadence(
            {}, {}, 2, now=self.now, max_daily_posts=72
        )
        self.assertTrue(result["scan_eta_is_provisional"])
        self.assertEqual(result["estimated_next_clean_scan_at"], "")
        self.assertEqual(result["interval_seconds"], 57 * 60)
        self.assertTrue(result["first_slot_due_now"])

    def test_product_cadence_is_not_capped_at_six_hours_for_sparse_cycles(self):
        clean_started = self.now - timedelta(hours=50)
        clean_completed = self.now - timedelta(hours=8)
        current_scan_started = self.now - timedelta(minutes=5)
        status = {
            "last_clean_cycle_started_at": clean_started.isoformat(),
            "last_clean_cycle_completed_at": clean_completed.isoformat(),
            "current_cycle_started_at": current_scan_started.isoformat(),
            "last_cycle_status": "in_progress",
        }
        result = calculate_product_publication_cadence(
            {}, status, 2, now=self.now, max_daily_posts=72
        )
        self.assertEqual(result["interval_seconds"], 57 * 60)
        self.assertEqual(result["maximum_product_interval_seconds"], 57 * 60)
        self.assertEqual(result["planned_product_slots"], 2)
        self.assertTrue(result["first_slot_due_now"])

    def test_variable_channel_gap_is_stable_and_never_round(self):
        first = channel_post_interval_seconds("product:1:dkp-a")
        self.assertEqual(first, channel_post_interval_seconds("product:1:dkp-a"))
        self.assertGreaterEqual(first, MIN_CHANNEL_POST_INTERVAL_SECONDS)
        self.assertLessEqual(first, MAX_CHANNEL_POST_INTERVAL_SECONDS)
        self.assertEqual(first % 60, 0)

    def test_product_reflow_keeps_reserved_editorial_before_related_product(self):
        editorial_at = self.now + timedelta(minutes=35)
        state = {
            "product_publication_plan_anchor_at": self.now.isoformat(),
            "product_publication_plan_anchor_kind": "last_channel",
            "content_delivery_queue": {
                "dkp-after-editorial": {
                    "content_type": "product",
                    "status": "queued",
                    "sequence_number": 8,
                    "scheduled_at": (self.now + timedelta(minutes=40)).isoformat(),
                    "next_attempt_at": (self.now + timedelta(minutes=40)).isoformat(),
                    "platforms": {},
                },
                "dkp-later": {
                    "content_type": "product",
                    "status": "queued",
                    "sequence_number": 9,
                    "scheduled_at": (self.now + timedelta(minutes=90)).isoformat(),
                    "next_attempt_at": (self.now + timedelta(minutes=90)).isoformat(),
                    "platforms": {},
                },
            },
            "editorial_delivery_queue": {
                "editorial:bridge": {
                    "content_id": "editorial:bridge",
                    "content_type": "editorial",
                    "status": "queued",
                    "related_product_id": "dkp-after-editorial",
                    "scheduled_at": editorial_at.isoformat(),
                }
            },
            "product_publication_cadence": {
                "interval_seconds": 57 * 60,
                "estimated_next_clean_scan_at": (self.now + timedelta(hours=3)).isoformat(),
                "catalog_cycle_id": "cycle",
                "first_slot_due_now": False,
            },
        }
        result = reschedule_product_queue_evenly(
            state, state["product_publication_cadence"], now=self.now
        )
        after_editorial = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-after-editorial"]["scheduled_at"]
        )
        later = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-later"]["scheduled_at"]
        )
        self.assertGreaterEqual(after_editorial, editorial_at + timedelta(
            seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS
        ))
        self.assertGreaterEqual(
            later - after_editorial, timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS)
        )
        self.assertEqual(result["scheduled"], 2)

    def test_recent_editorial_receipt_blocks_overdue_product_first_slot(self):
        last_product = self.now - timedelta(hours=2)
        last_editorial = self.now - timedelta(minutes=5)
        product_id = "dkp-after-recent-editorial"
        state = {
            "last_product_channel_published_at": last_product.isoformat(),
            "last_channel_published_at": last_editorial.isoformat(),
            "product_publication_plan_anchor_at": last_product.isoformat(),
            "product_publication_plan_anchor_kind": "cycle_start_after_max_gap",
            "content_delivery_queue": {
                product_id: {
                    "content_type": "product",
                    "status": "queued",
                    "sequence_number": 9,
                    "platforms": {},
                }
            },
        }
        cadence = {
            "interval_seconds": 57 * 60,
            "first_slot_due_now": True,
            "catalog_cycle_id": "cycle",
        }
        result = reschedule_product_queue_evenly(state, cadence, now=self.now)
        scheduled = datetime.fromisoformat(
            state["content_delivery_queue"][product_id]["scheduled_at"]
        )
        expected = last_editorial + timedelta(
            seconds=channel_post_interval_seconds(f"product:9:{product_id}")
        )
        self.assertEqual(scheduled, expected)
        self.assertGreaterEqual(
            scheduled - last_editorial,
            timedelta(seconds=MIN_CHANNEL_POST_INTERVAL_SECONDS),
        )
        self.assertEqual(result["scheduled"], 1)

    def test_product_plan_anchor_ignores_editorial_publication_clock(self):
        editorial_at = self.now - timedelta(minutes=2)
        state = {
            "last_channel_published_at": editorial_at.isoformat(),
            "editorial_delivery_history": [{
                "content_id": "editorial:test-guide",
                "published_at": editorial_at.isoformat(),
                "destinations": {"telegram": {"status": "sent"}},
            }],
        }
        result = calculate_product_publication_cadence(
            state, {}, 3, now=self.now, max_daily_posts=72
        )
        self.assertEqual(result["plan_anchor_kind"], "cycle_start")
        self.assertEqual(result["plan_anchor_at"], self.now.isoformat())

    def test_new_cycle_with_product_older_than_57_minutes_makes_next_slot_due_now(self):
        clean_started = self.now - timedelta(hours=42)
        clean_completed = self.now - timedelta(hours=8)
        current_scan_started = self.now - timedelta(hours=6)
        last_product = self.now - timedelta(hours=4)
        cycle_seconds = int((clean_completed - clean_started).total_seconds())
        status = {
            "last_clean_cycle_started_at": clean_started.isoformat(),
            "last_clean_cycle_completed_at": clean_completed.isoformat(),
            "current_cycle_started_at": current_scan_started.isoformat(),
            "last_cycle_status": "complete",
        }
        state = {
            "last_product_channel_published_at": last_product.isoformat(),
            "product_publication_plan_cycle_id": "older-cycle",
        }

        result = calculate_product_publication_cadence(
            state, status, 4, now=self.now, max_daily_posts=72
        )

        expected_next_scan = current_scan_started + timedelta(seconds=cycle_seconds)
        self.assertEqual(result["plan_anchor_kind"], "cycle_start_after_max_gap")
        self.assertEqual(result["plan_anchor_at"], self.now.isoformat())
        self.assertEqual(result["estimated_next_clean_scan_at"], expected_next_scan.isoformat())
        self.assertEqual(result["planned_product_slots"], 4)
        self.assertEqual(result["interval_seconds"], 57 * 60)
        self.assertTrue(result["first_slot_due_now"])

    def test_reflow_after_expired_scan_eta_keeps_products_moving_at_57_minutes(self):
        last_product = self.now - timedelta(hours=2)
        state = {
            "last_product_channel_published_at": last_product.isoformat(),
            "last_channel_published_at": last_product.isoformat(),
            "content_delivery_queue": {
                "dkp-reflow-now": {
                    "content_type": "product", "status": "queued",
                    "sequence_number": 1, "platforms": {},
                },
                "dkp-reflow-later": {
                    "content_type": "product", "status": "queued",
                    "sequence_number": 2, "platforms": {},
                },
            },
            "product_publication_cadence": {
                "estimated_next_clean_scan_at": (self.now - timedelta(minutes=5)).isoformat(),
                "interval_seconds": 0,
            },
        }
        result = reflow_product_queue_after_delivery(state, now=self.now)
        first = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-reflow-now"]["scheduled_at"]
        )
        second = datetime.fromisoformat(
            state["content_delivery_queue"]["dkp-reflow-later"]["scheduled_at"]
        )
        self.assertEqual(result["interval_seconds"], 57 * 60)
        self.assertEqual(first, self.now)
        self.assertEqual(
            second,
            self.now + timedelta(seconds=channel_post_interval_seconds(
                "product:2:dkp-reflow-later"
            )),
        )
        self.assertGreaterEqual(
            (second - self.now).total_seconds(), MIN_CHANNEL_POST_INTERVAL_SECONDS
        )
        self.assertLessEqual(
            (second - self.now).total_seconds(), MAX_CHANNEL_POST_INTERVAL_SECONDS
        )
        self.assertTrue(state["product_publication_cadence"]["scan_eta_is_provisional"])

    def test_product_queue_slots_are_evenly_rescheduled(self):
        last_product = self.now - timedelta(minutes=10)
        state = {
            "last_product_channel_published_at": last_product.isoformat(),
            "product_publication_plan_cycle_id": "cycle-1",
            "product_publication_plan_anchor_at": last_product.isoformat(),
            "product_publication_plan_anchor_kind": "last_product",
            "content_delivery_queue": {},
        }
        items = [self.item(f"dkp-plan-{i}") for i in range(3)]
        summary = enqueue_selected_content(
            state, items, now=self.now, interval_seconds=3600,
            max_items=3, max_active_items=250,
        )
        self.assertEqual(summary["added"], 3)
        schedule = {
            "catalog_cycle_id": "cycle-1",
            "interval_seconds": 3600,
            "estimated_next_clean_scan_at": (self.now + timedelta(hours=6)).isoformat(),
        }
        result = reschedule_product_queue_evenly(state, schedule, now=self.now)
        self.assertEqual(result["scheduled"], 3)
        ordered = [
            datetime.fromisoformat(state["content_delivery_queue"][f"dkp-plan-{i}"]["scheduled_at"])
            for i in range(3)
        ]
        expected_gaps = [
            channel_post_interval_seconds(
                f"product:{state['content_delivery_queue'][f'dkp-plan-{i + 1}']['sequence_number']}:dkp-plan-{i + 1}"
            )
            for i in range(2)
        ]
        actual_gaps = [(ordered[i + 1] - ordered[i]).total_seconds() for i in range(2)]
        self.assertEqual(actual_gaps, expected_gaps)
        self.assertTrue(all(
            MIN_CHANNEL_POST_INTERVAL_SECONDS <= gap <= MAX_CHANNEL_POST_INTERVAL_SECONDS
            for gap in actual_gaps
        ))

if __name__ == "__main__":
    unittest.main()
