"""Four-factor OfferChin ranking.

Scores are bounded 0..100. The aggregate uses a harmonic mean so a strong
single dimension cannot hide a serious weakness in another one.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable


POLICY_VERSION = "offerchin_four_factor_evidence_gated_v2"
MIN_PRICE_COHORT_SIZE = 8

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
    "catalog_taxonomy_other": 30,
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
    """A cash-ticket-size proxy; never represents the buyer's actual income."""
    price = _number(price_toman)
    if price <= 0:
        return 0.0
    # Anchors: 100k=100, 1m=85, 10m=70, 100m=55, 1bn=40 toman.
    return _clamp(100.0 - 15.0 * math.log10(max(price, 100_000.0) / 100_000.0))


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
    price = _number(row.get("current_price"))
    if price <= 0:
        return 0.0, "missing_cash_price"

    # A lower entry ticket is counted only when the record explicitly marks the
    # terms verified and provides the initial payment. Generic installment copy
    # or a product-level DigiPay mention is not proof of an applicable plan.
    if row.get("installment_terms_verified") is True:
        entry = _number(
            row.get("installment_down_payment_toman")
            or row.get("installment_entry_payment_toman")
        )
        if entry > 0 and entry <= price:
            return entry, "verified_installment_down_payment"
    return price, "cash_price"


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

        rank = _number(row.get("catalog_best_selling_rank"))
        rank_observed_at = str(row.get("catalog_rank_observed_at") or "").strip()
        demand_source = str(row.get("demand_signal_source") or "").strip()
        if rank > 0:
            demand_source = "digikala_native_bestseller_rank"
            demand_quality = "direct_relative_sales_rank_not_units_sold"
            demand_observed_at = rank_observed_at or None
        elif demand_source in {
            "digikala_recent_review_growth",
            "snappshop_recent_review_growth",
        }:
            demand_quality = "indirect_review_growth_not_sales"
            demand_observed_at = str(row.get("demand_observed_at") or "").strip() or None
        elif demand > 0:
            demand_source = str(
                row.get("live_demand_evidence_source") or "validated_live_demand_callback"
            )
            demand_quality = "callback_validated_live_signal"
            demand_observed_at = (
                str(row.get("demand_observed_at") or "").strip()
                or rank_observed_at or None
            )
        else:
            demand_source = "none"
            demand_quality = "missing"
            demand_observed_at = None

        generality_group = groups[index]
        generality_classified = (
            generality_group in GENERALITY_SCORES
            and generality_group not in {"unknown", "general"}
        )
        affordability_verified = bool(
            _number(row.get("current_price")) > 0 and entry_price > 0
        )
        discount_verified = independently_verified is True
        evidence_gaps = []
        if demand <= 0:
            evidence_gaps.append("live_demand_missing")
        if not affordability_verified:
            evidence_gaps.append("current_entry_price_missing")
        if not generality_classified:
            evidence_gaps.append("generality_taxonomy_unclassified")
        if not discount_verified:
            evidence_gaps.append("independent_discount_proof_missing")

        history_verified = (
            row.get("history_status") == "verified"
            and row.get("historical_deal_eligible") is True
        )
        market_verified = (
            row.get("market_status") == "verified"
            and row.get("market_reference_kind") == "seller_median"
        )
        if history_verified:
            discount_source = "verified_same_product_price_history"
            discount_observed_at = str(row.get("history_checked_at") or "").strip() or None
            discount_confidence = "verified_same_sku_history"
        elif market_verified:
            discount_source = "verified_same_product_market_median"
            discount_observed_at = str(row.get("market_price_checked_at") or "").strip() or None
            discount_confidence = "verified_comparable_seller_median"
        else:
            discount_source = "retailer_markdown_only_unverified"
            discount_observed_at = None
            discount_confidence = "retailer_claim_only"

        demand_observation_value = _number(
            row.get("live_demand_observation_value")
        )
        demand_observation_unit = str(
            row.get("live_demand_observation_unit") or ""
        ).strip()
        if demand_observation_value <= 0 and rank > 0:
            demand_observation_value = rank
            demand_observation_unit = "category_rank"
        elif demand_observation_value <= 0 and demand > 0:
            demand_observation_value = _number(
                row.get("recent_review_growth_window", row.get("recent_review_growth_7d"))
            )
            demand_observation_unit = "reviews_per_observation_window"
        demand_confidence = str(
            row.get("live_demand_confidence") or demand_quality
        ).strip()

        taxonomy_evidence = {
            "category_id": str(
                row.get("catalog_category_id")
                or row.get("catalog_best_selling_category_id") or ""
            ).strip() or None,
            "category_name": str(
                row.get("catalog_category_name")
                or row.get("catalog_best_selling_category_name") or ""
            ).strip() or None,
            "product_title": str(row.get("title") or "").strip() or None,
        }

        row["offerchin_four_factor"] = {
            "policy_version": POLICY_VERSION,
            "scored_at": current_iso,
            "live_demand": round(demand, 2),
            "affordability": round(_clamp(affordability), 2),
            "generality": round(generality, 2),
            "discount_attractiveness": discount,
            "balanced_score": balanced,
            "weakest_factor_score": round(min(components), 2),
            "generality_group": generality_group,
            "affordability_basis": affordability_basis,
            "price_cohort_size": cohort_sizes.get(price_groups[index], 0) if relative is not None else 0,
            "price_cohort_key": price_groups[index],
            "discount_evidence": discount_evidence,
            "evidence_complete": not evidence_gaps,
            "evidence_gaps": evidence_gaps,
            "factor_evidence": {
                "live_demand": {
                    "status": "verified" if demand > 0 else "missing",
                    "score": round(demand, 2),
                    "source": demand_source,
                    "observed_at": demand_observed_at,
                    "value": demand_observation_value if demand_observation_value > 0 else None,
                    "unit": demand_observation_unit or "validated_score_0_100",
                    "quality": demand_quality,
                    "confidence": demand_confidence,
                },
                "affordability": {
                    "status": "verified" if affordability_verified else "missing",
                    "score": round(_clamp(affordability), 2),
                    "source": affordability_basis,
                    "value": round(entry_price) if entry_price > 0 else None,
                    "entry_price_toman": round(entry_price) if entry_price > 0 else None,
                    "unit": "toman",
                    "confidence": (
                        "sku_installment_terms_verified"
                        if affordability_basis == "verified_installment_down_payment"
                        else "live_current_cash_price"
                    ),
                },
                "generality": {
                    "status": "verified" if generality_classified else "unclassified",
                    "score": round(generality, 2),
                    "source": "taxonomy_and_use_case_classifier",
                    "value": generality_group,
                    "unit": "use_case_class",
                    "confidence": "heuristic_taxonomy_mapping_not_market_survey",
                    "taxonomy": taxonomy_evidence,
                    "use_case_group": generality_group,
                },
                "discount_attractiveness": {
                    "status": "independently_verified" if discount_verified else "unverified",
                    "score": discount,
                    "source": discount_source,
                    "observed_at": discount_observed_at,
                    "value": {
                        "current_price_toman": round(_number(row.get("current_price"))),
                        "original_price_toman": round(_number(row.get("original_price"))),
                        "discount_percent": round(_number(row.get("discount_percent")), 2),
                        "savings_toman": round(_number(row.get("savings_toman"))),
                    },
                    "unit": "toman_and_percent",
                    "confidence": discount_confidence,
                },
            },
            "score_interpretation": "heuristic_priority_index_not_conversion_probability",
        }
    return rows


def _valid_observation_timestamp(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return False
    return parsed.tzinfo is not None


def four_factor_evidence_gate(row: dict) -> tuple[bool, list[str]]:
    """Fail closed unless all four dimensions carry source, unit, confidence and observations."""
    score = row.get("offerchin_four_factor") if isinstance(row, dict) else None
    if not isinstance(score, dict) or score.get("policy_version") != POLICY_VERSION:
        return False, ["four_factor_score_missing_or_stale"]
    gaps = score.get("evidence_gaps")
    gaps = [str(item) for item in gaps if item] if isinstance(gaps, list) else []
    evidence = score.get("factor_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}

    demand = evidence.get("live_demand") if isinstance(evidence.get("live_demand"), dict) else {}
    if (
        demand.get("status") != "verified"
        or not str(demand.get("source") or "").strip()
        or not _valid_observation_timestamp(demand.get("observed_at"))
        or _number(demand.get("value")) <= 0
        or not str(demand.get("unit") or "").strip()
        or not str(demand.get("confidence") or "").strip()
    ):
        gaps.append("live_demand_provenance_incomplete")

    affordability = evidence.get("affordability") if isinstance(evidence.get("affordability"), dict) else {}
    if (
        affordability.get("status") != "verified"
        or not str(affordability.get("source") or "").strip()
        or _number(affordability.get("entry_price_toman")) <= 0
        or affordability.get("unit") != "toman"
        or not str(affordability.get("confidence") or "").strip()
    ):
        gaps.append("affordability_provenance_incomplete")

    generality = evidence.get("generality") if isinstance(evidence.get("generality"), dict) else {}
    if (
        generality.get("status") != "verified"
        or not str(generality.get("source") or "").strip()
        or generality.get("use_case_group") in {None, "", "general", "unknown"}
        or generality.get("unit") != "use_case_class"
        or not str(generality.get("confidence") or "").strip()
    ):
        gaps.append("generality_provenance_incomplete")

    discount = evidence.get("discount_attractiveness") if isinstance(evidence.get("discount_attractiveness"), dict) else {}
    discount_value = discount.get("value") if isinstance(discount.get("value"), dict) else {}
    if (
        discount.get("status") != "independently_verified"
        or not str(discount.get("source") or "").startswith("verified_same_product_")
        or not _valid_observation_timestamp(discount.get("observed_at"))
        or discount.get("unit") != "toman_and_percent"
        or not str(discount.get("confidence") or "").strip()
        or _number(discount_value.get("current_price_toman")) <= 0
        or _number(discount_value.get("original_price_toman")) <= _number(discount_value.get("current_price_toman"))
        or _number(discount_value.get("discount_percent")) <= 0
        or _number(discount_value.get("savings_toman")) <= 0
    ):
        gaps.append("discount_provenance_incomplete")

    # Keep rejection reasons unique and deterministic for metrics.
    gaps = list(dict.fromkeys(gaps))
    if score.get("evidence_complete") is not True and not gaps:
        gaps = ["four_factor_evidence_incomplete"]
    return not gaps and score.get("evidence_complete") is True, gaps


def four_factor_sort_key(row: dict) -> tuple:
    score = row.get("offerchin_four_factor") if isinstance(row, dict) else None
    score = score if isinstance(score, dict) else {}
    # Diagnostic sorts put incomplete records last. Public selectors must apply
    # four_factor_evidence_gate before sorting; there is no public legacy fallback.
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
