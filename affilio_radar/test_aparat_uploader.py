import unittest

from aparat_uploader import APARAT_MY_VIDEOS_URL, delete_aparat_video


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class AparatDeletionTests(unittest.TestCase):
    def test_uses_account_list_delete_url_for_exact_video(self):
        session = FakeSession([
            FakeResponse({
                "included": [
                    {"id": "1", "attributes": {"hash": "other", "delete_url": "/delete/other"}},
                    {"id": "2", "attributes": {"hash": "offerchin-video", "delete_url": "/api/video/delete/offerchin-video"}},
                ]
            }),
            FakeResponse({"data": {"attributes": {"type": "success"}}}),
        ])
        result = delete_aparat_video(
            "offerchin-video",
            session=session,
            env={"APARAT_COOKIE_HEADER": "AuthV1=test-session"},
        )
        self.assertEqual(result, "deleted")
        self.assertEqual(session.calls[0][0], APARAT_MY_VIDEOS_URL)
        self.assertEqual(
            session.calls[1][0],
            "https://www.aparat.com/api/video/delete/offerchin-video",
        )

    def test_refuses_to_guess_or_follow_external_delete_endpoint(self):
        session = FakeSession([
            FakeResponse({
                "included": [
                    {
                        "id": "2",
                        "attributes": {
                            "hash": "offerchin-video",
                            "delete_url": "https://example.invalid/delete/offerchin-video",
                        },
                    }
                ]
            }),
        ])
        with self.assertRaises(RuntimeError):
            delete_aparat_video(
                "offerchin-video",
                session=session,
                env={"APARAT_COOKIE_HEADER": "AuthV1=test-session"},
            )
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
