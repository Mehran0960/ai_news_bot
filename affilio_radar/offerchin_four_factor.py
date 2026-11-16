"""Three-factor OfferChin quality ranking.

The publication score balances current demand, use-case generality, and verified
discount attractiveness. It deliberately has no buyer-budget or affordability
dimension: listed price is not a proxy for who can afford a product.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_three_factor_harmonic_v1_no_affordability"
MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE = 40.0

# Heuristic reach scores, not market-share claims. Missing taxonomy is deliberately
# scored low rather than being mistaken for a mass-market product.
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

_TEXT_GROUP_PATTERNS = (
    ("software_tools", r"نرم افزار|نرم‌افزار|سیستم عامل|ویندوز|windows|office|autocad|driver ?pack"),
    ("home_cleaning", r"نظافت|شوینده|تمیزکننده|جارو|دستمال نظافت|اسکاچ"),
    ("grocery_food", r"مواد غذایی|خوراکی|نوشیدنی|چای|قهوه|شکلات|تنقلات|ادویه|کنسرو"),
    ("kitchen_food", r"آشپزخانه|آشپزی|قابلمه|تابه|کتری|چای ساز|قهوه ساز|ظروف غذا"),
    ("personal_care", r"بهداشتی|آرایشی|مراقبت پوست|مراقبت مو|مسواک|ضدآفتاب|عطر"),
    ("mobile_productivity", r"گوشی|موبایل|تبلت|لپ.?تاپ|کامپیوتر|شارژر|کابل|حافظه|مودم|روتر|تجهیزات شبکه|شبکه اکتیو|شبکه پسیو|هارد|ssd|رم|ماوس|موس|کیبورد|صفحه کلید|مانیتور|وبکم|فلش مموری"),
    ("home_living", r"خانه|اتاق خواب|دکوراسیون|دکوراتیو|ساعت دیواری|ساعت رومیزی|مبلمان|کالای خواب|پتو|ملحفه|پرده|فرش|میز|صندلی"),
    ("lighting_electrical", r"روشنایی|لامپ|چراغ|الکتریکی|سیم برق"),
    ("audio_visual", r"هدفون|هدست|هندزفری|ایرپاد|اسپیکر|تلویزیون|دوربین|آلات موسیقی|میکروفن|میکروفون|دانگل بلوتوث|بلوتوث"),
    ("office_study", r"اداری|لوازم تحریر|مدرسه|دانشجویی|پرینتر|نوشت افزار|صندوق فروشگاهی|ماشین های اداری|پوز|فروشگاهی"),
    ("baby_care", r"نوزاد|کودک|سیسمونی|پوشک|تغذیه کودک"),
    ("books_learning", r"کتاب|رمان|داستان|آموزشی|زبان آموزی"),
    ("fashion_lifestyle", r"پوشاک|لباس|کفش|کیف|عینک آفتابی|جوراب|انگشتر|زیورآلات|بوت|شلوار|کلاه"),
    ("health_wellness", r"سلامت|پزشکی|تجهیزات پزشکی|ارتوپدی"),
    ("sports_fitness", r"ورزشی|بدنسازی|باشگاه|دوچرخه|توپ|راکت"),
    ("automotive", r"خودرو|ماشین|لاستیک|تایر|روغن موتور|لوازم خودرو"),
    ("tools_industrial", r"ابزار|هویه|مته|پیچ و مهره|کمپرسور|باغبانی"),
    ("outdoor_travel", r"کمپینگ|کوهنوردی|چادر مسافرتی|لوازم سفر|ماهیگیری"),
    ("pet_care", r"حیوان خانگی|گربه|سگ|آکواریوم|غذای حیوان"),
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


def infer_use_case_group(title: object, category: object = "") -> str:
    text = " ".join((str(title or ""), str(category or ""))).lower()
    text = text.replace("\u200c", " ").replace("\u200f", " ").replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[\u064b-\u065f\u0670ـ]", "", text)
    text = re.sub(r"[\s،,:;؛|/_\-]+", " ", text).strip()
    for group, pattern in _TEXT_GROUP_PATTERNS:
        if re.search(pattern, text, re.I):
            return group
    return "unknown"


def generality_score(use_case_group: object) -> float:
    group = str(use_case_group or "unknown").strip().lower()
    return float(GENERALITY_SCORES.get(group, GENERALITY_SCORES["unknown"]))


def discount_attractiveness_score(
    row: dict,
    independently_verified: bool = False,
) -> tuple[float, str]:
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
    """A weak or arithmetically false markdown cannot be compensated by other scores."""
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
    price_group_fn: Callable[[dict], str] | None = None,
) -> list[dict]:
    """Score live demand, generality, and real discount; listed price is not a score input."""
    rows = [row for row in records if isinstance(row, dict)]
    groups = [str(use_case_group_fn(row) or "unknown") for row in rows]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_iso = current.astimezone(timezone.utc).isoformat()

    for index, row in enumerate(rows):
        demand = _clamp(_number(live_demand_score_fn(row)))
        generality = generality_score(groups[index])
        independently_verified = bool(discount_verified_fn(row))
        discount, discount_evidence = discount_attractiveness_score(row, independently_verified)
        components = [demand, generality, discount]
        row.pop("offerchin_four_factor", None)
        row["offerchin_three_factor"] = {
            "policy_version": POLICY_VERSION,
            "scored_at": current_iso,
            "live_demand": round(demand, 2),
            "generality": round(generality, 2),
            "discount_attractiveness": discount,
            "balanced_score": harmonic_mean(components),
            "weakest_factor_score": round(min(components), 2),
            "generality_group": groups[index],
            "discount_evidence": discount_evidence,
            "score_dimensions": ["live_demand", "generality", "discount_attractiveness"],
            "score_interpretation": "heuristic_priority_index_not_conversion_probability",
        }
    return rows


def three_factor_sort_key(row: dict) -> tuple:
    score = row.get("offerchin_three_factor") if isinstance(row, dict) else None
    score = score if isinstance(score, dict) else {}
    required = ("live_demand", "generality", "discount_attractiveness")
    values = [_number(score.get(key)) for key in required]
    if any(value <= 0 for value in values):
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        harmonic_mean(values),
        min(values),
        values[0],
        values[2],
        values[1],
    )


# Compatibility aliases for older imports. Both now use the three-factor policy;
# neither stores or scores an affordability dimension.
def apply_four_factor_scores(
    records: list[dict],
    live_demand_score_fn: Callable[[dict], float],
    use_case_group_fn: Callable[[dict], str],
    discount_verified_fn: Callable[[dict], bool],
    now: datetime | None = None,
    price_group_fn: Callable[[dict], str] | None = None,
) -> list[dict]:
    return apply_three_factor_scores(
        records, live_demand_score_fn, use_case_group_fn,
        discount_verified_fn, now=now, price_group_fn=price_group_fn,
    )


def four_factor_sort_key(row: dict) -> tuple:
    return three_factor_sort_key(row)
