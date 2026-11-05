import unittest

from validate_offerchin_documentation import (
    added_changelog_entries,
    is_dated_heading,
    is_offerchin_implementation_file,
    validate_change,
)


class OfferChinDocumentationGateTests(unittest.TestCase):
    def test_manual_runtime_file_changes_in_a_pull_request_are_documented(self):
        # Scheduled state writes on main do not match the workflow path filters.
        # Manual edits submitted in a pull request must still pass the documentation gate.
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/state.json"))
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/integrity_audit_state.json"))
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/weekly_report.json"))
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/config/products.json"))

    def test_offerchin_code_and_workflows_are_scoped(self):
        self.assertTrue(is_offerchin_implementation_file("affilio_radar/publisher.py"))
        self.assertTrue(is_offerchin_implementation_file("cloudflare/affilio-minute-dispatcher.js"))
        self.assertTrue(is_offerchin_implementation_file(".github/workflows/offerchin-publisher.yml"))
        self.assertTrue(is_offerchin_implementation_file("offerchin-site/src/app.js"))
        self.assertTrue(is_offerchin_implementation_file("scripts/new_tool.py"))
        self.assertTrue(is_offerchin_implementation_file("docs/PROJECT_CHARTER_FA.md"))
        self.assertTrue(is_offerchin_implementation_file("README.md"))
        self.assertTrue(is_offerchin_implementation_file(".github/PULL_REQUEST_TEMPLATE.md"))
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

    def test_changelog_history_is_append_only_even_without_code_changes(self):
        previous = "## ۲۰۲۶-۱۱-۰۴ — old\nold entry\n"
        appended = previous + "\n## ۲۰۲۶-۱۱-۰۵ — new\nnew entry\n"
        self.assertEqual(
            validate_change(
                ["docs/CHANGELOG_FA.md"], False, True, previous, appended
            ),
            [],
        )

        rewritten = "## ۲۰۲۶-۱۱-۰۴ — old\nrewritten entry\n" + appended[len(previous):]
        errors = validate_change(
            ["docs/CHANGELOG_FA.md"], False, True, previous, rewritten
        )
        self.assertTrue(any("append-only" in error for error in errors))

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
