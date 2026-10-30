import unittest

from integrity_audit_state import (
    RECORD_FIELDS,
    apply_integrity_audit_ledger,
    capture_integrity_audit_ledger,
    empty_ledger,
    post_key,
)


class IntegrityAuditStateTests(unittest.TestCase):
    def invalidated_entry(self, product_id, post_id, platform_status):
        fields = {key: None for key in RECORD_FIELDS}
        fields.update({
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "posted_discount_percent": 50,
            "price_audit_status": "invalidated",
            "price_audit_reason": "price_mismatch",
            "price_audit_invalidated_at": "2026-10-26T10:00:00+00:00",
            "price_audit_mismatch_fields": ["current_price"],
            "price_audit_posted_price": 100_000,
            "price_audit_live_price": 120_000,
            "expires_at": "2026-10-26T10:00:00+00:00",
            "expiry_source": "live_product_stock_or_price",
            "expiry_estimated": False,
            "expiry_deadline_verified_directly": True,
            "expiry_deadline_verified_from_site_card": False,
            "expiry_reason": "price_mismatch",
        })
        return {
            "product_id": product_id,
            "post_id": str(post_id),
            "platform": "telegram",
            "updated_at": "2026-10-26T10:00:00+00:00",
            "price_audit_status": "invalidated",
            "record_fields": fields,
            "platform_status": platform_status,
            "platform_fields": {
                "expired_deleted_at": "2026-10-26T10:00:01+00:00" if platform_status == "deleted" else None,
                "expiry_last_absent_at": None,
                "telegram_expiry_last_delete_error": (
                    "network error" if platform_status == "delete_failed"
                    else "Bad Request: message can't be deleted" if platform_status == "delete_unavailable"
                    else None
                ),
            },
        }

    def test_confirmed_invalidation_is_applied_to_exact_post_and_terminal_status(self):
        state = {
            "published": {
                "dkp-123": {
                    "product_url": "https://www.digikala.com/product/dkp-123/",
                    "telegram_message_id": 101,
                    "expiry_status": "tracked",
                    "posted_current_price": 100_000,
                    "posted_discount_percent": 50,
                }
            }
        }
        ledger = {
            "posts": {
                post_key("telegram", 101): self.invalidated_entry("dkp-123", 101, "deleted")
            }
        }

        changed = apply_integrity_audit_ledger(state, ledger)
        record = state["published"]["dkp-123"]

        self.assertTrue(changed)
        self.assertEqual(record["expiry_status"], "deleted")
        self.assertEqual(record["price_audit_status"], "invalidated")
        self.assertEqual(record["expiry_source"], "live_product_stock_or_price")
        self.assertEqual(record["posted_current_price"], 100_000)
        self.assertEqual(record["price_audit_live_price"], 120_000)


    def test_delete_unavailable_is_preserved_as_terminal(self):
        state = {
            "published": {
                "dkp-124b": {
                    "telegram_message_id": 103,
                    "expiry_status": "tracked",
                }
            }
        }
        entry = self.invalidated_entry("dkp-124b", 103, "delete_unavailable")
        entry["platform_fields"]["telegram_expiry_last_delete_error"] = "Bad Request: message can't be deleted"
        ledger = {"posts": {post_key("telegram", 103): entry}}

        self.assertTrue(apply_integrity_audit_ledger(state, ledger))
        record = state["published"]["dkp-124b"]
        self.assertEqual(record["expiry_status"], "delete_unavailable")
        self.assertEqual(record["telegram_expiry_last_delete_error"], "Bad Request: message can't be deleted")

    def test_delete_failure_is_preserved_for_retry(self):
        state = {
            "published": {
                "dkp-124": {
                    "telegram_message_id": 102,
                    "expiry_status": "tracked",
                }
            }
        }
        ledger = {
            "posts": {
                post_key("telegram", 102): self.invalidated_entry("dkp-124", 102, "delete_failed")
            }
        }

        self.assertTrue(apply_integrity_audit_ledger(state, ledger))
        record = state["published"]["dkp-124"]
        self.assertEqual(record["expiry_status"], "delete_failed")
        self.assertEqual(record["price_audit_status"], "invalidated")
        self.assertEqual(record["telegram_expiry_last_delete_error"], "network error")

    def test_historical_post_status_does_not_leak_to_new_post_for_same_product(self):
        state = {
            "published": {
                "dkp-125": {
                    "telegram_message_id": 201,
                    "expiry_status": "tracked",
                    "posted_current_price": 150_000,
                    "post_history": [{
                        "telegram_message_id": 200,
                        "expiry_status": "tracked",
                        "posted_current_price": 100_000,
                    }],
                }
            }
        }
        ledger = {
            "posts": {
                post_key("telegram", 200): self.invalidated_entry("dkp-125", 200, "deleted")
            }
        }

        self.assertTrue(apply_integrity_audit_ledger(state, ledger))
        current = state["published"]["dkp-125"]
        old = current["post_history"][0]
        self.assertEqual(current["expiry_status"], "tracked")
        self.assertEqual(current["posted_current_price"], 150_000)
        self.assertEqual(old["expiry_status"], "deleted")
        self.assertEqual(old["price_audit_status"], "invalidated")
        self.assertEqual(old["posted_current_price"], 100_000)

    def test_audit_cadence_is_restored_only_for_the_independent_monitor(self):
        next_check = "2026-10-26T12:05:00+00:00"
        last_checked = "2026-10-26T12:00:00+00:00"
        fields = {key: None for key in RECORD_FIELDS}
        fields.update({
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "posted_discount_percent": 50,
            "price_audit_status": "match",
            "price_audit_last_checked_at": last_checked,
            "price_audit_next_check_at": next_check,
            "last_seen_current_price": 100_000,
            "last_seen_original_price": 200_000,
            "last_seen_in_stock": True,
        })
        entry = {
            "product_id": "dkp-127",
            "post_id": "401",
            "platform": "telegram",
            "updated_at": last_checked,
            "price_audit_status": "match",
            "record_fields": fields,
            "platform_status": "tracked",
            "platform_fields": {
                "expired_deleted_at": None,
                "expiry_last_absent_at": None,
                "telegram_expiry_last_delete_error": None,
            },
        }
        ledger = {"posts": {post_key("telegram", 401): entry}}
        publisher_state = {
            "published": {
                "dkp-127": {
                    "telegram_message_id": 401,
                    "expiry_status": "tracked",
                    "posted_current_price": 100_000,
                    "posted_discount_percent": 50,
                }
            }
        }
        monitor_state = {
            "published": {
                "dkp-127": {
                    "telegram_message_id": 401,
                    "expiry_status": "tracked",
                    "posted_current_price": 100_000,
                    "posted_discount_percent": 50,
                }
            }
        }

        self.assertFalse(apply_integrity_audit_ledger(publisher_state, ledger))
        self.assertNotIn("price_audit_next_check_at", publisher_state["published"]["dkp-127"])

        self.assertTrue(apply_integrity_audit_ledger(
            monitor_state, ledger, include_audit_cadence=True
        ))
        self.assertEqual(
            monitor_state["published"]["dkp-127"]["price_audit_next_check_at"],
            next_check,
        )
        self.assertEqual(
            monitor_state["published"]["dkp-127"]["price_audit_last_checked_at"],
            last_checked,
        )

    def test_active_posts_are_never_evicted_when_terminal_history_is_bounded(self):
        published = {}
        for post_id in range(1, 111):
            published[f"dkp-{post_id}"] = {
                "telegram_message_id": post_id,
                "expiry_status": "deleted",
                "posted_current_price": 100_000,
                "price_audit_status": "match",
            }
        published["dkp-active"] = {
            "telegram_message_id": 9001,
            "expiry_status": "tracked",
            "posted_current_price": 100_000,
            "posted_original_price": 200_000,
            "posted_discount_percent": 50,
            "price_audit_status": "match",
            "price_audit_next_check_at": "2026-10-26T13:00:00+00:00",
        }

        ledger = capture_integrity_audit_ledger(
            {"published": published},
            empty_ledger(),
            now_iso="2026-10-26T12:00:00+00:00",
            keep_posts=100,
        )

        self.assertIn(post_key("telegram", 9001), ledger["posts"])
        self.assertGreater(len(ledger["posts"]), 100)
        self.assertLessEqual(
            sum(
                1 for item in ledger["posts"].values()
                if item.get("platform_status") in {"deleted", "already_absent", "delete_unavailable"}
            ),
            100,
        )

    def test_integrity_audit_is_scheduled_separately_from_publisher(self):
        root = __import__("pathlib").Path(__file__).resolve().parent.parent
        audit_workflow = (root / ".github" / "workflows" / "offerchin-integrity-audit.yml").read_text(encoding="utf-8")
        publisher_workflow = (root / ".github" / "workflows" / "offerchin-publisher.yml").read_text(encoding="utf-8")

        # Cloudflare dispatches the audit on an off-slot minute; a second GitHub
        # cron would duplicate the work and compete with fresh product validation.
        self.assertIn("workflow_dispatch:", audit_workflow)
        self.assertNotIn('cron: "*/5 * * * *"', audit_workflow)
        self.assertIn('AFFILIO_PRICE_AUDIT_BATCH_SIZE: "8"', audit_workflow)
        self.assertIn('AFFILIO_DIRECT_PRODUCT_DETAIL_CHECK_LIMIT: "1"', audit_workflow)
        self.assertIn('AFFILIO_MAX_CHANNEL_EXPIRY_DELETE_ATTEMPTS: "24"', audit_workflow)
        self.assertIn('AFFILIO_MAX_VIDEO_EXPIRY_DELETE_ATTEMPTS: "2"', audit_workflow)
        self.assertIn('AFFILIO_HTTP_TIMEOUT: "8"', audit_workflow)
        self.assertIn('AFFILIO_PRODUCT_STATUS_TIMEOUT_SECONDS: "6"', audit_workflow)
        self.assertIn('AFFILIO_PRICE_AUDIT_RETRY_SECONDS: "300"', audit_workflow)
        self.assertIn('210s python affilio_radar/integrity_audit.py', audit_workflow)
        audit_code = (root / "affilio_radar" / "integrity_audit.py").read_text(encoding="utf-8")
        self.assertIn('budget=channel_budget', audit_code)
        self.assertIn('budget=youtube_budget', audit_code)
        self.assertIn('budget=aparat_budget', audit_code)
        self.assertIn('max_delete_attempts=channel_delete_budget', audit_code)
        self.assertIn('max_delete_attempts=video_delete_budget', audit_code)
        self.assertIn("group: offerchin-integrity-audit", audit_workflow)
        self.assertIn("group: offerchin-content-publisher", publisher_workflow)
        self.assertNotIn("offerchin-integrity-audit", publisher_workflow)

    def test_audit_entry_for_unknown_post_id_is_ignored(self):
        state = {"published": {"dkp-126": {"telegram_message_id": 301, "expiry_status": "tracked"}}}
        ledger = {
            "posts": {
                post_key("telegram", 999): self.invalidated_entry("dkp-126", 999, "deleted")
            }
        }
        self.assertFalse(apply_integrity_audit_ledger(state, ledger))
        self.assertEqual(state["published"]["dkp-126"]["expiry_status"], "tracked")


if __name__ == "__main__":
    unittest.main()
