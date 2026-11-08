# OfferChin Visual Branding Standard

This is the canonical placement and legibility standard for generated OfferChin product images and destination-specific vertical videos.

## Product images

- **Upper-right:** Place the discount tile in a target rectangle with exactly the same width and height as the upper-left retailer-logo target rectangle. Use the solid retailer-specific color and a large percentage; for the wide shared frame, place the percentage on the right and the Persian word “تخفیف” on the left.
- **Upper-left:** Place the relevant retailer's complete official logo from its locally bundled asset in the same target width and height as the discount tile. Preserve the supplied artwork, wordmark, original colors, and aspect ratio; fit proportionally inside the shared bounds.
- **Below retailer logo:** Place the official DigiPay mark on its blue field, preserving the mark itself. The blue field may extend to match the retailer tile's target dimensions; do not stretch the logo artwork.
- **Lower-left cross-media list:** Show every verified public OfferChin destination except the destination receiving the post. The current public set is Telegram, Bale, Rubika, YouTube, and Aparat; each post therefore has exactly four rows. Eitaa is not included until its actual public channel ID is confirmed.
- **Each row:** Put only the official pictorial symbol (icon/mark) of the destination beside its bare public ID. The logo artwork must contain no Persian or Latin platform-name lettering and no wordmark. The visible text label must show the brand as `OfferChin`, including `rubika.ir/OfferChin` and `youtube.com/@OfferChin`, with no extra platform-name label, no “OfferChin •” prefix, and no http://, https://, or www. The canonical route/handle stored in code and used as an actual link or API identifier remains unchanged where the platform's canonical form is lowercase (currently `rubika.ir/offerchin` and `youtube.com/@offerchin`).
- **Alignment:** Reserve one equal-width icon column for all rows. Center each pictorial mark inside that column and start every ID at exactly the same horizontal coordinate. Never calculate the ID x-position from the natural width of the symbol.
- **Logo fidelity:** Do not redraw, approximate, recolour, simplify, or alter any symbol. Start from the exact official/first-party artwork. Remove only the platform-name wordmark by changing the SVG viewport or cropping the source image; preserve every visible original path/pixel, its original colours, proportions, and details.
- **Bale logo:** In the pinned official SVG, the Persian wordmark is on the left and the complete green speech/check symbol is at `viewBox="54 4 32 32"`. Keep that entire symbol; do not crop into its top, bottom, or sides.
- **Rubika logo:** Keep the complete multicolour pictorial mark from the official SVG at `viewBox="783.5 0 495.39 543.02"`; exclude the grey wordmark to its left. No segments or colours of the symbol may be removed.
- **YouTube logo:** Show the original red play-button symbol from the official full-colour source asset. Crop away only the “YouTube” lettering; preserve the button's original rounded shape, white triangle, colours, and pixels. Do not redraw it.
- **Aparat logo:** Use the full pictorial icon-aparatfa symbol from Aparat's first-party header SVG at `viewBox="56 0 24 25"`. Exclude only the wordmark to its left.
- Scale the footer with source resolution instead of keeping every export at a tiny fixed pixel size. Row spacing remains resolution-aware, and logo width is derived from each source asset's actual aspect ratio.
- Choose each text foreground color from the luminance behind its actual ID area. Keep the IDs readable without making the cross-media footer compete with the product or discount.
- Keep every overlay inside a consistent safe margin. It must not cover essential product details.

## Vertical 9:16 videos

- Keep the same product-card hierarchy: retailer logo upper-left, discount upper-right, and DigiPay directly below the retailer logo. Preserve the exact official artwork and aspect ratios; only the DigiPay background tile may extend.
- Keep the cross-media ID panel below the product title and above the product image, clear of the platform's lower interface-safe area. Use four 26-pixel rows with a 20-pixel logo-height limit.
- A YouTube video lists only Telegram, Bale, Rubika, and Aparat; it must not list YouTube itself.
- An Aparat video lists only Telegram, Bale, Rubika, and YouTube; it must not list Aparat itself. When YouTube is another listed destination, show only its play-button icon, never its horizontal wordmark.
- YouTube and Aparat must be rendered as separate MP4 artifacts when both are due. Never upload the same poster/video file to both platforms if the destination-specific cross-media ID list would differ.
- Each video row contains only the icon-only pictorial mark and the bare ID string described above. Its visible brand segment must use `OfferChin` casing, even when the canonical URL/handle used by the platform remains lowercase. No platform-name lettering inside the artwork, no extra channel-name text, “OfferChin •” prefix, protocol, or www. is allowed. Icons sit centered in one fixed-width column; all four IDs share the same left edge.
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
- An icon must be resized proportionally with high-quality resampling. Its height is kept small and consistent; its width follows the symbol's aspect ratio. The only permitted source modification is the crop/viewport that removes the platform-name wordmark; the symbol artwork itself is immutable.
- A logo rendering failure must not block a product post. Log the missing/invalid asset and omit it rather than draw an inaccurate replacement.



## Brand display-name casing

Any visible Latin spelling of the project/brand name in generated captions, image text, video title cards, video metadata, descriptions, or other public-facing copy must be exactly **OfferChin** (capital O and C). Do not display `Offerchin`, `offerchin`, or `OFFERCHIN` as the brand name.

The shared `normalize_brand_display_name` helper enforces this spelling in public-facing title and description paths. It must not rewrite canonical platform identifiers, URLs, usernames, module/file names, API IDs, or environment-variable keys. For image/video overlays only, `platform_footer_label` separately formats the human-visible ID label with `OfferChin` casing; it does not mutate the canonical route/handle (`rubika.ir/offerchin` and `youtube.com/@offerchin`) used by links and APIs.


## Runtime casing guard and stale-video re-render

- Every generated product image and every destination-specific vertical video derives public channel rows from the same `platform_footer_label` formatter. Before any cross-media list is assembled, `validate_public_channel_footer_labels()` checks every registered public ID against the exact display contract: `t.me/OfferChin`, `ble.ir/OfferChin`, `rubika.ir/OfferChin`, `youtube.com/@OfferChin`, and `aparat.com/OfferChin`.
- If the registry or formatter drifts, rendering stops with an explicit validation error instead of silently publishing a lowercase brand spelling. This check is separate from canonical routes: `rubika.ir/offerchin` and `youtube.com/@offerchin` remain unchanged for routing and API use.
- `VIDEO_STYLE_VERSION` is advanced to 8 for the cross-media casing correction. Previously generated but not yet uploaded MP4s are marked for regeneration before their next eligible upload. Already-published images/videos are not rewritten or reposted automatically.
