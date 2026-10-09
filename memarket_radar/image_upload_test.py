#!/usr/bin/env python3
"""One-off private Telegram photo upload test; never publishes a customer-facing offer."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memarket_deal_radar as radar


def main():
    posts = radar.extract_posts(radar.fetch(radar.CHANNEL_URL))
    scored = [radar.score_post(p) for p in posts]
    candidates = [p for p in scored if p.get("qualifies")]
    candidates.sort(key=lambda p: (p["score"], p["percent"]), reverse=True)
    if not candidates:
        raise SystemExit("No qualifying source offer available for private photo-upload test.")

    post = candidates[0]
    result = radar.verify_offer_stock(post)
    image_url = result.get("product_image") or post.get("image") or ""
    if not image_url:
        raise SystemExit(
            f"No image could be extracted for test post {post['id']}; stock={result['status']}."
        )

    caption = (
        "🧪 آزمایش فنی آپلود تصویر محصول\n"
        f"نتیجه بررسی موجودی: {result['status']}\n"
        "⚠️ این پیام آفر خرید نیست. محصول قبلی ناموجود/غیرقابل‌تأیید بوده و برای تبلیغ ارسال نشود."
    )
    response = radar.upload_telegram_photo(image_url, caption)
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError(f"Telegram photo upload failed: {response!r}")
    print(
        f"PRIVATE_PHOTO_TEST=passed source_post={post['id']} "
        f"stock={result['status']} image_upload=success"
    )


if __name__ == "__main__":
    main()
