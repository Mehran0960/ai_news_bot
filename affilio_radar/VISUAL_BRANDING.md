# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and destination-specific vertical videos.

## Product images

- **Upper-right:** Place the discount tile in a target rectangle with exactly the same width and height as the upper-left retailer-logo target rectangle. Use the solid retailer-specific color and a large percentage; for the wide shared frame, place the percentage on the right and the Persian word “تخفیف” on the left.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset in the same target width and height as the discount tile. Preserve the supplied artwork, wordmark, original colors, and aspect ratio; fit proportionally inside the shared bounds.
- **Below retailer logo:** Place the official DigiPay mark on its blue field, preserving the mark itself. The blue field may extend to match the retailer tile's target dimensions; do not stretch the logo artwork.
- **Lower-left cross-media list:** Show every verified public OfferChin destination except the destination receiving the post. The current public set is Telegram, Bale, Rubika, YouTube, and Aparat; each post therefore has exactly four rows. Eitaa is not included until its actual public channel ID is confirmed.
- **Each row:** Put only the original official platform logo beside its bare public ID. The ID is the link text itself, with no platform name, no “OfferChin •” prefix, no descriptive label, and no http://, https://, or www. Canonical IDs are t.me/OfferChin, ble.ir/OfferChin, rubika.ir/offerchin, youtube.com/@offerchin, and aparat.com/OfferChin.
- **YouTube logo:** Use the official horizontal full-color wordmark on its light solid backing. Preserve its original landscape aspect ratio. Never force it into a square icon box or stretch/crop its artwork. Its height should match the other small channel marks; its width is derived from the source ratio.
- **Aparat logo:** Use the locally pinned first-party header wordmark from Aparat's own homepage. Preserve its 80:25 viewBox ratio; do not substitute a third-party redraw.
- Scale the footer with source resolution instead of keeping every export at a tiny fixed pixel size. Row spacing remains resolution-aware, and logo width is derived from each source asset's actual aspect ratio.
- Choose each text foreground color from the luminance behind its actual ID area. Keep the IDs readable without making the cross-media footer compete with the product or discount.
- Keep every overlay inside a consistent safe margin. It must not cover essential product details.

## Vertical 9:16 videos

- Keep the same product-card hierarchy: retailer logo upper-left, discount upper-right, and DigiPay directly below the retailer logo. Preserve the exact official artwork and aspect ratios; only the DigiPay background tile may extend.
- Keep the cross-media ID panel below the product title and above the product image, clear of the platform's lower interface-safe area. Use four 26-pixel rows with a 20-pixel logo-height limit.
- A YouTube video lists only Telegram, Bale, Rubika, and Aparat; it must not list YouTube itself.
- An Aparat video lists only Telegram, Bale, Rubika, and YouTube; it must not list Aparat itself. YouTube's full horizontal wordmark remains visible when it is one of the other destinations.
- YouTube and Aparat must be rendered as separate MP4 artifacts when both are due. Never upload the same poster/video file to both platforms if the destination-specific cross-media ID list would differ.
- Each video row contains only the original logo and the bare ID string described above. No channel-name text, “OfferChin •” prefix, protocol, or www. is allowed.
- Do not let video zoom/pan crop the discount, retailer mark, DigiPay tile, or cross-media IDs.
- Preserve product title, product image, current price, and purchase call-to-action as the primary sales content; platform marks remain secondary.

- Above the four cross-media ID rows, the YouTube poster displays exactly “لینک خرید: توضیحات کانال”; the Aparat poster displays exactly “لینک خرید: کپشن ویدئو و توضیحات کانال”. The CTA is destination-specific, stays within the same light panel, and must not be copied to messenger images or to the other platform's video.
- Aparat's video description continues to include the tracked product purchase URL for that specific product; the CTA must point viewers to the video caption/description and the already configured channel description. The YouTube CTA points to the already configured channel profile description/link area; do not claim the CTA URL itself is clickable in Shorts.
- The purchase CTA is centered above the cross-media rows, fitted to the available width, and must remain readable without crowding the logos or covering the product image.

## Official platform logo assets

- The platform marks must be official files, not hand-drawn substitutes or typographic approximations.
- Local assets are stored in affilio_radar/assets/platform-logos/: Telegram SVG, Bale SVG, Rubika SVG, YouTube full-color horizontal wordmark PNG, and Aparat first-party wordmark SVG.
- The sync workflow downloads the assets from official/first-party sources, validates the SVG/PNG formats and horizontal aspect ratios, and commits them to the repository. Content renderers never make network requests for platform logos.
- A logo must be resized proportionally with high-quality resampling. Its height is kept small and consistent; its width is allowed to differ to match the source aspect ratio.
- A logo rendering failure must not block a product post. Log the missing/invalid asset and omit it rather than draw an inaccurate replacement.
