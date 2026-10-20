import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from offerchin_audio import write_original_soundtrack

from short_video import (
    YOUTUBE_API_URL,
    YOUTUBE_TOKEN_URL,
    YOUTUBE_UPLOAD_URL,
    build_vertical_poster,
    telegram_video_review_available,
    update_youtube_video_description,
    upload_youtube_video,
    delete_youtube_video,
)


class FakeResponse:
    def __init__(self, payload=None, *, headers=None, status_code=200):
        self._payload = payload or {}
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeYouTubeHTTP:
    def __init__(self):
        self.posts = []
        self.puts = []
        self.gets = []
        self.deletes = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if url == YOUTUBE_API_URL:
            video_id = kwargs.get("params", {}).get("id", "testVideo123")
            return FakeResponse({"items": [{
                "id": video_id,
                "snippet": {
                    "title": "Existing title",
                    "description": "Old description",
                    "categoryId": "22",
                    "tags": ["آفرچین", "تخفیف"],
                    "defaultLanguage": "fa",
                },
            }]})
        raise AssertionError(f"Unexpected GET: {url}")

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url == YOUTUBE_TOKEN_URL:
            return FakeResponse({"access_token": "test-token"})
        if url == YOUTUBE_UPLOAD_URL:
            return FakeResponse({}, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"})
        raise AssertionError(f"Unexpected POST: {url}")

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        if url == YOUTUBE_API_URL:
            return FakeResponse({"id": kwargs.get("json", {}).get("id", "testVideo123")})
        return FakeResponse({"id": "testVideo123"})

    def delete(self, url, **kwargs):
        self.deletes.append((url, kwargs))
        return FakeResponse({}, status_code=204)


class ShortVideoTests(unittest.TestCase):
    def test_original_soundtrack_is_stereo_and_non_silent(self):
        import wave

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original-jingle.wav"
            written = write_original_soundtrack(path, duration_seconds=5)
            self.assertTrue(written.is_file())
            with wave.open(str(written), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 5.0, delta=0.05)
                self.assertGreater(wav.getnframes(), 100_000)
            self.assertGreater(path.stat().st_size, 100_000)

    def test_watermark_places_platform_marks_before_each_channel_id(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        poster = Image.open(io.BytesIO(build_vertical_poster(stream.getvalue(), 50))).convert("RGB")

        # Both platform marks now sit above the product card in the upper-left panel.
        self.assertEqual(poster.getpixel((61, 38)), (36, 161, 222))
        self.assertEqual(poster.getpixel((60, 86)), (0, 184, 148))

    def test_discount_is_drawn_inside_red_comic_burst(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        poster = Image.open(io.BytesIO(build_vertical_poster(stream.getvalue(), 76))).convert("RGB")

        # The upper-right region should contain a clearly visible red burst, not the old green pill.
        crop = poster.crop((455, 125, 710, 325))
        red_pixels = sum(
            1
            for red, green, blue in crop.getdata()
            if red > 120 and red > green * 1.6 and red > blue * 1.5
        )
        self.assertGreater(red_pixels, 1500)
        self.assertEqual(poster.size, (720, 1280))

    def test_private_review_is_disabled_until_both_settings_exist(self):
        self.assertFalse(telegram_video_review_available({}))
        self.assertFalse(telegram_video_review_available({"TELEGRAM_BOT_TOKEN": "token"}))
        self.assertTrue(telegram_video_review_available({
            "TELEGRAM_BOT_TOKEN": "token",
            "AFFILIO_VIDEO_REVIEW_CHAT_ID": "12345",
        }))

    def test_delete_youtube_video_uses_authorized_permanent_delete_endpoint(self):
        http = FakeYouTubeHTTP()
        result = delete_youtube_video(
            "testVideo123",
            session=http,
            env={
                "YOUTUBE_CLIENT_ID": "test-client",
                "YOUTUBE_CLIENT_SECRET": "test-secret",
                "YOUTUBE_REFRESH_TOKEN": "test-refresh",
            },
        )
        self.assertEqual(result, "deleted")
        url, request = http.deletes[0]
        self.assertEqual(url, YOUTUBE_API_URL)
        self.assertEqual(request["params"], {"id": "testVideo123"})
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-token")
        self.assertNotIn("json", request)

    def test_youtube_uploader_accepts_source_specific_description(self):
        http = FakeYouTubeHTTP()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.mp4"
            path.write_bytes(b"test-video")
            upload_youtube_video(
                path,
                "نمونه محصول دیجی‌کالا",
                25,
                description="عضویت از یوتیوب: https://t.me/+source_youtube",
                session=http,
                env={
                    "YOUTUBE_CLIENT_ID": "test-client",
                    "YOUTUBE_CLIENT_SECRET": "test-secret",
                    "YOUTUBE_REFRESH_TOKEN": "test-refresh",
                    "YOUTUBE_PRIVACY_STATUS": "unlisted",
                },
            )
        upload_request = next(kwargs for url, kwargs in http.posts if url == YOUTUBE_UPLOAD_URL)
        self.assertEqual(
            upload_request["json"]["snippet"]["description"],
            "عضویت از یوتیوب: https://t.me/+source_youtube",
        )


    def test_description_update_preserves_existing_video_metadata(self):
        http = FakeYouTubeHTTP()
        description = (
            "پیشنهادهای کاربردی و تخفیف‌های منتخب دیجی‌کالا را در آفِرچین دنبال کنید.\n\n"
            "کانال تلگرام:\nhttps://t.me/OfferChin\n"
            "کانال بله:\nhttps://ble.ir/OfferChin\n"
            "آپارات:\nhttps://www.aparat.com/OfferChin"
        )
        self.assertTrue(update_youtube_video_description(
            "testVideo123",
            description,
            session=http,
            env={
                "YOUTUBE_CLIENT_ID": "test-client",
                "YOUTUBE_CLIENT_SECRET": "test-secret",
                "YOUTUBE_REFRESH_TOKEN": "test-refresh",
            },
        ))
        api_update = next(kwargs for url, kwargs in http.puts if url == YOUTUBE_API_URL)
        self.assertEqual(api_update["params"], {"part": "snippet"})
        self.assertEqual(api_update["json"]["snippet"]["title"], "Existing title")
        self.assertEqual(api_update["json"]["snippet"]["categoryId"], "22")
        self.assertEqual(api_update["json"]["snippet"]["tags"], ["آفرچین", "تخفیف"])
        self.assertEqual(api_update["json"]["snippet"]["defaultLanguage"], "fa")
        self.assertEqual(api_update["json"]["snippet"]["description"], description)

    def test_default_youtube_description_uses_all_three_public_channel_links(self):
        http = FakeYouTubeHTTP()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.mp4"
            path.write_bytes(b"test-video")
            upload_youtube_video(
                path,
                "نمونه محصول دیجی‌کالا",
                25,
                session=http,
                env={
                    "YOUTUBE_CLIENT_ID": "test-client",
                    "YOUTUBE_CLIENT_SECRET": "test-secret",
                    "YOUTUBE_REFRESH_TOKEN": "test-refresh",
                    "YOUTUBE_PRIVACY_STATUS": "unlisted",
                },
            )
        upload_request = next(kwargs for url, kwargs in http.posts if url == YOUTUBE_UPLOAD_URL)
        description = upload_request["json"]["snippet"]["description"]
        self.assertIn("کانال تلگرام:\nhttps://t.me/OfferChin", description)
        self.assertIn("کانال بله:\nhttps://ble.ir/OfferChin", description)
        self.assertIn("آپارات:\nhttps://www.aparat.com/OfferChin", description)
        self.assertNotIn("قیمت، موجودی و شرایط تخفیف", description)

    def test_youtube_public_description_has_no_affiliate_disclosure(self):
        http = FakeYouTubeHTTP()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.mp4"
            path.write_bytes(b"test-video")
            result = upload_youtube_video(
                path,
                "نمونه محصول دیجی‌کالا",
                25,
                session=http,
                env={
                    "YOUTUBE_CLIENT_ID": "test-client",
                    "YOUTUBE_CLIENT_SECRET": "test-secret",
                    "YOUTUBE_REFRESH_TOKEN": "test-refresh",
                    "YOUTUBE_PRIVACY_STATUS": "unlisted",
                },
            )
        self.assertEqual(result["video_id"], "testVideo123")
        upload_request = next(kwargs for url, kwargs in http.posts if url == YOUTUBE_UPLOAD_URL)
        description = upload_request["json"]["snippet"]["description"]
        self.assertNotIn("همکاری در فروش", description)
        self.assertNotIn("کمیسیون", description)
        self.assertIn("دیجی‌کالا", description)
        self.assertIn("https://t.me/OfferChin", description)


if __name__ == "__main__":
    unittest.main()
