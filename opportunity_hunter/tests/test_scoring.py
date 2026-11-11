import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class OpportunityHunterTests(unittest.TestCase):
    def test_persian_discount_digits(self):
        self.assertEqual(scan.discount_claim("۱۰٪ تخفیف ویژه"), 10.0)

    def test_false_discount_label_is_flagged(self):
        self.assertTrue(scan.unreliable_discount({"title": "کالا", "text": "۹۵٪ تخفیف غیرواقعی"}))

    def test_active_sellers_are_not_buyers(self):
        group = {"id": "x", "title": "خدمت", "city_or_area": "تهران"}
        recs = [
            {"id": "s", "type": "supplier_offer", "url": "https://example.test", "discount_percent_claimed": 10},
            {"id": "m", "type": "market_signal", "active_service_listings": 926},
            {"id": "b", "type": "price_benchmark", "price_points_toman": [2500000, 3900000]},
        ]
        result = scan.build_service_opportunity(group, recs, dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc))
        self.assertEqual(result["active_competing_service_listings"], 926)
        self.assertNotIn("buyer_count", result)
        self.assertFalse(result["publish_ready"])

    def test_no_commercial_agreement_blocks_publication(self):
        group = {"id": "x", "title": "خدمت"}
        recs = [
            {"id": "s", "type": "supplier_offer", "url": "https://example.test"},
            {"id": "m", "type": "market_signal"},
            {"id": "b", "type": "price_benchmark"},
        ]
        result = scan.build_service_opportunity(group, recs, dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc))
        self.assertEqual(result["monetization_status"], "NO_AGREEMENT_VERIFIED")
        self.assertIn("commission_or_lead_fee_agreed", result["blocking_gates"])

    def test_recent_jalali_reviews_counted_as_weak_signal(self):
        group = {"id": "x", "title": "خدمت"}
        recs = [
            {"id": "s", "type": "supplier_offer"},
            {"id": "m", "type": "market_signal", "visible_recent_review_dates_jalali": ["1405/08/17"]},
            {"id": "b", "type": "price_benchmark"},
        ]
        result = scan.build_service_opportunity(group, recs, dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc))
        self.assertEqual(result["recent_review_count_7d"], 1)

    def test_atom_feed_extracts_title_url_and_discount(self):
        atom = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>فروش ویژه ابزار</title><link href="https://example.test/item"/>
        <updated>2026-11-11T10:00:00Z</updated><summary>۲۰٪ تخفیف</summary></entry></feed>"""
        with patch.object(scan, "fetch", return_value=(atom, "https://example.test/feed")):
            items = scan.parse_feed({"id": "atom", "url": "https://example.test/feed", "limit": 10})
        self.assertEqual(items[0]["title"], "فروش ویژه ابزار")
        self.assertEqual(items[0]["url"], "https://example.test/item")
        self.assertEqual(items[0]["discount_percent_claimed"], 20.0)

    def test_price_riyal_converted_to_toman(self):
        self.assertIn(250000, scan.price_points("۲٬۵۰۰٬۰۰۰ ریال"))

    def test_jalali_date_conversion(self):
        self.assertEqual(scan.jalali_to_gregorian(1405, 8, 17), dt.date(2026, 11, 8))

    def test_kitchenware_service_bundle_is_product(self):
        self.assertEqual(scan.classify("سرویس پخت و پز ۹ پارچه زولینگ"), "product")

    def test_extreme_discount_is_quarantined(self):
        item = {"title": "ابزار شارژی", "text": "ادعای ۹۱٪ تخفیف", "discount_percent_claimed": 91}
        self.assertIn("قرنطینه", scan.quarantine_reason(item))

    def test_normal_discount_is_not_automatically_quarantined(self):
        item = {"title": "کالا", "text": "۳۵٪ تخفیف", "discount_percent_claimed": 35}
        self.assertEqual(scan.quarantine_reason(item), "")


if __name__ == "__main__":
    unittest.main()
