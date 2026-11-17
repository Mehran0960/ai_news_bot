import unittest
from datetime import datetime, timedelta, timezone

from editorial_content import (
    editorial_content_fingerprint,
    editorial_topics_for_product,
    record_editorial_delivery,
    _is_near_duplicate_editorial,
    select_editorial_fallback,
    validate_editorial_item,
)

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def item(editorial_id="buying-checklist", topic="purchase-planning"):
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

    def test_recent_semantic_duplicate_is_skipped_even_with_a_new_id(self):
        original = item("original-buying-guide", "purchase-planning")
        rewritten = item("rewritten-buying-guide", "purchase-planning")
        rewritten["title"] = "پیش از خرید، فهرست نیازها و هزینه‌ها را بررسی کن"
        rewritten["body"] = "قبل از خرید، نیاز واقعی، هزینه نگهداری، ضمانت و امکان تعمیر محصول را بررسی کنید."
        distinct = item("return-policy-guide", "purchase-planning")
        distinct["title"] = "قواعد مرجوعی کالا را پیش از سفارش بخوان"
        distinct["body"] = "مهلت مرجوعی، بازپرداخت وجه و هزینه ارسال برگشتی را پیش از ثبت سفارش بررسی کن."
        state = {"editorial_delivery_history": [{
            "editorial_id": original["editorial_id"],
            "topic": original["topic"],
            "title": original["title"],
            "body": original["body"],
            "published_at": (NOW - timedelta(hours=4)).isoformat(),
        }]}

        self.assertTrue(_is_near_duplicate_editorial(rewritten, original))
        chosen = select_editorial_fallback(
            [original, rewritten, distinct], state, now=NOW
        )
        self.assertEqual(chosen["editorial_id"], "return-policy-guide")

    def test_distinct_delivery_guidance_is_not_misclassified_as_duplicate(self):
        delivery = {
            "editorial_id": "check-delivery-window",
            "title": "زمان تحویل را برای همان سفارش بررسی کن",
            "body": "زمان رسیدن سفارش برای همه کالاها یکسان نیست؛ نوع کالا، شهر مقصد، موجودی فروشنده و روش ارسال می‌توانند آن را تغییر دهند. پیش از پرداخت، بازه تحویل و روش‌های فعال برای همان کالا و نشانی را در صفحه سفارش بررسی کن؛ به یک زمان عمومی تکیه نکن.",
        }
        shipping = {
            "editorial_id": "shipping-window",
            "title": "زمان ارسال وعده‌داده‌شده را پیش از پرداخت ثبت کن",
            "body": "زمان پردازش، تحویل به شرکت حمل‌ونقل و بازه تقریبی دریافت را از هم تفکیک کن. اگر کالا را برای زمان مشخصی لازم داری، شرایط تأخیر و امکان پیگیری را هم بخوان و صفحه سفارش را نگه دار.",
        }
        self.assertFalse(_is_near_duplicate_editorial(delivery, shipping))

    def test_delivery_history_stores_copy_and_fingerprint_for_future_audits(self):
        state = {}
        chosen = select_editorial_fallback([item()], state, now=NOW)
        record_editorial_delivery(
            state, chosen, published_at=NOW,
            destinations={"telegram": {"status": "sent"}},
        )
        row = state["editorial_delivery_history"][0]
        self.assertEqual(row["title"], chosen["title"])
        self.assertEqual(row["body"], chosen["body"])
        self.assertEqual(row["content_fingerprint"], editorial_content_fingerprint(chosen))

    def test_selector_returns_non_recent_reviewed_item(self):
        chosen = select_editorial_fallback(
            [item(), item("seller-guide", "seller-check")], {}, now=NOW
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
            related_product={
                "product_id": "dkp-phone",
                "offerchin_four_factor": {"generality_group": "mobile_productivity"},
            },
        )
        self.assertEqual(chosen["editorial_id"], "new-mag-guide")
        self.assertEqual(state["editorial_cycle"]["cycle_number"], 3)

    def test_privacy_only_topics_and_retired_app_permissions_item_are_rejected(self):
        privacy_item = item("app-permissions", "privacy-and-security")
        self.assertEqual(
            validate_editorial_item(privacy_item, now=NOW)[1],
            "retired_off_topic_item",
        )
        renamed_privacy_item = item("generic-privacy-tip", "privacy")
        self.assertEqual(
            validate_editorial_item(renamed_privacy_item, now=NOW)[1],
            "unsupported_editorial_topic",
        )

    def test_selector_does_not_fall_back_to_an_unrelated_topic_for_a_product(self):
        product = {
            "product_id": "dkp-phone",
            "offerchin_four_factor": {"generality_group": "mobile_productivity"},
        }
        unrelated = item("seller-history-guide", "seller-verification")
        self.assertIsNone(
            select_editorial_fallback([unrelated], {}, now=NOW, related_product=product)
        )

    def test_local_digikala_mag_source_is_preferred_over_generic_foreign_source(self):
        global_item = item("global-buying-guide", "purchase-planning")
        local_item = item("local-buying-guide", "purchase-planning")
        local_item["sources"] = [{
            "source_id": "digikala-mag",
            "title": "راهنمای خرید دیجی‌کالا مگ",
            "publisher": "دیجی‌کالا مگ",
            "url": "https://www.digikala.com/mag/example/",
        }]
        local_item["claims"] = [{
            "text": "راهنمای خرید مرتبط با موضوع",
            "source_ids": ["digikala-mag"],
        }]
        chosen = select_editorial_fallback(
            [global_item, local_item], {}, now=NOW, related_product={}
        )
        self.assertEqual(chosen["editorial_id"], "local-buying-guide")

    def test_delivery_guidance_is_relevant_across_product_categories(self):
        topics = editorial_topics_for_product({
            "offerchin_four_factor": {"generality_group": "automotive"}
        })
        self.assertIn("delivery", topics)

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


    def test_publication_history_distinguishes_reuse_from_destination_receipts(self):
        state = {}
        first = select_editorial_fallback([item()], state, now=NOW)
        first["sequence_number"] = 101
        record_editorial_delivery(
            state, first, published_at=NOW,
            destinations={"telegram": {"status": "sent", "message_id": "tg-1"}},
        )
        record_editorial_delivery(
            state, first, published_at=NOW + timedelta(minutes=1),
            destinations={
                "telegram": {"status": "sent", "message_id": "tg-1"},
                "bale": {"status": "sent", "message_id": "ba-1"},
            },
        )
        self.assertEqual(len(state["editorial_delivery_history"]), 1)
        first_row = state["editorial_delivery_history"][0]
        self.assertEqual(first_row["destinations"]["telegram"]["message_id"], "tg-1")
        self.assertEqual(first_row["destinations"]["bale"]["message_id"], "ba-1")
        self.assertEqual(first_row["published_at"], (NOW + timedelta(minutes=1)).isoformat())

        second = dict(first)
        second["sequence_number"] = 102
        second_at = NOW + timedelta(hours=25)
        record_editorial_delivery(
            state, second, published_at=second_at,
            destinations={"telegram": {"status": "sent", "message_id": "tg-2"}},
        )
        self.assertEqual(len(state["editorial_delivery_history"]), 2)
        self.assertEqual(
            [row["sequence_number"] for row in state["editorial_delivery_history"]],
            [101, 102],
        )
        self.assertIsNone(
            select_editorial_fallback([item()], state, now=second_at + timedelta(hours=1))
        )

    def test_topic_cooldown_is_enforced_even_with_a_new_editorial_id(self):
        state = {}
        original = item("first-delivery-guide", "purchase-planning")
        original["title"] = "راهنمای تحویل سفارش را بررسی کن"
        original["body"] = "بازه تحویل، نشانی و روش ارسال را پیش از پرداخت بررسی کن."
        first = select_editorial_fallback([original], state, now=NOW)
        first["sequence_number"] = 1
        record_editorial_delivery(
            state, first, published_at=NOW,
            destinations={"telegram": {"status": "sent"}},
        )
        distinct = item("second-delivery-guide", "purchase-planning")
        distinct["title"] = "زمان پردازش و ارسال را جداگانه بررسی کن"
        distinct["body"] = "زمان آماده‌سازی، تحویل به حامل و بازه دریافت را با هم اشتباه نگیر."
        self.assertIsNone(
            select_editorial_fallback([distinct], state, now=NOW + timedelta(hours=3))
        )
        self.assertIsNotNone(
            select_editorial_fallback([distinct], state, now=NOW + timedelta(hours=5))
        )


if __name__ == "__main__":
    unittest.main()
