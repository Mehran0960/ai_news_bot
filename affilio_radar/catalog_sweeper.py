#!/usr/bin/env python3
"""Incremental, read-only DigiKala catalog sweep for OfferChin.

The scanner walks every queryable category exposed by DigiKala's public search
filters, follows pagination, and keeps a bounded shortlist for the main radar.
It never publishes, changes prices, or calls affiliate endpoints.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "catalog_sweep_state.json"
CANDIDATES_PATH = ROOT / "catalog_candidates.json"
SEARCH_API = "https://api.digikala.com/v1/search/"
ROOT_CATEGORY_ID = 1
MAX_CANDIDATES = max(500, min(10000, int(os.getenv("DIGIKALA_CATALOG_MAX_CANDIDATES", "3000"))))
MAX_CATEGORY_PAGES = max(100, min(2000, int(os.getenv("DIGIKALA_CATALOG_MAX_CATEGORY_PAGES", "1000"))))
REQUEST_TIMEOUT = (8, 25)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def safe_int(value, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        text = str(value or "0").replace(",", "").replace("٬", "").strip()
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(str(value or "0").replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError, OverflowError):
        return default


def load_json(path: Path, default):
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        return value
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _payload_data(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def extract_queryable_categories(payload: dict, parent_id: int | None = None) -> list[dict]:
    """Read category IDs from DigiKala's search filter options.

    DigiKala search results expose the navigable child categories under
    data.filters.categories.options. The 'code' field is required: it is the
    site's own indication that the option maps to a category route.
    """
    data = _payload_data(payload)
    filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
    category_filter = filters.get("categories") if isinstance(filters.get("categories"), dict) else {}
    options = category_filter.get("options")
    if not isinstance(options, list):
        return []

    found = {}
    for option in options:
        if not isinstance(option, dict):
            continue
        category_id = safe_int(option.get("id"), 0)
        title = str(option.get("title_fa") or option.get("title") or "").strip()
        code = str(option.get("code") or "").strip()
        if category_id <= 0 or not title or not code:
            continue
        if parent_id is not None and category_id == parent_id:
            continue
        found[str(category_id)] = {
            "id": category_id,
            "title": title[:160],
            "code": code[:160],
        }
    return sorted(found.values(), key=lambda row: (row["title"], row["id"]))


def extract_total_pages(payload: dict) -> int | None:
    """Find explicit pagination metadata without mistaking product counts for pages."""
    preferred_keys = {
        "total_pages", "totalpages", "last_page", "lastpage",
        "pages_count", "page_count", "total_page",
    }
    data = _payload_data(payload)
    stack = [data]
    seen = set()
    while stack:
        node = stack.pop()
        if not isinstance(node, (dict, list)) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict):
            for key, value in node.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in preferred_keys:
                    pages = safe_int(value, 0)
                    if 0 < pages <= 100000:
                        return pages
                if isinstance(value, (dict, list)):
                    stack.append(value)
        else:
            stack.extend(value for value in node if isinstance(value, (dict, list)))
    return None


def _money_toman(source: dict, toman_keys: tuple[str, ...], rial_keys: tuple[str, ...]) -> int:
    for key in toman_keys:
        value = safe_int(source.get(key), 0)
        if value > 0:
            return value
    for key in rial_keys:
        value = safe_int(source.get(key), 0)
        if value > 0:
            return max(1, round(value / 10))
    return 0


def _product_price_sources(product: dict) -> list[dict]:
    sources = []
    variant = product.get("default_variant")
    if isinstance(variant, dict) and isinstance(variant.get("price"), dict):
        sources.append(variant["price"])
    if isinstance(product.get("price"), dict):
        sources.append(product["price"])
    variants = product.get("variants")
    if isinstance(variants, list):
        for variant in variants[:3]:
            if isinstance(variant, dict) and isinstance(variant.get("price"), dict):
                sources.append(variant["price"])
    sources.append(product)
    return sources


def _rating_and_reviews(product: dict) -> tuple[float, int]:
    review_count = 0
    rating = 0.0
    variant = product.get("default_variant") if isinstance(product.get("default_variant"), dict) else {}
    sources = [
        product.get("rating"),
        product.get("rating_info"),
        product.get("aggregateRating"),
        product.get("aggregate_rating"),
        variant.get("rating"),
        variant.get("rating_info"),
        product,
        variant,
    ]
    for item in sources:
        if not isinstance(item, dict):
            continue
        if not review_count:
            for key in ("review_count", "reviews_count", "reviewCount", "rating_count",
                        "ratingCount", "rate_count", "count"):
                if item.get(key) not in (None, ""):
                    review_count = max(0, safe_int(item.get(key), 0))
                    if review_count:
                        break
        if not rating:
            for key in ("rating", "rating_value", "ratingValue", "rate", "average_rating"):
                if item.get(key) not in (None, ""):
                    rating = safe_float(item.get(key), 0.0)
                    if rating > 5 and rating <= 100:
                        rating = rating / 20
                    if not 0 <= rating <= 5:
                        rating = 0.0
                    if rating:
                        break
    return rating, review_count


def product_card_to_candidate(
    product: dict,
    category_id: int,
    category_title: str,
    observed_at: str | None = None,
) -> dict | None:
    """Convert one listing card into a compact candidate record."""
    if not isinstance(product, dict):
        return None
    title = str(product.get("title_fa") or product.get("product_title") or product.get("title") or "").strip()
    raw_id = product.get("id") or product.get("product_id")
    product_url = product.get("url")
    if isinstance(product_url, dict):
        product_url = product_url.get("uri") or product_url.get("url")
    product_url = str(product_url or "").strip()
    match = re.search(r"/product/(?:dkp-)?(\d{1,12})", product_url)
    product_id = str(match.group(1)) if match else str(raw_id or "").strip()
    if not product_id.isdigit() or not title:
        return None
    if product_url:
        product_url = urljoin("https://www.digikala.com", product_url)
    else:
        product_url = f"https://www.digikala.com/product/dkp-{product_id}/"
    if "/product/dkpi-" in product_url:
        return None

    sources = _product_price_sources(product)
    current_price = 0
    original_price = 0
    direct_discount = 0
    for source in sources:
        if not current_price:
            current_price = _money_toman(
                source,
                ("selling_price_toman", "selling_price_tooman", "price_toman"),
                ("selling_price", "selling_price_rial", "price"),
            )
        if not original_price:
            original_price = _money_toman(
                source,
                ("rrp_price_toman", "original_price_toman", "list_price_toman"),
                ("rrp_price", "rrp_price_rial", "original_price", "regular_price"),
            )
        if not direct_discount:
            direct_discount = max(0, min(100, safe_int(source.get("discount_percent"), 0)))
    savings = max(0, original_price - current_price) if original_price and current_price else 0
    discount = direct_discount
    if not discount and savings and original_price > current_price:
        discount = max(1, min(100, round(100 * savings / original_price)))
    if discount <= 0:
        return None

    rating, reviews = _rating_and_reviews(product)
    review_proxy = min(30, round(3.5 * math.log1p(reviews))) if reviews else 0
    rating_proxy = max(0, min(10, round((rating - 3.0) * 5))) if rating else 0
    return {
        "product_id": f"dkp-{product_id}",
        "product_url": product_url,
        "title": title[:240],
        "current_price": current_price or None,
        "original_price": original_price or None,
        "discount_percent": discount,
        "savings_toman": savings,
        "rating": round(rating, 2) if rating else None,
        "review_count": reviews,
        "demand_score": review_proxy + rating_proxy,
        "category_id": int(category_id),
        "category_title": str(category_title or "")[:120],
        "source": "digikala_category_catalog",
        "observed_at": observed_at or iso_now(),
    }


def candidate_sort_key(row: dict) -> tuple:
    return (
        safe_int(row.get("demand_score")),
        safe_int(row.get("review_count")),
        safe_float(row.get("rating")),
        safe_int(row.get("discount_percent")),
        safe_int(row.get("savings_toman")),
    )


def merge_candidate_pool(existing: list, incoming: list, now: datetime | None = None,
                         limit: int = MAX_CANDIDATES) -> list[dict]:
    """Keep a deduplicated, bounded best-offer shortlist while scanning the full catalog."""
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current.astimezone(timezone.utc) - timedelta(days=10)
    merged = {}
    for row in list(existing or []) + list(incoming or []):
        if not isinstance(row, dict):
            continue
        pid = str(row.get("product_id") or "")
        if not re.fullmatch(r"dkp-\d{1,12}", pid):
            continue
        try:
            seen = datetime.fromisoformat(str(row.get("observed_at") or "").replace("Z", "+00:00"))
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if seen.astimezone(timezone.utc) < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        old = merged.get(pid)
        if old is None or candidate_sort_key(row) >= candidate_sort_key(old):
            merged[pid] = row
    ordered = sorted(merged.values(), key=candidate_sort_key, reverse=True)
    return ordered[:max(1, int(limit))]


def _default_state() -> dict:
    now = iso_now()
    return {
        "schema_version": 1,
        "created_at": now,
        "updated_at": now,
        "cycle_number": 1,
        "cycle_started_at": now,
        "categories": {
            str(ROOT_CATEGORY_ID): {
                "id": ROOT_CATEGORY_ID,
                "title": "دسته‌بندی ریشه",
                "code": "root",
                "next_page": 1,
                "total_pages": None,
                "pages_processed_cycle": 0,
                "products_seen_cycle": 0,
                "status": "pending",
            }
        },
        "category_order": [str(ROOT_CATEGORY_ID)],
        "pages_processed_total": 0,
        "products_seen_total": 0,
        "unique_discounted_products_total": 0,
        "last_error": None,
        "last_cycle_completed_at": None,
        "last_full_cycle_completed_at": None,
    }


def _ensure_state(state: dict) -> dict:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        state = _default_state()
    categories = state.get("categories")
    if not isinstance(categories, dict) or not categories:
        state = _default_state()
    if str(ROOT_CATEGORY_ID) not in state["categories"]:
        state["categories"][str(ROOT_CATEGORY_ID)] = _default_state()["categories"][str(ROOT_CATEGORY_ID)]
        state.setdefault("category_order", []).insert(0, str(ROOT_CATEGORY_ID))
    state.setdefault("category_order", list(state["categories"]))
    state.setdefault("pages_processed_total", 0)
    state.setdefault("products_seen_total", 0)
    state.setdefault("unique_discounted_products_total", 0)
    state.setdefault("cycle_number", 1)
    return state


def _next_pending_category(state: dict) -> dict | None:
    categories = state.get("categories", {})
    order = state.get("category_order", [])
    for raw_id in order:
        record = categories.get(str(raw_id))
        if isinstance(record, dict) and record.get("status") == "pending":
            return record
    return None


def _add_categories(state: dict, rows: list[dict]) -> int:
    added = 0
    categories = state["categories"]
    order = state["category_order"]
    for row in rows:
        cid = str(row.get("id") or "")
        if not cid.isdigit() or cid in categories:
            continue
        categories[cid] = {
            "id": int(cid),
            "title": str(row.get("title") or "")[:160],
            "code": str(row.get("code") or "")[:160],
            "next_page": 1,
            "total_pages": None,
            "pages_processed_cycle": 0,
            "products_seen_cycle": 0,
            "status": "pending",
        }
        order.append(cid)
        added += 1
    return added


def _page_products(payload: dict) -> list[dict]:
    products = _payload_data(payload).get("products")
    if isinstance(products, list):
        return [row for row in products if isinstance(row, dict)]
    if isinstance(products, dict):
        for key in ("data", "items", "results"):
            rows = products.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _fetch_category_page(session: requests.Session, category_id: int, page: int) -> requests.Response:
    return session.get(
        SEARCH_API,
        params={"categories[]": category_id, "page": page},
        timeout=REQUEST_TIMEOUT,
    )


def _finish_cycle(state: dict, candidates: list[dict], now: str) -> tuple[dict, list[dict]]:
    categories = state["categories"]
    unqueryable = sum(row.get("status") == "unqueryable" for row in categories.values())
    capped = sum(row.get("status") == "capped" for row in categories.values())
    state["last_cycle_completed_at"] = now
    state["last_cycle_summary"] = {
        "cycle_number": state.get("cycle_number", 1),
        "categories_seen": len(categories),
        "queryable_categories": sum(row.get("status") == "done" for row in categories.values()),
        "unqueryable_categories": unqueryable,
        "capped_categories": capped,
        "pages_processed": sum(safe_int(row.get("pages_processed_cycle")) for row in categories.values()),
        "products_seen": sum(safe_int(row.get("products_seen_cycle")) for row in categories.values()),
        "complete_for_all_discovered_queryable_categories": unqueryable == 0 and capped == 0,
    }
    if unqueryable == 0 and capped == 0:
        state["last_full_cycle_completed_at"] = now
    state["cycle_number"] = safe_int(state.get("cycle_number"), 1) + 1
    state["cycle_started_at"] = now
    for row in categories.values():
        if row.get("status") == "done":
            row["next_page"] = 1
            row["total_pages"] = None
            row["pages_processed_cycle"] = 0
            row["products_seen_cycle"] = 0
            row["status"] = "pending"
    state["updated_at"] = now
    return state, candidates


def run_sweep(max_pages: int = 80, max_seconds: int = 600, delay_seconds: float = 0.45) -> dict:
    state = _ensure_state(load_json(STATE_PATH, _default_state()))
    candidate_payload = load_json(CANDIDATES_PATH, {})
    existing_candidates = candidate_payload.get("products", []) if isinstance(candidate_payload, dict) else []
    if not isinstance(existing_candidates, list):
        existing_candidates = []
    candidates = merge_candidate_pool(existing_candidates, [], limit=MAX_CANDIDATES)

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Origin": "https://www.digikala.com",
        "Referer": "https://www.digikala.com/",
    })
    start = time.monotonic()
    pages_this_run = 0
    products_this_run = 0
    discounted_this_run = 0
    pauses = 0

    while pages_this_run < max(1, int(max_pages)) and time.monotonic() - start < max(30, int(max_seconds)):
        category = _next_pending_category(state)
        if category is None:
            state, candidates = _finish_cycle(state, candidates, iso_now())
            print(
                "CATALOG_CYCLE_COMPLETED "
                + json.dumps(state.get("last_cycle_summary", {}), ensure_ascii=False, sort_keys=True)
            )
            break

        category_id = safe_int(category.get("id"))
        page = max(1, safe_int(category.get("next_page"), 1))
        title = str(category.get("title") or category_id)
        try:
            response = _fetch_category_page(session, category_id, page)
            if response.status_code in {403, 429}:
                retry_after = response.headers.get("Retry-After", "")
                state["last_error"] = {
                    "category_id": category_id,
                    "page": page,
                    "status_code": response.status_code,
                    "retry_after": retry_after,
                    "at": iso_now(),
                }
                pauses = 1
                print(
                    f"CATALOG_PAUSED status={response.status_code} category={category_id} "
                    f"page={page} retry_after={retry_after or 'unknown'}"
                )
                break
            if response.status_code in {400, 404}:
                if page == 1:
                    category["status"] = "unqueryable"
                    category["unqueryable_status"] = response.status_code
                    print(f"CATALOG_CATEGORY_UNQUERYABLE id={category_id} status={response.status_code} title={title!r}")
                    continue
                category["status"] = "done"
                print(f"CATALOG_CATEGORY_END id={category_id} page={page} status={response.status_code}")
                continue
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                raise RuntimeError("category search response exceeded 8 MB")
            payload = response.json()
            data = _payload_data(payload)
            rows = _page_products(payload)
            if page == 1:
                new_categories = extract_queryable_categories(payload, parent_id=category_id)
                added = _add_categories(state, new_categories)
                if category_id == ROOT_CATEGORY_ID and not new_categories and not state.get("category_discovery_confirmed"):
                    raise RuntimeError("root_category_filter_options_missing")
                if new_categories:
                    state["category_discovery_confirmed"] = True
                if added:
                    print(f"CATALOG_SUBCATEGORIES_DISCOVERED parent={category_id} added={added}")
            total_pages = extract_total_pages(payload)
            if total_pages:
                category["total_pages"] = total_pages
            if not rows:
                category["status"] = "done"
                print(f"CATALOG_CATEGORY_END id={category_id} page={page} reason=empty_page")
                continue

            observed = iso_now()
            page_candidates = []
            for product in rows:
                products_this_run += 1
                candidate = product_card_to_candidate(product, category_id, title, observed)
                if candidate is not None:
                    page_candidates.append(candidate)
            old_ids = {row.get("product_id") for row in candidates}
            candidates = merge_candidate_pool(candidates, page_candidates, limit=MAX_CANDIDATES)
            current_ids = {row.get("product_id") for row in candidates}
            discounted_this_run += len(page_candidates)
            state["unique_discounted_products_total"] = safe_int(state.get("unique_discounted_products_total")) + len(
                {row.get("product_id") for row in page_candidates} - old_ids
            )
            category["pages_processed_cycle"] = safe_int(category.get("pages_processed_cycle")) + 1
            category["products_seen_cycle"] = safe_int(category.get("products_seen_cycle")) + len(rows)
            category["next_page"] = page + 1
            if total_pages is not None and page >= total_pages:
                category["status"] = "done"
            elif page >= MAX_CATEGORY_PAGES:
                category["status"] = "capped"
                category["cap_reason"] = "max_category_pages"
            state["pages_processed_total"] = safe_int(state.get("pages_processed_total")) + 1
            state["products_seen_total"] = safe_int(state.get("products_seen_total")) + len(rows)
            pages_this_run += 1
            print(
                f"CATALOG_PAGE_OK category={category_id} page={page} items={len(rows)} "
                f"discounted={len(page_candidates)} total_pages={total_pages or 'unknown'} "
                f"candidate_pool={len(candidates)}"
            )
            if delay_seconds > 0:
                time.sleep(max(0.0, min(3.0, float(delay_seconds))))
        except requests.RequestException as exc:
            state["last_error"] = {
                "category_id": category_id,
                "page": page,
                "error": type(exc).__name__,
                "at": iso_now(),
            }
            print(f"CATALOG_REQUEST_FAILED category={category_id} page={page} error={type(exc).__name__}")
            break
        except (ValueError, RuntimeError) as exc:
            state["last_error"] = {
                "category_id": category_id,
                "page": page,
                "error": str(exc)[:180],
                "at": iso_now(),
            }
            print(f"CATALOG_PAGE_INVALID category={category_id} page={page} reason={str(exc)[:180]}")
            break

    now = iso_now()
    state["updated_at"] = now
    state["last_run"] = {
        "at": now,
        "pages_processed": pages_this_run,
        "products_seen": products_this_run,
        "discounted_candidates_seen": discounted_this_run,
        "candidate_pool_size": len(candidates),
        "paused_for_rate_limit": bool(pauses),
    }
    state["last_error"] = state.get("last_error") if pauses or state.get("last_error") else None
    total_categories = len(state["categories"])
    done = sum(row.get("status") == "done" for row in state["categories"].values())
    pending = sum(row.get("status") == "pending" for row in state["categories"].values())
    unqueryable = sum(row.get("status") == "unqueryable" for row in state["categories"].values())
    capped = sum(row.get("status") == "capped" for row in state["categories"].values())
    expected_pages = sum(
        safe_int(row.get("total_pages"))
        for row in state["categories"].values()
        if row.get("total_pages")
    )
    completed_known_pages = sum(
        safe_int(row.get("pages_processed_cycle"))
        for row in state["categories"].values()
    )
    state["coverage_snapshot"] = {
        "cycle_number": state.get("cycle_number", 1),
        "categories_total": total_categories,
        "categories_done": done,
        "categories_pending": pending,
        "categories_unqueryable": unqueryable,
        "categories_capped": capped,
        "pages_with_known_total": expected_pages,
        "pages_processed_in_known_categories": completed_known_pages,
        "estimated_page_coverage_percent": (
            round(100 * min(100, completed_known_pages) / expected_pages, 2)
            if expected_pages > 0 else None
        ),
        "full_cycle_completed_at": state.get("last_full_cycle_completed_at"),
        "warning": "A full-cycle claim is withheld while any discovered category is unqueryable or capped.",
    }
    save_json(STATE_PATH, state)
    save_json(CANDIDATES_PATH, {
        "schema_version": 1,
        "source": "DigiKala public category search API",
        "updated_at": now,
        "candidate_count": len(candidates),
        "retention_days": 10,
        "products": candidates,
    })
    print(
        "CATALOG_SWEEP_SUMMARY "
        + json.dumps({
            "pages": pages_this_run,
            "products": products_this_run,
            "discounted_candidates": discounted_this_run,
            "candidate_pool": len(candidates),
            "categories": total_categories,
            "pending": pending,
            "done": done,
            "unqueryable": unqueryable,
            "capped": capped,
            "coverage": state["coverage_snapshot"]["estimated_page_coverage_percent"],
        }, ensure_ascii=False, sort_keys=True)
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally sweep DigiKala queryable categories.")
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("DIGIKALA_CATALOG_MAX_PAGES_PER_RUN", "80")))
    parser.add_argument("--max-seconds", type=int, default=int(os.getenv("DIGIKALA_CATALOG_MAX_SECONDS", "600")))
    parser.add_argument("--delay", type=float, default=float(os.getenv("DIGIKALA_CATALOG_REQUEST_DELAY_SECONDS", "0.45")))
    args = parser.parse_args()
    run_sweep(max_pages=args.max_pages, max_seconds=args.max_seconds, delay_seconds=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
