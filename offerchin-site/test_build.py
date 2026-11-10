from __future__ import annotations

import json
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

import build


class StorefrontConversionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.deadline = self.now + timedelta(hours=4)

    def product(self, product_id="snp-2097083854", merchant="اسنپ‌شاپ"):
        host = "snappshop.ir" if product_id.startswith("snp-") else "digikala.com"
        path = f"/product/{product_id}/"
        return {
            "product_id": product_id,
            "title": "هدفون بی‌سیم آزمایشی",
            "merchant": merchant,
            "category": "کالای دیجیتال",
            "product_url": f"https://www.{host}{path}",
            "affiliate_url": f"https://aflo.ir/QekEYTRg?p=https%3A%2F%2F{host}{path}",
            "image_url": "https://images.example.test/product.webp",
            "availability": "in_stock",
            "qualifies_as_deal": True,
            "current_price": 800_000,
            "original_price": 1_000_000,
            "discount_percent": 20,
            "savings_toman": 200_000,
            "deal_expires_at": self.deadline.isoformat(),
            "demand_score": 75,
            "click_count_30d": 14,
            "promo_score": 58,
            "review_count": 230,
        }

    def state_for(self, product):
        return {
            "published": {
                product["product_id"]: {
                    "delivery_status": {"telegram": "sent"},
                    "expiry_status": "tracked",
                    "expires_at": self.deadline.isoformat(),
                    "ts": self.now.timestamp(),
                }
            }
        }

    def build_one(self, product=None):
        product = product or self.product()
        return build.build_products({"products": [product]}, self.state_for(product), self.now)

    def test_snappshop_product_is_eligible_and_labeled(self):
        products = self.build_one()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["retailer_key"], "snappshop")
        self.assertEqual(products[0]["retailer_name"], "اسنپ‌شاپ")
        self.assertEqual(products[0]["discount_percent"], 20)
        self.assertEqual(products[0]["savings_toman"], 200_000)

    def test_digikala_remains_supported(self):
        product = self.product("dkp-1234567", "دیجی‌کالا")
        result = self.build_one(product)
        self.assertEqual(result[0]["retailer_key"], "digikala")
        self.assertEqual(result[0]["retailer_name"], "دیجی‌کالا")

    def test_material_discount_mismatch_is_rejected(self):
        product = self.product()
        product["discount_percent"] = 66
        self.assertEqual(self.build_one(product), [])

    def test_expired_sold_out_unpublished_and_unsafe_id_are_rejected(self):
        product = self.product()
        expired = dict(product, deal_expires_at=(self.now - timedelta(minutes=2)).isoformat())
        self.assertEqual(self.build_one(expired), [])
        sold_out = dict(product, availability="sold_out")
        self.assertEqual(self.build_one(sold_out), [])
        unpublished_state = {"published": {product["product_id"]: {
            "delivery_status": {"telegram": "failed"},
            "expiry_status": "tracked",
            "expires_at": self.deadline.isoformat(),
        }}}
        self.assertEqual(build.build_products({"products": [product]}, unpublished_state, self.now), [])
        unsafe = dict(product, product_id="../snp-2097083854")
        self.assertEqual(self.build_one(unsafe), [])

    def test_detail_has_retailer_cta_and_structured_offer(self):
        product = self.build_one()[0]
        page = build.build_detail(product)
        self.assertIn("مشاهده و خرید در اسنپ‌شاپ", page)
        self.assertIn('"priceCurrency":"IRR"', page)
        self.assertIn('"availability":"https://schema.org/InStock"', page)
        self.assertIn('name="twitter:card" content="summary_large_image"', page)
        structured = page.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
        schema = json.loads(structured)
        self.assertEqual(schema["offers"]["price"], 8_000_000)
        self.assertEqual(schema["offers"]["seller"]["name"], "اسنپ‌شاپ")

    def test_catalog_has_search_filters_and_demand_first_sort(self):
        product = self.build_one()[0]
        page = build.build_index([product])
        self.assertIn('id="offerCategory"', page)
        self.assertIn('id="offerRetailer"', page)
        self.assertIn('<option value="demand">تقاضای بیشتر</option>', page)
        self.assertIn("دیجی‌کالا و اسنپ‌شاپ", page)
        self.assertIn("data-share-product", page)

    def test_ids_are_path_safe(self):
        self.assertTrue(build.valid_product_id("snp-2097083854"))
        self.assertTrue(build.valid_product_id("dkp-7832807"))
        self.assertFalse(build.valid_product_id("../snp-2097083854"))
        self.assertFalse(build.valid_product_id("id/with/slash"))


    def test_storefront_requires_the_original_affilio_url_for_the_same_product(self):
        product = self.product()
        result = self.build_one(product)
        self.assertEqual(result[0]["affiliate_url"], product["affiliate_url"])

        tracked = dict(
            product,
            affiliate_url=(
                "https://affiliate-deal-radar.m-hoseyni-6966.workers.dev/"
                "p/snp-2097083854?u=" + product["affiliate_url"]
            ),
        )
        self.assertEqual(self.build_one(tracked), [])

        wrong_destination = dict(
            product,
            affiliate_url=(
                "https://aflo.ir/QekEYTRg?p="
                "https%3A%2F%2Fsnappshop.ir%2Fproduct%2Fsnp-9999999999"
            ),
        )
        self.assertEqual(self.build_one(wrong_destination), [])

    def test_click_counts_do_not_rank_storefront_products(self):
        high_clicks = self.product("snp-2097083854")
        lower_clicks = self.product("dkp-1234567", "دیجی‌کالا")
        high_clicks["demand_score"] = lower_clicks["demand_score"] = 75
        high_clicks["promo_score"] = 10
        lower_clicks["promo_score"] = 20
        high_clicks["click_count_30d"] = 9999
        lower_clicks["click_count_30d"] = 0

        state = {"published": {}}
        for product in (high_clicks, lower_clicks):
            state["published"][product["product_id"]] = {
                "delivery_status": {"telegram": "sent"},
                "expiry_status": "tracked",
                "expires_at": self.deadline.isoformat(),
                "ts": self.now.timestamp(),
            }
        result = build.build_products({"products": [high_clicks, lower_clicks]}, state, self.now)
        self.assertEqual(result[0]["product_id"], lower_clicks["product_id"])

    def test_browser_purchase_links_are_direct_affilio_only(self):
        source = (Path(build.__file__).resolve().parent / "assets" / "site.js").read_text(encoding="utf-8")
        self.assertIn('u.hostname.toLowerCase() !== "aflo.ir"', source)
        self.assertNotIn("affiliate-deal-radar", source)
        self.assertNotIn("click_count_30d", source)



if __name__ == "__main__":
    unittest.main()
