import unittest

from relay_botapi import (
    extract_product_refs,
    make_affiliate_url,
    normalize_store_host,
    resolve_product_ref,
    clean_caption,
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

if __name__ == "__main__":
    unittest.main()
