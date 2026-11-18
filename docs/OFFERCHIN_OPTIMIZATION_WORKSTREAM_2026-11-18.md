# OfferChin optimization workstream — 2026-11-18

## Scope and safety
This work is staged on `codex/offerchin-optimization-2026-11-18-refresh3`, created from main commit `3b5272f71b9be6ed57d0bd8cad28a4310551c155`. The preceding PR #245 was 433 commits behind main and is not a safe merge base. This branch starts from a fresh main snapshot; only narrowly scoped, reviewed changes are reapplied. No changes are made to main, production secrets, Cloudflare deployment, or live publishing credentials. Merge and deployment remain separate approval steps.

## Technical changes staged
1. Move DigiKala live price/availability audit off retired v1/v2 routes to the current product-detail endpoint using `_digikala_get`; preserve exact product ID validation, one bounded HTML fallback, and no deletion on inconclusive evidence.
2. Stop calling the retired `/v1/incredible-offers/products/` feed for campaign deadlines. Use exact product-matched MCP deal cards; live product details remain a separate rotating price/stock audit.
3. Clarify that direct Aflo purchase buttons bypass the Cloudflare Worker. Worker events and A/B assignment are not live CTA click attribution. Official Affilio SubID or order/export data is still required for sales attribution.
4. Recognize all seven media sources in the Worker click-event schema; this does not change the current direct Aflo purchase CTA.
5. Add explicit `digikala_store_only` scope to the current store-native demand evidence. No independent market-wide demand provider is yet integrated; Torob is price comparison only and MeMarket is a separate affiliate offer feed.
6. Set Telegram/Bale product-photo retention to seven days; Telegram messages older than 48 hours require MTProto credentials. Editorial evergreen content and videos remain excluded.
7. Add trust-first affiliate playbook and Iran network due-diligence documentation. Deema/Dayan are candidates only; no new network is activated.

## Transferable models researched
- HotUKDeals: community deal verification, real votes/comments, transparent affiliate disclosure and editorial/commission independence.
- Wirecutter: independent product selection and commerce separation.
- Impact.com 2025 benchmark: traffic growth can coexist with transaction/conversion declines; it is a North American benchmark, not an Iran forecast.
- These patterns are translated into a trust-first publishing gate, independent editorial selection, full-funnel measurement, and no fake community engagement.

## Operational independence / constraints
- Photo destinations use separate per-destination delivery results; video destinations run through their own platform-specific workflows. This branch does not add a global cross-media lock.
- YouTube quota cannot be bypassed; Eitaa requires credentials; Filo submission is not proof of public publication; Aparat must be judged by actual verified receipt.
- No public posts are deleted by this branch. Seven-day retention only becomes active after merge/deploy; confirm Telegram MTProto secrets before relying on days 3–7 cleanup.

## Verification
- The predecessor PR #246 code snapshot `3742a1e4d43aaf6cfc704f6dc3f63f6e62d5ec83` passed 601 Python tests (2 skipped), 4 Node worker tests and 10 PR checks; its latest documentation-only head had 9/9 PR workflows successful.
- These are historical predecessor-branch results. The fresh `refresh3` branch must pass its own CI before merge consideration.
- Live marketplace-wide demand and completed purchase attribution remain unverified and are not simulated.
- No merge, deploy, live publish, secret change, or external network activation has been performed.

## Verification update — per-platform exception isolation

Photo delivery for Telegram, Bale, Rubika and Eitaa is now routed through `_deliver_photo_destinations_independently`. Each adapter receives a private copy; its future result is merged independently. A failure on one adapter is recorded for that destination and does not cancel sibling futures. A new test simulates Eitaa failure while requiring Telegram/Bale/Rubika to succeed. The regression workflow now includes this Python suite and Node worker attribution tests.

Limit: the four photo adapters still share one Actions runner; a runner crash/timeout can affect all four. Video platform workflows are separate. The successful tests and CI listed above belong to the predecessor branch snapshot; this refreshed branch must pass its own CI before merge.
