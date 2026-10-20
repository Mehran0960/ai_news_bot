import json
import unittest

from aparat_uploader import _approved_upload_server, _cookie_header, aparat_credentials_available


class AparatUploaderTests(unittest.TestCase):
    def test_auth_cookie_enables_upload_integration(self):
        self.assertTrue(aparat_credentials_available({
            "APARAT_COOKIE_HEADER": "AuthV1=example-session; AFCN=offerchin",
        }))

    def test_empty_or_incomplete_cookie_does_not_enable_upload(self):
        self.assertFalse(aparat_credentials_available({}))
        self.assertFalse(aparat_credentials_available({"APARAT_COOKIE_HEADER": "AFCN=offerchin"}))

    def test_bare_jwt_is_normalized_to_authv1_cookie(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        env = {"APARAT_COOKIE_HEADER": token}
        self.assertTrue(aparat_credentials_available(env))
        self.assertEqual(_cookie_header(env), f"AuthV1={token}")

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

    def test_find_uploaded_video_matches_exact_title_and_returns_uid(self):
        from aparat_uploader import find_uploaded_aparat_video, APARAT_MY_VIDEOS_URL

        class FakeResponse:
            def raise_for_status(self):
                return None
            def json(self):
                return {"included": [
                    {"id": "123", "attributes": {"title": "Other video", "uid": "otheruid"}},
                    {"id": "456", "attributes": {"title": "  تست محصول  ", "uid": "realuid"}},
                ]}

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.urls = []
            def get(self, url, **kwargs):
                self.urls.append(url)
                return FakeResponse()

        session = FakeSession()
        found = find_uploaded_aparat_video(
            "تست محصول",
            session=session,
            env={"APARAT_COOKIE_HEADER": "AuthV1=test-session"},
        )
        self.assertEqual(session.urls, [APARAT_MY_VIDEOS_URL])
        self.assertEqual(found["video_hash"], "realuid")
        self.assertEqual(found["url"], "https://www.aparat.com/v/realuid")
        self.assertEqual(found["video_id"], "456")

    def test_find_uploaded_video_can_match_by_record_id(self):
        from aparat_uploader import find_uploaded_aparat_video

        class FakeResponse:
            def raise_for_status(self):
                return None
            def json(self):
                return {"included": [
                    {"id": "457", "attributes": {"title": "Different shown title", "uid": "uid457"}}
                ]}

        class FakeSession:
            def __init__(self):
                self.headers = {}
            def get(self, url, **kwargs):
                return FakeResponse()

        found = find_uploaded_aparat_video(
            "Original title",
            video_id="457",
            session=FakeSession(),
            env={"APARAT_COOKIE_HEADER": "AuthV1=test-session"},
        )
        self.assertEqual(found["video_hash"], "uid457")
        self.assertEqual(found["url"], "https://www.aparat.com/v/uid457")


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
        payload = json.loads(kwargs["data"])
        self.assertTrue(payload["video_pass"])
        self.assertEqual(payload["title"], "پیشنهاد دیجی‌کالا")


if __name__ == "__main__":
    unittest.main()
