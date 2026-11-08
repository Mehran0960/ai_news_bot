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
    video_purchase_cta_text,
    TITLE_FONT_PATH,
    VIDEO_LOGO_COLUMN_WIDTH,
    VIDEO_LOGO_TEXT_GAP,
    _title_font,
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

    def test_product_video_default_is_twelve_seconds_and_selected_funk_track_matches(self):
        import inspect
        import short_video
        import wave

        self.assertEqual(short_video.DURATION_SECONDS, 12)
        self.assertEqual(
            inspect.signature(short_video.render_short_video).parameters["duration_seconds"].default,
            12,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected-funk.wav"
            write_original_soundtrack(path, duration_seconds=12)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 22050)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 12.0, delta=0.05)
                self.assertGreater(wav.getnframes(), 250_000)
            first = path.read_bytes()
            second = Path(directory) / "selected-funk-repeat.wav"
            write_original_soundtrack(second, duration_seconds=12)
            self.assertEqual(first, second.read_bytes(), "the soundtrack must render deterministically")
            self.assertGreater(len(first), 500_000)

    def test_render_short_video_normalizes_soundtrack_and_keeps_twelve_second_cut(self):
        import short_video

        commands = []

        def fake_soundtrack(path, duration):
            self.assertEqual(duration, 12)
            Path(path).write_bytes(b"test-wav")
            return Path(path)

        def fake_ffmpeg(command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"x" * 2048)
            return mock.Mock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.mp4"
            with (
                mock.patch("short_video._resolve_ffmpeg_binary", return_value="/fake/ffmpeg"),
                mock.patch("short_video.build_vertical_poster", return_value=b"test-poster"),
                mock.patch("short_video.write_original_soundtrack", side_effect=fake_soundtrack),
                mock.patch("short_video.subprocess.run", side_effect=fake_ffmpeg),
            ):
                rendered = short_video.render_short_video(
                    b"test-image",
                    50,
                    output,
                    duration_seconds=12,
                    fps=24,
                )

            self.assertEqual(rendered, output)
            self.assertGreater(output.stat().st_size, 1024)

        self.assertEqual(len(commands), 1)
        command = commands[0]
        audio_filter = command[command.index("-af") + 1]
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", audio_filter)
        self.assertIn("afade=t=in:st=0:d=0.18", audio_filter)
        self.assertIn("afade=t=out:st=11.580:d=0.40", audio_filter)
        self.assertEqual(command[command.index("-frames:v") + 1], "288")
        self.assertIn("1:a:0", command)

    def test_render_short_video_normalizes_soundtrack_and_keeps_twelve_second_cut(self):
        import short_video

        commands = []

        def fake_soundtrack(path, duration):
            self.assertEqual(duration, 12)
            Path(path).write_bytes(b"test-wav")
            return Path(path)

        def fake_ffmpeg(command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"x" * 2048)
            return mock.Mock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.mp4"
            with (
                mock.patch("short_video._resolve_ffmpeg_binary", return_value="/fake/ffmpeg"),
                mock.patch("short_video.build_vertical_poster", return_value=b"test-poster"),
                mock.patch("short_video.write_original_soundtrack", side_effect=fake_soundtrack),
                mock.patch("short_video.subprocess.run", side_effect=fake_ffmpeg),
            ):
                rendered = short_video.render_short_video(
                    b"test-image",
                    50,
                    output,
                    duration_seconds=12,
                    fps=24,
                )

            self.assertEqual(rendered, output)
            self.assertGreater(output.stat().st_size, 1024)

        self.assertEqual(len(commands), 1)
        command = commands[0]
        audio_filter = command[command.index("-af") + 1]
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", audio_filter)
        self.assertIn("afade=t=in:st=0:d=0.18", audio_filter)
        self.assertIn("afade=t=out:st=11.580:d=0.40", audio_filter)
        self.assertEqual(command[command.index("-frames:v") + 1], "288")
        self.assertIn("1:a:0", command)

    def test_real_twelve_second_render_contains_audio_and_video_streams(self):
        import short_video
        import subprocess

        image = Image.new("RGB", (400, 500), (35, 70, 55))
        stream = io.BytesIO()
        image.save(stream, format="PNG")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "real-render.mp4"
            rendered = short_video.render_short_video(
                stream.getvalue(),
                50,
                output,
                title="نمونهٔ آزمون رندر آفِرچین",
                current_price=100000,
                original_price=200000,
                destination_platform="youtube",
                duration_seconds=12,
                fps=24,
            )
            self.assertTrue(rendered.is_file())
            self.assertGreater(rendered.stat().st_size, 20_000)

            binary = short_video._resolve_ffmpeg_binary()
            probe = subprocess.run(
                [binary, "-hide_banner", "-i", str(rendered), "-f", "null", "-"],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            details = probe.stderr or ""
            self.assertEqual(probe.returncode, 0, details[:2000])
            self.assertIn("Video:", details)
            self.assertIn("Audio:", details)
            self.assertRegex(details, r"Duration: 00:00:12(?:\.00)?")

    def test_watermark_places_other_channel_marks_in_a_vertical_youtube_safe_area(self):
        import short_video

        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        with mock.patch(
            "short_video._draw_video_channel_logo",
            wraps=short_video._draw_video_channel_logo,
        ) as draw_logo:
            build_vertical_poster(stream.getvalue(), 50)

        drawn_platforms = [call.args[1] for call in draw_logo.call_args_list]
        self.assertEqual(drawn_platforms, ["telegram", "bale", "rubika", "aparat"])
        self.assertNotIn("youtube", drawn_platforms, "a YouTube Short must not list its own channel")
        # Official artwork and its backing fit cleanly into four non-overlapping
        # rows within the channel identity panel.
        self.assertEqual([call.args[3] for call in draw_logo.call_args_list], [188, 214, 240, 266])
        self.assertEqual([call.args[4] for call in draw_logo.call_args_list], [20, 20, 20, 20])
        self.assertEqual([call.kwargs["max_width"] for call in draw_logo.call_args_list], [96, 96, 96, 96])

    
    def test_bundled_official_platform_marks_are_icon_only_and_keep_their_ratios(self):
        import offerchin_visuals

        expected_platforms = ("telegram", "bale", "rubika", "youtube", "aparat")
        for platform in expected_platforms:
            with self.subTest(platform=platform):
                source = offerchin_visuals._load_platform_logo(platform)
                self.assertIsNotNone(source, f"{platform} official logo must be bundled locally")
                fitted = offerchin_visuals.fit_platform_logo(platform, 20, 96)
                self.assertIsNotNone(fitted)
                self.assertLessEqual(fitted.height, 20)
                self.assertLessEqual(fitted.width, 96)
                ratio = source.width / source.height
                self.assertLess(
                    ratio, 1.8,
                    f"{platform} must render its pictorial symbol only, without a horizontal name/wordmark",
                )
                self.assertAlmostEqual(
                    fitted.width / fitted.height,
                    ratio,
                    delta=0.03,
                    msg=f"{platform} icon was stretched or forced into a different aspect ratio",
                )

        youtube = offerchin_visuals._load_platform_logo("youtube")
        self.assertGreater(youtube.width / youtube.height, 1.2)
        self.assertLess(youtube.width / youtube.height, 1.8)
        bale = offerchin_visuals._load_platform_logo("bale")
        self.assertAlmostEqual(bale.width / bale.height, 1.0, delta=0.03)
        aparat = offerchin_visuals._load_platform_logo("aparat")
        self.assertLess(aparat.width / aparat.height, 1.2)

    def test_official_svg_symbol_crops_change_only_the_viewport_and_keep_full_marks(self):
        import offerchin_visuals
        from xml.etree import ElementTree

        expected_viewboxes = {
            "bale": "54 4 32 32",
            "rubika": "783.5 0 495.39 543.02",
            "aparat": "56 0 24 25",
        }
        for platform, expected_viewbox in expected_viewboxes.items():
            with self.subTest(platform=platform):
                original_bytes = offerchin_visuals._PLATFORM_LOGO_PATHS[platform].read_bytes()
                original = ElementTree.fromstring(original_bytes)
                cropped = ElementTree.fromstring(
                    offerchin_visuals._icon_only_svg_payload(original_bytes, platform)
                )
                self.assertEqual(cropped.attrib.get("viewBox"), expected_viewbox)

                # The crop is a viewport change only: do not edit, recolour,
                # redraw, stretch, or remove any path from the official source.
                ns = "{http://www.w3.org/2000/svg}path"
                original_paths = [
                    (node.attrib.get("d"), node.attrib.get("fill"), node.attrib.get("transform"))
                    for node in original.findall(ns)
                ]
                cropped_paths = [
                    (node.attrib.get("d"), node.attrib.get("fill"), node.attrib.get("transform"))
                    for node in cropped.findall(ns)
                ]
                self.assertEqual(cropped_paths, original_paths)

        bale = offerchin_visuals._icon_only_svg_payload(
            offerchin_visuals._PLATFORM_LOGO_PATHS["bale"].read_bytes(), "bale"
        )
        bale_root = ElementTree.fromstring(bale)
        self.assertEqual(bale_root.attrib["width"], "512")
        self.assertEqual(bale_root.attrib["height"], "512")

    def test_youtube_official_play_button_crop_keeps_antialiased_edges(self):
        import offerchin_visuals

        # A one-pixel, lightly blended red fringe represents the edge pixels
        # of the official rounded play button against its white PNG canvas.
        image = Image.new("RGBA", (100, 80), (255, 255, 255, 255))
        ImageDraw.Draw(image).rectangle((20, 20, 79, 59), fill=(255, 0, 51, 255))
        fringe = (255, 220, 229, 255)
        image.putpixel((19, 20), fringe)
        image.putpixel((80, 59), fringe)

        cropped = offerchin_visuals._crop_youtube_play_icon(image)
        self.assertEqual(cropped.size, (62, 40))
        self.assertEqual(cropped.getpixel((0, 0)), fringe)
        self.assertEqual(cropped.getpixel((-1, -1)), fringe)

    def test_product_image_footer_uses_resolution_aware_readable_official_logo_sizes(self):
        import affilio_radar
        import offerchin_visuals

        small = offerchin_visuals.platform_footer_metrics(400)
        large = offerchin_visuals.platform_footer_metrics(1600)
        self.assertGreaterEqual(small["logo_height"], 16)
        self.assertGreater(large["logo_height"], small["logo_height"])
        self.assertLessEqual(large["logo_height"], 44)
        self.assertGreater(large["font_size"], small["font_size"])

        source = io.BytesIO()
        Image.new("RGB", (640, 800), (238, 241, 246)).save(source, format="JPEG")
        metrics = offerchin_visuals.platform_footer_metrics(640)
        with mock.patch(
            "affilio_radar._draw_platform_watermark_icon",
            wraps=affilio_radar._draw_platform_watermark_icon,
        ) as draw_logo:
            rendered = affilio_radar.build_discount_image(
                source.getvalue(), None, destination_platform="telegram",
            )
        with Image.open(io.BytesIO(rendered)) as result:
            self.assertEqual(result.size, (640, 800))
        self.assertEqual(
            [call.args[1] for call in draw_logo.call_args_list],
            ["bale", "rubika", "youtube", "aparat"],
        )
        self.assertEqual(
            [call.args[4] for call in draw_logo.call_args_list],
            [metrics["logo_height"]] * 4,
        )
        self.assertEqual(
            [call.kwargs["max_width"] for call in draw_logo.call_args_list],
            [metrics["logo_max_width"]] * 4,
        )

    def test_platform_footer_labels_are_only_bare_public_ids(self):
        import offerchin_visuals

        for platform, url, expected in (
            ("telegram", "https://t.me/OfferChin/", "t.me/OfferChin"),
            ("bale", "http://ble.ir/OfferChin/", "ble.ir/OfferChin"),
            ("rubika", "https://www.rubika.ir/offerchin/", "rubika.ir/offerchin"),
            ("youtube", "https://www.youtube.com/@offerchin/", "youtube.com/@offerchin"),
            ("aparat", "https://www.aparat.com/OfferChin/", "aparat.com/OfferChin"),
        ):
            with self.subTest(platform=platform):
                self.assertEqual(offerchin_visuals.platform_footer_label(platform, url), expected)
                self.assertNotRegex(offerchin_visuals.platform_footer_label(platform, url), r"(?i)^https?://")
                self.assertNotIn("www.", offerchin_visuals.platform_footer_label(platform, url))

    def test_each_public_platform_lists_every_other_media_and_never_itself(self):
        import offerchin_visuals

        expected = {
            "telegram": ["bale", "rubika", "youtube", "aparat"],
            "bale": ["telegram", "rubika", "youtube", "aparat"],
            "rubika": ["telegram", "bale", "youtube", "aparat"],
            "youtube": ["telegram", "bale", "rubika", "aparat"],
            "aparat": ["telegram", "bale", "rubika", "youtube"],
        }
        for destination, expected_platforms in expected.items():
            with self.subTest(destination=destination):
                links = offerchin_visuals.public_channel_links(destination)
                self.assertEqual([platform for platform, _url in links], expected_platforms)
                for _platform, url in links:
                    self.assertNotRegex(url, r"(?i)^https?://")
                    self.assertNotIn("www.", url)

    def test_platform_logo_fitting_keeps_the_youtube_play_icon_proportional(self):
        import offerchin_visuals

        youtube_icon = Image.new("RGBA", (140, 100), (255, 0, 0, 255))
        square_mark = Image.new("RGBA", (100, 100), (0, 100, 200, 255))
        with mock.patch(
            "offerchin_visuals._load_platform_logo",
            side_effect=lambda platform: youtube_icon if platform == "youtube" else square_mark,
        ):
            fitted_youtube = offerchin_visuals.fit_platform_logo("youtube", 18, 78)
            fitted_telegram = offerchin_visuals.fit_platform_logo("telegram", 18, 78)
            self.assertIsNotNone(fitted_youtube)
            self.assertIsNotNone(fitted_telegram)
            self.assertLessEqual(fitted_youtube.height, 18)
            self.assertLessEqual(fitted_youtube.width, 78)
            self.assertAlmostEqual(
                fitted_youtube.width / fitted_youtube.height,
                1.4,
                delta=0.05,
            )
            self.assertAlmostEqual(
                fitted_telegram.width / fitted_telegram.height,
                1.0,
                delta=0.05,
            )

            canvas = Image.new("RGB", (180, 48), (30, 30, 30))
            width, height = offerchin_visuals.draw_platform_logo(
                canvas, "youtube", 4, 4, 18, 78,
            )
            self.assertLess(width, height * 1.8)
            self.assertLessEqual(height, 24)

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

        # The extra blank line below the purchase CTA shifts the product card
        # and its retailer/discount tiles down by 22 pixels.
        retailer_crop = digikala.crop((220, 346, 344, 394))
        digikala_discount_crop = digikala.crop((375, 346, 499, 394))
        snappshop_discount_crop = snappshop.crop((375, 346, 499, 394))
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
            for y in range(370, 445)
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

    def test_video_poster_shows_product_title_prices_and_other_channel_ctas(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        drawn_text = []
        original_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, value, *args, **kwargs):
            drawn_text.append(str(value))
            return original_text(draw, xy, value, *args, **kwargs)

        with mock.patch.object(ImageDraw.ImageDraw, "text", capture_text):
            poster = Image.open(io.BytesIO(build_vertical_poster(
                stream.getvalue(),
                80,
                title="هدفون بلوتوثی نمونه مدل X",
                current_price=1_999_000,
                original_price=10_000_000,
            ))).convert("RGB")

        self.assertEqual(format_persian_price(1_999_000), "۱٬۹۹۹٬۰۰۰")
        for label in (
            "t.me/OfferChin", "ble.ir/OfferChin",
            "rubika.ir/offerchin", "aparat.com/OfferChin",
        ):
            self.assertTrue(any(label in value for value in drawn_text), label)
        self.assertFalse(any("youtube.com/@offerchin" in value for value in drawn_text))
        self.assertIn(_shape_rtl("لینک خرید: توضیحات کانال"), drawn_text)
        self.assertEqual(video_purchase_cta_text("youtube"), "لینک خرید: توضیحات کانال")
        self.assertFalse(any("OfferChin  •" in value for value in drawn_text))
        # The compact CTA panel stays above the product card and YouTube interface-safe area.
        background_sample = poster.getpixel((680, 1150))
        self.assertGreater(min(background_sample), 45)
        self.assertNotEqual(background_sample, (14, 28, 22))
        price_panel = poster.getpixel((45, 753))
        self.assertGreater(price_panel[1], price_panel[0])
        self.assertEqual(poster.size, (720, 1280))

    def test_video_persian_overlay_typography_and_cta_spacing_follow_product_title(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        captured = []
        original_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, value, *args, **kwargs):
            captured.append({
                "text": str(value),
                "font": kwargs.get("font"),
                "xy": xy,
                "stroke_width": kwargs.get("stroke_width", 0),
            })
            return original_text(draw, xy, value, *args, **kwargs)

        with mock.patch.object(ImageDraw.ImageDraw, "text", capture_text):
            build_vertical_poster(
                stream.getvalue(),
                80,
                title="هدفون بلوتوثی نمونه مدل X",
                current_price=1_999_000,
                merchant="دیجی‌کالا",
                destination_platform="youtube",
            )

        persian_draws = [
            item for item in captured
            if any("\\u0600" <= char <= "\\u06ff" for char in item["text"])
        ]
        self.assertTrue(persian_draws, "the poster must contain Persian overlay text")
        for item in persian_draws:
            self.assertIsNotNone(item["font"])
            self.assertEqual(
                item["font"].getname()[0],
                "Lalezar",
                f"Persian overlay must use the product-title font: {item['text']!r}",
            )

        title_draws = [item for item in persian_draws if item["xy"][1] in (65, 73)]
        self.assertTrue(title_draws, "product title must be drawn")
        self.assertTrue(all(item["stroke_width"] == 1 for item in title_draws))

        price_draw = next(item for item in persian_draws if item["xy"][1] == 831)
        self.assertEqual(price_draw["stroke_width"], 1)

        cta_draw = next(
            item for item in persian_draws
            if item["text"] == _shape_rtl("لینک خرید: توضیحات کانال")
        )
        first_channel_id = next(
            item for item in captured if item["text"] == "t.me/OfferChin"
        )
        self.assertEqual(first_channel_id["xy"][1] - cta_draw["xy"][1], 48)

    def test_video_channel_ids_share_a_fixed_column_for_both_destinations(self):
        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        original_text = ImageDraw.ImageDraw.text

        for destination, expected_ids in (
            ("youtube", {"t.me/OfferChin", "ble.ir/OfferChin", "rubika.ir/offerchin", "aparat.com/OfferChin"}),
            ("aparat", {"t.me/OfferChin", "ble.ir/OfferChin", "rubika.ir/offerchin", "youtube.com/@offerchin"}),
        ):
            captured = []

            def capture_text(draw, xy, value, *args, **kwargs):
                label = str(value)
                if label in expected_ids:
                    captured.append((xy[0], label))
                return original_text(draw, xy, value, *args, **kwargs)

            with mock.patch.object(ImageDraw.ImageDraw, "text", capture_text):
                build_vertical_poster(
                    stream.getvalue(), 50, destination_platform=destination
                )

            self.assertEqual({label for _x, label in captured}, expected_ids)
            self.assertEqual(len(captured), 4)
            expected_x = 64 + VIDEO_LOGO_COLUMN_WIDTH + VIDEO_LOGO_TEXT_GAP
            self.assertEqual({x for x, _label in captured}, {expected_x})

    def test_video_title_uses_the_bundled_lalezar_display_face(self):
        self.assertTrue(TITLE_FONT_PATH.is_file())
        font = _title_font(32)
        self.assertEqual(font.getname()[0], "Lalezar")

    def test_aparat_poster_omits_its_own_id_and_includes_youtube_icon(self):
        import short_video

        image = Image.new("RGB", (400, 500), (255, 255, 255))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        drawn_text = []
        original_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, value, *args, **kwargs):
            drawn_text.append(str(value))
            return original_text(draw, xy, value, *args, **kwargs)

        with mock.patch.object(ImageDraw.ImageDraw, "text", capture_text), mock.patch(
            "short_video._draw_video_channel_logo",
            wraps=short_video._draw_video_channel_logo,
        ) as draw_logo:
            build_vertical_poster(stream.getvalue(), 40, destination_platform="aparat")

        self.assertEqual(
            [call.args[1] for call in draw_logo.call_args_list],
            ["telegram", "bale", "rubika", "youtube"],
        )
        self.assertTrue(any("youtube.com/@offerchin" in value for value in drawn_text))
        self.assertIn(
            _shape_rtl("لینک خرید: کپشن ویدئو و توضیحات کانال"),
            drawn_text,
        )
        self.assertEqual(
            video_purchase_cta_text("aparat"),
            "لینک خرید: کپشن ویدئو و توضیحات کانال",
        )
        self.assertEqual(video_purchase_cta_text("filo"), "لینک خرید: توضیحات ویدئو")
        self.assertFalse(any("aparat.com/OfferChin" in value for value in drawn_text))
        self.assertFalse(any("OfferChin  •" in value for value in drawn_text))

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

    def test_default_youtube_description_uses_all_other_public_channel_ids(self):
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
        for channel_id in ("t.me/OfferChin", "ble.ir/OfferChin", "rubika.ir/offerchin", "aparat.com/OfferChin"):
            self.assertIn(channel_id, description)
        self.assertNotIn("youtube.com/@offerchin", description)
        self.assertNotRegex(description, r"(?i)https?://|www\.")
        self.assertNotIn("کانال تلگرام", description)
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
        self.assertIn("t.me/OfferChin", description)
        self.assertNotRegex(description, r"(?i)https?://|www\.")


if __name__ == "__main__":
    unittest.main()
