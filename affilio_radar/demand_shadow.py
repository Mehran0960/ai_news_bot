"""Evidence-only demand signals for OfferChin's shadow selection experiment.

This module never changes the live publisher ordering. DigiKala ranks stay
category-local; Torob trends are search-interest hints, not sales counts.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


DIGIKALA_BESTSELLER_MAX_RANK = 60
DIGIKALA_BESTSELLER_MAX_AGE_HOURS = 24
TOROB_TRENDS_MAX_AGE_HOURS = 12
TOROB_TRENDS_LIMIT = 30
MAX_CATEGORY_GROUPS = 30
MAX_PRODUCTS_PER_CATEGORY = 15
MAX_TREND_MATCHES = 60

_TREND_STOP_WORDS = {
    "و", "یا", "در", "با", "برای", "از", "به", "را", "این", "آن",
    "مدل", "نسخه", "اصل", "قیمت", "خرید", "فروش", "تخفیف", "کالا",
    "محصول", "جدید", "بهترین", "ارزان", "ارزانترین", "ارزانتر",
    "گوشی", "موبایل", "لوازم", "دیجیتال", "مردانه", "زنانه",
}


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _integer(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None


def _normal_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.translate(str.maketrans({
        "ي": "ی", "ى": "ی", "ك": "ک", "ؤ": "و", "إ": "ا", "أ": "ا",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    }))
    text = text.replace("\u200c", " ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _token_forms(token: str) -> set[str]:
    forms = {token}
    for suffix in ("های", "ها", "ی"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            forms.add(token[:-len(suffix)])
    return forms


def _meaningful_tokens(value: Any) -> set[str]:
    tokens = set()
    for token in _normal_text(value).split():
        if len(token) <= 1 or token in _TREND_STOP_WORDS:
            continue
        tokens.update(_token_forms(token))
    return tokens


def _rank_tier(rank: int) -> str:
    if rank <= 10:
        return "top_10"
    if rank <= 30:
        return "top_30"
    return "top_60"


def extract_digikala_bestseller_evidence(
    product: dict[str, Any],
    now: datetime | None = None,
    max_age_hours: int = DIGIKALA_BESTSELLER_MAX_AGE_HOURS,
    max_rank: int = DIGIKALA_BESTSELLER_MAX_RANK,
) -> dict[str, Any]:
    """Read fresh category-local bestseller ranks; never compare ranks across categories."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    raw_by_category = product.get("catalog_best_selling_ranks_by_category")
    observations: list[dict[str, Any]] = []
    stale_observations = 0
    if isinstance(raw_by_category, dict):
        for category_id, row in raw_by_category.items():
            if not isinstance(row, dict):
                continue
            rank = _integer(row.get("rank"))
            observed_at = _parse_datetime(row.get("observed_at"))
            if rank is None or observed_at is None or not 1 <= rank <= max_rank:
                continue
            age_hours = (current - observed_at).total_seconds() / 3600
            if age_hours < -0.1 or age_hours > max_age_hours:
                stale_observations += 1
                continue
            observations.append({
                "category_id": str(category_id),
                "category_name": str(row.get("category_name") or product.get("catalog_best_selling_category_name") or "")[:120],
                "rank": rank,
                "rank_tier": _rank_tier(rank),
                "observed_at": observed_at.isoformat(),
                "age_hours": round(max(0.0, age_hours), 2),
            })

    # Legacy/flattened fields are accepted only when category-rank history is absent.
    if not observations and not raw_by_category:
        rank = _integer(product.get("catalog_best_selling_rank"))
        observed_at = _parse_datetime(product.get("catalog_rank_observed_at"))
        if rank is not None and observed_at is not None and 1 <= rank <= max_rank:
            age_hours = (current - observed_at).total_seconds() / 3600
            if -0.1 <= age_hours <= max_age_hours:
                observations.append({
                    "category_id": str(product.get("catalog_best_selling_category_id") or ""),
                    "category_name": str(product.get("catalog_best_selling_category_name") or "")[:120],
                    "rank": rank,
                    "rank_tier": _rank_tier(rank),
                    "observed_at": observed_at.isoformat(),
                    "age_hours": round(max(0.0, age_hours), 2),
                })
            else:
                stale_observations += 1

    observations.sort(key=lambda row: (row["rank"], -row["age_hours"], row["category_id"]))
    if observations:
        best = observations[0]
        return {
            "status": "fresh",
            "source": "digikala_category_bestseller_rank",
            "rank_scope": "category_local_top_60",
            "best_rank": best["rank"],
            "rank_tier": best["rank_tier"],
            "category_id": best["category_id"],
            "category_name": best["category_name"],
            "observed_at": best["observed_at"],
            "age_hours": best["age_hours"],
            "fresh_category_ranks": observations,
        }
    return {
        "status": "stale" if stale_observations else "missing",
        "source": "digikala_category_bestseller_rank",
        "rank_scope": "category_local_top_60",
        "best_rank": None,
        "rank_tier": "",
        "category_id": "",
        "category_name": "",
        "observed_at": "",
        "age_hours": None,
        "fresh_category_ranks": [],
        "stale_observations": stale_observations,
    }


def sanitize_torob_trends(
    payload: Any,
    captured_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Keep only small, non-sensitive trend fields needed for shadow comparison."""
    if not isinstance(payload, dict) or not isinstance(payload.get("trends"), list):
        return None
    rows = []
    for item in payload["trends"][:TOROB_TRENDS_LIMIT]:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        sample = item.get("sample") if isinstance(item.get("sample"), dict) else {}
        rows.append({
            "query": query[:160],
            "category_id": str(item.get("category_id") or "")[:80],
            "sample_name": str(sample.get("name_fa") or sample.get("title") or "")[:180],
        })
    if not rows:
        return None
    stamp = captured_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return {
        "source": "torob_mcp.torob_trends",
        "captured_at": stamp.astimezone(timezone.utc).isoformat(),
        "count": len(rows),
        "note": str(payload.get("note") or "")[:240],
        "trends": rows,
    }


def torob_trends_snapshot_status(
    snapshot: Any,
    now: datetime | None = None,
    max_age_hours: int = TOROB_TRENDS_MAX_AGE_HOURS,
) -> tuple[str, float | None]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("trends"), list):
        return "missing", None
    captured_at = _parse_datetime(snapshot.get("captured_at"))
    if captured_at is None:
        return "invalid", None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_hours = (current.astimezone(timezone.utc) - captured_at).total_seconds() / 3600
    if age_hours < -0.1:
        return "future_timestamp", age_hours
    if age_hours > max_age_hours:
        return "stale", age_hours
    return "fresh", max(0.0, age_hours)


def match_torob_trends_to_product(
    product: dict[str, Any],
    snapshot: Any,
    now: datetime | None = None,
    max_age_hours: int = TOROB_TRENDS_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Match only meaningful query terms; a one-token match remains explicitly weak."""
    status, age_hours = torob_trends_snapshot_status(snapshot, now, max_age_hours)
    if status != "fresh":
        return {
            "status": status,
            "source": "torob_mcp.torob_trends",
            "snapshot_age_hours": round(age_hours, 2) if age_hours is not None else None,
            "strong_matches": [],
            "weak_matches": [],
        }

    title = _normal_text(product.get("title") or "")
    title_tokens = _meaningful_tokens(title)
    matches: list[dict[str, Any]] = []
    for trend in snapshot.get("trends", []):
        if not isinstance(trend, dict):
            continue
        query = str(trend.get("query") or "").strip()
        query_tokens = _meaningful_tokens(query)
        if not query_tokens or not query_tokens.issubset(title_tokens):
            continue
        strength = "strong" if len(query_tokens) >= 2 else "weak"
        matches.append({
            "query": query[:160],
            "category_id": str(trend.get("category_id") or "")[:80],
            "sample_name": str(trend.get("sample_name") or "")[:180],
            "match_strength": strength,
            "matched_terms": sorted(query_tokens),
        })
    matches.sort(key=lambda row: (row["match_strength"] != "strong", row["query"]))
    return {
        "status": "matched" if matches else "no_match",
        "source": "torob_mcp.torob_trends",
        "snapshot_age_hours": round(age_hours or 0.0, 2),
        "strong_matches": [row for row in matches if row["match_strength"] == "strong"][:5],
        "weak_matches": [row for row in matches if row["match_strength"] == "weak"][:5],
    }


def build_demand_shadow_report(
    products: list[dict[str, Any]],
    torob_snapshot: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build category-local evidence tables without a global popularity score or live reordering."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    torob_status, torob_age = torob_trends_snapshot_status(torob_snapshot, current)

    category_buckets: dict[str, dict[str, Any]] = {}
    product_signals = []
    ranked_count = 0
    strong_count = 0
    weak_count = 0
    for product in products or []:
        if not isinstance(product, dict):
            continue
        product_id = str(product.get("product_id") or product.get("product_url") or "")[:160]
        title = str(product.get("title") or "")[:180]
        digikala = extract_digikala_bestseller_evidence(product, current)
        torob = match_torob_trends_to_product(product, torob_snapshot, current)
        ranked_count += digikala["status"] == "fresh"
        strong_count += bool(torob["strong_matches"])
        weak_count += bool(torob["weak_matches"]) and not bool(torob["strong_matches"])
        signal_row = {
            "product_id": product_id,
            "title": title,
            "discount_percent": max(0, _integer(product.get("discount_percent")) or 0),
            "savings_toman": max(0, _integer(product.get("savings_toman")) or 0),
            "digikala_bestseller": digikala,
            "torob_trends": torob,
        }
        product_signals.append(signal_row)

        for observation in digikala.get("fresh_category_ranks", []):
            category_id = observation["category_id"]
            bucket = category_buckets.setdefault(category_id, {
                "category_id": category_id,
                "category_name": observation["category_name"],
                "products": {},
            })
            row = {
                "product_id": product_id,
                "title": title,
                "rank": observation["rank"],
                "rank_tier": observation["rank_tier"],
                "observed_at": observation["observed_at"],
                "age_hours": observation["age_hours"],
                "discount_percent": signal_row["discount_percent"],
                "savings_toman": signal_row["savings_toman"],
                "torob_strong_trend_matches": torob["strong_matches"],
                "torob_weak_trend_matches": torob["weak_matches"],
            }
            previous = bucket["products"].get(product_id)
            if previous is None or row["rank"] < previous["rank"]:
                bucket["products"][product_id] = row

    category_rows = []
    for bucket in category_buckets.values():
        rows = sorted(
            bucket["products"].values(),
            key=lambda row: (row["rank"], -row["discount_percent"], -row["savings_toman"], row["product_id"]),
        )
        category_rows.append({
            "category_id": bucket["category_id"],
            "category_name": bucket["category_name"],
            "candidate_count": len(rows),
            "products": rows[:MAX_PRODUCTS_PER_CATEGORY],
        })
    category_rows.sort(key=lambda row: (-row["candidate_count"], row["category_name"], row["category_id"]))

    trend_rows = [
        row for row in product_signals
        if row["torob_trends"]["strong_matches"] or row["torob_trends"]["weak_matches"]
    ]
    trend_rows.sort(key=lambda row: (
        not bool(row["torob_trends"]["strong_matches"]),
        row["title"],
        row["product_id"],
    ))

    return {
        "schema_version": 1,
        "generated_at": current.isoformat(),
        "mode": "shadow_only",
        "live_ranking_changed": False,
        "global_cross_category_bestseller_rank": "not_computed",
        "principle": "DigiKala bestseller ranks are compared only inside their own category; Torob trends are query-interest hints, not unit sales.",
        "summary": {
            "products_examined": len(product_signals),
            "products_with_fresh_digikala_rank": ranked_count,
            "digikala_rank_coverage_percent": round(100 * ranked_count / len(product_signals), 1) if product_signals else 0.0,
            "torob_snapshot_status": torob_status,
            "torob_snapshot_age_hours": round(torob_age, 2) if torob_age is not None else None,
            "torob_trend_count": len(torob_snapshot.get("trends", [])) if torob_status == "fresh" and isinstance(torob_snapshot, dict) else 0,
            "products_with_strong_torob_trend_match": strong_count,
            "products_with_weak_torob_trend_match": weak_count,
            "category_groups": len(category_rows),
        },
        "category_rankings": category_rows[:MAX_CATEGORY_GROUPS],
        "torob_trend_matches": trend_rows[:MAX_TREND_MATCHES],
        "product_signals": product_signals[:MAX_TREND_MATCHES],
    }
