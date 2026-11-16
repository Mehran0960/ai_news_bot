from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import affilio_radar as radar


NOW = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


class OfferChinIndependentDiversityTests(unittest.TestCase):
    def history(self, product_id: str, title: str, **extra):
        return {
            "product_id": product_id,
            "title": title,
            "ts": (NOW - timedelta(hours=1)).timestamp(),
            **extra,
        }

    def product(self, product_id: str, title: str, **extra):
        return {"product_id": product_id, "title": title, **extra}

    def test_product_title_overrides_broad_retailer_parent_category(self):
        row = {
            "title": "دفترچه یادداشت طرح گربه",
            "catalog_category_id": "broad-parent",
            "catalog_category_name": "آرایشی و بهداشتی",
        }
        category, family, _brand = radar._publication_diversity_group(row)
        self.assertEqual(category, "books_stationery")
        self.assertEqual(family, "books_stationery")
        self.assertEqual(radar._publication_use_case_group(row), "books_learning")

    def test_brand_extraction_handles_nested_digikala_fields_and_attributes(self):
        self.assertEqual(
            radar._extract_product_brand({"brand": {"id": 12, "title_fa": "زیرووات"}}),
            "زیرووات",
        )
        self.assertEqual(
            radar._extract_product_brand({
                "attributes": [{"name": "برند", "value": {"title": "آور گریپ"}}],
            }),
            "آور گریپ",
        )
        self.assertEqual(
            radar._extract_product_brand({"title": "کالای نمونه | برند: نمونه‌ساز"}),
            "نمونه‌ساز",
        )

    def test_category_repeat_is_independent_of_use_case_repeat(self):
        history = [self.history(
            "dkp-history",
            "دفترچه یادداشت طرح گربه",
            forced_use_case="history_use_case",
        )]
        same_category_different_use_case = self.product(
            "dkp-same-category",
            "دفتر برنامه‌ریزی روزانه",
            forced_use_case="different_use_case",
        )
        other_category = self.product(
            "dkp-other-category",
            "گردنبند نقره زنانه",
            forced_use_case="jewelry_use_case",
        )
        with patch.object(
            radar,
            "_publication_use_case_group",
            side_effect=lambda row: row.get("forced_use_case", "unknown"),
        ):
            selected = radar._filter_recent_publication_repeats(
                [same_category_different_use_case, other_category],
                published={},
                recent_publications=history,
                now=NOW,
                label="TEST_CATEGORY",
            )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-other-category"])

    def test_use_case_repeat_is_independent_of_category_repeat(self):
        history = [self.history(
            "dkp-history",
            "دفترچه یادداشت طرح گربه",
            forced_use_case="shared_use_case",
        )]
        same_use_case_different_category = self.product(
            "dkp-same-use-case",
            "گردنبند نقره زنانه",
            forced_use_case="shared_use_case",
        )
        other_use_case = self.product(
            "dkp-other-use-case",
            "چراغ مطالعه رومیزی",
            forced_use_case="other_use_case",
        )
        with patch.object(
            radar,
            "_publication_use_case_group",
            side_effect=lambda row: row.get("forced_use_case", "unknown"),
        ):
            selected = radar._filter_recent_publication_repeats(
                [same_use_case_different_category, other_use_case],
                published={},
                recent_publications=history,
                now=NOW,
                label="TEST_USE_CASE",
            )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-other-use-case"])

    def test_soft_category_and_use_case_constraints_relax_only_when_queue_would_be_empty(self):
        radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS = {}
        history = [self.history("dkp-history", "دفترچه یادداشت طرح گربه")]
        repeated_category = self.product("dkp-last-resort", "کتاب داستان کودک")
        selected = radar._filter_recent_publication_repeats(
            [repeated_category],
            published={},
            recent_publications=history,
            now=NOW,
            label="TEST_SOFT_FALLBACK",
        )
        self.assertEqual([row["product_id"] for row in selected], ["dkp-last-resort"])
        self.assertTrue(radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS.get("fallback_events"))

    def test_hard_family_or_similarity_duplicate_is_never_softly_relaxed(self):
        radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS = {}
        history = [self.history("dkp-history", "اور گریپ راکت حرفه‌ای")]
        duplicate = self.product("dkp-duplicate", "اورگریپ راکت مدل جدید")
        selected = radar._filter_recent_publication_repeats(
            [duplicate],
            published={},
            recent_publications=history,
            now=NOW,
            label="TEST_HARD_GUARD",
        )
        self.assertEqual(selected, [])
        self.assertFalse(radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS.get("fallback_events"))

    def test_category_and_use_case_cooldowns_are_separate_from_24_hour_hard_guards(self):
        self.assertEqual(radar.FAMILY_REPEAT_COOLDOWN_HOURS, 24)
        self.assertEqual(radar.BRAND_REPEAT_COOLDOWN_HOURS, 24)
        self.assertEqual(radar.PUBLICATION_SIMILARITY_COOLDOWN_HOURS, 24.0)
        self.assertEqual(radar.CATEGORY_REPEAT_COOLDOWN_HOURS, 6.0)
        self.assertEqual(radar.USE_CASE_REPEAT_COOLDOWN_HOURS, 6.0)


if __name__ == "__main__":
    unittest.main()
