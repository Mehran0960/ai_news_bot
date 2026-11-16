"""OfferChin three-factor candidate ranking.

Demand, broad usefulness and genuine discount value are the only ranking
dimensions. Affordability is deliberately excluded from the policy.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_three_factor_harmonic_v1"
MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE = 40.0

GENERALITY_SCORES = {
    "home_cleaning": 96,
    "grocery_food": 94,
    "kitchen_food": 92,
    "personal_care": 88,
    "mobile_productivity": 86,
    "software_tools": 40,
    "home_living": 84,
    "lighting_electrical": 82,
    "audio_visual": 78,
    "office_study": 74,
    "baby_care": 70,
    "books_learning": 68,
    "fashion_lifestyle": 64,
    "health_wellness": 62,
    "sports_fitness": 56,
    "automotive": 55,
    "tools_industrial": 53,
    "local_goods": 52,
    "outdoor_travel": 47,
    "pet_care": 44,
    "gaming": 40,
    "tabletop_games": 38,
    "events_decor": 36,
    "arts_crafts": 34,
    "general": 22,
    "unknown": 18,
}

# Product-title matches are evaluated before retailer taxonomy. Patterns avoid
# generic words (e.g. "گربه" in a notebook design) that create false categories.
_TEXT_GROUP_PATTERNS = (
    ("software_tools", r"نرم افزار|سیستم عامل|ویندوز|windows|autocad|driver pack|office software"),
    ("books_learning", r"کتاب|دفترچه|دفتر یادداشت|دفتر(?:\s|$)|خودکار|مداد رنگی|مداد تحریر|نوشت افزار|لوازم تحریر|رمان|داستان|مجله"),
    ("pet_care", r"حیوان خانگی|غذای سگ|غذای گربه|تشویقی سگ|تشویقی گربه|قلاده|خاک گربه|اسکرچر|پد بهداشتی سگ|آکواریوم"),
    ("grocery_food", r"مواد غذایی|خوراکی|نوشیدنی|چای|قهوه|شکلات|تنقلات|ادویه|کنسرو|خرما|عسل|مربا|آجیل|خشکبار|برنج|حبوبات|کره نارگیل|کره بادام زمینی"),
    ("kitchen_food", r"آشپزخانه|آشپزی|قابلمه|تابه|کتری|چای ساز|قهوه ساز|ظروف غذا|ظرف غذا|فلاسک|ماگ|قمقمه|زمان سنج آشپزی"),
    ("home_cleaning", r"نظافت|شوینده|تمیزکننده|جارو|دستمال نظافت|اسکاچ|سیم ظرفشویی|بخارشوی|زمین شوی"),
    ("baby_care", r"نوزاد|نوزادی|سیسمونی|پوشک|تغذیه کودک|کالسکه|صندلی خودرو کودک"),
    ("automotive", r"خودرو|ماشین|موتور سیکلت|ضدیخ|ضد یخ|آب رادیاتور|مایع رادیاتور|روغن موتور|لاستیک|تایر|داشبورد|کفپوش خودرو"),
    ("mobile_productivity", r"گوشی|موبایل|تبلت|لپ تاپ|لپتاپ|کامپیوتر|دانگل بلوتوث|دانگل|شارژر همراه|کابل usb|کابل شارژ|کابل hdmi|حافظه|فلش مموری|هارد|ssd|رم|مودم|روتر|کیبورد|ماوس|مانیتور"),
    ("audio_visual", r"هدفون|هدست|هندزفری|ایرپاد|اسپیکر|تلویزیون|دوربین عکاسی|میکروفن|میکروفون|پروژکتور"),
    ("personal_care", r"آرایشی|بهداشتی|مراقبت پوست|مراقبت مو|مسواک|ضدآفتاب|عطر|ادکلن|کرم مرطوب|سرم پوست|اتو مو|سشوار|ریش تراش"),
    ("fashion_lifestyle", r"پوشاک|لباس|تی شرت|تیشرت|کفش|کیف|عینک آفتابی|جوراب|انگشتر|زیورآلات|بوت|شلوار|هودی|مانتو|سوتین"),
    ("lighting_electrical", r"روشنایی|لامپ|چراغ|الکتریکی|سیم برق"),
    ("home_living", r"خانه|اتاق خواب|دکوراسیون|دکوراتیو|مبلمان|کالای خواب|پتو|ملحفه|پرده"),
    ("office_study", r"اداری|لوازم اداری|پرینتر|ماشین اداری|صندوق فروشگاهی|پوز"),
    ("health_wellness", r"سلامت|پزشکی|تجهیزات پزشکی|ارتوپدی"),
    ("sports_fitness", r"ورزشی|بدنسازی|باشگاه|دوچرخه|توپ|راکت|تردمیل|دمبل"),
    ("tools_industrial", r"ابزار|هویه|مته|پیچ و مهره|کمپرسور|باغبانی|تجهیزات ایمنی"),
    ("outdoor_travel", r"کمپینگ|کوهنوردی|چادر مسافرتی|لوازم سفر|ماهیگیری|چمدان"),
    ("gaming", r"گیمینگ|کنسول بازی|پلی استیشن|ایکس باکس|دسته بازی"),
    ("tabletop_games", r"بازی فکری|بازی رومیزی|بوردگیم"),
    ("arts_crafts", r"صنایع دستی|خیاطی|نقاشی|کاردستی|بافتنی"),
    ("events_decor", r"لوازم جشن|پرچم|وسایل تزئینی"),
)


def _number(value: object) -> float:
    try:
        result = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _normalize_taxonomy_text(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("\u200c", " ").replace("\u200f", " ").replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[\u064b-\u065f\u0670ـ]", "", text)
    text = re.sub(r"[\s،,:;؛|/_\-]+", " ", text).strip()
    return text


def infer_use_case_group(title: object, category: object = "") -> str:
    """Use product-title evidence first; consult retailer taxonomy only as fallback."""
    title_text = _normalize_taxonomy_text(title)
    category_text = _normalize_taxonomy_text(category)
    for source in (title_text, category_text):
        if not source:
            continue
        for group, pattern in _TEXT_GROUP_PATTERNS:
            if re.search(pattern, source, re.I):
                return group
    return "unknown"


def generality_score(use_case_group: object) -> float:
    group = str(use_case_group or "unknown").strip().lower()
    return float(GENERALITY_SCORES.get(group, GENERALITY_SCORES["unknown"]))


def discount_attractiveness_score(
    row: dict,
    independently_verified: bool = False,
) -> tuple[float, str]:
    """Score only internally consistent savings and discount evidence."""
    current = _number(row.get("current_price"))
    original = _number(row.get("original_price"))
    discount = _number(row.get("discount_percent"))
    savings = _number(row.get("savings_toman"))
    if not (current > 0 and original > current and savings > 0 and discount > 0):
        return 0.0, "invalid_or_missing_markdown"

    actual_savings = original - current
    actual_discount = round(100.0 * actual_savings / original)
    if round(savings) != round(actual_savings) or round(discount) != actual_discount:
        return 0.0, "inconsistent_markdown_arithmetic"

    percent_component = 100.0 * (1.0 - math.exp(-discount / 28.0))
    savings_component = 100.0 * (
        1.0 - math.exp(-math.log1p(savings / 100_000.0) / 4.0)
    )
    evidence = "fresh_independent_history_or_market" if independently_verified else "live_retailer_markdown_only"
    evidence_component = 100.0 if independently_verified else 45.0
    score = 0.50 * percent_component + 0.20 * savings_component + 0.30 * evidence_component
    return round(_clamp(score), 2), evidence


def discount_publish_gate(
    row: dict,
    independently_verified: bool = False,
    minimum_score: float = MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE,
) -> tuple[bool, float, str]:
    """Hard publication gate: demand and generality cannot excuse a weak or false markdown."""
    score, evidence = discount_attractiveness_score(row, independently_verified)
    try:
        floor = _clamp(float(minimum_score))
    except (TypeError, ValueError, OverflowError):
        floor = MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE
    return score >= floor, score, evidence


def harmonic_mean(scores: list[float]) -> float:
    values = [_clamp(_number(value)) for value in scores]
    if not values or any(value <= 0 for value in values):
        return 0.0
    return round(len(values) / sum(1.0 / value for value in values), 2)


def apply_three_factor_scores(
    records: list[dict],
    live_demand_score_fn: Callable[[dict], float],
    use_case_group_fn: Callable[[dict], str],
    discount_verified_fn: Callable[[dict], bool],
    now: datetime | None = None,
) -> list[dict]:
    """Annotate candidates with demand, generality and genuine discount only."""
    rows = [row for row in records if isinstance(row, dict)]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_iso = current.astimezone(timezone.utc).isoformat()

    for row in rows:
        demand = _clamp(_number(live_demand_score_fn(row)))
        group = str(use_case_group_fn(row) or "unknown")
        generality = generality_score(group)
        independently_verified = bool(discount_verified_fn(row))
        discount, discount_evidence = discount_attractiveness_score(row, independently_verified)
        components = [demand, generality, discount]
        row["offerchin_three_factor"] = {
            "policy_version": POLICY_VERSION,
            "factor_count": 3,
            "scored_at": current_iso,
            "live_demand": round(demand, 2),
            "generality": round(generality, 2),
            "discount_attractiveness": discount,
            "balanced_score": harmonic_mean(components),
            "weakest_factor_score": round(min(components), 2),
            "generality_group": group,
            "discount_evidence": discount_evidence,
            "score_interpretation": "three_factor_priority_index_not_conversion_probability",
        }
    return rows


def three_factor_sort_key(row: dict) -> tuple:
    score = row.get("offerchin_three_factor") if isinstance(row, dict) else None
    score = score if isinstance(score, dict) else {}
    required = ("live_demand", "generality", "discount_attractiveness")
    if any(_number(score.get(key)) <= 0 for key in required):
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        _number(score.get("balanced_score")),
        _number(score.get("weakest_factor_score")),
        _number(score.get("live_demand")),
        _number(score.get("discount_attractiveness")),
        _number(score.get("generality")),
    )


# Temporary API aliases keep older importing modules functional while policy
# and payload names are migrated. Neither alias adds an affordability factor.
apply_four_factor_scores = apply_three_factor_scores
four_factor_sort_key = three_factor_sort_key
