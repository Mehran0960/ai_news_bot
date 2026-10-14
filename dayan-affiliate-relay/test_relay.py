import unittest

from bs4 import BeautifulSoup

from relay_botapi import (
    extract_product_refs,
    make_affiliate_url,
    normalize_store_host,
    resolve_product_ref,
    clean_caption,
    extract_product_details,
    build_caption,
    CHANNEL_FOLLOW_HTML,
    photo_url_from_node,
)

class DayanRelayTests(unittest.TestCase):
    def test_lead_route_is_preserved(self):
        self.assertEqual(
            extract_product_refs("ادرس فروشگااه/lead/51366"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_fastcart_code_from_caption(self):
        self.assertEqual(
            extract_product_refs("لینک کد 39612 را در این قسمت وارد کنید"),
            [{"route": "fastcart", "code": "39612"}],
        )

    def test_route_wins_over_duplicate_labeled_code(self):
        self.assertEqual(
            extract_product_refs("لینک /lead/51366 و لینک کد 51366"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_persian_digits_are_normalized(self):
        self.assertEqual(
            extract_product_refs("لینک /lead/۵۱۳۶۶"),
            [{"route": "lead", "code": "51366"}],
        )

    def test_make_lead_url(self):
        self.assertEqual(
            make_affiliate_url("https://seller.affdn.com", {"route": "lead", "code": "51366"}),
            "https://seller.affdn.com/lead/51366",
        )

    def test_make_fastcart_url(self):
        self.assertEqual(
            make_affiliate_url("https://seller.affdn.ir", {"route": "fastcart", "code": "39612"}),
            "https://seller.affdn.ir/fastcart/39612",
        )

    def test_rejects_unrelated_store_domain(self):
        with self.assertRaises(RuntimeError):
            normalize_store_host("https://example.com")

    def test_rejects_store_path_in_secret(self):
        with self.assertRaises(RuntimeError):
            normalize_store_host("https://seller.affdn.ir/fastcart/1234")

    def test_ambiguous_code_is_not_autoselected(self):
        item = {
            "source_message_id": 100,
            "product_refs": [
                {"route": "lead", "code": "51366"},
                {"route": "fastcart", "code": "51366"},
            ],
        }
        self.assertIsNone(resolve_product_ref(item, {}))

    def test_manual_override_route(self):
        item = {"source_message_id": 101, "product_refs": []}
        self.assertEqual(
            resolve_product_ref(item, {"101": {"route": "lead", "product_code": "51366"}}),
            {"route": "lead", "code": "51366"},
        )

    def test_store_placeholder_is_removed_from_caption(self):
        self.assertEqual(clean_caption("ادرس فروشگااه/lead/51366"), "")


    def test_extracts_product_title_and_both_prices(self):
        page = """
        <html><head><meta property="og:title" content="ایران گجت"></head>
        <body><h1>دسته های طرح PS5 بی سیم بلوتوثی به همراه دانگل اتصال</h1>
          <p>قیمت اصلی: 7,639,000 تومان</p>
          <p>قیمت با تخفیف: 5,789,000 تومان</p>
        </body></html>
        """
        details = extract_product_details(page)
        self.assertIn("PS5", details["title"])
        self.assertEqual(details["original_price"], "7,639,000 تومان")
        self.assertEqual(details["discounted_price"], "5,789,000 تومان")

    def test_caption_contains_benefits_and_strikes_original_price(self):
        caption = build_caption(
            "منبع",
            "https://seller.affdn.ir/lead/51366",
            product_details={
                "title": "دسته های PS5",
                "original_price": "7,639,000 تومان",
                "discounted_price": "5,789,000 تومان",
            },
        )
        self.assertIn("<s>7,639,000 تومان</s>", caption)
        self.assertIn("<b>5,789,000 تومان</b>", caption)
        self.assertIn("✅ پرداخت درب منزل", caption)
        self.assertIn("✅ ارسال به سراسر کشور", caption)
        self.assertIn("✅ گارانتی تعویض و برگشت", caption)
        self.assertNotIn("🧪 نمونهٔ آزمایشی انتشار خودکار", caption)
        self.assertNotIn("#اینستاگرام", caption)
        self.assertNotIn("لینک همکاری در فروش است", caption)
        self.assertTrue(caption.rstrip().endswith(CHANNEL_FOLLOW_HTML))
        self.assertIn('<a href="https://t.me/Iran_gajet">📣 @Iran_gajet</a>', caption)

    def test_instagram_hashtag_is_removed_from_source_caption(self):
        self.assertEqual(clean_caption("ادرس فروشگااه/lead/51366 #اینستاگرام"), "")

    def test_extracts_photo_url_from_telegram_post(self):
        html = """<div class="tgme_widget_message_photo_wrap"
        style="width:640px;background-image:url('https://cdn4.telesco.pe/file/photo.jpg')"></div>"""
        node = BeautifulSoup(html, "html.parser").div
        self.assertEqual(
            photo_url_from_node(node),
            "https://cdn4.telesco.pe/file/photo.jpg",
        )

    def test_caption_removes_duplicate_abbreviated_prices_and_source_tags(self):
        caption = build_caption(
            "🔥 ۵.۷۸۹ میلیون ۷.۶۳۹ میلیون 🚚 ارسال سریع و ارزان | 💳 پرداخت درب منزل #پیامرسانیداخلی",
            "https://seller.affdn.ir/fastcart/51366",
            product_details={
                "title": "گیم استیک M15 مدل 51366",
                "original_price": "7,639,000 تومان",
                "discounted_price": "5,789,000 تومان",
            },
        )
        self.assertNotIn("۵.۷۸۹ میلیون", caption)
        self.assertNotIn("۷.۶۳۹ میلیون", caption)
        self.assertNotIn("#پیامرسانیداخلی", caption)
        self.assertNotIn("💳 پرداخت درب منزل", caption)
        self.assertTrue(caption.rstrip().endswith(CHANNEL_FOLLOW_HTML))

if __name__ == "__main__":
    unittest.main()
