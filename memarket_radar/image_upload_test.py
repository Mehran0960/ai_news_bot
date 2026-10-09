#!/usr/bin/env python3
"""One-off private Telegram photo upload test; never publishes a customer-facing offer."""
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memarket_deal_radar as radar


def main():
    me = radar.telegram_request("getMe", {})
    if not isinstance(me, dict) or me.get("ok") is not True:
        print("TELEGRAM_PREFLIGHT=failed (token/API response rejected)", flush=True)
        raise SystemExit("Telegram bot token/API preflight failed.")
    print("TELEGRAM_PREFLIGHT=passed", flush=True)

    posts = radar.extract_posts(radar.fetch(radar.CHANNEL_URL))
    scored = [radar.score_post(p) for p in posts]
    candidates = [p for p in scored if p.get("qualifies")]
    candidates.sort(key=lambda p: (p["score"], p["percent"]), reverse=True)
    if not candidates:
        raise SystemExit("No qualifying source offer available for private photo-upload test.")

    post = candidates[0]
    result = radar.verify_offer_stock(post)
    images = list(dict.fromkeys([
        result.get("product_image") or "",
        post.get("image") or "",
    ]))
    images = [x for x in images if x]
    if not images:
        raise SystemExit(f"No image extracted for test post {post['id']}; stock={result['status']}.")

    caption = (
        "🧪 آزمایش فنی آپلود تصویر محصول\n"
        f"نتیجه بررسی موجودی: {result['status']}\n"
        "⚠️ این پیام آفر خرید نیست. این محصول ناموجود شناسایی شده؛ برای تبلیغ ارسال نشود."
    )
    errors = []
    for image_url in images:
        host = urlsplit(image_url).hostname or "unknown-host"
        print(f"IMAGE_TEST_ATTEMPT host={host}")
        try:
            response = radar.upload_telegram_photo(image_url, caption)
            if isinstance(response, dict) and response.get("ok") is True:
                print(
                    f"PRIVATE_PHOTO_TEST=passed source_post={post['id']} "
                    f"stock={result['status']} image_upload=success host={host}"
                )
                return
            errors.append(f"{host}: Telegram returned {response!r}")
        except Exception as exc:
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
            print(f"IMAGE_TEST_FAILED host={host} error={type(exc).__name__}: {exc}")

    raise SystemExit("All private image-upload candidates failed. " + " | ".join(errors))


if __name__ == "__main__":
    main()
