"""Balanced four-factor scoring for OfferChin product selection.

The scores are ranking aids, not estimates of unit sales or household income.
Hard product, demand-evidence, stock, price, link, safety, expiry, and anti-repeat
gates remain outside this module and must be enforced by the caller.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Callable, Iterable


SCORE_VERSION = "four-factor-equal-weight-v1"
FACTOR_WEIGHTS = {
    "live_demand": 0.25,
    "affordability": 0.25,
    "generality": 0.25,
    "discount_attractiveness": 0.25,
}
AFFORDABILITY_PRICE_ANCHOR_TOMAN = 250_000
DEMAND_MAX_RANK = 60
DEMAND_MAX_AGE_HOURS = 24
REVIEW_MIN_WINDOW_HOURS = 6
REVIEW_MAX_WINDOW_HOURS = 24
REVIEW_MAX_SIGNAL_AGE_HOURS = 12

# Category-level reach proxy, not population or sales data.
GENERALITY_BY_USE_CASE = {
    "grocery_food": 96,
    "home_cleaning": 94,
    "kitchen_food": 92,
    "home_living": 88,
    "personal_care": 86,
    "local_goods": 70,
    "health_wellness": 62,
    "fashion_lifestyle": 82,
    "baby_care": 80,
    "mobile_productivity": 79,
    "lighting_electrical": 76,
    "audio_visual": 74,
    "automotive": 72,
    "sports_fitness": 70,
    "books_learning": 68,
    "office_study": 66,
    "pet_care": 62,
    "outdoor_travel": 58,
    "gaming": 58,
    "tools_industrial": 56,
    "tabletop_games": 55,
    "arts_crafts": 52,
    "events_decor": 50,
    "catalog_taxonomy_other": 45,
    "general": 40,
}
GENERALITY_KEYWORDS = (
    ("grocery_food", r"خوراکی|خواربار|مواد غذایی|قهوه|چای|آجیل|خشکبار|تنقلات|محصولات بومی|محصولات محلی|سوغات محلی"),
    ("home_cleaning", r"نظافت|شوینده|پاک کننده|اسکاچ|دستمال|جارو|تمیزکاری"),
    ("kitchen_food", r"آشپزخانه|قابلمه|تابه|ظروف|پخت و پز|ابزار آشپزی"),
    ("personal_care", r"آرایش|پوست|مراقبت مو|شامپو|ماسک مو|سرم مو|بهداشت شخصی|عطر|ادکلن|اصلاح|مسواک|دهان شویه|ضدآفتاب"),
    ("home_living", r"خانه|منزل|خواب|مبلمان|دکوراسیون|فرش|پرده"),
    ("fashion_lifestyle", r"پوشاک|لباس|کفش|کیف|کوله|اکسسوری"),
    ("baby_care", r"کودک|نوزاد|مادر و کودک"),
    ("mobile_productivity", r"موبایل|گوشی|لپ تاپ|کامپیوتر|تبلت|لوازم دیجیتال"),
    ("lighting_electrical", r"روشنایی|لامپ|چراغ|برق|باتری|پاوربانک"),
    ("audio_visual", r"صوتی|تصویری|هدفون|هندزفری|اسپیکر|تلویزیون"),
    ("automotive", r"خودرو|ماشین|موتور|لاستیک|تایر"),
    ("sports_fitness", r"ورزشی|بدنسازی|تناسب اندام|دوچرخه"),
    ("books_learning", r"کتاب|آموزشی|یادگیری"),
    ("office_study", r"اداری|تحریر|مدرسه|دانشگاه|پرینتر|نوشت افزار"),
    ("pet_care", r"حیوانات خانگی|گربه|سگ|خوراک حیوان"),
    ("outdoor_travel", r"سفر|کمپینگ|کوهنوردی|ماهیگیری"),
    ("gaming", r"گیمینگ|کنسول|پلی استیشن|ایکس باکس"),
    ("tools_industrial", r"ابزار|صنعتی|دریل|پیچ گوشتی"),
    ("tabletop_games", r"بازی فکری|بازی رومیزی|بوردگیم"),
    ("arts_crafts", r"هنری|نقاشی|صنایع دستی|خیاطی"),
    ("events_decor", r"جشن|پرچم|تزئینی"),
)


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _utc(value) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _now(value=None) -> datetime:
    parsed = _utc(value) if value is not None else None
    return parsed or datetime.now(timezone.utc)


def _fresh_bestseller_evidence(record: dict, now: datetime) -> dict:
    product_id = str(record.get("product_id") or "").strip().lower()
    if not product_id.startswith("dkp-") or record.get("catalog_sort_mode") != "best_selling":
        return {}

    raw_rows = record.get("catalog_best_selling_ranks_by_category")
    raw_rows = raw_rows if isinstance(raw_rows, dict) else {}
    observations = []
    for category_id, entry in raw_rows.items():
        if not str(category_id).isdigit() or not isinstance(entry, dict):
            continue
        rank = _int(entry.get("rank"))
        observed = _utc(entry.get("observed_at"))
        if not 1 <= rank <= DEMAND_MAX_RANK or observed is None:
            continue
        age = (now - observed).total_seconds() / 3600
        if not 0 <= age <= DEMAND_MAX_AGE_HOURS:
            continue

        momentum = 0
        history = entry.get("rank_history")
        if isinstance(history, list):
            prior = []
            for sample in history:
                if not isinstance(sample, dict):
                    continue
                old_rank = _int(sample.get("rank"))
                old_at = _utc(sample.get("observed_at"))
                if old_at is None or not 1 <= old_rank <= DEMAND_MAX_RANK:
                    continue
                elapsed = (observed - old_at).total_seconds() / 3600
                if 6 <= elapsed <= 24 * 7:
                    prior.append((old_at, old_rank))
            if prior:
                _, prior_rank = max(prior, key=lambda item: item[0])
                momentum = max(0, prior_rank - rank)
        observations.append({
            "rank": rank,
            "age_hours": age,
            "category_id": str(category_id),
            "momentum": momentum,
        })

    if not observations:
        rank = _int(record.get("catalog_best_selling_rank"))
        observed = _utc(record.get("catalog_rank_observed_at"))
        category_id = str(
            record.get("catalog_best_selling_category_id")
            or record.get("catalog_category_id")
            or ""
        )
        if observed is not None:
            age = (now - observed).total_seconds() / 3600
            if 1 <= rank <= DEMAND_MAX_RANK and 0 <= age <= DEMAND_MAX_AGE_HOURS:
                observations.append({
                    "rank": rank,
                    "age_hours": age,
                    "category_id": category_id,
                    "momentum": 0,
                })
    if not observations:
        return {}
    best = min(observations, key=lambda row: (row["rank"], row["age_hours"]))
    return {
        **best,
        "category_count": len({row["category_id"] for row in observations if row["category_id"]}),
        "max_momentum": max(row["momentum"] for row in observations),
    }


def _fresh_review_growth(record: dict, now: datetime) -> tuple[bool, float]:
    if record.get("current_demand_verified") is not True:
        return False, 0.0
    growth = _int(record.get("recent_review_growth_window", record.get("recent_review_growth_7d")))
    window_hours = _float(record.get("demand_window_hours"))
    source = str(record.get("demand_signal_source") or "")
    observed = _utc(record.get("demand_observed_at"))
    if (
        growth < 1
        or not REVIEW_MIN_WINDOW_HOURS <= window_hours <= REVIEW_MAX_WINDOW_HOURS
        or source not in {"digikala_recent_review_growth", "snappshop_recent_review_growth"}
        or observed is None
    ):
        return False, 0.0
    age_hours = (now - observed).total_seconds() / 3600
    if not -0.1 <= age_hours <= REVIEW_MAX_SIGNAL_AGE_HOURS:
        return False, 0.0
    growth_per_day = growth * 24.0 / max(1.0, window_hours)
    return True, growth_per_day


def _demand_score(record: dict, now: datetime) -> int:
    evidence = _fresh_bestseller_evidence(record, now)
    if evidence:
        rank_score = 100.0 - ((evidence["rank"] - 1) / (DEMAND_MAX_RANK - 1)) * 32.0
        freshness_bonus = 3.0 * (1.0 - evidence["age_hours"] / DEMAND_MAX_AGE_HOURS)
        category_bonus = min(4.0, max(0, evidence["category_count"] - 1) * 2.0)
        momentum_bonus = min(6.0, evidence["max_momentum"] * 0.5)
        return max(0, min(100, round(rank_score + freshness_bonus + category_bonus + momentum_bonus)))

    is_fresh, growth_per_day = _fresh_review_growth(record, now)
    if not is_fresh:
        return 0
    # Review growth is explicitly a weaker proxy than native bestseller rank.
    return max(0, min(65, round(35 + 16 * math.log10(1 + growth_per_day))))


def _price_percentile_score(prices: list[int], price: int) -> int:
    if not prices:
        return 50
    ordered = sorted(prices)
    if len(ordered) == 1:
        return 50
    below = sum(1 for value in ordered if value < price)
    equal = sum(1 for value in ordered if value == price)
    mid_rank = below + (equal - 1) / 2
    return max(0, min(100, round(100 * (1 - mid_rank / (len(ordered) - 1)))))


def _absolute_price_score(price: int) -> int:
    if price <= 0:
        return 0
    relative = price / AFFORDABILITY_PRICE_ANCHOR_TOMAN
    return max(0, min(100, round(100 - 20 * math.log10(relative))))


def _infer_use_case(record: dict) -> str:
    category = record.get("catalog_best_selling_category_name") or record.get("catalog_category_name") or ""
    path = record.get("catalog_category_path") or record.get("category_path") or ""
    if isinstance(path, (list, tuple)):
        path = " ".join(
            str(item.get("name") or item.get("title") or "") if isinstance(item, dict) else str(item)
            for item in path
        )
    raw = " ".join((str(category or ""), str(path or ""), str(record.get("title") or "")))
    normalized = raw.lower().replace("\u200c", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    for key, pattern in GENERALITY_KEYWORDS:
        if re.search(pattern, normalized, re.I):
            return key
    if record.get("catalog_best_selling_category_id") or record.get("catalog_category_id"):
        return "catalog_taxonomy_other"
    return "general"


def _generality_score(use_case: str) -> int:
    return GENERALITY_BY_USE_CASE.get(str(use_case or "general"), GENERALITY_BY_USE_CASE["catalog_taxonomy_other"])


def _verified_discount_evidence(record: dict, now: datetime) -> tuple[bool, bool, float]:
    history_at = _utc(record.get("history_checked_at"))
    history_fresh = (
        history_at is not None
        and -0.1 <= (now - history_at).total_seconds() / 3600 <= 24
    )
    history_verified = (
        history_fresh
        and record.get("history_status") == "verified"
        and record.get("historical_deal_eligible") is True
    )

    market_at = _utc(record.get("market_price_checked_at"))
    market_fresh = (
        market_at is not None
        and -0.1 <= (now - market_at).total_seconds() / 3600 <= 24
    )
    advantage = _float(record.get("market_price_advantage_pct"), -999.0)
    market_verified = (
        market_fresh
        and record.get("market_status") == "verified"
        and record.get("market_reference_kind") == "seller_median"
        and advantage >= 5
    )
    if record.get("history_status") == "verified" and history_fresh and record.get("historical_deal_eligible") is False:
        return False, False, 0.0
    if record.get("market_status") == "verified" and market_fresh and record.get("market_reference_kind") == "seller_median" and advantage <= -5:
        return False, False, 0.0
    return history_verified, market_verified, max(0.0, advantage if market_verified else 0.0)


def _discount_score(record: dict, now: datetime) -> int:
    discount = _int(record.get("discount_percent"))
    savings = _int(record.get("savings_toman"))
    current_price = _int(record.get("current_price") or record.get("listed_current_price") or record.get("last_checked_price"))
    original_price = _int(record.get("original_price") or record.get("listed_original_price") or record.get("last_checked_original_price"))
    if (
        not 1 <= discount <= 100
        or savings <= 0
        or current_price <= 0
        or original_price <= current_price
        or original_price - current_price != savings
        or round(100 * savings / original_price) != discount
    ):
        return 0

    history_verified, market_verified, advantage = _verified_discount_evidence(record, now)
    percent_component = min(75.0, discount * 1.5)
    savings_component = min(15.0, 5.0 * math.log10(1 + savings / 100_000))
    verification_bonus = (42.0 if history_verified else 0.0) + (8.0 if market_verified and history_verified else 42.0 if market_verified else 0.0)
    market_bonus = min(5.0, advantage * 0.2) if market_verified else 0.0
    score = min(100.0, percent_component + savings_component + verification_bonus + market_bonus)
    if not (history_verified or market_verified):
        # A displayed markdown is not a proven bargain without price-history/market evidence.
        score = min(score, 40.0)
    return max(0, min(100, round(score)))


def score_candidates(
    records: Iterable[dict],
    *,
    now=None,
    use_case_resolver: Callable[[dict], str] | None = None,
) -> list[dict]:
    """Annotate a candidate pool with four equally weighted, evidence-labelled scores."""
    current = _now(now)
    source_rows = [row for row in records or [] if isinstance(row, dict)]
    use_cases = {}
    prices_by_use_case: dict[str, list[int]] = {}
    all_prices = []
    for index, row in enumerate(source_rows):
        use_case = (
            str(use_case_resolver(row) or "general")
            if use_case_resolver else _infer_use_case(row)
        )
        use_cases[index] = use_case
        price = _int(row.get("current_price") or row.get("listed_current_price") or row.get("last_checked_price"))
        if price > 0:
            all_prices.append(price)
            prices_by_use_case.setdefault(use_case, []).append(price)

    scored = []
    for index, row in enumerate(source_rows):
        candidate = dict(row)
        use_case = use_cases[index]
        price = _int(candidate.get("current_price") or candidate.get("listed_current_price") or candidate.get("last_checked_price"))
        global_percentile = _price_percentile_score(all_prices, price) if price > 0 else 0
        local_prices = prices_by_use_case.get(use_case, [])
        local_percentile = (
            _price_percentile_score(local_prices, price)
            if price > 0 and len(local_prices) >= 3
            else 50
        )
        absolute = _absolute_price_score(price)
        affordability = (
            round(0.50 * absolute + 0.25 * global_percentile + 0.25 * local_percentile)
            if price > 0 else 0
        )
        demand = _demand_score(candidate, current)
        generality = _generality_score(use_case)
        discount = _discount_score(candidate, current)
        combined = round(
            demand * FACTOR_WEIGHTS["live_demand"]
            + affordability * FACTOR_WEIGHTS["affordability"]
            + generality * FACTOR_WEIGHTS["generality"]
            + discount * FACTOR_WEIGHTS["discount_attractiveness"]
        )
        factors = {
            "live_demand": demand,
            "affordability": affordability,
            "generality": generality,
            "discount_attractiveness": discount,
            "combined": combined,
        }
        candidate["four_factor_score_version"] = SCORE_VERSION
        candidate["selection_factor_scores"] = factors
        candidate["selection_demand_score"] = demand
        candidate["selection_affordability_score"] = affordability
        candidate["selection_generality_score"] = generality
        candidate["selection_discount_attractiveness_score"] = discount
        candidate["selection_four_factor_score"] = combined
        candidate["selection_use_case_group"] = use_case
        candidate["selection_affordability_basis"] = "absolute_log_price_plus_pool_percentiles"
        candidate["selection_affordability_reference"] = "current_candidate_pool_not_household_income"
        candidate["selection_generality_basis"] = "retail_taxonomy_use_case_proxy_not_population_measure"
        history_verified, market_verified, _ = _verified_discount_evidence(candidate, current)
        candidate["selection_discount_evidence"] = (
            "verified_history_and_or_market"
            if history_verified or market_verified
            else "unverified_list_price_capped"
        )
        scored.append(candidate)
    return scored


def sort_key(record: dict) -> tuple:
    """Return the equal-weight composite order; component scores break only composite ties."""
    candidate = record if isinstance(record, dict) else {}
    factors = candidate.get("selection_factor_scores")
    if not isinstance(factors, dict) or candidate.get("four_factor_score_version") != SCORE_VERSION:
        candidate = score_candidates([candidate])[0] if candidate else {}
        factors = candidate.get("selection_factor_scores", {})
    demand = _int(factors.get("live_demand"))
    affordability = _int(factors.get("affordability"))
    generality = _int(factors.get("generality"))
    discount = _int(factors.get("discount_attractiveness"))
    combined = _int(factors.get("combined"))
    return (
        combined,
        demand,
        affordability,
        generality,
        discount,
        _int(candidate.get("discount_percent")),
        _int(candidate.get("savings_toman")),
        -_int(candidate.get("current_price")),
    )
