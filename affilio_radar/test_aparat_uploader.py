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


    def test_set_aparat_video_private_preserves_metadata_and_disables_sharing(self):
        from aparat_uploader import set_aparat_video_private

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.posts = []
            def get(self, url, **kwargs):
                self.detail_url = url
                return FakeResponse({"data": {
                    "id": 451,
                    "title": "پیشنهاد دیجی‌کالا",
                    "description": "قیمت روز را بررسی کنید",
                    "kids_friendly": True,
                    "category": {"id": 5},
                    "playList": {"data": {"id": 99}},
                    "tags": ["آفِرچین", "دیجی‌کالا"],
                    "comment_enable": "yes",
                }})
            def post(self, url, **kwargs):
                self.posts.append((url, kwargs))
                return FakeResponse({"success": True})

        session = FakeSession()
        changed = set_aparat_video_private(
            "a1b2c3",
            session=session,
            env={"APARAT_COOKIE_HEADER": "AuthV1=test-session; AFCN=test"},
        )

        self.assertTrue(changed)
        self.assertTrue(session.detail_url.endswith("/api/fa/v1/video/video/show/videohash/a1b2c3"))
        url, kwargs = session.posts[0]
        self.assertTrue(url.endswith("/api/fa/v1/video/video/edit/videohash/a1b2c3"))
        self.assertTrue(kwargs["json"]["video_pass"])
        self.assertEqual(kwargs["json"]["title"], "پیشنهاد دیجی‌کالا")


if __name__ == "__main__":
    unittest.main()
