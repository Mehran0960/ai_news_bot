# OfferChin optimization workstream — 2026-11-18

## Scope and safety
This work is staged on `codex/offerchin-optimization-2026-11-18` from the observed `main` commit `d349aebea2199f0039536af780e33f1f964c9c0a`. No changes are made to `main`, production secrets, Cloudflare configuration, or live publishing credentials. Merge and deployment remain separate approval steps.

## Confirmed findings at start
- Catalog discovery was healthy in the last inspected snapshot: 533/533 categories, 12,336 pages and 242,129 product rows in a completed cycle. This is catalog coverage, not proof of market-wide demand.
- The expiry/integrity monitor still attempted the retired DigiKala endpoints `/v2/product/{id}/`, `/v1/product/{id}/`, and `/v1/incredible-offers/products/`. The recent audit consequently reported all 8 checked products as unconfirmed (403/404), despite the workflow itself completing.
- The current product detail endpoint already used by discovery is `/product/v1/products/{id}/`, with a redirect/CDN-cookie-aware request helper and exact product-ID parsing.
- Latest operational evidence showed destination-specific constraints: YouTube daily upload quota, Filo submissions awaiting approval rather than public confirmation, Aparat runs with zero processed items in some windows, and Eitaa not connected.
- The 30-day performance report had 1,138 product publications and 106 tracked clicks, but no confirmed orders, sales or commission feed. Clicks must not be presented as sales.

## Changes in this branch
1. Updated `expiration_monitor.fetch_live_product_status` to use the same current DigiKala product-detail endpoint and safe redirect/CDN helper as discovery. The check remains bounded, validates the requested product through `parse_product_api`, and preserves the conservative rule that missing/ambiguous data cannot trigger deletion.
2. Removed calls to the retired legacy DigiKala live-deals feed. The deadline map is explicitly MCP-only and filters cards to required exact product IDs; product-detail API checks are handled separately by the rotating live-status/expiry confirmation monitor.
3. Updated regression tests for the current product-detail endpoint and for the single bounded HTML fallback after API failure.

## Explicit non-goals / external dependencies
- No attempt to bypass YouTube quota or platform anti-abuse controls.
- Eitaa requires valid, user-authorized bot/channel credentials.
- Filo's pending-approval receipt is not a public-publication receipt; confirmation must come from public availability or a platform status lookup.
- Affiliate sales attribution requires an official Affilio read-only report/API or export with orders, revenue, commission and preferably sub-ID/channel attribution.
- Additional independent market-demand providers require stable, lawful data access and must not be simulated from DigiKala-only signals.

## Verification required before merge
- Run expiry monitor unit tests and the full relevant CI suite.
- Confirm the new DigiKala endpoint with live, read-only probes and report verified / unavailable / inconclusive counts separately.
- Verify destination independence, retry behavior, idempotency and public receipts using platform-specific evidence.
- Confirm affiliate tracking and order attribution using Affilio's official report/export.
- Do not merge or deploy until the PR checks and review are satisfactory.
