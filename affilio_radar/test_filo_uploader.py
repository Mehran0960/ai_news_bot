import unittest
from pathlib import Path
from unittest.mock import Mock

from filo_uploader import (
    FiloUploadError,
    _find_publish_button,
    _visible_enabled_first,
    _normalize_text,
    _success_flag,
    _title_matches,
    filo_credentials_available,
    upload_filo_video,
    verify_filo_login,
)


class FiloUploaderUnitTests(unittest.TestCase):
    def test_credentials_check_requires_both_values(self):
        self.assertFalse(filo_credentials_available({}))
        self.assertFalse(filo_credentials_available({"FILO_USER": "user"}))
        self.assertFalse(filo_credentials_available({"FILO_PASS": "pass"}))
        self.assertTrue(filo_credentials_available({"FILO_USER": " user ", "FILO_PASS": " pass "}))

    def test_success_flag_accepts_supported_api_truthy_values(self):
        for value in (True, 1, "1", "true", "YES"):
            self.assertTrue(_success_flag(value))
        for value in (False, 0, "0", "false", "", None):
            self.assertFalse(_success_flag(value))

    def test_persian_and_arabic_text_normalization_is_stable(self):
        self.assertEqual(_normalize_text("آفرچین ۱۲۳"), _normalize_text("آفرچین ۱۲۳"))
        self.assertTrue(_title_matches("فعال | پیشنهاد ویژه آفرچین", "پیشنهاد ویژه آفرچین"))

    def test_publish_button_finder_supports_input_submit_controls(self):
        page = Mock()
        collection = Mock()
        candidate = Mock()
        candidate.count.return_value = 1
        candidate.is_visible.return_value = True
        candidate.is_enabled.return_value = True
        collection.evaluate_all.return_value = [{
            "index": 0,
            "tag": "input",
            "text": "بارگذاری ویدیو",
            "disabled": False,
            "visible": True,
        }]
        collection.nth.return_value = candidate
        page.locator.return_value = collection

        self.assertIs(_find_publish_button(page), candidate)
        collection.nth.assert_called_once_with(0)

    def test_login_selector_skips_visible_but_disabled_submit_decoy(self):
        page = Mock()
        collection = Mock()
        disabled = Mock()
        enabled = Mock()
        collection.count.return_value = 2
        collection.nth.side_effect = [disabled, enabled]
        disabled.count.return_value = 1
        disabled.is_visible.return_value = True
        disabled.is_enabled.return_value = False
        enabled.count.return_value = 1
        enabled.is_visible.return_value = True
        enabled.is_enabled.return_value = True
        page.locator.return_value = collection

        self.assertIs(_visible_enabled_first(page, ["button[type='submit']"]), enabled)

    def test_login_check_requires_credentials_without_launching_browser(self):
        with self.assertRaises(FiloUploadError) as caught:
            verify_filo_login(env={})
        self.assertEqual(caught.exception.code, "filo_credentials_missing")
        self.assertFalse(caught.exception.submission_started)

    def test_missing_credentials_fail_before_browser_start(self):
        with self.assertRaises(FiloUploadError) as caught:
            upload_filo_video(Path("missing.mp4"), "پیشنهاد آفرچین", env={})
        self.assertEqual(caught.exception.code, "filo_credentials_missing")
        self.assertFalse(caught.exception.submission_started)

    def test_bad_video_path_fails_before_browser_start(self):
        with self.assertRaises(FiloUploadError) as caught:
            upload_filo_video(Path("missing.mp4"), "پیشنهاد آفرچین",
                              env={"FILO_USER": "user", "FILO_PASS": "pass"})
        self.assertEqual(caught.exception.code, "filo_video_file_invalid")
        self.assertFalse(caught.exception.submission_started)


if __name__ == "__main__":
    unittest.main()
