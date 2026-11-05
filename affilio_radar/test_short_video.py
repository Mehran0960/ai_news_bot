import io
import tempfile
import unittest
import requests
from unittest import mock
from pathlib import Path

from PIL import Image, ImageDraw
from offerchin_audio import write_original_soundtrack

from short_video import (
    YOUTUBE_API_URL,
    YOUTUBE_TOKEN_URL,
    YOUTUBE_UPLOAD_URL,
    build_vertical_poster,
    format_persian_price,
    format_persian_discount,
    _font,
    _rtl_layout_kwargs,
    _shape_rtl,
    PERSIAN_TEXT_RAQM_AVAILABLE,
    _resolve_ffmpeg_binary,
    telegram_video_review_available,
    update_youtube_video_description,
    upload_youtube_video,
    _raise_for_youtube_http_error,
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
    def setUp(self):
        # Unit tests run without network-fetched workflow assets; production staging
        # validates the real DigiPay SVG before any video adapter is called.
        fake_logo = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
        self.digipay_logo_patch = mock.patch(
            "offerchin_visuals._load_digipay_logo",
            return_value=fake_logo,
        )
        self.digipay_logo_patch.start()
        self.addCleanup(self.digipay_logo_patch.stop)

    def test_video_poster_fails_closed_when_digipay_logo_is_missing(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        with mock.patch("offerchin_visuals._load_digipay_logo", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "official DigiPay logo unavailable"):
                build_vertical_poster(stream.getvalue(), 50)

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

    def test_watermark_places_platform_marks_in_visible_top_safe_area(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        poster = Image.open(io.BytesIO(build_vertical_poster(stream.getvalue(), 50))).convert("RGB")

        # Both platform marks now sit in the dedicated strip directly below the title.
        self.assertEqual(poster.getpixel((132, 191)), (36, 161, 222))
        self.assertEqual(poster.getpixel((386, 191)), (0, 184, 148))

    def test_retailer_logo_and_discount_use_the_same_upper_corner_positions_as_channel_images(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        digikala = Image.open(io.BytesIO(build_vertical_poster(
            stream.getvalue(), 50, merchant="دیجی‌کالا",
        ))).convert("RGB")
        snappshop = Image.open(io.BytesIO(build_vertical_poster(
            stream.getvalue(), 50, merchant="اسنپ‌شاپ",
        ))).convert("RGB")

        # For a 400x500 source, the fitted product photo is 333x416 at (193,246).
        # The retailer tile is upper-left and the equal-sized discount tile upper-right.
        retailer_crop = digikala.crop((202, 254, 334, 306))
        digikala_discount_crop = digikala.crop((388, 254, 520, 306))
        snappshop_discount_crop = snappshop.crop((388, 254, 520, 306))
        red_pixels = sum(1 for red, green, blue in retailer_crop.getdata() if red > 150 and red > green * 1.7 and red > blue * 1.5)
        digikala_discount_pixels = sum(1 for red, green, blue in digikala_discount_crop.getdata() if red > 150 and red > green * 1.7 and red > blue * 1.5)
        snappshop_discount_pixels = sum(1 for red, green, blue in snappshop_discount_crop.getdata() if blue > 90 and red > green * 1.6 and blue > green * 1.6)
        self.assertGreater(red_pixels, 250, "video poster must retain the official DigiKala retailer logo")
        self.assertGreater(digikala_discount_pixels, 1500, "DigiKala discount tile must sit in the upper-right")
        self.assertGreater(snappshop_discount_pixels, 1500, "SnappShop discount tile must sit in the upper-right")

    def test_digipay_badge_sits_directly_below_the_retailer_logo(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        fake_logo = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        with mock.patch("offerchin_visuals._load_digipay_logo", return_value=fake_logo):
            poster = Image.open(io.BytesIO(
                build_vertical_poster(stream.getvalue(), 76)
            )).convert("RGB")

        # The DigiPay tile now follows the actual retailer-logo bounds at upper-left.
        blue_points = [
            (x, y)
            for y in range(300, 375)
            for x in range(198, 340)
            if (lambda p: p[2] > 150 and p[2] > p[0] * 1.8 and p[2] > p[1] * 1.2)(
                poster.getpixel((x, y))
            )
        ]
        self.assertGreater(len(blue_points), 1_000)
        self.assertEqual(poster.size, (720, 1280))

    def test_discount_value_replaces_original_price_line(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        drawn_text = []
        original_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, value, *args, **kwargs):
            drawn_text.append(str(value))
            return original_text(draw, xy, value, *args, **kwargs)

        with mock.patch.object(ImageDraw.ImageDraw, "text", capture_text):
            build_vertical_poster(
                stream.getvalue(),
                76,
                current_price=1_234_000,
                original_price=5_000_000,
            )

        self.assertTrue(any("تخفیف" in value or "فیفخت" in value for value in drawn_text))
        self.assertFalse(any("قیمت اصلی" in value or "یلصا تمیق" in value for value in drawn_text))
        self.assertEqual(format_persian_discount(76), "🔥 ۷۶٪ تخفیف")
        self.assertEqual(format_persian_discount(0), "")
        self.assertEqual(format_persian_discount(101), "")

    def test_format_persian_discount_rejects_invalid_values(self):
        self.assertEqual(format_persian_discount(79), "🔥 ۷۹٪ تخفیف")
        self.assertEqual(format_persian_discount("45"), "🔥 ۴۵٪ تخفیف")
        self.assertEqual(format_persian_discount(None), "")
        self.assertEqual(format_persian_discount(-2), "")

    def test_compact_badge_dimensions_legacy_helper_retains_compatibility(self):
        from offerchin_visuals import discount_badge_dimensions_for_reference_height

        self.assertEqual(discount_badge_dimensions_for_reference_height(88), (118, 88))
        self.assertEqual(discount_badge_dimensions_for_reference_height(67), (90, 67))
        # Very small source artwork keeps the discount label readable.
        self.assertEqual(discount_badge_dimensions_for_reference_height(48), (74, 55))

    def test_discount_badge_can_match_exact_retailer_bounds(self):
        from offerchin_visuals import discount_badge_dimensions_for_reference_bounds

        self.assertEqual(discount_badge_dimensions_for_reference_bounds(280, 88), (280, 88))
        self.assertEqual(discount_badge_dimensions_for_reference_bounds(124, 48), (124, 48))

    def test_snappshop_video_keeps_store_tile_and_places_digipay_below_it(self):
        import short_video

        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        original_retailer_draw = short_video.draw_retailer_badge
        retailer_bounds_seen = []

        def capture_retailer_bounds(*args, **kwargs):
            bounds = original_retailer_draw(*args, **kwargs)
            retailer_bounds_seen.append(bounds)
            return bounds

        with (
            mock.patch(
                "short_video.draw_retailer_badge",
                side_effect=capture_retailer_bounds,
            ) as retailer_draw,
            mock.patch(
                "short_video.draw_digipay_badge",
                wraps=short_video.draw_digipay_badge,
            ) as digipay_draw,
        ):
            poster = Image.open(io.BytesIO(build_vertical_poster(
                stream.getvalue(), 42, merchant="اسنپ‌شاپ",
            ))).convert("RGB")

        retailer_bounds = retailer_bounds_seen[0] if retailer_bounds_seen else None
        self.assertIsNotNone(retailer_bounds, "SnappShop retailer mark must be present")
        left, top, width, height = retailer_bounds
        expected_gap = max(4, int(height * 0.08))
        self.assertEqual(digipay_draw.call_count, 1)
        self.assertEqual(
            digipay_draw.call_args.args[1:5],
            (left, top + height + expected_gap, width, height),
            "DigiPay must sit directly below the visible SnappShop logo bounds",
        )
        self.assertEqual(poster.size, (720, 1280))

    def test_persian_text_uses_one_bidi_engine_without_double_reordering(self):
        from PIL import ImageFont

        sample = "خرید از دیجی‌کالا"
        font = _font(28)
        if PERSIAN_TEXT_RAQM_AVAILABLE:
            self.assertEqual(font.layout_engine, ImageFont.Layout.RAQM)
            self.assertEqual(_shape_rtl(sample), sample)
            self.assertEqual(_rtl_layout_kwargs(), {"direction": "rtl"})
        else:
            self.assertEqual(font.layout_engine, ImageFont.Layout.BASIC)
            self.assertNotEqual(_shape_rtl(sample), sample)
            self.assertEqual(_rtl_layout_kwargs(), {})

    def test_video_poster_shows_product_title_prices_and_channel_cta(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        poster = Image.open(io.BytesIO(build_vertical_poster(
            stream.getvalue(),
            80,
            title="هدفون بلوتوثی نمونه مدل X",
            current_price=1_999_000,
            original_price=10_000_000,
        ))).convert("RGB")

        self.assertEqual(format_persian_price(1_999_000), "۱٬۹۹۹٬۰۰۰")
        # Top channel links are placed in their own compact strip, away from platform UI overlays.
        background_sample = poster.getpixel((680, 1150))
        self.assertGreater(min(background_sample), 45)
        self.assertNotEqual(background_sample, (14, 28, 22))
        # The price panel has a consistent pale-green surface distinct from the dark background.
        price_panel = poster.getpixel((45, 705))
        self.assertGreater(price_panel[1], price_panel[0])
        self.assertEqual(poster.size, (720, 1280))

    def test_ffmpeg_resolver_falls_back_to_bundled_binary(self):
        with (
            mock.patch("short_video.shutil.which", return_value=None),
            mock.patch("short_video._bundled_ffmpeg_binary", return_value="/bundled/ffmpeg"),
        ):
            self.assertEqual(_resolve_ffmpeg_binary(), "/bundled/ffmpeg")

    def test_private_review_is_disabled_until_both_settings_exist(self):
        self.assertFalse(telegram_video_review_available({}))
        self.assertFalse(telegram_video_review_available({"TELEGRAM_BOT_TOKEN": "token"}))
        self.assertTrue(telegram_video_review_available({
            "TELEGRAM_BOT_TOKEN": "token",
            "AFFILIO_VIDEO_REVIEW_CHAT_ID": "12345",
        }))

    def test_youtube_video_removal_is_refused_without_network_access(self):
        class MustNotBeCalledHTTP:
            def __getattr__(self, name):
                raise AssertionError(f"unexpected network call: {name}")

        with self.assertRaisesRegex(RuntimeError, "permanent-retention policy"):
            delete_youtube_video(
                "testVideo123",
                session=MustNotBeCalledHTTP(),
                env={
                    "YOUTUBE_CLIENT_ID": "test-client",
                    "YOUTUBE_CLIENT_SECRET": "test-secret",
                    "YOUTUBE_REFRESH_TOKEN": "test-refresh",
                },
            )

    def test_youtube_http_errors_include_google_reason_and_message_without_url(self):
        response = FakeResponse({
            "error": {
                "code": 403,
                "message": "The YouTube Data API quota has been exceeded.",
                "errors": [{
                    "message": "The request cannot be completed because quota was exceeded.",
                    "reason": "quotaExceeded",
                }],
            }
        }, status_code=403)

        with self.assertRaises(requests.HTTPError) as caught:
            _raise_for_youtube_http_error(response, "video content upload")

        message = str(caught.exception)
        self.assertIn("YouTube video content upload HTTP 403", message)
        self.assertIn("reason=quotaExceeded", message)
        self.assertIn("quota was exceeded", message)
        self.assertNotIn("https://", message)

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
