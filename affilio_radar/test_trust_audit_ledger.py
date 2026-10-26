import json
import tempfile
import unittest
from pathlib import Path

from trust_audit_ledger import apply_audit_ledger, write_audit_ledger


class TrustAuditLedgerTests(unittest.TestCase):
    def test_overlay_applies_status_only_to_matching_platform_post_id(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "price_audit_state.json"
            ledger_path.write_text(json.dumps({
                "version": 1,
                "posts": {
                    "telegram:101": {
                        "product_id": "dkp-1",
                        "platform_id": "telegram:101",
                        "patch": {
                            "price_audit_status": "invalidated",
                            "price_audit_reason": "price_mismatch",
                            "expiry_status": "deleted",
                        },
                    },
                },
            }), encoding="utf-8")
            state = {
                "published": {
                    "dkp-1": {
                        "telegram_message_id": 101,
                        "expiry_status": "tracked",
                    },
                    "dkp-2": {
                        "telegram_message_id": 202,
                        "expiry_status": "tracked",
                    },
                },
            }

            result = apply_audit_ledger(state, ledger_path)

            self.assertEqual(result["published"]["dkp-1"]["price_audit_status"], "invalidated")
            self.assertEqual(result["published"]["dkp-1"]["price_audit_reason"], "price_mismatch")
            self.assertEqual(result["published"]["dkp-1"]["expiry_status"], "deleted")
            self.assertEqual(result["published"]["dkp-2"]["expiry_status"], "tracked")
            self.assertNotIn("price_audit_status", result["published"]["dkp-2"])

    def test_ledger_persists_changed_audit_fields_without_mutating_publication_state(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "price_audit_state.json"
            baseline = {
                "published": {
                    "dkp-1": {
                        "telegram_message_id": 101,
                        "posted_current_price": 100_000,
                        "expiry_status": "tracked",
                    },
                },
            }
            changed = json.loads(json.dumps(baseline))
            changed["published"]["dkp-1"].update({
                "price_audit_status": "invalidated",
                "price_audit_reason": "price_mismatch",
                "expiry_status": "deleted",
            })
            before_state = json.dumps(changed, sort_keys=True)

            write_audit_ledger(changed, baseline, ledger_path)

            data = json.loads(ledger_path.read_text(encoding="utf-8"))
            patch = data["posts"]["telegram:101"]["patch"]
            self.assertEqual(patch["price_audit_status"], "invalidated")
            self.assertEqual(patch["price_audit_reason"], "price_mismatch")
            self.assertEqual(patch["expiry_status"], "deleted")
            self.assertEqual(json.dumps(changed, sort_keys=True), before_state)

    def test_orphan_snapshot_is_restored_when_shared_state_does_not_contain_post(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "price_audit_state.json"
            ledger_path.write_text(json.dumps({
                "version": 1,
                "posts": {
                    "telegram:101": {
                        "product_id": "dkp-1",
                        "platform_id": "telegram:101",
                        "updated_at": "2026-10-26T12:00:00+00:00",
                        "patch": {
                            "price_audit_status": "invalidated",
                            "expiry_status": "deleted",
                        },
                        "snapshot": {
                            "telegram_message_id": 101,
                            "title": "محصول نمونه",
                            "product_url": "https://www.digikala.com/product/dkp-1/",
                            "posted_current_price": 100_000,
                        },
                    },
                },
            }), encoding="utf-8")

            result = apply_audit_ledger({"published": {}}, ledger_path)

            self.assertIn("dkp-1", result["published"])
            restored = result["published"]["dkp-1"]
            self.assertEqual(restored["telegram_message_id"], 101)
            self.assertEqual(restored["price_audit_status"], "invalidated")
            self.assertEqual(restored["expiry_status"], "deleted")


if __name__ == "__main__":
    unittest.main()
