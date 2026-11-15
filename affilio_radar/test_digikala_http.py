from __future__ import annotations

import unittest

try:
    from . import digikala_http
except ImportError:
    import digikala_http


class DigiKalaHttpSessionTests(unittest.TestCase):
    def test_session_includes_browser_api_headers(self):
        session = digikala_http.new_digikala_session()
        try:
            headers = session.headers
            self.assertEqual(headers.get("Accept"), "application/json")
            self.assertEqual(headers.get("Accept-Language"), "fa-IR,fa;q=0.9,en;q=0.8")
            self.assertEqual(headers.get("Origin"), "https://www.digikala.com")
            self.assertEqual(headers.get("Referer"), "https://www.digikala.com/")
            self.assertEqual(headers.get("x-web-client"), "desktop")
            self.assertEqual(headers.get("x-web-client-id"), "web")
            self.assertEqual(headers.get("sec-fetch-mode"), "cors")
            self.assertEqual(headers.get("sec-fetch-site"), "same-site")
        finally:
            session.close()

    def test_session_uses_chrome_impersonation_when_dependency_is_installed(self):
        if digikala_http.curl_requests is None:
            self.skipTest("curl_cffi is not installed in this environment")
        session = digikala_http.new_digikala_session()
        try:
            self.assertTrue(session.__class__.__module__.startswith("curl_cffi"))
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
