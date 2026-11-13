"""Four-factor OfferChin ranking.

Scores are bounded 0..100. The aggregate uses a harmonic mean so a strong
single dimension cannot hide a serious weakness in another one.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_four_factor_harmonic_v3_market_affordability"
MIN_PRICE_COHORT_SIZE = 8
# 1404 (2025/26) average urban household spending was ~32.66m toman/month.
# Round down for a conservative nationwide proxy; this is not an individual income estimate.
AFFORDABILITY_MONTHLY_HOUSEHOLD_SPEND_BENCHMARK_TOMAN = 30_000_000
AFFORDABILITY_BENCHMARK_SOURCE = "Iran Statistical Center 1404 household expenditure survey; urban average rounded down"
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


def affordability_absolute_score(price_toman: object) -> float:
    """Score the final cash price against a conservative monthly household-spend benchmark.

    Every doubling of the share of monthly household expenditure lowers the score by
    10 points. Installment down-payments are intentionally excluded: the customer
    ultimately commits to the full final product price, not just the initial payment.
    """
    price = _number(price_toman)
    if price <= 0:
        return 0.0
    benchmark = float(AFFORDABILITY_MONTHLY_HOUSEHOLD_SPEND_BENCHMARK_TOMAN)
    # 0.5% of monthly spending is the 100-point anchor; 1%, 2%, 4%, ... decline
    # by ten points per doubling. Clamp at 10 so only missing/invalid price is zero.
    share = price / benchmark
    score = 100.0 - 10.0 * math.log2(max(share / 0.005, 1.0))
    return _clamp(score, 10.0, 100.0)


def _relative_price_scores(records: list[dict], groups: list[str]) -> dict[int, float]:
    buckets: dict[str, list[tuple[int, float]]] = {}
    for index, row in enumerate(records):
        price = _number(row.get("current_price"))
        if price > 0:
            buckets.setdefault(groups[index], []).append((index, price))
    result: dict[int, float] = {}
    for items in buckets.values():
        if len(items) < MIN_PRICE_COHORT_SIZE:
            continue
        ordered = sorted(items, key=lambda pair: pair[1])
        # Mid-rank handles tied prices without arbitrary ordering.
        cursor = 0
        while cursor < len(ordered):
            end = cursor + 1
            while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
                end += 1
            average_rank = (cursor + end - 1) / 2
            score = 100.0 * (1.0 - average_rank / max(1, len(ordered) - 1))
            for position in range(cursor, end):
                result[ordered[position][0]] = _clamp(score)
            cursor = end
    return result


def _entry_price_toman(row: dict) -> tuple[float, str]:
    """Use the final cash price as the primary affordability measure, never the down-payment."""
    price = _number(row.get("current_price"))
    if price <= 0:
        return 0.0, "missing_final_cash_price"
    return price, "final_cash_price_vs_household_spend_proxy"


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
    price_groups = [
        str((price_group_fn(row) if price_group_fn else groups[index]) or groups[index])
        for index, row in enumerate(rows)
    ]
    relative_prices = _relative_price_scores(rows, price_groups)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current_iso = current.astimezone(timezone.utc).isoformat()

    cohort_sizes = {
        group: sum(1 for index, candidate in enumerate(rows)
                   if price_groups[index] == group and _number(candidate.get("current_price")) > 0)
        for group in price_groups
    }
    for index, row in enumerate(rows):
        demand = _clamp(_number(live_demand_score_fn(row)))
        entry_price, affordability_basis = _entry_price_toman(row)
        absolute = affordability_absolute_score(entry_price)
        relative = relative_prices.get(index)
        affordability = absolute if relative is None else 0.65 * absolute + 0.35 * relative
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
            "affordability_monthly_household_spend_benchmark_toman": AFFORDABILITY_MONTHLY_HOUSEHOLD_SPEND_BENCHMARK_TOMAN,
            "affordability_benchmark_source": AFFORDABILITY_BENCHMARK_SOURCE,
            "affordability_price_to_monthly_spend_percent": round(
                100.0 * _number(row.get("current_price")) / AFFORDABILITY_MONTHLY_HOUSEHOLD_SPEND_BENCHMARK_TOMAN,
                3,
            ),
            "price_cohort_size": cohort_sizes.get(price_groups[index], 0) if relative is not None else 0,
            "price_cohort_key": price_groups[index],
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
