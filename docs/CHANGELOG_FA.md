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

## ۲۰۲۶-۱۱-۰۶ — اصلاح تطبیق برند و expectationهای guard

**هدف:** اطمینان از اینکه گارد برند ۲۴ساعته در تاریخچهٔ پایدار به‌درستی با برند کاندیدای تازه تطبیق می‌کند و تست‌ها رفتار مورد انتظار را می‌سنجند.

**تغییر/اقدام:** نرمال‌سازی برند در _publication_diversity_group idempotent شد: brand slug ذخیره‌شده با prefix قبلی دوباره prefix نمی‌گیرد. این نقص باعث می‌شد مقایسهٔ بعضی برندها پس از بازخوانی history بی‌اثر شود. ۱۱ آزمون قدیمی که family/brand/similarity repeat را بی‌مانع می‌دانستند با قرارداد guard ۲۴ساعته همسو شدند؛ آزمون‌های ۲۴ساعتهٔ جدید و آزمون batch حفظ شدند.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/test_affilio.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md؛ شاخهٔ fix/restore-24h-family-brand-similarity-guards-2026-11-06.

**آزمون و نتیجه:** اجرای نخست پس از بازگرداندن guardها ۱۲ failure داشت؛ علت‌ها شامل expectationهای قدیمیِ family/brand/similarity و تطبیق غیر-idempotent brand slug بودند. source و تست‌ها اصلاح و rerun خودکار شروع شده است؛ تا دریافت نتیجهٔ runهای جدید، موفقیت نهایی اعلام نمی‌شود.

**شواهد/شناسه:** source commit 2c492dadf4a0e98d398cb595ac274e970e3aae6c؛ test commit e8b1a047199fdd2b9d0920198680164bfeeddd84؛ نخستین failure runs 42179358861 و 42179365658.

**ریسک/بازگشت:** اصلاح brand normalization ممکن است در داده‌های قدیمی slugهای مختلف را معادل کند؛ تست‌های صریح برند و history باید حفظ شوند. بازگشت با revert source/test commits ممکن است اما گارد brand دوباره از کار می‌افتد.

**وضعیت:** اصلاح کد، تست و مستندسازی انجام شده؛ منتظر نتیجهٔ rerun CI و PR.

## ۲۰۲۶-۱۱-۰۶ — حفظ brand metadata در publication ledger

**هدف:** گارد ۲۴ساعتهٔ برند حتی پس از بازسازی ledger/history یا وقتی نام برند فقط در metadata بوده و در عنوان دیده نمی‌شود، پابرجا بماند.

**تغییر/اقدام:** فیلدهای `brand` و `brand_name` به فیلدهای پایدار publication ledger افزوده شدند. `ensure_recent_publications` اکنون brand صریح را هنگام طبقه‌بندی history لحاظ می‌کند، نه فقط متن عنوان را. regression test جدید، حذف‌نشدن برند metadata-only بعد از ledger/history rebuild و block شدن candidate هم‌برند را بررسی می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ شاخهٔ corrective PR #76.

**آزمون و نتیجه:** پیش از این افزودهٔ تکمیلی، PR #76 سه check اصلی را سبز کرده بود؛ source/test جدید اکنون rerun می‌شوند. تا تأیید rerun تازه، نتیجهٔ این regression جدید را موفق اعلام نمی‌کنیم.

**شواهد/شناسه:** source commit `19405ca12bf2510f72ffa9bd16fa54877ec7e533`؛ test commit `e43ad9c33f1f6bc90aa29cda4743ab751c3d167f`؛ PR #76: https://github.com/Mehran0960/ai_news_bot/pull/76.

**ریسک/بازگشت:** نگهداری brand metadata اندکی فیلدهای publication ledger را گسترش می‌دهد؛ در صورت rollback باید هم ledger و هم history handling بازگردند تا یکپارچگی guard حفظ شود.

**وضعیت:** کد و تست و مستندات ثبت شده‌اند؛ منتظر CI تازهٔ PR #76.

## ۲۰۲۶-۱۱-۰۶ — اصلاح fixture آزمون برند با شناسهٔ SKU معتبر

**هدف:** آزمون حفظ برند صریح در publication ledger باید از شناسه‌ای استفاده کند که با قرارداد واقعی محصول دیجی‌کالا سازگار است.

**تغییر/اقدام:** شناسهٔ ساختگی `dkp-brand-only-metadata` در fixture به `dkp-123456` تغییر یافت. شکست قبلی از ردشدن شناسهٔ غیرمعتبر توسط validator ledger بود، نه از منطق brand persistence. منطق اجرایی تغییر نکرد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/test_affilio.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ شاخهٔ corrective PR #76.

**آزمون و نتیجه:** rerun regression روی fixture معتبر آغاز شده؛ نتیجهٔ تازه هنوز در انتظار است.

**شواهد/شناسه:** commit تست `5642211d8c5cabace63ab31d60e4f242268363a2`؛ PR #76.

**ریسک/بازگشت:** تغییر فقط test fixture است؛ بازگشت با revert commit تست ممکن است.

**وضعیت:** fixture و مستندات اصلاح شدند؛ منتظر CI.

## ۲۰۲۶-۱۱-۰۶ — تکمیل ادغام گاردهای ۲۴ساعته و تأیید نهایی

**هدف:** تثبیت رفتار live مطابق تصمیم نهایی: انتخاب بیشترین تخفیف دیجی‌کالا پس از اعمال گاردهای ۲۴ساعتهٔ خانواده، برند و شباهت؛ در درصد برابر، صرفه‌جویی بیشتر.

**تغییر/اقدام:** PR #76 با squash merge به main ادغام شد. guard واقعی rolling 24h برای هر سه معیار اجرا می‌شود؛ brand cooldown از ۱۲ به ۲۴ ساعت افزایش یافت. برند صریح در publication ledger و recent-publication history حفظ می‌شود؛ brand normalization idempotent است. candidate مسدودشده حذف می‌شود و رتبهٔ بعدیِ مجاز بررسی می‌شود؛ اگر هیچ گزینه‌ای از گاردها نگذرد، انتشار نمی‌شود. همین محدودیت درون batch نیز اعمال می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `README.md`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ PR #76 و شاخهٔ main.

**آزمون و نتیجه:** Catalog Sweep Regression Tests run `42180472166`: success؛ Top-100/DigiPay Regression Tests run `42180472274`: success؛ Documentation Gate run `42180472333`: success. Affilio Product Radar full regression run `42180439592`: `Ran 421 tests`, `OK (skipped=2)`. Log اجرا تعداد blockهای family/brand/similarity و هر سه مقدار cooldown=24h را ثبت کرده است.

**شواهد/شناسه:** PR [#76](https://github.com/Mehran0960/ai_news_bot/pull/76)؛ merge commit `49b13f486d6412806c0c35d74c039c3b7d7cb9bc`؛ source commit `19405ca12bf2510f72ffa9bd16fa54877ec7e533`؛ test fixture commit `5642211d8c5cabace63ab31d60e4f242268363a2`؛ PR runs `42180472166`، `42180472274`، `42180472333`؛ Product Radar `42180439592`.

**ریسک/بازگشت:** گارد خانواده و شباهت ممکن است بعضی اقلام مستقل را هم‌معنا تشخیص دهد؛ در این حالت گزینهٔ بالاتر موقتاً رد می‌شود. پوشش برند به metadata و brand hints متکی است؛ برندهای بی‌نام/بی‌نشانه نیازمند دادهٔ بهتر هستند. بازگشت با revert merge commit ممکن است، اما نباید بدون تصمیم کاربر guardهای ۲۴ساعته حذف شوند.

**وضعیت:** PR #76 ادغام‌شده؛ سه check PR موفق و suite کامل ۴۲۱ تستی Affilio موفق. Full catalog cycle هنوز تکمیل نشده است؛ ادعای «بالاترین تخفیف تمام SKUها در هر لحظه» تا تکمیل پوشش چرخه اثبات‌شده نیست.

## ۲۰۲۶-۱۱-۰۶ — بازیابی Documentation Gate پس از به‌روزرسانی اسناد main

**هدف:** ثبت علت شکست‌های میانی Documentation Gate پس از merge PR #76 و نتیجهٔ بازیابی.

**تغییر/اقدام:** منشور، handbook و changelog پس از merge در سه commit جداگانهٔ main به‌روزرسانی شدند. Gate روی commit منشور `5918160bc160a9be027c4a08738e41f158427740` و commit handbook `7ca50d6c9fd38032459e1c5e86c84e777e23f029` به‌درستی fail شد؛ زیرا هر push به‌تنهایی فاقد handbook یا changelog متناظر بود. سپس changelog append-only با commit `999969f2f32aabf8e63b70dc38d243e8a5af3671` کامل شد و Gate نهایی روی همان commit success داد. این شکست‌ها میان‌راهی بودند؛ check آخرین commit کامل مستندات سبز است.

**فایل‌ها/سامانه‌ها:** `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`، `.github/workflows/offerchin-documentation-gate.yml`.

**آزمون و نتیجه:** Gate run `42180709633` روی منشور-only: failure به‌علت handbook و changelog؛ Gate run `42180795518` روی handbook-only: failure به‌علت changelog؛ Gate run `42180802859` روی آخرین commit مستندات: **success**. ۹ تست validator داخلی در Gate نیز success.

**شواهد/شناسه:** Charter commit `5918160bc160a9be027c4a08738e41f158427740`؛ Handbook commit `7ca50d6c9fd38032459e1c5e86c84e777e23f029`؛ Changelog commit `999969f2f32aabf8e63b70dc38d243e8a5af3671`؛ run IDs `42180709633`، `42180795518`، `42180802859`.

**ریسک/بازگشت:** pushهای مجزای اسناد می‌توانند Gate میانی را fail کنند تا زمانی که بستهٔ کامل مستندات منتشر شود. برای تغییرهای بعدی بهتر است handbook و changelog و در صورت نیاز charter در یک commit اتمی ثبت شوند. این ورودی append-only است و با اصلاح سوابق قبلی انجام نشده است.

**وضعیت:** بازیابی کامل شد؛ Documentation Gate روی آخرین commit main موفق است.

## ۲۰۲۶-۱۱-۰۶ — رفع از دست‌رفتن تغییرهای کاتالوگ در hand-off

**هدف:** جلوگیری از حذف دائمی کارت‌هایی که قبلاً hand-off شده‌اند، اما قیمت، درصد تخفیف یا وضعیت موجودی آن‌ها در اسکن بعدی تغییر کرده است؛ همچنین اطمینان از بررسی زندهٔ سریع‌تر برای محصولی که از قبل در صف کشف ناشر قرار دارد.

**تغییر/اقدام:** پاک‌سازی shortlist اکنون فقط کارت hand-offشده با fingerprint یکسان را حذف می‌کند؛ fingerprint تغییرکرده حفظ می‌شود. hand-off برای SKU موجود در `discovery_queue` نیز پذیرفته می‌شود و merge اطلاعات لیست را به‌روزرسانی کرده، `next_check_at` را پاک و وضعیت `catalog_listing_changed` را ثبت می‌کند تا بررسی عمیق محصول زودتر انجام شود. کارت‌های deferred با fingerprint و زمان retry نگهداری می‌شوند؛ تغییر واقعی fingerprint انتظار deferral را بی‌اثر می‌کند، اما کارت بدون تغییر تا زمان retry کنار می‌ماند. رکوردهای legacy timestamp-only یک بار برای ایجاد fingerprint پایه عبور می‌کنند. این سیگنال هیچ‌گاه جای live validation را نمی‌گیرد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `affilio_radar/test_affilio.py`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** آزمون اختصاصی scanner: run `42182686362` موفق، ۲۹ تست؛ مجموعهٔ Affilio/تحویل: run `42182686280` موفق، ۲۶۳ تست (از جمله تست جدید `test_catalog_listing_change_makes_existing_discovery_queue_item_due_now`)؛ Documentation Gate: run `42182686304` موفق، ۹ تست validator و `implementation_files=8`. مرحلهٔ `py_compile` در workflow نیز بدون خطا گذشت. هر سه check اصلی PR سبز شدند.

**شواهد/شناسه:** شاخهٔ `fix/catalog-handoff-respects-fingerprint-2026-11-06`؛ source commits `6f1b8addbef312443a90f3e77889398e8e0f7b64` و `7609a075f91470dca9094c5a70b2c28e204f92d5`؛ test commits `df5dd2095ecf0a28c06cf0e975c36b476e296e1e`، `99bafe742a2852bffdadadcf98826e1472e0c052` و `269f7a8b3859a51bf77d0984c490af43f45f6efc`.

**ریسک/بازگشت:** تغییر listing ممکن است false positive یا دادهٔ ناقص API باشد؛ بنابراین فقط deep-check را جلو می‌اندازد و نمی‌تواند مستقیماً انتشار ایجاد کند. احتمال افزایش تعداد درخواست‌های صفحهٔ محصول وجود دارد. بازگشت با revert تغییرهای scanner/publisher ممکن است، اما نقص از دست‌رفتن تغییرها دوباره ایجاد می‌شود.

**وضعیت:** کد، regression test و اسناد روی شاخهٔ کاری ثبت شده‌اند؛ منتظر PR، CI و ادغام کنترل‌شده.

## ۲۰۲۶-۱۱-۰۶ — ادغام hand-off حساس به fingerprint و افزایش سرعت چرخهٔ کاتالوگ

**هدف:** اطمینان از اینکه تغییر قیمت/تخفیف/موجودی یک SKU پس از hand-off گم نمی‌شود؛ کاهش زمان بیکاری بین batchهای اسکن و افزایش تعداد صفحه در هر batch، بدون حذف retry یا کاهش پوشش دسته‌ها.

**تغییر/اقدام:** PR #77 با squash در commit `b997cf88cf59f81e5605ccc49f879bd4ee9b9aa6` به `main` ادغام شد؛ hand-off fingerprint-aware و recheck فوری برای SKUهای موجود در discovery queue فعال شد. در بهینه‌سازی throughput، Cloudflare Worker به‌جای یک slot در هر پنج دقیقه، در هر tick یک‌دقیقه‌ای آزادبودن workflow اسکن را بررسی می‌کند؛ قفل workflow مانع overlap است. اندازهٔ batch اسکن از ۳۰۰ به ۴۸۰ صفحه افزایش یافت؛ سقف درخواستی worker همان ۱۲ حفظ شد و backoff خودکار برای 429 دست‌نخورده ماند. Cron Worker همان `* * * * *` باقی می‌ماند؛ زمان‌بندی publisher، Integrity Audit و Filo تغییر نکرد.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ Cloudflare Worker `affilio-minute-dispatcher`.

**آزمون و نتیجه:** مبنای اندازه‌گیری پیش از تغییر: run `42185874004` در ۶ نوامبر، ۲۸۸/۲۸۹ صفحهٔ batch با ۱۰ worker و یک retry/429؛ زمان شروع تا تکمیل job حدود ۷۱ ثانیه و فاصلهٔ dispatch ثابت ۵ دقیقه بود. اجرای scanner روی commit جدید و اندازه‌گیری pages/min، مدت job، retries و rate-limited پس از rollout لازم است؛ بهبود عددیِ واقعی هنوز ادعا نمی‌شود. Documentation Gate و syntax/deployment validation باید پس از PR/deploy ثبت شوند.

**شواهد/شناسه:** PR #77 merge commit `b997cf88cf59f81e5605ccc49f879bd4ee9b9aa6`؛ آخرین snapshot پیش از تغییر `42185874004`؛ branch کاری `perf/catalog-sweep-throughput-2026-11-06`.

**ریسک/بازگشت:** polling یک‌دقیقه‌ای تعداد درخواست‌های GitHub API را بیشتر می‌کند؛ guard فعال‌بودن workflow باعث می‌شود حداکثر یک scan هم‌زمان اجرا شود. batch بزرگ‌تر در صورت latency/429 می‌تواند زمان job را افزایش دهد، اما صفحه‌های ناموفق در صف می‌مانند و checkpoint فقط پس از دریافت نتایج batch ثبت می‌شود. در صورت افزایش خطا یا نزدیک‌شدن به timeout، batch را به ۳۰۰ برگردان و/یا cadence را به slot پنج‌دقیقه‌ای محدود کن؛ هیچ دسته یا صفحه‌ای را حذف نکن.

**وضعیت:** اصلاح کد Worker، ظرفیت workflow و اسناد روی شاخهٔ کاری ثبت شده‌اند؛ منتظر PR، CI، rollout Worker و ارزیابی اجرای بعدی.

## ۲۰۲۶-۱۱-۰۶ — تأیید rollout یک‌دقیقه‌ای dispatcher و اندازه‌گیری نخست

**هدف:** ثبت وضعیت واقعی انتشار تغییر Cloudflare و اولین اثر قابل‌اندازه‌گیری آن بر چرخهٔ اسکن؛ تفکیک ظرفیت تنظیم‌شده از تعداد صفحه‌ای که واقعاً در batch پردازش شد.

**تغییر/اقدام:** PR #78 با squash merge در commit `066548b81c6ec8b8800549cd43e537262204fd22` وارد `main` شد. Worker `affilio-minute-dispatcher` در Cloudflare با deployment ID `a20fdab9edea4cbaab00c2eecc9a0cba` در `2026-11-06T08:22:21Z` به نسخهٔ جدید ارتقا یافت. بررسی آزادبودن scanner اکنون در هر tick یک‌دقیقه‌ای انجام می‌شود؛ قفل workflow مانع هم‌پوشانی است. Cron `* * * * *`، secret bindingهای `GITHUB_TOKEN` و `FILO_GITHUB_TOKEN`، compatibility date، observability و logging حفظ شدند. workflow اسکن حداکثر ۴۸۰ صفحه و ۱۲ worker درخواست می‌کند؛ backoff 429 و retry حفظ شده‌اند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ Cloudflare Worker `affilio-minute-dispatcher`.

**آزمون و نتیجه:** Catalog Sweep Regression run `42187005370`: success؛ Documentation Gate run `42187005410`: success. اولین اجرای پس از merge، run `42187132905`: success؛ ۲۸۴/۲۸۴ صفحه موفق، ۸ worker، صفر retry/429، ۵٬۶۷۳ ردیف محصول، ۲۸۳ صفحهٔ pending؛ زمان job از `08:22:47` تا `08:24:16 UTC` برابر ۸۹ ثانیه بود. صف فقط ۲۸۴ مورد داشت؛ بنابراین ظرفیت ۴۸۰ در این اجرا اشباع نشد. پس از تکمیل همان job در `08:24:16 UTC`، Worker در `08:25:11 UTC` run `42187536920` را dispatch کرد (۵۵ ثانیه بعد)؛ این اجرای دوم در زمان ثبت این ورودی هنوز در حال اجرا بود. `completed_cycles=0`؛ هنوز چرخهٔ کامل به پایان نرسیده است.

**شواهد/شناسه:** PR #78 و merge commit `066548b81c6ec8b8800549cd43e537262204fd22`؛ Cloudflare deployment `a20fdab9edea4cbaab00c2eecc9a0cba`؛ runs `42187005370`، `42187005410`، `42187132905` و `42187536920`.

**ریسک/بازگشت:** بررسی یک‌دقیقه‌ای تعداد فراخوانی‌های GitHub API را افزایش می‌دهد، اما در زمان active بودن workflow فقط وضعیت را می‌خواند و dispatch تکراری نمی‌کند. batch بزرگ‌تر در شرایط کندی API ممکن است زمان job را بالا ببرد؛ retry و checkpoint مانع حذف بی‌صدای صفحه می‌شوند. در صورت افزایش پایدار 429، افت موفقیت یا نزدیک‌شدن به timeout، batch را از ۴۸۰ به ۳۰۰ برگردان و سقف worker را به‌صورت تطبیقی پایین بیاور؛ cadence یک‌دقیقه‌ای و صف صفحات را فقط در صورت شواهد لازم rollback کن.

**وضعیت:** PR #78 ادغام‌شده و Worker روی Cloudflare منتشر و bindingها/cron تأیید شده‌اند؛ اولین batch پس از rollout موفق بوده است. اجرای دوم هنوز در حال اجرا و تکمیل full-cycle همچنان باز است.

## ۲۰۲۶-۱۱-۰۶ — تکمیل اندازه‌گیری دوم پس از rollout

**هدف:** بررسی اینکه dispatcher یک‌دقیقه‌ای پس از آزادشدن scanner دوباره اجرا می‌شود و batch بعدی بدون overlap، retry یا 429 پیش می‌رود.

**تغییر/اقدام:** اجرای دومِ پس از rollout، run `42187536920`، در tick بعدی Worker آغاز شد؛ شروع workflow در `08:25:11 UTC` و شروع job در `08:25:15 UTC` بود، یعنی ۵۵ ثانیه پس از اتمام job قبلی. job در `08:26:27 UTC` با موفقیت تمام شد. فرمان اسکن همچنان ظرفیت حداکثر ۴۸۰ صفحه داشت، اما صف واقعی این batch ۲۸۳ صفحه بود.

**فایل‌ها/سامانه‌ها:** GitHub Actions workflow `.github/workflows/offerchin-digikala-catalog-sweep.yml` و Worker فعال `affilio-minute-dispatcher`؛ state جاری `affilio_radar/catalog_sweep_state.json`.

**آزمون و نتیجه:** run `42187536920`: ۲۸۳/۲۸۳ صفحه موفق، ۹ worker واقعی، صفر retry، صفر HTTP 429، ۵٬۶۴۹ ردیف محصول، ۲۸۲ صفحهٔ pending؛ job ۷۲ ثانیه زمان برد. همراه batch قبلی `42187132905`، مجموعاً ۵۶۷ صفحه در ۱۶۱ ثانیهٔ کاری و بدون retry/429 پردازش شد؛ فاصلهٔ شروع batchها ۱۴۴ ثانیه بود. state پس از اجرا: ۴٬۹۱۷ دسته، ۴٬۶۳۶ دستهٔ تکمیل‌شده، صفر دستهٔ غیرقابل‌دسترسی، ۱۷۱٬۰۰۲ صفحه در چرخهٔ جاری، ۲۸۲ صفحهٔ pending، `completed_cycles=0`. صف باقی‌مانده مربوط به صفحه‌های عمیق ۲۶۳ تا ۲۶۹ برای ۲۸۲ دسته است.

**شواهد/شناسه:** runهای `42187132905` و `42187536920`؛ دومین job ID: `127791334398`؛ state SHA: `1efe4781b9801adb881f96bdb1fd54b6ce5abe40`.

**ریسک/بازگشت:** به‌علت نبود batch کامل ۴۸۰تایی، این اندازه‌گیری سرعت پایدار روی سقف جدید را اثبات نمی‌کند. ادامهٔ polling یک‌دقیقه‌ای باید با شاخص‌های duration، throughput، retries، 429 و timeout پایش شود. full-cycle هنوز کامل نیست؛ افزایش سرعت، پوشش کامل SKUها را به‌تنهایی تضمین نمی‌کند.

**وضعیت:** دومین اجرای rollout موفق؛ اندازه‌گیری اولیه مثبت و بدون خطا؛ full-cycle و آزمایش batch اشباع‌شده هنوز باز هستند.

## ۲۰۲۶-۱۱-۰۶ — کاهش سربار checkout تاریخچه برای اسکن کاتالوگ

**هدف:** کاهش زمان بیکاری غیرمفید jobهای اسکن؛ اندازه‌گیری‌های rollout نشان دادند دریافت کامل تاریخچهٔ Git پیش از اجرای scanner بخش قابل‌توجهی از زمان job را مصرف می‌کند.

**تغییر/اقدام:** مقدار `actions/checkout` در workflow کاتالوگ از `fetch-depth: 0` به `fetch-depth: 20` تغییر داده شد. کد crawler، صف صفحه‌ها، checkpoint، سقف batch=۴۸۰، worker ceiling=۱۲، backoff 429 و retry بدون تغییر باقی ماندند. مرحلهٔ ثبت state همچنان `git pull --rebase origin main`، retry تا سه مرتبه و push را اجرا می‌کند؛ موفقیت آن در اولین workflow واقعی پس از merge شرط حفظ این تغییر است.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** اندازه‌گیری baseline: در jobهای runهای `42187132905` و `42187536920` مرحلهٔ checkout/fetch از حدود ۲۴ تا ۳۴ ثانیه زمان برد؛ در run `42188254294` مرحلهٔ checkout از `08:31:16` تا `08:31:59 UTC`، حدود ۴۳ ثانیه طول کشید، در حالی که scanner summary در `08:32:27 UTC` ثبت شد. CI روی PR لازم است و پس از merge، success مرحلهٔ `Persist resumable page queue and unacknowledged product candidates` و زمان جدید checkout/کل job بررسی خواهد شد. فعلاً هیچ بهبود زمانی ادعا نمی‌شود.

**شواهد/شناسه:** runهای baseline `42187132905`، `42187536920` و `42188254294`؛ branch `perf/shallow-catalog-checkout-2026-11-06`.

**ریسک/بازگشت:** shallow checkout ممکن است در صورت جلو رفتن شاخهٔ main هنگام اجرا، پیدا کردن merge-base برای `git pull --rebase` را دشوار کند. حفظ ۲۰ commit تاریخچه حاشیهٔ امنی برای چند checkpoint هم‌زمان می‌دهد؛ اگر persistence fail یا نیاز به deep history نشان داد، fetch-depth را به ۰ برگردان. هر شکست persist باید با re-run ایمن بازیابی شود؛ queue/checkpoint نباید دستی حذف شود.

**وضعیت:** تغییر روی شاخهٔ کاری ثبت شده؛ منتظر PR/CI و تأیید persistence واقعی پس از merge.

## ۲۰۲۶-۱۱-۰۶ — تأیید shallow checkout و حفظ checkpoint روی main

**هدف:** اطمینان از اینکه کاهش تاریخچهٔ fetch، زمان شروع اسکن را کم می‌کند و در عین حال persistence state و rebase روی main را مختل نمی‌کند.

**تغییر/اقدام:** PR #80 با squash merge در commit `b9b80489fc06ffcc582d3fa4eca7a89f0cfddc81` ادغام شد. workflow اسکن اکنون فقط ۲۰ commit اخیر را checkout می‌کند؛ اسکنر، cursor، batch=۴۸۰، worker ceiling=۱۲، backoff، retry و روش ثبت checkpoint تغییر نکردند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** Catalog Sweep Regression run `42188611652`: success؛ Documentation Gate run `42188611619`: success. اولین اجرای push پس از merge، run `42188770582`: success؛ checkout از `08:36:43` تا `08:36:45.736 UTC` (حدود ۲٫۶۵ ثانیه در برابر حدود ۴۳ ثانیه در run کامل‌تاریخچهٔ `42188254294`). اسکن ۲۸۰/۲۸۰ صفحه موفق با ۷ worker، صفر retry، صفر HTTP 429 و ۵٬۵۸۸ ردیف محصول؛ ۲۷۹ صفحهٔ pending. Job از `08:36:42` تا `08:37:30 UTC` اجرا شد. مرحلهٔ `git pull --rebase origin main` و push checkpoint در تلاش اول موفق بود: `CATALOG_SWEEP_STATE_PERSISTED attempt=1`. State SHA: `db7e79bc6e1a3ce85267d1cc491664fba4d3ac7e`.

**شواهد/شناسه:** PR #80، merge commit `b9b80489fc06ffcc582d3fa4eca7a89f0cfddc81`؛ runهای `42188611652`، `42188611619` و `42188770582`؛ baseline checkout run `42188254294`.

**ریسک/بازگشت:** shallow checkout می‌تواند در صورت رشد سریع تاریخچه و نبود merge-base کافی، rebase را دشوار کند. در اجرای واقعی فعلی، persistence بدون مشکل و در تلاش اول انجام شد. اگر هر اجرای بعدی rebase/push را fail کرد، fetch-depth را به ۰ بازگردان؛ هرگز state یا pending page را حذف نکن.

**وضعیت:** PR #80 ادغام‌شده؛ کاهش محسوس زمان checkout و persistence عملیاتی با موفقیت تأیید شده‌اند. تکمیل full-catalog cycle همچنان جداگانه باید اثبات شود.



## ۲۰۲۶-۱۱-۰۶ — بازیابی dispatcher از اجرای یتیم کاتالوگ و افزودن سنجه‌های throughput

**هدف:** رفع توقف اسکن تمام‌کاتالوگ که با وجود فعال‌بودن Cron یک‌دقیقه‌ای Cloudflare، به‌علت یک workflow run یتیم در GitHub متوقف شده بود؛ هم‌زمان فراهم‌کردن سنجه‌های لازم برای تشخیص گلوگاه واقعی هر batch.

**تغییر/اقدام:** telemetry مربوط به Worker نشان داد invocationها همچنان هر دقیقه اجرا می‌شوند، اما لغو run شمارهٔ 42196544516 به‌طور مکرر با HTTP 409 و پیام Cannot cancel a workflow run that has not been queued yet شکست می‌خورد. endpoint jobs برای این run آرایهٔ خالی برگرداند؛ بنابراین رکورد queued بدون job باعث توقف dispatch بعدی شده بود. روی شاخهٔ کاری، dispatcher فقط در مسیر read-only کاتالوگ پس از گذشت حد stale، وجود job را بررسی می‌کند و فقط اجرای قدیمیِ بدون هیچ job را از قفل dispatch کنار می‌گذارد. گروه concurrency workflow به offerchin-digikala-catalog-sweep-v2 منتقل می‌شود تا run یتیم قبلی قفل قدیمی را نگه ندارد. قفل و رفتار cancellation برای publisher، integrity audit، YouTube، Aparat و Filo تغییر نمی‌کند. در parallel scanner زمان fetch موازی، پردازش و مرتب‌سازی محلی، ذخیرهٔ shortlist و state، نرخ صفحه/ثانیه، نرخ ردیف/ثانیه و اندازهٔ فایل candidates ثبت می‌شود. پوشش تمام دسته‌ها/صفحات، retry، backoff، no-page-depth-cap و رتبه‌بندی discount-first تغییر نمی‌کنند.

**فایل‌ها/سامانه‌ها:** cloudflare/affilio-minute-dispatcher.js، .github/workflows/offerchin-digikala-catalog-sweep.yml، affilio_radar/parallel_catalog_sweep.py، affilio_radar/test_parallel_catalog_sweep.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md؛ Cloudflare Worker affilio-minute-dispatcher.

**آزمون و نتیجه:** شواهد baseline: run سالم 42196432894 با مدت ۶۷ ثانیه؛ run یتیم 42196544516 در وضعیت queued و بدون job؛ telemetry Worker با Cron * * * * * در حال اجرا و cancellation خطادار با HTTP 409. روی شاخه، آزمون‌های regression کاتالوگ باید سنجه‌های جدید را بررسی کنند؛ Node syntax check، Documentation Gate، CI، merge و deploy هنوز در انتظارند و موفقیت آن‌ها فرض نشده است. نتیجهٔ عملیاتی فقط پس از dispatch یک run تازه، ایجاد job، persist موفق checkpoint و مشاهدهٔ سنجه‌های batch ثبت خواهد شد.

**شواهد/شناسه:** runهای تشخیصی 42196432894 و 42196544516؛ Cloudflare deployment فعلی پیش از اصلاح a20fdab9-edea-4cba-ab00-c2eecc9a0cba؛ شاخهٔ کاری fix/offerchin-orphaned-catalog-dispatch-2026-11-06.

**ریسک/بازگشت:** اجرای یتیم قبلی حذف نمی‌شود و ممکن است در Actions باقی بماند؛ گروه concurrency جدید فقط قفل قدیمی را ایزوله می‌کند. bypass فقط برای run قدیمیِ بدون job و فقط در scanner مجاز است؛ اگر بررسی jobs خطا دهد یا حتی یک job وجود داشته باشد، dispatcher مسیر محافظه‌کارانه را ادامه می‌دهد. سایر مسیرهای انتشار به‌هیچ‌وجه از اجرای active عبور نمی‌کنند. rollback با بازگرداندن گروه concurrency قدیمی و نسخهٔ قبلی Worker/dispatcher ممکن است؛ در صورت تکرار HTTP 409 روی runهای بدون job، پاک‌سازی سمت GitHub ممکن است به پشتیبانی GitHub نیاز داشته باشد.

**وضعیت:** تغییرات روی شاخهٔ کاری انجام شده؛ PR، آزمون CI، merge، rollout Worker و تأیید اجرای تازه هنوز انجام نشده‌اند.


## ۲۰۲۶-۱۱-۰۶ — اصلاح regex مسیر GitHub Actions در Cloudflare Worker

**هدف:** رفع خطای validation نحوی که در نخستین upload نسخهٔ dispatcher اصلاح‌شده توسط Cloudflare گزارش شد؛ جلوگیری از هرگونه ادعای نادرست دربارهٔ فعال‌شدن deployment.

**تغییر/اقدام:** PR #82 در main ادغام شد و دو check مربوط به Catalog Sweep Regression و Documentation Gate موفق بودند. نخستین تلاش upload Worker با HTTP 400 و کد validation 10021 رد شد؛ پیام Cloudflare برابر Invalid regular expression flags و محل خطا worker.js:70:30 بود. علت، escape نادرست slash در regular expression تبدیل مسیر workflow بود. در شاخهٔ اصلاحی، expression به escaped slash استاندارد JavaScript اصلاح شد. این تغییر فقط نحو را اصلاح می‌کند؛ رفتار catalog-only برای run قدیمیِ بدون job، concurrency group نسخهٔ دوم، Cron و سیاست‌های انتشار تغییر تازه‌ای نمی‌گیرند. Worker نسخهٔ قبلی را حفظ کرده است.

**فایل‌ها/سامانه‌ها:** cloudflare/affilio-minute-dispatcher.js، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md؛ Cloudflare Worker affilio-minute-dispatcher.

**آزمون و نتیجه:** Cloudflare upload نخست به‌درستی رد شد و هیچ نسخهٔ جدیدی فعال نشد. شاخهٔ اصلاحی باید از Node syntax validation و Documentation Gate عبور کند؛ upload موفق، deployment ID جدید، حفظ bindingها و Cron و telemetry پس از deploy هنوز در انتظارند.

**شواهد/شناسه:** PR #82 merge commit 98c4195c616476c574beea15dbfc29c8cd7a8c0f؛ upload rejection با HTTP 400 / error 10021؛ نسخهٔ فعال قبلی a20fdab9-edea-4cba-ab00-c2eecc9a0cba؛ branch fix/offerchin-worker-regex-syntax-2026-11-06.

**ریسک/بازگشت:** تا پایان syntax validation و upload تأییدشده، Worker فعال قبلی حفظ می‌شود. اگر upload اصلاح‌شده رد شود، از deploy اجباری یا حذف binding استفاده نشود؛ محتوای Worker و settings فعال دوباره fetch و بررسی شوند. rollback با حفظ نسخهٔ 100 درصدی قبلی در deployment history ممکن است.

**وضعیت:** regex در شاخهٔ اصلاحی تغییر کرده و مستندات ثبت شده‌اند؛ PR، CI، upload و deployment هنوز انجام نشده‌اند.


## ۲۰۲۶-۱۱-۰۶ — بازیابی dispatch کاتالوگ و استقرار کنترل‌شدهٔ Worker

**هدف:** رفع توقف چرخهٔ کامل اسکن کاتالوگ دیجی‌کالا، جلوگیری از قفل‌شدن دوباره توسط اجرای یتیم GitHub Actions و ساخت مسیر استقرار قابل‌آزمون برای dispatcher؛ بدون کاهش پوشش کاتالوگ یا دست‌زدن به زمان‌بندی انتشار کانال‌ها.

**تغییر/اقدام:** اجرای یتیم `42196544516` (run شمارهٔ 1093) بررسی شد؛ وضعیت آن `queued` و فهرست jobهایش خالی بود. concurrency group اسکن از `offerchin-digikala-catalog-sweep-v2` به `v3` تغییر کرد تا run یتیم قدیمی مانع batch تازه نشود. مقایسهٔ Worker مخزن با نسخهٔ سالم Cloudflare #31 علت واقعی خطای build را آشکار کرد: بدنهٔ `dispatchWorkflowIfIdle` در main ناقص و درخواست `POST /dispatches` به‌همراه آکولاد پایانی حذف شده بود. همان منطق dispatch از نسخهٔ سالم بازیابی شد و bypass اجرای یتیم فقط برای catalog و تنها پس از بررسی stale بودن و صفر بودن jobها حفظ شد. پیکربندی Wrangler و workflow استقرار CI اضافه شد؛ entrypoint موقت MJS از سورس canonical ساخته می‌شود، `node --check` اجرا می‌شود و سپس dry-run/deploy رسمی Wrangler انجام می‌گیرد. `keep_vars = true` و عدم ثبت مقدار Secretها در مخزن حفظ شد. چند فرضیهٔ اولیه دربارهٔ پسوند ES Module و bundling در آزمایش رد شدند و در این ثبت، علت قطعی به‌عنوان نقص ساختاری خود Worker ثبت شده است.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `.github/workflows/deploy-affilio-minute-dispatcher.yml`، `cloudflare/wrangler.toml`، `cloudflare/affilio-minute-dispatcher.js`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ GitHub Actions و Cloudflare Worker با نام `affilio-minute-dispatcher`.

**آزمون و نتیجه:** آخرین batch سالم پیش از اصلاح، 256 از 256 صفحه را در 293.59 ثانیه پردازش کرد؛ 8 worker مؤثر، صفر retry و صفر HTTP 429 داشت. زمان fetch شبکه 293.275 ثانیه و پردازش محلی فقط 0.214 ثانیه بود؛ بنابراین گلوگاه شبکه است و افزایش کورکورانهٔ concurrency توجیه ندارد. پس از بازیابی بدنهٔ تابع، Wrangler 4.158.0 در PR dry-run موفق شد و bundle با حجم 16.35 KiB (gzip: 4.85 KiB) ساخته شد؛ آزمون رگرسیون اسکنر نیز در PR موفق بود. اجرای syntax check مستقل به pipeline افزوده شده است. در زمان ثبت این changelog، dry-run و تست رگرسیون تأیید شده‌اند؛ نتیجهٔ نهایی Documentation Gate، merge، deployment واقعی Worker، حفظ bindingهای Secret/Cron و اجرای تازهٔ scanner باید جداگانه بررسی شود. چرخهٔ کامل کاتالوگ هنوز تکمیل‌شده محسوب نمی‌شود.

**شواهد/شناسه:** GitHub orphan run `42196544516`؛ آخرین batch سالم `42212336045`؛ Wrangler dry-run موفق `42243528096`؛ Catalog Sweep Regression موفق `42243528021`؛ PR شمارهٔ `84` در `https://github.com/Mehran0960/ai_news_bot/pull/84`؛ نسخهٔ فعال قبلی Cloudflare Worker شمارهٔ `31` با شناسهٔ `a20fdab9-edea-4cba-ab00-c2eecc9a0cba`.

**ریسک/بازگشت:** تا قبل از موفقیت تمام checkها، merge و تأیید deployment، Worker نسخهٔ 31 و تنظیمات فعال آن مرجع production باقی می‌ماند. اگر Secretهای `CLOUDFLARE_API_TOKEN` یا `CLOUDFLARE_ACCOUNT_ID` وجود نداشته باشند یا مجوز Workers Scripts Write کافی نباشد، deploy باید fail شود و نسخهٔ فعال تغییر نکند. run یتیم گروه v2 حذف یا force-cancel نشده؛ گروه v3 فقط مانع مسدودشدن اجرای جدید را جدا می‌کند. تغییرات publisher، audit، YouTube، Aparat و Filo و همچنین سقف batch برابر 480، سقف درخواستی 12 worker، retry/backoff و رتبه‌بندی discount-first دست‌نخورده‌اند.

**وضعیت:** اصلاح کد و workflow روی شاخهٔ `fix/offerchin-dispatcher-production-recovery-2026-11-06` و در PR شمارهٔ 84 ثبت شده است. dry-run و regression test موفق‌اند؛ production deployment و تکمیل چرخهٔ کامل هنوز تأیید نشده‌اند.


## ۲۰۲۶-۱۱-۰۶ — تثبیت حساب مقصد در Cloudflare deployment workflow

**هدف:** رفع ابهام حساب مقصد در CI پس از ردشدن deploy توسط Cloudflare، بدون تغییر Token محرمانه یا مختل‌کردن Worker فعال.

**تغییر/اقدام:** اجرای production deploy پس از ادغام PR شمارهٔ 84، dry-run را گذراند ولی Cloudflare برای `/workers/services/affilio-minute-dispatcher` خطای `No access to the specified service` برگرداند. حساب حاوی Worker از اتصال Cloudflare با شناسهٔ عمومی `10dc992b8d84b77f509975e21ce5499d` تأیید شد؛ این شناسه در `cloudflare/wrangler.toml` به‌عنوان `account_id` ثابت شد و وابستگی workflow به Secret غیرقابل‌راستی‌آزمایی `CLOUDFLARE_ACCOUNT_ID` حذف شد. تنها Secret باقی‌مانده `CLOUDFLARE_API_TOKEN` است.

**فایل‌ها/سامانه‌ها:** `cloudflare/wrangler.toml`، `.github/workflows/deploy-affilio-minute-dispatcher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ GitHub Actions و Cloudflare Worker `affilio-minute-dispatcher`.

**آزمون و نتیجه:** deploy run شمارهٔ `42244114866` syntax check و Wrangler dry-run را با موفقیت گذراند، اما مرحلهٔ انتشار را با `No access to the specified service` رد کرد. تغییر جدید باید ابتدا در PR با dry-run و Documentation Gate تأیید شود؛ پس از merge، deploy تازه نتیجهٔ قطعی را مشخص می‌کند.

**شواهد/شناسه:** PR ادغام‌شدهٔ قبلی `#84`؛ Cloudflare account id `10dc992b8d84b77f509975e21ce5499d`؛ deploy run `42244114866`؛ version فعال پیش از تغییر `31` با id `a20fdab9-edea-4cba-ab00-c2eecc9a0cba`.

**ریسک/بازگشت:** Account ID شناسهٔ عمومی حساب است و Secret محسوب نمی‌شود؛ Token محرمانه باقی می‌ماند. اگر انتشار پس از تثبیت حساب همچنان رد شود، دسترسی `Workers Scripts Edit/Write` برای API Token باید بررسی شود. نسخهٔ فعال تا زمان تأیید deployment دست‌نخورده باقی می‌ماند؛ در صورت شکست، نسخهٔ 31 مرجع rollback است.

**وضعیت:** تغییرات در شاخهٔ `fix/cloudflare-account-target-for-offerchin-dispatcher` آمادهٔ بررسی CI هستند؛ هنوز deployment جدید انجام نشده است.


## ۲۰۲۶-۱۱-۰۶ — افزایش کنترل‌شدهٔ throughput اسکنر کاتالوگ

**هدف:** کاهش زمان پیمایش کامل کاتالوگ دیجی‌کالا، بدون حذف هیچ دسته یا عمق صفحه و بدون آسیب‌زدن به پایداری API.

**تغییر/اقدام:** baseline آخرین run بررسی شد: `42244114680`، شامل ۲۵۶ صفحهٔ موفق، صفر retry و صفر پاسخ 429؛ زمان شبکه ۲۵۶٫۸۳۶ ثانیه بود و مجموع پردازش محلی و ذخیره‌سازی کمتر از نیم ثانیه. همچنین مشخص شد `parallel_workers_used` بعد از تنظیم ظرفیت اجرای بعدی نوشته می‌شد و تعداد workerهای batch جاری را دقیق نشان نمی‌داد. این telemetry اصلاح شد. سقف درخواستی workerها از ۱۲ به ۱۶ افزایش یافت؛ ظرفیت به‌صورت تطبیقی بالا می‌رود، هر 429 منفرد یک worker از ظرفیت بعدی کم می‌کند و سه یا بیشتر آن را نصف می‌کند. batch=۴۸۰، timeout=۱۲ دقیقه، صف durable و رتبه‌بندی discount-first دست‌نخورده ماندند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`؛ GitHub Actions.

**آزمون و نتیجه:** دو regression test جدید برای صحت شمارش workerهای واقعی و backoff پس از یک 429 افزوده شد. اجرای مجموعهٔ تست‌ها روی PR باید نتیجهٔ قطعی را مشخص کند؛ هنوز نتیجهٔ CI یا بهبود throughput پس از تغییر ثبت نشده است.

**شواهد/شناسه:** baseline run `42244114680`؛ `fetch_s=256.836`، `process_s=0.323`، `candidate_write_s=0.103`، `state_write_s=0.028`؛ snapshot دارای ۲۵۵ صفحهٔ در انتظار و `completed_cycles=0`.

**ریسک/بازگشت:** افزایش concurrency می‌تواند نرخ 429 را بالا ببرد؛ backoff با هر 429 فعال می‌شود و برای burstهای سه‌تایی یا بیشتر ظرفیت را نصف می‌کند. در صورت افت نرخ موفقیت یا افزایش retry، سقف workflow را به ۱۲ یا مقدار پایین‌تر برمی‌گردانیم. هیچ دست‌کاری در محدودیت‌های سمت دیجی‌کالا انجام نمی‌شود.

**وضعیت:** تغییرات روی شاخهٔ `perf/offerchin-catalog-throughput-20261106` ثبت می‌شوند؛ ادغام، تست نهایی CI و اثبات بهبود سرعت در اجرای زنده هنوز انجام نشده‌اند.
