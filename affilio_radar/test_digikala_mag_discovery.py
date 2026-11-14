import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from digikala_mag_discovery import (
    FEED_URL,
    canonical_article_url,
    fetch_feed,
    parse_feed,
)


NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>راهنمای خرید هدفون بی‌سیم؛ به چه نکاتی توجه کنیم؟</title>
      <link>https://www.digikala.com/mag/buy-wireless-headphones/?utm_source=rss</link>
      <pubDate>Sat, 14 Nov 2026 08:10:00 +0000</pubDate>
      <category>گجت</category>
      <description><![CDATA[اين متن نباید در گزارش ذخیره شود.]]></description>
    </item>
    <item>
      <title>راهنمای انتخاب صندلی اداری مناسب</title>
      <link>https://www.digikala.com/mag/office-chair-guide/</link>
      <pubDate>Sat, 14 Nov 2026 08:20:00 +0000</pubDate>
      <category>خانه و سبک زندگی</category>
    </item>
    <item>
      <title>برنامه بازی‌های لیگ فوتبال در هفته جدید</title>
      <link>https://www.digikala.com/mag/football-schedule/</link>
      <pubDate>Sat, 14 Nov 2026 08:30:00 +0000</pubDate>
      <category>ورزش</category>
    </item>
    <item>
      <title>راهنمای خرید لپ‌تاپ</title>
      <link>https://example.org/mag/laptop-guide/</link>
      <pubDate>Sat, 14 Nov 2026 08:35:00 +0000</pubDate>
      <category>تکنولوژی</category>
    </item>
    <item>
      <title>راهنمای خرید جاروبرقی قدیمی</title>
      <link>https://www.digikala.com/mag/old-vacuum-guide/</link>
      <pubDate>Sat, 01 Nov 2026 08:00:00 +0000</pubDate>
      <category>خانه</category>
    </item>
  </channel>
</rss>
""".encode("utf-8")


class DigikalaMagDiscoveryTests(unittest.TestCase):
    def test_only_official_mag_article_urls_are_accepted(self):
        self.assertEqual(
            canonical_article_url("https://digikala.com/mag/article/?utm_source=x#top"),
            "https://www.digikala.com/mag/article/",
        )
        self.assertIsNone(canonical_article_url("http://www.digikala.com/mag/article/"))
        self.assertIsNone(canonical_article_url("https://example.org/mag/article/"))
        self.assertIsNone(canonical_article_url("https://www.digikala.com/product/123/"))

    def test_relevant_shortlist_excludes_irrelevant_stale_and_external_items(self):
        candidates, counts, _seen = parse_feed(RSS, now=NOW)
        self.assertEqual(
            {row["title"] for row in candidates},
            {
                "راهنمای خرید هدفون بی‌سیم؛ به چه نکاتی توجه کنیم؟",
                "راهنمای انتخاب صندلی اداری مناسب",
            },
        )
        self.assertEqual(counts["feed_items"], 5)
        self.assertEqual(counts["rejected_irrelevant_or_excluded"], 1)
        self.assertEqual(counts["rejected_invalid_url"], 1)
        self.assertEqual(counts["rejected_out_of_window"], 1)

    def test_candidate_filter_rejects_non_actionable_tech_news_and_speculation(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item><title>بررسی کارت گرافیک RTX 5050؛ ارزش خرید دارد؟</title>
            <link>https://www.digikala.com/mag/rtx-5050-review/</link>
            <pubDate>Fri, 13 Nov 2026 08:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>مقایسه گوشی سامسونگ A07 و A08؛ کدام را بخریم؟</title>
            <link>https://www.digikala.com/mag/a07-vs-a08/</link>
            <pubDate>Fri, 13 Nov 2026 09:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>جنسن هوانگ از مدیرعاملی انویدیا استعفا کرد</title>
            <link>https://www.digikala.com/mag/ceo-resigns/</link>
            <pubDate>Fri, 13 Nov 2026 10:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>سفر به مریخ چقدر طول می‌کشد؟</title>
            <link>https://www.digikala.com/mag/mars-trip/</link>
            <pubDate>Fri, 13 Nov 2026 11:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>تعداد کاربران فعال پلی‌استیشن رکورد زد</title>
            <link>https://www.digikala.com/mag/console-users/</link>
            <pubDate>Fri, 13 Nov 2026 12:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>ماکت آیفون جدید لو رفت؛ نمایشگر بزرگ‌تر در راه است</title>
            <link>https://www.digikala.com/mag/iphone-dummy-leak/</link>
            <pubDate>Fri, 13 Nov 2026 13:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>اپلیکیشن ایکس‌باکس روی کامپیوتر به‌روزرسانی شد</title>
            <link>https://www.digikala.com/mag/xbox-app-update/</link>
            <pubDate>Fri, 13 Nov 2026 14:00:00 +0000</pubDate><category>تکنولوژی</category></item>
          <item><title>بهترین شامپو ضد ریزش مو؛ راهنمای انتخاب</title>
            <link>https://www.digikala.com/mag/anti-hair-loss-shampoo/</link>
            <pubDate>Fri, 13 Nov 2026 15:00:00 +0000</pubDate><category>زیبایی</category></item>
        </channel></rss>""".encode("utf-8")
        candidates, counts, _seen = parse_feed(feed, now=NOW, max_candidates=20)
        self.assertEqual(
            {row["title"] for row in candidates},
            {
                "بررسی کارت گرافیک RTX 5050؛ ارزش خرید دارد؟",
                "مقایسه گوشی سامسونگ A07 و A08؛ کدام را بخریم؟",
            },
        )
        self.assertEqual(counts["rejected_speculative_or_low_signal"], 1)
        self.assertEqual(counts["rejected_low_actionability"], 1)
        self.assertEqual(counts["rejected_irrelevant_or_excluded"], 6)

    def test_actionable_buying_content_is_ranked_before_less_direct_guidance(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item><title>ترفندهای استفاده بهتر از هدفون بی‌سیم</title>
            <link>https://www.digikala.com/mag/headphone-tips/</link>
            <pubDate>Fri, 13 Nov 2026 08:00:00 +0000</pubDate><category>گجت</category></item>
          <item><title>راهنمای خرید هدفون بی‌سیم؛ کدام مدل ارزش خرید دارد؟</title>
            <link>https://www.digikala.com/mag/headphone-buying-guide/</link>
            <pubDate>Thu, 12 Nov 2026 08:00:00 +0000</pubDate><category>گجت</category></item>
        </channel></rss>""".encode("utf-8")
        candidates, _counts, _seen = parse_feed(feed, now=NOW, max_candidates=20)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["title"], "راهنمای خرید هدفون بی‌سیم؛ کدام مدل ارزش خرید دارد؟")
        self.assertGreaterEqual(
            candidates[0]["editorial_relevance_score"],
            candidates[1]["editorial_relevance_score"],
        )

    def test_article_excerpt_and_image_are_not_stored(self):
        candidates, _counts, _seen = parse_feed(RSS, now=NOW)
        serialized = json.dumps(candidates, ensure_ascii=False)
        self.assertNotIn("اين متن نباید", serialized)
        self.assertNotIn("description", serialized)
        self.assertNotIn("image", serialized)
        self.assertTrue(all(row["public_copy_generated"] is False for row in candidates))
        self.assertTrue(all(row["status"] == "discovered_requires_original_persian_summary" for row in candidates))

    def test_seen_articles_are_not_repeated(self):
        first, _counts, seen = parse_feed(RSS, now=NOW)
        second, counts, _seen2 = parse_feed(RSS, seen=seen, now=NOW)
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(counts["already_seen"], 2)

    def test_candidates_over_output_limit_are_not_lost(self):
        first, _counts, seen = parse_feed(RSS, now=NOW, max_candidates=1)
        self.assertEqual(len(first), 1)
        second, _counts2, _seen2 = parse_feed(RSS, seen=seen, now=NOW, max_candidates=10)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["candidate_id"], second[0]["candidate_id"])

    def test_invalid_xml_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_xml"):
            parse_feed(b"<rss><item>", now=NOW)

    def test_missing_feed_items_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no_items"):
            parse_feed(b"<rss><channel /></rss>", now=NOW)

    def test_feed_fetch_is_restricted_to_official_rss_endpoint(self):
        with self.assertRaisesRegex(ValueError, "official_digikala_mag_rss"):
            fetch_feed("https://example.org/mag/feed/")
        with patch("digikala_mag_discovery.requests.get") as mocked_get:
            response = Mock()
            response.content = RSS
            response.raise_for_status.return_value = None
            mocked_get.return_value = response
            self.assertEqual(fetch_feed(FEED_URL), RSS)
            mocked_get.assert_called_once()
            self.assertEqual(mocked_get.call_args.args[0], FEED_URL)
            self.assertEqual(mocked_get.call_args.kwargs["timeout"], (10, 25))


if __name__ == "__main__":
    unittest.main()
