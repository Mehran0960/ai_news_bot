# OfferChin storefront

A static Persian product catalog designed for Cloudflare Pages. It uses the existing public data files in affilio_radar/candidates.json and affilio_radar/state.json; it does not scrape a second feed or modify the publishing automation.

## Product eligibility

A product appears only if it was previously sent successfully to at least one OfferChin channel, the state still marks it as tracked, the latest candidate snapshot says it qualifies and is in stock, the price and HTTPS links are usable, and both the current candidate and publication record carry a reliable future deadline. If the two deadlines differ, the earlier one wins. The listing stops showing it 10 minutes before that deadline, matching the existing channel safety buffer.

The browser refreshes products.json every minute, updates countdowns locally, and disables product detail pages if the product disappears from the active feed. The build regenerates product detail pages, robots.txt, and sitemap.xml whenever candidates or publication state materially change.

## Build locally

From the repository root, run:

    python offerchin-site/build.py

The generated static site is written to offerchin-site/dist/.

## Deploy

The GitHub Actions workflow deploys to Cloudflare Pages project offerchin-storefront, creating the project if needed. Repository Actions secrets required: CLOUDFLARE_API_TOKEN (with Cloudflare Pages edit access) and CLOUDFLARE_ACCOUNT_ID. URL after a successful deployment: https://offerchin-storefront.pages.dev.

The workflow runs on relevant source/data updates and can also be started manually.