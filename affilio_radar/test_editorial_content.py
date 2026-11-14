import unittest
from datetime import datetime, timedelta, timezone

from editorial_content import (
    is_persian_public_text,
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
        "sources": [{"source_id": "s1", "title": "Official Consumer Guide", "display_title_fa": "راهنمای رسمی مصرف‌کننده", "url": "https://example.org/guide"}],
        "claims": [{"text": "هزینه نگهداری را پیش از انتخاب بررسی کنید", "source_ids": ["s1"]}],
        "reviewed_at": (NOW - timedelta(days=1)).isoformat(),
        "review_due_at": (NOW + timedelta(days=30)).isoformat(),
        "priority": "normal",
    }


class EditorialContentTests(unittest.TestCase):
    def test_valid_item_passes(self):
        self.assertEqual(validate_editorial_item(item(), now=NOW), (True, "ok"))


    def test_latin_letters_in_public_title_are_rejected(self):
        value = item()
        value["title"] = "راهنمای خرید USB"
        self.assertEqual(
            validate_editorial_item(value, now=NOW)[1],
            "editorial_title_must_be_persian_only",
        )

    def test_latin_letters_in_public_body_are_rejected(self):
        value = item()
        value["body"] += " لینک را در Website بررسی کن."
        self.assertEqual(
            validate_editorial_item(value, now=NOW)[1],
            "editorial_body_must_be_persian_only",
        )

    def test_latin_letters_in_claims_are_rejected(self):
        value = item()
        value["claims"][0]["text"] = "اعتبار Website را بررسی کن"
        self.assertEqual(
            validate_editorial_item(value, now=NOW)[1],
            "editorial_claim_must_be_persian_only",
        )

    def test_public_source_label_must_be_persian(self):
        value = item()
        value["sources"][0]["display_title_fa"] = "Official guide"
        self.assertEqual(
            validate_editorial_item(value, now=NOW)[1],
            "missing_or_invalid_sources",
        )

    def test_public_text_language_helper_is_strict(self):
        self.assertTrue(is_persian_public_text("راهنمای خرید آگاهانه"))
        self.assertFalse(is_persian_public_text("راهنمای خرید USB"))
        self.assertFalse(is_persian_public_text("English only"))

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

    def test_selector_skips_recent_item_and_topic(self):
        state = {"editorial_delivery_history": [{
            "editorial_id": "old",
            "topic": "buying-guide",
            "published_at": (NOW - timedelta(hours=1)).isoformat(),
        }]}
        self.assertIsNone(select_editorial_fallback([item()], state, now=NOW))

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
