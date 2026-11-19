"""Three-factor OfferChin ranking (legacy module/API name retained for compatibility).

The balanced priority index contains only live demand, product generality and
verified discount attractiveness. Product price/affordability is not a ranking
factor, gate, fallback criterion or proxy.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_three_factor_harmonic_v5"
MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE = 40.0

GENERALITY_SCORES = {
    "home_cleaning": 96, "grocery_food": 94, "kitchen_food": 92,
    "personal_care": 88, "mobile_productivity": 86, "software_tools": 40,
    "home_living": 84, "lighting_electrical": 82, "audio_visual": 78,
    "office_study": 74, "baby_care": 70, "books_learning": 68,
    "fashion_lifestyle": 64, "health_wellness": 62, "sports_fitness": 56,
    "automotive": 55, "tools_industrial": 53, "local_goods": 52,
    "outdoor_travel": 47, "pet_care": 44, "gaming": 40,
    "tabletop_games": 38, "events_decor": 36, "arts_crafts": 34,
    "general": 22, "unknown": 18,
}

_TEXT_GROUP_PATTERNS = (
    ("software_tools", r"نرم افزار|نرم‌افزار|سیستم عامل|ویندوز|windows|office|autocad|driver ?pack"),
    ("home_cleaning", r"نظافت|شوینده|تمیزکننده|جارو|دستمال نظافت|اسکاچ"),
    ("kitchen_food", r"آشپزخانه|آشپزی|قابلمه|تابه|کتری|چای ساز|چای‌ساز|قهوه ساز|قهوه‌ساز|ظروف غذا"),
    ("grocery_food", r"مواد غذایی|خوراکی|نوشیدنی|چای(?!\s*ساز)|قهوه(?!\s*ساز)|شکلات|تنقلات|ادویه|کنسرو|گوشت|مرغ|ماهی|میگو|سوسیس|کالباس|تخم مرغ|لبنیات|ماست|پنیر|شیر|دوغ|کره|خامه|بستنی|میوه|سبزی|صیفی|برنج|جو|گندم|آرد|حبوبات|روغن خوراکی|شکر|قند|نمک|رب|نوشابه|آبمیوه|آب معدنی|پودر سیر|غذای آماده"),
    ("personal_care", r"بهداشتی|آرایشی|مراقبت پوست|مراقبت مو|مسواک|ضدآفتاب|عطر"),
    ("baby_care", r"نوزاد|نوزادی|کودک|سیسمونی|پوشک|تغذیه کودک|اسباب بازی کودک"),
    ("books_learning", r"کتاب|رمان|داستان|مجله|زبان آموزی"),
    ("mobile_productivity", r"گوشی|موبایل|تبلت|لپ.?تاپ|کامپیوتر|شارژر|کابل|حافظه|مودم|روتر|تجهیزات شبکه|شبکه اکتیو|شبکه پسیو|هارد|ssd|(?<![\u0600-\u06ff])رم(?![\u0600-\u06ff])|\bram\b|ماوس|موس|کیبورد|صفحه کلید|مانیتور|وبکم|فلش مموری"),
    ("home_living", r"خانه|اتاق خواب|دکوراسیون|دکوراتیو|ساعت دیواری|ساعت رومیزی|مبلمان|کالای خواب|پتو|ملحفه|پرده"),
    ("lighting_electrical", r"روشنایی|لامپ|چراغ|الکتریکی|سیم برق"),
    ("audio_visual", r"هدفون|هدست|هندزفری|ایرپاد|اسپیکر|تلویزیون|دوربین|آلات موسیقی|میکروفن|میکروفون|دانگل بلوتوث|بلوتوث"),
    ("office_study", r"اداری|لوازم تحریر|مدرسه|دانشجویی|پرینتر|نوشت افزار|صندوق فروشگاهی|ماشین های اداری|پوز|فروشگاهی"),
    ("fashion_lifestyle", r"پوشاک|لباس|کفش|کیف|عینک آفتابی|جوراب|انگشتر|زیورآلات|بوت|شلوار|کلاه"),
    ("health_wellness", r"سلامت|پزشکی|تجهیزات پزشکی|ارتوپدی|مکمل"),
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
    """Score only consistent markdown arithmetic and evidence confidence; never rank by ticket price."""
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
    """A genuinely verified discount remains a hard gate; no other score can disguise a weak offer."""
    score, evidence = discount_attractiveness_score(row, independently_verified)
    try:
        floor = _clamp(float(minimum_score))
    except (TypeError, ValueError, OverflowError):
        floor = MIN_PUBLISHABLE_DISCOUNT_ATTRACTIVENESS_SCORE
    # A large retailer-declared markdown is not proof of a real bargain.
    # Independent, fresh price evidence is mandatory regardless of the score.
    return bool(independently_verified and score >= floor), score, evidence


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
    """Annotate a price-independent three-factor score.

    ``price_group_fn`` is accepted only for compatibility with catalog-sweep
    callers from older releases. It is deliberately ignored and cannot affect
    eligibility, ranking, or any score component.
    """
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
        balanced = harmonic_mean(components)
        row["offerchin_four_factor"] = {
            "policy_version": POLICY_VERSION,
            "scored_at": current_iso,
            "dimensions": ["live_demand", "generality", "discount_attractiveness"],
            "live_demand": round(demand, 2),
            "generality": round(generality, 2),
            "discount_attractiveness": discount,
            "balanced_score": balanced,
            "weakest_factor_score": round(min(components), 2),
            "generality_group": group,
            "discount_evidence": discount_evidence,
            "price_independent": True,
            "score_interpretation": "three_factor_heuristic_priority_index_not_conversion_probability",
        }
    return rows


def four_factor_sort_key(row: dict) -> tuple:
    """Legacy-compatible key name; rank only demand, generality and discount."""
    score = row.get("offerchin_four_factor") if isinstance(row, dict) else None
    score = score if isinstance(score, dict) else {}
    if any(
        _number(score.get(key)) <= 0
        for key in ("live_demand", "generality", "discount_attractiveness")
    ):
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        _number(score.get("balanced_score")),
        _number(score.get("weakest_factor_score")),
        _number(score.get("live_demand")),
        _number(score.get("discount_attractiveness")),
        _number(score.get("generality")),
    )


apply_three_factor_scores = apply_four_factor_scores
three_factor_sort_key = four_factor_sort_key
