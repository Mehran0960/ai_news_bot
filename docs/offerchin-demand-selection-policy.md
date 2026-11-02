# OfferChin demand-first, verified-value selection

## Goal

The publication policy is ordered: (1) current market demand, (2) genuine purchase value, then (3) the largest displayed discount among offers that pass both proof gates. A large retailer markdown is not, by itself, evidence that an offer is good.

## DigiKala catalogue discovery

- The resumable parallel crawler discovers the current category tree and deduplicates product cards by DigiKala product ID.
- Best-selling pagination has no application-level three-page cap. It follows the API's reported page count; when page totals are absent, it continues until the endpoint returns an empty terminal page or a 404 boundary.
- The first three pages (up to 60 items) of the most-viewed order are also scanned for a second demand signal.
- Each category/sort-mode page is queued independently. Transient failures are retried; inaccessible category/sort tasks are retained in the cycle coverage record.
- Per-category ranks are normalized to a 0–100 percentile using the API's exact total product count when exposed; otherwise the crawler estimates the category size from reported pages × page size. This makes ranks from differently sized categories comparable, while the estimate is explicitly less precise when DigiKala omits totals.
- The one-time migration from the former top-60 bestseller scanner explicitly seeds page 4 for every known category and adds the most-viewed pages.

## Coverage is reported honestly

The crawler stores `parallel_coverage_status` and `last_cycle_coverage`:

- `in_progress`: pages remain in the durable queue.
- `complete`: all known category/sort tasks were traversed using explicit pagination boundaries and no category was inaccessible.
- `complete_with_inferred_boundaries`: all queued work ended, but at least one boundary was inferred from an empty page or a 404 because the API did not provide a reliable total-page count.
- An empty page before the API-reported final page is treated as an unqueryable/inconsistent category task, not as proof of complete coverage.
- `partial_unqueryable_categories`: at least one category/sort task could not be queried.

This is the most complete inventory obtainable from the public endpoint at the time of each crawl, not a guarantee that DigiKala exposed every active product. The endpoint does not provide a frozen catalogue snapshot, and categories can change while pagination is running. A new category, a rate limit, an access restriction, or a moving result set can make a cycle partial or temporarily stale. The system must not call a cycle fully complete when its coverage record says otherwise.

## Demand proof and ranking

A candidate needs at least one fresh signal:

1. Recent review growth in the active observation window.
2. A fresh bestseller rank in the top 30% of its category, calculated from the category percentile.
3. A fresh most-viewed rank in the top 10% where percentile data is available; legacy top-60 view records are also accepted.

The demand sort combines normalized bestseller percentile (65%), recent activity score (25%), and normalized view percentile (10%). Best-seller position is weighted most heavily because it is the closest public proxy for purchase intent. Lifetime review count and rating can help break ties, but cannot independently qualify a candidate for publication.

These are public demand proxies, not unit-sales data. DigiKala's public search response does not expose a reliable, cross-category count of units sold in the crawler's current data contract. The ranking therefore cannot honestly claim to know the exact most-purchased item in Iran.

## Genuine discount proof

A live positive markdown is still required, but there is no fixed 50% (or similar) display-discount floor. The offer must also pass one independent value proof:

- Fresh same-product price history shows an eligible reduction versus its recent reference price; or
- A fresh comparable-market check finds a seller-median advantage of at least 5%.

The 5% figure is a comparison-evidence threshold, not a requirement that DigiKala's displayed discount be 5%. A displayed markdown with no independent price evidence is rejected for publication. Stock, current price, affiliate URL, product title, and offer runway remain hard checks.

## Processing capacity and operational limits

The application code now supports up to 200 product-detail checks, 200 catalog handoff candidates, five history checks, and four market comparisons per run. The current publisher workflow still explicitly configures 100 product checks, 100 catalog handoff candidates, and two history plus two market checks per run. Those workflow-level overrides therefore remain the live throughput until the workflow configuration itself is changed.

The catalog candidate sidecar retains up to 3,000 candidates and rotates underrepresented categories into the handoff. Each candidate's price/value checks are cached and rechecked on a schedule; market-provider challenges trigger cooldown rather than fabricated verification.

## Scope note: SnappShop

DigiKala is the catalogue-wide primary source. SnappShop remains an optional secondary discovery source in the publisher, not a verified exhaustive catalogue crawler. No claim of full SnappShop catalogue coverage is made.
