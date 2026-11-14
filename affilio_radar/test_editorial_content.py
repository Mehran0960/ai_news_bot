import unittest
from datetime import datetime, timedelta, timezone

from editorial_content import (
    record_editorial_delivery,
    select_editorial_fallback,
    validate_editorial_item,
)

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def item(editorial_id="buying-checklist", topic="buying-guide"):
    return {
        "editorial_id": editorial_id,
        "title": "چک‌لیست انتخاب کالای بادوام",
        "body": "پیش از خرید، نیاز واقعی، هزینه نگهداری، ضمانت و امکان تعمیر را بررسی کنید.",
        "topic": topic,
        "sources": [{"source_id": "s1", "title": "راهنمای رسمی مصرف‌کننده", "url": "https://example.org/guide"}],
        "claims": [{"text": "هزینه نگهداری را پیش از انتخاب بررسی کنید", "source_ids": ["s1"]}],
        "reviewed_at": (NOW - timedelta(days=1)).isoformat(),
        "review_due_at": (NOW + timedelta(days=30)).isoformat(),
        "priority": "normal",
    }


class EditorialContentTests(unittest.TestCase):
    def test_valid_item_passes(self):
        self.assertEqual(validate_editorial_item(item(), now=NOW), (True, "ok"))

    def test_current_commercial_claim_is_rejected(self):
        value = item()
        value["body"] += " قیمت فعلی فقط تا امشب معتبر است."
        self.assertEqual(validate_editorial_item(value, now=NOW)[1], "unsupported_commercial_claim")

    def test_missing_claim_sources_is_rejected(self):
        value = item()
        value["claims"][0]["source_ids"] = ["unknown"]
        self.assertEqual(validate_editorial_item(value, now=NOW)[1], "claim_without_source")

    def test_expired_review_is_rejected(self):
        value = item()
        value["review_due_at"] = (NOW - timedelta(seconds=1)).isoformat()
        self.assertEqual(validate_editorial_item(value, now=NOW)[1], "editorial_review_expired")

    def test_bank_exhaustion_starts_a_new_cycle_instead_of_stopping(self):
        state = {
            "editorial_cycle": {
                "bank_ids": ["buying-checklist"],
                "used_ids": ["buying-checklist"],
                "cycle_number": 1,
                "last_editorial_id": "buying-checklist",
            }
        }
        chosen = select_editorial_fallback([item()], state, now=NOW)
        self.assertEqual(chosen["editorial_id"], "buying-checklist")
        self.assertEqual(state["editorial_cycle"]["cycle_number"], 2)
        self.assertEqual(state["editorial_cycle"]["used_ids"], [])

    def test_item_can_be_reused_after_24_hour_cooldown(self):
        state = {"editorial_delivery_history": [{
            "editorial_id": "buying-checklist",
            "topic": "buying-guide",
            "published_at": (NOW - timedelta(hours=25)).isoformat(),
        }]}
        chosen = select_editorial_fallback([item()], state, now=NOW)
        self.assertEqual(chosen["editorial_id"], "buying-checklist")

    def test_selector_returns_non_recent_reviewed_item(self):
        chosen = select_editorial_fallback(
            [item(), item("home-maintenance", "home-care")], {}, now=NOW
        )
        self.assertEqual(chosen["content_type"], "editorial")
        self.assertEqual(chosen["content_id"], "editorial:buying-checklist")
        self.assertEqual(chosen["delivery_status"], "selected_not_published")

    def test_newly_approved_item_joins_the_active_rotation(self):
        state = {
            "editorial_cycle": {
                "bank_ids": ["buying-checklist"],
                "used_ids": ["buying-checklist"],
                "cycle_number": 3,
            }
        }
        chosen = select_editorial_fallback(
            [item(), item("new-mag-guide", "device-compatibility")],
            state,
            now=NOW,
        )
        self.assertEqual(chosen["editorial_id"], "new-mag-guide")
        self.assertEqual(state["editorial_cycle"]["cycle_number"], 3)

    def test_related_editorial_topic_is_preferred_for_product(self):
        state = {}
        bank = [
            item("fashion-guide", "fit-and-size"),
            item("device-guide", "device-compatibility"),
        ]
        product = {
            "product_id": "dkp-123",
            "offerchin_four_factor": {"generality_group": "mobile_productivity"},
        }
        chosen = select_editorial_fallback(
            bank, state, now=NOW, related_product=product
        )
        self.assertEqual(chosen["editorial_id"], "device-guide")
        self.assertEqual(chosen["related_product_id"], "dkp-123")

    def test_confirmed_delivery_marks_item_used_in_current_cycle(self):
        state = {}
        chosen = select_editorial_fallback([item()], state, now=NOW)
        record_editorial_delivery(
            state, chosen, published_at=NOW,
            destinations={"telegram": {"status": "sent"}},
        )
        self.assertIn("buying-checklist", state["editorial_cycle"]["used_ids"])
        self.assertEqual(state["editorial_cycle"]["last_editorial_id"], "buying-checklist")

    def test_delivery_history_requires_confirmed_destination(self):
        state = {}
        chosen = select_editorial_fallback([item()], state, now=NOW)
        with self.assertRaises(ValueError):
            record_editorial_delivery(state, chosen, published_at=NOW, destinations={"youtube": {"status": "failed"}})

    def test_delivery_history_records_only_confirmed_publication(self):
        state = {}
        chosen = select_editorial_fallback([item()], state, now=NOW)
        record_editorial_delivery(
            state, chosen, published_at=NOW,
            destinations={"telegram": {"status": "sent"}, "youtube": {"status": "failed"}},
        )
        self.assertEqual(len(state["editorial_delivery_history"]), 1)


if __name__ == "__main__":
    unittest.main()
