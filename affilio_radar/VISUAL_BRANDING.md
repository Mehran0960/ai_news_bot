# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and vertical videos.

## Product images

- **Upper-right:** Place the discount tile in a target rectangle with exactly the same width and height as the upper-left retailer-logo target rectangle. Use the solid retailer-specific color and a large percentage; for the wide shared frame, place the percentage on the right and the Persian word “تخفیف” on the left.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset in the same target width and height as the discount tile. Preserve the supplied artwork, wordmark, original colors, and aspect ratio; fit proportionally inside the shared bounds.
- **Below retailer logo:** Place the official DigiPay mark on its blue field, preserving the mark itself. The blue field may extend to match the retailer tile's target dimensions; do not stretch the logo artwork.
- **Lower-left:** Place the other three public OfferChin destinations as a compact, vertically stacked list. Every row uses its official local logo first, then the channel identity and short address. Telegram, Bale, and Rubika use “OfferChin • {channel URL}”; the YouTube row uses its official horizontal wordmark and youtube.com/@offerchin.
- **YouTube logo:** Use the official horizontal full-color wordmark on its light solid backing. Preserve its original landscape aspect ratio. Never force it into a square icon box or stretch/crop its artwork. Its height should match the other small channel marks; its width is derived from the source ratio.
- Scale the footer with source resolution instead of keeping every export at a tiny fixed pixel size: logo height is clamped to 16–44 source pixels, width to 46–128 pixels, and channel text to 13–32 pixels. Row spacing is resolution-aware. The source logo's own ratio determines its final footprint; a wider wordmark may occupy more width but is never compressed to a square.
- Choose each text foreground color from the luminance behind its actual text area. Keep logos and text legible without making the channel footer compete with the product or discount.
- Keep every overlay inside a consistent safe margin. It must not cover essential product details.

## Vertical 9:16 videos

- Keep the same product-card hierarchy: retailer logo upper-left, discount upper-right, and DigiPay directly below the retailer logo. Preserve the exact official artwork and aspect ratios; only the DigiPay background tile may extend.
- Keep the channel identity panel below the product title and above the product image, clear of YouTube's lower interface-safe area. On the 720×1280 poster, use four 26-pixel rows with a 20-pixel logo-height limit and 16-pixel label text; this keeps the complete YouTube wordmark tile within its row without collisions or clipping.
- For a YouTube Short, show the official YouTube horizontal wordmark and youtube.com/@offerchin first, followed by the Telegram, Bale, and Rubika rows. This identifies the current destination as well as the other channels.
- The three cross-channel rows use exactly the same official local logos and label treatment as product images. Keep marks small but readable and derive widths from their actual aspect ratios.
- Do not let video zoom/pan crop the discount, retailer mark, DigiPay tile, or channel identities.
- Preserve product title, product image, current price, and purchase call-to-action as the primary sales content; platform marks remain secondary.

## Official platform logo assets

- The platform marks must be the official files, not hand-drawn substitutes or typographic approximations.
- Local assets are stored in affilio_radar/assets/platform-logos/: Telegram SVG, Bale SVG, Rubika SVG, and the YouTube full-color horizontal wordmark PNG.
- The sync workflow downloads the files once from the official brand/press sources, validates the SVG/PNG formats and the YouTube landscape aspect ratio, and commits them to the repository. Content renderers never make network requests for platform logos.
- A logo must be resized proportionally with high-quality resampling. Its height is kept small and consistent; its width is allowed to differ to match the source aspect ratio.
- A logo rendering failure must not block a product post. Log the missing/invalid asset and omit that logo rather than draw an inaccurate replacement.
