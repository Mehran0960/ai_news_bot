# MeMarket Affiliate Deal Radar

این پروژه جدا از پروژه‌های محتوایی است و فقط برای پایش آفرهای MeMarket و ارسال هشدار تلگرامی استفاده می‌شود.

## Secrets
در Settings → Secrets and variables → Actions این ۵ Secret را ثبت کن:
- MEMARKET_USERNAME
- MEMARKET_PASSWORD
- MEMARKET_AFFILIATE_CODE
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

مقادیر محرمانه را داخل کد یا Commit نگذار.

## رفتار
- اجرا هر ۱۵ دقیقه
- حداقل تخفیف ۳۰٪
- تخفیف ۴۰٪+ سیگنال قوی‌تر
- افت قیمت ۸٪+ سیگنال مهم
- موجودی ۵ یا کمتر سیگنال کمکی
- حداکثر ۳ هشدار در هر اجرا
- Cooldown شش‌ساعته برای جلوگیری از اسپم
- اولین اجرای واقعی فقط وضعیت را جمع می‌کند و به‌صورت پیش‌فرض هشدار نمی‌فرستد

## شروع
بعد از ثبت Secrets:
Actions → MeMarket Deal Radar → Run workflow

اولین اجرا اتصال MeMarket و Telegram را تست و state را ساخته/به‌روزرسانی می‌کند.
