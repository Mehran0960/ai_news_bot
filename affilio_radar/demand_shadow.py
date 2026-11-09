"""DigiKala-only, category-local bestseller evidence for OfferChin.

This module is diagnostic (shadow-only): it never scores products globally,
reorders candidates, or changes production publication eligibility.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

DIGIKALA_BESTSELLER_MAX_AGE_HOURS = 24
DIGIKALA_BESTSELLER_MAX_RANK = 60
MAX_CATEGORY_EXAMPLES = 12


def _as_utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fresh_digikala_bestseller_evidence(
    product: dict,
    now: datetime,
) -> dict | None:
    product_id = str(product.get("product_id") or "").strip().lower()
    if not re.fullmatch(r"dkp-\d{1,12}", product_id):
        return None
    if product.get("catalog_sort_mode") != "best_selling":
        return None

    raw_rank = product.get("catalog_best_selling_rank")
    if isinstance(raw_rank, bool):
        return None
    if isinstance(raw_rank, float) and not raw_rank.is_integer():
        return None
    try:
        rank = int(raw_rank)
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

    category_id = str(product.get("catalog_best_selling_category_id") or "").strip()
    if not category_id.isdigit():
        return None
    category_name = str(product.get("catalog_best_selling_category_name") or "").strip()

    return {
        "rank": rank,
        "category_id": category_id,
        "category_name": category_name[:120],
        "observed_at": observed.isoformat(),
        "scope": "category_local",
    }


def annotate_shadow_demand_evidence(
    products: list[dict],
    now: datetime | None = None,
) -> dict:
    """Attach fresh DigiKala ranks and report them strictly within category groups.

    The input list is never sorted or mutated except for each product's evidence
    field. A rank in one category is not compared with a rank in another.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    records = [row for row in (products or []) if isinstance(row, dict)]
    category_groups: dict[str, dict] = {}
    fresh_count = 0

    for product in records:
        evidence = _fresh_digikala_bestseller_evidence(product, current)
        product["shadow_demand_evidence"] = {
            "evidence_level": (
                "fresh_digikala_bestseller"
                if evidence else "no_fresh_digikala_bestseller_rank"
            ),
            "digikala_bestseller": evidence,
            "production_ranking_affected": False,
        }
        if not evidence:
            continue

        fresh_count += 1
        category_id = evidence["category_id"]
        group = category_groups.setdefault(category_id, {
            "category_id": category_id,
            "category_name": evidence["category_name"],
            "candidate_count": 0,
            "products": [],
        })
        group["candidate_count"] += 1
        group["products"].append({
            "product_id": str(product.get("product_id") or "")[:80],
            "title": str(product.get("title") or "")[:220],
            "rank": evidence["rank"],
            "observed_at": evidence["observed_at"],
            "discount_percent": int(product.get("discount_percent") or 0),
            "current_price": int(product.get("current_price") or 0),
        })

    # Category IDs only provide deterministic grouping; they are not a ranking.
    categories = []
    for category_id in sorted(category_groups):
        group = category_groups[category_id]
        group["products"].sort(key=lambda item: (item["rank"], item["product_id"]))
        group["products"] = group["products"][:MAX_CATEGORY_EXAMPLES]
        categories.append(group)

    return {
        "mode": "shadow_only",
        "source": "existing_digikala_full_catalog_scanner",
        "source_scope": "DigiKala bestseller ranks only",
        "production_ranking_affected": False,
        "ranking_method": "category_local_bestseller_rank_no_global_score",
        "freshness_policy": {
            "maximum_rank_per_category": DIGIKALA_BESTSELLER_MAX_RANK,
            "maximum_age_hours": DIGIKALA_BESTSELLER_MAX_AGE_HOURS,
        },
        "cross_category_comparability": (
            "not comparable: raw bestseller ranks are valid only inside the same DigiKala category"
        ),
        "excluded_sources": ["Torob trends", "SnappShop", "Google Trends", "review-growth proxy"],
        "generated_at": current.isoformat(),
        "candidate_count": len(records),
        "fresh_digikala_rank_count": fresh_count,
        "no_fresh_digikala_rank_count": len(records) - fresh_count,
        "category_count": len(categories),
        "categories": categories,
    }
