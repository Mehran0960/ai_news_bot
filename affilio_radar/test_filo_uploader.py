import unittest
from pathlib import Path

from filo_uploader import (
    FiloUploadError,
    _normalize_text,
    _success_flag,
    _title_matches,
    filo_credentials_available,
    upload_filo_video,
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
