# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and destination-specific vertical videos.

## Product images

- **Upper-right:** Place the discount tile in a target rectangle with exactly the same width and height as the upper-left retailer-logo target rectangle. Use the solid retailer-specific color and a large percentage; for the wide shared frame, place the percentage on the right and the Persian word “تخفیف” on the left.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset in the same target width and height as the discount tile. Preserve the supplied artwork, wordmark, original colors, and aspect ratio; fit proportionally inside the shared bounds.
- **Below retailer logo:** Place the official DigiPay mark on its blue field, preserving the mark itself. The blue field may extend to match the retailer tile's target dimensions; do not stretch the logo artwork.
- **Lower-left cross-media list:** Show every verified public OfferChin destination except the destination receiving the post. The current public set is Telegram, Bale, Rubika, YouTube, and Aparat; each post therefore has exactly four rows. Eitaa is not included until its actual public channel ID is confirmed.
- **Each row:** Put only the official pictorial symbol (icon/mark) of the destination beside its bare public ID. The logo artwork must contain no Persian or Latin platform-name lettering and no wordmark. The ID is the link text itself, with no extra platform-name label, no “OfferChin •” prefix, and no http://, https://, or www. Canonical IDs are t.me/OfferChin, ble.ir/OfferChin, rubika.ir/offerchin, youtube.com/@offerchin, and aparat.com/OfferChin.
- **Alignment:** Reserve one equal-width icon column for all rows. Center each pictorial mark inside that column and start every ID at exactly the same horizontal coordinate. Never calculate the ID x-position from the natural width of the symbol.
- **YouTube logo:** Show only the official red play-button symbol from the full-color source asset. Crop away the “YouTube” lettering; preserve the play-button shape and original proportions. Do not display the horizontal wordmark.
- **Aparat logo:** Use only the pictorial icon-aparatfa symbol cropped from Aparat's first-party header SVG. Exclude the Latin wordmark/letters; do not substitute a third-party redraw.
- Scale the footer with source resolution instead of keeping every export at a tiny fixed pixel size. Row spacing remains resolution-aware, and logo width is derived from each source asset's actual aspect ratio.
- Choose each text foreground color from the luminance behind its actual ID area. Keep the IDs readable without making the cross-media footer compete with the product or discount.
- Keep every overlay inside a consistent safe margin. It must not cover essential product details.

## Vertical 9:16 videos

- Keep the same product-card hierarchy: retailer logo upper-left, discount upper-right, and DigiPay directly below the retailer logo. Preserve the exact official artwork and aspect ratios; only the DigiPay background tile may extend.
- Keep the cross-media ID panel below the product title and above the product image, clear of the platform's lower interface-safe area. Use four 26-pixel rows with a 20-pixel logo-height limit.
- A YouTube video lists only Telegram, Bale, Rubika, and Aparat; it must not list YouTube itself.
- An Aparat video lists only Telegram, Bale, Rubika, and YouTube; it must not list Aparat itself. When YouTube is another listed destination, show only its play-button icon, never its horizontal wordmark.
- YouTube and Aparat must be rendered as separate MP4 artifacts when both are due. Never upload the same poster/video file to both platforms if the destination-specific cross-media ID list would differ.
- Each video row contains only the icon-only pictorial mark and the bare ID string described above. No platform-name lettering inside the artwork, no channel-name text, “OfferChin •” prefix, protocol, or www. is allowed. Icons sit centered in one fixed-width column; all four IDs share the same left edge.
- Product titles inside the video title card use the bundled local Lalezar display font (SIL OFL 1.1), as a free, Titr-inspired headline treatment. Do not use an unlicensed Microsoft B Titr font or load fonts from the network at render time.
- Do not let video zoom/pan crop the discount, retailer mark, DigiPay tile, or cross-media IDs.
- Preserve product title, product image, current price, and purchase call-to-action as the primary sales content; platform marks remain secondary.

- Above the four cross-media ID rows, the YouTube poster displays exactly “لینک خرید: توضیحات کانال”; the Aparat poster displays exactly “لینک خرید: کپشن ویدئو و توضیحات کانال”. The CTA is destination-specific, stays within the same light panel, and must not be copied to messenger images or to the other platform's video.
- Aparat's video description continues to include the tracked product purchase URL for that specific product; the CTA must point viewers to the video caption/description and the already configured channel description. The YouTube CTA points to the already configured channel profile description/link area; do not claim the CTA URL itself is clickable in Shorts.
- The purchase CTA is centered above the cross-media rows, fitted to the available width, and must remain readable without crowding the logos or covering the product image.

## Official platform logo assets

- The platform marks must be official files, not hand-drawn substitutes or typographic approximations.
- Local source assets are stored in affilio_radar/assets/platform-logos/. Some official source files are complete lockups, but the shared renderer selects only the pictorial symbol: Telegram's mark, Bale's standalone mark, Rubika's multicolor symbol, YouTube's red play button, and Aparat's icon-aparatfa symbol. Source wordmarks are never painted into the cross-media ID rows.
- The sync workflow downloads the source assets from official/first-party sources and commits them locally. The shared renderer crops the icon-only viewBox/mark before drawing; content renderers never make network requests for platform logos. Regression tests validate icon-only geometry and preserved proportions.
- An icon must be resized proportionally with high-quality resampling. Its height is kept small and consistent; its width follows the symbol's aspect ratio.
- A logo rendering failure must not block a product post. Log the missing/invalid asset and omit it rather than draw an inaccurate replacement.
