# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and 9:16 videos.

## Product images

- **Upper-right:** Keep the discount burst as the strongest visual accent. Do not place any logo or text in this corner.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset. Preserve the supplied logo, wordmark, original colors, and brand background tile exactly; scale proportionally only. Do not strip the tile, recolor, redraw, or add a separate panel. Keep it secondary to the discount burst and product.
- **Lower-left:** Place the Telegram and Bale channel IDs on two compact lines: `T.me/OfferChin` and `ble.ir/OfferChin`. Keep the text directly over the image, without a box or solid background.
- Choose each ID's foreground color from the luminance behind its actual text area: white over dark areas, dark over light areas. Add only a thin opposing outline when needed for legibility.
- Keep all overlays inside a consistent safe margin. They must not cover essential product details.

## Vertical 9:16 videos

- Keep the same hierarchy: discount upper-right and retailer mark upper-left within the product-card area.
- Keep the channel IDs at the lower-left, above the bottom platform-interface safe area. Do not add a solid text panel.
- Do not let the zoom/pan crop the discount, retailer mark, or channel IDs.
- Preserve the product title, main product image, current price, and call-to-action as the primary sales content; brand marks remain secondary.

## Asset and runtime rules

- Retailer logos live in `affilio_radar/assets/retailer-logos/` and must be read locally at render time. Never fetch logo assets from a remote URL during post creation.
- Preserve each official logo's original background and color. Resize the full asset proportionally; do not create a transparent cut-out or a substitute icon.
- A logo rendering failure must not block publishing; log the failure and continue without that logo.
- Apply this standard consistently to Telegram/Bale product posts and to generated YouTube Shorts/Aparat videos.
