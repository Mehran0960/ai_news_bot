import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import affilio_radar as radar
from publisher import _eligible_fallback_candidates


class OfferChinSelectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    def _verified_review_growth(self, **overrides):
        record = {
            "current_demand_verified": True,
            "recent_review_growth_window": 6,
            "recent_review_growth_7d": 6,
            "demand_window_hours": 6,
            "demand_observed_at": self.now.isoformat(),
            "demand_signal_source": "digikala_recent_review_growth",
        }
        record.update(overrides)
        return record

    def test_same_family_candidates_are_blocked_before_primary_and_backup_selection(self):
        products = [
            {
                "product_id": f"dkp-family-{index}",
                "product_url": f"https://www.digikala.com/product/dkp-family-{index}/",
                "title": title,
                "brand": brand,
                "availability": "in_stock",
                "current_price": 500_000,
                "original_price": 1_000_000,
                "discount_percent": discount,
                "savings_toman": 500_000,
                "catalog_category_id": "812",
                "catalog_category_name": "پاوربانک",
                "catalog_category_ids": ["812"],
                "catalog_best_selling_category_id": "812",
                "catalog_best_selling_category_name": "پاوربانک",
                **self._verified_review_growth(),
            }
            for index, (title, brand, discount) in enumerate((
                ("پاوربانک ۲۰۰۰۰ میلی آمپر مدل A", "Brand A", 90),
                ("شارژر همراه ۱۰۰۰۰ میلی آمپر مدل B", "Brand B", 85),
                ("پاوربانک باریک ۵۰۰۰ میلی آمپر مدل C", "Brand C", 80),
            ), start=1)
        ]
        state = {"published": {}, "recent_publications": []}
        with (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
        ):
            selected, floor, quality = radar.select_discount_fallback_candidates(
                products, state, now=self.now, include_fallback_bands=True
            )
        self.assertEqual(floor, 1)
        self.assertEqual(len(quality), 3)
        self.assertEqual(
            [row["product_id"] for row in selected],
            ["dkp-family-1"],
            "only the highest-ranked family member may pass as primary or backup",
        )
        rejected = radar._LAST_PUBLICATION_DIVERSITY_DIAGNOSTICS["rejection_events"]
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all("family_repeat" in row["reasons"] for row in rejected))
        self.assertEqual({row["catalog_category_id"] for row in rejected}, {"812"})
        self.assertTrue(all(row["catalog_category_name"] == "پاوربانک" for row in rejected))

    def test_publication_classifier_uses_digikala_category_and_application(self):
        automotive = {
            "title": "چراغ شارژی مدل آزمایشی",
            "catalog_best_selling_category_id": "91",
            "catalog_best_selling_category_name": "چراغ خودرو و تجهیزات روشنایی",
        }
        travel = {
            "title": "چراغ شارژی مدل آزمایشی",
            "catalog_best_selling_category_id": "92",
            "catalog_best_selling_category_name": "چراغ کمپینگ و کوهنوردی",
        }
        self.assertEqual(radar._publication_use_case_group(automotive), "automotive")
        self.assertEqual(radar._publication_use_case_group(travel), "outdoor_travel")
        auto_category, auto_family, _ = radar._publication_diversity_group(automotive)
        travel_category, travel_family, _ = radar._publication_diversity_group(travel)
        self.assertNotEqual(auto_category, travel_category)
        self.assertNotEqual(auto_family, travel_family)
        self.assertIn("digikala_category:91", auto_family)
        self.assertIn("digikala_category:92", travel_family)


    def test_live_digikala_taxonomy_categories_do_not_collapse_into_general(self):
        samples = [
            ("آرایش چشم", "personal_care"),
            ("آرایشی بهداشتی", "personal_care"),
            ("ابزار آلات و تجهیزات", "tools_industrial"),
            ("ابزار ایمنی", "tools_industrial"),
            ("ابزار مراقبت از پوست", "personal_care"),
            ("اسکاچ و سیم ظرفشویی", "home_cleaning"),
            ("بوردگیم، اوریگامی و بازی فکری", "tabletop_games"),
            ("تی شرت مردانه", "fashion_lifestyle"),
            ("خواب", "home_living"),
            ("دهان‌شویه و خمیردندان کودک و نوزاد", "baby_care"),
            ("سایر لوازم خودرو", "automotive"),
            ("سرویس کفگیر و ملاقه", "kitchen_food"),
            ("سلامت و پزشکی", "health_wellness"),
            ("شانه مو", "personal_care"),
            ("صبحانه", "grocery_food"),
            ("لوازم اداری", "office_study"),
            ("لوازم تحریر", "office_study"),
            ("لوازم ماهیگیری", "outdoor_travel"),
            ("لوازم یدکی ابزار برقی", "tools_industrial"),
            ("ماسک صورت و بدن", "personal_care"),
            ("محصولات بومی و محلی", "local_goods"),
            ("مداد چشم", "personal_care"),
            ("مهر و استامپ", "office_study"),
            ("مکمل غذایی", "health_wellness"),
            ("مکمل کمک درمانی کودک", "baby_care"),
            ("ورزش های توپی", "sports_fitness"),
            ("پرچم", "events_decor"),
            ("کتاب رمان و ادبیات داستانی و نمایشی", "books_learning"),
            ("کتاب روانشناسی", "books_learning"),
        ]
        for index, (category_name, expected) in enumerate(samples, start=9000):
            with self.subTest(category=category_name):
                product = {
                    "product_id": f"dkp-{index}",
                    "catalog_best_selling_category_id": str(index),
                    "catalog_best_selling_category_name": category_name,
                }
                actual = radar._publication_use_case_group(product)
                self.assertEqual(actual, expected)
                self.assertNotIn(actual, {"general", "catalog_taxonomy_other"})

    def test_unknown_digikala_taxonomy_is_distinguished_from_missing_taxonomy(self):
        known_but_unmapped = {
            "product_id": "dkp-999991",
            "catalog_best_selling_category_id": "999991",
            "catalog_best_selling_category_name": "رده آزمایشی نامتعارف",
        }
        self.assertEqual(radar._publication_use_case_group(known_but_unmapped), "catalog_taxonomy_other")
        self.assertEqual(radar._publication_use_case_group({"title": ""}), "general")

    def test_review_growth_is_only_an_indirect_fresh_proxy_not_sales(self):
        record = self._verified_review_growth()
        self.assertTrue(radar.has_current_demand_signal(record, now=self.now))
        self.assertTrue(radar.has_actionable_demand_signal(record, now=self.now))

        stale = dict(
            record,
            demand_observed_at=(self.now - timedelta(hours=radar.CURRENT_DEMAND_MAX_SIGNAL_AGE_HOURS + 1)).isoformat(),
        )
        self.assertFalse(radar.has_actionable_demand_signal(stale, now=self.now))

        lifetime_reviews_only = {
            "product_id": "dkp-lifetime",
            "review_count": 250_000,
            "rating": 4.9,
            "historical_popularity_score": 100,
            "demand_score": 100,
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": self.now.isoformat(),
        }
        self.assertFalse(radar.has_actionable_demand_signal(lifetime_reviews_only, now=self.now))
        self.assertEqual(
            radar._fresh_digikala_bestseller_evidence(lifetime_reviews_only, self.now)["best_rank_across_categories"],
            1,
        )

    def test_fresh_review_growth_outranks_a_larger_markdown_when_no_bestseller_rank_exists(self):
        high_discount_without_growth = {
            "product_id": "dkp-high-discount",
            "discount_percent": 85,
            "savings_toman": 8_500_000,
            "review_count": 0,
        }
        lower_discount_with_growth = {
            "product_id": "dkp-review-growth",
            "discount_percent": 18,
            "savings_toman": 180_000,
            "review_count": 50,
            **self._verified_review_growth(),
        }
        self.assertGreater(
            radar.deal_sort_key(lower_discount_with_growth, now=self.now),
            radar.deal_sort_key(high_discount_without_growth, now=self.now),
        )
        self.assertGreater(
            radar.discovery_queue_sort_key(lower_discount_with_growth, now=self.now),
            radar.discovery_queue_sort_key(high_discount_without_growth, now=self.now),
        )

    def test_direct_bestseller_rank_precedes_review_growth_and_deal_value(self):
        top_seller = {
            "product_id": "dkp-top-seller",
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 2,
            "catalog_rank_observed_at": self.now.isoformat(),
            "discount_percent": 10,
            "savings_toman": 100_000,
            "review_count": 25,
            "rating": 4.0,
        }
        review_spike = {
            "product_id": "dkp-review-spike",
            "discount_percent": 90,
            "savings_toman": 9_000_000,
            "review_count": 100,
            **self._verified_review_growth(),
        }
        self.assertGreater(
            radar.deal_sort_key(top_seller, now=self.now),
            radar.deal_sort_key(review_spike, now=self.now),
        )

        stale_bestseller = {
            **top_seller,
            "catalog_rank_observed_at": (
                self.now - timedelta(hours=radar.DIGIKALA_BESTSELLER_MAX_AGE_HOURS + 1)
            ).isoformat(),
        }
        self.assertFalse(radar._fresh_digikala_bestseller_evidence(stale_bestseller, self.now))
        self.assertGreater(
            radar.deal_sort_key(review_spike, now=self.now),
            radar.deal_sort_key(stale_bestseller, now=self.now),
        )

    def test_four_factor_balance_can_trade_off_live_demand_against_affordability_and_discount(self):
        products = [
            {
                "product_id": "dkp-popular-low-discount",
                "product_url": "https://www.digikala.com/product/dkp-popular-low-discount/",
                "title": "لپ تاپ اداری مدل نمونه",
                "brand": "Brand A",
                "availability": "in_stock",
                "current_price": 900_000,
                "original_price": 1_000_000,
                "discount_percent": 10,
                "savings_toman": 100_000,
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_rank": 1,
                "catalog_rank_observed_at": self.now.isoformat(),
                "catalog_best_selling_category_id": "101",
                "catalog_best_selling_category_name": "لپ تاپ",
            },
            {
                "product_id": "dkp-weak-high-discount",
                "product_url": "https://www.digikala.com/product/dkp-weak-high-discount/",
                "title": "هدفون بلوتوثی مدل نمونه",
                "brand": "Brand B",
                "availability": "in_stock",
                "current_price": 200_000,
                "original_price": 1_000_000,
                "discount_percent": 80,
                "savings_toman": 800_000,
                "review_count": 2,
                "rating": 3.5,
                **self._verified_review_growth(),
            },
        ]
        state = {"published": {}, "recent_publications": []}
        with (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
        ):
            selected, _floor, quality = radar.select_discount_fallback_candidates(
                products, state, now=self.now, include_fallback_bands=True
            )

        self.assertEqual(len(quality), 2)
        scores = {
            row["product_id"]: row["offerchin_four_factor"]
            for row in selected
        }
        self.assertGreater(
            scores["dkp-popular-low-discount"]["live_demand"],
            scores["dkp-weak-high-discount"]["live_demand"],
        )
        self.assertGreater(
            scores["dkp-weak-high-discount"]["affordability"],
            scores["dkp-popular-low-discount"]["affordability"],
        )
        self.assertGreater(
            scores["dkp-weak-high-discount"]["discount_attractiveness"],
            scores["dkp-popular-low-discount"]["discount_attractiveness"],
        )
        self.assertGreater(
            scores["dkp-weak-high-discount"]["balanced_score"],
            scores["dkp-popular-low-discount"]["balanced_score"],
        )
        queue = {row["product_id"]: {} for row in selected}
        by_id = {row["product_id"]: row for row in selected}
        published = radar.select_publish_candidates(queue, by_id, self.now)
        expected = sorted(selected, key=radar.deal_sort_key, reverse=True)
        self.assertEqual(
            [row["product_id"] for row in published],
            [row["product_id"] for row in expected],
        )
        self.assertEqual(published[0]["product_id"], "dkp-weak-high-discount")

    def test_discount_is_the_final_tiebreak_after_equal_demand_evidence(self):
        base = {
            "product_id": "dkp-equal-demand",
            "review_count": 500,
            "rating": 4.5,
            **self._verified_review_growth(),
        }
        larger_discount = {**base, "discount_percent": 70, "savings_toman": 700_000}
        smaller_discount = {**base, "discount_percent": 20, "savings_toman": 200_000}
        self.assertGreater(
            radar.deal_sort_key(larger_discount, now=self.now),
            radar.deal_sort_key(smaller_discount, now=self.now),
        )

    def test_fresh_bestseller_rank_never_counts_as_review_growth_or_sales(self):
        bestseller_only = {
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 1,
            "catalog_rank_observed_at": self.now.isoformat(),
            "review_count": 25_000,
            "rating": 4.9,
        }
        self.assertFalse(radar.has_actionable_demand_signal(bestseller_only, now=self.now))

    def test_primary_selection_and_publish_queue_reject_discount_without_fresh_demand(self):
        no_demand = {
            "product_id": "dkp-no-demand",
            "product_url": "https://www.digikala.com/product/dkp-no-demand/",
            "title": "پاوربانک تخفیف‌دار آزمایشی",
            "availability": "in_stock",
            "current_price": 700_000,
            "original_price": 1_000_000,
            "discount_percent": 30,
            "savings_toman": 300_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-no-demand%2F",
        }
        state = {"published": {}, "recent_publications": []}
        with (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
        ):
            selected, _floor, quality = radar.select_discount_fallback_candidates(
                [no_demand], state, now=self.now
            )
            queued = radar.select_publish_candidates(
                {"dkp-no-demand": {}}, {"dkp-no-demand": no_demand}, now=self.now
            )
        self.assertEqual(selected, [])
        self.assertEqual(quality, [])
        self.assertEqual(queued, [])

    def test_emergency_continuity_relaxes_only_the_demand_gate_for_strong_live_deals(self):
        product = {
            "product_id": "dkp-emergency-strong",
            "product_url": "https://www.digikala.com/product/dkp-emergency-strong/",
            "title": "پاوربانک پرظرفیت مدل نمونه",
            "availability": "in_stock",
            "current_price": 400_000,
            "original_price": 1_000_000,
            "discount_percent": 60,
            "savings_toman": 600_000,
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-emergency-strong%2F",
        }

        def score(rows, now=None):
            for row in rows:
                row["offerchin_four_factor"] = {
                    "affordability": 75,
                    "generality": 80,
                    "discount_attractiveness": 90,
                    "balanced_score": 81,
                }

        common_patches = (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "has_verified_market_demand", return_value=False),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
            patch.object(radar, "_has_active_publication_or_delivery", return_value=False),
            patch.object(radar, "_apply_offerchin_four_factor_scores", side_effect=score),
            patch.object(radar, "_filter_recent_publication_repeats", side_effect=lambda rows, *args, **kwargs: rows),
            patch.object(radar, "deal_sort_key", side_effect=lambda row, **kwargs: (
                row["offerchin_four_factor"]["balanced_score"],
                row["discount_percent"],
                row["savings_toman"],
            )),
        )
        with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6], common_patches[7], common_patches[8], common_patches[9]:
            selected, _floor, quality = radar.select_discount_fallback_candidates(
                [product], {}, now=self.now, allow_emergency_demand_relaxation=True
            )
        self.assertEqual(quality, [], "demand-relaxed products must not be mislabeled as demand-qualified")
        self.assertEqual([row["product_id"] for row in selected], ["dkp-emergency-strong"])
        self.assertEqual(
            selected[0]["selection_demand_evidence"],
            "not_verified_emergency_continuity_override",
        )
        self.assertEqual(
            selected[0]["selection_demand_quality"],
            "demand_not_verified_three_factor_proxy_only",
        )

    def test_emergency_continuity_still_rejects_weak_discount_score(self):
        product = {
            "product_id": "dkp-emergency-weak",
            "product_url": "https://www.digikala.com/product/dkp-emergency-weak/",
            "title": "کالای نمونه با تخفیف ناکافی",
            "availability": "in_stock",
            "current_price": 900_000,
            "original_price": 1_000_000,
            "discount_percent": 10,
            "savings_toman": 100_000,
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-emergency-weak%2F",
        }

        def score(rows, now=None):
            for row in rows:
                row["offerchin_four_factor"] = {
                    "affordability": 75,
                    "generality": 80,
                    "discount_attractiveness": 54,
                    "balanced_score": 67,
                }

        with (
            patch.object(radar, "is_product_suppressed", return_value=False),
            patch.object(radar, "is_discount_publish_eligible", return_value=True),
            patch.object(radar, "has_publishable_expiry_or_open_offer", return_value=True),
            patch.object(radar, "has_verified_market_demand", return_value=False),
            patch.object(radar, "is_selection_candidate_rejected", return_value=False),
            patch.object(radar, "is_fresh_selection_candidate", return_value=True),
            patch.object(radar, "_has_active_publication_or_delivery", return_value=False),
            patch.object(radar, "_apply_offerchin_four_factor_scores", side_effect=score),
        ):
            selected, _floor, _quality = radar.select_discount_fallback_candidates(
                [product], {}, now=self.now, allow_emergency_demand_relaxation=True
            )
        self.assertEqual(selected, [])

    def test_demand_is_required_but_positive_market_or_history_confirmation_is_not(self):
        product = {
            "product_id": "dkp-1234567",
            "product_url": "https://www.digikala.com/product/dkp-1234567/",
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 700_000,
            "original_price": 1_000_000,
            "discount_percent": 30,
            "savings_toman": 300_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1234567%2F",
            "selection_discount_floor": 1,
            "publication_policy": "digikala_demand_first_bestseller_review_quality_discount_v1",
            **self._verified_review_growth(),
        }
        # A recent review-growth proxy qualifies; external market/history confirmation is optional.
        self.assertTrue(radar.is_discount_publish_eligible(product, minimum_discount_percent=1, now=self.now))
        self.assertEqual(
            [row["product_id"] for row in _eligible_fallback_candidates([product], self.now)],
            ["dkp-1234567"],
        )

        # A large discount without fresh demand evidence cannot pass the publication fallback.
        no_demand = {
            key: value for key, value in product.items()
            if key not in {
                "current_demand_verified", "recent_review_growth_window",
                "recent_review_growth_7d", "demand_window_hours",
                "demand_observed_at", "demand_signal_source",
            }
        }
        self.assertTrue(radar.is_discount_publish_eligible(no_demand, minimum_discount_percent=1, now=self.now))
        self.assertEqual(_eligible_fallback_candidates([no_demand], self.now), [])

    def test_native_bestseller_rank_is_a_valid_hard_demand_signal(self):
        product = {
            "product_id": "dkp-best-seller",
            "product_url": "https://www.digikala.com/product/dkp-1234567/",
            "title": "پاوربانک پرفروش آزمایشی",
            "availability": "in_stock",
            "current_price": 700_000,
            "original_price": 1_000_000,
            "discount_percent": 30,
            "savings_toman": 300_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1234567%2F",
            "selection_discount_floor": 1,
            "catalog_sort_mode": "best_selling",
            "catalog_best_selling_rank": 3,
            "catalog_rank_observed_at": self.now.isoformat(),
        }
        self.assertTrue(radar.has_verified_market_demand(product, now=self.now))
        self.assertEqual(
            [row["product_id"] for row in _eligible_fallback_candidates([product], self.now)],
            ["dkp-best-seller"],
        )

    def test_fresh_verified_contradictory_history_can_veto_but_stale_history_cannot(self):
        base = {
            "product_id": "dkp-history-check",
            "product_url": "https://www.digikala.com/product/dkp-1234567/",
            "title": "پاوربانک آزمایشی",
            "availability": "in_stock",
            "current_price": 700_000,
            "original_price": 1_000_000,
            "discount_percent": 30,
            "savings_toman": 300_000,
            "image_url": "https://example.com/product.webp",
            "affiliate_url": "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-1234567%2F",
        }
        fresh_reject = {
            **base,
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": self.now.isoformat(),
        }
        self.assertFalse(radar.is_discount_publish_eligible(fresh_reject, minimum_discount_percent=1, now=self.now))

        stale_reject = {
            **base,
            "history_status": "verified",
            "historical_deal_eligible": False,
            "history_checked_at": (self.now - timedelta(hours=radar.PRICE_HISTORY_RECHECK_HOURS + 1)).isoformat(),
        }
        self.assertTrue(radar.is_discount_publish_eligible(stale_reject, minimum_discount_percent=1, now=self.now))

    def test_price_math_must_match_and_default_floor_is_any_positive_markdown(self):
        valid = {
            "discount_percent": 10,
            "savings_toman": 100_000,
            "current_price": 900_000,
            "original_price": 1_000_000,
        }
        self.assertTrue(radar.has_meaningful_discount(valid))
        self.assertFalse(radar.has_meaningful_discount({**valid, "discount_percent": 11}))
        self.assertFalse(radar.has_meaningful_discount({**valid, "savings_toman": 99_000}))
        self.assertTrue(radar.has_meaningful_discount({
            "discount_percent": 1,
            "savings_toman": 10_000,
            "current_price": 990_000,
            "original_price": 1_000_000,
        }))


if __name__ == "__main__":
    unittest.main()
