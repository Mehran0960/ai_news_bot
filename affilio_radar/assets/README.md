# OfferChin shared artwork

This folder is the single, version-controlled asset library used by both product-photo and vertical-video renderers.

## Rules

- Production rendering must read local files only. Do not add per-run downloads or CDN fallbacks for logos, fonts, badges, or icons.
- Add or replace a visual file under this folder, then register it in `asset-manifest.json`.
- Every required asset must be included in `offerchin_visuals.validate_brand_assets()` coverage through the manifest.
- Use `offerchin_visuals.load_brand_asset(name)` for shared image assets and `draw_discount_flame()`, `draw_discount_burst()`, `draw_retailer_badge()`, and `draw_digipay_badge()` for reusable render components.
- Discount percentage badges are generated programmatically from the current product's verified percentage; the shared flame artwork is a local SVG.
- Never commit user-specific product photos, campaign artwork, or API credentials into this directory.

The retailer and DigiPay brand files are first-party logo artwork. The DigiPay SVG is preserved from the official MyDigiPay asset URL recorded in the manifest.
