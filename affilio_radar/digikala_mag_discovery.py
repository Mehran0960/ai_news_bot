"""Discover relevant DigiKala Mag article metadata for OfferChin's editorial review queue.

This module reads only the public RSS feed. It deliberately does not fetch article
pages, copy descriptions, store article text/images, generate summaries, or publish.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

FEED_URL = "https://www.digikala.com/mag/feed/"
SOURCE_LABEL_FA = "دیجی‌کالا مگ"
MAX_FEED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_AGE_HOURS = 24 * 7
DEFAULT_MAX_CANDIDATES = 20
SEEN_RETENTION_DAYS = 45

# The scanner is intentionally narrow: it looks for shopping-adjacent topics,
# not every article published by the magazine.
EXCLUDED = re.compile(
    r"سیاست|انتخابات|فوتبال|ورزش|بسکتبال|والیبال|سینما|فیلم|سریال|بازیگر|"
    r"موسیقی|خواننده|کنسرت|رمزارز|ارز دیجیتال|بیت.?کوین|بورس|سرمایه.?گذاری|"
    r"درمان|بیماری|دارو|نسخه پزشکی|تشخیص پزشکی|ریزش مو|ضد.?ریزش|آکنه|جوش پوستی|"
    r"مدیرعامل|استعفا|برکناری|جانشین|بیوگرافی|زندگی.?نامه|جنسن هوانگ|"
    r"بحران مدیریتی|هیئت مدیره|مریخ|سیاره سرخ|فضاپیما|سفر فضایی|"
    r"تعداد کاربران فعال|رکوردشکنی کاربران|آمار کاربران",
    re.IGNORECASE,
)

# The editorial queue is not a technology-news digest. Require an explicit
# practical/buying intent in the title before a topic can become a candidate.
ACTIONABLE_TITLE = re.compile(
    r"راهنمای خرید|راهنمای انتخاب|مقایسه|بررسی|بهترین|ارزش خرید|خرید اقتصادی|"
    r"کدام.{0,30}(?:بخریم|بهتر|انتخاب)|چه بخریم|چطور.{0,25}(?:بخریم|انتخاب)|"
    r"تفاوت|فرق|ارتقا|نکات خرید|ترفند|روش استفاده|آموزش کاربردی|"
    r"به.?صرفه|اقتصادی.?تر|ارزان.?تر",
    re.IGNORECASE,
)

SPECULATIVE_TITLE = re.compile(
    r"شایعه|لو رفت|ماکت|احتمالاً|احتمالا|به دنبال ساخت|قصد ساخت|"
    r"در راه است|احتمال عرضه|طرح ساخت|تصاویر لو رفته",
    re.IGNORECASE,
)

TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "technology",
        re.compile(
            r"تکنولوژی|فناوری|گوشی|موبایل|تلفن همراه|آیفون|سامسونگ|شیائومی|"
            r"لپ.?تاپ|رایانه|کامپیوتر|تبلت|مانیتور|تلویزیون|هدفون|هندزفری|"
            r"اسپیکر|ساعت هوشمند|دوربین|مودم|روتر|کنسول|پلی.?استیشن|ایکس.?باکس|"
            r"گجت|پردازنده|کارت گرافیک|هوش مصنوعی|اندروید|اپل|ایسوس|لنوو|"
            r"nvidia|intel|amd|iphone|samsung|xiaomi|laptop|smartphone",
            re.IGNORECASE,
        ),
    ),
    (
        "home_kitchen",
        re.compile(
            r"لوازم خانگی|آشپزخانه|یخچال|لباسشویی|ماشین لباسشویی|ظرفشویی|"
            r"جاروبرقی|تصفیه هوا|کولر|پنکه|قهوه.?ساز|پلوپز|مایکروویو|ماکروویو|"
            r"قابلمه|ظروف|صندلی|مبل|مبلمان|میز|تشک|بالش|فرش|چراغ|لامپ|"
            r"خانه.?داری|نظافت خانه",
            re.IGNORECASE,
        ),
    ),
    (
        "fashion_beauty",
        re.compile(
            r"پوشاک|لباس|کفش|کیف|کوله.?پشتی|عطر|ادکلن|زیبایی|آرایش|مراقبت از پوست|"
            r"مراقبت مو|مو و پوست|استایل|پالتو|بارانی|کاپشن|شلوار|عینک|زیورآلات|"
            r"ضدآفتاب|شامپو|کرم",
            re.IGNORECASE,
        ),
    ),
    (
        "buying_guides",
        re.compile(
            r"راهنمای خرید|راهنمای انتخاب|مقایسه|چه بخریم|چطور انتخاب|"
            r"نکات خرید|نکته و ترفند|آموزش کاربردی|ترفند|روش استفاده",
            re.IGNORECASE,
        ),
    ),
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _tag_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].split(":")[-1].lower()


def _child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if _tag_name(child.tag) in names:
            return " ".join("".join(child.itertext()).split())
    return ""


def _parse_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_article_url(value: str) -> str | None:
    """Accept only HTTPS DigiKala Mag article URLs; drop tracking query strings."""
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme.lower() != "https"
        or host not in {"digikala.com", "www.digikala.com"}
        or parsed.username
        or parsed.password
        or not path.startswith("/mag/")
        or path == "/mag"
    ):
        return None
    return urlunsplit(("https", "www.digikala.com", path + "/", "", ""))


def _classify(title: str, categories: list[str]) -> tuple[str | None, int]:
    combined = " ".join([title, *categories])
    if EXCLUDED.search(combined) or SPECULATIVE_TITLE.search(title):
        return None, 0
    if not ACTIONABLE_TITLE.search(title):
        return None, 0

    for topic, pattern in TOPIC_PATTERNS:
        if pattern.search(combined):
            matches = len(pattern.findall(combined))
            category_bonus = 8 if any(pattern.search(category) for category in categories) else 0
            if re.search(r"راهنمای خرید|راهنمای انتخاب|چه بخریم|نکات خرید", title):
                intent_bonus = 28
            elif re.search(r"مقایسه|تفاوت|فرق|کدام", title):
                intent_bonus = 26
            elif re.search(r"بررسی|ارزش خرید|خرید اقتصادی", title):
                intent_bonus = 24
            else:
                intent_bonus = 18
            return topic, min(100, 35 + min(matches, 3) * 6 + category_bonus + intent_bonus)
    return None, 0


def _entry_link(node: ET.Element) -> str:
    direct = _child_text(node, {"link"})
    if direct:
        return direct
    # Atom feeds express link destinations as attributes.
    for child in list(node):
        if _tag_name(child.tag) == "link":
            rel = str(child.attrib.get("rel") or "alternate").lower()
            if rel == "alternate" and child.attrib.get("href"):
                return str(child.attrib["href"]).strip()
    return ""


def parse_feed(
    xml_payload: bytes | str,
    *,
    seen: dict[str, str] | None = None,
    now: datetime | None = None,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, str]]:
    """Parse feed metadata into new candidates without retaining article excerpts."""
    current = now or _now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    seen_map = dict(seen or {})
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        raise ValueError("digikala_mag_feed_invalid_xml") from exc

    items = [node for node in root.iter() if _tag_name(node.tag) in {"item", "entry"}]
    if not items:
        raise ValueError("digikala_mag_feed_has_no_items")

    counts = {
        "feed_items": len(items),
        "rejected_invalid_url": 0,
        "rejected_missing_title_or_date": 0,
        "rejected_out_of_window": 0,
        "rejected_irrelevant_or_excluded": 0,
        "rejected_low_actionability": 0,
        "rejected_speculative_or_low_signal": 0,
        "already_seen": 0,
    }
    candidates: list[dict[str, Any]] = []
    encountered_ids: set[str] = set()
    oldest_seen = current - timedelta(days=SEEN_RETENTION_DAYS)
    seen_map = {
        key: stamp for key, stamp in seen_map.items()
        if (_parse_datetime(stamp) or datetime.min.replace(tzinfo=timezone.utc)) >= oldest_seen
    }

    for node in items:
        title = _child_text(node, {"title"})
        url = canonical_article_url(_entry_link(node))
        if not url:
            counts["rejected_invalid_url"] += 1
            continue
        published_raw = _child_text(node, {"pubdate", "published", "updated", "date"})
        published_at = _parse_datetime(published_raw)
        if not title or published_at is None:
            counts["rejected_missing_title_or_date"] += 1
            continue
        age = current - published_at
        if age < timedelta(minutes=-10) or age > timedelta(hours=max(1, int(max_age_hours))):
            counts["rejected_out_of_window"] += 1
            continue

        categories = [
            " ".join("".join(child.itertext()).split())
            for child in list(node)
            if _tag_name(child.tag) == "category"
        ]
        if SPECULATIVE_TITLE.search(title):
            counts["rejected_speculative_or_low_signal"] += 1
            counts["rejected_irrelevant_or_excluded"] += 1
            continue
        if not ACTIONABLE_TITLE.search(title):
            counts["rejected_low_actionability"] += 1
            counts["rejected_irrelevant_or_excluded"] += 1
            continue

        topic, score = _classify(title, categories)
        if topic is None:
            counts["rejected_irrelevant_or_excluded"] += 1
            continue

        candidate_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        if candidate_id in seen_map or candidate_id in encountered_ids:
            counts["already_seen"] += 1
            continue
        encountered_ids.add(candidate_id)

        candidates.append({
            "candidate_id": candidate_id,
            "source": SOURCE_LABEL_FA,
            "source_url": url,
            "title": title,
            "published_at": published_at.isoformat(),
            "topic": topic,
            "editorial_relevance_score": score,
            "status": "discovered_requires_original_persian_summary",
            "summary_target_words": "۳۵ تا ۶۰",
            "rewrite_requirement_fa": (
                "یک نکتهٔ مستقل و کاربردی به فارسی بنویس؛ متن یا تصویر مقاله را کپی نکن؛ "
                "فقط یک فایدهٔ روشن برای مخاطب نگه دار و پیوند منبع را درج کن."
            ),
            "public_copy_generated": False,
        })

    # Prioritize practical buying value first; recency breaks ties within the
    # seven-day window instead of allowing generic news to outrank guides.
    candidates.sort(
        key=lambda item: (item["editorial_relevance_score"], item["published_at"]),
        reverse=True,
    )
    selected = candidates[: max(1, int(max_candidates))]
    # Mark only returned candidates as seen. Items beyond this run's output cap
    # must remain eligible for the next run rather than being silently dropped.
    for candidate in selected:
        seen_map[candidate["candidate_id"]] = current.isoformat()
    return selected, counts, seen_map


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"mag_discovery_state_unreadable:{type(exc).__name__}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("seen", {}), dict):
        raise RuntimeError("mag_discovery_state_shape_invalid")
    return state


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fetch_feed(url: str = FEED_URL, *, timeout: tuple[int, int] = (10, 25)) -> bytes:
    """Fetch only the known public RSS endpoint, never article pages."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in {"digikala.com", "www.digikala.com"}
        or parsed.path.rstrip("/") != "/mag/feed"
    ):
        raise ValueError("only_official_digikala_mag_rss_is_allowed")
    response = requests.get(
        url,
        headers={"User-Agent": "OfferChin-Mag-Source-Discovery/1.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.content
    if not payload or len(payload) > MAX_FEED_BYTES:
        raise RuntimeError("digikala_mag_feed_size_invalid")
    return payload


def run_discovery(
    *,
    state_path: Path,
    output_path: Path,
    now: datetime | None = None,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> dict[str, Any]:
    state = _load_state(state_path)
    xml_payload = fetch_feed()
    candidates, counts, updated_seen = parse_feed(
        xml_payload,
        seen=state.get("seen", {}),
        now=now,
        max_age_hours=max_age_hours,
        max_candidates=max_candidates,
    )
    current = now or _now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    report = {
        "generated_at": current.astimezone(timezone.utc).isoformat(),
        "source": SOURCE_LABEL_FA,
        "feed_url": FEED_URL,
        "mode": "metadata_discovery_only",
        "article_pages_fetched": 0,
        "article_text_or_images_stored": False,
        "public_publication_performed": False,
        "public_copy_generated": False,
        "summary_policy_fa": (
            "نامزدهای این گزارش فقط برای بازبینی‌اند. برای انتشار، متن فارسی مستقل ۳۵ تا ۶۰ "
            "واژه‌ای با پیوند منبع لازم است؛ متن و تصویر مقاله بازنشر نشود."
        ),
        "counts": counts,
        "new_candidates": candidates,
    }
    _write_json(output_path, report)
    _write_json(state_path, {
        "last_successful_fetch_at": current.astimezone(timezone.utc).isoformat(),
        "seen": updated_seen,
    })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover DigiKala Mag editorial source candidates.")
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    args = parser.parse_args(argv)
    try:
        report = run_discovery(
            state_path=args.state_path,
            output_path=args.output,
            max_age_hours=args.max_age_hours,
            max_candidates=args.max_candidates,
        )
    except Exception as exc:
        print(f"MAG_SOURCE_DISCOVERY_FAILED error={type(exc).__name__}:{str(exc)[:180]}", file=sys.stderr)
        return 1
    counts = report["counts"]
    print(
        "MAG_SOURCE_DISCOVERY_COMPLETE "
        f"scanned={counts['feed_items']} new={len(report['new_candidates'])} "
        f"seen={counts['already_seen']} rejected={sum(v for k, v in counts.items() if k.startswith('rejected_'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
