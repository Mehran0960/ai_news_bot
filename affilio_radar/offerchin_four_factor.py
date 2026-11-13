"""Four-factor OfferChin ranking.

Scores are bounded 0..100. The aggregate uses a harmonic mean so a strong
single dimension cannot hide a serious weakness in another one.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_four_factor_v3_final_price_affordability"
# Conservative proxy: 1404 average rural household income was about 297.1m Toman/year
# (~24.76m/month), lower than the urban average. This is not a median or disposable income.
AFFORDABILITY_REFERENCE_MONTHLY_HOUSEHOLD_INCOME_TOMAN = 25_000_000
# A weak discount cannot be compensated for by demand, affordability or generality.
MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE = 40.0

# Heuristic reach scores, not market-share claims. Missing taxonomy is deliberately
# scored low rather than being mistaken for a mass-market product.
GENERALITY_SCORES = {
    "home_cleaning": 96,
    "grocery_food": 94,
    "kitchen_food": 92,
    "personal_care": 88,
    "mobile_productivity": 86,
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
    ("home_cleaning", r"نظافت|شوینده|تمیزکننده|جارو|دستمال نظافت|اسکاچ"),
    ("grocery_food", r"مواد غذایی|خوراکی|نوشیدنی|چای|قهوه|شکلات|تنقلات|ادویه|کنسرو"),
    ("kitchen_food", r"آشپزخانه|آشپزی|قابلمه|تابه|کتری|چای ساز|قهوه ساز|ظروف غذا"),
    ("personal_care", r"بهداشتی|آرایشی|مراقبت پوست|مراقبت مو|مسواک|ضدآفتاب|عطر"),
    ("mobile_productivity", r"گوشی|موبایل|تبلت|لپ.?تاپ|کامپیوتر|شارژر|کابل|حافظه|مودم|ماوس|موس|کیبورد|صفحه کلید|مانیتور|وبکم|فلش مموری"),
    ("home_living", r"خانه|اتاق خواب|دکوراسیون|مبلمان|کالای خواب|پتو|ملحفه|پرده"),
    ("lighting_electrical", r"روشنایی|لامپ|چراغ|الکتریکی|سیم برق"),
    ("audio_visual", r"هدفون|هدست|هندزفری|ایرپاد|اسپیکر|تلویزیون|دوربین"),
    ("office_study", r"اداری|لوازم تحریر|مدرسه|دانشجویی|پرینتر|نوشت افزار"),
    ("baby_care", r"نوزاد|کودک|سیسمونی|پوشک|تغذیه کودک"),
    ("books_learning", r"کتاب|رمان|داستان|آموزشی|زبان آموزی"),
    ("fashion_lifestyle", r"پوشاک|لباس|کفش|کیف|عینک آفتابی|جوراب"),
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


def affordability_absolute_score(
    price_toman: object,
    reference_monthly_income_toman: object = AFFORDABILITY_REFERENCE_MONTHLY_HOUSEHOLD_INCOME_TOMAN,
) -> float:
    """Score the full cash price against a conservative monthly household-income proxy."""
    price = _number(price_toman)
    reference = _number(reference_monthly_income_toman)
    if price <= 0 or reference <= 0:
        return 0.0

    share = price / reference
    # The score falls as the final cash ticket consumes a larger share of monthly
    # household income. This is deliberately absolute: no category-cohort ranking
    # and no installment down-payment substitution.
    bands = (
        (0.01, 100.0),
        (0.025, 90.0),
        (0.05, 80.0),
        (0.10, 65.0),
        (0.20, 45.0),
        (0.35, 25.0),
    )
    for maximum_share, score in bands:
        if share <= maximum_share:
            return score
    return 10.0


def _entry_price_toman(row: dict) -> tuple[float, str]:
    """Return the full final cash price; installments never replace product affordability."""
    price = _number(row.get("current_price"))
    if price <= 0:
        return 0.0, "missing_final_cash_price"
    return price, "full_final_cash_price"


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
    """Hard publication gate for discount value; other factors cannot compensate for a weak deal."""
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


def apply_four_factor_scores(
    records: list[dict],
    live_demand_score_fn: Callable[[dict], float],
    use_case_group_fn: Callable[[dict], str],
    discount_verified_fn: Callable[[dict], bool],
    now: datetime | None = None,
    price_group_fn: Callable[[dict], str] | None = None,
) -> list[dict]:
    """Annotate a candidate cohort in place and return it, preserving input order."""
    rows = [row for row in records if isinstance(row, dict)]
    groups = [str(use_case_group_fn(row) or "unknown") for row in rows]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_iso = current.astimezone(timezone.utc).isoformat()

    for index, row in enumerate(rows):
        demand = _clamp(_number(live_demand_score_fn(row)))
        final_cash_price, affordability_basis = _entry_price_toman(row)
        affordability = affordability_absolute_score(final_cash_price)
        generality = generality_score(groups[index])
        independently_verified = bool(discount_verified_fn(row))
        discount, discount_evidence = discount_attractiveness_score(row, independently_verified)
        components = [demand, affordability, generality, discount]
        balanced = harmonic_mean(components)
        row["offerchin_four_factor"] = {
            "policy_version": POLICY_VERSION,
            "scored_at": current_iso,
            "live_demand": round(demand, 2),
            "affordability": round(_clamp(affordability), 2),
            "generality": round(generality, 2),
            "discount_attractiveness": discount,
            "balanced_score": balanced,
            "weakest_factor_score": round(min(components), 2),
            "generality_group": groups[index],
            "affordability_basis": affordability_basis,
            "affordability_reference_monthly_income_toman": AFFORDABILITY_REFERENCE_MONTHLY_HOUSEHOLD_INCOME_TOMAN,
            "price_cohort_size": 0,
            "price_cohort_key": "absolute_final_cash_price",
            "discount_evidence": discount_evidence,
            "score_interpretation": "heuristic_priority_index_not_conversion_probability",
        }
    return rows


def four_factor_sort_key(row: dict) -> tuple:
    score = row.get("offerchin_four_factor") if isinstance(row, dict) else None
    score = score if isinstance(score, dict) else {}
    # Incomplete legacy/test cards must fall back to the pre-existing demand/deal
    # order rather than being spuriously rearranged by partial four-factor data.
    if any(
        _number(score.get(key)) <= 0
        for key in ("live_demand", "affordability", "generality", "discount_attractiveness")
    ):
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        _number(score.get("balanced_score")),
        _number(score.get("weakest_factor_score")),
        _number(score.get("live_demand")),
        _number(score.get("discount_attractiveness")),
        _number(score.get("generality")),
        _number(score.get("affordability")),
    )
