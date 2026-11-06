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


## ۲۰۲۶-۱۱-۰۵ — تکمیل خط زمانی تاریخی منشور OfferChin

**هدف:** ثبت مسیر طی‌شده، تصمیم‌های مهم، نقاط عطف زمان‌دار و محدودیت‌هایی که نباید در ادامهٔ پروژه فراموش شوند.

**تغییر/اقدام:** بخش ۱۱ به منشور افزوده شد. تاریخ‌های نامعلوم به‌صورت نامعلوم باقی ماندند؛ اقدامات ۴ و ۵ نوامبر با commit/PR و شواهد ثبت‌شده پیوند خوردند. وضعیت فعلی ranking، تفاوت کلیک داخلی با conversion افیلیو، مسیرهای رسانه و کارهای باز نیز در خط زمانی آمده‌اند.

**فایل‌ها/سامانه‌ها:** `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** Gate مستندات PR باید بررسی کند که دفتر قبلی فقط append شده و ورودی جدید همهٔ فیلدها را دارد؛ نتیجهٔ Actions پس از بازشدن PR ثبت می‌شود.

**شواهد/شناسه:** merge commit منشور و Gate: `111c674d93bd6034f25eacbd449bb67010d0912f`؛ merge commit hardening: `c12f9aee289b31cac898a1ee205710820ed63204`. شاخهٔ فعلی: `docs/offerchin-project-timeline-2026-11-05`.

**ریسک/بازگشت:** تاریخ‌های مراحل قدیمی‌تر عمداً تخمین زده نشده‌اند. هر اصلاح آتی باید بر مبنای commit/PR یا سند واقعی باشد؛ بازگشت با revert PR ممکن است.

**وضعیت:** در انتظار بررسی و ادغام PR.


## ۲۰۲۶-۱۱-۰۵ — افزودن ارزیابی سایه‌ای رتبه‌بندی تقاضا و ارزش

**هدف:** سنجش عملی اختلاف سیاست زندهٔ تخفیف‌محور با هدف محصولی demand/value، بدون تغییر انتخاب یا انتشار واقعی.

**تغییر/اقدام:** تابع `selection_policy_shadow_sort_key` بر مبنای سیگنال تقاضای تازه، شواهد مستقل و تازهٔ ارزش، درصد تخفیف و مبلغ صرفه‌جویی اضافه شد. `log_selection_policy_shadow` رتبه‌بندی پنج گزینهٔ اول live و shadow و شمار شواهد معتبر را فقط log می‌کند. فراخوانی آن در selector در یک بلوک ایمن قرار دارد و خطای آن مسیر اصلی را متوقف نمی‌کند. سه تست برای تقدم تقاضای تازه در shadow، تقدم شواهد مستقل ارزش و عدم تغییر/جهش لیست کاندیداها اضافه شد. رتبه‌بندی زنده همچنان discount-first باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_selection_evidence.py`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های جدید در `test_selection_evidence.py` و مجموعهٔ کامل regression در CI اجرا می‌شوند؛ نتیجهٔ واقعی پس از اجرای GitHub Actions تکمیل خواهد شد.

**شواهد/شناسه:** شاخهٔ `offerchin/demand-value-shadow-ranking-2026-11-05`؛ PR و SHA پس از ایجاد ثبت می‌شوند.

**ریسک/بازگشت:** shadow logger فقط log می‌نویسد؛ مسیر انتخاب زنده را تغییر نمی‌دهد و با revert کردن commit قابل حذف است. تعداد logها محدود به هر اجرای selector و پنج ID برتر است؛ دادهٔ حساس یا URL/secret ثبت نمی‌شود.

**وضعیت:** پیاده‌سازی و مستندسازی انجام‌شده؛ در انتظار CI و بازبینی.


## ۲۰۲۶-۱۱-۰۵ — نتیجهٔ CI و ادغام ارزیابی سایه‌ای رتبه‌بندی

**هدف:** ثبت شواهد نهایی آزمون و استقرار telemetry رتبه‌بندی هدف، بدون تغییر سیاست انتشار.

**تغییر/اقدام:** PR شمارهٔ ۷۰ با موفقیت ادغام شد. shadow rank و log مقایسهٔ پنج گزینهٔ اول در کد اصلی فعال است؛ ترتیب live، eligibility و hand-off همچنان discount-first باقی مانده‌اند. اجرای push مربوط به branch feature فقط regression/validation را انجام داد و مرحلهٔ discovery/queue در آن skip بود؛ بنابراین از آن، انتشار یا دادهٔ واقعی محصول نتیجه‌گیری نمی‌شود. logهای تغییر ترتیب در CI از نمونه‌های آزمون هستند، نه نمونهٔ واقعی live. نخستین مقایسهٔ زنده پس از اجرای عادی انتخاب باید از خروجی `SELECTION_POLICY_SHADOW_ONLY` بررسی و ثبت شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_selection_evidence.py`، منشور و handbook.

**آزمون و نتیجه:** `Affilio Product Radar` run `42073195387`: success؛ regression suite شامل `test_selection_evidence.py`: **۴۱۶ تست، ۲ مورد skip، نتیجه OK**. Catalog Sweep Regression run `42073380511`: success. Top-100 and DigiPay Regression run `42073380556`: success. Documentation Gate برای PR run `42073380878`: success؛ push به main run `42073598975`: success.

**شواهد/شناسه:** [PR #70](https://github.com/Mehran0960/ai_news_bot/pull/70)، merge commit `5e4bb1d3c73d1ec8402e6fd56655da0fc252ea58`؛ [Affilio Product Radar](https://github.com/Mehran0960/ai_news_bot/actions/runs/42073195387)، [Documentation Gate on main](https://github.com/Mehran0960/ai_news_bot/actions/runs/42073598975).

**ریسک/بازگشت:** این تغییر فقط log می‌نویسد؛ هیچ تغییری در رتبهٔ واقعی، صف، زمان‌بندی، لینک افیلیت یا انتشار ایجاد نمی‌کند. بازگشت با revert merge commit ممکن است. فعال‌سازی demand/value/diversity در سیاست live نیازمند بررسی نمونه‌های واقعی shadow و آزمون مستقل است.

**وضعیت:** ادغام‌شده؛ تمام CIهای مرتبط موفق؛ مشاهدهٔ خروجی shadow واقعی در اجرای عادی بعدی باقی است.


## ۲۰۲۶-۱۱-۰۵ — گسترش Documentation Gate به تمام فایل‌های مخزن

**هدف:** بستن امکان دور زدن الزام مستندسازی با افزودن فایل در مسیر یا ماژول جدیدی که قبلاً در allowlist نبود.

**تغییر/اقدام:** validator اکنون همهٔ فایل‌های trackشدهٔ مخزن را مشمول مستندسازی می‌کند و فقط `docs/CHANGELOG_FA.md` را با قاعدهٔ append-only جداگانه می‌سنجد. workflow برای push روی main به‌طور کلی فعال است و فقط commitهای زمان‌بندی‌شده‌ای را که منحصراً state/candidate/reportهای runtime مشخص هستند با `paths-ignore` نادیده می‌گیرد. PR دستی روی هر مسیر، از جمله state، همچنان باید handbook و changelog را به‌روزرسانی کند. تست scope برای پوشش یک ماژول فرضی جدید اضافه شد.

**فایل‌ها/سامانه‌ها:** `scripts/validate_offerchin_documentation.py`، `scripts/test_validate_offerchin_documentation.py`، `.github/workflows/offerchin-documentation-gate.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های validator و Documentation Gate در CI این PR اجرا می‌شوند؛ نتیجه پس از اجرا ثبت می‌شود.

**شواهد/شناسه:** شاخهٔ `ci/offerchin-repository-wide-documentation-gate-2026-11-05`.

**ریسک/بازگشت:** فایل runtime جدید اگر به‌صورت خودکار commit شود و در الگوهای `paths-ignore` فهرست نشده باشد، Gate اجرا می‌شود و ممکن است به‌دلیل نبود مستندات fail شود؛ این رفتار عمداً fail-closed است تا مسیر جدید نادیده گرفته نشود. rollback با revert PR ممکن است.

**وضعیت:** پیاده‌سازی و مستندسازی؛ در انتظار CI.


## ۲۰۲۶-۱۱-۰۵ — تأیید نهایی Gate سراسری مخزن

**هدف:** ثبت نتیجهٔ استقرار سیاست مستندسازی برای تمام فایل‌های مخزن و بستن اقدام مستندات سراسری.

**تغییر/اقدام:** PR شمارهٔ ۷۲ ادغام شد. validator اکنون همهٔ فایل‌های trackشده به‌جز خود changelog را مشمول مستندسازی می‌کند؛ فایل‌های جدید/مسیرهای جدید نیز پوشش دارند. هر entry جدید changelog باید تمام فیلدهای ساختاری را داشته باشد و سوابق قبلی append-only باقی می‌مانند. push به main برای همهٔ تغییرها Gate اجرا می‌کند، به‌جز commitهایی که فقط شامل runtime state/candidate/reportهای شناخته‌شده‌اند. PR دستی در همان فایل‌های runtime همچنان مشمول Gate است.

**فایل‌ها/سامانه‌ها:** `scripts/validate_offerchin_documentation.py`، `scripts/test_validate_offerchin_documentation.py`، `.github/workflows/offerchin-documentation-gate.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست validator در PR #72: **۹ تست موفق**؛ Documentation Gate برای PR run `42074573807`: success؛ Documentation Gate روی main run `42074769163`: success.

**شواهد/شناسه:** [PR #72](https://github.com/Mehran0960/ai_news_bot/pull/72)، merge commit `b46103985ddcb11aa9df5b35e5687f398abe60cf`؛ [PR Gate](https://github.com/Mehran0960/ai_news_bot/actions/runs/42074573807)، [Main push Gate](https://github.com/Mehran0960/ai_news_bot/actions/runs/42074769163).

**ریسک/بازگشت:** workflow اکنون در PR و push اجرا می‌شود، اما اجرای workflow به‌تنهایی push مستقیم را مسدود نمی‌کند؛ هنوز باید `enforce-docs` به‌عنوان Required status check در Branch Protection تنظیم و bypass/direct push محدود شود. اتصال فعلی مجوز مدیریتی برای اعمال آن تنظیم را ندارد. بازگشت با revert PR #72 ممکن است.

**وضعیت:** ادغام‌شده؛ ۹ تست validator و هر دو اجرای Gate موفق.

## ۲۰۲۶-۱۱-۰۶ — تثبیت سیاست سراسری تخفیف‌اول و اصلاح گارد تکرار

**هدف:** اجرای تصمیم نهایی محصول: انتخاب بالاترین درصد تخفیفِ مشاهده‌شده و واجدشرایط از کل کاتالوگ قابل‌دسترسی دیجی‌کالا؛ در درصد برابر، مبلغ صرفه‌جویی بیشتر مقدم باشد. هیچ شاخص تقاضا، بازار یا تنوع نباید رتبه را تغییر دهد.

**تغییر/اقدام:** تابع `_filter_recent_publication_repeats` بازطراحی شد تا تکرار خانواده/برند/عنوان مشابه را فقط به‌صورت telemetry با شمارنده‌های `REPEAT_DIAGNOSTICS` ثبت کند و هیچ کاندیدایی را حذف، تعویق یا جابه‌جا نکند. ترتیب اصلی `discount_percent DESC` سپس `savings_toman DESC` حفظ شد. تست‌های قدیمیِ انتظارِ family/brand/similarity suppression به قرارداد جدید تغییر کردند و regression test صریح درصد/صرفه‌جویی اضافه شد. کنترل همان SKUِ بدون بهبود، صحت قیمت و موجودی، deadline، لینک، ایمنی و idempotency دست‌نخورده ماند. منشور و handbook به تصمیم نهایی به‌روزرسانی شدند؛ دادهٔ shadow مورخ ۵ نوامبر صرفاً به‌عنوان سابقه حفظ شد. بررسی مستقیم API عمومی DigiKala در ۶ نوامبر نشان داد `sort=7` پرفروش‌ترین است و گزینهٔ sort سراسری برای بیشترین تخفیف وجود ندارد؛ پس جمع‌آوری صفحات و رتبه‌بندی محلی لازم است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ شاخهٔ `docs/discount-first-charter-and-operating-rules-2026-11-06`.

**آزمون و نتیجه:** regression tests به‌روز شده‌اند؛ نتیجهٔ نهایی unit/CI و Documentation Gate در زمان ثبت این ورودی هنوز در انتظار اجرای PR است و موفقیت فرض نمی‌شود. شواهد scanner همان روز: run `42167917939` با ۳۰۰/۳۰۰ صفحه موفق، ۵٬۹۸۶ ردیف محصول، ۹ worker، صفر retry و صفر HTTP 429؛ ۳۲۱ صفحه pending و `completed_cycles=0`. بنابراین full-cycle هنوز اثبات نشده است. ممیزی run `42168017640` فقط ۸ مورد از ۱۵۸ محصول سررسیدشده را بررسی کرد و ۳۳۲/۳۴۴ deadline unresolved ماند.

**شواهد/شناسه:** commit منطق `da2d162bb293bdcc68c3fc605abdcad95eb17c5f`؛ commit تست `d4827632c817db2f2ec6dd868b1a71f9b310b0e2`؛ commit منشور `6e2110ef2cab5859abb24687c2f0613be2a660db`؛ commit handbook `3369500dcf7791712359a47c1c4296dabfa99056`؛ scanner run `42167917939`؛ audit run `42168017640`؛ سابقهٔ shadow run `42073608036`.

**ریسک/بازگشت:** حذف گارد خانواده/برند/شباهت می‌تواند تکرار محتوای هم‌خانواده را بیشتر کند؛ این موضوع فقط باید در گزارش کیفیت دیده شود و نباید محصول دارای تخفیف کمتر را جایگزین کند. بازگشت فنی با revert همین تغییر source/test ممکن است. تغییر روی `main` یا تنظیمات افیلیو/Cloudflare/Secret اعمال نشده و هیچ VPS یا هزینهٔ جدیدی ایجاد نشده است. برای اجبار غیرقابل‌بای‌پس مستندات، Required status check و محدودیت direct push همچنان به دسترسی مالک مخزن نیاز دارد.

**وضعیت:** پیاده‌سازی و مستندسازی روی شاخهٔ کاری؛ منتظر اجرای PR/CI و ادغام کنترل‌شده.

## ۲۰۲۶-۱۱-۰۶ — هم‌راستایی آزمون‌های انتخاب فوری با رتبه‌بندی تخفیف‌اول

**هدف:** حذف انتظارهای باقی‌مانده در آزمون‌ها که محصول دارای تخفیف بالاتر را صرفاً به‌دلیل تکرار خانواده مسدود می‌کردند.

**تغییر/اقدام:** دو آزمون قدیمی urgent selection تغییر نام و اصلاح شدند. اکنون گزینهٔ دارای ۸۲٪ تخفیف حتی با تکرار خانواده بر گزینهٔ جایگزین ۳۵٪ مقدم است و اگر همان گزینه تنها کاندیدا باشد نیز صرفاً به‌دلیل تکرار خانواده رد نمی‌شود. منطق محصول تغییری نکرد؛ این commit فقط قرارداد موردنظر را در تست‌های باقی‌مانده تثبیت می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/test_affilio.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ PR #75 و شاخهٔ discount-first.

**آزمون و نتیجه:** نخستین اجرای suite در PR، ۲ failure از آزمون‌های قدیمی را نشان داد؛ ۹ تست Documentation Gate و آزمون Catalog Sweep موفق بودند. آزمون‌های باقی‌مانده اصلاح شده‌اند و اجرای مجددِ CI هنوز در انتظار نتیجه است؛ موفقیت نهایی ادعا نمی‌شود.

**شواهد/شناسه:** failing runs `42169247526` و PR test run `42170264865`؛ commit اصلاح تست `4779b091bac00cc4a536a1cebd52c141db7f993d`؛ PR `https://github.com/Mehran0960/ai_news_bot/pull/75`.

**ریسک/بازگشت:** این تغییر فقط expectation تست را همسو می‌کند؛ تغییر رفتاری تازه‌ای روی publisher یا main اعمال نمی‌کند. بازگشت با revert همین commit تست ممکن است، اما باعث بازگشت آزمون‌های ناسازگار با تصمیم محصول خواهد شد.

**وضعیت:** اصلاح تست و مستندسازی انجام شد؛ در انتظار rerun و تأیید PR CI.

## ۲۰۲۶-۱۱-۰۶ — ادغام و تأیید CI سیاست discount-first

**هدف:** ثبت وضعیت نهاییِ اعمال تصمیم تخفیف‌اول در شاخهٔ اصلی و بستن مسیر تغییرات PR شمارهٔ ۷۵.

**تغییر/اقدام:** PR #75 با squash merge در `main` ادغام شد. منطق خانواده/برند/شباهت فقط diagnostics تولید می‌کند و دیگر رتبهٔ تخفیف را تغییر نمی‌دهد؛ ترتیب درصد تخفیف نزولی و سپس مبلغ صرفه‌جویی نزولی live است. منشور و handbook نیز از وضعیت «شاخهٔ کاری/در انتظار CI» به وضعیت ادغام‌شده تغییر کردند. دفتر تغییرات همچنان append-only است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ GitHub PR #75 و شاخهٔ `main`.

**آزمون و نتیجه:** روی آخرین commit PR، Catalog Sweep Regression Tests run `42170452852` موفق؛ Top-100 and DigiPay Regression Tests run `42170452832` موفق؛ Documentation Gate run `42170452952` موفق. در run نخست PR دو آزمون قدیمی family cooldown شکست خوردند؛ پس از اصلاح expectationهای ناسازگار، rerunهای فوق موفق شدند. اجرای مستقل Product Radar روی main با run `42170588349` در زمان ثبت این entry هنوز در حال اجراست و موفقیت آن ادعا نمی‌شود.

**شواهد/شناسه:** PR [#75](https://github.com/Mehran0960/ai_news_bot/pull/75)؛ merge commit `36367fe4df27b33ab01ed155adc0d03b557c7fb9`؛ latest PR head `a8fcc924edc79f7845df38088bf8019a5c373ede`؛ CI run IDs: `42170452852`، `42170452832`، `42170452952`، Product Radar main `42170588349`.

**ریسک/بازگشت:** تکرار خانواده/برند/شباهت ممکن است بیشتر شود؛ فقط telemetry آن را گزارش می‌کند و نباید کالای کم‌تخفیف‌تر را جایگزین کند. بازگشت با revert merge commit یا commitهای مربوطه ممکن است. مهم‌تر اینکه scanner هنوز full-cycle را تأیید نکرده و shortlist ۳٬۰۰۰/TTL ۷۲ساعته نیازمند ممیزی است. Required status check و منع direct push نیز همچنان نیازمند تنظیم مالک مخزن است.

**وضعیت:** PR #75 ادغام‌شده؛ سه check اصلی PR موفق؛ Product Radar main در زمان ثبت این entry هنوز pending.

## ۲۰۲۶-۱۱-۰۶ — اصلاح نهایی: حفظ گاردهای ۲۴ساعته خانواده، برند و شباهت

**هدف:** اجرای توضیح تکمیلی و نهایی کاربر: انتخاب بالاترین تخفیف از کل محصولات دیجی‌کالا، اما با حفظ گارد rolling 24h برای خانواده، برند و شباهت معنایی.

**تغییر/اقدام:** تصمیم PR #75 که family/brand/similarity را telemetry-only کرده بود با این قید ناسازگار تشخیص داده شد. در اصلاحیه، ابتدا کنترل‌های سخت و هر سه guard مستقل ۲۴ساعته اعمال می‌شوند؛ candidate مسدودشده کنار گذاشته شده و بالاترین گزینهٔ بعدیِ مجاز بررسی می‌شود. سپس گزینه‌های باقی‌مانده با درصد تخفیف نزولی و در درصد برابر با saving نزولی مرتب/انتخاب می‌شوند. guardها نه score هستند و نه fallback می‌تواند آن‌ها را نادیده بگیرد. guardهای داخل یک batch نیز اعمال می‌شوند. مقدار برند از ۱۲ به ۲۴ ساعت افزایش می‌یابد؛ family و similarity روی ۲۴ ساعت باقی می‌مانند.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/test_affilio.py، README.md، docs/PROJECT_CHARTER_FA.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md؛ شاخهٔ fix/restore-24h-family-brand-similarity-guards-2026-11-06.

**آزمون و نتیجه:** آزمون‌های رگرسیون برای ۲۴ساعته‌بودن هر سه guard، مسدودشدن family/brand/similarity، آزادشدن پس از ۲۴ ساعت، انتخاب گزینهٔ بعدی و عدم تکرار در batch اضافه/اصلاح شدند. اجرای CI روی source/test در حال بررسی است؛ تا دریافت نتیجهٔ واقعی، موفقیت نهایی اعلام نمی‌شود.

**شواهد/شناسه:** PR #75 و merge commit 36367fe4df27b33ab01ed155adc0d03b557c7fb9 به‌عنوان تغییر superseded؛ branch اصلاحی fix/restore-24h-family-brand-similarity-guards-2026-11-06؛ commits source 4db9fe8db5717a80ea6d833eccf2b438b9dea537 و tests 54dd27c8b5f4aac0b1aac8c70ec0c279fce8931b.

**ریسک/بازگشت:** classification خانواده و شباهت عنوان ممکن است بعضی اقلام مستقل را هم‌معنا تشخیص دهد؛ در نتیجه یک گزینهٔ بالاتر ممکن است ۲۴ ساعت کنار گذاشته شود. معیار similarity و taxonomy باید با تست‌های فارسی/لاتین و نمونه‌های واقعی نگهداری شوند. بازگشت فنی با revert commit اصلاحیه ممکن است اما guard brand را دوباره کوتاه یا خاموش می‌کند.

**وضعیت:** کد، آزمون و اسناد اصلاح شده‌اند؛ منتظر CI و merge PR اصلاحی.