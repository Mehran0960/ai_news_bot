import unittest

from aparat_uploader import _approved_upload_server, aparat_credentials_available


class AparatUploaderTests(unittest.TestCase):
    def test_auth_cookie_enables_upload_integration(self):
        self.assertTrue(aparat_credentials_available({
            "APARAT_COOKIE_HEADER": "AuthV1=example-session; AFCN=offerchin",
        }))

    def test_empty_or_incomplete_cookie_does_not_enable_upload(self):
        self.assertFalse(aparat_credentials_available({}))
        self.assertFalse(aparat_credentials_available({"APARAT_COOKIE_HEADER": "AFCN=offerchin"}))

    def test_cookie_header_rejects_newlines(self):
        self.assertFalse(aparat_credentials_available({
            "APARAT_COOKIE_HEADER": "AuthV1=example-session\nInjected: bad",
        }))

    def test_only_https_aparat_upload_hosts_are_accepted(self):
        self.assertEqual(_approved_upload_server("https://upload.aparat.com"), "https://upload.aparat.com")
        with self.assertRaises(RuntimeError):
            _approved_upload_server("http://upload.aparat.com")
        with self.assertRaises(RuntimeError):
            _approved_upload_server("https://upload.example.com")


if __name__ == "__main__":
    unittest.main()
