# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and 9:16 videos.

## Product images

- **Upper-right:** Place the discount tile in a target rectangle with exactly the same width and height as the upper-left retailer-logo target rectangle. Use the solid retailer-specific color and a large percentage; for the wide shared frame, place the percentage on the right and the Persian word “تخفیف” on the left. The badge remains the strongest visual accent through color and typography, not by taking more space.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset in the same target width and height as the discount tile. Preserve the supplied artwork, wordmark, original colors, and aspect ratio; fit proportionally inside the shared bounds. Apply the same subtle, antialiased corner radius to the retailer tile, DigiPay tile, and discount tile. Do not stretch, strip the tile, recolor, redraw, or add a separate panel.
- **Lower-left:** Place the other three public OfferChin destinations as a compact, vertically stacked list. Each row starts with its matching platform mark, immediately followed by its link: Telegram `t.me/OfferChin`, Bale `ble.ir/OfferChin`, Rubika `rubika.ir/offerchin`, and YouTube `youtube.com/@offerchin`. Exclude the destination receiving the post; for example, a Telegram image lists Bale, Rubika, and YouTube. Keep the marks and text directly over the image, without a box or solid background.
- Choose each ID's foreground color from the luminance behind its actual text area: white over dark areas, dark over light areas. Add only a thin opposing outline when needed for legibility.
- Keep all overlays inside a consistent safe margin. They must not cover essential product details.

## Vertical 9:16 videos

- Keep the same hierarchy: discount upper-right and retailer mark upper-left within the product-card area; use exactly equal target width and height for both elements.
- Keep the other three network destinations in a vertical CTA list below the title and above the product image, clear of YouTube's bottom interface-safe area. Exclude YouTube itself from the YouTube Short overlay.
- Do not let the zoom/pan crop the discount, retailer mark, or channel IDs.
- Preserve the product title, main product image, current price, and call-to-action as the primary sales content; brand marks remain secondary.

## Asset and runtime rules

- Retailer logos live in `affilio_radar/assets/retailer-logos/`; channel logos live in `affilio_radar/assets/channel-logos/`. Both are read locally at render time. Never fetch logo assets from a remote URL during post creation.
- Telegram, Bale, Rubika, and YouTube marks use their bundled color SVG files. Do not replace them with hand-drawn approximations, initials, or generic platform glyphs.
- Decode each SVG once per process and reuse the cached image. Preserve source colors, shape, and aspect ratio; only proportional antialiased downscaling is allowed. A missing/corrupt asset is logged and must not block publishing.
- Preserve each official logo's original background and color. Resize the full asset proportionally; do not create a transparent cut-out or a substitute icon.
- A logo rendering failure must not block publishing; log the failure and continue without that logo.
- Apply destination-aware links consistently to Telegram, Bale, and Rubika product images and to the YouTube Short artwork. The current shared video asset remains designed for the YouTube destination.
