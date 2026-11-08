"""Explainable, non-production demand evidence for OfferChin.

This module deliberately emits evidence tiers instead of a weighted popularity
score: DigiKala bestseller ranks are category-local, while Torob trend ranks are
global within Torob's current trend list. They are not directly comparable.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

MAX_TOROB_TRENDS = 30
TOROB_TRENDS_MAX_AGE_MINUTES = 90
DIGIKALA_BESTSELLER_MAX_AGE_HOURS = 24
DIGIKALA_BESTSELLER_MAX_RANK = 60
REVIEW_GROWTH_MAX_AGE_HOURS = 12

_PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
_STOPWORDS = {
    "و", "در", "از", "با", "برای", "به", "را", "این", "آن", "یک",
    "های", "ها", "می", "روی", "یا", "the", "a", "an", "and", "for",
    "with", "of", "in", "on", "to", "buy", "best", "new", "model",
    "مدل", "خرید", "قیمت", "فروش", "ارزان", "بهترین", "تخفیف",
    "موجود", "جدید", "اصل", "کالا", "محصول", "مناسب",
}

_EVIDENCE_ORDER = {
    "cross_source": 0,
    "torob_trend_only": 1,
    "digikala_bestseller_only": 2,
    "review_growth_proxy_only": 3,
    "no_verified_demand_signal": 4,
}


def _as_utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: Any) -> str:
    parsed = _as_utc(value)
    if parsed is None:
        raise ValueError("invalid_observed_at")
    return parsed.isoformat()


def normalize_search_tokens(value: Any) -> set[str]:
    """Normalize Persian/Arabic spelling and remove generic shopping words."""
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_PERSIAN_DIGITS)
    text = (
        text.replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("\u0640", "")
    )
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", " ", text)
    text = "".join(
        char for char in text
        if unicodedata.category(char) not in {"Mn", "Me"}
    ).lower()
    tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    return {
        token for token in tokens
        if len(token) > 1 and token not in _STOPWORDS
    }


def build_torob_trends_snapshot(
    payload: Any,
    observed_at: str | datetime,
) -> dict:
    """Validate and compact Torob MCP's read-only torob_trends response."""
    if isinstance(payload, dict):
        rows = payload.get("trends")
        if rows is None and isinstance(payload.get("data"), dict):
            rows = payload["data"].get("trends")
    else:
        rows = None
    if not isinstance(rows, list):
        raise ValueError("torob_trends_payload_missing_list")

    if isinstance(observed_at, datetime):
        stamp = observed_at.astimezone(timezone.utc).isoformat() if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc).isoformat()
    else:
        stamp = _iso_utc(observed_at)

    trends: list[dict] = []
    seen_queries: set[str] = set()
    for source_rank, row in enumerate(rows[:MAX_TOROB_TRENDS], start=1):
        if not isinstance(row, dict):
            continue
        query = re.sub(r"\s+", " ", str(row.get("query") or "")).strip()[:160]
        key = " ".join(sorted(normalize_search_tokens(query)))
        if not query or not key or key in seen_queries:
            continue
        seen_queries.add(key)

        sample = row.get("sample") if isinstance(row.get("sample"), dict) else {}
        sample_title = re.sub(
            r"\s+",
            " ",
            str(
                sample.get("name_fa")
                or sample.get("title_fa")
                or sample.get("title")
                or sample.get("name")
                or ""
            ),
        ).strip()[:220]
        trends.append({
            "rank": source_rank,
            "query": query,
            "category_id": str(row.get("category_id") or "")[:80],
            "sample_title": sample_title,
            "sample_url": str(sample.get("url") or "")[:500],
        })

    return {
        "source": "torob_public_mcp.torob_trends",
        "observed_at": stamp,
        "count": len(trends),
        "trends": trends,
    }


def torob_trends_snapshot_is_fresh(
    snapshot: Any,
    now: datetime | None = None,
    max_age_minutes: int = TOROB_TRENDS_MAX_AGE_MINUTES,
) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("trends"), list):
        return False
    observed = _as_utc(snapshot.get("observed_at"))
    if observed is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_minutes = (current.astimezone(timezone.utc) - observed).total_seconds() / 60
    return 0 <= age_minutes <= max(0, int(max_age_minutes))


def _fresh_digikala_bestseller_evidence(
    product: dict,
    now: datetime,
) -> dict | None:
    if not str(product.get("product_id") or "").startswith("dkp-"):
        return None
    if product.get("catalog_sort_mode") != "best_selling":
        return None
    try:
        rank = int(product.get("catalog_best_selling_rank") or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    if not 1 <= rank <= DIGIKALA_BESTSELLER_MAX_RANK:
        return None
    observed = _as_utc(product.get("catalog_rank_observed_at"))
    if observed is None:
        return None
    age_hours = (now - observed).total_seconds() / 3600
    if not 0 <= age_hours <= DIGIKALA_BESTSELLER_MAX_AGE_HOURS:
        return None
    category_id = str(product.get("catalog_best_selling_category_id") or "")
    category_name = str(product.get("catalog_best_selling_category_name") or "")
    if not category_id.isdigit():
        return None
    return {
        "rank": rank,
        "category_id": category_id,
        "category_name": category_name[:120],
        "observed_at": observed.isoformat(),
        "scope": "category_local",
    }


def _trend_match(product_title: Any, trends: list[dict]) -> dict | None:
    product_tokens = normalize_search_tokens(product_title)
    if len(product_tokens) < 2:
        return None

    matches: list[tuple[int, float, dict]] = []
    for trend in trends:
        if not isinstance(trend, dict):
            continue
        query_tokens = normalize_search_tokens(trend.get("query"))
        sample_tokens = normalize_search_tokens(trend.get("sample_title"))
        options: list[tuple[float, str, int]] = []

        # Short queries require every informative token to match. One shared
        # generic word is never enough to attach a trend to a product.
        if len(query_tokens) >= 2:
            overlap = len(query_tokens & product_tokens)
            coverage = overlap / len(query_tokens)
            if overlap >= 2 and coverage >= 0.75:
                options.append((coverage, "query_tokens", overlap))

        # Sample-product matching permits title variants, but requires at least
        # three informative shared tokens and a meaningful fraction of the sample.
        if len(sample_tokens) >= 3:
            overlap = len(sample_tokens & product_tokens)
            coverage = overlap / len(sample_tokens)
            union = len(sample_tokens | product_tokens)
            jaccard = overlap / union if union else 0.0
            if overlap >= 3 and coverage >= 0.65 and jaccard >= 0.30:
                options.append((coverage, "sample_product_tokens", overlap))

        if not options:
            continue
        coverage, method, overlap = max(options, key=lambda item: (item[0], item[2]))
        try:
            rank = int(trend.get("rank") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if rank < 1:
            continue
        matches.append((rank, -coverage, {
            "rank": rank,
            "query": str(trend.get("query") or "")[:160],
            "category_id": str(trend.get("category_id") or "")[:80],
            "sample_title": str(trend.get("sample_title") or "")[:220],
            "match_method": method,
            "matched_token_count": overlap,
            "token_coverage": round(coverage, 3),
        }))

    if not matches:
        return None
    return min(matches, key=lambda item: (item[0], item[1]))[2]


def _fresh_review_growth_proxy(product: dict, now: datetime) -> dict | None:
    if product.get("current_demand_verified") is not True:
        return None
    observed = _as_utc(product.get("demand_observed_at"))
    if observed is None:
        return None
    age_hours = (now - observed).total_seconds() / 3600
    if not 0 <= age_hours <= REVIEW_GROWTH_MAX_AGE_HOURS:
        return None
    try:
        growth = int(product.get("recent_review_growth_window") or 0)
        window_hours = float(product.get("demand_window_hours") or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    if growth <= 0 or window_hours <= 0:
        return None
    return {
        "growth": growth,
        "window_hours": round(window_hours, 1),
        "source": str(product.get("demand_signal_source") or "")[:80],
        "observed_at": observed.isoformat(),
        "meaning": "indirect_proxy_not_unit_sales",
    }


def annotate_shadow_demand_evidence(
    products: list[dict],
    torob_snapshot: dict | None,
    now: datetime | None = None,
) -> dict:
    """Attach separate, freshness-checked source evidence without reordering products."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    snapshot = torob_snapshot if torob_trends_snapshot_is_fresh(torob_snapshot, current) else {}
    trends = snapshot.get("trends", []) if isinstance(snapshot, dict) else []
    if not isinstance(trends, list):
        trends = []

    for product in products:
        if not isinstance(product, dict):
            continue
        digikala = _fresh_digikala_bestseller_evidence(product, current)
        torob = _trend_match(product.get("title"), trends)
        review_growth = _fresh_review_growth_proxy(product, current)
        if digikala and torob:
            level = "cross_source"
        elif torob:
            level = "torob_trend_only"
        elif digikala:
            level = "digikala_bestseller_only"
        elif review_growth:
            level = "review_growth_proxy_only"
        else:
            level = "no_verified_demand_signal"
        product["shadow_demand_evidence"] = {
            "evidence_level": level,
            "digikala_bestseller": digikala,
            "torob_trend": (
                {**torob, "observed_at": snapshot.get("observed_at")}
                if torob else None
            ),
            "review_growth_proxy": review_growth,
            "production_ranking_affected": False,
        }
    return build_shadow_demand_report(products, snapshot, current)


def build_shadow_demand_report(
    products: list[dict],
    torob_snapshot: dict | None,
    generated_at: datetime | None = None,
) -> dict:
    current = generated_at or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    records = [row for row in products if isinstance(row, dict)]
    counts = {key: 0 for key in _EVIDENCE_ORDER}
    examples = []
    for row in records:
        evidence = row.get("shadow_demand_evidence")
        level = evidence.get("evidence_level") if isinstance(evidence, dict) else None
        if level not in counts:
            level = "no_verified_demand_signal"
        counts[level] += 1
        digikala = evidence.get("digikala_bestseller") if isinstance(evidence, dict) else None
        torob = evidence.get("torob_trend") if isinstance(evidence, dict) else None
        examples.append({
            "product_id": str(row.get("product_id") or "")[:80],
            "title": str(row.get("title") or "")[:220],
            "discount_percent": int(row.get("discount_percent") or 0),
            "current_price": int(row.get("current_price") or 0),
            "evidence_level": level,
            "digikala_category": digikala.get("category_name") if isinstance(digikala, dict) else None,
            "digikala_bestseller_rank": digikala.get("rank") if isinstance(digikala, dict) else None,
            "torob_trend_rank": torob.get("rank") if isinstance(torob, dict) else None,
            "torob_trend_query": torob.get("query") if isinstance(torob, dict) else None,
            "torob_match_method": torob.get("match_method") if isinstance(torob, dict) else None,
        })

    def sort_key(item: dict) -> tuple:
        level = item["evidence_level"]
        torob_rank = item["torob_trend_rank"]
        if torob_rank is None:
            torob_rank = 10_000
        # DigiKala ranks are only ordered inside their own category. Category id
        # is used to keep those groups together, never as a market-size proxy.
        category = ""
        if level == "digikala_bestseller_only":
            category = str(item.get("digikala_category") or "")
        rank = item["digikala_bestseller_rank"]
        if rank is None:
            rank = 10_000
        return (_EVIDENCE_ORDER.get(level, 99), torob_rank, category, rank, item["product_id"])

    examples.sort(key=sort_key)
    trends = torob_snapshot.get("trends", []) if isinstance(torob_snapshot, dict) else []
    observed_at = torob_snapshot.get("observed_at") if isinstance(torob_snapshot, dict) else None
    return {
        "mode": "shadow_only",
        "production_ranking_affected": False,
        "ranking_method": "transparent_evidence_tiers_no_weighted_score",
        "evidence_tier_order": list(_EVIDENCE_ORDER),
        "cross_category_comparability": {
            "torob_trend_rank": "global order only within Torob's current trend list",
            "digikala_bestseller_rank": "category-local only; never compare raw ranks across categories",
            "review_growth": "indirect proxy only; not units sold",
        },
        "generated_at": current.isoformat(),
        "torob": {
            "source": "torob_public_mcp.torob_trends",
            "status": (
                "fresh"
                if torob_trends_snapshot_is_fresh(torob_snapshot, current)
                else "unavailable_or_stale"
            ),
            "observed_at": observed_at,
            "trend_count": len(trends) if isinstance(trends, list) else 0,
        },
        "candidate_count": len(records),
        "evidence_counts": counts,
        "products": examples[:40],
    }
