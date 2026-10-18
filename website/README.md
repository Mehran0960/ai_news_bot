# آفِرچین — وب‌سایت راهنمای خرید

Static, mobile-first Persian/RTL landing page for the OfferChin affiliate project.

## Hosting
Designed for Cloudflare Pages at zero hosting cost on the free plan and a `pages.dev` subdomain. No build step or third-party JavaScript libraries are required.

## Live offer feed
The homepage reads the public `affilio_radar/state.json` and `affilio_radar/candidates.json` files from the project's `main` branch. A product is displayed only when:
- its tracked expiry is still in the future;
- a delivery record says it was published;
- the candidate is in stock and has a verified affiliate URL and product image;
- current/original prices and discount percentage match the recorded published values;
- the product's last check is recent and the title is not a medicine/supplement.

If the feed cannot be fetched or no products pass all checks, the page does not invent offers and links visitors to the public Telegram and Bale channels instead.

## Project constraints
- No paid domain, paid hosting, paid API, analytics cookie, or third-party JS library required.
- Affiliate links route through the existing click-tracker Worker.
- Verify price, seller, stock and final terms on Digikala before purchase.
