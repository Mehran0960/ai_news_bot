import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from digikala_mag_editorial import (
    EditorialDraftError,
    extract_article_text,
    run_pipeline,
    validate_generated_summary,
)

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
ARTICLE_BODY = (
    "انتخاب هدفون مناسب فقط به ظاهر یا اندازهٔ باتری وابسته نیست. "
    "حذف نویز فعال به کاهش صدای محیط در مسیرهای شلوغ کمک می‌کند. "
    "راحتی گوشی‌ها، کیفیت میکروفون و سازگاری با تلفن همراه نیز اهمیت دارند. "
    "پیش از تصمیم‌گیری، شیوهٔ استفادهٔ روزانه و نیازهای واقعی خود را مشخص کنید. "
    "بررسی تجربهٔ کاربران در موقعیت‌های گوناگون می‌تواند تصویر دقیق‌تری از عملکرد دستگاه بدهد. "
    "در استفادهٔ طولانی، وزن و فشار روی گوش هم بر راحتی اثر می‌گذارد."
)
PERSIAN_DRAFT = {
    "title_fa": "سه معیار برای انتخاب هدفون مناسب",
    "body_fa": (
        "برای انتخاب هدفون، ابتدا مشخص کنید بیشتر در محیط شلوغ به آن نیاز دارید یا برای تماس و رفت‌وآمد. "
        "اگر حذف نویز برایتان مهم است، عملکرد آن را در تجربه‌های واقعی بررسی کنید و فقط به ظاهر دستگاه تکیه نکنید. "
        "سازگاری با تلفن همراه، راحتی در استفاده طولانی و کیفیت میکروفون نیز بر تجربه روزمره اثر می‌گذارند. "
        "پیش از تصمیم‌گیری، اولویت‌های خود را بنویسید و امکانات غیرضروری را کنار بگذارید."
    ),
    "claims": [
        {
            "text_fa": "حذف نویز فعال می‌تواند صدای محیط را در مکان‌های شلوغ کاهش دهد",
            "evidence_quote": "حذف نویز فعال به کاهش صدای محیط در مسیرهای شلوغ کمک می‌کند",
        }
    ],
}
CANDIDATE = {
    "candidate_id": "abc123def456",
    "source": "دیجی‌کالا مگ",
    "source_url": "https://www.digikala.com/mag/headphone-guide/",
    "title": "راهنمای خرید هدفون بی‌سیم؛ چه نکاتی مهم است؟",
    "published_at": "2026-11-13T08:00:00+00:00",
    "topic": "technology",
    "editorial_relevance_score": 90,
}


class DigiKalaMagEditorialTests(unittest.TestCase):
    def _files(self, root: Path, candidates=None):
        source = root / "source-candidates.json"
        source.write_text(
            json.dumps({"new_candidates": candidates if candidates is not None else [CANDIDATE]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return source, root / "pending-editorial.json", root / "drafts.json"

    def test_extract_article_text_prefers_json_ld_article_body(self):
        html = """
        <html><head><script type="application/ld+json">
        {"@type":"NewsArticle","headline":"راهنمای هدفون","articleBody":%s}
        </script></head><body><article><p>متن کوتاه جایگزین</p></article></body></html>
        """ % json.dumps(ARTICLE_BODY, ensure_ascii=False)
        self.assertEqual(extract_article_text(html), " ".join(ARTICLE_BODY.split()))

    def test_extract_article_text_falls_back_to_article_paragraphs(self):
        body = " ".join(["این یک بند کاربردی درباره انتخاب و استفاده درست از دستگاه است."] * 12)
        html = "<html><body><article><p>" + body + "</p></article></body></html>"
        self.assertIn("انتخاب و استفاده درست", extract_article_text(html))

    @patch("digikala_mag_editorial._fetch_article")
    @patch("digikala_mag_editorial.requests.post")
    def test_missing_provider_configuration_keeps_candidate_without_fetching(self, post, fetch):
        with tempfile.TemporaryDirectory() as folder:
            source, state, output = self._files(Path(folder))
            report = run_pipeline(
                input_path=source,
                state_path=state,
                output_path=output,
                env={},
                now=NOW,
            )
            fetch.assert_not_called()
            post.assert_not_called()
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["pending_candidates"]), 1)
            self.assertEqual(report["status"], "waiting_for_provider_configuration")
            self.assertFalse(report["public_publication_performed"])
            self.assertFalse(report["publisher_queue_modified"])

    @patch("digikala_mag_editorial._fetch_article", return_value=ARTICLE_BODY)
    @patch("digikala_mag_editorial.requests.post")
    def test_valid_model_output_becomes_review_only_draft_without_evidence_or_article_text(self, post, fetch):
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(PERSIAN_DRAFT, ensure_ascii=False)}}]
        }
        response.raise_for_status.return_value = None
        post.return_value = response
        config = {
            "OFFERCHIN_EDITORIAL_API_URL": "https://api.example.test/v1/chat/completions",
            "OFFERCHIN_EDITORIAL_MODEL": "test-model",
            "OFFERCHIN_EDITORIAL_API_KEY": "secret-test-key",
        }
        with tempfile.TemporaryDirectory() as folder:
            source, state, output = self._files(Path(folder))
            report = run_pipeline(
                input_path=source,
                state_path=state,
                output_path=output,
                env=config,
                now=NOW,
            )
            fetch.assert_called_once()
            post.assert_called_once()
            self.assertEqual(report["drafts_generated_this_run"], 1)
            self.assertEqual(report["candidates_waiting"], 0)
            self.assertTrue(report["required_human_review"])
            self.assertFalse(report["public_publication_performed"])
            draft = report["drafts"][0]
            self.assertEqual(draft["approval_status"], "pending_human_review")
            self.assertNotIn("reviewed_at", draft)
            serialized = output.read_text(encoding="utf-8")
            self.assertNotIn("evidence_quote", serialized)
            self.assertNotIn("حذف نویز فعال به کاهش صدای محیط در مسیرهای شلوغ کمک می‌کند", serialized)
            self.assertNotIn(ARTICLE_BODY, serialized)
            self.assertNotIn("secret-test-key", serialized)

    def test_summary_validation_rejects_latin_short_text_and_unverified_evidence(self):
        latin = dict(PERSIAN_DRAFT, title_fa="راهنمای هدفون RTX")
        self.assertEqual(
            validate_generated_summary(latin, article_text=ARTICLE_BODY)[1],
            "title_must_be_persian",
        )
        short = dict(PERSIAN_DRAFT, body_fa="هدفون مناسب را بر اساس نیاز خود انتخاب کنید.")
        self.assertEqual(
            validate_generated_summary(short, article_text=ARTICLE_BODY)[1],
            "body_word_count_out_of_range",
        )
        false_claim = {
            **PERSIAN_DRAFT,
            "claims": [{
                "text_fa": "این دستگاه بهترین گزینهٔ بازار است",
                "evidence_quote": "این ادعای ساختگی در مقاله وجود ندارد و پشتیبانی نشده است",
            }],
        }
        self.assertEqual(
            validate_generated_summary(false_claim, article_text=ARTICLE_BODY)[1],
            "claim_evidence_not_found_in_source",
        )

    def test_summary_validation_rejects_long_verbatim_overlap(self):
        copied = dict(PERSIAN_DRAFT)
        copied["body_fa"] = (
            "انتخاب هدفون مناسب فقط به ظاهر یا اندازهٔ باتری وابسته نیست. "
            + PERSIAN_DRAFT["body_fa"]
        )
        self.assertEqual(
            validate_generated_summary(copied, article_text=ARTICLE_BODY)[1],
            "body_word_count_out_of_range",
        )

    def test_unofficial_article_url_is_rejected_before_network_access(self):
        with self.assertRaises(EditorialDraftError):
            run_pipeline(
                input_path=Path("/not-used"),
                state_path=Path("/not-used-state"),
                output_path=Path("/not-used-output"),
                env={},
            )
        from digikala_mag_editorial import _safe_candidate_url
        with self.assertRaises(EditorialDraftError):
            _safe_candidate_url("https://example.com/mag/fake/")


if __name__ == "__main__":
    unittest.main()
