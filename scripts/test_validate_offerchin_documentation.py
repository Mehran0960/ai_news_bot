import unittest

from validate_offerchin_documentation import (
    added_changelog_entries,
    is_dated_heading,
    is_offerchin_implementation_file,
    validate_change,
)


class OfferChinDocumentationGateTests(unittest.TestCase):
    def test_runtime_state_files_are_excluded_from_scheduled_noise(self):
        # These files are written by scheduled automation; a manual edit must still
        # be documented as an operational change in the handbook and changelog.
        self.assertFalse(is_offerchin_implementation_file("affilio_radar/state.json"))
        self.assertFalse(is_offerchin_implementation_file("affilio_radar/integrity_audit_state.json"))
        self.assertFalse(is_offerchin_implementation_file("affilio_radar/weekly_report.json"))
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/config/products.json"))

    def test_offerchin_code_and_workflows_are_scoped(self):
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/publisher.py"))
        self.assertTrue(is_offerchin_implementation_file("cloudflare/affilio-minute-dispatcher.js"))
        self.assertTrue(is_offerchin_implementation_file(".github/workflows/offerchin-publisher.yml"))
        self.assertTrue(is_offerchin_implementation_file("offerchin-site/src/app.js"))
        self.assertTrue(is_offerchin_implementation_file("scripts/new_tool.py"))
        self.assertFalse(is_offerchin_implementation_file(".github/workflows/dayan-archive-best-post.yml"))

    def test_dated_headings_accept_latin_and_persian_digits(self):
        self.assertTrue(is_dated_heading("## 2026-11-05 — Latin date"))
        self.assertTrue(is_dated_heading("## ۲۰۲۶-۱۱-۰۵ — تاریخ فارسی"))
        self.assertFalse(is_dated_heading("## 2026/11/05 — wrong separator"))
        self.assertFalse(is_dated_heading("## no date"))

    def test_new_dated_heading_is_detected(self):
        old = "# Log\n\n## ۲۰۲۶-۱۱-۰۴ — old\n"
        new = old + "\n## ۲۰۲۶-۱۱-۰۵ — new\n"
        self.assertEqual(
            added_changelog_entries(old, new),
            ["## ۲۰۲۶-۱۱-۰۵ — new"],
        )

    def test_code_change_without_docs_fails(self):
        errors = validate_change(
            ["affilio_radar/publisher.py"],
            False,
            False,
            "",
            "",
        )
        self.assertEqual(len(errors), 2)

    def test_code_change_requires_new_structured_entry(self):
        entry = """## ۲۰۲۶-۱۱-۰۵ — test
**هدف:** هدف
**تغییر/اقدام:** اقدام
**فایل‌ها/سامانه‌ها:** مسیر
**آزمون و نتیجه:** OK
**شواهد/شناسه:** SHA
**ریسک/بازگشت:** rollback
**وضعیت:** انجام‌شده
"""
        errors = validate_change(
            ["affilio_radar/publisher.py"],
            True,
            True,
            "",
            entry,
        )
        self.assertEqual(errors, [])

    def test_missing_changelog_evidence_is_reported(self):
        entry = """## ۲۰۲۶-۱۱-۰۵ — incomplete
**هدف:** هدف
**تغییر/اقدام:** اقدام
"""
        errors = validate_change(
            ["affilio_radar/publisher.py"],
            True,
            True,
            "",
            entry,
        )
        self.assertTrue(any("missing required fields" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
