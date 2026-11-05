# دفتر تغییرات و اقدامات OfferChin

> این دفتر append-only است: ورودی‌های قبلی پاک یا بازنویسی نمی‌شوند. هر تغییر فنی/تنظیمی/عملیاتیِ دستی باید یک ورودی تازه داشته باشد. اجرای زمان‌بندی‌شدهٔ عادی که فقط state یا cursor تولید می‌کند، به‌جای ثبت روزانهٔ تک‌تک رویدادها از GitHub Actions و artifact/state ledger قابل ردیابی است.

## قالب اجباری هر ورودی

هر ورودی باید این موارد را داشته باشد:
- **هدف:** مسئله یا نتیجه‌ای که تغییر دنبال می‌کند.
- **تغییر/اقدام:** آنچه واقعاً انجام شد؛ نه برنامه یا ادعای انجام‌نشده.
- **فایل‌ها/سامانه‌ها:** مسیر فایل یا سرویس/Worker/تنظیم بیرونی.
- **آزمون و نتیجه:** command و نتیجهٔ واقعی یا عبارت «در انتظار اجرا».
- **شواهد/شناسه:** commit SHA، PR، Actions run ID، post ID یا پاسخ مستند سرویس؛ هرکدام که مرتبط است.
- **ریسک/بازگشت:** خطر احتمالی و روش rollback/feature flag.
- **وضعیت:** انجام‌شده، در انتظار، مسدود یا لغوشده.

## ۲۰۲۶-۱۱-۰۵ — منشور پروژه و الزام مستندسازی

**هدف:** تثبیت هدف، تصمیم‌ها، مسیر طی‌شده و نقشهٔ راه؛ جلوگیری از تغییرات بدون سابقه و قابل‌بازیابی‌نبودن پروژه.

**تغییر/اقدام:** منشور پروژه و دفتر append-only اضافه می‌شود؛ handbook فنی به هدف و وضعیت واقعی کد پیوند داده می‌شود؛ Documentation Gate برای PR و pushهای main افزوده می‌شود؛ الگوی PR الزام ثبت شواهد، تست و rollback را روشن می‌کند.

**فایل‌ها/سامانه‌ها:** `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`، `scripts/validate_offerchin_documentation.py`، `scripts/test_validate_offerchin_documentation.py`، `.github/workflows/offerchin-documentation-gate.yml`، `.github/PULL_REQUEST_TEMPLATE.md`، `README.md`.

**آزمون و نتیجه:** تست‌های واحد validator و اجرای واقعی Documentation Gate پس از ایجاد PR؛ نتیجهٔ CI در همین ورودی تکمیل می‌شود.

**شواهد/شناسه:** شاخهٔ `docs/offerchin-charter-and-documentation-gate-2026-11-05`؛ PR و commit نهایی پس از ایجاد ثبت می‌شوند.

**ریسک/بازگشت:** Gate تنها وقتی merge را واقعاً مسدود می‌کند که در تنظیمات GitHub برای `main` به‌عنوان Required status check تعریف شود و bypass/direct push محدود شود. تا تأیید این تنظیم، workflow تخلف را آشکار می‌کند اما تضمین کامل جلوگیری از push مستقیم نیست. بازگشت: revert کردن commit مستندات/Workflow؛ تغییری در منطق انتشار زنده انجام نشده است.

## ۲۰۲۶-۱۱-۰۵ — تثبیت تغییرات برندینگ ویدئو (سابقهٔ موجود)

**هدف:** هم‌ترازی لوگوی فروشگاه، نشان تخفیف و نشان دیجی‌پی در تصویر محصول.

**تغییر/اقدام:** در PR شمارهٔ 66 چیدمان نشان فروشگاه بالا-چپ، تخفیف بالا-راست با ابعاد هماهنگ و دیجی‌پی زیر نشان فروشگاه اصلاح شد؛ درصد تکراری زیر قیمت حذف شد. این تغییر برای ویدئوهای بعدی است و محتوای منتشرشدهٔ قبلی را بازسازی نکرد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`.

**آزمون و نتیجه:** در CI گزارش‌شده ۴۱۳ تست اجرا شد؛ ۲ مورد skip و نتیجهٔ کلی OK بود.

**شواهد/شناسه:** [PR #66](https://github.com/Mehran0960/ai_news_bot/pull/66)، merge commit `1644acb78e9b59e3b862de373dae3a4bbc3e7620`؛ اجرای ناشر run `42066318179` با نتیجهٔ success ثبت شده است.

**ریسک/بازگشت:** rollback با revert همان merge commit ممکن است؛ چون فایل‌های runtime-state در این PR نبودند، صف و داده‌های انتشار نباید دستکاری شوند.

## ۲۰۲۶-۱۱-۰۴ — اسکن جامع و سیاست تخفیف‌محور (سابقهٔ موجود)

**هدف:** حذف محدودیت سه صفحه در هر دسته و پوشش چرخه‌ای تمام صفحات قابل‌دسترسی.

**تغییر/اقدام:** pagination بدون سقف عمق ثابت، صف صفحه‌های پایدار، retry و اجرای موازی اضافه/اصلاح شد. در همان تغییر، راهبرد انتخاب زنده به درصد تخفیف نزولی و سپس مبلغ صرفه‌جویی نزولی تغییر یافت و تقاضا/تنوع در رتبه‌بندی انتخاب از حالت مؤثر خارج شد. این مورد یک تغییر مهم سیاست محصول است و در منشور به‌عنوان اختلاف میان هدف و رفتار فعلی ثبت شده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/affilio_radar.py`، تست‌های مربوط و workflowهای اسکن/انتشار.

**آزمون و نتیجه:** گزارش اجرای ۴ نوامبر: ۳۰۰/۳۰۰ صفحهٔ batch موفق، ۵٬۸۸۴ کارت محصول، صفر retry و صفر HTTP 429؛ اما ۲٬۶۳۷ صفحه در صف مانده و full cycle کامل نشده بود.

**شواهد/شناسه:** جزئیات در [handbook فنی](OFFERCHIN_PROJECT_HANDBOOK_FA.md) و workflowهای کاتالوگ ثبت شده‌اند؛ SHA اجرای دقیقِ full-cycle در این دفتر موجود نیست.

**ریسک/بازگشت:** تغییر ranking باید با branch و تست مستقل انجام شود؛ برگرداندن آن بدون آزمون می‌تواند ترتیب صف و انتشار را تغییر دهد. pagination پایدار را نباید هم‌زمان با تغییر ranking rollback کرد.


## ۲۰۲۶-۱۱-۰۵ — تکمیل اعتبارسنج مستندات و آزمون محلی PR شمارهٔ ۶۷

**هدف:** اطمینان از اینکه Documentation Gate تاریخ فارسی، مسیرهای workflow و تغییرهای دستی فایل‌های runtime را درست تشخیص می‌دهد.

**تغییر/اقدام:** regex تاریخ با تشخیص صریح ارقام فارسی/لاتین جایگزین شد؛ نرمال‌سازی مسیرهای ویندوزی اصلاح شد؛ ویرایش دستی فایل‌های runtime در PR نیز مشمول الزام مستندسازی شد. اجرای زمان‌بندی‌شدهٔ معمول روی main همچنان فقط از طریق state و workflow قابل ردیابی است و path filter آن‌ها را به‌عنوان تغییر دستی تلقی نمی‌کند.

**فایل‌ها/سامانه‌ها:** `scripts/validate_offerchin_documentation.py`، `scripts/test_validate_offerchin_documentation.py`.

**آزمون و نتیجه:** `python -m py_compile validate_offerchin_documentation.py test_validate_offerchin_documentation.py` موفق؛ `python -m unittest -v test_validate_offerchin_documentation.py` موفق، ۷ تست از ۷ تست. اجرای Actions برای این workflow پیش از ادغام در دسترس نیست، زیرا workflow تازه در همین PR اضافه شده و هنوز در `main` وجود ندارد؛ پس از ادغام باید اجرای واقعی آن بررسی شود.

**شواهد/شناسه:** [PR #67](https://github.com/Mehran0960/ai_news_bot/pull/67)، head SHA `01eb60faf49930d40026e006cedf354a65d488ff`.

**ریسک/بازگشت:** اگر Gate مسیر اشتباهی را مسدود کند، validator/test را اصلاح و دوباره اجرا کنید؛ تغییر در منطق انتشار انجام نشده است. بازگشت کامل با revert PR امکان‌پذیر است.

**وضعیت:** تست محلی موفق؛ ادغام و اجرای واقعی GitHub Actions در انتظار.


## ۲۰۲۶-۱۱-۰۵ — نتیجهٔ ادغام PR شمارهٔ ۶۷ و تکمیل سیاست ثبت تغییرات

**هدف:** ثبت ادغام موفق منشور و Gate روی main و بستن خلأهای باقی‌مانده در الزام مستندسازی.

**تغییر/اقدام:** PR شمارهٔ ۶۷ با روش squash در main ادغام شد. دامنهٔ الزام مستندسازی در این PR تکمیلی به تغییر handbook، منشور، README و الگوی PR نیز گسترش یافت؛ سابقهٔ changelog دیگر قابل بازنویسی نیست و حذف فایل‌های پروژه هم به‌عنوان تغییر بررسی می‌شود. اجرای زمان‌بندی‌شدهٔ عادی همچنان با Actions/state ledger ردیابی می‌شود، ولی ویرایش دستی فایل runtime در PR نیازمند ثبت است.

**فایل‌ها/سامانه‌ها:** `scripts/validate_offerchin_documentation.py`، `scripts/test_validate_offerchin_documentation.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** اجرای PR Gate با run ID `42070726804` و Push Gate با run ID `42070783975` هر دو success؛ ۷ تست validator در اجرای PR موفق. تست‌های تازهٔ append-only و پوشش docs در PR تکمیلی اجرا می‌شوند.

**شواهد/شناسه:** [PR #67](https://github.com/Mehran0960/ai_news_bot/pull/67)، merge commit `111c674d93bd6034f25eacbd449bb67010d0912f`، run IDs بالا؛ PR تکمیلی روی شاخهٔ `fix/offerchin-append-only-docs-gate-2026-11-05`.

**ریسک/بازگشت:** Required status check و محدودسازی direct push هنوز در تنظیمات Branch Protection تأیید نشده است؛ تا آن زمان Gate در PR و pushهای مشمول اجرا می‌شود اما ممکن است با direct push دور زده شود. بازگشت با revert PR تکمیلی ممکن است.

**وضعیت:** PR #67 ادغام‌شده و Gate آن موفق؛ append-only hardening در انتظار ادغام و آزمون CI.
