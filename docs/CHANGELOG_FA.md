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

## ۲۰۲۶-۱۱-۱۱ — یکسان‌سازی ترتیب و منبع انتخاب در انتشار چندرسانه‌ای

**هدف:** تضمین اینکه ویدئوهای OfferChin دقیقاً از محصولات انتخاب‌شده و اعتبارسنجی‌شدهٔ مسیر اصلی کانال‌ها ساخته شوند؛ نه از یک مسیر کشف/رتبه‌بندی موازی.

**تغییر/اقدام:** مرتب‌سازی صف‌های ویدئویی YouTube، Aparat و Filo از رتبه‌بندی مستقل تخفیف به FIFO بر پایهٔ زمان تحویل کانالی تغییر کرد. گیت ساخت ویدئو اکنون فقط موفقیت مقصدهای تصویری Telegram/Bale/Rubika/Eitaa را می‌پذیرد و موفقیت ویدئویی به‌تنهایی مجوز ایجاد همراه ویدئویی جدید نیست. قرارداد انتخاب مشترک و مسیرهای مجزای تحویل در سند مرجع ثبت شد؛ workflowهای هر مقصد نیز به تست مشترک متصل شدند. این تغییر cadence و سهمیهٔ اختصاصی هر رسانه را تغییر نمی‌دهد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_shared_selection_media_routing.py`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/affilio-radar.yml`، workflowهای Filo/YouTube/Aparat، `README.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`.

**آزمون و نتیجه:** شش آزمون جدید برای FIFO همهٔ مقصدهای ویدئویی، حفظ ترتیب انتخاب کانالی، tie-break قطعی و الزام تحویل موفق کانالی اضافه و به CI متصل شده‌اند؛ نتیجهٔ اجرای GitHub Actions پس از push ثبت می‌شود.

**شواهد/شناسه:** تغییر کد اولیه `d7efe597141b5895c6483356290834d98382568d`؛ فایل آزمون `c3e414e4c982115c2132aa7a4d3f406adf38df81`. اجرای CI: در انتظار تکمیل.

**ریسک/بازگشت:** در صورت افت throughput ویدئو ممکن است تعدادی hand-off به‌علت محدودیت ۲۴ساعتهٔ تازگی یا quota مقصد منقضی شوند؛ سیستم نباید برای جبران، محصولی را با انتخاب مستقل جایگزین کند. rollback با revert تغییر FIFO در `affilio_radar.py` ممکن است؛ فایل‌های state و صف جاری نباید reset شوند.

**وضعیت:** تغییر منطق و مستندات انجام‌شده؛ تأیید نهایی CI در انتظار.

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


## ۲۰۲۶-۱۱-۰۶ — اثبات عملی سرعت اسکن و تشخیص مانع dispatcher

**هدف:** اعتبارسنجی throughput پس از بهینه‌سازی اسکنر، تعیین وضعیت واقعی چرخهٔ کامل و رفع تداوم dispatch کاتالوگ بدون ریسک‌کردن credentialها.

**تغییر/اقدام:** PR شمارهٔ 86 ادغام شد. اسکنر run شمارهٔ 1096 را با ۲۵۵/۲۵۵ صفحهٔ موفق، صفر retry، صفر HTTP 429، ۹ worker واقعی و `fetch_s=25.324` به پایان رساند؛ run قبلی #1095 برای batch تقریباً هم‌اندازه `fetch_s=256.836` داشت. checkpoint با موفقیت ثبت شد. بررسی مستقیم Cloudflare نشان داد Worker نسخهٔ 31 هنوز Cron یک‌دقیقه‌ای دارد، اما به علت تلاش برای cancel کردن یک run که GitHub هنوز queue نکرده، در مسیر اسکن کاتالوگ HTTP 409 می‌گیرد. سورس main حاوی guard اصلاحی است ولی deploy واقعی به علت `No access to the specified service` رد شد. راهنمای deploy در این تغییر به نقش مستندشدهٔ Workers Editor اصلاح شد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/deploy-affilio-minute-dispatcher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ GitHub Actions و Cloudflare Worker.

**آزمون و نتیجه:** run #1096 موفق بود؛ هر ۳۱ تست scanner در workflow اجرا شدند. publisher run #2875 و Integrity Audit run #3121 نیز پس از dispatch زمان‌بندی‌شده با موفقیت تکمیل شدند. بااین‌حال، اسکن چرخه هنوز ۲۵۵ صفحهٔ pending و `completed_cycles=0` دارد. deploy Worker هنوز ناموفق است و باید پس از اصلاح مجوز Token دوباره اجرا شود.

**شواهد/شناسه:** PR #86 و merge commit `049cc45f2fed0fc89f25979d6a738200495aff85`؛ scan run `42246038180`؛ checkpoint commit `92d861a187e7b507509080f134e0ec66386d5404`؛ state: ۴٬۹۱۷ دسته، ۴٬۶۷۱ برگ، ۱۸۶٬۵۶۵ صفحهٔ موفق در چرخه، ۲۵۵ صفحهٔ pending؛ deploy run `42244812744`؛ Cloudflare version 31.

**ریسک/بازگشت:** افزایش concurrency بدون نظارت می‌تواند نرخ 429 را افزایش دهد؛ backoff تطبیقی برقرار است. deploy مستقیم نسخهٔ ۳۴ انجام نشد، چون صرفاً annotation و binding metadata برای اثبات صحت کد کافی نیست. Worker نسخهٔ ۳۱ و secret bindingهای آن تا زمان مجوز deploy صحیح دست‌نخورده می‌مانند.

**وضعیت:** اسکنر جدید روی main فعال و یک اجرای واقعی موفق دارد؛ رفع باگ زمان‌بند در سورس main است اما deployment production به‌علت نبود Workers Editor در Token فعلی مسدود است. اقدام نهایی نیازمند جایگزینی Secret `CLOUDFLARE_API_TOKEN` با Account-owned Token دارای Workers Editor برای همین Worker و اجرای مجدد workflow است.


## ۲۰۲۶-۱۱-۰۶ — اسنپ‌شات کامل کاتالوگ و حفظ پیوستگی انتشار

**هدف:** رتبه‌بندی نامزدها از یک پیمایش کامل و بدون شکاف کاتالوگ، بدون تحمیل یک چرخهٔ چندساعتهٔ تازه بین هر دو پست.

**تغییر/اقدام:** اسکنر پس از یک چرخهٔ کامل، بدون دستهٔ غیرقابل‌جست‌وجو و با پوشش ۱۰۰٪، اسنپ‌شات immutable نامزدهای برتر را همراه با شواهد پوشش، شناسهٔ همهٔ دسته‌ها، تعداد صفحهٔ موفق و رتبهٔ جهانی ذخیره می‌کند. نشانگر کوچک وضعیت، اسنپ‌شات آخرین چرخهٔ سالم را مستقل از آخرین تلاش اسکن نگه می‌دارد؛ در نتیجه چرخهٔ بعدی می‌تواند در حال اجرا باشد یا با شکاف پایان یابد، بی‌آنکه اسنپ‌شات سالم قبلی را از بین ببرد. Cloudflare Worker همان اسنپ‌شات را در slotهای متوالی ۱۷ دقیقه‌ای بازاستفاده می‌کند و به چرخهٔ کامل جدید بین هر دو انتشار نیاز ندارد. فقط در warm-up اولیه، تا پیش از وجود هر اسنپ‌شات کامل، مسیرهای کشف زندهٔ قبلی مجازند ادامه پیدا کنند؛ ناسازگاری یا خرابی اسنپ‌شات موجود به fallback باز نمی‌گردد و fail-closed باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/catalog_status_snapshot.py`، تست‌های اسکنر و status snapshot، `cloudflare/affilio-minute-dispatcher.js` و تست Node آن، handbook، GitHub Actions و Worker `affilio-minute-dispatcher`.

**آزمون و نتیجه:** پس از این اصلاح، تست‌های Python، Node و Wrangler باید دوباره اجرا شوند؛ نتیجهٔ قطعی در PR شمارهٔ ۸۸ ثبت می‌شود. تا پیش از اجرای سبز CI، این تغییر تأییدشده یا deploy‌شده محسوب نمی‌شود.

**شواهد/شناسه:** PR شمارهٔ ۸۸؛ شاخهٔ `feat/offerchin-publish-only-after-full-catalog-sweep`. SHA و run ID نهایی پس از CI ثبت می‌شود.

**ریسک/بازگشت:** اگر دسته‌ای غیرقابل‌دسترسی یا اسنپ‌شات نامعتبر باشد، انتشار بر پایهٔ آن اسنپ‌شات متوقف می‌شود؛ warm-up فقط برای حالتی است که هنوز هیچ اسنپ‌شات قبلی وجود ندارد. کنترل زندهٔ قیمت/موجودی و گاردهای تکرار مستقل باقی می‌مانند. rollback با revert تغییرات PR و بازگرداندن Worker قبلی ممکن است.

**تکمیل اصلاحات در PR:** فایل snapshot نهایی اکنون همراه status marker در Git stage می‌شود؛ Python ناشر hash، پوشش دسته‌ها، عمر حداکثر ۹۶ ساعته و عضویت/rank هر نامزد را دوباره بررسی می‌کند. در `selection_only` وضعیت نامعتبر اجازهٔ انتخاب تازه نمی‌دهد و publisher نیز پیش از ارسال صف، عضویت محصول را با snapshot فعال تطبیق می‌دهد. مسیر warm-up فقط پیش از اولین snapshot معتبر مجاز است؛ SnapShop همچنان یک مسیر جداگانه با کنترل زنده دارد.

**وضعیت:** اصلاحات در شاخهٔ PR شمارهٔ ۸۸ پیاده‌سازی شده و منتظر اجرای CI نهایی و ادغام هستند؛ merge، deploy و اثبات یک چرخهٔ کامل سالم در production هنوز انجام نشده است.


## 2026-11-07 — گسترش آزمایشی پیام‌رسان‌ها

- افزودن آداپتور مستقل انتشار تصویری روبیکا بر پایه Bot API رسمی و مسیر آپلود تصویر.
- افزودن آداپتور آزمایشی ایتا از مسیر ایتایار، با خاموشی پیش‌فرض و ثبت رسید API در صورت نبود شناسه پیام.
- افزودن روبیکا و ایتا به رجیستری مقصدها، بدون تغییر منطق کشف و رتبه‌بندی محصول.
- افزودن کلیدهای فعال‌سازی مستقل؛ تا زمان افزودن Secretها و فعال‌کردن Variableها هیچ ارسال جدیدی به این دو مقصد انجام نمی‌شود.
- نگهداری شناسه‌های واقعی و رسیدهای API در فیلدهای جداگانه؛ بدون جعل شناسه پیام.
- افزودن آزمون‌های mock برای مسیر روبیکا، پذیرش ایتایار و رد لینک نامعتبر.


**هدف:** اضافه‌کردن کانال‌های انتشار بیشتر با هزینهٔ نزدیک به صفر، بدون وابستگی به سرویس تجمیع‌گر و بدون اثر منفی بر تلگرام و بله.

**تغییر/اقدام:** ثبت روبیکا و ایتا به‌عنوان مقصد تصویری مستقل؛ پیاده‌سازی آپلود سه‌مرحله‌ای تصویر و ارسال با Bot API روبیکا؛ افزودن مسیر آزمایشی ایتایار با opt-in صریح؛ تفکیک شناسهٔ واقعی پیام از رسید پذیرش API؛ نگهداری وضعیت هر مقصد در صف مستقل؛ خاموش‌بودن هر دو مقصد تا زمان افزودن Secretها و Variableهای فعال‌سازی.

**فایل‌ها/سامانه‌ها:** affilio_radar/platform_registry.py، affilio_radar/publisher.py، affilio_radar/affilio_radar.py، affilio_radar/messenger_adapters.py، affilio_radar/test_messenger_adapters.py، .github/workflows/offerchin-publisher.yml، .github/workflows/offerchin-messenger-adapter-tests.yml، راهنمای توسعه پیام‌رسان‌ها و دفترچهٔ پروژه.

**آزمون و نتیجه:** آزمون اختصاصی آداپتورها و آزمون رگرسیون کاتالوگ موفق شدند؛ یک assertion قدیمی در آزمون صف به‌دلیل افزایش مقصدهای تصویری از دو به چهار به‌روزرسانی شد و منتظر اجرای مجدد CI است. هیچ درخواست واقعی انتشار اجرا نشد.

**شواهد/شناسه:** Pull Request شمارهٔ ۸۹؛ شاخهٔ feat/free-messenger-adapters؛ Bot API رسمی روبیکا: https://rubika.ir/botapi/methods ؛ مستند عمومی ایتا دربارهٔ اعتبار ۵۰هزار پیام مربوط به API برنامه به کاربر است و نه اثبات رایگان‌بودن انتشار کانالی ربات.

**ریسک/بازگشت:** روبیکا و ایتا به‌صورت پیش‌فرض خاموش‌اند؛ با خاموش‌کردن Variableهای RUBIKA_ENABLE_PUBLISHING و EITAA_ENABLE_PUBLISHING می‌توان ارسال را متوقف کرد. ایتا تا تأیید تعرفه و رفتار API در حالت آزمایشی باقی می‌ماند. حذف مقصدها از Registry، کد آداپتور و متغیرها، بازگشت کامل را ممکن می‌کند.

**وضعیت:** پیاده‌سازی در PR پیش‌نویس است؛ ادغام با main، ثبت Secretها، فعال‌سازی کانال‌ها و اثبات انتشار عمومی هنوز انجام نشده است.


## 2026-11-07 — کشف خودکار شناسه کانال روبیکا

**هدف:** استخراج شناسه واقعی کانال OfferChin از پیام آزمایشی، بدون مشاهده یا افشای توکن و بدون ارسال پیام تازه.

**تغییر/اقدام:** افزودن ابزار read-only مبتنی بر getMe، getUpdates و getChat؛ تطبیق دقیق username=offerchin و نوع چت Channel؛ رد تطبیق عنوانی؛ جلوگیری از چاپ متن پیام‌ها؛ افزودن workflow خودکار پس از ادغام، آزمون در Pull Request و امکان اجرای دستی مجدد.

**فایل‌ها/سامانه‌ها:** scripts/discover_rubika_channel.py، scripts/test_discover_rubika_channel.py، .github/workflows/rubika-channel-discovery.yml، affilio_radar/MESSENGER_EXPANSION_FA.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md.

**آزمون و نتیجه:** آزمون‌های واحد برای تطبیق نام کاربری، نوع کانال، حذف شناسه‌های تکراری و رد چت خصوصی اضافه شده‌اند؛ نتیجه اجرای زنده پس از دسترسی workflow به RUBIKA_BOT_TOKEN گزارش می‌شود. ابزار هیچ پیام عمومی ارسال نمی‌کند.

**شواهد/شناسه:** مستند رسمی روبیکا درباره getUpdates، getChat و مدل‌های Update و Chat: https://rubika.ir/botapi/methods و https://rubika.ir/botapi/models ؛ نام کاربری هدف: offerchin.

**ریسک/بازگشت:** توکن فقط به‌عنوان GitHub Actions Secret در محیط اجرا مصرف می‌شود و چاپ نمی‌شود. اگر دریافت همه پیام‌های کانال در BotFather فعال نباشد، ممکن است پیام آزمایشی در updateها دیده نشود؛ در آن صورت پس از فعال‌سازی، پیام تازه لازم است. حذف workflow و script بازگشت را انجام می‌دهد.

**وضعیت:** پیاده‌سازی در PR عملیاتی است؛ شناسه کانال هنوز از API استخراج و در تنظیمات ناشر ثبت نشده و انتشار روبیکا خاموش باقی می‌ماند.


## 2026-11-07 — ثبت شناسهٔ واقعی کانال روبیکا در ناشر

**هدف:** حذف نیاز به ثبت دستی شناسهٔ کانال و آماده‌کردن اتصال ناشر روبیکا بدون افشای دادهٔ محرمانه.

**تغییر/اقدام:** ثبت chat_id تأییدشدهٔ کانال offerchin به‌عنوان مقدار پیش‌فرض غیرمحرمانه در workflow ناشر؛ امکان override از طریق Actions Variable؛ حفظ RUBIKA_BOT_TOKEN به‌عنوان Secret؛ حفظ RUBIKA_ENABLE_PUBLISHING در حالت خاموش تا اجازهٔ فعال‌سازی.

**فایل‌ها/سامانه‌ها:** .github/workflows/offerchin-publisher.yml، affilio_radar/MESSENGER_EXPANSION_FA.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** اجرای Rubika Channel ID Discovery با موفقیت انجام شد؛ API نام کاربری offerchin، عنوان «آفِرچین»، نوع Channel و chat_id را تأیید کرد. اجرای تشخیصی هیچ پیامی ارسال نکرد. فعال‌سازی انتشار همچنان انجام نشده است.

**شواهد/شناسه:** workflow run شمارهٔ ۵ به شناسهٔ 42337335090؛ job شمارهٔ 128297122528؛ chat_id=c0EH9WW0c7fa831d965d050233b7ab35؛ Pull Request شمارهٔ ۹۰.

**ریسک/بازگشت:** شناسهٔ کانال دادهٔ عمومی است؛ توکن در Secret باقی می‌ماند. برای تغییر مقصد می‌توان Actions Variable به نام RUBIKA_CHANNEL_ID تعریف کرد یا مقدار پیش‌فرض workflow را تغییر داد. ارسال ناخواسته با خاموش نگه‌داشتن RUBIKA_ENABLE_PUBLISHING جلوگیری می‌شود.

**وضعیت:** شناسه در ناشر تنظیم شده است؛ انتشار روبیکا هنوز خاموش است و هیچ پست تبلیغاتی به کانال ارسال نشده است.


## 2026-11-07 — فعال‌سازی انتشار OfferChin در روبیکا

**هدف:** فعال‌کردن مقصد روبیکا برای انتشار محصولات منتخب صف OfferChin و پشتیبانی از نام متغیر شناسه‌ای که در تنظیمات مخزن ثبت شده است.

**تغییر/اقدام:** نگاشت RUBIKA_CHAT_ID از Secret یا Actions Variable به متغیر محیطی RUBIKA_CHANNEL_ID که آداپتور فعلی انتظار دارد؛ حفظ سازگاری با RUBIKA_CHANNEL_ID قدیمی و شناسهٔ کانال تأییدشده به‌عنوان fallback؛ روشن‌کردن انتشار به‌صورت پیش‌فرض با امکان توقف فوری از طریق RUBIKA_ENABLE_PUBLISHING=false؛ محدودکردن push-trigger ناشر به شاخهٔ main تا commitهای شاخه‌های کاری ناخواسته چرخهٔ انتشار را آغاز نکنند.

**فایل‌ها/سامانه‌ها:** .github/workflows/offerchin-publisher.yml، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md، آداپتور موجود در affilio_radar/messenger_adapters.py.

**آزمون و نتیجه:** آزمون رگرسیون Top-100 و DigiPay برای PR شمارهٔ ۹۲ موفق شد. Documentation Gate در اجرای نخست به‌درستی به‌علت نبود این دو سند رد شد؛ این commit آن الزام را برطرف می‌کند و Gate باید روی commit به‌روزشده دوباره اجرا شود. انتشار عمومی روبیکا هنوز با نتیجهٔ sendFile و message_id اثبات نشده است.

**شواهد/شناسه:** PR شمارهٔ ۹۲؛ شاخهٔ ops/enable-rubika-publishing؛ commit اولیهٔ 7493784f2eab9263abe3797b6d4ac7fd1d5b2b1c؛ شناسهٔ کانال تأییدشده c0EH9WW0c7fa831d965d050233b7ab35.

**ریسک/بازگشت:** در صورت خطا یا نیاز به توقف، Actions Variable با نام RUBIKA_ENABLE_PUBLISHING را به false تنظیم کنید. توکن فقط در GitHub Actions Secret می‌ماند؛ شناسهٔ کانال به‌تنهایی دادهٔ محرمانه محسوب نمی‌شود.

**وضعیت:** پیکربندی روی شاخهٔ PR اعمال شده است؛ ادغام در main و تأیید انتشار عمومی واقعی هنوز باید از CI و گزارش اجرای ناشر تأیید شود.


## 2026-11-07 — نمایش شبکهٔ کانال‌های آفِرچین روی تصاویر محصولات

**هدف:** معرفی کانال‌های تلگرام، بله و روبیکا در تصویر تمام پست‌های محصول، برای هدایت مخاطب هر کانال به سایر بسترهای آفِرچین.

**تغییر/اقدام:** افزودن لینک rubika.ir/offerchin به فهرست مشترک کنار لینک‌های T.me/OfferChin و ble.ir/OfferChin؛ نمایش نشان/آیکون هر پلتفرم دقیقاً قبل از لینک خودش؛ یکسان‌سازی سه ردیف در تصاویر هر سه مقصد؛ حذف نشان متنی تکراری روبیکا از تصویر پست روبیکا؛ حفظ رفتار ایتا بدون ساخت لینک عمومی تأییدنشده.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/messenger_adapters.py، affilio_radar/test_affilio.py، affilio_radar/test_messenger_adapters.py، affilio_radar/VISUAL_BRANDING.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** تست رندر کنترل می‌کند که هر تصویر دقیقاً نشان‌های telegram، bale و rubika را به‌ترتیب دارد و خروجی تصویر برای ورودی‌های مقصدهای تلگرام، بله و روبیکا یکسان است. آزمون آداپتور نیز نبود نشان تکراری روبیکا را بررسی می‌کند. نتیجهٔ CI پس از اجرای Pull Request ثبت می‌شود.

**شواهد/شناسه:** شاخهٔ feat/all-channel-links-on-product-art؛ لینک‌های تأییدشدهٔ کانال‌های عمومی آفِرچین: https://t.me/OfferChin، https://ble.ir/OfferChin و https://rubika.ir/offerchin.

**ریسک/بازگشت:** در صورت کوچک‌شدن بیش‌ازحد فضای پایین تصویر یا پوشاندن جزئیات محصول، اندازهٔ فونت و آیکون‌ها به‌صورت تطبیقی کاهش می‌یابد و رنگ متن از روشنایی پس‌زمینه انتخاب می‌شود. برای بازگشت، فهرست سه‌ردیفی به دو مقصد پیشین برگردانده و نشان اضافهٔ روبیکا از آداپتور بازگردانی می‌شود.

**وضعیت:** تغییر کد و مستندات روی شاخهٔ کاری ثبت شده است؛ ادغام و تأیید CI نهایی هنوز انجام نشده است.


## 2026-11-07 — فهرست مقصد‌محور لینک تلگرام، بله، روبیکا و یوتیوب روی تصاویر

**هدف:** معرفی هر چهار بستر عمومی OfferChin روی تصاویر پست‌ها، بدون نمایش لینک همان بستری که پست در آن منتشر می‌شود؛ با حفظ فهرست عمودی و نشان تصویری قبل از هر لینک.

**تغییر/اقدام:** افزودن منبع واحد چهار لینک عمومی در `offerchin_visuals.py`؛ ساخت footer مقصد‌محور برای تصاویر تلگرام، بله و روبیکا؛ افزودن آیکون قرمز/پخش یوتیوب؛ افزودن لینک یوتیوب به footer تصاویر تلگرام، بله و روبیکا؛ تبدیل نوار CTA ویدئوی یوتیوب به سه ردیف عمودی تلگرام، بله و روبیکا؛ تفکیک تصویر در مسیر repair تلگرام و بله به‌جای اشتراک یک تصویر بین دو مقصد؛ حفظ فهرست چهارگانه در رندرهای بدون مقصد مشخص برای پیش‌نمایش.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_visuals.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/messenger_adapters.py`، `affilio_radar/short_video.py`، تست‌های `test_affilio.py`، `test_messenger_adapters.py` و `test_short_video.py`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های رگرسیون برای حذف مقصد جاری و حضور سه مقصد دیگر در هر یک از چهار خروجی تصویری، دریافت مقصد روبیکا/ایتا در آداپتور، و فهرست عمودی سه‌لینکی پوستر یوتیوب اضافه شدند. نتیجهٔ CI و تست نهایی پس از اجرای Pull Request ثبت می‌شود؛ تا پیش از آن موفقیت تست‌ها یا انتشار عمومی ادعا نمی‌شود.

**شواهد/شناسه:** نشانی یوتیوب از اجرای read-only OAuth check شمارهٔ `42341310897` استخراج شد: `https://www.youtube.com/@offerchin`؛ شناسهٔ کانال `UCkInXAxxNdzR9LDE2oviA2w`. شاخهٔ کاری `feat/destination-aware-cross-channel-overlays`.

**ریسک/بازگشت:** فهرست بیشتر ممکن است فضای footer را محدود کند؛ الگوریتم فعلی اندازهٔ قلم و آیکون را با ابعاد تصویر تطبیق می‌دهد و رنگ نوشته را از روشنایی پس‌زمینه انتخاب می‌کند. اگر خوانایی تصویر واقعی افت کند، اندازه و فاصلهٔ ردیف‌ها باید اصلاح شود؛ بازگشت با revert تغییر renderer و ثابت‌کردن دوبارهٔ فهرست مقصدها ممکن است. این تغییر تصاویر پست‌های قدیمی را به‌صورت خودکار ویرایش نمی‌کند.

**وضعیت:** کد و تست‌ها در شاخهٔ Pull Request آمادهٔ CI هستند؛ ادغام در `main` و مشاهدهٔ خروجی انتشار عمومی هنوز انجام نشده است.


## 2026-11-07 — یکسان‌سازی کپشن روبیکا و افزودن دکمهٔ عضویت کانال

**هدف:** همسان‌کردن متن کپشن روبیکا با تلگرام و بله و فراهم‌کردن لینک مستقیم عضویت در کانال روبیکا، بدون ارسال پیام جداگانه.

**تغییر/اقدام:** حذف تبدیل متفاوت کپشن روبیکا و حذف الحاق متن جداگانهٔ URL خرید؛ استفاده از تابع مشترک `build_caption` با نشانی کانال روبیکا؛ تبدیل خروجی قالب‌بندی‌شده به متن ساده برای فیلد متنی روبیکا؛ افزودن `inline_keypad` به متد `sendFile` شامل دکمهٔ لینک خرید افیلیت و دکمهٔ لینک عضویت به `https://rubika.ir/offerchin`؛ حفظ شناسهٔ واقعی پیام و کنترل‌های اعتبارسنجی موجود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `affilio_radar/MESSENGER_EXPANSION_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست جدید بررسی می‌کند کپشن از همان سازندهٔ مشترک گرفته شود، channel URL دقیق روبیکا به کپشن‌ساز برسد، دکمهٔ خرید به URL معتبر Affilio و دکمهٔ عضویت به کانال روبیکا متصل باشند و هر دو در همان payload ارسال تصویر قرار بگیرند. نتیجهٔ CI پس از اجرای Pull Request ثبت می‌شود؛ هیچ پیام عمومی آزمایشی ارسال نمی‌شود.

**شواهد/شناسه:** مستند رسمی روبیکا، بخش متد `sendFile` که `inline_keypad` را به‌عنوان پارامتر ارسال فایل معرفی می‌کند: https://rubika.ir/botapi/methods ؛ مدل دکمه و فیلد URL: https://rubika.ir/botapi/models ؛ کانال هدف: https://rubika.ir/offerchin.

**ریسک/بازگشت:** مستند رسمی روبیکا برای `sendFile` فیلد metadata مستقلِ لینک درون متن را در فهرست ورودی‌ها ذکر نمی‌کند؛ بنابراین CTA عضویت به‌صورت دکمهٔ URL زیر همان پیام تصویری پیاده می‌شود. در صورت رد شدن ساختار ButtonLink از سوی API، ارسال روبیکا باید fail-safe بماند و نباید پست موفق یا لینک کلیکی را بدون دریافت پاسخ تأییدشده گزارش کند. بازگشت با revert تغییر آداپتور و تست‌ها ممکن است.

**وضعیت:** کد، تست و مستندات در شاخهٔ Pull Request ثبت شده‌اند؛ ادغام در `main`، اجرای CI و تأیید payload توسط API واقعی هنوز انجام نشده است.


## 2026-11-07 — استانداردسازی متن کپشن، CTA و لینک‌های اقدام

**هدف:** حذف واگرایی متن خرید و عضویت میان پیام‌رسان‌ها و ایجاد منبع واحد برای متن‌های قابل‌مشاهدهٔ کپشن و دکمه‌ها.

**تغییر/اقدام:** فایل `offerchin_copy.py` به‌عنوان منبع واحد عبارت‌های کپشن و CTA افزوده شد. سازندهٔ کپشن Telegram/Bale/Rubika از عبارت‌های مشترک فروش، عنوان، قیمت، تخفیف، دیجی‌پی، جداکننده و عضویت استفاده می‌کند. برچسب خرید همهٔ دکمه‌ها از یک helper می‌آید. Rubika همچنان دکمهٔ خرید و عضویت را روی همان پیام می‌فرستد. Eitaa عبارت خرید را عین متن دکمه و URL افیلیت را در کپشن می‌گیرد؛ CTA عضویت فقط با URL عمومی واقعیِ تنظیم‌شده فعال می‌شود و URL حدسی حذف شده است. workflow ناشر متغیر اختیاری `EITAA_CHANNEL_URL` را به آداپتور می‌رساند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_copy.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `.github/workflows/offerchin-publisher.yml`، `affilio_radar/MESSENGER_EXPANSION_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های آداپتور برای یکسان‌بودن متن دکمهٔ روبیکا با منبع مشترک، برچسب خرید Eitaa، حذف لینک عضویت بدون URL پیکربندی‌شده و استفاده از URL واقعی در صورت تنظیم افزوده شدند. نتیجهٔ اجرای GitHub Actions پس از بازشدن PR ثبت می‌شود؛ تا قبل از آن، قبولی CI یا دیده‌شدن ظاهری در کلاینت‌ها ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-canonical-caption-actions-standard-20261107`؛ PR/commit پس از ایجاد ثبت می‌شود.

**ریسک/بازگشت:** تفاوت قالب متن و جایگاه CTA ناشی از محدودیت API هر پیام‌رسان باقی می‌ماند؛ متن‌های قابل‌مشاهده از منبع مشترک هستند. اگر Eitaa URL عمومی صحیحی در متغیر تنظیم نشده باشد، لینک عضویت درج نمی‌شود. بازگشت با revert همین PR ممکن است.

**وضعیت:** تغییر کد، تست و مستندات در شاخهٔ کاری آمادهٔ CI؛ ادغام و تست نهایی هنوز انجام نشده است.


## 2026-11-07 — جایگزینی لوگوهای دستی با دارایی‌های رسمی پلتفرم‌ها

**هدف:** نمایش نشان‌های واقعی و منطبق با برند Telegram، Bale، Rubika و YouTube در تصاویر پست و ویدئوهای عمودی؛ با حفظ اندازهٔ کوچک، خوانایی و نسبت واقعی، به‌ویژه مستطیلی بودن wordmark یوتیوب.

**تغییر/اقدام:** renderer مشترک offerchin_visuals.py برای بارگذاری فایل‌های رسمی محلی، fit متناسب بدون کشیدگی/برش، و رسم کوچکِ خوانا اضافه شد. نشان‌های دستی در مسیر عکس و ویدئو با همین renderer جایگزین شدند. در عکس‌ها فقط سه مقصد دیگر نمایش داده می‌شود؛ در YouTube Short، لوگوی افقی خود یوتیوب و نشانی کانال در ابتدای پنل چهارردیفی و سپس سه مقصد دیگر می‌آیند. چیدمان فروشگاه/تخفیف/DigiPay داخل تصویر محصول تغییر نمی‌کند. گردش‌کار sync رسمی، فایل‌های لوگو را از منابع رسمی دریافت، اعتبارسنجی و به پوشهٔ محلی مخزن commit می‌کند.

**فایل‌ها/سامانه‌ها:** affilio_radar/offerchin_visuals.py، affilio_radar/affilio_radar.py، affilio_radar/short_video.py، تست‌های test_affilio.py و test_short_video.py، affilio_radar/VISUAL_BRANDING.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، .github/workflows/sync-official-platform-logos.yml، .github/platform-brand-assets-sync.request.

**آزمون و نتیجه:** تست fit متناسب نسبت ۴٫۲:۱ لوگوی YouTube و نشان مربعی، حضور لوگوی YouTube در پوستر Short، ترتیب فهرست کانال‌ها، و حفظ مقصدهای عکس افزوده شده‌اند. workflow sync ساختار SVGها، فرمت PNG و افقی بودن فایل YouTube را کنترل می‌کند. اجرای کامل CI و موفقیت ذخیرهٔ فایل‌ها پس از ایجاد PR ثبت خواهد شد؛ هیچ پست عمومی آزمایشی ارسال نمی‌شود.

**شواهد/شناسه:** منابع اعلام‌شدهٔ رسمی: بستهٔ Telegram Press، لوگوی رسمی Bale، فایل لوگوی رسمی Rubika و بستهٔ لوگوهای YouTube Brand. PR و SHA نهایی پس از ایجاد ثبت می‌شوند.

**ریسک/بازگشت:** اگر یک منبع رسمی موقتاً در دسترس نباشد یا فایل دانلودی نسبت مورد انتظار را نداشته باشد، sync با خطا متوقف می‌شود و دارایی ناقص commit نمی‌شود؛ publisher از لوگوی حدسی استفاده نمی‌کند. rollback با revert همین PR و commit sync دارایی‌ها ممکن است.

**وضعیت:** منطق renderer، تست و مستندات در شاخهٔ کاری ثبت شده‌اند؛ دریافت و commit نهایی فایل‌های باینری در workflow پس از ادغام هنوز در انتظار اجراست.


## 2026-11-07 — مقاوم‌سازی commit فایل‌های لوگوی رسمی در برابر push هم‌زمان

**هدف:** جلوگیری از ردشدن commit دارایی‌های لوگو در صورتی که workflow دیگری هم‌زمان `main` را جلو ببرد.

**تغییر/اقدام:** پس از اعتبارسنجی موفق چهار فایل رسمی، workflow قبل از push آخرین `origin/main` را fetch و commit دارایی‌ها را rebase می‌کند؛ در صورت race، تا چهار بار با فاصلهٔ افزایشی تلاش می‌کند. درخواست sync با version=2 دوباره trigger می‌شود تا assets رسمی مجدداً و روی HEAD تازه دانلود/ثبت شوند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/sync-official-platform-logos.yml`، `.github/platform-brand-assets-sync.request`، `docs/CHANGELOG_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** اجرای نخست در run `42390714727` چهار فایل رسمی را کامل دریافت و اعتبارسنجی کرد؛ YouTube horizontal wordmark با نسبت ابعاد `2.976:1` تأیید شد. push نهایی به‌دلیل non-fast-forward رد شد، زیرا `main` در فاصلهٔ checkout و push به‌روزرسانی شده بود. اجرای دوم پس از ادغام retry logic باید commit واقعی فایل‌ها را ثبت کند.

**شواهد/شناسه:** PR شمارهٔ ۹۹ merge commit `8b08c5f86fddb315947b46d0e3d0d59ef82ac625`؛ asset-sync run `42390714727` (validation success / push failure).

**ریسک/بازگشت:** rebase خودکار فقط روی commit تازه‌ای انجام می‌شود که assetها را اضافه می‌کند؛ اگر conflict واقعی رخ دهد، job fail می‌شود و فایل‌های main بازنویسی نمی‌شوند. rollback با revert این تغییر workflow امکان‌پذیر است.

**وضعیت:** retry logic و sync trigger نسخهٔ ۲ در شاخهٔ کاری آمادهٔ PR؛ commit دارایی‌ها پس از اجرای مجدد هنوز در انتظار است.


## 2026-11-07 — بهبود مقیاس خوانایی لوگوهای رسمی در تصویر و ویدئو

**هدف:** کوچک و مرتب ماندن لوگوهای اصلی، بدون ریزشدن بیش از حد در عکس‌های پُروضوح؛ حفظ نسبت افقی لوگوی کامل YouTube و جلوگیری از هم‌پوشانی لوگوهای نوار بالای ویدئو.

**تغییر/اقدام:** تابع `platform_footer_metrics` مقیاس logo height، حداکثر عرض متناسب، اندازهٔ متن و فاصلهٔ ردیف‌ها را بر اساس وضوح تصویر تعیین می‌کند. در poster ویدئو، چهار ردیف YouTube/Telegram/Bale/Rubika با ارتفاع لوگوی ۲۰ پیکسل و فاصلهٔ عمودی ۲۶ پیکسل قرار می‌گیرند؛ پنل و بخش‌های پایین‌تر به اندازهٔ لازم جابه‌جا شده‌اند تا کادرها هم‌پوشانی نکنند. لوگوی کامل افقی YouTube، فایل اصلیِ رنگی و مستطیلی است و با همان نسبت اصلی fit می‌شود؛ هیچ مربع یا آیکون جایگزینی استفاده نمی‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_visuals.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `affilio_radar/VISUAL_BRANDING.md`، `docs/CHANGELOG_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌ها وجود هر چهار asset رسمی، حفظ نسبت منبع در اندازهٔ خروجی، نسبت افقی بیش از ۲٫۸ برای YouTube wordmark، مقیاس تطبیقی footer تصاویر، حضور لوگوی YouTube در ردیف اول و فاصلهٔ غیرهم‌پوشان ردیف‌های ویدئو را بررسی می‌کنند. نتیجهٔ CI پس از PR ثبت می‌شود؛ هیچ محتوای عمومی آزمایشی منتشر نمی‌شود.

**شواهد/شناسه:** شاخهٔ کاری `fix/offerchin-platform-logo-scale-and-video-layout-20261107`؛ PR و commit نهایی پس از ایجاد ثبت می‌شود.

**ریسک/بازگشت:** افزایش اندازه فقط در footer کانال‌هاست و چیدمان retailer/discount/DigiPay داخل کارت محصول حفظ می‌شود. اگر متن در یک تصویر خاص با محصول تداخل کند، متریک مقیاس در `platform_footer_metrics` قابل تنظیم است. rollback با revert همین PR ممکن است.

**وضعیت:** کد، تست و مستندات در شاخهٔ کاری؛ CI، ادغام و بررسی خروجی نهایی پس از ایجاد PR در انتظار.


## ۲۰۲۶-۱۱-۰۷ — یکپارچه‌سازی آیدی متقابل پنج رسانه با لوگوی رسمی

**هدف:** هر رسانه در محتوای منتشرشده، چهار رسانهٔ عمومی دیگر را با هویت بصری دقیق و بدون نوشتهٔ تبلیغاتی اضافه معرفی کند؛ مقصد جاری نباید خودش را در فهرست ببیند.

**تغییر/اقدام:** فهرست رسانه‌های عمومی به پنج مقصد تأییدشدهٔ Telegram، Bale، Rubika، YouTube و Aparat گسترش یافت. برای هر ردیف فقط لوگوی اصلی کنار آیدی کوتاه نمایش داده می‌شود؛ متن «OfferChin •»، نام پلتفرم، توضیحات اضافه و پیشوندهای http://، https:// و www. حذف شدند. لوگوی افقی Aparat از SVG هدر وب‌سایت رسمی استخراج و به‌صورت asset محلی افزوده شد؛ workflow همگام‌سازی رسمی نیز اعتبارسنجی نسبت ۸۰:۲۵ آن را انجام می‌دهد. پوستر YouTube و Aparat اکنون هرکدام فقط چهار رسانهٔ دیگر را نمایش می‌دهند و هنگام آماده‌بودن هم‌زمان دو آپلود، دو MP4 مقصد‌محور مجزا ساخته می‌شود. توضیحات متنی و fallback uploaderها نیز از آیدی‌های کوتاه و بدون پروتکل استفاده می‌کنند.

**فایل‌ها/سامانه‌ها:** affilio_radar/offerchin_visuals.py، affilio_radar/affilio_radar.py، affilio_radar/short_video.py، affilio_radar/aparat_uploader.py، affilio_radar/assets/platform-logos/aparat-official.svg، .github/workflows/sync-official-platform-logos.yml، تست‌های رگرسیون برندینگ/ویدئو، VISUAL_BRANDING.md و handbook.

**آزمون و نتیجه:** تست‌ها برای پنج لوگوی محلی، حذف مقصد جاری، آیدی‌های canonical، خروجی‌های مجزای YouTube/Aparat و توضیحات بدون برچسب اضافه به‌روزرسانی شدند؛ نتیجهٔ CI پس از اجرای PR در همین ورودی تکمیل می‌شود.

**شواهد/شناسه:** شاخهٔ fix/offerchin-five-platform-logo-only-crosslinks-20261107؛ PR و merge SHA پس از تأیید CI ثبت می‌شوند.

**ریسک/بازگشت:** فایل‌های MP4 تولیدشده از این نسخه فقط برای رسانهٔ مقصد خود معتبرند؛ استفادهٔ مجدد از یک artifact برای هر دو مقصد مجاز نیست. Eitaa عمداً در فهرست عمومی نیست، چون URL عمومی تأییدشده‌ای برای آن در مخزن وجود ندارد. بازگشت با revert کردن PR ممکن است؛ این تغییر محتوای منتشرشدهٔ قبلی را ویرایش یا پست آزمایشی عمومی ارسال نمی‌کند.

**وضعیت:** در انتظار CI و ادغام.


**پیگیری وضعیت — ۲۰۲۶-۱۱-۰۷:** همهٔ پنج بررسی GitHub Actions موفق شدند: Platform Logo Regression Tests، Documentation Gate، Catalog Sweep Regression Tests، Messenger Adapter Tests و Top-100 and DigiPay Regression Tests. PR شمارهٔ ۱۰۳ با commit ادغام `257c21af6f8ae66ae8075f6c872e37947baad53a` در شاخهٔ `main` ادغام شد. هیچ پست آزمایشی عمومی ارسال نشد؛ مشاهدهٔ نهاییِ ظاهر پست در کلاینت‌های واقعی پس از انتشار عادی، هنوز جداگانه قابل بررسی است.


## 2026-11-07 — همگام‌سازی مستندات با وضعیت زنده و رفع شکست Documentation Gate

**هدف:** رفع تعارض مستندات قدیمی با وضعیت واقعی Cloudflare و اسکن کاتالوگ، ثبت علت شکست Documentation Gate، بستن PR تکراری لوگو و تفکیک موفقیت اجرای workflow از انتشار عمومی واقعی.

**تغییر/اقدام:** به‌روزرسانی handbook با وضعیت read-only نسخهٔ ۳۶ Worker و Cron یک‌دقیقه‌ای، شواهد آخرین چرخهٔ کامل کاتالوگ و پیشرفت چرخهٔ بعدی، و نتیجهٔ واقعی ناشر که در آن گاردهای تکرار مانع انتخاب شدند و پست تازه‌ای ارسال نشد. علت شکست run شمارهٔ 42395130657 از روی log ثبت شد: نه تست validator، بلکه فقدان عنوان تاریخ‌دار جدید برای یادداشت پیگیری changelog. یک بخش تاریخ‌دار مستقل با تمام هفت فیلد الزامی افزوده شد. PR قدیمی شمارهٔ ۹۶ به‌دلیل هم‌پوشانی و superseded شدن توسط PR شمارهٔ ۱۰۳ بسته شد. هیچ پست آزمایشی عمومی ارسال نشد.

**فایل‌ها/سامانه‌ها:** `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`، Cloudflare Worker `affilio-minute-dispatcher`، GitHub Actions اسکنر کاتالوگ و ناشر؛ PRهای ۹۶ و ۱۰۳.

**آزمون و نتیجه:** در run شکست‌خوردهٔ Documentation Gate، هر ۹ تست `test_validate_offerchin_documentation.py` موفق بودند و فقط مرحلهٔ enforce به‌علت نبود heading تاریخ‌دار جدید شکست خورد. اسکنر run شمارهٔ 42395883443 با success و checkpoint پایدار خاتمه یافت. ناشر run شمارهٔ 42395636227 نیز از نظر فنی موفق بود، اما `selected=0`، `publisher_invoked=false` و `PUBLISHER_NOTHING_DUE` ثبت کرد؛ بنابراین انتشار عمومی تازه‌ای اثبات نشد. صفحه‌های عمومی Telegram، Bale، YouTube و Aparat از نظر متن/فهرست قابل خواندن بودند و Rubika فقط metadata کانال را نشان داد؛ هیچ‌یک از این خروجی‌های متنی، نمایش لوگو و شناسه درون فایل تصویر را اثبات نمی‌کند. Documentation Gate اصلاح مستندات در PR شمارهٔ ۱۰۴ با run شمارهٔ 42396356334 موفق شد؛ merge و push-trigger پس از آن جداگانه پیگیری می‌شوند.

**شواهد/شناسه:** Cloudflare deployment `19791161-bcb9-4c85-b802-e0aae51aa57a`، Worker version 36 با شناسهٔ `5b9c8cf2-898c-46ff-adc2-88cff1050fb5` و ۱۰۰٪ ترافیک؛ Cron برابر `* * * * *`. آخرین snapshot کامل: ۴٬۹۱۶/۴٬۹۱۶ دسته، ۲۲۷٬۰۰۹ صفحه، ۴٬۴۷۴٬۰۴۷ ردیف محصول، ۳٬۰۰۰ candidate و پایان در `2026-11-07T11:42:22.241603+00:00`. چرخهٔ بعدی در snapshot ساعت ۱۷:۲۴:۲۶ UTC: ۳٬۸۶۶ دسته تکمیل و ۱٬۰۵۰ صفحه pending. Catalog run: `42395883443`؛ publisher run: `42395636227`؛ شکست Documentation Gate: `42395130657`؛ PR #103 merge SHA: `257c21af6f8ae66ae8075f6c872e37947baad53a`؛ PR #96 closed.

**ریسک/بازگشت:** این تغییرات فقط مستندات و وضعیت PR را اصلاح می‌کنند؛ کد انتشار، Worker، Cron، Secretها، صف‌ها و گاردهای تکرار تغییر نکرده‌اند. سابقهٔ changelog append-only باقی می‌ماند. تأیید بصری تصاویر عمومی تا زمان انتشار طبیعی و مشاهدهٔ شناسه‌دار در هر مقصد، باز می‌ماند. rollback مستندات با revert همین PR امکان‌پذیر است.

**وضعیت:** مستندات در شاخهٔ کاری به‌روزرسانی می‌شوند؛ Documentation Gate و merge این اصلاح هنوز باید با نتیجهٔ واقعی Actions تأیید شوند.


## ۲۰۲۶-۱۱-۰۷ — افزودن CTA خرید اختصاصی به ویدئوهای YouTube و Aparat

**هدف:** کوتاه‌کردن مسیر تبدیل بازدید ویدئو به مراجعه به محل لینک خرید، با متن کوتاه و متناسب با قابلیت هر پلتفرم.

**تغییر/اقدام:** روی پوستر ویدئوی YouTube عبارت «لینک خرید: توضیحات کانال» و روی پوستر ویدئوی Aparat عبارت «لینک خرید: کپشن ویدئو و توضیحات کانال» افزوده شد. متن CTA بالای ردیف‌های آیدی متقابل رسانه‌ها نمایش داده می‌شود. پنل برای یک ردیف CTA بلندتر و کارت محصول ۲۲ پیکسل پایین‌تر منتقل شد؛ قیمت، تصویر محصول، لوگوی فروشگاه، تخفیف، DigiPay و چهار لینک رسانه‌ای بدون تغییر محتوایی باقی ماندند. منطق موجود توضیحات ویدئوی Aparat همچنان لینک افیلیت همان محصول را در صورت اعتبار می‌افزاید؛ پیوندهای پروفایل کانال دست‌نخورده‌اند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست رگرسیون متن دقیق CTA برای هر دو مقصد و موقعیت چهار ردیف آیدی‌ها به‌روزرسانی شد؛ اجرای محلی/CI پس از push شاخه و بازشدن PR ثبت می‌شود. هیچ ویدئوی آزمایشی در مقصد عمومی منتشر نشده است.

**شواهد/شناسه:** شاخهٔ `feat/offerchin-youtube-aparat-video-purchase-cta-20261107`؛ PR، SHA ادغام و Run ID پس از بررسی واقعی CI تکمیل می‌شوند.

**ریسک/بازگشت:** جابه‌جایی کارت محصول به‌اندازهٔ ۲۲ پیکسل فضای نمایش عکس را اندکی کم می‌کند؛ آزمون crop نشان/لوگو و محدودهٔ پنل CTA باید موفق باشد. در صورت مشکل، با revert کردن همین PR، موقعیت قبلی پوستر بازمی‌گردد. هیچ صف، Secret، Worker یا تنظیم انتشار عمومی تغییر نکرده است.

**وضعیت:** پیاده‌سازی، تست و مستندات در شاخهٔ کاری؛ CI، بازبینی و ادغام در انتظار.


## ۲۰۲۶-۱۱-۰۷ — نتیجهٔ CI و ادغام CTA ویدئوهای YouTube و Aparat

**هدف:** ثبت نتیجهٔ نهایی اجرای تست‌ها و ادغام تغییر CTA خرید مقصد‌محور در main، بدون دست‌کاری تاریخچهٔ قبلی.

**تغییر/اقدام:** PR شمارهٔ ۱۰۵ ادغام شد. merge commit برابر `479a769cf796fc62b8af91d274f48d4b1a6f3a2d` است. رشته‌های CTA در `main` دوباره خوانده و وجود هر دو تأیید شد. handbook با شواهد CI و تفکیک تست mock از انتشار عمومی به‌روزرسانی شد.

**فایل‌ها/سامانه‌ها:** `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`؛ کد و تست اصلی در PR #105.

**آزمون و نتیجه:** Platform Logo Regression Tests run `42398570846` موفق: کامپایل renderer، ۲۶ تست `test_short_video.py` و دو تست یکپارچه‌سازی مربوط به watermark مقصد و رندر جداگانهٔ YouTube/Aparat موفق شدند. Documentation Gate run `42398570849` موفق: ۹ تست validator و مرحلهٔ enforce مستندات موفق شدند. لاگ آپلودهای تستی از mock استفاده می‌کند و انتشار عمومی واقعی نیست.

**شواهد/شناسه:** [PR #105](https://github.com/Mehran0960/ai_news_bot/pull/105)، merge SHA `479a769cf796fc62b8af91d274f48d4b1a6f3a2d`، Actions run IDs: `42398570846` و `42398570849`.

**ریسک/بازگشت:** هیچ Worker، Cron، Secret، صف انتشار یا پست عمومی تغییر نکرد. rollback کد با revert PR #105 و rollback این ثبت با revert همین PR مستندات ممکن است. QA بصری اولین ویدئوی واقعی YouTube و Aparat هنوز به مشاهدهٔ انتشار طبیعی نیاز دارد.

**وضعیت:** تغییر کد در main ادغام‌شده و CI مربوط به PR موفق؛ ثبت نهایی شواهد مستند شده است.


## ۲۰۲۶-۱۱-۰۷ — هم‌ترازی شناسه‌های رسانه و ارتقای فونت تیتر ویدئو

**هدف:** رفع به‌هم‌ریختگی دیداری در فوتر تصاویر و پنل آیدی ویدئوها، حذف امکان بازگشت برچسب‌های اضافی و نزدیک‌کردن ظاهر تیتر محصول به فونت‌های نمایشی مانند Titr.

**تغییر/اقدام:** در تصویر محصول و پوستر ویدئو، یک ستون ثابت برای لوگوها تعریف شد؛ لوگو/لوگوتایپ متناسب با عرض اصلی خود درون ستون قرار می‌گیرد و همهٔ آیدی‌ها از یک مختصات افقی یکسان شروع می‌شوند. متن آیدی فقط URL کوتاه رسمی می‌ماند و هیچ «OfferChin •» یا برچسب متنی دیگری اضافه نمی‌شود. تیتر محصول در ویدئو با فایل محلی Lalezar جایگزین DejaVu Sans عمومی شد. خود فایل فونت به‌همراه مجوز SIL OFL 1.1 در مخزن ذخیره شد؛ متن‌های CTA/قیمت و سایر اجزا تغییر نکردند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_short_video.py`، `affilio_radar/assets/fonts/Lalezar-Regular.ttf`، `affilio_radar/assets/fonts/Lalezar-OFL.txt`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های جدید مختصات شروع یکسان چهار آیدی در فوتر تصویر و ویدئو، نبود پیشوند و عبارت اضافه، وجود و بارگذاری فونت Lalezar و رندر جداگانهٔ مقصدها را بررسی می‌کنند. نتیجهٔ کامپایل و Regression CI پس از اجرای PR ثبت می‌شود. هیچ پست آزمایشی عمومی ارسال نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-logo-id-alignment-and-display-title-font-20261107`؛ PR و SHA ادغام پس از CI ثبت می‌شوند. منبع فونت: [BornaIz/Lalezar](https://github.com/BornaIz/Lalezar)، فایل مجوز SIL OFL 1.1 در کنار asset ثبت شده است.

**ریسک/بازگشت:** فونت Lalezar یک شخصیت نمایشی و پررنگ‌تر از فونت قبلی دارد؛ اگر در تیترهای طولانی خوانایی یا تناسب سطرها مشکل پیدا کند، بازگشت به فونت قبلی از طریق revert همین PR ممکن است. ستون ثابت فضای افقی مشخصی رزرو می‌کند؛ در صورت عریض‌بودن آیدی، اندازهٔ متن footer مطابق قواعد فعلی کوچک می‌شود. هیچ صف، Secret، Worker، Cron یا محتوای عمومی قبلی تغییر نکرده است.

**وضعیت:** کد، asset فونت و تست‌ها در شاخهٔ کاری؛ CI، بررسی پوستر و ادغام در انتظار.


## ۲۰۲۶-۱۱-۰۷ — نتیجهٔ CI و ادغام اصلاح لوگوها و فونت تیتر

**هدف:** ثبت شواهد نهایی آزمون و ادغام PR شمارهٔ ۱۰۷ و تفکیک تست‌های رندر از انتشار عمومی.

**تغییر/اقدام:** PR #107 با merge commit `db46958ecbf0a4dae0ebd4bdcb223bdaa3b35c1f` در main ادغام شد. فوتر تصویر و پنل ویدئو از ستون ثابت لوگو/آیدی استفاده می‌کنند و تیتر محصول از فایل محلی Lalezar با مجوز SIL OFL 1.1 رندر می‌شود. Handbook با نتایج CI و وضعیت اجرای push همگام شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/assets/fonts/Lalezar-Regular.ttf`، `affilio_radar/assets/fonts/Lalezar-OFL.txt`، تست‌های رگرسیون و `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** Platform Logo Regression run `42400049341` موفق: ۲۸ تست short-video و تست‌های یکپارچه‌سازی. Top-100 and DigiPay run `42400049340` موفق: ۲۶۶ تست، ۲ مورد skip؛ تست فوتر تصویر با آیدی‌های خام و مختصات یکسان موفق. Messenger Adapter run `42400049359`، Catalog Sweep Regression run `42400049375`، PR Documentation Gate run `42400049412` و push Documentation Gate run `42400184741` همگی success شدند؛ Gate شامل ۹ تست validator بود. Radar push run `42400184676` موفق بود ولی مرحلهٔ کشف/صف‌گذاری skipped شد؛ هیچ پست تازه‌ای منتشر نشد. Storefront run `42400188791` با موفقیت build/test/SEO/deploy شد.

**شواهد/شناسه:** [PR #107](https://github.com/Mehran0960/ai_news_bot/pull/107)، merge SHA `db46958ecbf0a4dae0ebd4bdcb223bdaa3b35c1f`؛ Actions run IDs: `42400049341`، `42400049340`، `42400049359`، `42400049375`، `42400049412`، `42400184741`، `42400184676` و `42400188791`.

**ریسک/بازگشت:** تصاویر و ویدئوهای عمومی قبلی خودکار ویرایش نمی‌شوند؛ کد جدید روی رندرهای بعدی اعمال می‌شود. Rollback با revert کردن PR #107 ممکن است. هیچ Worker، Cron، Secret یا صف انتشار مستقیم دست‌کاری نشد و پست آزمایشی ارسال نشد.

**وضعیت:** تغییر کد و asset فونت در main ادغام‌شده؛ همهٔ CIهای PR و push Gate موفق؛ بررسی بصری اولین انتشار طبیعیِ جدید همچنان باقی است.


## ۲۰۲۶-۱۱-۰۷ — ویدئوی ۱۲ ثانیه‌ای با موسیقی فانک منتخب و تشخیص امن خطای روبیکا

**هدف:** افزایش زمان واقعی تماشای ویدئوی محصول از ۸ به ۱۲ ثانیه، جایگزینی جینگل ساده با حال‌وهوای موسیقی فانک/نو-دیسکو منتخب کاربر، و قابل‌تشخیص‌کردن خطای واقعی تحویل روبیکا بدون افشای توکن یا URL حساس.

**تغییر/اقدام:** مقدار پیش‌فرض `DURATION_SECONDS` به ۱۲ ثانیه تغییر کرد؛ دامنهٔ امن رندر ۵ تا ۱۲ ثانیه باقی ماند. موسیقی فانک منتخب از نمونهٔ خصوصی فیوز خودرو به‌صورت مستقل و بدون SoundFont/فایل شخص ثالث، با بیس plucked، سازهای ضربه‌ای off-beat، clavinet، brass accent، هوک و امضای سه‌نتی بازسازی شد. تست مدت ۱۲ ثانیه و deterministic بودن خروجی افزوده شد. آداپتور روبیکا اکنون code/message کوتاه پاسخ API را پس از redaction ثبت می‌کند؛ publisher نیز detail امن را در state/log نگه می‌دارد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/short_video.py`، `affilio_radar/offerchin_audio.py`، `affilio_radar/test_short_video.py`، `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `affilio_radar/publisher.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست محلی تولید WAV دوازده‌ثانیه‌ای در ۰٫۷۵ ثانیه اجرا شد؛ خروجی stereo PCM با ۲۲٬۰۵۰Hz و زمان دقیق ۱۲ ثانیه تولید کرد. تست‌های واحد اضافه‌شده و Documentation Gate پس از اجرای CI ثبت می‌شوند؛ در زمان نگارش این ورودی، نتیجهٔ CI در انتظار است.

**شواهد/شناسه:** مبنای موسیقی: نمونهٔ خصوصی `03_funky-groove` مربوط به محصول «فیوز خودرو الپا»؛ وضعیت عملیاتی رسانه‌ها بر مبنای GitHub Actions runs `42392125523`، `42398023113`، `42400262177` و `42404810613` ثبت شد. PR و merge SHA پس از ایجاد/ادغام تکمیل می‌شوند.

**ریسک/بازگشت:** طول ۱۲ ثانیه درآمدزایی فیلو یا YouTube را تضمین نمی‌کند و محتوای تکراری با ارزش افزودهٔ کم همچنان ریسک policy دارد. بازگشت با revert کردن تغییر `DURATION_SECONDS` و فایل موسیقی امکان‌پذیر است. تغییر زمان‌بندی/تکرار/مهلت انتشار انجام نشده است. روبیکا همچنان تا دیدن پاسخ دقیق API یا یک تحویل موفق، نیازمند پایش است.

**وضعیت:** کد و مستندات در شاخهٔ کاری آمادهٔ CI و بازبینی؛ انتشار عمومی ویدئوی جدید هنوز انجام نشده است.


## ۲۰۲۶-۱۱-۰۷ — ثبت نتیجهٔ CI و ادغام PR شمارهٔ ۱۰۹

**هدف:** تکمیل شواهد انتشار نسخهٔ ویدئوی ۱۲ ثانیه‌ای و soundtrack فانک منتخب؛ ثبت نتیجهٔ تست‌ها و SHA نهایی بدون بازنویسی ورودی قبلی changelog.

**تغییر/اقدام:** PR شمارهٔ ۱۰۹ با روش squash در `main` ادغام شد. مقدار پیش‌فرض ویدئو ۱۲ ثانیه و موسیقی فانک/نو-دیسکو مستقل فعال شدند؛ diagnostics امن روبیکا نیز به main رسید. زمان‌بندی انتشار، صف، گاردهای ضدتکرار، مهلت محصول، credentialها و Worker تغییر نکردند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/short_video.py`، `affilio_radar/offerchin_audio.py`، `affilio_radar/test_short_video.py`، `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `affilio_radar/publisher.py`، handbook و changelog.

**آزمون و نتیجه:** run `42406664718`: ۴۴۱ تست regression موفق؛ run `42406762709`: ۲۹ تست رندر/لوگو موفق؛ run `42406762662`: ۷ تست آداپتور موفق؛ run `42406762722`: ۹ تست Documentation Gate موفق؛ push gate پس از merge با run `42406975332` نیز موفق شد.

**شواهد/شناسه:** [PR #109](https://github.com/Mehran0960/ai_news_bot/pull/109)، merge commit `159a371096b1dfe8115da00d774ca558072531c9`؛ [Regression run](https://github.com/Mehran0960/ai_news_bot/actions/runs/42406664718)، [Platform Logo tests](https://github.com/Mehran0960/ai_news_bot/actions/runs/42406762709)، [Messenger Adapter tests](https://github.com/Mehran0960/ai_news_bot/actions/runs/42406762662)، [PR Documentation Gate](https://github.com/Mehran0960/ai_news_bot/actions/runs/42406762722)، [post-merge Documentation Gate](https://github.com/Mehran0960/ai_news_bot/actions/runs/42406975332).

**ریسک/بازگشت:** ویدئوهای قبلی خودکار جایگزین نمی‌شوند؛ فقط رندرهای بعدی از تنظیم جدید استفاده می‌کنند. طول ۱۲ ثانیه درآمدزایی Filo/YouTube را تضمین نمی‌کند. rollback با revert کردن merge commit PR #109 انجام می‌شود؛ صف‌ها و تاریخچهٔ انتشار نباید برای بازگشت دستکاری شوند.

**وضعیت:** ادغام‌شده و CIهای مرتبط موفق؛ انتشار ویدئوی بعدی از زمان‌بندی عادی و فقط برای محصول واجدشرایط انجام خواهد شد.


## ۲۰۲۶-۱۱-۰۷ — بهبود بلندی صدای موسیقی و آزمون مسیر رندر ویدئو

**هدف:** شنیده‌شدن یکنواخت‌تر موسیقی در Shorts و Aparat، با کنترل قلهٔ صدا و بدون وابستگی به فایل یا بانک صدای خارجی در زمان رندر.

**تغییر/اقدام:** فیلتر ثابت `volume=0.84` با نرمال‌سازی FFmpeg به هدف `-16 LUFS` و سقف `-1.5 dBTP` جایگزین شد؛ fade-in/fade-out حفظ شدند. تست مستقیم برای بررسی فیلتر صوتی، اتصال stream موسیقی و خروجی ۱۲ثانیه‌ای/۲۴fps/۲۸۸ فریم افزوده شد. راهنمای دارایی صوتی و ملاحظهٔ مجوز SoundFont نمونهٔ خصوصی نیز اضافه شد؛ فایل MP3 نمونه به مخزن منتقل نشد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `affilio_radar/AUDIO_ASSETS.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** یک تست mock فرمان نهایی FFmpeg، نرمال‌سازی، fade، اتصال stream و ۲۸۸ فریم را کنترل می‌کند؛ تست دوم MP4 واقعی ۱۲ثانیه‌ای می‌سازد و با FFmpeg وجود stream صوتی و تصویری و مدت را دوباره بررسی می‌کند. اجرای مجموعهٔ `test_short_video.py` و Documentation Gate از GitHub Actions در حال بررسی است؛ این تست‌ها انتشار عمومی نیستند.

**شواهد/شناسه:** شاخهٔ کاری `feat/offerchin-video-audio-loudness-20261107`؛ PR و شناسه‌های CI پس از ایجاد ثبت خواهند شد. مبنای کد، مولد مستقل فعلی و تنظیمات رندر موجود در `main` است.

**ریسک/بازگشت:** نرمال‌سازی ممکن است شدت ادراکی را نسبت به نسخهٔ قبل افزایش دهد؛ true peak روی `-1.5 dBTP` محدود شده است. فقط خروجی‌های بعدی تغییر می‌کنند؛ انتشار قبلی دست‌نخورده می‌ماند. بازگشت با revert کردن تغییرات این PR ممکن است. زمان‌بندی، صف، guard ضدتکرار، credentialها و Worker تغییر نکردند.

**وضعیت:** تغییرات در شاخهٔ مستقل ثبت شده و آمادهٔ CI؛ ادغام به main منوط به موفقیت آزمون‌ها است.


## ۲۰۲۶-۱۱-۰۸ — تغییر فاصلهٔ کانال‌ها و گسترش اسکن صف ویدئو

**هدف:** تنظیم آهنگ انتشار کانال‌های Telegram/Bale روی ۳۷ دقیقه و جلوگیری از پنهان‌ماندن وظایف ویدئویی معوق پشت شش رکورد جدیدتر، بدون دورزدن محدودیت‌های واقعی پلتفرم‌ها.

**تغییر/اقدام:** فاصلهٔ Cloudflare dispatcher، مقدار پیش‌فرض Python، هر دو مقدار AFFILIO_MIN_POST_INTERVAL_HOURS در workflow ناشر و cadenceهای urgent به ۳۷ دقیقه تغییر کرد. Worker اکنون کل sidecar ویدئویی فشرده را (حداکثر ۲۵۰ رکورد) برای کار معوق می‌سنجد؛ محدودیت انتخاب نامزد در اسکریپت ویدئو و هر دو workflow نیز از ۶ به ۲۵۰ افزایش یافت. گارد تازگی ۲۴ساعته و اعتبار مهلت پیشنهاد حفظ شدند. فاصلهٔ ۳ساعتهٔ آپلود YouTube/Aparat به‌دلیل سابقهٔ uploadLimitExceeded تغییر نکرد؛ بنابراین این تغییر یک‌به‌یک بودن ویدئو برای هر پست متنی را تضمین نمی‌کند. مسیر فعلی آپارات نیز فقط feed معمولی را آپلود می‌کند؛ Shorts واقعی در مسیر اپلیکیشن باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** cloudflare/affilio-minute-dispatcher.js، cloudflare/affilio-minute-dispatcher.test.mjs، affilio_radar/affilio_radar.py، affilio_radar/test_affilio.py، .github/workflows/offerchin-publisher.yml، .github/workflows/youtube-video-upload.yml، .github/workflows/aparat-video-upload.yml، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md و docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** تست Python فاصلهٔ ۳۷دقیقه‌ای و برابر بودن پنجرهٔ کاندیدا با sidecar؛ تست Worker برای فاصلهٔ ۳۷دقیقه‌ای، یافتن رکورد معوق بعد از شش رکورد کامل‌شده و رد رکورد قدیمی‌تر از ۲۴ ساعت؛ کامپایل و Regression CI در PR اجرا می‌شوند و نتیجه پس از اجرای واقعی ثبت خواهد شد.

**شواهد/شناسه:** شاخهٔ کاری feat/offerchin-37m-channel-cadence-video-queue-20261108؛ PR و merge SHA پس از CI تکمیل می‌شوند.

**ریسک/بازگشت:** افزایش آهنگ کانال به حدود ۳۹ نوبت در روز می‌تواند ورودی صف ویدئو را از ظرفیت فعلی YouTube/Aparat جلو بیندازد؛ صف فقط تا پنجرهٔ تازگی و اعتبار آفر قابل استفاده است. برای برقراری نسبت یک‌به‌یک باید ظرفیت رسمی YouTube بررسی/افزایش یابد یا cadence متن با ظرفیت واقعی مقصدها هماهنگ شود. rollback با revert کردن همین PR ممکن است؛ زمان‌بندی امن و محدودیت سهمیهٔ ویدئو در این تغییر دست‌نخورده می‌مانند.

**وضعیت:** پیاده‌سازی در شاخهٔ کاری؛ CI، بازبینی و ادغام هنوز در انتظار.

## ۲۰۲۶-۱۱-۰۸ — افزودن مقصد ویدئویی فیلو به OfferChin

**هدف:** انتشار مستقل ویدئوهای کوتاه تبلیغاتیِ تولیدشده توسط OfferChin در حساب اختصاصی فیلو، بدون تغییر معیار انتخاب محصول یا صف مقصدهای دیگر.

**تغییر/اقدام:** مقصد filo به رجیستری ویدئو اضافه شد؛ آداپتور مستقل Playwright برای ورود، بارگذاری MP4، انتخاب کاور و ثبت نتیجه ساخته شد؛ workflow مستقل filo-video-upload.yml با Secrets موجود FILO_USER و FILO_PASS افزوده شد؛ زمان‌بندی جداگانهٔ سه‌ساعته در state sidecar و Cloudflare dispatcher اضافه شد؛ گزینهٔ --filo-upload-only برای پردازش صف بدون کشف محصول/آپلود مقصدهای دیگر اضافه شد.

**فایل‌ها/سامانه‌ها:** affilio_radar/filo_uploader.py، affilio_radar/affilio_radar.py، affilio_radar/short_video.py، affilio_radar/platform_registry.py، تست‌های test_filo_uploader.py و test_filo_upload_schedule.py، cloudflare/affilio-minute-dispatcher.js و تست آن، .github/workflows/filo-video-upload.yml، .github/workflows/offerchin-platform-logo-tests.yml، handbook و دفتر تغییرات.

**آزمون و نتیجه:** تست‌های واحدِ آداپتور، وضعیت‌های API، تشخیص دکمه، cadence مستقل، sidecar و فیلتر Worker اضافه شده‌اند؛ نتیجهٔ واقعی GitHub Actions هنوز در انتظار اجراست. هیچ ویدئوی عمومی آزمایشی ارسال نمی‌شود.

**شواهد/شناسه:** شاخهٔ feat/offerchin-filo-video-publisher-20261108؛ آخرین تغییرات این ورودی در commitهای e456296ebdfad92660f733ba0e6161d8e085743e (تست کنترل submit) و e8b877b748abcef2a7704e78aa410663b3a5c523 (گارد مهلت) ثبت شده‌اند؛ PR و merge SHA پس از CI ثبت خواهند شد.

**ریسک/بازگشت:** مسیر کنونی UI automation است، نه API رسمی عمومی؛ تغییر فرم/حفاظت ورود/OTP ممکن است workflow را متوقف کند. شکست پیش از submit فقط در صف فیلو retry می‌شود؛ نتیجهٔ نامشخص پس از submit هرگز خودکار دوباره ارسال نمی‌شود. rollback با revert همین تغییرها و غیرفعال‌کردن workflow/Worker Filo انجام می‌شود؛ زمان‌بندی و آپلود YouTube، آپارات و کانال‌ها مستقل می‌مانند.

**وضعیت:** پیاده‌سازی در شاخهٔ کاری؛ CI، بازبینی، ادغام، deploy Worker و اولین آپلود واقعی هنوز در انتظار.

 
## ۲۰۲۶-۱۱-۰۸ — افزودن بررسی ورود فیلو بدون انتشار

**هدف:** امکان تأیید صحت Secrets و دسترسی حساب اختصاصی OfferChin به فرم بارگذاری فیلو، پیش از اولین آپلود عمومی.

**تغییر/اقدام:** تابع verify_filo_login، فرمان --filo-login-check-only و ورودی دستی mode با گزینهٔ verify-login به workflow فیلو افزوده شدند. مقدار پیش‌فرض mode برابر upload است تا dispatcher خودکار رفتار عادی داشته باشد.

**فایل‌ها/سامانه‌ها:** affilio_radar/filo_uploader.py، affilio_radar/affilio_radar.py، affilio_radar/test_filo_uploader.py، .github/workflows/filo-video-upload.yml، handbook و دفتر تغییرات.

**آزمون و نتیجه:** تست واحد اطمینان می‌دهد بررسی ورود بدون هر دو Secret پیش از راه‌اندازی مرورگر fail-closed می‌شود؛ آزمون زندهٔ ورود فقط پس از ادغام و به‌صورت دستی اجرا خواهد شد و هیچ ویدئویی منتشر نمی‌کند.

**شواهد/شناسه:** شاخهٔ feat/offerchin-filo-video-publisher-20261108؛ commitهای 44d452c0cb1ef67d8d53bd5223b96ae75f9956ea، a2923d1460c1b4c026c30554b2c807c6c2f14db1 و cfe6ad48bc24e98a27c48e7f9756798bd058f376.

**ریسک/بازگشت:** بررسی ورود یک نشست احراز هویت‌شدهٔ کوتاه ایجاد می‌کند اما هیچ درخواست انتشار نمی‌فرستد. در صورت بروز OTP/CAPTCHA یا تغییر فرم، وضعیت شکست تشخیصی ثبت می‌شود؛ با revert کردن فرمان و ورودی workflow می‌توان این قابلیت را حذف کرد.

**وضعیت:** افزوده‌شده به شاخه؛ اعتبارسنجی CI و اجرای دستیِ بدون انتشار پس از ادغام در انتظار.

## ۲۰۲۶-۱۱-۰۸ — قفل انتشار خودکار فیلو تا تأیید ورود

**هدف:** جلوگیری از اولین آپلود خودکار پیش از تأیید صحت دسترسی حساب اختصاصی فیلو.

**تغییر/اقدام:** وضعیت موفق بررسی ورود در state و sidecar ثبت می‌شود؛ Python و Cloudflare فقط تأیید معتبر با عمر حداکثر ۷ روز را می‌پذیرند؛ بررسی ناموفق تأیید قبلی را حذف می‌کند.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، cloudflare/affilio-minute-dispatcher.js، تست‌های صف و Worker، handbook.

**آزمون و نتیجه:** تست‌های جدید تأیید تازه، تاریخ آینده، انقضای هفت‌روزه و شکست احراز هویت را پوشش می‌دهند؛ CI نهایی در انتظار.

**شواهد/شناسه:** شاخهٔ feat/offerchin-filo-video-publisher-20261108؛ commitهای 3816eff579945fbef634a02481a18c0451456adf، 6b76f2a333405aec380de8880f895c4cc0baec21، 304f28112176117e3a7b094e3fb2d232aa76e8ff و 760596128017571e4c0fa9136865671e7cd798a0.

**ریسک/بازگشت:** تا ثبت موفق بررسی ورود فیلو dispatch نمی‌شود؛ پس از ۷ روز تأیید منقضی است و باید دوباره اجرا شود. rollback با revert همین تغییر و گیت انجام می‌شود.

**وضعیت:** افزوده‌شده به شاخه؛ CI، ادغام، deploy Worker و بررسی ورود زنده در انتظار.


## ۲۰۲۶-۱۱-۰۸ — بازگشت cadence کانال به ۲۷ دقیقه و همگام‌سازی ویدئوهای فیلو

**هدف:** بازگرداندن فاصلهٔ انتشار کانال‌های OfferChin به ۲۷ دقیقه و ایجاد یک ویدئوی متناظر در فیلو برای هر رکوردی که واقعاً در یکی از کانال‌های فعال منتشر شده است؛ بدون تغییر سهمیه و زمان‌بندی YouTube/Aparat.

**تغییر/اقدام:**
- فاصلهٔ کانال در Cloudflare Worker، مقدار پیش‌فرض Python و هر دو ورودی cadence در workflow ناشر از ۳۷ به ۲۷ دقیقه بازگردانده شد. ساعت cadence از زمان واقعی آخرین ارسال موفق کانالی (last_channel_published_at) استفاده می‌کند؛ sidecar نیز این timestamp را حفظ می‌کند.
- فاصلهٔ مستقل فیلو از ۳ ساعت به ۲۷ دقیقه تغییر کرد؛ حداکثر یک ویدئو در هر اجرای فیلو پردازش می‌شود تا هر slot حداکثر یک submit داشته باشد. صف فیلو قدیمی‌ترین hand-off واجدشرایط را اولویت می‌دهد تا انتشارهای قبلی پشت پیشنهادهای جدیدتر جا نمانند.
- hand-off فیلو از موفقیت Telegram، Bale، Rubika یا Eitaa ساخته می‌شود. ارسال ناموفق کانال، صرفاً انتخاب محصول یا صف‌شدن آن، مجوز آپلود فیلو نیست.
- فیلو دیگر به deadline رسمی و مستقیماً تأییدشدهٔ خرده‌فروش نیاز ندارد؛ چون محصول قبلاً در مقصد کانالی با کنترل زندهٔ قیمت/موجودی تأیید شده است. تازگی ۲۴ساعته، رد آفر منقضی/نزدیک به انقضا، تأیید ورود حداکثر ۷روزه و منع retry خودکار پس از نتیجهٔ نامشخص حفظ شدند. گارد deadline سخت‌گیرانهٔ Aparat بدون تغییر باقی می‌ماند.
- state قدیمی فیلو با نسخهٔ سیاست ۲ به cadence جدید migrate می‌شود؛ فاصلهٔ قدیمی سه‌ساعته از آخرین attempt/submit معتبر به ۲۷ دقیقه بازحساب می‌شود. فیلدهای نتیجه و لینک فیلو هنگام retry همان delivery حفظ می‌شوند تا ارسال تکراری رخ ندهد.
- محدودیت ۳ساعته و سازوکار pause ناشی از quota در YouTube/Aparat تغییر نکردند. مقادیر FILO_USER و FILO_PASS فقط در GitHub Actions Secrets مصرف می‌شوند؛ هیچ مقدار credential در commit/log/doc قرار نمی‌گیرد.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/publisher.py، affilio_radar/test_affilio.py، affilio_radar/test_filo_upload_schedule.py، cloudflare/affilio-minute-dispatcher.js، cloudflare/affilio-minute-dispatcher.test.mjs، .github/workflows/offerchin-publisher.yml، .github/workflows/filo-video-upload.yml، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md و docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** تست‌ها برای cadence ۲۷دقیقه‌ای، مهاجرت slot سه‌ساعته، پذیرش hand-off چهار کانال، FIFO فیلو، حفظ idempotency در retry، gateهای deadline متفاوت Aparat/Filo و استفاده از زمان واقعی ارسال کانال به‌روزرسانی شدند. نتیجهٔ CI پس از ایجاد PR ثبت می‌شود؛ تا آن زمان این تغییرات ادغام یا مستقرشده محسوب نمی‌شوند.

**شواهد/شناسه:** شاخهٔ کاری feat/offerchin-27m-channel-filo-one-to-one-20261108. PR و شناسه‌های CI پس از اجرای workflowها ثبت خواهند شد.

**ریسک/بازگشت:** UI automation فیلو به تغییر فرم، CAPTCHA/OTP، محدودیت درخواست و moderation وابسته است؛ هر ۲۷ دقیقه یک submit سقف هدف است، نه تضمین پذیرش/انتشار عمومی در همین بازه. rollback با revert کردن PR ممکن است؛ migration state با نسخهٔ ۲ برای جلوگیری از بازگشت ناخواسته به slot قدیمی نگهداری می‌شود. نتیجهٔ upload_result_unknown نباید خودکار دوباره submit شود.

**وضعیت:** پیاده‌سازی و تست‌های رگرسیون در شاخهٔ مستقل؛ CI، بازبینی، ادغام، deploy و اولین تأیید انتشار عمومی فیلو در انتظار.


## ۲۰۲۶-۱۱-۰۸ — اجرای خودکار بررسی ورود فیلو بدون انتشار عمومی

**هدف:** حذف نیاز به اجرای دستی verify-login پس از تغییر workflow و جلوگیری از باقی‌ماندن گیت ورود فیلو بدون بررسی.

**تغییر/اقدام:** با هر تغییر فایل `.github/workflows/filo-video-upload.yml` روی main، workflow یک بررسی ورود verify-only اجرا می‌کند. برای رویداد push، مرحلهٔ آپلود صراحتاً غیرفعال است؛ آپلود فقط از مسیر workflow_dispatch و حالت upload انجام می‌شود. نتیجهٔ تأیید در state و sidecar Worker ذخیره می‌شود و فقط status/error غیرحساس در log چاپ می‌شود. مرحلهٔ دریافت لوگوی DigiPay نیز در verify-only رد می‌شود تا بررسی حساب به دسترس‌پذیری سایت ثالث وابسته نباشد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/filo-video-upload.yml`، `affilio_radar/affilio_radar.py`، `affilio_radar/test_filo_upload_schedule.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های انتقال status ورود به sidecar، تست‌های queue فیلو، رگرسیون Worker و دروازهٔ مستندات روی نسخهٔ نهایی PR اجرا می‌شوند؛ نتیجه پس از تکمیل CI ثبت خواهد شد.

**شواهد/شناسه:** PR #115، شاخهٔ `ops/offerchin-auto-verify-filo-login-20261108`.

**ریسک/بازگشت:** این مسیر هیچ ویدئوی آزمایشی منتشر نمی‌کند و CAPTCHA/OTP یا سایر کنترل‌های امنیتی را دور نمی‌زند. در صورت شکست ورود، وضعیت failed به Worker می‌رسد و آپلود متوقف می‌شود. rollback با revert کردن PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ PR؛ پس از merge، workflow به‌طور خودکار verify-only اجرا می‌شود.


## ۲۰۲۶-۱۱-۰۸ — تکمیل مسیر انتقال تأیید ورود فیلو به Worker

**هدف:** اطمینان از اینکه نتیجهٔ verify-login فقط در state کامل ذخیره نشود و Cloudflare Worker نیز آن را در sidecar ببیند.

**تغییر/اقدام:** تابع ثبت نتیجهٔ ورود اکنون sidecar ویدئو را از state به‌روز می‌سازد و هر دو فایل را ذخیره می‌کند؛ هم در تأیید موفق و هم در شکست ورود. برای این انتقال تست واحد اضافه شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_filo_upload_schedule.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست جدید بررسی می‌کند وضعیت verified و زمان آن در sidecar ذخیره شوند؛ آزمون‌های کامل PR #115 روی نسخهٔ نهایی در حال اجرا هستند.

**شواهد/شناسه:** PR #115، شاخهٔ `ops/offerchin-auto-verify-filo-login-20261108`؛ اجرای قبلی documentation gate در run `42420052282` فقط به‌دلیل ناقص‌بودن قالب ورودی قبلی شکست خورد و این ورودی ساختاریافته آن را اصلاح می‌کند.

**ریسک/بازگشت:** در صورت شکست ورود، وضعیت failed نیز در sidecar نوشته می‌شود و Worker انتشار فیلو را متوقف می‌کند؛ هیچ credential یا محتوای عمومی در این مرحله ارسال نمی‌شود. بازگشت با revert کردن PR ممکن است.

**وضعیت:** اصلاح کد و مستندات در شاخهٔ PR؛ CI نهایی در انتظار.


## ۲۰۲۶-۱۱-۰۸ — مستقل‌کردن verify-login فیلو از دانلود لوگوی فروشگاه

**هدف:** جلوگیری از شکست بی‌دلیل بررسی حساب فیلو به‌علت اختلال سایت لوگوی DigiPay.

**تغییر/اقدام:** مرحلهٔ دریافت لوگوی DigiPay فقط در workflow_dispatch حالت upload اجرا می‌شود؛ اجرای push/verify-login آن را skip می‌کند و مستقیماً مرحلهٔ بررسی ورود را انجام می‌دهد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/filo-video-upload.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** منطق شرط workflow به‌روزرسانی شد؛ تست‌های PR پس از این تغییر مجدداً اجرا می‌شوند.

**شواهد/شناسه:** PR #115، شاخهٔ `ops/offerchin-auto-verify-filo-login-20261108`.

**ریسک/بازگشت:** فقط مرحلهٔ جانبی دانلود لوگو در verify-only اجرا نمی‌شود؛ مسیر آپلود واقعی همچنان لوگو را دریافت می‌کند. rollback با revert PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ PR؛ CI نهایی در انتظار.


## ۲۰۲۶-۱۱-۰۸ — تشخیص امن علت غیرفعال‌ماندن دکمهٔ ورود فیلو

**هدف:** تعیین علت خطای `filo_login_submit_stayed_disabled` بدون افشای اطلاعات ورود یا اطلاعات شخصی حساب.

**تغییر/اقدام:** در صورت غیرفعال‌ماندن دکمهٔ ورود، آداپتر metadata ساختاری فیلدها، اعتبارسنجی HTML، دکمه‌ها، مسیر فرم و پرچم‌های OTP/CAPTCHA/تأیید موبایل را ثبت می‌کند. متن آزاد alertها و مقادیر واردشده ثبت نمی‌شوند؛ فقط طول مقدار و وضعیت اعتبارسنجی ذخیره می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/filo_uploader.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** compile و regression تست‌های Filo پس از ایجاد PR اجرا می‌شوند؛ تشخیص زندهٔ قبلی با کد `filo_login_submit_stayed_disabled` ثبت شد و sidecar در حالت `failed` باقی ماند.

**شواهد/شناسه:** GitHub Actions run `42420459788`؛ وضعیت Worker sidecar در commit شامل `filo_login_verification_status=failed` است.

**ریسک/بازگشت:** log فقط metadata ساختاری و دسته‌بندی خطا را می‌گیرد؛ رمز، شناسهٔ ورود، cookie، query string یا متن آزاد صفحه را چاپ نمی‌کند. این تغییر صرفاً تشخیصی است و هیچ تلاش برای دورزدن CAPTCHA/OTP یا submit خودکار اضافی انجام نمی‌دهد. rollback با revert PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ مستقل؛ تشخیص زنده پس از merge و اجرای verify-only بعدی انجام می‌شود.


## ۲۰۲۶-۱۱-۰۸ — انتخاب کنترل ورود فعال در فرم فیلو

**هدف:** جلوگیری از توقف ورود به‌علت انتخاب اولین submit غیرفعال در DOM، در حالی که ممکن است دکمهٔ ورود فعال دیگری وجود داشته باشد.

**تغییر/اقدام:** انتخاب submit اکنون ابتدا در فرم ورود و سپس در کل صفحه، فقط کنترل‌های قابل‌مشاهده و فعال را بررسی می‌کند. اگر هیچ دکمهٔ فعالی پیدا نشود، تشخیص ساختاریِ بدون مقدار محرمانه ثبت و workflow متوقف می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/filo_uploader.py`، `affilio_radar/test_filo_uploader.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست واحد جدید انتخاب دکمهٔ فعال را در حضور submit غیرفعال پوشش می‌دهد؛ تست‌های compile و Filo regression پس از ایجاد PR اجرا می‌شوند.

**شواهد/شناسه:** GitHub Actions run `42420459788`، خطای قبلی `filo_login_submit_stayed_disabled`.

**ریسک/بازگشت:** هیچ کلیک نهایی یا submit جدیدی خارج از دکمهٔ فعال فرم انجام نمی‌شود؛ CAPTCHA/OTP دور زده نمی‌شود. rollback با revert PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ مستقل؛ پس از CI، یک بررسی ورود دیگر اجرا خواهد شد.


## ۲۰۲۶-۱۱-۰۸ — اجرای مجدد خودکار verify-login پس از تغییر آداپتر فیلو

**هدف:** پس از هر اصلاح در کد ورود فیلو، همان حساب واقعی بدون اقدام دستی دوباره بررسی شود.

**تغییر/اقدام:** مسیر trigger پوش workflow verify-only علاوه بر خود فایل workflow، فایل `affilio_radar/filo_uploader.py` را نیز شامل می‌شود؛ تغییر آداپتر پس از merge یک اجرای push verify-only ایجاد می‌کند و مرحلهٔ upload در رویداد push همچنان غیرفعال می‌ماند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/filo-video-upload.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های workflow، آداپتر و دروازهٔ مستندات در PR #116 اجرا می‌شوند؛ پس از merge، GitHub Actions یک بررسی واقعی login بدون انتشار انجام خواهد داد.

**شواهد/شناسه:** PR #116، شاخهٔ `fix/offerchin-filo-login-form-diagnostics-20261108`.

**ریسک/بازگشت:** فقط verify-only در push اجرا می‌شود؛ مرحلهٔ upload فقط از workflow_dispatch حالت upload مجاز است. rollback با revert PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ PR؛ CI و اجرای مجدد verify-only در انتظار.


## ۲۰۲۶-۱۱-۰۸ — رفع race مربوط به hydration فرم ورود فیلو

**هدف:** رفع شکست تأیید ورود فیلو که در آن دو ورودی login پس از پرشدن خالی می‌شدند، بدون تکرار ارسال یا دورزدن کنترل امنیتی.

**تغییر/اقدام:** آداپتر پیش از پرکردن فیلدها منتظر اتصال handler واقعی Vue `v-model` با شناسهٔ `Symbol("_assign")` به هر دو ورودی می‌ماند. در صورت آماده‌نشدن فرم، با کد غیرحساس `filo_login_form_not_hydrated` متوقف می‌شود. Tab مصنوعی پس از fill حذف شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/filo_uploader.py`، `affilio_radar/test_filo_uploader.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست رگرسیون پلتفرم/ویدئو موفق شد؛ در تست نخست، واحد جدید به دلیل نبود Playwright در محیط تست عادی خطا داد، سپس وابستگی اختیاری حذف و تست در اجرای دوم موفق شد. دروازهٔ مستندات پس از تکمیل قالب changelog دوباره اجرا می‌شود. آزمون ورود زنده پس از merge باید دسترسی واقعی به `/upload` را تأیید کند.

**شواهد/شناسه:** اجرای verify-only شمارهٔ `42440343526` نشان داد `valueLength=0` برای username و password و `captcha=false`، `otp=false`؛ خطای قبلی `filo_login_submit_stayed_disabled` به علت hydration زودهنگام بود. PR #118.

**ریسک/بازگشت:** رمز، شناسهٔ ورود، cookie و token در لاگ ثبت نمی‌شوند. CAPTCHA/OTP دور زده نمی‌شود. اجرای push همچنان verify-only است و مرحلهٔ upload در آن اجرا نمی‌شود. بازگشت با revert PR ممکن است.

**وضعیت:** اصلاح کد و تست پیاده‌سازی شده؛ تست رگرسیون کد موفق است؛ اصلاح قالب مستندات ثبت شد؛ تأیید ورود واقعی و انتشار عمومی هنوز در انتظار اجرای verify-only بعد از merge است.


## ۲۰۲۶-۱۱-۰۸ — نتیجهٔ اجرای زندهٔ verify-only فیلو پس از اصلاح Vue

**هدف:** ثبت نتیجهٔ اعتبارسنجی واقعی حساب فیلو و جلوگیری از اعلام اشتباه انتشار عمومی.

**تغییر/اقدام:** اجرای verify-only پس از ادغام اصلاح hydration در PR #118 انجام شد. فرم این بار اطلاعات را نگه داشت و درخواست ورود به API فیلو رسید، اما پاسخ API با `filo_login_rejected` ثبت شد. به‌دلیل این پاسخ، مرحلهٔ پردازش صف اجرا نشد و status صف قفل باقی ماند.

**فایل‌ها/سامانه‌ها:** GitHub Actions در مخزن `Mehran0960/ai_news_bot`، آداپتر `affilio_radar/filo_uploader.py` و sidecar `affilio_radar/video_upload_dispatch_state.json`.

**آزمون و نتیجه:** تست‌های آداپتر و صف موفق بودند. ورود واقعی رد شد؛ آپلود ویدئو `skipped` بود و هیچ انتشار عمومی انجام نشد. sidecar با `filo_login_verification_status=failed`، زمان تأیید خالی و slot بعدی خالی ذخیره شد. در زمان بررسی ۲۵۰ رکورد موجود بود: ۱۴ مورد منقضی/نزدیک انقضا و ۲۳۶ مورد بدون وضعیت آپلود.

**شواهد/شناسه:** GitHub Actions run `42440801271`، job `128609426353`، خطای `filo_login_rejected`؛ sidecar commit `dd702f4cd9ae68ccafcebec41bbea0b352e4846a`.

**ریسک/بازگشت:** تلاش‌های ورود ناموفق تکرار نشوند تا از افزایش شمار خطا و فعال‌شدن CAPTCHA/قفل امنیتی جلوگیری شود. هیچ رمز، شناسهٔ ورود، cookie یا token ثبت نشده است. تا دریافت تأیید ورود و دسترسی به `/upload`، صف فیلو قفل بماند؛ بازگشت تغییرات مستنداتی با revert PR ممکن است.

**وضعیت:** کد اصلاح hydration ادغام شده و تست‌های آداپتر موفق‌اند؛ اعتبارنامه‌های ذخیره‌شده در GitHub Secrets توسط API فیلو رد شدند. انتشار عمومی فیلو هنوز فعال نشده و هیچ URL ویدئویی تأیید نشده است.

## 2026-11-08 — حفظ انتشار هنگام افزوده‌شدن دسته‌های جدید به کاتالوگ

**هدف:** جلوگیری از توقف کامل انتشار به‌دلیل اضافه‌شدن تعداد کمی دستهٔ جدید، در حالی که آخرین اسنپ‌شات کامل و hash-verified هنوز تازه و قابل‌استفاده است.

**تغییر/اقدام:** اعتبار اسنپ‌شات قبلی دیگر با هر تغییر افزایشی در فهرست دسته‌ها باطل نمی‌شود. اگر همهٔ شناسه‌های دستهٔ snapshot هنوز در کاتالوگ فعلی باشند، حداکثر ۱٪ دستهٔ جدید (با سقف ۵۰ دسته) تا زمان پیمایش کامل چرخهٔ جاری قابل‌تحمل است. حذف/جایگزینی دسته، عبور از بودجه، snapshot قدیمی‌تر از ۹۶ ساعت، hash نامعتبر یا چرخهٔ ناقص همچنان انتشار را مسدود می‌کند. همین قاعده در Python selector، loader و Cloudflare dispatcher اعمال شد. گاردهای rolling 24h خانواده، برند و شباهت و کنترل‌های قیمت/موجودی/لینک/ایمنی تغییری نکردند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/test_catalog_status_snapshot.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** آزمون‌های تازه، پذیرش دسته‌های افزودهٔ محدود، رد حذف/جایگزینی، رد عبور از بودجهٔ ۱٪/۵۰ و حفظ بررسی hash/provenance را پوشش می‌دهند. نتایج واقعی GitHub Actions پس از اجرای PR ثبت می‌شود.

**شواهد/شناسه:** در وضعیت مخزن هنگام طراحی اصلاح، آخرین چرخهٔ کامل در `2026-11-07T11:42:22Z` با ۴٬۹۱۶/۴٬۹۱۶ دسته، ۲۲۷٬۰۰۹ صفحه و ۴٬۴۷۴٬۰۴۷ ردیف محصول کامل شده بود؛ snapshot شامل ۳٬۰۰۰ نامزد و `last_cycle_candidate_snapshot_valid=true` بود. دو شناسهٔ دستهٔ جدید `11797` و `214186` باعث mismatch با مجموعهٔ فعلی ۴٬۹۱۸ دسته شده بودند؛ چرخهٔ بعدی در حال اجرا بود و آخرین وضعیت مشاهده‌شده ۴٬۶۷۶ دستهٔ کامل و ۲۴۲ صفحهٔ pending را نشان می‌داد. در نتیجهٔ mismatch، status، snapshot را unavailable علامت می‌زد و Cloudflare ناشر را dispatch نمی‌کرد.

**ریسک/بازگشت:** هنگام اضافه‌شدن دسته‌های جدید، تا سقف بودجه ممکن است پیشنهادهای آن دسته‌ها تا تکمیل sweep در shortlist نباشند؛ اما دسته‌های قبلی همچنان کامل و hash-verified هستند. حذف/جایگزینی دسته یا backlog بزرگ‌تر همچنان fail-closed است. بازگشت با revert همین PR ممکن است.

**وضعیت:** پیاده‌سازی و تست‌های رگرسیون در شاخهٔ PR؛ تأیید CI و انتشار روی `main` در انتظار.


## ۲۰۲۶-۱۱-۰۸ — رفع گرسنگی صف بررسی نامزدهای کاتالوگ

**هدف:** جلوگیری از هدررفتن بودجهٔ بررسی محصول وقتی نامزدهای بالای رتبه‌بندی بعداً به‌خاطر گارد تکرار ۲۴ساعته رد می‌شوند و اطمینان از اینکه کل shortlist کاتالوگ در صف جا می‌گیرد.

**تغییر/اقدام:** سقف صف کشف از ۱٬۰۰۰ به ۵٬۰۰۰ افزایش یافت و مقدار صریح هر دو workflow کشف و ناشر نیز هماهنگ شد. پیش از محدودکردن تعداد بررسی‌های جزئیات، مجموعهٔ کامل نامزدهای آماده با همان فیلتر خانواده/برند/شباهت ۲۴ساعته پالایش می‌شود؛ سپس تا سقف تنظیم‌شده، نامزدهای مجاز با حفظ ترتیب تخفیف و مبلغ صرفه‌جویی انتخاب می‌شوند. نامزدهای موقتاً مسدودشده از صف حذف نمی‌شوند. برند استخراج‌شده از کارت نیز در رکورد صف حفظ می‌شود.

**تغییر/اقدام ترب:** تشخیص challenge ترب بر اساس status code واقعی HTTP تقویت شد؛ 403/429/490 با status مشخص ثبت می‌شوند، cooldown محصول و توقف موقت سراسری اعمال می‌شود و بررسی‌های باقی‌مانده به اجراهای بعد منتقل می‌شوند. این منبع صرفاً تشخیصی است؛ نبود قیمت ترب مجوز کاهش کنترل قیمت زندهٔ فروشگاه یا انتشار نامعتبر نیست. منبع جایگزین تأییدنشده یا دورزدن anti-bot اضافه نشد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `.github/workflows/affilio-radar.yml`، `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**شواهد/شناسه:** گزارش اجرای قبلی ناشر، ۱۱ نامزد نهایی را نشان می‌داد که همگی در گارد ۲۴ساعته رد شده و انتخاب نهایی صفر شده بود؛ هم‌زمان ۳٬۰۰۰ نامزد در snapshot وجود داشت، اما سقف صف کشف فقط ۱٬۰۰۰ بود. PR #121 این دو گلوگاه را هدف می‌گیرد.

**آزمون و نتیجه:** تست‌ها برای انتخاب نامزد جایگزین پس از رد خانواده/برند، حفظ برند در صف، و طبقه‌بندی مستقل HTTP 490 افزوده شدند. نتیجهٔ CI، ادغام و استقرار پس از اجرای PR ثبت می‌شود.

**ریسک/بازگشت:** صف بزرگ‌تر می‌تواند فایل state را حجیم‌تر کند؛ سقف ۵٬۰۰۰ و TTL محدود ۲۴ساعته باقی می‌ماند. گارد ضدتکرار، کنترل قیمت/موجودی/لینک و شروط ایمنی تضعیف نشده‌اند. بازگشت با revert همین PR ممکن است.

**وضعیت:** پیاده‌سازی در شاخهٔ PR؛ CI، بازبینی، merge و deploy در انتظار.

## ۲۰۲۶-۱۱-۰۸ — اصلاح نام تست متمرکز workflow ناشر

**هدف:** جلوگیری از توقف workflow ناشر پیش از مرحلهٔ انتخاب محصول به‌علت فراخوانی نام قدیمی تست کشف.

**تغییر/اقدام:** مرجع تست متمرکز در `.github/workflows/offerchin-publisher.yml` از نام قدیمی `test_discovery_check_budget_is_discount_first_and_ignores_category_history` به نام جدید `test_discovery_check_budget_applies_24h_family_guard_before_budget` تغییر کرد؛ نام جدید با متد موجود در `affilio_radar/test_affilio.py` تطابق دارد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `affilio_radar/test_affilio.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**شواهد/شناسه:** اجرای ناشر #42445429205 در مرحلهٔ focused regression با `AttributeError: type object 'AffilioRadarTests' has no attribute 'test_discovery_check_budget_is_discount_first_and_ignores_category_history'` متوقف شد؛ خطا پیش از اجرای publisher.py و هرگونه ارسال کانالی رخ داد.

**آزمون و نتیجه:** CI باید focused regression suite ناشر و دروازهٔ مستندات را روی این اصلاح دوباره اجرا کند.

**ریسک/بازگشت:** فقط نام متد تست در workflow عوض شده است؛ رفتار production و گاردهای ضدتکرار بدون تغییرند. بازگشت با revert همین PR ممکن است.

**وضعیت:** اصلاح در شاخهٔ PR؛ CI، merge و اجرای بعدی ناشر در انتظار.

## ۲۰۲۶-۱۱-۰۸ — حفظ تحویل روبیکا پس از ردشدن inline keypad

**هدف:** جلوگیری از شکست کامل ارسال تصویر روبیکا وقتی API درخواست دارای دکمه‌های inline را با پاسخ صریح `INVALID_INPUT` رد می‌کند.

**تغییر/اقدام:** ارسال معمول با دو دکمهٔ لینک‌دار خرید و عضویت بدون تغییر باقی می‌ماند. فقط در صورت دریافت پاسخ صریح `INVALID_INPUT` از `sendFile`، یک بار دیگر همان فایل با کپشن متنی و دو URL معتبر خرید/عضویت ارسال می‌شود؛ دکمه‌ها در این مسیر جای خود را به لینک‌های قابل‌کلیک در متن می‌دهند. خطای شبکه، timeout، پاسخ مبهم یا هر خطای دیگر retry نمی‌شود تا از ارسال تکراری پس از نتیجهٔ نامعلوم جلوگیری شود. پاسخ موفق و message_id همچنان شرط ثبت `sent` است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `docs/CHANGELOG_FA.md` و `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**شواهد/شناسه:** اجرای ناشر #42445774346، محصول `dkp-6262614`: تلگرام و بله با شناسهٔ پیام واقعی موفق شدند؛ پاسخ روبیکا در `sendFile` برابر `INVALID_INPUT` بود. مستند رسمی روبیکا برای `sendFile`، فیلد `inline_keypad` را می‌پذیرد اما علت دقیق ردشدن payload در پاسخ عملیاتی موجود نبود؛ بنابراین منشأ دقیق ردشدن دکمه‌ها قطعی اعلام نمی‌شود.

**آزمون و نتیجه:** تست mock برای fallback پس از `INVALID_INPUT`، حفظ URL خرید و عضویت، نبود keypad در payload جایگزین و عدم retry برای خطاهای دیگر افزوده شد. این تست‌ها انتشار زنده را اثبات نمی‌کنند؛ تأیید نهایی نیازمند اجرای ناشر و مشاهدهٔ `delivery_status.rubika=sent` است.

**ریسک/بازگشت:** در حالت fallback، دو دکمهٔ اینلاین نمایش داده نمی‌شوند و URLها در کپشن درج می‌شوند. فقط پاسخ صریح ردشدن API اجازهٔ این مسیر جایگزین را می‌دهد. بازگشت با revert همین تغییر ممکن است.

**وضعیت:** شاخهٔ اصلاحی؛ اجرای تست‌ها، merge و مشاهدهٔ ارسال موفق روبیکا در انتظار.

## ۲۰۲۶-۱۱-۰۸ — نمایش آیکون خالص رسانه‌ها در تصاویر و ویدئوها

**هدف:** حذف نام نوشتاری پلتفرم‌ها از نشان‌های کنار شناسه‌های عمومی رسانه‌ها و یکسان‌سازی ظاهر همهٔ مقصدها.

**تغییر/اقدام:** رندرر مشترک، نشان‌های رسمی Bale، Rubika و Aparat را به نماد تصویری مستقل برش می‌دهد و از منبع رسمی YouTube فقط دکمهٔ قرمز پخش را نگه می‌دارد. رفتار برای تصاویر کانال‌ها و پوستر ویدئوها مشترک است؛ شناسه‌های متنی و لوگوهای فروشگاه/DigiPay تغییر نمی‌کنند. تست‌های رگرسیون و سند برندینگ نیز با قاعدهٔ icon-only هم‌راستا شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_visuals.py`، `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `affilio_radar/VISUAL_BRANDING.md`، `affilio_radar/assets/platform-logos/SOURCES.md`، `.github/workflows/sync-official-platform-logos.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** Workflow اختصاصی لوگو/ویدئو با موفقیت اجرا شد؛ رگرسیون عمومی OfferChin نیز موفق بود. در اجرای نخست Documentation Gate فقط به‌دلیل درج ورودی در جای غیرانتهایی فایل رد شد؛ ورودی به انتهای changelog منتقل شده و اجرای مجدد Gate لازم است.

**شواهد/شناسه:** شاخهٔ `fix/platform-icon-only-watermarks-2026-11-08`؛ شمارهٔ PR و commit نهایی پس از ایجاد ثبت می‌شوند.

**ریسک/بازگشت:** برش اشتباه می‌تواند بخشی از نماد رسمی را حذف کند؛ آزمون هندسهٔ آیکون‌ها و تناسب ابعاد پیش از merge الزامی است. بازگشت با revert همین PR ممکن است. هیچ تغییری در صف/تنظیم انتشار یا متن شناسه‌ها انجام نمی‌شود.

**وضعیت:** تغییر کد و تست لوگو/ویدئو موفق؛ در انتظار تأیید نهایی Documentation Gate و بررسی PR.

## ۲۰۲۶-۱۱-۰۸ — اصلاح محدودهٔ برش برای حفظ کامل نشان رسمی رسانه‌ها

**هدف:** اطمینان از اینکه حذف عنوان پلتفرم هیچ بخشی از خود نماد رسمی را قطع یا دگرگون نمی‌کند.

**تغییر/اقدام:** محدودهٔ رسمی Bale به تمام نماد سبز گفت‌وگو/تأیید، محدودهٔ Rubika به کل نشان چندرنگ و محدودهٔ Aparat به نشان تصویری کامل تنظیم شد. هیچ مسیر SVG، رنگ، شکل یا جزئیات لوگو بازطراحی نمی‌شود؛ فقط viewBox/crop برای حذف wordmark تغییر می‌کند. تست جدید برابری کامل path/fill/transform فایل اصلی و خروجی برش‌خورده را کنترل می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_visuals.py`، `affilio_radar/test_short_video.py`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** اجرای تست‌های لوگو/ویدئو، رگرسیون عمومی و Documentation Gate در PR؛ نتیجه پس از اجرا ثبت می‌شود.

**شواهد/شناسه:** شاخهٔ `fix/precise-official-platform-mark-crops-2026-11-08`؛ شمارهٔ PR پس از ایجاد ثبت می‌شود.

**ریسک/بازگشت:** برش اشتباه ممکن است بخشی از نماد را حذف کند؛ تست جدید محدوده و عدم تغییر artwork را کنترل می‌کند. بازگشت با revert همین PR ممکن است.

**وضعیت:** در انتظار CI و merge.


## ۲۰۲۶-۱۱-۰۸ — یکپارچه‌سازی فونت نوشته‌های فارسی و فاصلهٔ CTA ویدئو

**هدف:** یکدست‌کردن تایپوگرافی تمام نوشته‌های فارسی افزوده‌شده روی ویدئوهای محصول و واضح‌ترکردن سلسله‌مراتب عنوان/قیمت و محل راهنمای خرید.

**تغییر/اقدام:** متن فارسی عنوان، CTA، برچسب قیمت، مبلغ، tagline و متن نشان تخفیف در رندر ویدئو از همان فایل محلی Lalezar-Regular.ttf استفاده می‌کند که پیش‌تر برای عنوان محصول به‌کار می‌رفت. عنوان محصول و مبلغ فعلی با stroke هم‌رنگ، وزن بصری بیشتری از سایر نوشته‌ها دارند؛ فایل فونت یا لوگو بازطراحی نشده است. یک فاصلهٔ یک‌خطی میان CTA «لینک خرید: توضیحات کانال» و نخستین آیدی رسانه ایجاد شد. برای حفظ فاصله‌ها، پنل CTA بلندتر و کارت محصول و پنل قیمت ۲۲ پیکسل پایین‌تر منتقل شدند. فونت نشان تخفیف فقط برای رندر ویدئو override می‌شود؛ پوسترهای ثابت کانال‌ها از فونت قبلی خود استفاده می‌کنند.

**فایل‌ها/سامانه‌ها:** affilio_radar/short_video.py، affilio_radar/offerchin_visuals.py، affilio_radar/test_short_video.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** تست رگرسیون جدید باید یکسان‌بودن خانوادهٔ فونت تمام متن‌های فارسی، ضخیم‌تر بودن عنوان و قیمت، و فاصلهٔ ۴۸ پیکسلی مرکز CTA تا نخستین ردیف آیدی را کنترل کند؛ اجرای CI در انتظار است.

**شواهد/شناسه:** شاخهٔ fix/video-lalezar-overlay-typography-cta-spacing-2026-11-08؛ PR و commit نهایی پس از اجرای CI ثبت می‌شوند.

**ریسک/بازگشت:** افزایش ارتفاع پنل، مختصات محصول و پنل قیمت را جابه‌جا می‌کند؛ تست‌های رگرسیون مختصات لوگوی فروشگاه، تخفیف و دیجی‌پی به‌روزرسانی شده‌اند. بازگشت با revert همین تغییر ممکن است. فقط ویدئوهای رندرشده پس از ادغام از این تنظیمات استفاده می‌کنند؛ ویدئوهای منتشرشدهٔ قبلی خودکار تغییر نمی‌کنند.

**وضعیت:** پیاده‌سازی و تست‌ها در شاخه انجام شده؛ نتیجهٔ CI و ادغام در انتظار.

## ۲۰۲۶-۱۱-۰۸ — تثبیت رتبه‌بندی تخفیف‌محور و حذف گیت‌های تقاضا/محبوبیت

**هدف:** اجرای سیاست نهایی کاربر: انتخاب بالاترین تخفیف واقعی در کل کاتالوگ دیجی‌کالا، با مبلغ صرفه‌جویی به‌عنوان معیار دوم و سیگنال شتاب فروش فقط به‌عنوان ترجیح اختیاری در تساوی کامل.

**تغییر/اقدام:**
- رتبه‌بندی زنده و صف کشف به درصد تخفیف نزولی، سپس مبلغ صرفه‌جویی نزولی و فقط در تساوی دقیق این دو، پروکسی تازهٔ رشد تعداد نظرات محدود شدند. این پروکسی صراحتاً دادهٔ فروش نیست و نبود آن کاندیدا را حذف نمی‌کند.
- امتیاز popularity مبتنی بر lifetime review/rating، bestseller rank دسته و مسیر shadow demand/value از رتبه‌بندی/تصمیم‌گیری حذف شدند.
- امتیازدهی محصول دیگر از تعداد کل نظرات یا rating امتیاز تقاضا تولید نمی‌کند.
- اعتبار تخفیف با کنترل سازگاری ریاضی قیمت اصلی، قیمت فعلی، درصد و مبلغ صرفه‌جویی تقویت شد؛ هر تخفیف مثبت واقعی از ۱٪ می‌تواند رقابت کند.
- شواهد مثبت مستقل بازار/تاریخچه شرط انتشار نیستند؛ فقط تناقض تازه و معتبر قیمت بازار یا تاریخچه می‌تواند veto کند.
- fallback ناشر دیگر به رشد نظرات، bestseller rank یا تأیید مثبت بازار/تاریخچه وابسته نیست.
- تست‌های رتبه‌بندی، پروکسی رشد نظر، نبود popularity و fallback بدون دادهٔ تقاضا به‌روز شدند؛ Handbook و منشور هم با سیاست جدید هم‌راستا شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/publisher.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_selection_evidence.py`، `.github/workflows/offerchin-publisher.yml`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** روی commit اجرایی `08f10b5d8217b0b315fe54142e077e8e76d98c7e`، تمام بررسی‌های مرتبط GitHub Actions موفق شدند: تست Top-100/DigiPay، اسکن کاتالوگ، آداپتر پیام‌رسان، تست لوگو، Documentation Gate و اجرای کامل تست‌های code-push در Affilio Product Radar. شناسه‌های اجرا به‌ترتیب: `42469575963`، `42469576028`، `42469575962`، `42469575944`، `42469575985` و `42469571700`.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-discount-first-review-growth-tiebreak-2026-11-08`؛ PR شمارهٔ `127` در https://github.com/Mehran0960/ai_news_bot/pull/127 . commitهای اولیهٔ پیاده‌سازی: `e97141f0e4af5129d713664d4cd7cc7f211884ca`، `3a9d3ed9c8670a44559c32a2b9a9d4e5d1396e29` و `72e03f10b35d6fac68bd7b21fcf786d721ae4da2`.

**ریسک/بازگشت:** هر تغییر در tie-break می‌تواند فقط میان کالاهایی با درصد و صرفه‌جویی یکسان ترتیب را عوض کند. رشد نظر فقط پروکسی است و نباید به‌عنوان فروش گزارش شود. تغییرات روی شاخهٔ کاری انجام شده‌اند و تا merge روی `main` اثر زنده ندارند؛ بازگشت با revert commitهای این PR ممکن است. هیچ state، صف انتشار یا شناسهٔ پست موجود تغییر داده نشده است.

**وضعیت:** پیاده‌سازی روی شاخه و آزمون‌های مرتبط موفق است؛ PR هنوز به `main` ادغام نشده است. پیش از ادغام، branch باید با تغییرات state خودکار جدید `main` همگام شود؛ این تغییرات فقط فایل‌های state کاتالوگ و ممیزی را لمس کرده‌اند و در فایل‌های کد این PR تعارضی ثبت نشده است.



## ۲۰۲۶-۱۱-۰۸ — اصلاح CTA کپشن روبیکا و تثبیت نگارش نام OfferChin

**هدف:** همسان‌سازی واقعی پست روبیکا با Telegram/Bale و جلوگیری از نوسان حروف نام برند در خروجی‌های عمومی.

**تغییر/اقدام:**
- دعوت عضویت روبیکا از یک دکمهٔ دومِ صرفاً کی‌پدی به یک پیوند واقعی داخل کپشن با Rubika `metadata` از نوع `Link` منتقل شد.
- دکمهٔ خرید با لینک افیلیت معتبر به‌صورت دکمهٔ مستقل زیر پست باقی ماند.
- fallback در صورت `INVALID_INPUT` صریح، دو دکمهٔ لینک‌دار خرید و عضویت را نگه می‌دارد؛ خطای شبکه/مبهم retry نمی‌شود.
- تابع مرکزی `normalize_brand_display_name` افزوده شد و در کپشن‌های Telegram/Bale، عنوان کارت ویدئو، metadata YouTube/Aparat/Filo به کار می‌رود.
- URLها و usernameهای canonical مانند `rubika.ir/offerchin` و `youtube.com/@offerchin` عمداً حفظ می‌شوند؛ این‌ها نام نمایشی برند نیستند.
- تست آداپتور Rubika برای metadata لینک با offset/length واحد UTF-16، دکمهٔ خرید و fallback دو دکمه‌ای به‌روز شد؛ تست نرمال‌سازی نام برند و حفظ شناسه‌های کانال اضافه شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/messenger_adapters.py`، `affilio_radar/test_messenger_adapters.py`، `affilio_radar/offerchin_copy.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `affilio_radar/aparat_uploader.py`، `affilio_radar/filo_uploader.py`، `.github/workflows/offerchin-platform-logo-tests.yml`، `affilio_radar/MESSENGER_EXPANSION_FA.md`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** روی commit `a1f8c207882e815496847091e027c67993580bbf`، همهٔ بررسی‌های مرتبط موفق شدند: آداپترهای پیام‌رسان (run `42503460912`)، تست کاتالوگ (run `42503460940`)، Top-100/DigiPay (run `42503460852`)، تست لوگو/ویدئو شامل `test_short_video.py`، `test_aparat_uploader.py` و تست‌های Filo (run `42503474509`)، Documentation Gate (run `42503460880`) و اجرای کامل Affilio Product Radar (run `42503436583`).

**شواهد/شناسه:** شاخهٔ کاری `fix/rubika-caption-link-and-offerchin-brand-case-20261108`؛ PR شمارهٔ `128` در https://github.com/Mehran0960/ai_news_bot/pull/128 .

**ریسک/بازگشت:** metadata لینک باید با offset و length دقیق UTF-16 هم‌خوان باشد؛ در پاسخ صریح INVALID_INPUT fallback دو دکمه‌ای فعال می‌شود. هیچ پیام عمومی یا محتوای منتشرشدهٔ قبلی ویرایش نشده است. بازگشت با revert همین PR ممکن است.

**وضعیت:** همهٔ تست‌های PR روی commit ثبت‌شده موفق‌اند؛ PR هنوز ادغام نشده است. پیش از merge باید stateهای خودکار تازهٔ main حفظ و شاخه با آخرین main همگام شود؛ سپس checkهای روی commit همگام‌شده باید دوباره موفق باشند.


## ۸ نوامبر ۲۰۲۶ — ایجاد «پکیج بهینه‌سازی OfferChin»

**نوع تغییر:** مستندسازی و ثبت نقشهٔ راه پیشنهادی؛ بدون تغییر رفتار runtime.

- سند جامع `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md` ایجاد شد تا پیشنهادهای مربوط به هدف تجاری و انتخاب محصول، طراحی تصاویر، ویدئوهای کوتاه، کپشن، اعتمادسازی، اندازه‌گیری کلیک/فروش و الگوبرداری رقابتی در یک مرجع قابل بازیابی جمع شوند.
- پیوند سند به README و راهنمای اصلی پروژه افزوده شد تا در گفتگوهای بعدی با عنوان «پکیج بهینه‌سازی OfferChin» قابل ارجاع باشد.
- سند صراحتاً پیشنهادها را از رفتار اجرایی فعلی جدا می‌کند. رتبه‌بندی جاری تخفیف‌محور، قالب‌های فعلی و تنظیمات انتشار با ایجاد این بسته تغییر نکرده‌اند.
- گام شروعِ کار مشترک، تصمیم‌گیری دربارهٔ هدف تجاری و معیار سنجش موفقیت است؛ سپس هر حوزه جداگانه بررسی، تصویب، آزمایش و مستند می‌شود.

**فایل‌ها:** `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md`، `README.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**وضعیت:** صرفاً مستندسازی؛ بدون تغییر کد، workflow، Worker، secret، متغیر محیطی یا مقصد انتشار.


## 2026-11-08 — اصلاح حروف نام برند در شناسه‌های فوتر تصویر و ویدئو

**هدف:** نمایش یکدست نام برند به شکل دقیق `OfferChin` در شناسه‌های رسانه‌ای چاپ‌شده روی تصاویر و پوستر ویدئوها، بدون تغییر شناسه‌های واقعی و URLهای عملیاتی.

**تغییر/اقدام:** تابع `platform_footer_label` اکنون فقط بخش پایانی handle را در متن نمایشی به `OfferChin` تبدیل می‌کند. در نتیجه متن روی خروجی شامل `rubika.ir/OfferChin` و `youtube.com/@OfferChin` خواهد بود؛ مقادیر canonical در `PUBLIC_CHANNEL_LINKS` و URLهای قابل‌استفاده توسط پلتفرم‌ها با casing قبلی باقی می‌مانند. تست‌های خروجی تصویر و ویدئو نیز بر همین اساس به‌روزرسانی شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_visuals.py`، `affilio_radar/test_short_video.py`، `affilio_radar/test_affilio.py`، `affilio_radar/VISUAL_BRANDING.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های Platform Logo Regression (run `42506192000`) و Top-100/DigiPay Regression (run `42506191999`) موفق شدند. اجرای Documentation Gate نخست به دلیل قالب تاریخ/فیلدهای همین ورودی رد شد؛ پس از اصلاح این ورودی، اجرای مجدد Gate در انتظار است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-brand-case-in-visual-channel-ids-20261108`؛ [PR #129](https://github.com/Mehran0960/ai_news_bot/pull/129)؛ head پیش از اصلاح قالب changelog: `3eb116607fc591b5f6fa5ac06c1e1a467603b202`.

**ریسک/بازگشت:** متن نمایشی تصویر ممکن است از نظر حروف بزرگ/کوچک با شکل canonical handle تفاوت داشته باشد؛ بنابراین فقط برچسب چاپ‌شده تغییر می‌کند و URL/API واقعی دست‌نخورده می‌ماند. بازگشت با revert کردن PR #129 امکان‌پذیر است. تصاویر و ویدئوهای قبلی به‌صورت عطف‌به‌ماسبق ویرایش نمی‌شوند.

**وضعیت:** اصلاح کد و تست انجام شده؛ دو workflow فنی موفق‌اند؛ اصلاح قالب مستندات برای اجرای مجدد Documentation Gate ثبت شد. ادغام در main هنوز انجام نشده است.


## ۲۰۲۶-۱۱-۰۹ — گارد تنوع پیش از انتخاب و بازیابی انتشار در حالت snapshot نامعتبر

**هدف:** جلوگیری از عبور چند کالای هم‌خانواده/هم‌برند/مشابه در یک نوبت انتخاب و جلوگیری از توقف کامل ناشر صرفاً به‌دلیل در دسترس نبودن snapshot کامل، در حالی که رجیستری دسته‌ها و کنترل زندهٔ محصول معتبرند.

**تغییر/اقدام:** گارد خانواده، برند و شباهت به مسیر انتخاب اصلی منتقل شد و روی کل فهرست نامزدها، شامل تمام fallbackها، پیش از hand-off اعمال می‌شود. طبقه‌بندی از شناسه/نام دستهٔ واقعی دیجی‌کالا، عنوان، برند و کاربرد محصول استفاده می‌کند. رد هر محصول با علت‌ها، شناسهٔ محصول مقایسه‌شده و metadata طبقه‌بندی ثبت می‌شود و گزارش تنوع شامل توزیع کاربرد/دستهٔ دیجی‌کالا و آمار ردها می‌شود. metadata دسته در رکورد تحویل نگهداری می‌شود. persistence ناشر نیز اصلاح شد تا `diversity_report.json` پس از `git reset --hard` از بین نرود. برای توقف فعلی، حالت جایگزین محدود اضافه شد: snapshot ناقص همچنان نامعتبر می‌ماند؛ فقط وقتی رجیستری کامل و بدون تکرار شناسه‌های دسته قابل‌اعتماد باشد، نامزدهای دارای شناسه/URL canonical دیجی‌کالا یا اسنپ‌شاپ وارد مسیر بررسی زندهٔ مجدد می‌شوند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/publisher.py`، `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/test_selection_evidence.py`، `affilio_radar/test_catalog_status_snapshot.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست regression برای سه کالای هم‌خانواده با برندهای متفاوت، تست تشخیص دسته/کاربرد، تست رجیستری دستهٔ کامل و تست Worker افزوده شد. اجرای واقعی Python unit tests، Node tests و GitHub Actions پس از ایجاد PR در انتظار است؛ هنوز نتیجهٔ موفقی ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/publication-diversity-and-safe-dispatch-20261109`؛ commitهای تغییر کد شامل `85bae64166d1d5a35cc83322d8a91502c8404f99`، `38ef7b496ef3b8c13aa8b54990238c011dc80aaa`، `e8428783f6644244e2aaaa94a7f8144d213ae6cc`، `254cea121f3530b6caeddef62937ed08147e262b`، `00ba98e1ed26e27bbdf45f82a00d4b9b52c52452`، `4db4c845151c6d801f2cd9393623abd71e397785`، `d293d932f071e0a1df4d342ce6aa030bf8d92bec`، `d3b5f1b8226616ef6e299ed6cf61f537536ec029` و `2049c4e780e465089a9b586e2e3053d7f4e052bb`. اجرای تولیدی ناشر/Worker هنوز تغییر نکرده است.

**ریسک/بازگشت:** حالت degraded می‌تواند صرفاً در صورت صحت رجیستری taxonomy فعال شود و اعتبار snapshot را جعل نمی‌کند؛ در صورت نامعتبر بودن registry همچنان fail-closed است. کنترل زندهٔ قیمت، موجودی، هویت و لینک افیلیت حذف نشده است. بازگشت کامل با revert PR/commitها و deploy نکردن Worker جدید ممکن است.

**وضعیت:** پیاده‌سازی و مستندسازی روی شاخهٔ مستقل انجام شده؛ اجرای CI، بازبینی نهایی، ادغام و deploy در انتظار است.

## ۲۰۲۶-۱۱-۰۹ — گذار به رتبه‌بندی تقاضامحور دیجی‌کالا، آزمایش A/B و گزارش انتساب

**هدف:** انتخاب محصول بر مبنای تقاضای واقعیِ قابل‌مشاهده در داده‌های خود دیجی‌کالا و منفعت مخاطب، مستقل از کمیسیون یا درآمد افیلیت؛ حفظ یک ترتیب واحد از اسکن کاتالوگ تا صف انتشار؛ آغاز اندازه‌گیری نسخه‌های خلاقه و کلیک بدون جعل CTR یا فروش.

**تغییر/اقدام:** 
- رتبهٔ پرفروش‌ترین دیجی‌کالا در مرتب‌سازی native با `sort=7` به سیگنال اصلی تقاضا تبدیل شد. رتبه‌های تازهٔ ۱ تا ۶۰، سطح‌بندی ۱–۱۰/۱۱–۳۰/۳۱–۶۰، تازگی ۲۴ ساعته، حضور در چند دسته و تاریخچهٔ محدود تغییر رتبه در اولویت قرار گرفتند.
- رشد تازهٔ تعداد نظرها به پروکسی ثانویه و تعداد نظر کل/امتیاز به زمینهٔ تاریخی ضعیف تبدیل شدند. تعداد قطعی فروش در اتصال عمومی فعلی موجود نیست و از رتبه یا نظر ساخته نمی‌شود. کلیک و درآمد افیلیت در رتبه‌بندی تقاضا دخالت ندارند.
- shortlist کاتالوگ، انتخاب اصلی، fallbackها و صف انتشار به ترتیب سراسری تقاضامحور تغییر کردند. پله‌های تخفیف فقط metadata گیت اعتبارسنجی‌اند و دیگر یک دستهٔ تخفیف را به‌صورت پنهان جلو نمی‌اندازند.
- metadata دسته و تاریخچهٔ رتبه از discovery تا live recheck و publisher حفظ شد. تشخیص کاربرد با taxonomy واقعی دیجی‌کالا گسترش یافت تا وابستگی بیش از حد به عنوان کالا و گروه `general` کاهش یابد. گاردهای خانواده/برند/شباهت بدون تغییر در نقش مستقل ضدتکرار باقی ماندند.
- تخصیص پایدار A/B برای هر محصول اضافه شد؛ نسخهٔ B تغییر محدود در تصویر کانال، کپشن و پوستر ویدئو دارد. شناسهٔ آزمایش و نسخه تا رکورد publisher حفظ می‌شوند.
- Worker رهگیری کلیک برای ثبت تجمیعی رسانه و نسخهٔ A/B توسعه یافت؛ /stats دادهٔ محصول/منبع/نسخه را گزارش می‌کند. مسیر خرید فقط بعد از health probe و تأیید قابلیت انتساب فعال می‌شود و در صورت عدم سلامت به URL مستقیم معتبر Affilio بازمی‌گردد.
- `performance_report.json` برای تعداد پست و کلیک ۳۰روزه به تفکیک رسانه/نسخه ساخته و در Workflow ناشر به persistence افزوده شد. چون impression، سفارش و کمیسیون رسمی هنوز متصل نیستند، CTR، فروش و کمیسیون `null` ثبت می‌شوند.
- پکیج بهینه‌سازی و Handbook به وضعیت مصوب/در حال اجرا به‌روزرسانی شدند؛ سیاست تخفیف‌محور ۸ نوامبر در Handbook به‌عنوان سابقهٔ superseded مشخص شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/publisher.py`، `affilio_radar/short_video.py`، `affilio_radar/affiliate-deal-radar-worker.js`، تست‌های `test_affilio.py`، `test_selection_evidence.py`، `test_catalog_sweep.py`، `test_parallel_catalog_sweep.py`، `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md` و `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های رگرسیون برای رتبهٔ مستقیم پرفروش‌ها، برتری تقاضا در برابر تخفیف بزرگ‌تر، حفظ ترتیب در صف انتشار، انتساب کلیک A/B و عدم جعل CTR/فروش افزوده/به‌روزرسانی شده‌اند. نتیجهٔ اجرای واقعی Python unit tests، Node Worker tests و GitHub Actions در زمان ثبت این ورودی هنوز در انتظار PR است؛ تا تکمیل CI هیچ موفقیت تستی ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ کاری `feat/offerchin-digikala-demand-optimization`. commitهای مهم این مرحله: `cb127fd` (رتبه‌بندی و طبقه‌بندی تقاضا)، `414cbed` (رتبه‌بندی shortlist کاتالوگ)، `5f74d2` (تاریخچه رتبه)، `86c3a85` (حفظ ترتیب تقاضا در انتخاب نهایی)، `07a7c6b` (گزارش عملکرد و A/B)، `c29258b` (حفظ metadata در publisher)، `9d6a3e5` و `e9ae656` (A/B ویدئو)، `907dd26` (اعلام قابلیت انتساب Worker) و `517ad7c` (هماهنگ‌سازی Handbook). PR و run ID پس از ایجاد/اجرا به همین ورودی تکمیل می‌شوند.

**ریسک/بازگشت:** رتبهٔ پرفروش، رتبهٔ نسبی در دسته است، نه تعداد فروش. نبود رتبهٔ تازه به‌صورت شواهد ناموجود/ضعیف تلقی می‌شود و باعث توقف سراسری نمی‌شود. کلیک، impression یا فروش یکسان نیستند. در صورت deploy نشدن یا ناسالم بودن Worker، لینک خرید مستقیم Affilio حفظ می‌شود. بازگشت کد با revert همین PR/commitها ممکن است؛ Worker فقط پس از آزمون redirect و stats در محیط production deploy شود.

**وضعیت:** پیاده‌سازی روی شاخهٔ مستقل انجام شده؛ CI/PR، ادغام در `main` و deploy Worker در انتظارند. رفتار تولیدی تا پیش از این مراحل تغییر نکرده است.

## ۲۰۲۶-۱۱-۰۹ — ادغام و استقرار تولیدی رتبه‌بندی تقاضامحور و انتساب کلیک

**هدف:** تکمیل rollout سیاست تقاضامحور دیجی‌کالا و زیرساخت آزمایش/انتساب، هماهنگ‌سازی اسناد مرجع و تأیید رفتار Worker در محیط production.

**تغییر/اقدام:**
- PR شمارهٔ ۱۳۵ با عنوان «OfferChin: demand-first DigiKala selection and performance attribution» در ساعت 04:56:20 UTC در `main` ادغام شد؛ merge commit برابر `10ad29a03771702137c7f51c32b694484bcad307` است.
- کد رتبه‌بندی تقاضامحور، تاریخچهٔ رتبه، حفظ ترتیب تا صف انتشار، طبقه‌بندی کاربرد، تخصیص A/B برای تصویر/کپشن/ویدئو، گزارش عملکرد و تست‌های مرتبط در main قرار گرفتند.
- Worker `affiliate-deal-radar` با Cloudflare API deploy شد؛ deployment ID برابر `ab6ae47e9f204c91bfd823caca497682` است. binding موجود KV با نام `CLICKS` و تنظیمات observability و redact کردن query string حفظ شدند.
- Workflow smoke به‌روزرسانی شد تا وجود `experimentAttribution` را در health، redirect امن لینک‌های Digikala/SnappShop، مسیر HEAD غیرشمارشی و schema تفکیک‌شدهٔ /stats را کنترل کند.
- Handbook، پکیج بهینه‌سازی و READMEهای ریشه و radar با سیاست جاری هماهنگ شدند. سیاست تخفیف‌محور قبلی به‌عنوان سابقهٔ تاریخی/منسوخ مشخص شد.

**فایل‌ها/سامانه‌ها:** `README.md`، `affilio_radar/README.md`، `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`، `.github/workflows/affilio-radar.yml`، `.github/workflows/offerchin-publisher.yml`، Cloudflare Worker `affiliate-deal-radar`.

**آزمون و نتیجه:** تست‌های Python و Node برای رتبه‌بندی، صف، fallback، A/B و attribution در CI مربوط به PR موفق شدند. Documentation Gate، Catalog Sweep، Platform Logo Regression، Messenger Adapter Regression و Product Radar روی merge commit موفق بودند. اجرای پس از deploy Product Radar در run `42564719064` با نتیجهٔ success، smoke check جدید health/experiment flag، redirect و آمار را با موفقیت گذراند. اسکن کاتالوگ پس از ادغام نیز در run `42564479942` موفق شد.

**شواهد/شناسه:** [PR #135](https://github.com/Mehran0960/ai_news_bot/pull/135)، merge commit `10ad29a03771702137c7f51c32b694484bcad307`، Cloudflare deployment `ab6ae47e9f204c91bfd823caca497682`، production smoke run `42564719064`. Documentation Gate روی merge commit در run `42564479969` موفق شد.

**ریسک/بازگشت:** رتبهٔ پرفروش سیگنال نسبی دسته است، نه تعداد قطعی واحدهای فروش. CTR به impression نیاز دارد و سفارش/فروش/کمیسیون فقط با خروجی رسمی افیلیو قابل ثبت‌اند؛ هیچ‌کدام از روی کلیک تخمین زده نمی‌شوند. در صورت ناسالم شدن Worker، health probe ناشر را به لینک مستقیم معتبر Affilio برمی‌گرداند. rollback کد با revert کردن merge commit/PR و rollback Worker با بازگرداندن نسخهٔ قبلی Worker انجام می‌شود؛ stateهای تاریخی و گزارش کلیک نباید پاک شوند.

**وضعیت:** PR ادغام شده، Worker مستقر و smoke test production موفق است. پایش عملکرد A/B، اتصال impression و دادهٔ رسمی سفارش/کمیسیون، کارهای بعدی‌اند.

## ۲۰۲۶-۱۱-۰۹ — تثبیت قرارداد کپشن در آزمایش A/B و تکمیل همگام‌سازی مستندات

**هدف:** حفظ متن فروش مصوب و یکسان در همهٔ مقصدها، در حالی که اثر تغییرات بصری A/B تصویر و ویدئو جداگانه اندازه‌گیری شود؛ هم‌راستا کردن وضعیت نهایی rollout در Handbook و پکیج بهینه‌سازی.

**تغییر/اقدام:**
- تغییر متن آغازین کپشن در بازوی B حذف شد. هر دو بازوی A و B اکنون از همان SALE_TITLE_PREFIX و بدنهٔ canonical کپشن استفاده می‌کنند.
- تفاوت آزمایش A/B به تصویر محصول و پوستر/ویدئوی عمودی محدود شد؛ لوگوهای رسمی، ترتیب/عبارت قیمت و تخفیف، جملهٔ دیجی‌پی، CTA عضویت و دکمهٔ خرید ثابت باقی می‌مانند.
- تست test_visual_experiment_variants_preserve_the_approved_caption اضافه شد و برابری کامل خروجی A/B کپشن و حفظ پیشوند تأییدشده را بررسی می‌کند.
- Handbook و پکیج بهینه‌سازی با این محدودیت و نتیجهٔ smoke تولیدی به‌روزرسانی شدند؛ وضعیت قدیمی «در انتظار deploy/smoke» در بخش وضعیت جاری اصلاح شد.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/test_affilio.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md و docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** تست واحد جدید متن یکسان کپشن برای A/B را بررسی می‌کند. باید اجرای تازهٔ Affilio Product Radar و Documentation Gate پس از ادغام این اصلاحیه موفق شود؛ نتیجهٔ این اجرا در زمان نگارش هنوز ثبت نشده است. smoke production قبلی run 42564719064 موفق بوده است.

**شواهد/شناسه:** main code commit 857f6c5db35033a812ae2a870a02d64778c35a95، test commit a8a43275c95d508dfb10010cfef2415650867935، package correction 2ded74776fd3b9d494cb87b43456efec71ae4163، PR ادغام rollout #135 و production smoke 42564719064.

**ریسک/بازگشت:** تغییر متن کپشن می‌تواند پیام مصوب، یکپارچگی رسانه‌ها یا انتساب A/B را مخدوش کند؛ به همین دلیل آزمایش فعلی فقط بصری است. بازگشت کد با revert همین PR/commit امکان‌پذیر است؛ نسخهٔ قبلی کپشن در هیچ‌یک از بازوها لازم نیست حفظ شود، چون متن جدیدی تصویب نشده است.

**وضعیت:** اصلاح متن کپشن و تست آن در main ثبت شده‌اند؛ این PR مستندسازی وضعیت نهایی و محدودیت آزمایش را همگام می‌کند. نتیجهٔ CI تازه پس از ادغام این مستندات و اصلاح کد در انتظار است.


## ۲۰۲۶-۱۱-۰۹ — سخت‌سازی گیت ناشر و پوشش taxonomy واقعی دیجی‌کالا

**هدف:** بستن خطای عملیاتی ناشر که آزمون را به‌علت نام تابع قدیمی متوقف می‌کرد و کاهش دسته‌بندی نادرست محصولات دیجی‌کالا در گروه عمومی.

**تغییرات:**
- فراخوانی Workflow ناشر از نام قدیمی test_click_tracker_preserves_supported_affilio_template به نام واقعی test_click_tracker_preserves_supported_affilio_template_and_adds_experiment_labels اصلاح شد.
- گیت ناشر، آزمون‌های بی‌اثر بودن کلیک/امتیاز مصنوعی بر رتبهٔ تقاضا، تخصیص پایدار A/B، یکسان ماندن کپشن دو بازو و عدم استنتاج CTR/فروش/کمیسیون از کلیک را نیز اجرا می‌کند.
- طبقه‌بندی کاربرد با نگاشت دقیق‌تر taxonomy واقعی دیجی‌کالا گسترش یافت؛ برای نمونه ابزار و ایمنی، مراقبت شخصی و آرایش، بازی فکری، سلامت/مکمل، خوراکی، خانه، پوشاک، ورزش، اداری، سفر و خودرو. دستهٔ موجود ولی نگاشت‌نشده با catalog_taxonomy_other از فقدان کامل داده (general) جدا می‌شود.
- ترتیب رتبه‌بندی بر اساس دادهٔ خود دیجی‌کالا حفظ می‌شود؛ هیچ منبع بیرونی برای ادامهٔ اسکن/انتخاب/انتشار اجباری نیست.

**محدودیت و اندازه‌گیری:** رتبهٔ پرفروش یک رتبهٔ نسبی در دسته است، نه تعداد واحدهای فروش. بدون impression، CTR قابل محاسبه نیست؛ فروش و کمیسیون نیز فقط با گزارش رسمی افیلیو ثبت می‌شوند. هیچ‌یک از این مقادیر از روی کلیک حدس زده نمی‌شود.

**آزمون:** تست taxonomy برای نمونه‌های واقعی دسته‌های دیده‌شده در گزارش تنوع افزوده شد؛ تست‌های رتبه‌بندی، A/B و report integrity در گیت ناشر فراخوانی شدند. نتیجهٔ CI این پیگیری باید پس از اجرای PR ثبت شود.


**تغییر/اقدام:** نام تست قدیمی در Workflow ناشر اصلاح شد؛ تست‌های تقاضا، تخصیص A/B، برابری کپشن و صحت گزارش عملکرد به preflight اضافه شدند. طبقه‌بندی کاربرد با نمونه‌های پرتکرار taxonomy دیجی‌کالا گسترش یافت و گیت CI یک بررسی ایستا برای تطبیق همهٔ نام‌های تست ارجاع‌شده در Workflow ناشر با متدهای واقعی اضافه کرد.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/test_selection_evidence.py، .github/workflows/offerchin-publisher.yml، .github/workflows/affilio-radar.yml، docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md و docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** اجرای PR شمارهٔ ۱۳۷ در run شمارهٔ 42593763247 شامل مجموعهٔ Python و تست‌های Node Worker موفق شد؛ runهای کاتالوگ، لوگو و آداپتر پیام‌رسان نیز موفق شدند. گیت مستندسازی در run شمارهٔ 42593763081 به‌علت ناقص بودن قالب همین ورودی متوقف شد و قالب در این اصلاحیه تکمیل شده است. اجرای کامل شاخه شامل cross-check نام تست‌های Workflow و Documentation Gate پس از این اصلاحیه باید مجدداً تأیید شود.

**شواهد/شناسه:** PR شمارهٔ ۱۳۷، commit طبقه‌بندی دوتداخل‌زدایی‌شده d13b81d0a985ea3b7205430a4dada4fa5b7ed378، commit گیت ایستای Workflow برابر 603dc04bb09b72df31104a53809423e8da15e5df، run Python/Node برابر 42593763247 و run Documentation Gate برابر 42593763081.

**ریسک/بازگشت:** نگاشت‌های کاربرد مبتنی بر دادهٔ عنوان و taxonomy دیجی‌کالا هستند و دستهٔ شناخته‌شدهٔ فاقد نگاشت با catalog_taxonomy_other مشخص می‌شود؛ در صورت طبقه‌بندی نادرست می‌توان نگاشت یا کل PR را revert کرد. هیچ مقدار فروش واحدی از رتبهٔ پرفروش یا نظرها تخمین زده نمی‌شود. بازگشت گیت ناشر نیز با revert کردن تغییر Workflow ممکن است.

**وضعیت:** PR شمارهٔ ۱۳۷ هنوز برای بازبینی/تأیید CI باز است؛ تا ثبت نتیجهٔ موفق همهٔ گیت‌های آخرین SHA، ادغام نشده است.


## ۲۰۲۶-۱۱-۰۹ — اصلاح گزارش پوشش آزمایش و تثبیت شواهد تقاضای دیجی‌کالا

**هدف:** شفاف‌کردن تفاوت میان قابلیت فنی رهگیری کلیک و اجرای واقعی آزمایش A/B؛ جلوگیری از اثرگذاری کمیسیون افیلیت بر رتبه‌بندی تقاضا؛ تثبیت صحت سیگنال پرفروش دیجی‌کالا.

**تغییر/اقدام:** docstringها و commentهای قدیمیِ ناسازگار با رتبه‌بندی تقاضامحور اصلاح شدند. گزارش عملکرد اکنون تعداد محصولات منتشرشده، پست‌های دارای بازوی A/B، رکوردهای بدون بازو، پوشش انتساب، کلیک‌های برچسب‌خورده و کلیک‌های بدون برچسب را جداگانه ثبت می‌کند. قابلیت Worker از فعال‌بودن واقعی آزمایش تفکیک شده است؛ پست و کلیک تاریخی به‌صورت فرضی به A یا B منتسب نمی‌شوند. تست مستقل نیز تضمین می‌کند کمیسیون یا درآمد افیلیت نتواند رتبهٔ تقاضا را تغییر دهد. shortlist اسکن موازی تستی دارد که تقدم رتبهٔ native پرفروش بر تخفیف بزرگ‌تر را ثابت می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_sweep.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `.github/workflows/offerchin-publisher.yml`، `affilio_radar/performance_report.json`، `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** چهار اجرای Product Radar روی commitهای کد و تست این شاخه با نتیجهٔ success تمام شدند؛ syntax، regression tests، smoke test Worker و مراحل persistence موفق بودند. گیت PR برای مستندات و بررسی نهایی آخرین SHA هنوز در انتظار است. اجرای قبلی ناشر پس از PR #137 نیز در run `42595183315` موفق بود.

**شواهد/شناسه:** PRهای ادغام‌شدهٔ #135 و #137؛ merge commit PR #137 برابر `d4d118727d4a4944120536306635c1ada11256cc`. snapshot عملکرد `2026-11-09T09:44:39Z`: ۸۷۴ رکورد منتشرشده، صفر رکورد A/B، ۹۲ کلیک روی ۴۶ محصول، صفر کلیک tagشده. پاسخ زندهٔ endpoint دیجی‌کالا برای دستهٔ ۶۰۴۲، `data.sort_options` را با id=7 برابر «پرفروش‌ترین» و id=4 برابر «پربازدیدترین» نشان داد؛ درخواست sort=5 پاسخ 404 داشت. اجرای regression این شاخه: `42597959867`، `42597954282`، `42597938914` و `42597932748`.

**ریسک/بازگشت:** رتبهٔ پرفروش دیجی‌کالا رتبهٔ نسبی دسته است، نه تعداد مطلق واحد فروش. impression، CTR، سفارش، فروش و کمیسیون فقط با دادهٔ رسمی متناظر قابل محاسبه‌اند. هیچ سابقهٔ click یا پست قدیمی به نسخهٔ آزمایشی منتسب نمی‌شود. rollback کد با revert کردن PR این شاخه ممکن است؛ دادهٔ تاریخی حفظ می‌شود.

**وضعیت:** PR #138 باز است؛ تست‌های کد موفق‌اند و گیت مستندات/CI نهایی و merge همچنان pending است.


## ۲۰۲۶-۱۱-۰۹ — آزمایش مستقل کپشن A/B و انتساب دوگانهٔ Worker

**هدف:** سنجش جداگانهٔ اثر تصویر/ویدئو و اثر متن کپشن، بدون مخلوط کردن دو متغیر و بدون دست‌کاری قیمت، تخفیف یا سایر واقعیت‌های پیشنهاد.

**تغییر/اقدام:**
- شناسه و تخصیص پایدار جدا برای آزمایش کپشن اضافه شد؛ تخصیص بصری قبلی بدون تغییر معنایی حفظ شد.
- نسخهٔ B کپشن فقط تیتر آغازین را از «🔥 فروش ویژه» به «✨ پیشنهاد ویژه» تغییر می‌دهد. نام محصول، قیمت جاری، درصد تخفیف، عبارت DigiPay، عضویت و دکمهٔ خرید در دو نسخه ثابت‌اند.
- لینک رهگیری دو بُعد مستقل `exp/variant` و `cexp/cvariant` را منتقل می‌کند. Telegram، Bale و لینک خرید توضیحات ویدئو هر دو tag را حفظ می‌کنند.
- Worker نسخهٔ جدید رویدادهای دوگانه را می‌خواند و در `/stats` شمارش بصری و کپشن را جدا برمی‌گرداند؛ کلیک هر رویداد در total فقط یک بار شمرده می‌شود و schema قدیمی برای legacy clicks حفظ شده است.
- گزارش عملکرد پوشش پست و کلیک‌های tagشده/بدون tag را برای آزمایش بصری و متنی به‌صورت مستقل گزارش می‌کند. پست‌های قدیمی backfill یا حدس زده نمی‌شوند.
- health probe و smoke workflow وجود هر دو قابلیت Worker را کنترل می‌کنند؛ در صورت عدم سلامت Tracker، لینک مستقیم معتبر Affilio همچنان مسیر fallback است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/publisher.py`، `affilio_radar/affiliate-deal-radar-worker.js`، `affilio_radar/test_affilio.py`، `affilio_radar/test_affiliate_deal_radar_worker.mjs`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/affilio-radar.yml`، `docs/OFFERCHIN_OPTIMIZATION_PACKAGE_FA.md` و `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های جدید Python و Node به گیت ناشر اضافه شدند؛ smoke workflow health flags، redirect امن و breakdownهای جداگانهٔ `visualExperimentVariants` و `captionExperimentVariants` را بررسی می‌کند. تا زمان اجرای CI روی آخرین SHA، نتیجه هنوز تأییدشده نیست.

**شواهد/شناسه:** شاخهٔ کاری `feat/offerchin-caption-attribution-dual-ab`. commitهای اصلی پیاده‌سازی: `6e56eb5351d47efcd0c3d9242025520ecefd0032` (Worker dual attribution)، `2c57c2164065a92ba4e8ee8d72044b4cf124a8f8` (Python assignment/report)، `e394be08de96a55f38a4e1ed6a05ca0de5a49780` (queue persistence).

**ریسک/بازگشت:** متن B باید از نظر نگارش و اثر بر اعتماد/کلیک پایش شود؛ بدنهٔ factual و CTA عمداً ثابت مانده است. در صورت شکست آزمایش، می‌توان فقط تخصیص کپشن را به A برگرداند یا commit مربوط را revert کرد؛ schema قدیمی Worker و داده‌های کلیک قبلی حذف نمی‌شوند. CTR بدون impression و فروش/کمیسیون بدون گزارش رسمی افیلیو محاسبه نمی‌شوند.

**وضعیت:** کد، تست‌ها و مستندات در شاخهٔ کاری ثبت شده‌اند. CI، merge به `main` و deploy نسخهٔ Worker دو‌بُعدی هنوز pending هستند؛ تا آن زمان قابلیت جدید در production فعال تلقی نمی‌شود.

## ۲۰۲۶-۱۱-۰۹ — قرارداد snapshot تقاضامحور و پیش‌نمایش آفر ممتاز روزانه

**هدف:** هم‌راستاسازی validator با ترتیب تقاضامحور اسکنر، و فراهم‌کردن shortlist فشرده برای معرفی حداکثر یک آفر ممتاز در روز.

**تغییر/اقدام:** snapshotهای جدید اسکنر موازی با `candidate_order_policy=catalog_demand_first_v1` علامت‌گذاری می‌شوند. validator برای این policy ترتیب فهرست را بر اساس تخفیف بازتفسیر نمی‌کند؛ برای snapshotهای قدیمی فاقد policy، قرارداد legacy تخفیف‌محور حفظ می‌شود. فایل وضعیت، در صورت snapshot کامل، تازه و hash-verified با policy صریح demand-first، پیش‌نمایش حداکثر ۱۰۰ نامزد اول را در `top_candidates_preview` ارائه می‌کند؛ در snapshot نامعتبر/legacy این پیش‌نمایش خالی است. سند جداگانهٔ آفر ممتاز روزانه اضافه شد: یک گزینهٔ استثنایی یا اعلام نبود گزینه، تحویل ساعت ۱۸:۰۰ تهران و زمان انتشار آزمایشی جداگانه.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_catalog_status_snapshot.py`، `README.md`، `docs/OFFERCHIN_DAILY_FEATURED_OFFER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های رگرسیون برای non-monotonic discount زیر policy demand-first، رد policy ناشناخته، preview فقط از snapshot معتبر و عدم نمایش preview از snapshot نامعتبر/legacy اضافه شدند؛ اجرای CI در انتظار است.

**شواهد/شناسه:** شاخهٔ `feat/offerchin-daily-featured-offer-current-main-20261109`؛ PR و SHA پس از ایجاد ثبت می‌شوند.

**ریسک/بازگشت:** snapshot legacy برای گیت عضویت کاتالوگ قابل ارزیابی می‌ماند اما preview تقاضامحور از آن صادر نمی‌شود. انتشار آگهی بیرونی و publisher کانال‌ها تغییر نکرده‌اند. بازگشت با revert همین PR ممکن است.

**وضعیت:** تغییرات شاخه ثبت شده؛ CI در انتظار اجرا.

## ۲۰۲۶-۱۱-۰۹ — جداسازی قفل CI اعتبارسنجی PR از اسکن زندهٔ کاتالوگ

**هدف:** جلوگیری از قرارگرفتن تست‌های code-only یک PR پشت اجرای طولانی اسکن read-only کاتالوگ.

**تغییر/اقدام:** در workflow اسکن کاتالوگ، PR validation اکنون از concurrency group مستقل `offerchin-digikala-catalog-sweep-pr-v1` استفاده می‌کند؛ اجرای main و workflow_dispatch همچنان در گروه عملیاتی موجود `offerchin-digikala-catalog-sweep-v3` سریالی می‌مانند. صف، workerها، cadence، retry و منطق crawler تغییر نکرده‌اند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-digikala-catalog-sweep.yml`، این changelog و handbook.

**آزمون و نتیجه:** اجرای PR قبلی در گروه مشترک pending بود؛ اجرای مجدد پس از جداسازی گروه در انتظار GitHub Actions است.

**شواهد/شناسه:** PR #142، branch `feat/offerchin-daily-featured-offer-current-main-20261109`.

**ریسک/بازگشت:** فقط قفل‌های validation و crawler از هم جدا شده‌اند؛ PR همچنان py_compile و regression tests را اجرا می‌کند. بازگشت با revert تغییر concurrency block ممکن است.

**وضعیت:** تغییر شاخه ثبت شد؛ CI مجدد در انتظار.

## ۲۰۲۶-۱۱-۰۹ — اصلاح برچسب ترتیب رتبه‌بندی در گزارش اسکنر

**هدف:** یکسان‌سازی telemetry و handbook با رفتار واقعی رتبه‌بندی کاتالوگ.

**تغییر/اقدام:** برچسب انتهای `PARALLEL_CATALOG_SWEEP_SUMMARY` از `discount_percent_desc,savings_toman_desc` به `demand_score,bestseller_rank,discount_percent,savings_toman` تغییر کرد. کد واقعی `catalog_candidate_sort_key` و `retain_diverse_candidates` پیش از این demand-first بود؛ این اصلاح الگوریتم را تغییر نمی‌دهد و صرفاً جلوی گزارش گمراه‌کننده را می‌گیرد. بندهای جاری handbook که هنوز discount-first می‌گفتند با سیاست ۹ نوامبر هم‌راستا شدند. تست منبع‌سطحی جدید مانع بازگشت برچسب قدیمی می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست Catalog Sweep Regression برای label واقعی اضافه شد؛ اجرای CI در انتظار است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-demand-first-sort-telemetry-docs-20261109`؛ PR و SHA پس از ایجاد ثبت می‌شوند. اجرای عملیاتی پیشین run `42666232145`، پس از پردازش ۴۸۰ صفحه، برچسب قدیمی را در لاگ نشان داد؛ کد مرتب‌سازی در `catalog_sweep.py:catalog_candidate_sort_key` و `retain_diverse_candidates` demand-first بود.

**ریسک/بازگشت:** فقط telemetry و متن سیاستی مستندات عوض می‌شوند؛ صف، رتبه‌بندی واقعی، snapshotها، publisher و cadence کانال‌ها تغییر نمی‌کنند. بازگشت با revert همین PR ممکن است.

**وضعیت:** شاخهٔ اصلاحی آمادهٔ CI؛ merge و اجرای عملیاتی پس از آن در انتظار.


## ۲۰۲۶-۱۱-۰۹ — افزایش کنترل‌شدهٔ ظرفیت و سنجش تأخیر اسکن کاتالوگ

**هدف:** کوتاه‌کردن زمان چرخهٔ جامع دیجی‌کالا بدون افزایش خطر HTTP 429، حذف صفحه از صف یا تولید snapshot ناقص.

**تغییر/اقدام:** کنترل تطبیقی ظرفیت پس از batch پاک به‌جای یک Worker، دو Worker افزایش می‌دهد تا نقاط ۱۲، ۱۴ و ۱۶ سریع‌تر سنجیده شوند. 429 منفرد باعث کاهش دو Worker؛ سه یا بیشتر 429 یا retry باعث نصف‌شدن ظرفیت؛ و retry موقت دیگر باعث کاهش یک Worker می‌شود. مدت end-to-end درخواست/parse برای هر صفحه ثبت و صدک‌های p50/p95/max به‌همراه شمار timeout و HTTP 5xx در state، status snapshot و لاگ خلاصه منتشر می‌شوند. سقف ۱۶ Worker و batch فعلی ۴۸۰ صفحه حفظ شده‌اند؛ اجرای چند Runner و افزایش اندازهٔ batch تا دریافت شواهد پایدار به تعویق افتاده‌اند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `affilio_radar/test_catalog_status_snapshot.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** regression test برای مسیر پاک ۱۲→۱۴→۱۶، سقف Worker، backoff در 429 و retry موقت، و صدک‌های تأخیر افزوده شده است؛ اجرای CI این شاخه هنوز باید نتیجه بدهد. پیش از تغییر، run عملیاتی `42674869281` تعداد ۴۸۰/۴۸۰ صفحه را در ۳۱٫۵ ثانیه با ۱۱ Worker واقعی و ۱۵٫۵۴ صفحه در ثانیه، بدون 429 و retry، ثبت کرده بود.

**شواهد/شناسه:** مبنای تغییر main در SHA `472b02a0162e71a6228c87def25d2611ccac7d21`؛ شاخهٔ کاری `perf/offerchin-catalog-adaptive-throughput-20261109`؛ run عملیاتی مرجع [42674869281](https://github.com/Mehran0960/ai_news_bot/actions/runs/42674869281).

**ریسک/بازگشت:** افزایش دو‌تایی ممکن است در بار بالاتر پاسخ منبع را کند یا 429 ایجاد کند؛ کنترل جدید در مواجهه با این علائم ظرفیت را کاهش می‌دهد و صف و checkpoint را حفظ می‌کند. سقف worker را می‌توان با تغییر مقدار workflow محدود کرد؛ بازگشت کامل نیز با revert همین PR ممکن است. هیچ تغییری در انتشار، ترتیب انتخاب محصول، pagination یا دادهٔ صف انجام نشده است.

**وضعیت:** تغییرات روی شاخهٔ مستقل ثبت شده‌اند؛ CI، ادغام و تأیید رفتار عملیاتی در نقاط ۱۲، ۱۴ و ۱۶ در انتظارند.

## ۲۰۲۶-۱۱-۰۹ — تثبیت پله‌های آزمایش ظرفیت ۱۲، ۱۴ و ۱۶ Worker

**هدف:** اطمینان از اینکه اجرای پاک پس از checkpoint قدیمی نیز نقاط آزمایشی ۱۲، ۱۴ و ۱۶ را دقیق و به‌ترتیب می‌سنجد.

**تغییر/اقدام:** اگر ظرفیت ذخیره‌شده پس از اجرای قبلی روی ۱۱ یا کمتر باقی مانده باشد، ramp پاک ابتدا با افزایش‌های دو‌تایی تا ۱۲ بالا می‌رود؛ سپس فقط پله‌های ۱۴ و ۱۶ را آزمایش می‌کند. در صورت محدودسازی یا retry، قواعد کاهش ظرفیت PR #144 بدون تغییر اولویت دارند. این اصلاح مانع رد شدن ناخواسته از نقطهٔ ۱۲ (مثلاً ۱۱→۱۳→۱۵) می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست رگرسیون اکنون مسیر ۱۱→۱۲→۱۴→۱۶، سقف‌های درخواستی پایین‌تر و backoff در خطا را کنترل می‌کند؛ اجرای CI این اصلاحیه در انتظار است.

**شواهد/شناسه:** PR #144 و merge commit `89f887805ebb9567e06524aa68165d594a1e476d`؛ وضعیت عملیاتی قبل از اصلاحیه، پس از batch ۴۸۰ صفحه‌ای با ۲ retry/429، ظرفیت بعدی را ۱۱ ثبت کرده بود (run `42675466948`).

**ریسک/بازگشت:** فقط انتخاب ظرفیت بعدی پس از batch پاک اصلاح شده است؛ queue، retry، pagination، snapshot، ranking و publication تغییر نمی‌کنند. در صورت نیاز با revert این PR امکان بازگشت وجود دارد.

**وضعیت:** روی شاخهٔ مستقل ثبت شد؛ CI و ادغام در انتظارند.

## ۲۰۲۶-۱۱-۰۹ — نرمال‌سازی یک‌بارهٔ checkpoint قدیمی برای ramp ظرفیت

**هدف:** جلوگیری از آنکه checkpoint تولیدشده با کنترل قدیمی (+۱ Worker در هر batch پاک) باعث شروع آزمایش جدید از ۱۳ یا ۱۵ شود و پلهٔ ۱۲ یا ۱۴ را دور بزند.

**تغییر/اقدام:** در اولین اجرای کنترل ظرفیت جدید، اگر مقدار ذخیره‌شده از ۱۲ بالاتر باشد، worker limit پیش از ساخت pool به ۱۲ برگردانده می‌شود. نسخهٔ سیاست `explicit_12_14_16_v1` در state ثبت می‌شود تا این reset فقط یک بار اعمال شود و پله‌های ۱۴ و ۱۶ در اجراهای بعدی حفظ شوند. مقدارهای کمتر از ۱۲ بدون جهش حفظ می‌شوند تا ramp تدریجی ادامه یابد؛ سقف درخواستی workflow نیز رعایت می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های جدید نرمال‌سازی مقدار قدیمی ۱۳ به ۱۲، عدم reset پس از ثبت marker، حفظ مقدارهای زیر ۱۲ و احترام به سقف پایین‌تر را کنترل می‌کنند؛ CI این اصلاحیه هنوز باید اجرا شود.

**شواهد/شناسه:** PR #145 و merge commit `471d4cf8c19f0084ffefa021cbb2162294d03b2b`. آخرین اجرای legacy پیش از فعال‌شدن این نرمال‌سازی، ۱۱ Worker را با ۴۸۰/۴۸۰ صفحهٔ موفق، بدون 429/retry و ۱۳٫۹۹ صفحه در ثانیه ثبت کرد و ظرفیت بعدی را ۱۳ گذاشت (run `42676341609`).

**ریسک/بازگشت:** فقط مقدار شروع یک‌بارهٔ کنترل تطبیقی و marker نسخه تغییر می‌کند؛ queue، retry، pagination، checkpoint صفحات، رتبه‌بندی، snapshot و مسیر انتشار دست‌نخورده‌اند. با revert همین PR می‌توان بازگشت کرد.

**وضعیت:** روی شاخهٔ مستقل ثبت شد؛ CI و ادغام در انتظارند.

## ۲۰۲۶-۱۱-۰۹ — پنجرهٔ سه‌مرحله‌ای برای افزایش بهره‌وری اسکن کاتالوگ

**هدف:** کاهش فاصله‌های ناشی از راه‌اندازی دوبارهٔ GitHub Actions و کاهش دفعات commit وضعیت، بدون بالا بردن اندازهٔ هر batch، سقف Worker یا اجرای چند Runner موازی.

**تغییر/اقدام:** workflow اکنون از runner پنجره‌ای استفاده می‌کند که حداکثر سه batch مستقلِ ۴۸۰صفحه‌ای را به‌ترتیب اجرا می‌کند. کنترل تطبیقی Worker در هر batch دوباره ارزیابی می‌شود. مکث بین batchها از telemetry قبلی تعیین می‌شود: ۳ ثانیه پس از batch پاک، ۱۰ ثانیه برای retry موقت، ۲۰ ثانیه در حضور 429، و ۳۰ ثانیه در شرایط شدید یا telemetry ناموجود. کنترل‌گر ظرفیت نیز یک 5xx منفرد را فقط با حفظ تعداد Worker فعلی تحمل می‌کند؛ 429، timeout و خطاهای تکرارشونده همچنان backoff دارند. در اولین خطای batch، پنجره متوقف می‌شود؛ state batchهای موفق قبلی همچنان در workspace باقی می‌ماند و مرحلهٔ persistence همواره اجرا می‌شود.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `affilio_radar/catalog_sweep_batch_window.py`، `affilio_radar/test_catalog_sweep_batch_window.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/CHANGELOG_FA.md`.

**شواهد/شناسه:** PR #147 روی شاخهٔ `feat/catalog-batch-window-3x480`؛ سقف ثابت ۴۸۰ صفحه و ۱۶ Worker در هر microbatch؛ اجرای سه microbatch متوالی هنوز در production اندازه‌گیری نشده است.

**آزمون و نتیجه:** تست‌های جدید تعداد batchها، cooldown تمیز، backoff پس از 429/retry، توقف در خطا و سقف سه batch را پوشش می‌دهند؛ تست کنترل‌گر نیز ثابت می‌کند یک 5xx منفرد ظرفیت را بی‌دلیل کم نمی‌کند و timeout/5xx تکراری همچنان backoff دارند. نتیجهٔ اجرای CI پس از ثبت این اصلاحات هنوز در انتظار است؛ افزایش سرعت production تا اندازه‌گیری واقعی ادعا نمی‌شود.

**ریسک/بازگشت:** اندازهٔ هر batch (۴۸۰)، سقف Worker (۱۶)، گروه concurrency، صف retry، pagination، checkpoint، رتبه‌بندی و گیت انتشار ثابت‌اند. اگر زمان اجرای پنجره به سقف ۱۲ دقیقه نزدیک شود یا خطاها افزایش یابند، می‌توان تعداد batchها را به ۱ یا ۲ کاهش داد یا PR را revert کرد.

**وضعیت:** روی شاخهٔ مستقل `feat/catalog-batch-window-3x480` آمادهٔ CI و بازبینی است.

## 2026-11-10 — قفل گیت تقاضا و مستقیم‌سازی مسیر خرید افیلیت

**هدف:** جلوگیری از انتشار کالایی که فقط تخفیف دارد اما شواهد تازهٔ تقاضا ندارد، و حذف وابستگی مسیر خرید مخاطب به رلهٔ کلیک Cloudflare.

**تغییر/اقدام:** در انتخاب اصلی، backup، صف انتشار و آخرین راستی‌آزمایی، رتبهٔ تازهٔ ۱ تا ۶۰ در bestseller بومی دیجی‌کالا یا رشد تازه و راستی‌آزمایی‌شدهٔ بررسی‌ها شرط سخت شد. رتبهٔ پرفروش سیگنال ترجیحی است و رشد بررسی‌ها فقط پروکسی غیرمستقیم است؛ هیچ‌کدام به‌عنوان تعداد مطلق فروش گزارش نمی‌شوند. تخفیف/مبلغ صرفه‌جویی فقط پس از تساوی شواهد تقاضا tie-breaker است. دکمه‌های خرید URL معتبر Affilio را بدون rewrite برمی‌گردانند و از مسیر واسط `/p/<id>` عبور نمی‌کنند. تحویل ناقصی که حداقل یک مقصد را با موفقیت فرستاده، برای تکمیل مقصدهای دیگر حتی پس از کهنه‌شدن مدرک تقاضا قابل retry می‌ماند؛ این استثنا انتخاب محصول جدید نیست.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/publisher.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_content_delivery.py`، `affilio_radar/test_selection_evidence.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، دکمه‌های خرید رسانه‌ها و توضیحات ویدئو.

**آزمون و نتیجه:** اجرای اولیه CI ناسازگاری تعدادی از تست‌های legacy با سیاست جدید را شناسایی کرد؛ تست‌های انتخاب، backup، retry ناقص و URL مستقیم بازنویسی شدند. نتایج نهایی CI پس از آخرین commit هنوز تأیید نشده است.

**شواهد/شناسه:** PR #148؛ انتشار قبلی با `demand_gate=false` و `review_growth_proxy_verified=False`: run `42740982035`، محصول `dkp-16206478`. CI اولیه: runs `42744905796` و `42744905986`.

**ریسک/بازگشت:** گیت سخت در نبود شواهد تقاضای تازه می‌تواند انتشار را متوقف یا فاصلهٔ پست‌ها را بیشتر کند؛ این رفتار عمدی است و از پرکردن صف با تخفیف کم‌تقاضا جلوگیری می‌کند. retry تحویل ناقص فقط مقصدهای باقی‌مانده را تکمیل می‌کند. برای بازگشت باید همین PR revert شود؛ برای سبزکردن تست، گیت تقاضا را تضعیف نکنید.

**وضعیت:** در PR #148 روی شاخهٔ مستقل؛ ادغام و فعال‌سازی production منوط به سبزشدن همهٔ گیت‌ها و تأیید اجرای واقعی بعدی است.

## 2026-11-10 — هم‌ترازی پیام‌های سیاست و منشور با گیت سخت تقاضا

**هدف:** حذف تناقض میان سیاست جاری demand-first و پیام‌های قدیمی discount-first در لاگ تشخیصی و اسناد مرجع.

**تغییر/اقدام:** پیام آغازگر run() و توضیح دفتر publication ledger با سیاست جاری همسو شدند: مدرک تقاضای تازه شرط سخت انتشار، رتبه‌بندی تقاضامحور، و تخفیف/saving فقط tie-breaker. Handbook: ظرفیت scanner، نقش فایل catalog sweep و دستور AI ادامه‌دهنده اصلاح شد. Charter: معیار قطعی انتخاب، وضعیت P1/P2، بخش سیاست جاری و برچسب بخش‌های تاریخی ۶ نوامبر اصلاح شدند. مسیر CTA مستقیم Affilio در منشور تصریح شد.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/PROJECT_CHARTER_FA.md، docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** این تغییر فقط پیام تشخیصی، comment و اسناد را اصلاح می‌کند؛ منطق انتخاب و URL خریدِ merge commit 167ef33608be41c187ba2b0de45f9fac356c3baa تغییر نمی‌کند. Syntax/Regression و Documentation Gate باید روی PR جدید اجرا شوند؛ نتیجهٔ نهایی هنوز در انتظار است.

**شواهد/شناسه:** PR #148، merge commit 167ef33608be41c187ba2b0de45f9fac356c3baa؛ پیام stale در run قبلی پس از merge کشف شد.

**ریسک/بازگشت:** ریسک اجرایی پایین است؛ حذف پیام قدیمی مانع تفسیر غلط telemetry می‌شود. برای بازگشت، همین PR revert می‌شود؛ سیاست اصلی نباید به discount-first برگردد.

**وضعیت:** روی شاخهٔ fix/policy-log-and-charter-alignment-20261110؛ ادغام پس از سبزشدن گیت‌ها.

## 2026-11-10 — مستقل‌سازی تحویل رسانه‌های اختیاری، مهاجرت snapshot و افزایش ظرفیت اسکن زنده

**هدف:** جلوگیری از حبس صف انتشار اصلی به‌علت خطای روبیکا/ایتا، بازیابی snapshot کامل قبلی که فقط metadata ترتیب تقاضامحور را نداشت، و افزایش سرعت راستی‌آزمایی نامزدهای برتر کاتالوگ.

**تغییر/اقدام:**
- تلگرام و بله به‌عنوان مقصدهای اصلی چرخه تعریف شدند. پس از تحویل موفق این دو، شکست روبیکا/ایتا فقط یک retry اختیاری و محدود باقی می‌ماند و دیگر زمان انتشار بعدی یا صف اصلی را رزرو نمی‌کند.
- fallback روبیکا پس از پاسخ صریح INVALID_INPUT از تلاش مجدد با keypad/metadata صرف‌نظر می‌کند و یک sendFile حداقلی با کپشن ساده و URLهای واقعی خرید/عضویت می‌فرستد. خطاهای مبهم شبکه/سرور همچنان بدون retry مجدد باقی می‌مانند تا خطر ارسال تکراری ایجاد نشود.
- snapshot قدیمی فقط در صورت اثبات چرخهٔ کامل، پوشش ۱۰۰٪ دسته‌ها، نبود دستهٔ غیرقابل‌خواندن، صفحات و ردیف‌های موفق، ۳٬۰۰۰ یا کمتر نامزد یکتا و منشأ digikala_catalog_sweep با رتبهٔ بومی bestseller قابل مهاجرت است. مهاجرت ترتیب ثبت‌شده را بازمرتب نمی‌کند؛ فقط برچسب صریح catalog_demand_first_v1 را اضافه و رتبه‌های snapshot را پیوسته می‌کند.
- سقف بررسی زنده، handoff کاتالوگ، بررسی صف کشف و تلاش نهایی نامزد از ۱۰۰/۶۴ به حداکثر ۲۵۰ مورد در هر اجرا افزایش یافت. فهرست نامزدهای کاتالوگ همچنان چرخشی و محدود است؛ این تغییر ادعای راستی‌آزمایی هم‌زمان تمام محصولات دیجی‌کالا نیست.
- workflow رگرسیون fallback از نام تست‌های حذف‌شدهٔ قدیمی به تست‌های موجود و همسو با سیاست جاری تقاضامحور تغییر کرد؛ مسیر تست صف تحویل هم برای Pull Request فعال است.

**فایل‌ها/سامانه‌ها:** affilio_radar/platform_registry.py، affilio_radar/publisher.py، affilio_radar/messenger_adapters.py، affilio_radar/catalog_status_snapshot.py، affilio_radar/affilio_radar.py، affilio_radar/test_messenger_adapters.py، affilio_radar/test_content_delivery.py، affilio_radar/test_catalog_status_snapshot.py، .github/workflows/offerchin-publisher.yml و .github/workflows/offerchin-fallback-regression.yml.

**آزمون و نتیجه:** آزمون‌های رگرسیون برای خطای روبیکا و non-blocking بودن مقصد اختیاری، و مهاجرت امن snapshot افزوده شدند. اجرای CI و نتیجهٔ نهایی پس از ثبت این ورودی باید در همین شاخه و PR درج شود؛ تا پیش از سبزشدن گیت‌ها این تغییرات production تلقی نمی‌شوند.

**شواهد/شناسه:** شاخهٔ offerchin/reliability-catalog-sweep-20261110؛ commitهای شاخه در GitHub Actions/PR ثبت خواهند شد.

**ریسک/بازگشت:** افزایش ظرفیت به ۲۵۰، بار درخواست‌های live را نسبت به ۱۰۰ افزایش می‌دهد؛ سقف سخت، timeout و صف چرخشی حفظ شده‌اند. مهاجرت snapshot تنها یک‌بار و فقط با provenance کامل انجام می‌شود. برای بازگشت، PR یکپارچه revert شود؛ در صورت شکست مهاجرت، snapshot دست‌نخورده و گیت انتشار بسته می‌ماند.
**وضعیت:** تغییرات روی شاخهٔ مستقل offerchin/reliability-catalog-sweep-20261110؛ ادغام و فعال‌سازی production منوط به سبزشدن آزمون‌ها و Documentation Gate است.

## ۲۰۲۶-۱۱-۱۰ — جلوگیری از اشغال shortlist با اقلام ممنوع و اصلاح تأیید تحویل کاتالوگ

**هدف:** جلوگیری از مصرف ظرفیت محدود ۳٬۰۰۰ نامزد برتر توسط داروها، مکمل‌ها و اقلام داروخانه‌ای که ناشر در مرحلهٔ نهایی به‌درستی رد می‌کند؛ همچنین حذف تأیید کاذب نامزدهایی که فقط به‌دلیل شناسهٔ تکراری در صف قدیمی حضور دارند.

**تغییر/اقدام:**
- قاعدهٔ ممنوعیت دارو، مکمل، ویتامین و اقلام داروخانه‌ای به ماژول مشترک product_quality.py منتقل شد تا اسکنر کاتالوگ و ناشر دقیقاً از یک سیاست استفاده کنند.
- این اقلام پیش از رتبه‌بندی و پر شدن shortlist حذف می‌شوند؛ در مسیر handoff نیز یک کنترل دفاعی دوم باقی است.
- علت‌های رد/تعویق handoff به‌صورت شمارندهٔ پایدار ثبت می‌شوند: شناسه یا URL نامعتبر، عنوان جایگزین‌شده، عنوان سلامت ممنوع، fingerprint تکراری، تعویق فعال، تعداد تازه‌های واجدشرایط و تعداد منتخب.
- تأیید handoff فقط برای محصولی انجام می‌شود که همان ردیف جاری از اعتبار URL، عنوان و فیلتر ایمنی عبور کرده و واقعاً در صف کشف وجود داشته باشد؛ وجود اتفاقی همان شناسه در صف قدیمی دیگر برای acknowledge کافی نیست.
- خانوادهٔ مستقل خوراکی‌ها اضافه شد تا عبارت‌هایی مانند «کرم کنجد» با مراقبت پوست اشتباه نشوند؛ ضدآفتاب همچنان در خانوادهٔ skincare می‌ماند.

**فایل‌ها/سامانه‌ها:** affilio_radar/product_quality.py، affilio_radar/catalog_sweep.py، affilio_radar/affilio_radar.py، تست‌های test_catalog_sweep.py و test_affilio.py.

**سیاست‌های دست‌نخورده:** گیت تقاضای تازه، بررسی زندهٔ قیمت و موجودی، حداقل شرایط تخفیف/صرفه‌جویی، کنترل تنوع، و cooldown تکرار ۲۴ساعته کاهش نیافته‌اند. ظرفیت یا تعداد انتشار با رد کردن اقلام ممنوع و رفع false positive بهبود می‌یابد، نه با تضعیف معیارهای خریدپذیری.

**آزمون و نتیجه:** تست‌های regression برای حذف اقلام سلامت از shortlist و ثبت علت رد handoff، و نیز تفکیک خوراکی از skincare اضافه شده‌اند. fixtureهای آزمون snapshot نیز به timestamp نسبی وابسته شدند تا پنجرهٔ اعتبار ۹۶ساعته باعث شکست مصنوعی تست‌ها پس از گذشت چند روز نشود. تست کامل رادار روی commit اصلاح regex، ۵۰۰ تست را با موفقیت اجرا کرده است؛ گیت snapshot و Documentation پس از آخرین اصلاحات هنوز در حال اجرا هستند. این تغییر تا ادغام production-active نیست.

**شواهد/شناسه:** PR #154؛ شاخهٔ fix/offerchin-catalog-gate-safety-20261110؛ اجرای کامل Affilio Product Radar روی commit b740cd6fd2ef392456f3aa2362329944816529fe.

**ریسک/بازگشت:** ریسک اصلی، false positive در تشخیص عنوان دارو/مکمل یا طبقه‌بندی خوراکی است؛ تست‌های نمونه برای مکمل، خوراکی کنجدی و ضدآفتاب اضافه شده‌اند. در صورت مشاهدهٔ حذف اشتباه، regex/قاعدهٔ طبقه‌بندی با تست بازتولید اصلاح شود؛ برای بازگشت کلی، PR #154 قابل revert است. گیت‌های تقاضا، قیمت و موجودی عمداً دست‌نخورده‌اند.

**وضعیت:** روی شاخهٔ مستقل fix/offerchin-catalog-gate-safety-20261110؛ PR #154 پیش‌نویس است و تا سبزشدن همهٔ گیت‌ها و بازبینی diff ادغام یا فعال‌سازی production انجام نمی‌شود.


## ۲۰۲۶-۱۱-۱۰ — ایجاد «فیلتر آگهی دیوار» به‌عنوان سند مرجع مستقل

**هدف:** تثبیت یک سیاست قابل‌بازیابی در گفتگوهای آینده برای انتخاب کالایی که در شرایط اقتصادی فعلی، هم تقاضای کوتاه‌مدت و داغ داشته باشد، هم برای بخش گسترده‌ای از مردم قابل‌خرید باشد و هم محرک واقعی برای ثبت درخواست خرید ایجاد کند.

**تغییر/اقدام:**
- سند مستقل `docs/AD_DIWAR_FILTER_FA.md` با نسخهٔ ۱٫۰ ایجاد شد؛ نام ارجاع ثابت آن «فیلتر آگهی دیوار» است.
- گیت تقاضای جاری ۲۴ تا ۷۲ ساعته، استطاعت خرید، ارزش واقعی قیمت/محرک خرید، تناسب آگهی و انتخاب شهر داده‌محور تعریف شد.
- رتبهٔ تاریخی، درصد تخفیف اسمی، موجودی محدودِ بدون زمینه و تعداد آگهی‌ها به‌تنهایی مدرک تقاضا محسوب نمی‌شوند.
- README و handbook به سند مستقل ارجاع می‌دهند و مرز سیاست آن با منطق اصلی OfferChin را ثبت می‌کنند.
- از اصول فیلتر فقط در طرح آفر ممتاز روزانهٔ دیوار OfferChin (استطاعت، شتاب تقاضا و ارزش خرید) استفاده می‌شود؛ گیت تقاضا، گاردها و منطق ناشر اصلی تغییر نکرده‌اند.

**فایل‌ها/سامانه‌ها:** `docs/AD_DIWAR_FILTER_FA.md`، `README.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/OFFERCHIN_DAILY_FEATURED_OFFER_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تغییرات این شاخه مستنداتی‌اند و منطق اجرایی/کد/تنظیمات انتشار را تغییر نمی‌دهند؛ تست کد لازم نبوده است. Documentation Gate و بازبینی لینک‌ها در PR باید اجرا و نتیجه در صورت نیاز افزوده شود.

**شواهد/شناسه:** شاخهٔ `docs/ad-diwar-filter-v1-20261110-current`؛ سند اصلی نسخهٔ ۱٫۰؛ commit اولیهٔ سند در شاخهٔ قبلی: `70dd5e3e81e0d8c068d12cb8e9eb34275f876f30`. PR و نتیجهٔ CI هنگام ایجاد/بررسی ثبت می‌شوند.

**ریسک/بازگشت:** خطر اصلی، تفسیر امتیازهای راهنما به‌عنوان احتمال فروش قطعی یا اتکای بی‌جا به داده‌های پروکسی شهر/درآمد است؛ سند الزام به اعلام منبع، زمان مشاهده، عدم قطعیت و اعلام «گزینهٔ واجدشرایط پیدا نشد» را دارد. برای بازگشت، PR مستندات revert شود؛ هیچ تغییر runtime نیازمند rollback نیست.

**وضعیت:** سند و ارجاعات روی شاخهٔ مستقل ثبت شده‌اند؛ ادغام در `main` منوط به بررسی و تأیید است.

## 2026-11-11 — پیاده‌سازی و سخت‌گیری اولیهٔ Opportunity Hunter مستقل

**هدف:** ایجاد موتور مستقل برای کشف فرصت‌های درآمدی در کالاها و خدمات ایران با مدل درآمدی ترکیبی، بدون تغییر رفتار فعال OfferChin.

**تغییر/اقدام:** افزودن اسکنر Python چندمنبعی، پیکربندی صفحات عرضه/بازار/قیمت، RSS و Google News RSS و پیش‌نمایش عمومی تلگرام؛ امتیازدهی محافظه‌کارانه؛ گیت‌های اجباری انتشار؛ قرنطینهٔ ادعاهای تخفیف ۸۰٪ به بالا؛ ثبت نخستین snapshot و workflow روزانه/دستی GitHub Actions. طبقه‌بندی بسته‌های کالایی با واژهٔ «سرویس» نیز اصلاح شد.

**فایل‌ها/سامانه‌ها:** `opportunity_hunter/**`، `.github/workflows/opportunity-hunter.yml`، `README.md`، `docs/CHANGELOG_FA.md` و `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`. ماژول مستقل است و ناشر یا مسیر عملیاتی OfferChin را تغییر نمی‌دهد.

**آزمون و نتیجه:** اجرای اولیهٔ GitHub Actions با شناسهٔ `43063035400` موفق شد؛ تست‌ها سبز، ۹/۹ منبع بدون خطای دریافت/تجزیه، ۷۲ قلم خام و ۵۳ سرنخ اکتشافی. یک فرصت خدماتی با امتیاز اولیهٔ ۵۰/۱۰۰ و بدون آمادگی انتشار به دست آمد. پس از مشاهدهٔ عدم استخراج تخفیف/بنچمارک قیمت از صفحهٔ زنده، وزن تقاضا و گیت تخفیف سخت‌تر شدند؛ تست‌های تکمیلی در اجرای بعدی بررسی می‌شوند.

**شواهد/شناسه:** GitHub Actions run `43063035400` و artifact `13874038241`؛ snapshot دستی ۶۳/۱۰۰ به‌عنوان سابقه حفظ شده و جایگزین نتیجهٔ اسکن خودکار نیست.

**ریسک/بازگشت:** ساختار HTML/RSS ممکن است تغییر کند؛ دریافت موفق منبع به‌تنهایی اثبات استخراج درست یا تقاضای خرید نیست. تخفیف بزرگ، نظر تجمعی یا تعداد عرضه‌کنندگان به‌تنهایی سیگنال فروش نیستند. برای بازگشت، مسیر `opportunity_hunter/` و workflow مستقل revert شوند؛ منطق OfferChin دست‌نخورده می‌ماند.

**وضعیت:** نسخهٔ آزمایشی ۰٫۱ در `main` ثبت و اجرا شد؛ هیچ آگهی، تماس فروشنده، خرید یا پرداخت انجام نشده است.


## ۲۰۲۶-۱۱-۱۱ — رتبه‌بندی چهارعاملی OfferChin

**هدف:** بهینه‌سازی انتخاب OfferChin تا تقاضای زنده، استطاعت خرید، عمومیت کاربرد و جذابیت تخفیف هم‌زمان و با وزن برابر در رتبه‌بندی نهایی اثر داشته باشند؛ بدون تضعیف گیت‌های ایمنی و اعتبار پیشنهاد.

**تغییر/اقدام:**
- ماژول خالص `offerchin_four_factor.py` اضافه شد؛ چهار بُعد را به بازهٔ صفر تا ۱۰۰ نرمال می‌کند و با میانگین هارمونیک تجمیع می‌کند تا یک بُعد قوی، ضعف شدید بُعد دیگر را پنهان نکند.
- استطاعت با proxy شفاف مبلغ ورود از قیمت نقدی و مقایسهٔ نسبی قیمت در گروه کاربردی با حداقل ۸ مشاهده محاسبه می‌شود؛ پیش‌پرداخت اقساط فقط با فیلدهای صریح و تأییدشده پذیرفته می‌شود. منبع فعلی شرایط قسط SKU-specific ندارد؛ لوگو/متن عمومی DigiPay شاهد محسوب نمی‌شود.
- عمومیت با use-case/taxonomy دسته‌بندی می‌شود؛ دادهٔ ناشناخته امتیاز پایین می‌گیرد و به‌اشتباه کالای عمومی فرض نمی‌شود.
- جذابیت تخفیف بر اساس درصد، صرفه‌جویی و سطح اطمینان شواهد قیمت محاسبه می‌شود؛ تاریخچه/بازار تازه و مستقل از تخفیف فهرست‌شدهٔ بدون تأیید مستقل تفکیک شده‌اند.
- امتیاز چهارعاملی هم در shortlist اسکن کاتالوگ و هم در انتخاب نهایی/urgent اعمال می‌شود؛ metadata سیاست و امتیاز اجزا در رکورد انتخاب نگهداری می‌شود.
- workflow اعتبارسنجی مستقل افزوده شد که فقط تست اجرا می‌کند و ناشر Telegram/Bale را trigger نمی‌کند.
- هیچ state صف/کاتالوگ reset یا migrate نشده، انتشار عمومی انجام نشده و سقف/فاصلهٔ انتشار دست‌نخورده مانده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_four_factor.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_offerchin_four_factor.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `.github/workflows/offerchin-four-factor-validation.yml`، `docs/OFFERCHIN_FOUR_FACTOR_RANKING_FA.md`، handbook، README و همین changelog.

**آزمون و نتیجه:** تست واحد برای میانگین هارمونیک، لنگرهای قیمت، cohort استطاعت، اقساط تأییدشده، عمومیت، تخفیف ناسازگار/تأیید مستقل، بی‌اثری click/score ساختگی و اتصال به selector اضافه شد. اجرای CI این شاخه هنوز تأیید نشده است؛ بنابراین syntax/runtime/CI سبز یا موفقیت انتشار ادعا نمی‌شود. workflow جدید پس از ایجاد PR اجرا خواهد شد.

**شواهد/شناسه:** شاخهٔ `feature/offerchin-four-factor-ranking`؛ پایهٔ `main` در زمان انشعاب: `23e6deb71e91d97c9ea80ae29f1a56177f7656a9`. commit اصلی ادغام امتیازدهی نهایی: `372ab0ed17e9aa49e470dc83dbb3f56adb74289f`؛ commit امتیازدهی cohort زنده: `3af1e96eb632209526e4f53c6fac4dd466290c9d`. شناسهٔ PR/CI پس از ایجاد ثبت می‌شود.

**ریسک/بازگشت:** امتیاز عمومیت و anchorهای استطاعت heuristics هستند و باید با رفتار سفارش واقعی کالیبره شوند؛ price percentile برای گروه‌های کوچک اعمال نمی‌شود. امتیاز balanced احتمال خرید نیست. اگر regression یا افت کیفیت مشاهده شود، PR revert شود؛ state جاری دست‌نخورده بماند و هیچ migration یا reset انجام نشود.

**وضعیت:** پیاده‌سازی روی شاخهٔ مستقل انجام شده؛ هنوز PR/merge/فعال‌سازی production انجام نشده است. فقط پس از عبور CI و بازبینی diff می‌توان آن را فعال‌شده اعلام کرد.

## ۲۰۲۶-۱۱-۱۱ — یادداشت تکمیلی append-only برای قرارداد چندرسانه‌ای

**هدف:** ثبت append-only تکمیلی پس از بازبینی Documentation Gate و حفظ تمام ورودی‌های قبلی بدون جابه‌جایی یا بازنویسی.

**تغییر/اقدام:** سند قرارداد انتخاب مشترک، FIFO مشترک YouTube/Aparat/Filo و الزام داشتن تحویل موفق کانالی برای ساخت ویدئوی همراه در انتهای دفتر ثبت می‌شود. ورودی اولیهٔ همین تغییر که پیش‌تر به بالای فایل افزوده شده بود، در این یادداشت بازنویسی یا حذف نمی‌شود؛ این ورودی تکمیلی، شواهد اصلاح ترتیب و ادامهٔ CI را ثبت می‌کند.

**فایل‌ها/سامانه‌ها:** `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`، `affilio_radar/affilio_radar.py`، `affilio_radar/test_shared_selection_media_routing.py`، `affilio_radar/test_affilio.py`، workflowهای publisher و رسانه‌های ویدئویی.

**آزمون و نتیجه:** شش تست جدید FIFO و گیت تحویل کانالی موفق شدند. دو تست قدیمیِ وابسته به ترتیب تخفیف‌اول شناسایی و به سیاست FIFO به‌روزرسانی شدند؛ اجرای مجدد مجموعهٔ کامل و Documentation Gate در انتظار تکمیل است.

**شواهد/شناسه:** تست‌های اولیه در Affilio Product Radar run `43087587401`؛ اجرای اصلاح‌شده پس از commit `968d5d1a457671a26c56c65a74ddefe032fd6c45` در صف اجراست.

**ریسک/بازگشت:** quota/محدودیت سکوها ممکن است زمان انتشار ویدئو را از کانال جدا کند؛ ترتیب محصول منتخب نباید مستقل تغییر کند. rollback فقط با revert منطق FIFO و تست‌های نگهبان انجام شود؛ state و صف موجود reset نشوند.

**وضعیت:** اصلاح منطق انجام‌شده؛ نتیجهٔ CI نهایی در انتظار.

## ۲۰۲۶-۱۱-۱۱ — نتیجهٔ نهایی آزمون قرارداد انتخاب مشترک

**هدف:** جایگزینی وضعیت «در انتظار CI» با نتیجهٔ واقعی و قابل‌ردیابی پس از اجرای کامل آزمون‌ها.

**تغییر/اقدام:** آزمون رگرسیون کامل پس از اصلاح دو انتظار قدیمیِ تخفیف‌اول اجرا شد؛ مسیر FIFO مشترک YouTube/Aparat/Filo، الزام تحویل موفق کانالی و سایر regressionهای OfferChin تأیید شدند. Documentation Gate نیز پس از ثبت append-only مستندات موفق شد.

**فایل‌ها/سامانه‌ها:** کد و تست‌های ثبت‌شده در ورودی قبلی؛ .github/workflows/affilio-radar.yml و docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** Affilio Product Radar run 43088164734: نتیجهٔ success، اجرای py_compile و ۵۰۷ تست با نتیجهٔ موفق. Documentation Gate run 43088412959: نتیجهٔ success، شامل آزمون validator و بررسی handbook/changelog.

**شواهد/شناسه:** commit کد و تست 968d5d1a457671a26c56c65a74ddefe032fd6c45؛ commit مستندات ac5c217ec922478a34644758aa61feb8614d9140.

**ریسک/بازگشت:** cadence و سهمیهٔ مقصدها مستقل باقی می‌مانند؛ تأخیر مقصد ویدئویی نباید موجب انتخاب محصول دیگری شود. بازگشت با revert تغییر FIFO و تست‌های متناظر ممکن است؛ state و صف موجود reset نشوند.

**وضعیت:** انجام‌شده؛ کد، تست‌ها و گیت مستندات موفق.


## ۲۰۲۶-۱۱-۱۱ — همگام‌سازی رویدادمحور کانال و رسانه‌های ویدئویی

**هدف:** انطباق محتوای ویدئویی با همان محصولی که در Telegram/Bale/Rubika/Eitaa با موفقیت منتشر شده است؛ بدون انتخاب محصول مستقل یا دور زدن محدودیت واقعی مقصدها.

**تغییر/اقدام:**
- قرارداد انتشار چندرسانه‌ای اصلاح شد تا «انتشار موفق کانالی» صریحاً رویداد ورود همان رکورد canonical به صف واجدشرایط ویدئو باشد.
- رفتار Worker مستند شد: در هر tick دقیقه‌ای، رکوردهای کانالی را بررسی می‌کند؛ rate limit شناور هر مقصد فقط زمان dispatch را محدود می‌کند و انتخاب محصول/ترتیب FIFO را تغییر نمی‌دهد.
- آزمون Worker اضافه شد تا تأیید کند یک رکورد با تحویل موفق کانالی، بلافاصله برای هر سه مقصد YouTube/Aparat/Filo واجدشرایط است؛ slot بسته باید فقط dispatch را عقب بیندازد.
- نرخ‌گذارهای فعلی عمداً تغییر نکردند: YouTube و Aparat سه‌ساعته؛ Filo بیست‌وهفت‌دقیقه‌ای. YouTube علاوه بر فاصلهٔ سه‌ساعته، `uploadLimitExceeded` را تشخیص می‌دهد و pause ۲۴ساعت‌و۱۵دقیقه‌ای دارد.
- snapshot sidecar در `2026-11-11T19:43:42Z` بررسی شد: از ۲۸ رکورد کانالی ۲۴ساعته، YouTube شامل ۷ uploaded، ۱۴ pending و ۷ skipped-expiring؛ Aparat شامل ۱۹ pending و ۹ skipped-expiring؛ Filo شامل ۲ submitted-pending-approval، ۱۷ pending و ۹ skipped-expiring بود. این داده محدودیت عملی ظرفیت/مهلت را نشان می‌دهد و آمار عمومی‌شدن یا فروش نیست.

**فایل‌ها/سامانه‌ها:** `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs` و همین changelog.

**آزمون و نتیجه:** آزمون جدید eligibility رویدادمحور اضافه شد. اجرای CI/Worker test در PR باید بررسی شود؛ تا پیش از نتیجهٔ واقعی CI، موفقیت آزمون یا انتشار عمومی ادعا نمی‌شود.

**شواهد/شناسه:** PR #160؛ commits `8c3a3d9689d3a2f8d54138e354a714f16c6bf367` و `ff88df6194f96090ff6f3e7b1e20df02aabf50d4` در شاخهٔ `feature/offerchin-event-driven-video-sync-20261111`؛ این شناسه‌ها مسیر Worker eligibility و آزمون مربوط را مشخص می‌کنند.

**ریسک/بازگشت:** افزایش cadence بدون رفع واقعی محدودیت‌های مقصد می‌تواند باعث خطا، توقف روزانه یا محتوای منقضی شود. هیچ صف، state یا slot runtime reset نشد؛ rollback با revert همین تغییر مستندات/تست/توضیحات ممکن است.

**وضعیت:** تغییرات مستندات و آزمون در شاخهٔ مستقل؛ PR و CI در انتظار.


## ۲۰۲۶-۱۱-۱۲ — fan-out مستقل همهٔ رسانه‌ها از رویداد انتخاب canonical و اصلاح چیدمان عنوان ویدئو

**هدف:** وقتی یک محصول پس از اعتبارسنجی نهایی انتخاب شد، همان محصول برای تمام مقصدهای فعال تصویری و ویدئویی نامزد انتشار شود؛ هیچ مقصدی برای شروع یا retry منتظر موفقیت مقصد دیگری نماند. همچنین عنوان محصول در پوستر ویدئو دو فاصلهٔ خطی پایین‌تر از بالای بوم آغاز شود.

**تغییر/اقدام:**
- گیت قدیمی ویدئو که فقط رکورد دارای تحویل موفق Telegram/Bale/Rubika/Eitaa را واجدشرایط می‌کرد، با رویداد canonical انتخاب جایگزین شد. رکورد `published` که پیش از فراخوانی شبکه‌ای مقصدها ساخته می‌شود و `distribution_queue_id` دارد، از همان لحظه واجدشرایط fan-out ویدئویی است؛ موفقیت یا شکست کانال تصویری دیگر شرط شروع YouTube/Aparat/Filo نیست.
- sidecar کوچک Worker حالا رکورد منتخب را حتی با وضعیت تصویری `pending` با نشانگر `video_dispatch_eligible=true` وارد projection می‌کند. رکوردهای قدیمی فاقد `distribution_queue_id` فقط با رسید واقعی تحویل کانالی همچنان واجدشرایط می‌مانند.
- Worker و Python processor هر سه مقصد ویدئویی را بر اساس رویداد انتخاب مشترک می‌بینند؛ quota، slot، pause، deadline، اعتبارنامه و retry هر مقصد مستقل و بدون انتخاب محصول جایگزین باقی می‌ماند.
- گیت‌های قیمت/موجودی/تخفیف و اعتبار لینک در آخرین مرحلهٔ ناشر حفظ شده‌اند؛ deadline تأییدشدهٔ Aparat، pause روزانهٔ YouTube، freshness بیست‌وچهارساعته و تأیید نشست Filo نیز دست‌نخورده‌اند.
- قفل مشترک نوشتن `state.json` حفظ شد تا workflowهای مختلف نتوانند وضعیت همدیگر را بازنویسی کنند. این قفل تضمین یکپارچگی state است؛ شرط موفقیت یک مقصد برای شروع مقصد دیگر نیست. حذف قفل بدون persistence اتمیک/تفکیک‌شده امن نیست.
- در `short_video.py` فضای خالی بالای عنوان به ۱۲۸px از بالای بوم افزایش یافت؛ عنوان و تمام اجزای پایین‌تر شامل CTA، کارت محصول و پنل قیمت به اندازهٔ ۹۴px جابه‌جا شدند. لوگوهای کانال، لوگوی فروشنده، تخفیف و نشان دیجی‌پی نیز با layout جدید هم‌تراز باقی می‌مانند.
- قرارداد چندرسانه‌ای بازنویسی شد تا تفاوت «یک انتخاب مشترک» با «fan-out مستقل مقصدها» و محدودیت قفل state صریح باشد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_shared_selection_media_routing.py`، `affilio_radar/test_affilio.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `affilio_radar/short_video.py`، `affilio_radar/test_short_video.py`، `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md` و همین changelog.

**آزمون و نتیجه:** آزمون جدید Worker برای واجدشرایط‌بودن محصول بدون تحویل تصویری اضافه شد؛ آزمون Python برای sidecar و compatibility رکوردهای قدیمی اصلاح شد؛ آزمون چیدمان title-space و مختصات CTA/لوگو/پنل قیمت اصلاح شد. نتیجهٔ CI کامل و تست رندر پس از اجرای workflowهای PR باید ثبت شود؛ پیش از آن موفقیت نهایی ادعا نمی‌شود.

**شواهد/شناسه:** PR #160؛ head commit `fb7c93626ca671ef44cccdaba452f117c8877df5`؛ Worker validation run `43098874123` موفق؛ Documentation Gate run `43098874143` و Platform Logo Regression run `43098874345` در نخستین اجرا به‌ترتیب به علت تکمیل‌نبودن مستندات و import نشدن ثابت‌های layout شکست خوردند. این نتایج هنوز تأیید نهایی کل تغییر نیستند.

**ریسک/بازگشت:** fan-out ویدئو حتی در صورت شکست همهٔ کانال‌های تصویری ممکن است ادامه یابد؛ این مطابق سیاست استقلال است، مشروط به اینکه رکورد canonical و گیت‌های زنده معتبر باشند. بازگشت با revert تغییر helper واجدشرایط‌بودن، projection Worker، تست‌ها و layout ویدئو انجام می‌شود؛ state/صف موجود reset یا migrate نمی‌شود.

**وضعیت:** تغییرات در شاخهٔ `feature/offerchin-event-driven-video-sync-20261111` و PR شمارهٔ ۱۶۰؛ تا زمان CI سبز و ادغام، production فعال اعلام نمی‌شود.

## ۲۰۲۶-۱۱-۱۲ — حذف فاصله‌های مصنوعی و fan-out ترتیبی مشترک ویدئو

**هدف:** با هر رویداد انتخاب/انتشار محصول، یک دستور واحد برای YouTube، Aparat و Filo صادر شود؛ ترتیب محصول در هر مقصد با صف canonical سایر مقصدها یکسان بماند و خرابی یک مقصد باعث توقف بقیه نشود.

**تغییر/اقدام:** فاصله‌های داخلی ۳ساعتهٔ YouTube/Aparat، ۲۷دقیقه‌ای Filo، retry backoff و TTL بیست‌وچهارساعتهٔ صف ویدئو حذف شدند. یک Workflow واحد `offerchin-video-publisher.yml` اضافه شد که هر محصول را در یک پردازش مشترک به هر سه مقصد fan-out می‌کند و تا ثبت وضعیت همان SKU به محصول بعدی نمی‌رود. ناشر کانالی پس از persist رکورد یک dispatch واحد صادر می‌کند؛ Worker نیز برای recovery هر دقیقه همان Workflow را dispatch می‌کند. retryهای قابل‌تکرار هر مقصد به ۳ تلاش محدود و سپس terminal skip می‌شوند؛ نتیجهٔ نامعلوم پس از آغاز upload به manual review می‌رود و کورکورانه retry نمی‌شود. گیت‌های واقعی quota YouTube، deadline تأییدشدهٔ Aparat، نشست Filo و انقضای واقعی پیشنهاد حفظ شده‌اند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `affilio_radar/test_shared_selection_media_routing.py`، `affilio_radar/test_aparat_upload_schedule.py`، `affilio_radar/test_filo_upload_schedule.py`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/offerchin-video-publisher.yml`، `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`، `docs/OFFERCHIN_FOUR_FACTOR_RANKING_FA.md` و همین handbook/changelog.

**آزمون و نتیجه:** regression tests مربوط به FIFO واحد، عبور مقصد از خطای مقصد دیگر، حذف slotها، dispatch قدیمی بدون محدودیت زمانی و terminal skip افزوده/اصلاح شده‌اند. نتایج CI هنوز در انتظار اجرای PR هستند؛ موفقیت production یا انتشار عمومی جدید ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `feature/offerchin-video-fanout-no-throttle-20261112`. commitهای اصلی: Python `3f4439cae7855c3c56e3f47c52cc8a4d219e4f9c`؛ Worker `4a0f6852ba04f1d62e26327b82082798b6b8bed8` و اصلاح terminal status `fdedc45af301f38e0ec56776c2547d3cab322c14`؛ dispatch ناشر `7117c087f8c321160fa80c86e7588cd732fa1813`؛ Workflow واحد `0bafe9d828167e719d9c99a9957a3d4601b29669` و اصلاح login Filo `2fe63fcd67c85c392b2a7fa3c6794435547ae0db`. تست‌ها و اسناد نیز در commitهای بعدی همین شاخه به‌روز شده‌اند.

**ریسک/بازگشت:** اشتراک `state.json` همچنان مستلزم قفل مشترک است؛ یک Workflow ترتیبی عمداً جایگزین سه workflow موازی شد. محدودیت سهمیهٔ واقعی YouTube یا عدم تأیید deadline/credential می‌تواند برای همان مقصد skip ایجاد کند. نتیجهٔ unknown به‌صورت دستی بررسی می‌شود تا duplicate نشود. بازگشت با revert PR ممکن است؛ state/صف موجود reset نمی‌شود.

**وضعیت:** کد و مستندات در شاخهٔ feature انجام‌شده؛ PR و CI در مرحلهٔ بعد؛ تا ادغام و deploy خودکار Worker روی main فعال production نیستند.


## ۲۰۲۶-۱۱-۱۲ — اتصال مسیر اضطراری دستی به fan-out ویدئویی

**هدف:** هیچ مسیر محصولیِ ارسال Telegram/Bale بدون صدور دستور مشترک برای YouTube، Aparat و Filo باقی نماند.

**تغییر/اقدام:** مسیر اضطراری دستی `affilio-publisher.yml` نیز پس از ذخیرهٔ موفق وضعیت تحویل، Workflow واحد `offerchin-video-publisher.yml` را dispatch می‌کند. مجوز `actions: write` و شرط موفقیت مرحلهٔ persistence اضافه شد؛ بنابراین مسیر اصلی و مسیر اضطراری هر دو از یک صف ویدئویی مشترک استفاده می‌کنند. مسیر کمپین دستی بدون SKU عمداً خارج از این قرارداد محصولی باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/affilio-publisher.yml`، `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و همین changelog.

**آزمون و نتیجه:** تغییر به PR شمارهٔ ۱۶۳ اضافه شد؛ CI مربوط به نسخهٔ نهایی پس از push اجرا می‌شود. هیچ ارسال عمومی دستی اجرا نشد.

**شواهد/شناسه:** PR #163؛ شاخهٔ `feature/offerchin-video-fanout-no-throttle-20261112`؛ commit اتصال مسیر اضطراری `bf95787ee244c94e1b7cc7231097de60f974d310`.

**ریسک/بازگشت:** اگر مرحلهٔ persistence شکست بخورد، dispatch ویدئو انجام نمی‌شود و Worker با خواندن صف pending بازیابی می‌کند. بازگشت با revert همین تغییر workflow ممکن است؛ state صف نباید پاک شود.

**وضعیت:** در شاخهٔ PR انجام‌شده؛ تا ادغام PR فعال production نیست.


## ۲۰۲۶-۱۱-۱۲ — ایجاد قرارداد امن محتوای جایگزین تحریریه‌ای (بدون فعال‌سازی انتشار)

**هدف:** آماده‌سازی مسیر محتوای آموزشی/کاربردی مستقل از SKU، بدون جعل قیمت/تخفیف/موجودی یا دورزدن گیت‌های محصول.

**تغییر/اقدام:** ماژول مستقل editorial_content.py برای اعتبارسنجی منبع هر ادعا، تاریخ بازبینی/انقضا، جلوگیری از ادعاهای تجاری لحظه‌ای، انتخاب با cooldown و ثبت فقط انتشار تأییدشده اضافه شد. تست‌های واحد برای رد ادعای تجاری بی‌منبع، انقضای محتوا، تکرار موضوع و ثبت موفقیت کاذب نوشته شد. سند معماری محدودیت اتصال فعلی را شفاف می‌کند.

**فایل‌ها/سامانه‌ها:** affilio_radar/editorial_content.py، affilio_radar/test_editorial_content.py، docs/OFFERCHIN_EDITORIAL_FALLBACK_FA.md، docs/CHANGELOG_FA.md، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md.

**آزمون و نتیجه:** تست‌های جدید پس از اجرای CI روی PR ثبت می‌شوند؛ هنوز هیچ انتشار عمومی انجام نشده است.

**شواهد/شناسه:** شاخهٔ feat/offerchin-hourly-editorial-fallback-20261112؛ PR پس از ثبت تغییرات ایجاد می‌شود.

**ریسک/بازگشت:** این تغییر عمداً به ناشر زنده متصل نیست؛ بنابراین cadence فعلی و صف محصول را تغییر نمی‌دهد. rollback با revert همین commit ممکن است.

**وضعیت:** قرارداد و تست‌ها آمادهٔ بازبینی؛ اتصال به مقصدها و تضمین SLA ساعتی هنوز انجام نشده است.


## ۲۰۲۶-۱۱-۱۲ — اتصال مسیر fallback تحریریه‌ای به صف مشترک و مقصدها (در انتظار CI نهایی)

**هدف:** افزودن محتوای غیرمحصولی برای حفظ حضور منظم، بدون دورزدن گیت‌های انتخاب محصول یا تولید ادعای تجاری بی‌پشتوانه.

**تغییر/اقدام:** شمارندهٔ توالی مشترک محصول/تحریریه در `content_delivery.py` افزوده شد؛ محصول در زمان enqueue شماره و شناسهٔ canonical دریافت می‌کند. `editorial_publisher.py` صف مستقل تحریریه را با وضعیت هر هفت مقصد اجرا می‌کند: Telegram/Bale پیام متنی، Rubika/Eitaa کارت تصویری و YouTube/Aparat/Filo ویدئوی عمودی. `editorial_video.py` پوستر و MP4 مستقل از SKU می‌سازد و `editorial_bank.json` شامل شش مطلب evergreen منبع‌دار است. `publisher.py` با وجود تحریریهٔ فعال، ارسال محصول جدیدتر را متوقف می‌کند. workflow کانال و workflow ویدئو به مراحل تحریریه متصل شده‌اند. timeout/نتیجه نامعلوم به بررسی دستی می‌رود، HTTP 429 به‌عنوان محدودیت ثبت می‌شود، Filo pending approval موفقیت عمومی نیست و Aparat همچنان از مسیر web session غیررسمی پروژه استفاده می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/content_delivery.py`، `publisher.py`، `editorial_content.py`، `editorial_publisher.py`، `editorial_video.py`، `editorial_bank.json`، تست‌های editorial، دو workflow انتشار و CI اختصاصی، handbook و سند fallback.

**آزمون و نتیجه:** compile ماژول‌ها و اعتبارسنجی شش مطلب در CI موفق بوده‌اند. یک تست عدم‌پیش‌دستی صف محصول شکست خورد چون fixture دو ساعت قدیمی بود و تابع cleanup آن را طبق قرارداد ۸ دقیقه‌ای stale کرد؛ fixture به آیتم تازهٔ پنج‌دقیقه‌ای تغییر کرده است. اجرای مجدد تست و آزمون یکپارچهٔ sequence در انتظار CI نهایی است. هیچ درخواست انتشار عمومی آزمایشی اجرا نشده است.

**شواهد/شناسه:** PR #165؛ head فعلی تا پیش از اصلاحات بعدی: `2eb4d9921e622a8f9776e8a31d380591a3406c57`. نتایج workflow در run `43278785650` یک failure تست ثبت کرده‌اند؛ باید run بعدی جایگزین آن را تأیید کند.

**ریسک/بازگشت:** به‌علت صف مستقل، کد محصول تحت validation تحریریه قرار نمی‌گیرد؛ اما قفل FIFO می‌تواند در صورت خطای مداوم یک مقصد، انتشار محصول جدید را عقب بیندازد. موارد نتیجه نامعلوم به‌جای retry کور در manual_review باقی می‌مانند. rollback با revert PR/commitها ممکن است؛ فایل state و شمارندهٔ ترتیب نباید دستی پاک شوند.

**وضعیت:** پیاده‌سازی شاخه انجام‌شده؛ CI نهایی، shadow run، ادغام، استقرار و تأیید عمومی در انتظار.


## ۲۰۲۶-۱۱-۱۲ — تکمیل چرخش محتوای fallback و حفظ ترتیب در fallback محصول/ویدئو

**هدف:** جلوگیری از خالی‌شدن بانک محتوای تحریریه‌ای پس از چند ساعت و حفظ شناسهٔ ترتیبی slot هنگام جایگزینی محصول یا انتقال به صف ویدئو.

**تغییر/اقدام:** بانک از ۶ به ۳۶ مطلب مستقلِ دارای منبع و claim provenance گسترش یافت. cooldown هر مطلب از ۷۲ به ۲۴ ساعت کاهش یافت؛ cooldown موضوع ۴ ساعت باقی ماند. fallback محصولی که در last-mile جای محصول ردشده را می‌گیرد، sequence همان slot را از history به ارث می‌برد؛ publisher.py sequence را از hand-off به رکورد منتشرشده منتقل می‌کند؛ video FIFO برای timestamp مساوی از sequence به‌عنوان tie-break استفاده می‌کند و dispatch sidecar این metadata را نگه می‌دارد. تست‌های مربوط به چرخش ۲۴ساعته، fallback sequence و video tie-break اضافه شدند.

**فایل‌ها/سامانه‌ها:** editorial_bank.json، editorial_content.py، content_delivery.py، publisher.py، affilio_radar.py، تست‌های editorial و content delivery، workflow CI و سند Handbook.

**آزمون و نتیجه:** اجرای نهایی این تغییرات در GitHub Actions هنوز در حال اجرا/در انتظار است؛ هیچ انتشار عمومی آزمایشی انجام نشده است.

**شواهد/شناسه:** PR #165؛ commit گسترش بانک e9a4ea49d228712e8e7e61d4d2000e58ba238223؛ commit ترتیب و fallback محصول در شاخهٔ جاری.

**ریسک/بازگشت:** محتوای منقضی یا نامعتبر رد می‌شود؛ در صورت نبود مطلب واجد شرایط، سیستم نباید محتوای ساختگی منتشر کند و gap واقعی ثبت می‌شود. rollback با revert PR ممکن است؛ state و sequence counter نباید reset شوند.

**وضعیت:** پیاده‌سازی انجام‌شده در شاخه؛ CI نهایی، shadow run، ادغام و تأیید انتشار عمومی در انتظار.


## ۲۰۲۶-۱۱-۱۲ — آماده‌سازی Shadow read-only و قفل پیش‌فرض انتشار عمومی

**هدف:** امکان پایش ۲۴ساعتهٔ تصمیم fallback بدون ارسال پست آزمایشی، و جلوگیری از شروع ناخواستهٔ انتشار عمومی هنگام ادغام کد.

**تغییر/اقدام:** گزینهٔ \`--shadow-report\` گزارش read-only از سلامت بانک، تصمیم صف، شمارهٔ توالی شبیه‌سازی‌شده، قفل FIFO و وجود محلی credentialها تولید می‌کند؛ state فقط در حافظه کپی می‌شود و هیچ مقصدی فراخوانی نمی‌شود. workflow زمان‌بندی‌شدهٔ \`offerchin-editorial-shadow.yml\` هر ۱۰ دقیقه گزارش artifact ذخیره می‌کند. workflow کانال و ویدئو هر دو انتشار عمومی editorial را پشت متغیر \`OFFERCHIN_EDITORIAL_PUBLISH_ENABLED\` گذاشته‌اند؛ نبود متغیر مساوی false است. تست CI تضمین می‌کند workflow shadow فاقد \`--publish\` بماند و feature flag پیش‌فرض خاموش باشد.

**فایل‌ها/سامانه‌ها:** editorial_publisher.py، offerchin-editorial-shadow.yml، offerchin-editorial-contract.yml، offerchin-publisher.yml، offerchin-video-publisher.yml، handbook و سند fallback.

**آزمون و نتیجه:** تست‌ها و اعتبارسنجی workflow روی PR اجرا می‌شوند؛ shadow ۲۴ساعته هنوز اجرا نشده، زیرا workflow فقط پس از ادغام روی main زمان‌بندی خواهد شد. هیچ انتشار عمومی آزمایشی انجام نشده است.

**شواهد/شناسه:** PR #165؛ شاخهٔ feat/offerchin-hourly-editorial-fallback-20261112.

**ریسک/بازگشت:** اگر shadow report خطا دهد، مرحلهٔ عمومی همچنان خاموش است. فعال‌سازی فقط با تنظیم متغیر مخزن و پس از ارزیابی ۲۴ ساعت artifactها انجام شود؛ rollback با خاموش‌کردن variable و revert commitهای تغییر ممکن است.

**وضعیت:** پیاده‌سازی branch انجام‌شده؛ اجرای shadow، ادغام، استقرار و فعال‌سازی عمومی در انتظار.

## ۲۰۲۶-۱۱-۱۳ — الزام حداقل جذابیت تخفیف و تاب‌آوری کشف دسته‌های کاتالوگ

**هدف:** جلوگیری از انتشار آفرهای دارای تخفیف اسمی/ناچیز؛ ادامهٔ امن اسکن کاتالوگ هنگام اختلال موقت API بدون اعلام اشتباه چرخهٔ کامل.

**تغییر/اقدام:** نسخهٔ چهارعامل به `offerchin_four_factor_harmonic_v2_discount_gate` ارتقا یافت. عامل چهارم «استطاعت خرید» است. علاوه بر میانگین هارمونیک، گیت مستقل جذابیت تخفیف با حداقل ۴۰/۱۰۰ به انتخاب و آخرین‌لحظهٔ انتشار اضافه شد. امتیاز تخفیف درصد، مبلغ واقعی صرفه‌جویی و تأیید مستقل تاریخچه/مقایسهٔ بازار را ترکیب می‌کند؛ درصد ثابت سراسری تعریف نشده است. در کشف دسته‌ها، خطا با HTTP status دقیق ثبت می‌شود؛ cache دستهٔ تأییدشده تا ۹۶ ساعت قابل استفاده است؛ retry با backoff انجام می‌شود و پس از انقضای cache سیستم fail-closed می‌ماند. وضعیت fallback و age به status snapshot افزوده شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_four_factor.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_sweep.py`، `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/test_offerchin_four_factor.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های جدید برای رد تخفیف ۵٪ بدون شاهد مستقل، پذیرش استثنای تخفیف کوچک با شاهد مستقل/صرفه‌جویی کافی، عدم جبران عامل ضعیف توسط سایر عوامل، ثبت HTTP 403، استفاده از taxonomy cache، backoff و fail-closed پس از ۹۶ ساعت افزوده شدند. اجرای CI روی PR پس از ایجاد آن در انتظار است.

**شواهد/شناسه:** branch `fix/offerchin-discount-quality-and-catalog-resilience-20261113`; commits `02f98531e745f982a916d37806d18db604e17248`, `e8656c3bff44b723165daf5bfc45d50d25ef712d`, `0f4f4dbef457d7db03630034fe245ac7e11a8936`, `560160544cff778ff3e853da659bd215986e831d`, `6cd2fbb45095cc5202705891fd5837bdc7d8461a1`.

**ریسک/بازگشت:** گیت جدید تعداد کاندیدهای واجد شرایط را کاهش می‌دهد؛ این رفتار عمدی است و جای آن با تحریریهٔ منبع‌دار یا فاصلهٔ خالی پر می‌شود، نه تخفیف ضعیف. taxonomy cache فقط تا ۹۶ ساعت مجاز است و snapshot سالم قبلی را به‌عنوان چرخهٔ جدید جا نمی‌زند. در صورت اثر بیش‌ازحد، threshold با backtest روی خرید/کمیسیون واقعی تنظیم شود؛ درصد تخفیف به‌تنهایی پایین آورده نشود.

**وضعیت:** پیاده‌سازی و تست‌ها روی شاخه؛ CI و تأیید آمار واقعی پس از ادغام در انتظار.

## ۲۰۲۶-۱۱-۱۳ — اصلاح استطاعت بر پایهٔ قیمت نهایی و الزام تاب‌آوری شبکهٔ ملی

**هدف:** هم‌راستاسازی عامل دوم چهارگانه با قدرت خرید عمومی مخاطب؛ حذف اثر پیش‌پرداخت اقساط از امتیاز استطاعت؛ قفل‌کردن مسیر خرید مستقیم افیلیو و منع وابستگی CTA به واسطه‌های خارجی/ثالث.

**تغییر/اقدام:** نسخهٔ چهارعامل به `offerchin_four_factor_harmonic_v3_final_price_affordability` ارتقا یافت. امتیاز استطاعت از `current_price` و مرجع آفلاین حداقل مزد پایهٔ ۱۴۰۵ (۱۶٬۶۲۵٬۵۵۰ تومان برای ۳۰ روز، بدون مزایا) محاسبه می‌شود؛ رتبهٔ نسبی هم‌گروه با حداقل ۸ مورد حفظ شده است. پیش‌پرداخت اقساط هیچ اثری بر affordability ندارد. مرجع درآمد با تاریخ/منبع ذخیره می‌شود تا runtime به اینترنت یا API خارجی وابسته نشود. منشور تاب‌آوری ملی: CTA فقط URL رسمی `aflo.ir` را مستقیم باز می‌کند؛ هیچ Cloudflare/GitHub/کوتاه‌کننده/ردیاب ثالث در مسیر خرید نیست. کوکی فقط با کلیک واقعی کاربر قابل‌طرح است؛ lifetime و last-click تا دریافت پاسخ رسمی افیلیو نامشخص می‌مانند و cookie stuffing/hidden redirect ممنوع است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/offerchin_four_factor.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/test_offerchin_four_factor.py`، `affilio_radar/test_affilio.py`، `docs/OFFERCHIN_FOUR_FACTOR_RANKING_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/PROJECT_CHARTER_FA.md`.

**آزمون و نتیجه:** تست‌ها anchor درآمدی نسخه‌دار، افت امتیاز با رشد نسبت قیمت به مرجع، عدم اثر پیش‌پرداخت بر امتیاز و نسخهٔ چهارعامل را بررسی می‌کنند. تست موجود `test_purchase_button_always_opens_direct_affilio_url_without_tracker` تضمین می‌کند CTA از tracker عبور نکند؛ CI روی این شاخه در انتظار است.

**شواهد/شناسه:** branch `fix/offerchin-final-price-affordability-and-domestic-resilience-20261113`; code commits `1d1c9ce02fb0e4626a166853a484af71569f0e97`, `6b50ac0f6fb710086d9a9785aad774ae3b919404`, `b673f69886033083bb7401b89a89f934a9f80609`, `fc4440a0ed644f19152e869260ecfa51baa1d198`.

**ریسک/بازگشت:** مرجع حداقل مزد یک proxy محافظه‌کارانه است، نه متوسط درآمد/دادهٔ توان خرید واقعی؛ با انتشار بخشنامهٔ جدید باید نسخه‌دار به‌روزرسانی شود. هزینهٔ ارسال نامعلوم نباید صفر فرض شود. در صورت اختلال aflo.ir، لینک غیرمجاز یا غیرقابل‌انتساب جایگزین نمی‌شود و انتشار آفر متوقف/معلق می‌ماند؛ state/صف حفظ می‌شود.

**وضعیت:** پیاده‌سازی روی شاخه؛ CI و merge در انتظار.


## ۲۰۲۶-۱۱-۱۴ — کشف نامزدهای تحریریه از دیجی‌کالا مگ

**هدف:** افزودن یک منبع فارسی داخلی برای کشف سوژه‌های کوتاه و کاربردی، بدون کپی‌کردن محتوای ناشر یا ایجاد مزاحمت برای صف محصول.

**تغییر/اقدام:** ماژول `affilio_radar/digikala_mag_discovery.py` و workflow مستقل `.github/workflows/offerchin-mag-source-discovery.yml` اضافه شدند. workflow هر ۳۰ دقیقه RSS عمومی را بررسی می‌کند و نامزدهای مرتبط با فناوری/گجت، خانه/آشپزخانه، پوشاک/زیبایی و راهنمای خرید را به‌شکل فرادادهٔ داخلی ثبت می‌کند. عنوان، URL canonical، تاریخ، موضوع و امتیاز ارتباط نگهداری می‌شود؛ متن RSS، محتوای مقاله و تصاویر دانلود/ذخیره نمی‌شوند. cache از تکرار جلوگیری می‌کند و گزارش به‌صورت artifact با ماندگاری ۱۴ روز ثبت می‌شود.

**گیت انتشار:** خروجی فقط «نامزد برای بازبینی» است. هیچ خلاصهٔ خودکار یا انتشار عمومی انجام نمی‌شود. هر محتوای بعدی باید مستقل و فارسی، حدود ۳۵ تا ۶۰ واژه، دارای پیوند منبع و فاقد نقل/کپی متن یا تصویر باشد. تا دریافت مجوز روشن، استفادهٔ تجاری از متن و تصویر منبع مجاز فرض نمی‌شود. هیچ API key یا هزینهٔ جدید افزوده نشده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/digikala_mag_discovery.py`، `affilio_radar/test_digikala_mag_discovery.py`، `.github/workflows/offerchin-mag-source-discovery.yml`، `.github/workflows/offerchin-fallback-regression.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `README.md`.

**آزمون و نتیجه:** هر ۸ تست واحد کشف دیجی‌کالا مگ در workflow مستقل با موفقیت اجرا شدند؛ همان ۸ تست در گیت regression موجود پروژه نیز موفق‌اند. تست‌های صف تحویل، پنج تست رتبه‌بندی و workflow یکپارچهٔ video fan-out نیز روی commit کد `ef55155f9708462cf964674d06f240fc037d6fc7` موفق شدند. اجرای PR به‌درستی job واقعی `discover` را skip می‌کند؛ پس دریافت زندهٔ RSS و artifact پس از ادغام هنوز تأیید نشده است.

**شواهد/شناسه:** PR #178؛ شاخهٔ `feat/offerchin-digikala-mag-discovery-20261114`؛ commit کد آزموده‌شده `ef55155f9708462cf964674d06f240fc037d6fc7`؛ workflowها: `43558086758` (کشف)، `43558086734` (regression)، `43558086735` (video fan-out).

**ریسک/بازگشت:** شکل و دسترس‌پذیری RSS ممکن است تغییر کند؛ در خطای fetch/XML گزارش تولید نمی‌شود و هیچ انتشار عمومی رخ نمی‌دهد. فیلتر واژگانی ممکن است مطلب مرتبطی را از دست بدهد یا نامزد کم‌ارزش را عبور دهد؛ خروجی باید بازبینی شود. دسترسی RSS مجوز بازنشر تجاری متن یا تصویر نیست؛ تا اخذ اجازهٔ روشن، فقط فراداده و پیوند نگهداری می‌شود. بازگشت ساده با غیرفعال‌کردن workflow و حذف ماژول مستقل انجام می‌شود؛ صف و ناشر محصول تغییری نمی‌کنند.

**وضعیت:** فقط شاخهٔ کاری/PR؛ هنوز ادغام، اجرای زمان‌بندی‌شده یا دریافت موفق زنده از feed تأیید نشده است. این تغییر زمان‌بند انتشار محصول یا رفتار production را تغییر نمی‌دهد.


## ۲۰۲۶-۱۱-۱۴ — سخت‌گیری کیفیت نامزدهای دیجی‌کالا مگ و نتیجهٔ اجرای زنده

**هدف:** جلوگیری از ورود خبرهای عمومی، شایعه‌ها و سوژه‌های فاقد ارزش خرید/کاربرد به فهرست تحریریه؛ اولویت با محتوای کوتاه و عملی برای تصمیم خرید یا استفادهٔ مخاطب است.

**تغییر/اقدام:** فیلتر عنوان اکنون وجود نشانهٔ عملی مثل راهنمای خرید/انتخاب، مقایسه، بررسی محصول، ارزش خرید، ارتقا یا ترفند کاربردی را لازم می‌داند. خبرهای مدیریتی اشخاص، موضوعات فضایی، آمار کاربران بازی، خبرهای فاقد قصد خرید، شایعه/ماکت و ادعاهای پزشکی یا ضدریزش مو حذف می‌شوند. رتبه‌بندی ابتدا به ارزش عملی و سپس به تازگی توجه می‌کند. namespace cache به نسخهٔ v2 تغییر یافت تا خروجی‌های دیده‌شده تحت فیلتر اولیه، با قواعد دقیق‌تر دوباره ارزیابی شوند. متن و تصویر مقاله همچنان واکشی یا ذخیره نمی‌شوند و هیچ انتشار عمومی فعال نشده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/digikala_mag_discovery.py`، `affilio_radar/test_digikala_mag_discovery.py`، `.github/workflows/offerchin-mag-source-discovery.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** دو تست جدید برای حذف خبر غیرعملی/شایعه و تقدم راهنمای خرید بر ترفند عمومی اضافه شد. آزمون نهایی PR #179 باید پس از اجرا ثبت شود. اجرای زندهٔ نسخهٔ اول پس از ادغام PR #178 روی ۱۴ نوامبر ۲۰۲۶ با موفقیت RSS را خواند: `feed_items=70`، `rejected_irrelevant_or_excluded=41` و ۲۰ نامزد در artifact بارگذاری شد. بازبینی همان artifact ضرورت سخت‌گیری بیشتر را نشان داد.

**شواهد/شناسه:** PR #178؛ merge commit `847239d4dcf8794063a7a05c299b1391c366af1c`؛ live workflow run `43558404517`؛ artifact ID `14098884855`؛ شاخهٔ اصلاح کیفیت `feat/offerchin-digikala-mag-quality-filter-20261114`.

**ریسک/بازگشت:** فیلتر عنوانی ممکن است راهنمای مفیدی را که عنوانش نشانهٔ خرید ندارد کنار بگذارد؛ از سوی دیگر ممکن است تیتر گمراه‌کننده از فیلتر عبور کند. خروجی همچنان فقط نامزد بازبینی است و نباید خودکار منتشر شود. در صورت افت recall، regexهای ACTIONABLE_TITLE و EXCLUDED قابل تنظیم‌اند. بازگشت نسخهٔ فیلتر با revert این PR ممکن است؛ cache v2 از داده‌های قدیمی جداست و state ناشر محصول را تغییر نمی‌دهد.

**وضعیت:** تغییر سخت‌گیری کیفیت در PR #179 و تا پایان تست‌ها ادغام‌نشده است؛ نسخهٔ اولیهٔ کشف فراداده روی main فعال است. هیچ تولید خلاصه یا پست عمومی به این جریان وصل نشده است.

## ۲۰۲۶-۱۱-۱۴ — ثبت اعتبارسنجی فیلتر کیفیت دیجی‌کالا مگ

**هدف:** ثبت شواهد آزمون فیلتر سخت‌گیرانه‌تر برای جلوگیری از خبرهای عمومی/شایعه و اولویت‌دادن به راهنمای خرید و مقایسه‌های کاربردی.

**تغییر/اقدام:** فیلتر دلیل رد را جداگانه ثبت می‌کند: موضوعات خارج از دامنه، تیترهای فاقد قصد خرید/کاربرد، و سوژه‌های speculative. بررسی دامنه‌های ممنوع قبل از سنجش actionable بودن انجام می‌شود تا آمار رد با علت درست ثبت شود. namespace حافظهٔ دیده‌شده‌ها به v2 تغییر کرده تا نامزدهای ذخیره‌شده تحت فیلتر نسخهٔ اول دوباره ارزیابی شوند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/digikala_mag_discovery.py`، `affilio_radar/test_digikala_mag_discovery.py`، `.github/workflows/offerchin-mag-source-discovery.yml`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** ۱۰ تست واحد کشف منبع در workflow مستقل موفق شدند؛ تست‌های صف تحویل و چهارعامل در regression موفق شدند؛ آزمون یکپارچهٔ video fan-out نیز موفق شد. گیت مستندسازی در اجرای نخست PR #179 شکست خورد چون changelog در diff خود PR نبود؛ این entry برای پوشش مستنداتی همان تغییر به شاخهٔ PR افزوده می‌شود و نتیجهٔ گیت باید دوباره تأیید شود.

**شواهد/شناسه:** PR #179؛ commit کد آزموده‌شده `4925ca326094021e5d7bb7dd2b79724415f1475f`؛ اجرای تست مستقل `43558775122`؛ regression `43558775114`؛ video fan-out `43558775118`؛ خطای اولیهٔ docs gate `43558775216`.

**ریسک/بازگشت:** فیلتر عنوانی ممکن است سوژهٔ عملی با عنوان غیرمستقیم را از دست بدهد؛ فهرست خروجی همچنان فقط نامزد بازبینی است و انتشار خودکار وجود ندارد. با تنظیم الگوهای `ACTIONABLE_TITLE` و `EXCLUDED` می‌توان حساسیت فیلتر را اصلاح کرد.

**وضعیت:** کد و تست‌ها موفق‌اند؛ تکمیل گیت مستندسازی و ادغام PR #179 هنوز در انتظار است.


## ۲۰۲۶-۱۱-۱۴ — بستن شکاف تیترهای افشاگرانه در کشف دیجی‌کالا مگ

**هدف:** جلوگیری از عبور خبرهای مبتنی بر افشا/گمانه‌زنی دربارهٔ محصولات آینده به فهرست سوژه‌های کاربردی تحریریه.

**تغییر/اقدام:** الگوی `SPECULATIVE_TITLE` علاوه بر «شایعه»، «لو رفت» و «ماکت»، واژه‌های «فاش» و «افشا» و عبارت‌های دارای «احتمال» را نیز رد می‌کند. یک تست رگرسیون با نمونهٔ تیتر دوربین گلکسی S27 اضافه شده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/digikala_mag_discovery.py`، `affilio_radar/test_digikala_mag_discovery.py`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** فیلتر نسخهٔ دوم در اجرای زندهٔ `43559273004` از ۷۰ آیتم فید، ۱۱ نامزد انتخاب کرد؛ بازبینی نشان داد یک تیتر افشاگرانه با واژهٔ «فاش» از فیلتر عبور کرده است. تست جدید باید پس از اجرای PR #181 همراه با ۱۰ تست قبلی پاس شود؛ اجرای زندهٔ تأییدی پس از ادغام نیز لازم است.

**شواهد/شناسه:** PR #180؛ merge commit `6da5f032b6fc4c6912bfd6431700abb305c97301`؛ live run `43559273004`؛ artifact ID `14099677297`; فهرست ۱۱ نامزد خروجی.

**ریسک/بازگشت:** واژهٔ «احتمال» می‌تواند در تیترهای غیرشایعه نیز به‌کار رود و باعث رد کاذب شود؛ در صورت افت پوشش، الگوی `SPECULATIVE_TITLE` باید با نمونه‌های واقعی تنظیم شود. نامزدهای خروجی همچنان نیازمند بازبینی انسانی‌اند.

**وضعیت:** اصلاح در شاخهٔ `fix/offerchin-mag-rumor-filter-20261114` و PR #181؛ تا پایان CI و اجرای مجدد زنده ادغام نشده است.


## ۲۰۲۶-۱۱-۱۴ — بازنشانی cache کشف دیجی‌کالا مگ پس از نهایی‌شدن فیلتر

**هدف:** پس از سخت‌ترشدن فیلتر تیترهای افشاگرانه در PR #181، نامزدهای قبلاً انتخاب‌شده باید یک بار با قواعد نهایی دوباره ارزیابی شوند.

**مشاهدهٔ زنده:** اجرای `43559563222` با موفقیت ۷۰ آیتم فید را خواند، ۶۰ مورد را خارج از دامنه/نامرتبط تشخیص داد، ۶ مورد را speculative و ۱۳ مورد را فاقد actionable signal شمرد؛ اما ۱۰ مورد قبلاً در cache v2 دیده شده بودند و در خروجی نامزد جدیدی باقی نماند. بنابراین cache باگ در خود فیلتر نبود؛ نسخهٔ حافظه پس از تغییر سیاست باید یک بار bump شود.

**تغییر/اقدام:** namespace از `offerchin-mag-seen-v2-` به `offerchin-mag-seen-v3-` تغییر داده شد تا تمام نامزدها با سیاست نهایی مجدداً ارزیابی شوند. cache مربوط به کشف تحریریه است و state صف/ناشر محصول را لمس نمی‌کند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-mag-source-discovery.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** PR #182 باید تست‌های موجود discovery، regression، video fan-out و documentation را دوباره اجرا کند. پس از ادغام باید اجرای زنده با cache v3 بررسی شود؛ در آن مرحله فهرست تازه باید بر اساس فیلتر نهایی تولید شود.

**شواهد/شناسه:** PR #181 و merge commit `d60f9f13c851b642eeaab65c34e49b6e1b59fff9`؛ اجرای زنده `43559563222`؛ artifact ID `14099008090` با `new_candidates=0` و `already_seen=10`.

**ریسک/بازگشت:** bump نسخهٔ cache عمداً موجب ارزیابی مجدد یک‌بارهٔ نامزدهای هفت‌روزه می‌شود؛ پس از آن dedup عادی برقرار می‌ماند. بازگشت به v2 موجب می‌شود نامزدهای قبلاً دیده‌شده مجدداً پنهان بمانند؛ بنابراین فقط در صورت لغو تغییر سیاست، rollback شود.

**وضعیت:** تغییر در شاخهٔ `fix/offerchin-mag-cache-v3-20261114` و PR #182؛ هنوز ادغام یا اجرای زندهٔ v3 تأیید نشده است.


## ۲۰۲۶-۱۱-۱۴ — تأیید cache v3 و فهرست واقعی نامزدهای دیجی‌کالا مگ

**هدف:** تأیید اینکه پس از تغییر cache، نامزدهای قبلی با فیلتر نهایی دوباره ارزیابی می‌شوند و dedup مانع خروجی ناخواستهٔ خالی نمی‌شود.

**تغییر/اقدام:** PR #182 با موفقیت ادغام شد؛ namespace cache اکنون `offerchin-mag-seen-v3-` است. workflow مستقل RSS همچنان هر ۳۰ دقیقه اجرا می‌شود و فقط artifact فراداده‌ای تولید می‌کند.

**نتیجهٔ اجرای زنده:** workflow run `43559910923` روی merge commit `c37c194ed96b76ce12c9699ae106abc4dd675a5a` موفق شد. ۷۰ آیتم فید پردازش شد؛ ۱۰ نامزد تازه پذیرفته شد؛ ۶۰ مورد در شمار کلی خارج از دامنه/کم‌ارزش رد شدند (۱۳ مورد فاقد نشانهٔ actionable و ۶ مورد speculative، زیرمجموعه‌های آماری این شمار هستند)؛ `already_seen=0`، URL نامعتبر صفر و خارج از بازه صفر بود.

**دسته‌های پذیرفته‌شده:** ۷ فناوری و گجت، ۱ خانه و آشپزخانه، ۱ پوشاک و زیبایی، ۱ راهنمای خرید مرتبط با خودرو. عنوان‌ها و پیوندها در artifact قرار دارند؛ متن مقاله و تصاویر آن دریافت/ذخیره نشده‌اند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-mag-source-discovery.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**شواهد:** PR #182؛ merge commit `c37c194ed96b76ce12c9699ae106abc4dd675a5a`؛ workflow run `43559910923`؛ artifact ID `14099114972`؛ نام فایل `offerchin-digikala-mag-candidates-43559910923.zip`.

**محدودیت و گیت انتشار:** خروجی همچنان نامزد بازبینی است، نه محتوای آمادهٔ انتشار. هیچ خلاصهٔ ماشینی تولید یا پست عمومی ارسال نشده است. پیش از انتشار باید متن فارسی مستقل ۳۵ تا ۶۰ واژه‌ای تولید، صحت نکته کنترل و پیوند منبع درج شود؛ متن/تصویر ناشر بدون مجوز روشن بازنشر نمی‌شود.

**وضعیت:** کشف RSS و خروجی ۱۰ نامزد با اجرای زنده تأیید شده؛ اتصال به صف انتشار عمومی عمداً انجام نشده است.


## ۲۰۲۶-۱۱-۱۴ — تبصرهٔ استمرار انتشار و زمان‌بندی پویای محصولات

**هدف:** جلوگیری از توقف انتشار در نبود نامزد محصول، بدون قربانی‌کردن اولویت محصولات ممتاز، FIFO چندرسانه‌ای، سقف روزانه یا گیت‌های صحت آفر.

**مشاهدهٔ مبنا:** اجرای واقعی ناشر در ۱۴ نوامبر، `hard_eligible=0`، `PENDING_QUEUE size=0` و `PUBLISHER_QUEUE_EMPTY` داشت؛ مرحلهٔ تحریریه نیز به‌دلیل `OFFERCHIN_EDITORIAL_PUBLISH_ENABLED=false` فقط shadow بود. اسکن کاتالوگ ۴۸۰ صفحه را پردازش کرد اما ۰ ردیف محصول برگرداند و چرخه را `complete_with_gaps` ثبت کرد؛ کشف دسته و جست‌وجوی دیجی‌کالا نیز 404 داشت. آخرین snapshot کامل سالم ۳۰۰۰ نامزد داشت و چرخهٔ کامل قبلی حدود ۳۳ ساعت و ۴۴ دقیقه طول کشیده بود. علاوه بر آن، sidecar ویدئو ۱۲۷ رکورد را به‌ظاهر pending نشان می‌داد؛ ۱۵ وضعیت pending مقصد Aparat روی آفرهای منقضی بود و ۶ رکورد legacy فاقد وضعیت تولید/مقصد قابل‌پردازش بودند.

**تغییر/اقدام:**
- انتشار عمومی محتوای تحریریهٔ فارسی در workflow زمان‌بندی‌شدهٔ کانال و workflow ویدئو صریحاً فعال شد. گپ هدف تحریریه ۵۵ دقیقه باقی ماند؛ shadow read-only همچنان بدون انتشار است.
- قفل FIFO حفظ شد: تحریریه تا terminal شدن مقصدهای تصویری اصلی Telegram/Bale منتظر می‌ماند. پس از terminal شدن آن دو، انتشار تصویری محصولات جدیدتر می‌تواند ادامه یابد؛ retry ویدئوی تحریریه محصول ممتاز را عقب نمی‌اندازد.
- در workflow ویدئویی، بررسی ویدئوی تحریریهٔ فعال پیش از fan-out ویدئوهای محصولات جدیدتر اجرا می‌شود؛ تابع تحریریه فقط اگر محصول ویدئویی قدیمی‌ترِ واقعاً قابل‌ارسال باقی نمانده باشد، محتوای تازه می‌سازد. بنابراین FIFO ویدئو حفظ می‌شود، اما صف ویدئو قفل انتشار تصویری را در اختیار نمی‌گیرد.
- وضعیت منقضی/نزدیک انقضا و legacy فاقد وضعیت عملیاتی دیگر صف تحریریه را بی‌نهایت مسدود نمی‌کند؛ pending معتبر با deadline آینده همچنان مقدم است.
- ساعت مستقل `last_product_channel_published_at` اضافه شد. ارسال تحریریه فقط ساعت عمومی کانال را به‌روزرسانی می‌کند و cadence محصول را reset نمی‌کند.
- فاصلهٔ انتخاب محصول به‌صورت پویا از تعداد نامزدهای واجدشرایط و ETA تخمینی چرخهٔ سالم بعدی محاسبه می‌شود؛ کف ۲۷ دقیقه، سقف ۶ ساعت و سقف مشترک ۷۲ پست روزانه رعایت می‌شود. زمان‌بند عمومی ۲۷دقیقه‌ای حفظ شده تا تحریریهٔ ۵۵دقیقه‌ای در اجراهای کم‌نامزد از قلم نیفتد.
- شمارندهٔ سقف روزانه اکنون پست‌های تأییدشدهٔ تحریریه را نیز در کنار محصول می‌شمارد. گیت‌های تقاضا، چهارعامل، قیمت/موجودی/تخفیف/لینک، deadline و idempotency تغییر نکردند.
- تست‌های اختصاصی cadence، استقلال ساعت محصول، رکورد ویدئویی expired/legacy و سقف مشترک افزوده شدند؛ workflow قرارداد تحریریه نیز با حالت عملیاتی جدید هم‌راستا شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/content_delivery.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/publisher.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/test_content_delivery.py`، `affilio_radar/test_shared_selection_media_routing.py`، `affilio_radar/test_editorial_publisher.py`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/offerchin-video-publisher.yml`، `.github/workflows/offerchin-editorial-contract.yml`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `docs/PROJECT_CHARTER_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/OFFERCHIN_SHARED_SELECTION_MEDIA_ROUTING_FA.md`.

**آزمون و نتیجه:** اجرای نخست PR #184 نشان داد دو مجموعهٔ ویدئو به‌علت fixtureهای قدیمیِ فاقد وضعیت تولید/مقصد صریح و ناهماهنگی در requeue ویدئوی دارای deadline فعال شکست خوردند؛ این شکست‌ها پنهان یا به‌عنوان موفقیت گزارش نشدند. اصلاح هماهنگ Python/Cloudflare برای requeue امنِ `skipped_expiring_soon` با deadline مستند و اصلاح YouTube برای `skipped_unverified_deadline`، به‌همراه به‌روزرسانی fixtureها و تست dispatch دقیقه‌ای، روی همان شاخه ثبت شد. اجرای دوبارهٔ CI پس از آخرین تغییر هنوز در انتظار است. تست قرارداد تحریریه، fallback، crawler و adapter در اجرای اول موفق شدند. پس از ادغام، انتشار واقعی فقط با شناسهٔ پیام کانال یا شناسه/URL و وضعیت عمومی ویدئو تأیید خواهد شد.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-editorial-continuity-dynamic-cadence-20261114`؛ مشاهدهٔ ناشر `run 43601837168`؛ اسکن کاتالوگ `run 43602239422`؛ ویدئوی یکپارچه `run 43602187646`؛ sidecar ویدئو در زمان بازبینی `generated_at=2026-11-14T14:14:15Z`.

**ریسک/بازگشت:** ETA چرخهٔ بعدی برآوردی است و API دیجی‌کالا/تکمیل crawl هنوز مشکل مستقل دارد؛ اگر چرخهٔ سالم دیرتر برسد، cadence با کف ۲۷ دقیقه ادامه می‌یابد و تحریریه فقط نقش پرکنندهٔ شکاف را دارد. بازگشت با revert کردن همین PR ممکن است؛ وضعیت‌های واقعی انتشار و receiptها نباید حذف یا بازنویسی شوند.

**وضعیت:** پیاده‌سازی در شاخهٔ PR؛ هنوز ادغام و انتشار عمومیِ حاصل از این تغییر تأیید نشده است.

## ۲۰۲۶-۱۱-۱۴ — تکمیل تبصرهٔ اضطراری، زمان‌بندی شناور و dispatch بر پایهٔ صف

**هدف:** اجرای استمرار انتشار در زمان خرابی کشف محصول، سپس توزیع مساوی محصولات منتخب تا اسکن سالم بعدی و درج اختیاری تحریریه در فاصله‌های امن، بدون تبدیل ۲۷ دقیقه به نرخ ثابت.

**تغییر/اقدام:**
- استثنای اضطراری فقط از snapshot سالمِ آخر، با SHA و timestamp ثابت‌شده، leadهای شناسه/URL می‌گیرد؛ قیمت/تخفیف/موجودی/انقضای قدیمی snapshot حذف می‌شوند و همهٔ شروط تجاری زنده دوباره بررسی می‌شوند. استثنا فقط تا نخستین چرخهٔ سالم جدید یا ۷۲ ساعت فعال می‌ماند و تنها گیت تقاضا را با سه حداقل امتیاز و harmonic mean سخت‌گیرانه relax می‌کند.
- گیت آخرین‌مرحلهٔ ناشر نیز استثنا را دوباره با state فعال، SHA snapshot و membership همان product_id تأیید می‌کند؛ حالت blocked کاتالوگ به‌تنهایی مجوز ارسال اضطراری نیست.
- interval محصولات بر اساس تعداد slotهای قابل‌استفاده و ETA چرخهٔ سالم بعدی محاسبه و صف محصولات منتشرنشده به‌صورت مساوی reflow می‌شود؛ interval حداقل ۲۷ دقیقه دارد و سقف مصنوعی ۶ ساعت ندارد.
- sidecar Worker اکنون next_channel_content_due_at و cycle ID برنامهٔ محصول را نگه می‌دارد. Worker در هر دقیقه نزدیک‌ترین slot محصول/تحریریه را بررسی می‌کند؛ پایان چرخهٔ سالم تازه باعث refresh صف می‌شود، ولی حداقل ۲۷ دقیقه بین دو پست عمومی دور زده نمی‌شود. نبود slot فعال، fallback مستقل ۵۵دقیقه‌ای تحریریه را حفظ می‌کند.
- تحریریهٔ مرتبط در صورت وجود فاصلهٔ امن، در میانهٔ فاصلهٔ دو محصول صف می‌شود؛ هر ID در یک دور یک‌بار مصرف می‌شود، موارد جدیدِ تأییدشدهٔ editorial_approved_items.json فوراً به چرخه اضافه می‌شوند و پس از مصرف همهٔ موارد معتبر، چرخه دوباره آغاز می‌شود. RSS دیجی‌کالا مگ همچنان فقط metadata تولید می‌کند؛ خلاصهٔ فارسی منبع‌دار و بازبینی‌شده باید پیش از افزودن به فهرست approved تهیه شود.
- نقص legacy ویدئوی Aparat نیز اصلاح شد: رکورد قدیمی با generation صریح pending و فیلد Aparat غایب، فقط در Shorts-only به‌عنوان hand-off بررسی‌نشده تشخیص داده می‌شود؛ وضعیت‌های terminal همچنان مسدودند.

**فایل‌ها/سامانه‌ها:** affilio_radar/catalog_status_snapshot.py، affilio_radar/affilio_radar.py، affilio_radar/publisher.py، affilio_radar/content_delivery.py، affilio_radar/editorial_content.py، affilio_radar/editorial_publisher.py، تست‌های snapshot/cadence/selection/publisher/editorial، cloudflare/affilio-minute-dispatcher.js، cloudflare/affilio-minute-dispatcher.test.mjs، .github/workflows/offerchin-publisher.yml، همین handbook/changelog.

**آزمون و نتیجه:** در آخرین SHA آزموده‌شدهٔ 12a087fb6a3a9d74262fcbb6b57ae45924615eeb، تست‌های Four-Factor، Fallback، Top-100/DigiPay، Catalog Sweep، Editorial Contract، Messenger Adapter، Video Fan-out، Platform Logos و Node/Cloudflare dispatcher همگی موفق شدند. Documentation Gate در زمان ثبت این ورودی هنوز در حال اجرا بود. اجرای production روی main و ارسال عمومی با رسید واقعی هنوز تأیید نشده است.

**شواهد/شناسه:** PR #184؛ شاخهٔ fix/offerchin-editorial-continuity-dynamic-cadence-20261114؛ CI runهای 43618005001، 43618005000، 43618004974، 43618005043، 43618005064، 43618004992، 43618005170، 43618005052، 43618005045 و 43618004982.

**ریسک/بازگشت:** ETA چرخهٔ بعدی تخمینی است؛ اگر API دیجی‌کالا 403/404 یا gap اسکن بدهد، اسکن کامل ادعا نمی‌شود. در نبود snapshot سالم هش‌شده، محصول اضطراری منتشر نمی‌شود و فقط تحریریهٔ تأییدشده مسیر استمرار است. بازگشت با revert کردن PR #184 انجام می‌شود؛ state، صف و رسیدهای قبلی نباید reset شوند.

**وضعیت:** کد روی شاخهٔ PR پیاده‌سازی شده و CI اصلی سبز است؛ گیت مستندسازی، ادغام PR و استقرار production/تأیید پست واقعی هنوز جداگانه لازم‌اند.

## ۲۰۲۶-۱۱-۱۴ — بیدارباش پیش‌برنامه‌ریزی تحریریه و مجوز اضطراری Worker

**هدف:** اطمینان از اینکه تحریریهٔ مرتبط پیش از محصول در فاصلهٔ امن به صف اضافه شود و Cloudflare در پنجرهٔ اضطراری، ناشر را پیش از اجرای منطق راستی‌آزمایی Python مسدود نکند.

**تغییر/اقدام:**
- sidecar زمان مستقل `next_editorial_planning_at` را محاسبه می‌کند: ۲۷ دقیقه پس از آخرین پست کانالی، فقط وقتی تا محصول بعدی شکاف حداقل ۵۴ دقیقه وجود دارد و قبلاً تحریریه‌ای برای همان محصول ثبت نشده است. این زمان یک بیدارباش برای برنامه‌ریزی است، نه مجوز ارسال فوری.
- اگر صف محصولی وجود ندارد، زمان بررسی مستقل تحریریه ۵۵ دقیقه پس از آخرین پست یا آخرین بررسی بانک خالی است تا workflow بی‌وقفه dispatch نشود.
- پرچم اضطراری فقط وقتی در sidecar فعال می‌شود که state دارای snapshot hash‌شده، timestamp مبنا، پنجرهٔ منقضی‌نشده و `snapshot_lead_fallback_enabled=true` باشد. Worker همین SHA و زمان انقضا را کنترل می‌کند و در صورت معتبر بودن فقط dispatch محدود می‌دهد؛ عضویت دقیق محصول در snapshot، انقضا و داده‌های تجاری زنده همچنان در Python و ناشر آخرین‌مرحله بررسی می‌شود.
- حداکثر ۵۰ lead از snapshot قدیمی در هر batch بررسی می‌شود و برای آن‌ها ظرفیت واکشی زنده رزرو می‌شود تا کشف معمول نتواند بودجهٔ بررسی را کاملاً پر و مسیر اضطراری را گرسنه کند.
- سقف ۷۲ پست روزانه، فاصلهٔ حداقل ۲۷ دقیقه، گیت‌های تجاری/ایمنی و چرخش بانک تحریریه حفظ شده‌اند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_status_snapshot.py`، `affilio_radar/publisher.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `affilio_radar/test_affilio.py`، `affilio_radar/test_catalog_status_snapshot.py`، handbook و همین changelog.

**آزمون و نتیجه:** روی SHA `82d73085c635b0f766a4f7ac1151ed01dcea71b7`، تست‌های Python ranking/fallback/top-100/catalog/editorial/adapters/video و تست Node/Cloudflare موفق شدند؛ Worker syntax و Wrangler dry-run نیز موفق شدند. Documentation Gate در اجرای نخست شکست خورد، چون همین ورودی کوتاه فاقد برچسب‌های الزامی بود؛ این ورودی ساختاریافته شد تا گیت دوباره اجرا شود. هیچ اجرای production یا انتشار عمومی با این SHA ادعا نمی‌شود.

**شواهد/شناسه:** PR #184؛ شاخهٔ `fix/offerchin-editorial-continuity-dynamic-cadence-20261114`؛ آخرین SHA آزموده‌شده `82d73085c635b0f766a4f7ac1151ed01dcea71b7`؛ CIهای Python/Worker با runهای `43619322741`، `43619322758`، `43619322778`، `43619322805`، `43619322806`، `43619322837` و گیت مستندات `43619322796`.

**ریسک/بازگشت:** ETA چرخهٔ بعدی تخمینی است. اگر snapshot سالم hash-verified یا state اضطراری منقضی/ناسازگار باشد، محصول قدیمی از تبصره پذیرفته نمی‌شود و تحریریهٔ تأییدشده مسیر استمرار می‌ماند. انتشار عمومی تا ادغام PR، موفقیت deploy واقعی Cloudflare و مشاهدهٔ رسید عمومی کانال تأیید نشده است. بازگشت با revert کردن PR #184 انجام می‌شود؛ state و رسیدهای موجود نباید reset شوند.

**وضعیت:** پیاده‌سازی در شاخهٔ PR است؛ گیت مستندات پس از این اصلاح باید دوباره بررسی شود؛ PR هنوز open و production rollout تأییدنشده است.


## ۲۰۲۶-۱۱-۱۴ — رفع توقف مسیر اضطراری به‌علت import ناقص در اجرای مستقیم

**هدف:** بازگرداندن امکان استفاده از leadهای snapshot سالمِ قبلی در اجرای واقعی ناشر، پس از توقف مسیر انتخاب محصول با خطای NameError.

**تغییر/اقدام:** بررسی لاگ production اجرای \`43620546875\` نشان داد \`load_emergency_continuity_candidates\` در import نسبی ماژول تعریف شده، اما در شاخهٔ \`except ImportError\` برای اجرای مستقیم فایل وارد نشده است. از آنجا که workflow دستور \`python affilio_radar/affilio_radar.py --select-only\` را اجرا می‌کند، همین مسیر fallback استفاده و انتخاب محصول با \`NameError\` متوقف می‌شد. helper به هر دو مسیر import افزوده شد و تست صریح برای دسترس‌پذیری آن در حالت import مستقیم به suite ناشر اضافه شد. سیاست اضطراری و شروط تجاری آن تغییر نکردند.

**فایل‌ها/سامانه‌ها:** \`affilio_radar/affilio_radar.py\`، \`affilio_radar/test_affilio.py\`، \`.github/workflows/offerchin-publisher.yml\`.

**آزمون و نتیجه:** تست regression مسیر import مستقیم، تست‌های کاتالوگ، validation، adapter و editorial در CI این PR موفق شده‌اند؛ گیت مستندسازی هنگام ثبت این ورودی هنوز در حال اجراست. پس از ادغام، dispatch و انتشار محصول اضطراری باید با لاگ انتخاب و رسید واقعی مقصد جداگانه تأیید شود.

**شواهد/شناسه:** PR #186؛ شاخهٔ \`fix/offerchin-emergency-helper-import-20261114\`؛ commit سرشاخهٔ اولیهٔ اصلاح \`fede9137f96544b990b34cd072c0c2a7d81341b8\`؛ اجرای production دارای خطا: \`43620546875\`.

**ریسک/بازگشت:** این تغییر فقط import شاخهٔ اجرای مستقیم را هم‌تراز مسیر package می‌کند و هیچ گیت انتخاب/انتشار را شل نمی‌کند. در صورت نیاز، با revert کردن PR #186 بازگشت انجام می‌شود؛ state، cursor و رسیدهای انتشار نباید reset شوند.

**وضعیت:** اصلاح و تست در PR؛ ادغام، اجرای مجدد ناشر و تأیید پست محصول اضطراری هنوز در انتظارند.


## ۲۰۲۶-۱۱-۱۴ — بیدارباش batch اضطراری و هم‌ترازی زمان تحریریه با نقطهٔ میانی

**هدف:** پس از فعال‌شدن تبصرهٔ اضطراری، خالی‌بودن صف محصول نباید باعث انتظار تا نوبت ۵۵ دقیقه‌ای تحریریه شود؛ در عین حال retry کشف نباید با انتشار عمومی اشتباه گرفته شود. بیدارباش تحریریه نیز باید با زمان واقعی صف هماهنگ باشد.

**تغییر/اقدام:**
- محاسبهٔ cadence هنگام آغاز چرخهٔ جدید، آخرین محصول منتشرشده پس از شروع همان اسکن را حتی اگر پیش از نوبت برنامه‌ریزی فعلی منتشر شده باشد به‌عنوان anchor حفظ می‌کند؛ این حالت دیگر به‌اشتباه با slot فوریِ ابتدای چرخه جایگزین نمی‌شود.
- در حالت emergency continuity معتبر و فقط وقتی هیچ slot محصول/تحریریهٔ زمان‌بندی‌شده‌ای وجود ندارد، Worker ناشر را با retry سه‌دقیقه‌ای برای بررسی batch بعدی leadهای snapshot بیدار می‌کند.
- حداقل ۲۷ دقیقه از آخرین پست عمومیِ تأییدشده و اولویت slotهای از قبل زمان‌بندی‌شده حفظ می‌شود؛ retry سه‌دقیقه‌ای صرفاً cadence بررسی/انتخاب است، نه cadence انتشار.
- در sidecar، بیدارباش تحریریه از ۲۷ دقیقه پس از آخرین پست به نقطهٔ میانی واقعی بین آخرین پست کانالی و محصول بعدی منتقل شد؛ اگر در دو سوی آن حداقل فاصلهٔ ایمن جا نشود، بیدارباش تحریریه ساخته نمی‌شود.
- فایل Workflow ناشر با marker محافظت‌شدهٔ `[publisher-run-now]` برای یک اجرای کنترل‌شده پس از merge علامت‌گذاری شد؛ این فقط شروع تبصرهٔ یک‌باره است و cadence جاری همچنان از صف و تعداد محصولات منتخب محاسبه می‌شود.
- cooldown خواندن آخرین اجرای ناشر اکنون رویدادهای guarded `push` و `workflow_dispatch` را هر دو می‌شناسد؛ بنابراین اجرای یک‌بارهٔ پس از merge باعث dispatch یک‌دقیقه‌ای تکراری نمی‌شود.
- سیاست ماده‌به‌مادهٔ تبصره اضطراری، توزیع مساوی محصولات در پنجرهٔ دو اسکن، قرارگیری تحریریهٔ مرتبط قبل از محصول و چرخش مجدد بانک به‌روز مستند شد. بانک اصلی و بانک تأییدهای تازه در هر اجرا ادغام می‌شوند؛ cooldown و اعتبار منبع همچنان اجباری‌اند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `affilio_radar/affilio_radar.py`، `affilio_radar/content_delivery.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_content_delivery.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و `docs/OFFERCHIN_FLOATING_PUBLICATION_POLICY_FA.md`.

**آزمون و نتیجه:** تست‌های regression برای (۱) retry اضطراری با رعایت حداقل فاصلهٔ انتشار، (۲) تقدم صف زمان‌بندی‌شده بر retry، (۳) بیدارباش در نقطهٔ میانی و (۴) حذف تحریریه در شکاف کوتاه اضافه شدند. نتیجهٔ نهایی فقط پس از CI مربوط به PR و بررسی رسید عمومی پس از rollout ثبت می‌شود.

**شواهد/شناسه:** PR #187؛ SHA شاخه پیش از تکمیل گیت مستندات `f8045a37dc4ff6ad9eee8b4f603822f75c7695f9`؛ اجرای تست Python `43625330467`؛ قرارداد تحریریه `43625330438`؛ تست Worker و dry-run استقرار `43625330363`.

**ریسک/بازگشت:** این تغییر هیچ گیت اعتبار قیمت/موجودی/هویت/تخفیف/افیلیت را حذف نمی‌کند و صرفاً زمان بررسی batch بعدی را جلو می‌آورد. در صورت rollback، Worker به انتظار قبلی بازمی‌گردد و cadence شناور محصول و state/رسیدهای قبلی دست‌نخورده می‌مانند.

**وضعیت:** تغییر در شاخهٔ PR؛ استقرار Worker و اجرای محصول اضطراری هنوز تا پس از CI و merge تأیید نشده‌اند.


## ۲۰۲۶-۱۱-۱۴ — ادغام و rollout سیاست زمان‌بندی شناور؛ نخستین تحریریهٔ عمومی

**هدف:** ثبت نتیجهٔ عملیاتی تبصرهٔ اضطراری و زمان‌بندی شناور پس از ادغام، جدا از نتیجهٔ آزمون‌های شاخه.

**تغییر/اقدام:**
- PR #187 با موفقیت در `main` ادغام شد؛ کد Worker، برنامه‌ریز تحریریه، anchor فاصله‌گذاری چرخه و تست‌های نگهبان فعال در main قرار گرفتند.
- Worker زمان‌بندی Cloudflare مستقر شد. بیدارباش اضطراریِ بعدی تا رعایت ۲۷ دقیقه حداقل فاصله از آخرین پست عمومی صبر می‌کند؛ پس از آن، اگر صف زمان‌بندی‌شده‌ای ساخته نشود و snapshot اضطراری معتبر بماند، بررسی batch بعدی با retry سه‌دقیقه‌ای ادامه می‌یابد.
- اجرای موفق ناشر یک batch با ۵۰ lead را بررسی کرد؛ ۴۶ lead به hand-off بررسی زنده اضافه شدند و cursor به ۱۰۰ رسید. هیچ محصولی در آن نوبت از اعتبارسنجی نهایی عبور نکرد، پس محصول نامعتبر منتشر نشد.
- برای جلوگیری از خالی‌ماندن کانال، مطلب فارسی امنیت حساب خرید با شناسهٔ `editorial:account-security` با رسید موفق در Telegram، Bale و Rubika منتشر شد.
- اجرای push یک‌باره در حالی که اجرای ناشر قبلی قفل را در اختیار داشت، لغو شد؛ اجرای قبلی تکمیل شد و دو ناشر موازی اجرا نشدند.

**فایل‌ها/سامانه‌ها:** Cloudflare Worker `affilio-minute-dispatcher`، GitHub Actions، صف تحویل محصول و تحریریه، دفتر راهنمای OfferChin و سیاست زمان‌بندی شناور.

**آزمون و نتیجه:** همهٔ گیت‌های PR #187 سبز شدند؛ تست Python شامل ۳۰۷ آزمون در اجرای نهایی پیشین موفق بود و تست‌های Worker، editorial, catalog, ranking, fallback, video, messenger, platform logo و Documentation Gate نیز موفق شدند. Deploy واقعی Cloudflare موفق بود. انتشار عمومی تحریریه از لاگ مقصدها تأیید شد؛ انتشار محصول در این batch تأیید نشد.

**شواهد/شناسه:** PR #187؛ merge commit `5dcf50c176275aca7dd8bb7330657e6a00cc3d1e`؛ Deploy run `43626568817`؛ Cloudflare Version ID `caf22bb3-8dae-474c-864c-b21a0f7c8d7c`؛ publisher run `43626023462`؛ push run لغوشده `43626568847`؛ آخرین پست کانالی `2026-11-14T18:26:43.613976+00:00`.

**ریسک/بازگشت:** استمرار انتشار به معنی اجبار به انتشار کالای بی‌اعتبار نیست. اگر هیچ محصولی از قیمت/موجودی/هویت/تخفیف/افیلیت زنده عبور نکند، تحریریهٔ معتبر جای خالی را پر می‌کند و انتخاب محصول در batchهای بعدی ادامه می‌یابد. حداقل ۲۷ دقیقه، سقف روزانه، cooldown و کنترل تکرار حذف نمی‌شوند.

**وضعیت:** ادغام و Deploy تأییدشده؛ یک محتوای تحریریه‌ای در سه مقصد عمومی ارسال شده؛ محصول اضطراری در اولین batch پیدا نشد؛ اولین بیدارباش بعدی پس از حداقل فاصلهٔ انتشار در انتظار اجرای زمان‌بندی‌شده است.


## ۲۰۲۶-۱۱-۱۴ — نتیجهٔ نخستین اسکن پس از rollout و ادامهٔ تبصرهٔ اضطراری

**هدف:** تعیین اینکه آیا اسکن بعدی کاتالوگ snapshot سالم تازه‌ای ساخته و می‌توان تبصرهٔ اضطراری را خاتمه داد یا خیر.

**تغییر/اقدام:**
- Workflow اسکن کاتالوگ `43626848687` پس از rollout به‌صورت خودکار اجرا و سه batch کنترل‌شده را شروع کرد.
- batch ثبت‌شده ۴۸۰ صفحه را بررسی کرد: `pages_attempted=480`، `pages_ok=480`، اما `products=0` و `nonempty_product_pages=0` بود.
- در همان نتیجه، ۱۹۰۹ دسته در چرخهٔ جاری غیرقابل‌دسترسی، ۳۰۱۰ صفحه در صف، صفر دستهٔ کامل‌شده در چرخهٔ جاری و وضعیت `complete_with_gaps` ثبت شد.
- snapshot سالم قبلی با ۳۰۰۰ candidate و تاریخ تکمیل ۱۰ نوامبر ۲۰۲۶ حفظ شد. بنابراین اسکن جدید واجد شرایط خاتمهٔ تبصره نیست؛ emergency continuity تا snapshot کامل و معتبر بعدی فعال می‌ماند.

**فایل‌ها/سامانه‌ها:** GitHub Actions catalog sweep، `catalog_sweep_status.json`، صف صفحات و candidate snapshot اضطراری، Cloudflare Worker `affilio-minute-dispatcher`.

**آزمون و نتیجه:** اجرای Workflow از نظر فنی موفق بود، اما معیار محصولی/کامل‌بودن اسکن شکست خورد: صفر محصول تازه استخراج شد و ۱۹۰۹ دسته unqueryable گزارش شدند. این وضعیت به‌عنوان اسکن سالم ثبت نشد و snapshot سالم قبلی جایگزین نشد.

**شواهد/شناسه:** Catalog Sweep run `43626848687`؛ job `132544572510`؛ log marker `PARALLEL_CATALOG_SWEEP_SUMMARY`؛ آخرین snapshot سالم `2026-11-10T21:00:41.336795+00:00` با ۳۰۰۰ candidate.

**ریسک/بازگشت:** انتشار محصول فقط از leadهای snapshot پس از بازبینی زندهٔ قیمت، موجودی، هویت، تخفیف و لینک افیلیت مجاز است. صفر محصول تازه به معنی توقف انتشار نیست؛ محتوای تحریریهٔ معتبر و retry کنترل‌شدهٔ emergency discovery جایگزین می‌شوند. هرگز snapshot ناقص به‌عنوان snapshot کامل علامت‌گذاری نشود.

**وضعیت:** اسکن بعدی اجرا شده ولی کامل و معتبر نیست؛ تبصرهٔ اضطراری باز است؛ retryهای ناشر طبق فاصلهٔ ایمن عمومی و سیاست سه‌دقیقه‌ای بررسی batch ادامه می‌یابد.


## ۲۰۲۶-۱۱-۱۵ — حذف فاصله‌های ثابت، اصلاح مسیر محصول و بهبود تحریریه

**هدف:** بازگرداندن اولویت واقعی محصولات و اجرای سیاست انتشار شناور؛ جلوگیری از پست تحریریهٔ مستقل؛ خواناتر کردن منابع و دعوت به کانال و افزودن تصویر مرتبط.

**تغییر/اقدام:**
- همهٔ slotهای محصول با تقسیم مساوی زمان باقی‌مانده تا ETA معتبر اسکن سالم بعدی بر تعداد محصولات منتخبِ منتشرنشده محاسبه می‌شوند. فاصلهٔ ثابت عمومی ۲۷/۵۵ دقیقه یا فاصلهٔ ایمنی وجود ندارد. تحریریه فقط در نقطهٔ میانی فاصلهٔ واقعی تا محصول بعدی قرار می‌گیرد و بدون slot محصول، هیچ پست تحریریه‌ای ساخته نمی‌شود.
- مسیر اعتبارسنجی اضطراری اجازه می‌دهد در صورت تطبیق شناسهٔ دقیق، عنوان محصول صرفاً از snapshot کامل و hash-pinned به‌عنوان fallback هویتی بازیابی شود؛ هیچ قیمت، تخفیف، موجودی، تصویر یا لینک تاریخی از snapshot به‌عنوان دادهٔ زنده پذیرفته نمی‌شود.
- مسیر اسکن برای درخواست فهرست دسته، علاوه بر Search API v2، دو route جایگزین عمومی را هم امتحان می‌کند؛ پاسخ ۴۰۳ به‌عنوان رد قطعی دسته تلقی نمی‌شود و قابل retry باقی می‌ماند. شناسهٔ sort برای bestseller به مقدار ۵ اصلاح شد.
- متن تحریریه دارای فاصله‌گذاری بندها، ایموجی موضوعی، معرفی فارسی سازمان/عنوان منبع، URL در خط جدا و CTA کلیک‌خور Telegram/Bale است. اگر عکس محصول مرتبط موجود باشد در پوستر استفاده می‌شود؛ در غیر این صورت تصویرسازی اختصاصی برای موضوع ایجاد می‌شود.
- یک خلاصهٔ مستقل فارسی دربارهٔ بررسی بازهٔ تحویل بر پایهٔ مقالهٔ دیجی‌کالا مگ، بدون کپی متن/تصویر مقاله، به صف تأییدشده افزوده شد.
- سه regression اصلاح شد: حفظ cursor بر اساس شناسهٔ دسته پس از مرتب‌سازی taxonomy، مقدار bestseller sort، و fixture تحریریه با topic معتبر.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `affilio_radar/affilio_radar.py`، `catalog_sweep.py`، `parallel_catalog_sweep.py`، `content_delivery.py`، `publisher.py`، `editorial_publisher.py`، `editorial_video.py`، آزمون‌های مرتبط، `editorial_approved_items.json`، `docs/OFFERCHIN_FLOATING_PUBLICATION_POLICY_FA.md`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، handbook و changelog.

**آزمون و نتیجه:** regressionها و Documentation Gate در شاخهٔ تازه بر پایهٔ آخرین main دوباره اجرا می‌شوند؛ تا پیش از نتیجهٔ Actions، قبولی تست‌ها یا رفع کامل ۴۰۳/۴۰۴ ادعا نمی‌شود. اجرای قبلی ناشر در ۱۵ نوامبر ۲۴۸ مورد از ۲۵۰ بررسی اضطراری را به‌علت عنوان ناقص رد کرد و صف محصول خالی ماند؛ اسکن فعلی نیز snapshot سالم جدید ندارد.

**شواهد/شناسه:** کد منبع از PR #188 با head SHA `e14244fa68f915f0df6aef01770648309165213e` منتقل شد؛ شاخهٔ تازه از main با SHA `7dbee5efb89c6fff7b73d064c973c5643890b5f3` ساخته شد. نتیجهٔ CI و رسیدهای واقعی محصول پس از اجرای شاخهٔ تازه ثبت می‌شوند.

**ریسک/بازگشت:** اگر routeهای جایگزین یا APIهای دسته نیز از محیط اجرا ۴۰۳/۴۰۴ بدهند، اسکن همچنان کامل محسوب نمی‌شود و انتشار محصول فقط با اعتبارسنجی زندهٔ leadهای اضطراری مجاز است؛ هیچ کالای نامعتبر منتشر نمی‌شود. rollback با revert کردن commit این شاخه ممکن است؛ فایل‌های runtime state، صف و رسیدها reset نمی‌شوند.

**وضعیت:** تغییرات در شاخهٔ تازه آمادهٔ CI؛ merge، deploy و انتشار محصول جدید هنوز انجام‌شده محسوب نمی‌شوند.


## ۲۰۲۶-۱۱-۱۵ — حذف تنظیم قدیمی فاصلهٔ ثابت انتشار

**هدف:** حذف هر اثر باقی‌مانده از تنظیم فاصلهٔ ثابت در پیکربندی زمان‌بندی کانال‌ها.

**تغییر/اقدام:** متغیر بلااستفادهٔ `AFFILIO_MIN_POST_INTERVAL_HOURS` از `.github/workflows/affilio-radar.yml` حذف شد. تست رگرسیون افزوده شد تا بازگشت این متغیر به Workflow را رد کند. در کد جاری، فاصلهٔ محصولات صرفاً از تقسیم پنجرهٔ باقی‌مانده تا ETA اسکن سالم بین محصولات منتخب محاسبه می‌شود. retry سه‌دقیقه‌ای Worker فقط برای کشف batch بعدی در نبود slot است و آستانهٔ ۲۸دقیقه‌ای فقط stale-run recovery است؛ هیچ‌یک زمان‌بندی پست نیستند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/affilio-radar.yml`، `affilio_radar/test_content_delivery.py`، `cloudflare/affilio-minute-dispatcher.js` (بررسی رفتار)، handbook و این دفتر.

**آزمون و نتیجه:** تست جدید `test_publication_workflow_has_no_fixed_post_interval_setting` افزوده شد؛ اجرای CI و Documentation Gate در انتظار است. هیچ انتشار یا اجرای عمومی به‌واسطهٔ این حذف انجام نشده است.

**شواهد/شناسه:** شاخهٔ `chore/offerchin-remove-stale-publication-interval-20261115` از main با commit پایهٔ `8de0ccf67a0c93f59f3bc52e4e906dd60ede0f15` ساخته شد.

**ریسک/بازگشت:** حذف این متغیر رفتار زمان‌بندی را تغییر نمی‌دهد، زیرا در موتور صف مصرف نمی‌شد؛ rollback فقط با افزودن دوبارهٔ همین تنظیم ممکن است و توصیه نمی‌شود.

**وضعیت:** تغییرات روی شاخهٔ مستقل آمادهٔ بررسی و CI؛ هنوز در main ادغام نشده‌اند.


## ۲۰۲۶-۱۱-۱۵ — رفع توقف اسکن کاتالوگ پس از حذف APIهای قدیمی دیجی‌کالا

**هدف:** بازگرداندن اسکن واقعی کاتالوگ و جلوگیری از ثبت اشتباه هزاران دسته به‌عنوان غیرقابل‌جست‌وجو پس از تغییر API عمومی دیجی‌کالا.

**تغییر/اقدام:** endpointهای حذف‌شدهٔ `/v1/search/`، `/v1/autocomplete/` و `/v2/category/{id}/` از مسیر اصلی اسکن کنار گذاشته شدند. کشف دسته از Discovery Search و `query_attributes.category_ids` انجام می‌شود؛ پیمایش هر دسته با فیلتر `categories[0]` و sort بومی ۷ (پرفروش‌ترین) انجام می‌شود. یک preflight پیش از اسکن تولیدی اضافه شد تا تغییر route/schema باعث fail-closed شود. نسخهٔ مسیر در state ذخیره می‌شود و با مهاجرت به قرارداد جدید، صف همهٔ دسته‌ها از صفحهٔ اول دوباره ساخته می‌شود؛ تاریخچهٔ انتشار و state ناشر پاک نمی‌شوند. تست‌های endpoint و مهاجرت صف اصلاح/اضافه شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** کامپایل کدهای اسکنر موفق بوده است. اجرای کامل regressionهای رتبه‌بندی/کاتالوگ و اسکن زندهٔ endpoint جدید در GitHub Actions پس از اصلاح نهایی تست‌ها در انتظار نتیجه است؛ تا دریافت نتیجهٔ موفق، پوشش کاتالوگ و انتشار واقعی موفق اعلام نمی‌شود.

**شواهد/شناسه:** کد اسکنر: `7fdc6d8019ba429374c90e6c021a29269d9e0381` و `9544e18d06bab58959f8f3c38ded38fda8ce34dc`. تست‌ها: `afbc003a4170f713c6822b964a298fe865d9305f` و `413b68d09fb0b4565347165ee8dd9aa8dd3a77a7`. preflight workflow: `d28047fda18911a3aa37eb0bb402ad7c66e47459`. upstream route-change evidence: `https://github.com/mmdju/digikala-mcp/blob/main/CHANGELOG.md` (نسخهٔ 0.9.1 مورخ ۱۳ نوامبر ۲۰۲۶).

**ریسک/بازگشت:** اگر Discovery API پاسخ معتبر ندهد، preflight باید اسکن را متوقف کند و state صف/ناشر را دست‌نخورده نگه دارد. بازگشت کد با revert commitهای اسکنر ممکن است، اما endpointهای قدیمی همچنان حذف‌شده‌اند؛ بنابراین rollback به مسیر قبلی راه‌حل عملی نیست. در صورت شکست endpoint جدید، اسکن متوقف و سازگاری با قرارداد جدید دوباره بررسی شود؛ از دور زدن گیت‌ها یا انتشار کاندیدای تأییدنشده خودداری شود.

**وضعیت:** اصلاح کد و تست ثبت شده؛ اجرای زنده و نتیجهٔ نهایی CI در انتظار.


## ۲۰۲۶-۱۱-۱۵ — تصحیح مسیرهای عملیاتی Discovery API

**علت:** preflight زنده روی GitHub Runner نشان داد URL ریشهٔ `/discovery/api/v1/` پاسخ 404 می‌دهد؛ بنابراین صرفاً جایگزین کردن پیشوند API کافی نبود. اسناد نسخهٔ 0.9.1 و 0.9.2 سرویس مرجع، جابه‌جایی جست‌وجو و autocomplete به namespace جدید و پارامتر `categories[0]` را تأیید می‌کنند. پیاده‌سازی مرجع قبلی نیز عملیات را به‌صورت مسیرهای جداگانهٔ search و autocomplete مصرف می‌کند.

**تغییر/اقدام:** مسیرها به `/discovery/api/v1/search` و `/discovery/api/v1/autocomplete` تفکیک شدند؛ headerهای `Origin` و `X-Web-Optimize-Response: 1` افزوده شدند؛ parser شناسه‌های دسته حالا metadata تو‌در‌توی `vertical_product_listing` و پاسخ `data.auto_complete` را نیز می‌خواند. نسخهٔ route policy تغییر کرد تا صف کامل کاتالوگ از صفحهٔ اول دوباره ساخته شود، بدون حذف تاریخچه و state ناشر.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های قرارداد endpoint، parser metadata تو‌در‌تو، پاسخ autocomplete و headerها افزوده/به‌روزرسانی شدند. preflight زنده پس از این اصلاح هنوز باید اجرا شود؛ تا وقتی پاسخ واقعی HTTP 200 و ردیف‌های محصول از GitHub Runner تأیید نشده، اسکن جامع و انتشار محصول موفق اعلام نمی‌شوند.

**شواهد/شناسه:** endpoint/code: `6f5a11df1602cb9160a7af2ba36059970de2cccb`، route migration: `6313deddee3e407fce6f8c0afec46f9d6c0afc20`، nested parser: `87e8bd4de3d709de59bf8b273594cf1e3134fc90`، tests: `27f4c3c5437f53d205ba680cb74b0d101a6adc4b` و `b5a89271a46be8682ff69f4d96f55724e4a9e8f1`.

**ریسک/بازگشت:** اگر مسیرهای جدید نیز 404 یا ساختار payload ناشناخته برگردانند، preflight اسکن را متوقف نگه می‌دارد. از بازگرداندن routeهای قدیمی یا تضعیف گیت‌های تقاضا/تخفیف خودداری شود.

**وضعیت:** مسیرها و parser اصلاح شده‌اند؛ CI و راستی‌آزمایی endpoint زنده در انتظار.


## ۲۰۲۶-۱۱-۱۵ — تکمیل سازگاری با Discovery و وضعیت موجودی variant

**هدف:** اطمینان از اینکه اسکنر پس از مهاجرت API علاوه بر دریافت محصول، وضعیت موجودی و قیمت همان variant قابل‌خرید را درست می‌خواند و کالای نامعلوم را موجود فرض نمی‌کند.

**تغییر/اقدام:** مسیرهای عملیاتی به `/discovery/api/v1/search` و `/discovery/api/v1/autocomplete` تفکیک شدند؛ headerهای `Origin` و `X-Web-Optimize-Response: 1` اضافه شدند؛ parser category metadata تو‌در‌تو و پاسخ `auto_complete` را می‌خواند. parser محصول، قیمت را با اولویت `default_variant` می‌خواند و وضعیت را از `default_variant`/ردیف‌های `variants` نیز استخراج می‌کند. ورود به صف فقط با وضعیت صریح بازارپذیر/موجود انجام می‌شود؛ موجودی نامعلوم پذیرفته نمی‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** در GitHub Actions اجرای Four-Factor Ranking شمارهٔ ۲۴۰ موفق شد؛ compile و ۳۶۶ تست کاتالوگ/رتبه‌بندی با نتیجهٔ `OK (skipped=2)` گذشتند. اجرای اسکن زندهٔ کاتالوگ شمارهٔ ۸۳۱۳ هنوز در صف اجراست؛ بنابراین HTTP 200 و استخراج واقعی محصول از endpoint جدید هنوز تأیید نشده است.

**شواهد/شناسه:** مسیرها/headers: `6f5a11df1602cb9160a7af2ba36059970de2cccb`; route-policy/requeue: `6313deddee3e407fce6f8c0afec46f9d6c0afc20`; parser nested/category: `87e8bd4de3d709de59bf8b273594cf1e3134fc90`; variant status: `ffd3e243ebecacd6d76a312d6d9c68700b2a51b8`; regression: `27f4c3c5437f53d205ba680cb74b0d101a6adc4b`, `b5a89271a46be8682ff69f4d96f55724e4a9e8f1`, `7e95ae66a039b88075da5d19017c49e54d0464cf` و `3052b85a1458910677efbdaf26bba146d8354f35`.

**ریسک/بازگشت:** اگر API جدید خطای HTTP بدهد یا payload موجودی variant نداشته باشد، preflight/اسکن باید fail-closed بماند و هیچ محصولی صرفاً بر پایهٔ قیمت یا عنوان وارد صف انتشار نشود.

**وضعیت:** کد و regressionها موفق؛ اجرای زندهٔ کاتالوگ و Documentation Gate در انتظار تکمیل.


## ۲۰۲۶-۱۱-۱۵ — گیت پیش‌بررسی مبتنی بر محصول واقعی و فیلتر دسته

**هدف:** جلوگیری از آغاز اسکن کامل زمانی که endpoint فقط HTTP 200 یا envelope خالی برمی‌گرداند و عملاً هیچ محصولی قابل استخراج نیست.

**تغییر/اقدام:** `validate_discovery_api()` اکنون جست‌وجوی عمومی را اجرا و حداقل یک محصول صریحاً بازارپذیر را استخراج می‌کند؛ سپس category ID را از metadata یا autocomplete می‌گیرد و با `categories[0]` درخواست دسته‌ای جداگانه می‌زند. این درخواست نیز باید حداقل یک محصول بازارپذیر برگرداند. هر پاسخ خالی/نامعتبر با خطای اختصاصی preflight را متوقف می‌کند و از تغییر cursor/صف در اثر پاسخ ۲۰۰ بی‌محتوا جلوگیری می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** دو regression برای مسیر موفق جست‌وجو + فیلتر دسته و برای پاسخ ۲۰۰ بدون محصول بازارپذیر افزوده شدند. آزمون CI این commit در انتظار اجراست؛ تا تأیید اجرای زنده با خروجی واقعی محصول، اسکن جامع و انتشار موفق اعلام نمی‌شوند.

**شواهد/شناسه:** سخت‌گیری preflight: `9c523e7c5636055942c882dac9a1c6442c832a6a`; regression tests: `af1a42bd5f4ed8d93ffcfea378b2a9ba0bae4203`. upstream API migration reference: `https://github.com/mmdju/digikala-mcp/blob/main/CHANGELOG.md`.

**ریسک/بازگشت:** اگر محصول، دسته یا نتیجهٔ فیلتر دسته از API پاسخ داده نشود، اسکن متوقف می‌شود. این fail-closed عمدی است؛ به‌جای شل کردن شروط یا قبول موجودی نامعلوم، قرارداد زندهٔ API باید دوباره بررسی شود.

**وضعیت:** گیت و تست‌ها ثبت شده‌اند؛ CI و اجرای زندهٔ strict preflight در انتظار.


## ۲۰۲۶-۱۱-۱۵ — اصلاح refresh درخت دسته از فیلترهای Discovery

**هدف:** جلوگیری از استفادهٔ طولانی از نام/شناسه‌های taxonomy منسوخ، که می‌تواند باعث انتساب محصولات نامرتبط به دسته‌های اشتباه شود.

**تغییر/اقدام:** `discover_categories()` اکنون category facets/tree موجود در `data.filters` پاسخ `/discovery/api/v1/search` را با `extract_categories()` استخراج می‌کند و آن را با شناسه‌های query-scoped از `query_attributes.category_ids` و autocomplete ادغام می‌کند. در برخورد شناسه، metadata زندهٔ دسته (نام، parent، depth) جای دادهٔ قدیمی را می‌گیرد؛ cache کامل صرفاً به‌خاطر محدود بودن query results کنار گذاشته نمی‌شود. preflight هم از category facets برای انتخاب category probe استفاده می‌کند و sample category/product-category را در log ثبت می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** regression برای استخراج درخت parent/child از فیلترهای Discovery و ادغام query-scoped IDs اضافه شد. اجرای چهارعاملی و ۳۶۶ تست قبلی موفق بوده‌اند؛ تست جدید و اجرای live با taxonomy تازه در انتظار نتیجه‌اند.

**شواهد/شناسه:** کد: `4ab234bb545912267c0e94096de8809f29a6b698`; regression: `11fd882f23539f377536acf0883d271b6498baf0`.

**ریسک/بازگشت:** اگر Discovery پاسخ filters ندهد، اسکنر به query-scoped IDs و سپس autocomplete برمی‌گردد؛ اگر آن‌ها نیز قابل استفاده نباشند، از cache معتبر با backoff استفاده می‌شود و وضعیت fallback صریح گزارش می‌شود. هیچ دسته یا محصولی بدون شناسه/وضعیت قابل‌تأیید به‌عنوان معتبر فرض نمی‌شود.

**وضعیت:** اصلاح taxonomy و regression ثبت شده؛ CI و اسکن واقعی بعد از refresh در انتظار.

 
## ۲۰۲۶-۱۱-۱۵ — اصلاح برچسب منبع taxonomy زنده
 
**هدف:** ثبت منبع واقعی دادهٔ دسته‌بندی به‌نحوی که هم فیلترهای دسته و هم query metadata پاسخ Search را پوشش دهد.
 
**تغییر/اقدام:** برچسب منبع `digikala_discovery_api_v1_search_filters` به `digikala_discovery_api_v1_search_taxonomy` تغییر کرد؛ چون استخراج از پاسخ Search هر دو شکل category filters/tree و `query_attributes.category_ids` را پوشش می‌دهد.
 
**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.
 
**آزمون و نتیجه:** آزمون منبع taxonomy اصلاح شد؛ CI جدید در انتظار اجراست.
 
**شواهد/شناسه:** کد `10ef46f52108066154f3fe3b42c2adf8c95c8d33`؛ اصلاح تست `10ef46f52108066154f3fe3b42c2adf8c95c8d33` و commitهای بعدی.
 
**ریسک/بازگشت:** فقط label منبع تغییر کرده؛ ترتیب استخراج و معیار پذیرش دسته تغییر نکرده است.
 
**وضعیت:** ثبت شد؛ CI در انتظار.


## ۲۰۲۶-۱۱-۱۵ — جلوگیری از انتساب رتبهٔ تقاضا به دستهٔ نامرتبط

**هدف:** جلوگیری از اینکه یک محصول نامرتبط به‌علت taxonomy منسوخ یا فیلتر ناقص، زیر یک دستهٔ دیگر رتبهٔ پرفروش بگیرد و وارد فهرست انتشار شود.

**تغییر/اقدام:** درخواست دسته‌ای اکنون هر دو پارامتر `q=<category name>` و `categories[0]=<category_id>` را می‌فرستد. قبل از ثبت رتبهٔ بومی پرفروش، گروه معنایی `data_layer.category` محصول با دستهٔ در حال پیمایش مقایسه می‌شود. اگر هر دو گروه معتبر و متفاوت باشند، محصول برای آن دسته رد و رویداد `PARALLEL_CATALOG_CATEGORY_MISMATCH_REJECTED` ثبت می‌شود. دستهٔ نامعلوم به‌اشتباه mismatch فرض نمی‌شود. گروه‌های نرم‌افزار، شبکه/ذخیره‌سازی، صوتی‌تصویری، دکوراتیو، اداری/فروشگاهی و پوشاک دقیق‌تر شده‌اند. نسخهٔ سیاست چهارعاملی به `offerchin_four_factor_harmonic_v4_taxonomy_consistency` ارتقا یافت.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/offerchin_four_factor.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py` و `affilio_radar/test_offerchin_four_factor.py`.

**آزمون و نتیجه:** تست‌های mismatch آشکار نرم‌افزار/موبایل و دکوراتیو/دانگل، حالت taxonomy نامعلوم، درخواست دسته‌ای همراه q و گروه جدید نرم‌افزار اضافه شدند. CI این تغییرها در انتظار اجراست؛ تا پایان regression و اسکن زندهٔ نسخهٔ جدید، انتشار محصولات جدید تأیید نمی‌شود.

**شواهد/شناسه:** گروه‌های taxonomy: `f1676714c02fdea45046606905d9020f469817ca`; گیت دسته: `263321d92e444755834f559ec2e92119914fbccc`; اجرای گیت: `1ae62980e74c36af078f1f7cbb29cea4b56c3b18`; تست‌ها: `a58c872f9679a2063ad5d408fd69c50861613665`, `e0df70a81d4fb53ce2a4de9fa224ccc617d69283`, `14417ffc913945dac4ba08bf885ef1d8946cbc6a`.

**ریسک/بازگشت:** در صورت خطای taxonomy، محصول با دستهٔ نامعلوم صرفاً به‌علت این کنترل حذف نمی‌شود، اما رتبهٔ تقاضای آن فقط با شواهد معتبر و گیت‌های موجود قابل‌استفاده است. اگر تشخیص گروه ناسازگار شد، این گیت می‌تواند از افزودن rank اشتباه جلوگیری کند؛ rollback با revert commitهای اسکنر/سیاست ممکن است، اما endpoint قدیمی بازگردانده نمی‌شود.

**وضعیت:** قاعده و regressionها ثبت شده‌اند؛ CI و پیمایش زنده با نسخهٔ جدید در انتظار.


## ۲۰۲۶-۱۱-۱۵ — حفظ query اصلی در تمام صفحه‌های اسکن موازی دیجی‌کالا

**هدف:** جلوگیری از حذف زمینهٔ جست‌وجوی دسته در صفحه‌های دوم به بعد؛ درخواست ناقص می‌تواند فهرست خالی یا نامرتبط ایجاد کند و رتبهٔ پرفروش را به دستهٔ اشتباه نسبت دهد.

**تغییر/اقدام:** `_category_page_url` اکنون پارامتر `q` را همراه `categories[0]`، شمارهٔ صفحه و sort بومی ۷ ارسال می‌کند. عبارت query از جست‌وجوی اصلی دسته استفاده می‌کند و در `_next_page_task` تا صفحه‌های بعدی حفظ می‌شود. دسته‌های تازه‌کشف‌شده نیز query خود را در صف ثبت می‌کنند. نشانگر سیاست مسیر موازی به `digikala_discovery_api_v1_query_scoped_category_filter_v3` ارتقا یافت تا صف‌های قدیمی با قرارداد ناقص از صفحهٔ اول دوباره بررسی شوند؛ تاریخچه و رسیدهای قبلی دست‌نخورده می‌مانند. assertion قدیمیِ نسخهٔ رتبه‌بندی نیز به ثابت نسخهٔ جاری متصل شد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، `affilio_radar/test_affilio.py`، handbook فنی و همین دفتر تغییرات.

**آزمون و نتیجه:** regression موجود درخواست دسته‌ای را با query و شناسه کنترل می‌کند؛ تست جدید `test_next_page_preserves_original_query_and_pagination` انتقال عبارت query به صفحهٔ بعد را بررسی می‌کند. CI روی شاخهٔ اصلاحی باید پیش از ادغام موفق باشد؛ اجرای موفق batch به‌تنهایی معادل چرخهٔ کامل کاتالوگ یا انتشار نیست.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-query-scoped-pagination-20261115`؛ سیاست مسیر `digikala_discovery_api_v1_query_scoped_category_filter_v3`.

**ریسک/بازگشت:** اگر query معتبر نباشد، صفحه نباید به‌عنوان کامل ثبت شود؛ تلاش مجدد و fail-closed حفظ می‌شوند. rollback با revert همین تغییر و نشانگر سیاست متناظر انجام می‌شود؛ مسیرهای بازنشستهٔ قدیمی نباید بازگردند.

**وضعیت:** تغییر کد، regression و مستندات آمادهٔ اجرای CI در شاخهٔ مستقل؛ چرخهٔ تمیز کاتالوگ و رسید واقعی انتشار همچنان معیارهای جداگانه‌اند.


## ۲۰۲۶-۱۱-۱۵ — همگام‌سازی regression با برچسب منشأ taxonomy زنده

**هدف:** جلوگیری از شکست کاذب CI به‌علت انتظار برچسب منسوخ برای شناسه‌های دسته‌ای که از پاسخ Search API استخراج می‌شوند.

**تغییر/اقدام:** assertion تست `test_discover_categories_reads_category_ids_from_discovery_api` با برچسب واقعی parser یعنی `digikala_discovery_api_v1_search_taxonomy` همگام شد. منطق parser و ترتیب استخراج تغییر نکرد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/test_catalog_sweep.py`، handbook فنی و changelog.

**آزمون و نتیجه:** اجرای مجدد Catalog Sweep Regression و PR CI پس از ثبت تغییر انجام می‌شود؛ نتیجه تا پایان اجرای Actions نامشخص است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-query-scoped-pagination-20261115`، PR #195.

**ریسک/بازگشت:** فقط انتظار تست تغییر کرده است؛ rollback با بازگرداندن assertion قدیمی ممکن است، اما با منشأ فعلی parser سازگار نخواهد بود.

**وضعیت:** اصلاح assertion و مستندسازی ثبت شد؛ اجرای CI دوباره لازم است.


## ۲۰۲۶-۱۱-۱۵ — اصلاح آلودگی taxonomy و گیت رتبه‌بندی دسته‌ای

**هدف:** جلوگیری از اینکه facetهای فروشنده/برند/ارسال یا محصولات nested به‌عنوان category شناخته شوند و محصولات نامرتبط رتبهٔ پرفروش یک دسته را به ارث ببرند.

**تغییر/اقدام:** `extract_categories()` از پیمایش عمومی کل payload به خواندن محدود از فیلدهای صریح `category_tree`، `mega_menu` و filter groupهای دقیق category تبدیل شد. گروه‌های `seller_ids`، `brands` و delivery facets دیگر category محسوب نمی‌شوند. query-matched `query_attributes.category_ids` همچنان از مسیر اختصاصی خود ادغام می‌شود. گیت سازگاری محصول/دسته نیز یک طبقه‌بندی دقیق‌تر برای گوشی، لوازم جانبی کامپیوتر، حافظه، نمایشگر، شبکه، دوربین، قطعات کامپیوتر، اداری، جواهرات، پوشاک و کابل/مبدل اضافه کرد؛ mismatch روشن پیش از ثبت bestseller rank رد می‌شود. route policy به `digikala_discovery_api_v1_trusted_category_taxonomy_v4` ارتقا یافت تا تمام category taskها از صفحهٔ ۱ دوباره seed شوند. snapshot نامزدهای چرخهٔ قبلی به‌دلیل تفاوت شناسهٔ چرخه در چرخهٔ جدید مصرف نمی‌شود؛ تاریخچه و رسیدهای انتشار ناشر حفظ می‌شوند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/parallel_catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، handbook و همین changelog.

**آزمون و نتیجه:** regressionهای جدید، seller/brand/delivery facets و product widgets را به‌عنوان category رد می‌کنند، category tree/facet صریح را حفظ می‌کنند، و mismatchهای ماوس/فلش/مانیتور در دستهٔ گوشی و دوربین در دستهٔ عینک را رد می‌کنند. آزمون مهاجرت نیز seed مجدد صفحهٔ اول را بررسی می‌کند. CI و اسکن زندهٔ این نسخه پس از ثبت تغییرات باید موفق شوند؛ هیچ موفقیت snapshot یا انتشار پیشاپیش ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-trusted-taxonomy-guard-20261115` از `main`؛ سیاست مسیر `digikala_discovery_api_v1_trusted_category_taxonomy_v4`.

**ریسک/بازگشت:** استخراج category محدودتر می‌شود؛ در صورت تغییر schema، صف خالی/ناقص می‌ماند تا parser برای ساختار واقعی اصلاح شود. گیت mismatch فقط زمانی محصول را رد می‌کند که هر دو سمت topic دقیق و متفاوت داشته باشند؛ طبقه‌بندی نامعلوم به‌تنهایی حذف‌کننده نیست. rollback با revert همین commitها ممکن است، اما parser عمومی قبلی نباید به‌عنوان fallback فعال شود.

**وضعیت:** اصلاح کد، تست و مستندات روی شاخهٔ مستقل؛ CI، refresh زندهٔ taxonomy و چرخهٔ کامل بدون شکاف هنوز معیارهای پذیرش‌اند.


## ۲۰۲۶-۱۱-۱۵ — بی‌اعتبارسازی cache taxonomy قدیمی در مهاجرت parser

**هدف:** جلوگیری از مصرف دوبارهٔ فهرست دسته‌های آلودهٔ cache‌شده پس از محدودشدن parser به category roots صریح.

**تغییر/اقدام:** نشانگر `CATEGORY_TAXONOMY_POLICY_VERSION=discovery_explicit_category_roots_v2` اضافه شد. cache فاقد این نشانگر، حتی اگر از نظر زمانی تازه باشد، در مهاجرت معتبر نیست؛ refresh زنده اجباری می‌شود و cache قدیمی نه merge می‌شود و نه fallback. اگر Discovery API خطا بدهد، اسکن با پیام `category_taxonomy_migration_requires_live_refresh` متوقف می‌شود و retry-after برای جلوگیری از درخواست‌های فشرده ثبت می‌شود. پس از refresh موفق، cache نسخه‌دار و fallback موقت بعدی مجاز می‌شود. تست‌های cache قبلی اکنون فقط cache دارای policy marker را «تأییدشده» فرض می‌کنند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، handbook و changelog.

**آزمون و نتیجه:** دو regression جدید تضمین می‌کنند cache legacy در خطای API مصرف نشود و در موفقیت زنده کاملاً جایگزین شود. CI تازه پس از commit لازم است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-trusted-taxonomy-guard-main-sync-20261115`، PR #196؛ policy cache `discovery_explicit_category_roots_v2`.

**ریسک/بازگشت:** اگر Discovery API برای مدت طولانی taxonomy قابل‌خواندن ارائه نکند، اسکن تا بازیابی منبع دسته متوقف می‌شود؛ این توقف عمدی و ایمن‌تر از رتبه‌دهی بر پایهٔ cache آلوده است.



**وضعیت:** پیاده‌سازی مهاجرت cache و تست‌های fail-closed روی شاخهٔ PR ثبت شد؛ اجرای CI آخرین نسخه و اسکن زنده پس از ادغام هنوز لازم است.

## ۲۰۲۶-۱۱-۱۵ — علامت‌گذاری fixtureهای taxonomy معتبر در regressionهای صف قدیمی

**هدف:** تفکیک تست‌هایی که عمداً رفتار عادی cache معتبر را بررسی می‌کنند از تست مهاجرت cache قدیمی و غیرقابل‌اعتماد.

**تغییر/اقدام:** fixture تست پیمایش ترتیبی و تست صف موازی، نشانگر `category_taxonomy_policy_version` را دریافت کردند. بنابراین این تست‌ها رفتار صفحه‌بندی عادی را بدون refresh اجباری مهاجرت می‌سنجند؛ تست‌های مستقل جدید همچنان ثابت می‌کنند cache فاقد نشانگر در خطای API پذیرفته نمی‌شود و در موفقیت زنده جایگزین می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_parallel_catalog_sweep.py`، همین دفتر تغییرات.

**آزمون و نتیجه:** دو regression قبلی که به‌علت استفاده از fixture فاقد policy marker وارد مسیر migration می‌شدند اصلاح شدند؛ اجرای کامل Catalog Sweep Regression، Four-Factor Ranking، Top-100، Video Fan-out و Documentation Gate روی آخرین head لازم است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-trusted-taxonomy-guard-main-sync-20261115`، PR #196.

**ریسک/بازگشت:** منطق تولیدی تغییر نکرده است؛ فقط fixtureهایی که ادعای «cache معتبر قبلی» دارند این وضعیت را صریح اعلام می‌کنند.


**وضعیت:** fixtureها و مستندات روی شاخهٔ PR به‌روزرسانی شدند؛ نتیجهٔ CI نهایی در انتظار ثبت است.


## ۲۰۲۶-۱۱-۱۵ — مهاجرت کشف ناشر به Discovery API و سخت‌سازی HTTP دیجی‌کالا

**هدف:** حذف خطاهای 404 از مسیر کشف داخل ناشر و بازیابی دسترسی قابل‌اتکا به جزئیات محصول، بدون پذیرفتن قیمت/موجودی نامعلوم.

**تغییر/اقدام:** `search_digikala_discovery_product_urls()` اکنون مستقیماً از `/discovery/api/v1/search` با `q`، `page=1` و `sort=7` استفاده می‌کند؛ مسیرهای `/v1/autocomplete/` و `/v2/category/{id}/` دیگر در جریان جاری ناشر فراخوانی نمی‌شوند. پاسخ فقط URL محصولاتی که `status=marketable` دارند را برای بررسی عمیق استخراج می‌کند. نشست HTTP نیز هدرهای Web Client/Origin/Referer و `X-Web-Optimize-Response` را می‌فرستد. helper مشترک `_digikala_get` پاسخ ۳۰۷ دارای `digicdn_cookie` را حداکثر یک بار با همان URL تکرار می‌کند؛ ۳۰۷ بدون cookie و حلقهٔ redirect با خطا متوقف می‌شوند. این helper در جست‌وجوی محصولات، فید آفرهای ویژه، نمودار تاریخچهٔ قیمت، صفحهٔ محصول و کنترل مجدد قیمت به‌کار می‌رود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، handbook فنی و همین changelog.

**آزمون و نتیجه:** regressionهای جدید، Search API فعلی و پارامتر sort=7، حذف endpointهای بازنشسته، انتخاب صرفاً محصول marketable، retry یک‌بارهٔ ۳۰۷ با cookie و fail-closed در نبود cookie را پوشش می‌دهند. CI کامل و smoke test زندهٔ جزئیات محصول پس از ثبت این تغییر لازم‌اند؛ موفقیت جست‌وجو به‌تنهایی به‌معنی تأیید قیمت یا موجودی نیست.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-publisher-discovery-and-digikala-http-20261115`؛ endpoint جاری `/discovery/api/v1/search`؛ HTTP helper `_digikala_get`.

**ریسک/بازگشت:** اگر دیجی‌کالا هدرها یا چالش cookie را تغییر دهد، درخواست جزئیات با خطای مشخص متوقف می‌شود و هیچ قیمت یا موجودی فرضی وارد انتشار نمی‌شود. rollback با revert commitهای همین PR ممکن است؛ endpointهای قدیمی نباید به‌عنوان fallback بازگردند.

**وضعیت:** کد، regression و مستندات روی شاخهٔ مستقل ثبت شدند؛ اجرای CI و اثبات زندهٔ جزئیات محصول هنوز معیار پذیرش نهایی است.


## ۲۰۲۶-۱۱-۱۵ — تکمیل fixtureهای کنترل زندهٔ قیمت برای HTTP helper مشترک

**هدف:** حفظ regressionهای قبلیِ قیمت، اختلاف قیمت و موجودی ناموجود پس از عبور واکشی زنده از helper جدید HTTP.

**تغییر/اقدام:** سه mock پاسخ جزئیات محصول اکنون `status_code=200`، `headers`، `cookies` و `raise_for_status()` را مانند قرارداد استاندارد `requests.Response` ارائه می‌کنند. دلیل شکست قبلی fixture فاقد متد `raise_for_status` بود؛ منطق کنترل قیمت و وضعیت کالا تغییر نکرده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/test_affilio.py`، handbook فنی و changelog.

**آزمون و نتیجه:** اجرای دوبارهٔ OfferChin regression، Four-Factor Ranking و Top-100/DigiPay لازم است؛ سه تستی که شکست داشتند به‌ترتیب موجودی ناموجود، قیمت برابر و اختلاف قیمت را پوشش می‌دهند.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-publisher-discovery-and-http-main-sync2-20261115`، PR #199.

**ریسک/بازگشت:** فقط fixture تست تغییر کرده و هیچ پاسخ واقعی یا وضعیت موجودی دست‌کاری نمی‌شود؛ rollback با بازگرداندن mockهای قبلی ممکن است، اما آن‌ها دیگر با قرارداد helper سازگار نیستند.

**وضعیت:** fixture و مستندات به‌روزرسانی شدند؛ CI کامل نسخهٔ جدید هنوز لازم است.


## ۲۰۲۶-۱۱-۱۵ — ادغام اصلاح مسیر ناشر و درخواست احیای صف محصولات

**هدف:** برطرف‌کردن routeهای منسوخ کشف مکمل ناشر و هم‌راستاکردن واکشی جزئیات با رفتار فعلی وب‌کلاینت دیجی‌کالا، سپس اجرای کنترل‌شدهٔ ناشر برای بازسازی صف منتخب‌ها.

**تغییر/اقدام:** PR #199 با کامیت `279574181e69aa340f9d974d0cbd177c82d6d4ad` ادغام شد. جست‌وجوی مکمل ناشر از autocomplete و category routeهای بازنشسته به `/discovery/api/v1/search` با sort بومی ۷ منتقل شد. helper مشترک `_digikala_get` هدرهای Web Client را به‌کار می‌گیرد و challenge ۳۰۷ را فقط یک بار، تنها با `digicdn_cookie` و روی همان URL تکرار می‌کند؛ در نبود cookie یا تکرار challenge، fail-closed است. جزئیات محصول، صفحه، بازبینی قیمت، نمودار قیمت و فید آفرهای ویژه از همین helper استفاده می‌کنند.

**حفظ ایمنی:** کارت جست‌وجو فقط برای کشف URL است؛ قیمت، موجودی، تخفیف، انقضا، تقاضا، سلامت لینک افیلیت، خانواده/برند/شباهت و idempotency همچنان در مسیر نهایی اعتبارسنجی می‌شوند. هیچ محصول تاریخی یا دادهٔ snapshot تجاری بدون بازبینی زنده منتشر نمی‌شود.

**شواهد CI:** Catalog Sweep Regression، Editorial Contract، Messenger Adapter، Unified Video Fan-out، Four-Factor Ranking، Top-100/DigiPay، Platform Logo و Documentation Gate همگی موفق شدند. این‌ها آزمون کد هستند، نه smoke test زندهٔ API یا رسید انتشار.

**وضعیت اسکن زنده هنگام checkpoint:** ساعت ۱۶:۵۵:۱۴ UTC در ۱۵ نوامبر: ۱۵۰/۴۸۹ دسته تکمیل، ۶٬۰۴۳ صفحه موفق، ۱۱۸٬۵۶۶ ردیف محصول، صفر دستهٔ غیرقابل‌دسترسی در چرخهٔ فعال و ۳۳۹ صفحهٔ باقی‌مانده. چرخه هنوز کامل نیست و snapshot کامل معتبر در دسترس نیست؛ تعداد ردیف‌ها با تعداد نامزدهای قابل انتشار یکسان نیست.

**اقدام بعدی:** اجرای یک‌بارهٔ کنترل‌شدهٔ publisher پس از ادغام برای بازسازی صف با قواعد زنده. فقط receipt/post ID مقصد یا صف تأییدشده، اثبات انتشار است. قاعدهٔ جاری زمان‌بندی همان توزیع مساوی محصولات منتخب تا ETA اسکن کامل بعدی است؛ هیچ فاصلهٔ ثابت عمومی دوباره معرفی نمی‌شود.


## ۲۰۲۶-۱۱-۱۵ — اصلاح endpoint جزئیات زندهٔ محصول دیجی‌کالا

**هدف:** رفع گلوگاه واکشی جزئیات و اعتبارسنجی نهایی محصول پس از آنکه اجرای ناشر در ۱۵ نوامبر برای دو مسیر قدیمی v1/v2 پاسخ 404 گرفت و هیچ قیمت/موجودی زنده‌ای برای ۱۹۵ نامزد استخراج نشد.

**تغییر/اقدام:** هر دو مسیر `fetch_product_record` و `verify_live_page_price` اکنون از `GET https://api.digikala.com/product/v1/products/{id}/` استفاده می‌کنند؛ parser فقط پاسخ دارای شناسهٔ دقیق SKU درخواستی را می‌پذیرد. شمارش واقعی `comments_count` و `reviews_count` بر `rating.count` اولویت دارد و مقدار rating فقط fallback است؛ پنجره/حداقل رشد تقاضا تغییر نکرده است. fallback صفحهٔ HTML نیز حفظ شده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `.github/workflows/offerchin-digikala-catalog-sweep.yml`، راهنمای پروژه و همین changelog.

**آزمون و نتیجه:** regressionهای دریافت محصول، تبدیل ریال به تومان، موجودی marketable، تطبیق شناسه و revalidation اضافه شدند. تمامی workflowهای regression مرتبط در commit `61dac0a9589de1dbb6c2f5fb9da9f2d914a7ded7` موفق شدند. smoke خواندنی endpoint در run `43739297892` با SKU واقعی `dkp-23035367`، شناسهٔ دقیق، قیمت و وضعیت `in_stock` موفق شد؛ هیچ پست یا صفی از این smoke ساخته نشد.

**شواهد/شناسه:** اجرای ناشر اصلی `43737701046`؛ PR `#200`؛ smoke test زنده `43739297892`. مسیر API از پیاده‌سازی عمومی مستقل [amupouya/digikala-mcp](https://github.com/amupouya/digikala-mcp) کشف شده است و قرارداد رسمی تأییدشدهٔ دیجی‌کالا تلقی نمی‌شود.

**ریسک/بازگشت:** endpoint غیررسمی و قابل‌تغییر است. هر پاسخ 4xx، عنوان/قیمت نامعتبر، شناسهٔ نامنطبق یا موجودی نامعلوم همچنان fail-closed می‌ماند و هیچ snapshot تجاری جای دادهٔ زنده را نمی‌گیرد. بازگشت با revert کردن همین تغییر ممکن است؛ دو مسیر شناخته‌شدهٔ 404 نباید دوباره به‌عنوان fallback فعال شوند.

**وضعیت:** smoke زنده و regressionهای کد موفق‌اند؛ ادغام در main و اجرای ناشر روی main هنوز لازم است. فقط رسید واقعی Telegram/Bale و ثبت شناسهٔ پیام می‌تواند احیای انتشار عمومی را تأیید کند.


## ۲۰۲۶-۱۱-۱۵ — درخواست اجرای کنترل‌شدهٔ ناشر پس از مهاجرت جزئیات محصول

**هدف:** واداشتن ناشر production به استفاده از کد تازهٔ main پس از برطرف‌شدن مسیر 404 جزئیات محصول، بدون ایجاد اجرای هم‌زمان یا ارسال آزمایشیِ خارج از صف.

**تغییر/اقدام:** کامنت marker `[publisher-run-now]` به workflow اصلی اضافه شد و یک commit با همین marker ثبت می‌شود تا workflow رسمی ناشر یک‌بار dispatch شود. concurrency group موجود حفظ می‌شود؛ در صورت فعال بودن اجرای قبلی، اجرای جدید پشت آن در صف می‌ماند. مرحلهٔ انتخاب با `AFFILIO_AUTOPUBLISH=false` و ارسال کانالی طبق صف و زمان‌بندی فعلی انجام می‌شود.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، همین changelog و GitHub Actions ناشر.

**آزمون و نتیجه:** smoke زندهٔ جزئیات برای `dkp-23035367` در run `43739297892` موفق بود؛ regressionهای رتبه‌بندی، کاتالوگ، پیام‌رسان، ویدئو، DigiPay و مستندات PR #200 موفق شدند. اجرای ناشر قدیمی `43738906081` در زمان ثبت marker هنوز `in_progress` است؛ اجرای جدید باید پس از آن شروع شود. موفقیت ارسال عمومی هنوز ادعا نمی‌شود.

**شواهد/شناسه:** PR #200؛ merge commit `4fa64df09e03019ec36f4e01e1a0275855e1c9ec`؛ catalog sweep runs `43739584013` و `43739599995`؛ workflow قدیمی `43738906081`.

**ریسک/بازگشت:** اگر نامزدها از هویت، قیمت، موجودی، تقاضا، تخفیف، افیلیو یا ضدتکرار عبور نکنند، صف خالی می‌ماند و پستی ارسال نمی‌شود. اجرای جدید با concurrency ناشر serialized است؛ marker را می‌توان با revert کامیت عملیاتی حذف کرد. cadence شناور و تقدم محصول حفظ می‌شود.

**وضعیت:** درخواست اجرای یک‌بارهٔ رسمی ثبت می‌شود؛ نتیجهٔ اجرا، صف و رسید Telegram/Bale باید جداگانه راستی‌آزمایی شود.


## ۲۰۲۶-۱۱-۱۵ — آزادسازی سریع قفل ناشر برای صف ویدئوی خالی

**هدف:** جلوگیری از معطل‌ماندن انتشار محصولات کانالی پشت یک اجرای ویدئویی که هیچ محتوای واجد ارسال ندارد.

**تغییر/اقدام:** workflow واحد ویدئو پس از checkout، `video_upload_dispatch_state.json` را بررسی می‌کند. اگر `published` خالی باشد، نصب Python/Playwright، بررسی ورود Filo، رندر و ارسال ویدئو و persistence همگی skip می‌شوند؛ بنابراین concurrency مشترک سریع آزاد می‌شود. در صورت وجود هر رکورد ویدئویی، رفتار قبلی حفظ می‌شود.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-video-publisher.yml`، راهنمای پروژه و همین changelog.

**آزمون و نتیجه:** اجرای فعلی ویدئو `43739888281` با projection خالی `published={}` در شروع کار، بدون نیاز به آپلود واقعی باید فقط gate را طی کند. CI workflow و گیت مستندات پس از PR اجرا می‌شوند.

**شواهد/شناسه:** اجرای ویدئو `43739888281`؛ در projection ذخیره‌شده `generated_at=2026-11-15T17:13:21Z` و تعداد رکوردها صفر بود؛ صف ناشر محصول `43739938216` در آن زمان pending بود.

**ریسک/بازگشت:** اگر projection ناقص/قدیمی و خالی باشد، اجرای ویدئو موقتاً skip می‌شود؛ dispatcher دقیقه‌ای همچنان می‌تواند آن را با projection تازه dispatch کند. هیچ وضعیت یا رسیدی حذف نمی‌شود. rollback با revert تغییر workflow ممکن است. قفل مشترک حفظ می‌شود.

**وضعیت:** اصلاح روی شاخهٔ مستقل و آمادهٔ CI/بازبینی؛ این تغییر cadence محصول یا گیت انتخاب را دست نمی‌زند.


**Regression guard:** آزمون `test_empty_video_projection_releases_shared_publisher_lock_before_setup` به `affilio_radar/test_shared_selection_media_routing.py` اضافه شد تا ترتیب gate، بررسی projection، خروجی empty و شرط اجرای مراحل سنگین را کنترل کند.

## ۲۰۲۶-۱۱-۱۵ — تازه‌سازی شواهد پرفروش در انتقال نامزد به صف ناشر

**هدف:** جلوگیری از ماندن نامزدهای بدون تغییر قیمت در صف قدیمی و از دست رفتن رتبهٔ پرفروش تازه‌ای که چرخهٔ کامل کاتالوگ ثبت می‌کند.

**تغییر/اقدام:** اثرانگشت `catalog_handoff_fingerprint()` اکنون حالت مرتب‌سازی پرفروش، رتبهٔ تازه، دستهٔ رتبه‌بندی، نقشهٔ رتبه‌های دسته‌ای و زمان مشاهده را نیز لحاظ می‌کند. در نتیجه تغییر مدرک تقاضا حتی وقتی قیمت/موجودی ثابت‌اند، نامزد را برای بررسی زندهٔ مجدد به handoff بازمی‌گرداند. تست رگرسیون جداگانه برای این سناریو افزوده شد. هیچ گیت انتشار یا کنترل زنده‌ای تغییر نکرد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md` و همین changelog.

**آزمون و نتیجه:** Catalog Sweep Regression، Catalog Sweep PR validation، Four-Factor Ranking، Top-100/DigiPay و Unified Video Fan-out در PR #202 موفق شدند. اجرای قدیمی ناشر #3705 در run `43741002934` پس از رسیدن snapshot کامل، ۲۵۰ نامزد را handoff و ۴۸ محصول را واجد انتخاب/صف‌بندی کرد؛ همان اجرا در انتها `PUBLISHER_NOTHING_DUE queue_size=48` ثبت کرد، بنابراین این نتیجه هنوز رسید انتشار عمومی نیست. Documentation Gate ابتدا به‌علت نبود این دو به‌روزرسانی سندی fail شد و پس از افزودن این ورودی باید دوباره بررسی شود.

**شواهد/شناسه:** PR #202؛ head commit `e3440d865f5fd36bcefaeb719453454fbd1a8bcc`؛ Catalog Sweep Regression run `43741919631`؛ Catalog Sweep validation `43741919652`؛ Four-Factor run `43741919723`؛ Top-100/DigiPay run `43741919725`؛ Video fan-out run `43741919685`؛ ناشر run `43741002934`.

**ریسک/بازگشت:** تغییر رتبه یا timestamp می‌تواند تعداد بیشتری نامزد را برای بازبینی زنده به صف برگرداند و بار درخواست API را افزایش دهد؛ handoff همچنان محدود به batch تنظیم‌شده است و مراحل زنده/ضدتکرار پابرجا هستند. rollback با revert تغییر `catalog_handoff_fingerprint()` و تست همراه ممکن است.

**وضعیت:** اصلاح کد و تست ثبت شده؛ به‌روزرسانی handbook و changelog انجام شد؛ ادغام PR و رسید واقعی ارسال مقصد هنوز تأیید نشده‌اند.


## ۲۰۲۶-۱۱-۱۵ — تازه‌سازی handoff شواهد تقاضای پرفروش

**هدف:** جلوگیری از ماندن نامزدهای کاتالوگ در صف بررسی با مدرک تقاضای منقضی، درحالی‌که اسکن کامل جدید رتبهٔ پرفروش آن‌ها را به‌روز کرده است.

**تغییر/اقدام:** اثرانگشت handoff علاوه بر قیمت، تخفیف و موجودی، حالت مرتب‌سازی، رتبهٔ پرفروش، شناسه و نام دسته، نقشهٔ رتبه‌های دسته‌ای و زمان مشاهده را نیز لحاظ می‌کند. در نتیجه تغییر مدرک تقاضا حتی با ثابت‌ماندن قیمت و موجودی، نامزد را دوباره برای واکشی و اعتبارسنجی زنده وارد صف می‌کند؛ صف و سقف handoff حفظ می‌شوند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/catalog_sweep.py`، `affilio_radar/test_catalog_sweep.py`، `.github/workflows/offerchin-publisher.yml`.

**آزمون و نتیجه:** آزمون رگرسیون `test_handoff_rechecks_fresh_bestseller_evidence_without_price_change` اضافه شد. اجرای Catalog Sweep Regression شمارهٔ ۵۳۳ با run ID `43741919631` موفق شد؛ سایر تست‌های PR نیز جداگانه موفق‌اند. Documentation Gate ابتدا به‌دلیل ثبت‌نشدن تغییر در handbook و changelog رد شد و پس از این اصلاح باید دوباره اجرا شود.

**شواهد/شناسه:** PR #202، شاخهٔ `fix/refresh-catalog-demand-evidence-20261115`، head اولیه `e3440d865f5fd36bcefaeb719453454fbd1a8bcc`.

**ریسک/بازگشت:** تازه‌سازی شواهد می‌تواند نامزدهای بیشتری را به بررسی زنده بازگرداند؛ سقف handoff و همهٔ گیت‌های قیمت، موجودی، هویت، تقاضا، افیلیت و ضدتکرار برقرارند. بازگشت با revert همین تغییر کد ممکن است و نباید state/صف منتشرشده reset شود.

**وضعیت:** اصلاح کد و تست انجام‌شده؛ ادغام پس از موفقیت مجدد Documentation Gate.



## ۲۰۲۶-۱۱-۱۵ — مسیر سریع برای اسلات‌های موعدرسیدهٔ انتشار

**هدف:** جلوگیری از اشغال اجرای ناشر با اسکن و بررسی کاتالوگ در زمانی که صف محصول یا نقطهٔ میانی تحریریه آمادهٔ انتشار است.

**تغییر/اقدام:** ابزار fail-open `publication_due_gate.py` از projection کوچک dispatch، موعد اسلات محصول و تحریریه را تشخیص می‌دهد. اگر اسلاتی موعدرسیده باشد، مرحلهٔ discovery در workflow ناشر skip می‌شود و اجرای ناشر مستقیم سراغ صف پایدار می‌رود. هر اجرا حداکثر سه محصول موعدرسیده را به‌ترتیب صف تحویل می‌دهد. سقف واکشی زندهٔ جزئیات و صف discovery در اجرای عادی بدون اسلات موعدرسیده به ۱۰۰ کاهش یافته و نامزدهای بررسی‌نشده در صف پایدار باقی می‌مانند. projection dispatch در صورت تغییر state نیز برای GitHub Worker ذخیره می‌شود.

**فایل‌ها/سامانه‌ها:** `affilio_radar/publication_due_gate.py`، `affilio_radar/test_publication_due_gate.py`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/offerchin-top100-digipay-tests.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** شش regression برای اسلات محصول موعدرسیده، midpoint تحریریه، زمان آینده، اولویت اسلات، fail-open بودن projection نامعتبر و timestamp بدون timezone اضافه شده‌اند. اجراهای Catalog/Ranking/DigiPay/Video/Documentation در PR پس از push باید بررسی شوند؛ نتیجهٔ نهایی هنوز در انتظار CI است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-due-slot-fast-publish-20261115`؛ workflow ناشر و تست regression به‌روزرسانی شده‌اند. هیچ پیام عمومی بدون شناسهٔ مقصد، منتشرشده تلقی نمی‌شود.

**ریسک/بازگشت:** اگر projection خوانده نشود، گیت fail-open است و discovery اجرا می‌شود؛ در نتیجه محتوا به‌خاطر sidecar خراب مسدود نمی‌شود. ارسال هر محصول همچنان قیمت، موجودی، هویت، تخفیف، تقاضا، لینک افیلیت، انقضا و ضدتکرار را زنده بررسی می‌کند. سقف سه محصول فقط برای آیتم‌های موعدرسیده است و ترتیب FIFO حفظ می‌شود. بازگشت با revert گیت و تغییر batch ممکن است؛ صف یا state زنده نباید reset شود.

**وضعیت:** تغییر کد، workflow و مستندات انجام‌شده؛ در انتظار CI و ادغام.


## ۲۰۲۶-۱۱-۱۵ — محدودسازی تاریخچهٔ checkout در workflowهای دارای قفل انتشار

**هدف:** کاهش زمان انتظار ناشر محصول و ویدئو برای checkout مخزن؛ اجرای ویدئویی با صف خالی نباید به‌دلیل دریافت کل تاریخچهٔ Git قفل مشترک را طولانی نگه دارد.

**تغییر/اقدام:** `fetch-depth` در workflowهای `offerchin-publisher.yml` و `offerchin-video-publisher.yml` از صفر (تاریخچهٔ کامل) به ۱۰۰ commit تغییر کرد. این عمق برای پوشش تغییرهای هم‌زمان state در اجرای معمول workflow در نظر گرفته شده و همچنان امکان rebase/push را در شرایط معمول حفظ می‌کند. اگر هم‌زمانی از این پنجره فراتر رود، retry/خطای push باید آشکار بماند و هیچ state بازنویسی اجباری نمی‌شود.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `.github/workflows/offerchin-video-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** تست‌های wiring ناشر و FIFO ویدئو در GitHub Actions پس از PR اجرا می‌شوند. اجرای ناشر قبل از این تغییر به‌طور واقعی چند دقیقه در مرحلهٔ checkout مانده بود؛ زمان checkout پس از ادغام باید با runهای بعدی مقایسه شود.

**شواهد/شناسه:** شاخهٔ `perf/offerchin-shallow-action-checkout-20261115`؛ workflowهای فعلی هر دو `fetch-depth: 0` داشتند.

**ریسک/بازگشت:** در صورت ایجاد بیش از ۱۰۰ commit هم‌زمان بین checkout و persist، rebase ممکن است به تاریخچهٔ عمیق‌تر نیاز داشته باشد؛ retry باید شکست را گزارش کند و state را force-push نمی‌کند. rollback با بازگرداندن `fetch-depth: 0` ممکن است؛ این تغییر cadence یا محتوای انتشار را تغییر نمی‌دهد.

**وضعیت:** تغییر workflow و مستندات انجام‌شده؛ در انتظار CI و ادغام.


## ۲۰۲۶-۱۱-۱۵ — حذف فاصلهٔ قدیمی ۵۵ دقیقه‌ای از گزارش سایه‌ای OfferChin

**هدف:** پاک‌کردن اثر باقی‌ماندهٔ سیاست قدیمی فاصلهٔ ثابت از پیکربندی تشخیصی و جلوگیری از اشتباه‌گرفتن آن با cadence زندهٔ محصولات.

**تغییر/اقدام:** متغیر بلااستفادهٔ `OFFERCHIN_EDITORIAL_GAP_MINUTES=55` از workflow صرفاً تشخیصی `offerchin-editorial-shadow.yml` حذف شد. آزمون قراردادی اکنون همزمان فایل‌های ناشر کانال، ناشر ویدئو و shadow را برای نبودن این متغیر بررسی می‌کند و فرمول `remaining_seconds / pending_product_count` و سیاست `equal_spacing_pending_selected_products_across_time_until_next_clean_catalog_scan` را الزام می‌کند. کد انتشار زنده برای حذف یک مقدار بلااستفاده تغییر نکرد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-editorial-shadow.yml`، `.github/workflows/offerchin-editorial-contract.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** Editorial Contract run `43748642729` با نتیجهٔ success تمام شد؛ شامل کامپایل ماژول‌ها، اعتبارسنجی بانک تحریریه، کنترل نبودن فاصلهٔ ثابت، گزارش سایه‌ای read-only و آزمون‌های `test_editorial_content.py`، `test_editorial_publisher.py` و `test_content_delivery.py`. Documentation Gate در زمان ثبت اولیه در حال اجرا بود و باید نتیجهٔ نهایی آن پیش از ادغام ثبت شود.

**شواهد/شناسه:** PR #212، شاخهٔ `fix/offerchin-remove-legacy-editorial-gap`، head commit `9e3fbba1428fe54e770c98e58d00a0f1dd7c159d`؛ اجرای ناشر #43747781304 در همان روز سه محصول را با وضعیت `CONTENT_CHANNEL_DELIVERY_COMPLETE` به Telegram و Bale تحویل داد.

**ریسک/بازگشت:** حذف این متغیر رفتار انتشار زنده را تغییر نمی‌دهد، چون فقط در shadow workflow بود و در کد زمان‌بندی مصرف نمی‌شد. بازگشت صرفاً با revert تغییر workflow و تست ممکن است؛ صف، state، تاریخچه و رسیدهای انتشار نباید reset شوند.

**وضعیت:** اصلاح workflow و regression guard انجام شد؛ آزمون قراردادی موفق است؛ ادغام نهایی منوط به موفقیت Documentation Gate است.


## ۲۰۲۶-۱۱-۱۵ — خواناتر کردن بندهای تحریریه و لینک منبع

**هدف:** رفع حالت متن یک‌تکه در بیشتر مطالب evergreen و روشن‌تر کردن مقصد لینک منبع برای مخاطب کانال.

**تغییر/اقدام:** قالب‌بند تحریریه اکنون شکست‌خط‌های دستی را حفظ و جمله‌های کامل را با فاصلهٔ خالی از هم جدا می‌کند. لینک HTML منبع با عنوان قابل فهم «مشاهدهٔ منبع» نمایش داده می‌شود؛ نام ناشر و عنوان مقاله همچنان کنار آن درج می‌شوند. دعوت انتهایی به کانال جدا و قابل کلیک باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_publisher.py`، `affilio_radar/test_editorial_publisher.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `docs/CHANGELOG_FA.md`.

**آزمون و نتیجه:** آزمون جدید جداسازی جمله‌ها و حفظ لینک CTA را کنترل می‌کند؛ آزمون‌های قالب‌بندی قبلی نیز برچسب لینک منبع و لینک عضویت را بررسی می‌کنند. نتیجهٔ نهایی پس از اجرای Editorial Contract و Documentation Gate در PR ثبت می‌شود.

**شواهد/شناسه:** PR مربوط به اصلاح قالب‌بندی تحریریه روی شاخهٔ `feat/offerchin-editorial-readability`؛ اجرای ناشر `43747781304` پیش‌تر تحویل سه محصول را با موفقیت ثبت کرده بود و این commit رفتار انتشار محصول را تغییر نمی‌دهد.

**ریسک/بازگشت:** اگر متن خاصی به‌علت نشانه‌گذاری غیرمعمول بیش از حد خرد شود، می‌توان منطق `_readable_editorial_body` را با revert همین commit به حالت قبل برگرداند. گیت‌های صحت منبع، ترتیب FIFO، CTA، سقف طول پیام و سیاست cadence دست‌نخورده‌اند.

**وضعیت:** تغییر قالب و regression guard ثبت شد؛ در انتظار CI و ادغام.

## ۲۰۲۶-۱۱-۱۵ — اصلاح توزیع slotهای محصول و تقدم midpoint تحریریه

**هدف:** جلوگیری از انتشار چند محصولِ معوق به‌صورت burst، رعایت ترتیب زمانی محصول و تحریریه، و بازگرداندن فاصله‌گذاری مساوی محصولات باقی‌مانده تا اسکن پاک بعدی.

**تغییر/اقدام:** سقف پردازش ناشر در هر dispatch به یک محتوای عمومی محدود شد و تنظیم batch سه‌محصولی حذف شد. پس از تحویل واقعی یک محصول به کانال اصلی، فاصلهٔ باقی‌مانده تا ETA اسکن پاک بعدی بر تعداد محصولات منتشرنشده تقسیم و صف با همین فاصلهٔ مساوی بازچینی می‌شود. ناشر midpoint تحریریه را فقط وقتی پیش از slot محصول مرتبط است جلوتر از آن اجرا می‌کند؛ محصولی که قبلاً به کانال اصلی رسیده، دیگر تحریریهٔ دیرهنگام مرتبط دریافت نمی‌کند. پس از تغییر state تحریریه/محصول، projection زمان‌بندی Worker نیز تازه می‌شود. هیچ فاصلهٔ ثابت ۲۷/۵۵ دقیقه‌ای یا safety gap به cadence اضافه نشده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/content_delivery.py`، `affilio_radar/publisher.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/test_content_delivery.py`، `affilio_radar/test_editorial_publisher.py`، `.github/workflows/offerchin-publisher.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، همین changelog و GitHub Actions.

**آزمون و نتیجه:** تست‌های Editorial Contract، Messenger Adapter، Unified Video Fan-out، Fallback Regression و Top-100/DigiPay روی head اولیهٔ PR #214 موفق شدند. Documentation Gate در اجرای اول به‌درستی به‌دلیل نبود handbook و changelog تازه رد شد؛ هر دو سند اکنون به‌روزرسانی شده‌اند و Gate باید دوباره اجرا شود. آزمون‌های موفق CI به‌تنهایی اثبات انتشار عمومی پس از ادغام نیستند.

**شواهد/شناسه:** اجرای واقعی ناشر `43750208575` پیش از اصلاح، تحویل محصولات `dkp-21196655` و `dkp-20502655` را با شناسه‌های واقعی Telegram/Bale/Rubika ثبت کرد؛ فاصلهٔ دو تحویل ۲۷ ثانیه بود و صف پس از آن ۱۸ آیتم باقی داشت. PR #214؛ شاخهٔ `fix/offerchin-product-editorial-order`؛ head اولیهٔ PR `345da5b9de9193e4bdb1b319c7d784c66e9634a7`.

**ریسک/بازگشت:** dispatch تک‌محتوایی مانع burst می‌شود، اما چون Cloudflare هر دقیقه بررسی می‌کند، slotهای با فاصلهٔ کمتر از یک دقیقه ممکن است تا tick بعدی تأخیر بگیرند؛ این تأخیر با burst جبران نمی‌شود و زمان‌بندی بعد از رسید واقعی محصول دوباره reflow می‌شود. اگر ETA اسکن پاک بعدی یا رسید واقعی محصول در دسترس نباشد، صف نباید با فاصلهٔ ساختگی زمان‌بندی شود. بازگشت با revert کردن تغییرات این PR ممکن است؛ state، صف و رسیدهای انتشار نباید reset یا حذف شوند.

**وضعیت:** اصلاح کد و regressionها ثبت شده؛ پنج workflow اصلی CI موفق‌اند؛ مستندات تکمیل شد و نتیجهٔ اجرای مجدد Documentation Gate و ادغام PR #214 هنوز باید تأیید شود.

## ۲۰۲۶-۱۱-۱۵ — رفع تقدم تکراری تحریریه بر صف محصول و افزودن منبع دیجی‌کالا مگ

**هدف:** جلوگیری از تکرار یک مطلب تحریریه در slot میانی و عقب‌افتادن محصولات به‌دلیل retry مقصدهای عکس/ویدئوی همان مطلب؛ تکمیل استفادهٔ واقعی از دیجی‌کالا مگ.

**تغییر/اقدام:** photo_slot_attempted_at پیش از رندر/ارسال اولین تحریریه در state ثبت می‌شود. انتخاب midpoint فقط برای تحریریه‌ای مجاز است که هنوز تلاش کانالی نداشته باشد؛ retryهای بعدی آن دیگر محصول را preempt نمی‌کنند. وقتی موعد محصول مرتبط فرا برسد، تحریریهٔ فعالِ جا‌مانده لغو می‌شود تا بعد از محصول منتشر نشود. یک مطلب بررسی‌شده دربارهٔ تطبیق گوشی با نیاز و بودجه، با لینک مستقیم به راهنمای دیجی‌کالا مگ، به بانک ۳۷‌تایی تحریریه اضافه شد. زمان‌بندی مساوی محصولات و سقف یک پست در هر dispatch تغییر نکرد.

**فایل‌ها/سامانه‌ها:** affilio_radar/publisher.py، affilio_radar/editorial_publisher.py، affilio_radar/test_content_delivery.py، affilio_radar/test_editorial_publisher.py، affilio_radar/editorial_bank.json، .github/workflows/offerchin-publisher.yml، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md.

**آزمون و نتیجه:** دو regression جدید برای عدم preempt دوبارهٔ محصول و لغو midpoint منقضی اضافه شد. اجرای CI پس از ایجاد PR در انتظار است؛ تا پیش از نتیجهٔ واقعی، موفقیت تست ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ fix/editorial-midpoint-retry-does-not-block-products. منبع تازه: https://www.digikala.com/mag/best-smartphone-buying-guide/ (راهنمای انتخاب گوشی موبایل بازار ایران، آبان ۱۴۰۵).

**ریسک/بازگشت:** یک تحریریهٔ ناموفق ممکن است به‌جای retry فوری، slot خود را از دست بدهد تا محصول مرتبط در اولویت بماند؛ retry مقصدها در مسیر مستقل ادامه دارد. بازگشت با revert تغییرهای ناشر/ناشر تحریریه و تست‌ها ممکن است؛ state صف و تاریخچه نباید reset شود.

**وضعیت:** تغییرات در شاخهٔ مستقل ثبت شده؛ CI/ادغام/انتشار کنترل‌شده در انتظار.

## ۲۰۲۶-۱۱-۱۵ — تقدم انتشار کانال‌ها بر صف ویدئو

**هدف:** جلوگیری از اشغال قفل مشترک وضعیت انتشار توسط بارگذاری ویدئو و حفظ تقدم انتشار پست‌های محصول و تحریریه در slotهای تعیین‌شده.

**تغییر/اقدام:** dispatch فوری ویدئو از انتهای workflow ناشر محصولات حذف شد. Worker فقط در پنجرهٔ idle واقعی اجازهٔ آغاز workflow ویدئو دارد: هیچ slot کانالِ محصول/تحریریه در sidecar برنامه‌ریزی نشده باشد، workflow ناشر و اسکن کاتالوگ فعال یا در صف نباشند، وضعیت اسکن قابل‌خواندن باشد و `pending_page_count` صفر باشد. در وضعیت نامشخص، dispatch ویدئو fail-closed می‌شود و صف ویدئو برای بررسی در tick بعدی باقی می‌ماند. قفل concurrency مشترک حفظ شد، چون هر دو workflow روی `state.json` مشترک می‌نویسند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `.github/workflows/offerchin-publisher.yml`، `.github/workflows/offerchin-video-fanout-validation.yml`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست wiring و regressionهای fan-out ویدئو موفق؛ اعتبارسنجی Worker و Wrangler dry-run موفق؛ تست‌های تحریریه، fallback، Top-100/DigiPay و آداپتر پیام‌رسان موفق. Documentation Gate ابتدا به‌دلیل ناقص‌بودن قالب همین ورودی شکست خورد و پس از تکمیل این فیلدها باید مجدداً اجرا شود. هیچ پست عمومی آزمایشی توسط این تغییر ارسال نشده است.

**شواهد/شناسه:** PR #215، شاخهٔ `fix/editorial-midpoint-retry-does-not-block-products`؛ Video Fan-out Validation run `43754052411`؛ Worker validation run `43754052427`؛ Editorial Contract run `43754052410`؛ Fallback run `43754052437`؛ Top-100/DigiPay run `43754052443`؛ Messenger Adapter run `43754052591`.

**ریسک/بازگشت:** ممکن است بارگذاری ویدئو تا خالی‌شدن slotها و تکمیل اسکن سالم عقب بیفتد؛ این تأخیر عمدی و پایین‌اولویت است و نباید پست کانالی را عقب بیندازد. رکوردها و صف ویدئو reset یا حذف نمی‌شوند. بازگشت با revert تغییر dispatch Worker و حذف شرط idle ممکن است؛ قفل مشترک state نباید حذف شود مگر آنکه ذخیره‌سازی تراکنشی/تفکیک‌شده پیاده شود.

**وضعیت:** اصلاح و آزمون‌ها روی PR ثبت شده‌اند؛ تا تأیید نهایی Documentation Gate، ادغام و استقرار production انجام نشده است.


## ۲۰۲۶-۱۱-۱۶ — استخراج برند، اصلاح طبقه‌بندی و تنوع مستقل انتخاب

**هدف:** کاهش دسته‌بندی نادرست و سهم «سایر»، افزایش پوشش برندهای قابل‌شناسایی، و جلوگیری از تکرار متوالی کاربرد/دسته بدون برهم‌زدن اولویت تقاضا و ارزش یا گرسنه‌ماندن صف کم‌تعداد.

**تغییر/اقدام:** تابع مشترک و محافظه‌کارانهٔ `normalize_brand_value()` اضافه شد؛ برند از پاسخ جزئیات و کاتالوگ به رکورد انتخاب منتقل می‌شود. الگوهای طبقه‌بندی برای محصولات خوراکی، مراقبت شخصی، حیوانات، ابزار و لوازم خانگی بزرگ دقیق‌تر شدند و تشخیص «رم» از تطبیق زیررشتهٔ «گرم» جدا شد. گارد خانواده/برند/شباهت ۲۴ساعته سخت باقی ماند؛ تکرار دسته با پنجرهٔ ۶ ساعت و کاربرد با پنجرهٔ ۴ ساعت به‌صورت تعویق نرم و مستقل اضافه شد. fallback ظرفیت خالی را پر می‌کند و ترتیب منبع رتبه‌بندی را پس از انتخاب حفظ می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/product_quality.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/catalog_sweep.py`، `affilio_radar/offerchin_four_factor.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_catalog_sweep.py`، `affilio_radar/test_selection_evidence.py` و همین دو سند.

**آزمون و نتیجه:** regression برای حفظ برند در جزئیات/کاتالوگ، جداسازی «رم/گرم»، طبقه‌بندی روغن خوراکی/بالم لب/غذای حیوانات/ماشین لباسشویی و رفتار تعویق نرم اضافه شد. اجرای نخست CI پیش از اصلاح فیلد merge برند و حفظ ترتیب نهایی چند شکست را آشکار کرد؛ اصلاحات بعدی در شاخه ثبت شده‌اند و اجرای کامل جدید در انتظار نتیجه است. اجرای کاتالوگ و regression مستقل آن موفق بوده‌اند؛ ادغام تا سبزشدن آزمون‌های رادار، چهارعاملی، Top-100/DigiPay و Documentation Gate مجاز نیست.

**شواهد/شناسه:** PR #220 — https://github.com/Mehran0960/ai_news_bot/pull/220 ؛ شاخهٔ `fix/offerchin-diversity-taxonomy-2026-11-16`؛ اجرای اولیهٔ رادار `43830360662` و اجرای کاتالوگ `43830370615`.

**ریسک/بازگشت:** تشخیص برند از عنوان فقط برای نام‌های با اطمینان بالا انجام می‌شود؛ برند ناشناخته خالی می‌ماند و نباید حدس زده شود. تعویق دسته/کاربرد فقط اولویت batch محدود را تنظیم می‌کند و جایگزین گیت تقاضا، تخفیف، قیمت، موجودی یا لینک نیست. در صورت regression می‌توان فقط commitهای شاخه/PR را revert کرد؛ state، صف‌های کاتالوگ/انتشار و رسیدهای پلتفرم نباید reset یا حذف شوند.

**وضعیت:** اصلاحات و regressionها در PR #220 ثبت شده‌اند؛ Documentation Gate پس از ثبت این ورودی و handbook باید دوباره اجرا شود؛ ادغام و هرگونه انتشار عملیاتی تا موفقیت کامل CI انجام نمی‌شود.

## 2026-11-16 — رفع توقف انتشار، سقف ۵۷ دقیقه و رتبه‌بندی سه‌عاملی

**هدف:** جلوگیری از معطل‌شدن محصولات انتخاب‌شده در صف به‌علت ETA ناموجود یا اسکن ناقص؛ توزیع یکنواخت انتشار محصول با سقف ۵۷ دقیقه؛ درج تحریریه فقط در شکاف قابل‌تحویل؛ حذف قیمت/استطاعت از امتیاز و فیلتر محصول.

**تغییر/اقدام:** زمان‌بندی محصولات به‌جای حداقل‌فاصلهٔ ۵۷ دقیقه از سقف فاصلهٔ ۵۷ دقیقه استفاده می‌کند؛ وقتی ETA معتبر اسکن وجود ندارد، صف منتخب با پنجرهٔ موقت حداکثر ۵۷ دقیقه برای هر slot ادامه می‌یابد و نخستین محصول پس از عبور ۵۷ دقیقه از انتشار قبلی فوراً due می‌شود. Worker قبل از گیت اسکن، صف سررسیدشده را dispatch می‌کند و با پایین‌آمدن صف به دو محصول، refill انجام می‌دهد. Workflow ناشر نیز پیش از setup و discovery، slot سررسیدشده را شناسایی می‌کند و مسیر ارسال را از discovery سنگین جدا می‌سازد. ناشر برای محصولی که قبلاً منتخب و صف‌بندی شده دیگر منتظر snapshot اسکن بعدی نمی‌ماند، اما تقاضای زنده، قیمت، موجودی، تخفیف، هویت محصول و لینک افیلیت را در لحظه دوباره اعتبارسنجی می‌کند. تحریریه با midpoint و صدک ۹۰ زمان واقعی ارسال به شکاف وارد می‌شود؛ در نبود runway کافی رد/تعویق می‌شود و محصول را عقب نمی‌اندازد. رتبه‌بندی و مسیر اضطراری به سه معیار تقاضای زنده، عمومیت و تخفیف واقعی تغییر کرد؛ قیمت فقط برای راستی‌آزمایی قیمت و حساب تخفیف باقی می‌ماند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/content_delivery.py`، `affilio_radar/affilio_radar.py`، `affilio_radar/offerchin_four_factor.py`، `affilio_radar/publisher.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/publication_due_gate.py`، فایل‌های regression وابسته، `cloudflare/affilio-minute-dispatcher.js`، تست Worker، `.github/workflows/offerchin-publisher.yml`، handbook و سند سیاست رتبه‌بندی.

**آزمون و نتیجه:** تست‌های cadence، سرریز صف، dispatch due، refill، گیت ارسال پیش از discovery، editorial delivery runway و score مستقل از قیمت به مجموعهٔ آزمون افزوده/به‌روزرسانی شده‌اند. در زمان ثبت این ورودی، اجرای کامل CI شاخهٔ اصلاحی هنوز نهایی نشده است؛ بنابراین نتیجهٔ سبز یا انتشار عمومی ادعا نمی‌شود. گیت آخرین‌مایل همچنان قیمت/موجودی/تخفیف/لینک را مجدداً بررسی می‌کند.

**شواهد/شناسه:** علت توقف در اجرای ناشر `43834771090` ثبت شد: `queue_size=17`، `planned_products=17`، `available_slots=0` و `PUBLISHER_NOTHING_DUE`. شاخهٔ اصلاحی `fix/offerchin-57m-three-factor-editorial-20261116-v2`؛ CI و PR پس از ثبت این ورودی پیگیری می‌شوند.

**ریسک/بازگشت:** پنجرهٔ موقت در صورت ناموجود بودن ETA می‌تواند با زمان واقعی اسکن فاصله داشته باشد؛ این مقدار صرفاً برنامهٔ تحویل است و نباید ETA اسکن معرفی شود. هر slot فقط یک پست اصلی را به صف می‌دهد؛ محدودیت سقف روزانه و duplicate guard باقی می‌ماند. برای بازگشت، commitهای کد/Worker revert شوند؛ state، صف، رسیدهای Telegram/Bale و سابقهٔ انتشار reset یا حذف نشوند.

**وضعیت:** تغییرات در شاخهٔ مجزا ثبت شده‌اند؛ ادغام و deploy فقط پس از سبزشدن تست‌های Python، Node/Worker و Documentation Gate انجام می‌شود. پس از ادغام، اولین نوبت صف موجود باید با اجرای کنترل‌شدهٔ ناشر بازیابی و رسید عمومی بررسی شود.

## ۲۰۲۶-۱۱-۱۶ — بهبود تصویر و CTA تحریریه در رسانه‌ها

**هدف:** یکسان‌سازی ظاهر و متن تحریریه در تمام رسانه‌ها، حذف نمایش منابع از محتوای عمومی، پرهیز از عکس محصولات در پست‌های آموزشی و رفع دعوت غیرقابل‌کلیک کانال بله.

**تغییر/اقدام:** در شاخهٔ اصلاحی، قالب پیام تحریریه از نمایش نام/URL منابع پاک شد؛ منابع و اتصال claim به منبع همچنان در اعتبارسنجی دادهٔ داخلی باقی می‌ماند. کپشن با چند ایموجی معنایی و فاصله‌گذاری خواناتر ساخته می‌شود. تصویرسازی پوستر/ویدئو موضوع‌محور شد و دیگر عکس محصول صف بعدی دریافت یا واکشی نمی‌شود. دعوت بله به دکمهٔ واقعی inline keyboard با URL کانال تبدیل شد؛ لینک متنی تلگرام حفظ شد. توضیحات ویدئو نیز از منابع عمومی پاک شد. تست‌های regression برای این قراردادها اضافه/به‌روزرسانی شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_publisher.py`، `affilio_radar/editorial_video.py`، `affilio_radar/test_editorial_publisher.py`، `docs/OFFERCHIN_EDITORIAL_FALLBACK_FA.md`، `docs/CHANGELOG_FA.md`. مسیرهای کارت محصول و انتخاب آفر تغییر داده نشدند.

**آزمون و نتیجه:** تست‌های regression و CI پس از ایجاد PR باید اجرا شوند؛ در زمان ثبت این ورودی، نتیجهٔ نهایی CI و مشاهدهٔ واقعی دکمه در کانال بله هنوز در انتظار است. انتشار زنده یا موفقیت کلیک واقعی ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-editorial-media-and-bale-cta-20261116`. Commitهای کد: `940ae27011794ab7e770cb6060fab084e7b53c0c`، `c698975925503b09461a21160acb709fe4980d3e` و `386ac509135da988c23f59254cc42bdba0d2d30f`. PR و نتیجهٔ Actions پس از ایجاد ثبت می‌شود.

**ریسک/بازگشت:** اگر Bale نسخه یا ساختار inline keyboard را نپذیرد، API ارسال ممکن است خطا دهد؛ نباید آن را به‌عنوان دعوت کلیک‌پذیر یا انتشار موفق ثبت کرد. بازگشت با revert همین تغییرات کد ممکن است؛ صف، state و تاریخچهٔ انتشار نباید reset شوند.

**وضعیت:** کد و تست‌ها در شاخهٔ جدا ثبت شده‌اند؛ CI و بررسی واقعی مقصد بله در انتظار؛ هنوز روی `main` و production اعمال نشده‌اند.

---

## ۲۰۲۶-۱۱-۱۶ — نتیجهٔ نهایی CI و ادغام اصلاحات تحریریه

**هدف:** تکمیل سابقهٔ اصلاحات تحریریه با نتیجهٔ واقعی آزمون‌ها و وضعیت استقرار پس از PR #224.

**تغییر/اقدام:** PR #224 با روش squash در شاخهٔ `main` ادغام شد. تصویرسازی موضوعی، حذف منابع از خروجی عمومی، ایموجی‌های معنایی و دکمهٔ مستقل عضویت بله اکنون در کد اصلی قرار دارند. workflow تشخیصی shadow پس از ادغام اجرا شد و موفق بود؛ این workflow صرفاً read-only است و پست عمومی ایجاد نمی‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_publisher.py`، `affilio_radar/editorial_video.py`، تست‌های تحریریه، handbook و قرارداد سبک تحریریه؛ PR #224.

**آزمون و نتیجه:** Editorial Contract Tests با ۹۰ تست موفق؛ Unified Video Fan-out Validation موفق؛ Documentation Gate روی PR موفق؛ Editorial Shadow Diagnostics پس از ادغام موفق. اجرای Documentation Gate مربوط به push نهایی در زمان ثبت این ورودی در حال اجراست. هیچ تستی به کانال عمومی پیام ارسال نکرده است.

**شواهد/شناسه:** PR #224: https://github.com/Mehran0960/ai_news_bot/pull/224 ؛ merge commit `9282c94b2846a85f72424b9dc9145aa23780aec9`؛ Editorial Contract run `43906363441`؛ Video Fan-out run `43906363699`؛ PR Documentation Gate run `43906363687`؛ Post-merge Shadow run `43907168610`؛ Post-merge Documentation Gate run `43907168768`.

**ریسک/بازگشت:** تأیید ساختار payload دکمه در تست خودکار به معنی اثبات نمایش/کلیک نهایی در اپ بله نیست. نخستین پست تحریریهٔ عادی پس از ادغام باید از نظر نمایش دکمه و باز شدن `https://ble.ir/OfferChin` بررسی شود. در صورت شکست API، ارسال باید ناموفق/نیازمند بررسی ثبت شود و نباید ادعای CTA کلیک‌پذیر شود. rollback با revert merge commit ممکن است؛ state و صف انتشار نباید reset شوند.

**وضعیت:** تغییر کد در `main` ادغام شده؛ تست‌های PR و shadow پس از ادغام موفق؛ تأیید end-to-end دکمهٔ بله تا بررسی نخستین پست واقعی در انتظار است.

---



## ۲۰۲۶-۱۱-۱۶ — تمرکز تجاری تحریریه، شفافیت منبع و نگهداری ۴۸ساعتهٔ آفرها

**هدف:** تبدیل fallback تحریریه از نکته‌های عمومی و گاه نامرتبط به محتوای تصمیم‌یار خرید؛ حذف CTA بی‌معنای عضویت در همان کانال؛ افزودن مسیر درآمدزای قابل انتساب بدون دور زدن اعتبارسنج افیلیو؛ و حذف آفرهای قدیمی بدون ازبین‌بردن محتوای ماندگار.

**تغییر/اقدام:**  
- قالب تحریریه سربرگ ثابت «راهنمای کاربردی آفِرچین» و امضای تکراری برند/عضویت در همان کانال را حذف کرد.
- نام و URL منبع در کپشن نمایش داده می‌شود.
- CTA تنها از محصول مرتبط صف ساخته می‌شود و فقط با قالب فعلی افیلیو برای همان محصول اعتبار می‌گیرد؛ در بله دکمهٔ واقعی پیشنهاد مرتبط ایجاد می‌شود.
- چهار مطلب privacy-only از بانک evergreen حذف و ارتباط آن موضوع از mapping محصولات موبایل/صوتی کنار گذاشته شد؛ ۳۳ مطلب باقی مانده است.
- اسکنر metadata-only از دیجی‌کالا مگ و زومیت پشتیبانی می‌کند؛ فیدهای ناموفق جداگانه ثبت می‌شوند و تنها نامزدهای خروجی در حافظهٔ دیده‌شده علامت می‌خورند.
- سیاست retention برای پست‌های محصول Telegram/Bale از ۷ روز به ۴۸ ساعت تغییر کرد؛ محتوای editorial مستثناست.
- ویدئوهای YouTube/Aparat و محتوای Filo حذف یا خصوصی نمی‌شوند تا مسیر رسمی و قابل‌آزمون آماده باشد.

**فایل‌ها/سامانه‌ها:**  
affilio_radar/editorial_publisher.py، affilio_radar/test_editorial_publisher.py، affilio_radar/editorial_bank.json، affilio_radar/editorial_content.py، affilio_radar/digikala_mag_discovery.py، affilio_radar/test_digikala_mag_discovery.py، affilio_radar/expiration_monitor.py، affilio_radar/test_expiration_monitor.py، workflowهای discovery و retention، handbook و policy docs.

**آزمون و نتیجه:** تست‌های رندر تحریریه، فیدهای مجاز و retention به‌روزرسانی شده‌اند؛ CI روی PR #225 در حال اجرا/بازبینی است. هیچ پست عمومی و هیچ دادهٔ live state در شاخه دستکاری نشده است.

**شواهد/شناسه:** شاخهٔ feat/offerchin-editorial-commerce-focus-20261116؛ PR شمارهٔ ۲۲۵.

**ریسک/بازگشت:** فعال شدن retention پس از merge باعث حذف خودکار پست‌های محصول قدیمی‌تر از ۴۸ ساعت در Telegram/Bale خواهد شد؛ rollback با بازگرداندن مقدار retention در workflow و monitor ممکن است. CTA تنها برای لینک‌های محصول تأییدشده کار می‌کند و هیچ deep-link دسته‌بندی را مجاز نمی‌کند. Rollback هر تغییر با revert همان PR ممکن است.

**وضعیت:** تغییرات روی شاخهٔ ویژگی انجام شده؛ CI و بازبینی نهایی در انتظار.


**تکمیل اتصال منبع محلی به چرخهٔ انتخاب:** مشخص شد که `_load_bank()` از قبل `editorial_approved_items.json` را با بانک evergreen ادغام می‌کند؛ یک مورد مستقل DigiKala Mag در آن ثبت است. در این PR تست صریح ادغام و انتخاب این آیتم اضافه و CI برای اعتبارسنجی هر دو فایل اصلاح شد. بانک evergreen ۳۳ مورد و فایل تأییدشده یک مورد محلی دارد؛ جمع مؤثر ۳۴ مورد.

## ۲۰۲۶-۱۱-۱۶ — گیت سخت ارتباط تحریریه با محصول

**هدف:** جلوگیری قطعی از انتشار محتوای عمومی و بی‌ارتباط با کالای انتخاب‌شده و جلوگیری از ارسال مجدد آیتم‌هایی که از بانک جاری حذف یا منقضی شده‌اند.

**تغییر/اقدام:**
- تبدیل ارتباط موضوع با محصول از «امتیاز ترجیحی» به شرط لازم؛ در نبود مطلب مرتبط، slot تحریریه خالی می‌ماند.
- افزودن فهرست topicهای مجاز و بازنشسته‌کردن IDهای خارج از تمرکز، از جمله `app-permissions`.
- اولویت‌دهی به دیجی‌کالا مگ، سپس زومیت و بعد منابع معتبر ایرانی؛ منابع خارجی برای اصول عمومی تصمیم خرید نگه داشته می‌شوند.
- اعتبارسنجی مجدد صف فعال در زمان ارسال با بانک جاری، claims/sources، تاریخ بازبینی و محصول مرتبط؛ آیتم حذف‌شده، تغییرکرده، منقضی یا نامرتبط لغو می‌شود.
- افزودن regression برای رد محتوای حریم خصوصی نامرتبط، جلوگیری از fallback بی‌ربط، رتبه‌بندی منبع ایرانی و حذف آیتم قدیمی از صف.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_content.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/test_editorial_content.py`، `affilio_radar/test_editorial_publisher.py`، `.github/workflows/offerchin-documentation-gate.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** Editorial Contract Tests شامل compile، اعتبارسنجی بانک، shadow read-only، تست‌های محتوا/صف/رندر/retry و retention ۴۸ساعته موفق شد؛ Unified Video Fan-out Validation و Multi-Source Editorial Discovery نیز موفق شدند. Documentation Gate برای commit پیشین به‌دلیل عدم رعایت قالب ساختاری changelog شکست خورد؛ قالب این ورودی و عمق checkout آن workflow اصلاح شده و اجرای جدید در انتظار نتیجه است. هیچ پیام زنده‌ای حذف یا ارسال آزمایشی نشده است.

**شواهد/شناسه:** PR #226: https://github.com/Mehran0960/ai_news_bot/pull/226 ؛ head commit `3302621a533fd3ae3e3de3128aea2ad8d0738741`؛ Editorial Contract run `43932200880`؛ Video Fan-out run `43932201118`؛ Multi-Source Discovery run `43932200845`.

**ریسک/بازگشت:** سخت‌گیری موضوعی می‌تواند تعداد slotهای تحریریه را کم کند؛ این رفتار عمدی است و کیفیت را بر حجم مقدم می‌کند. برای افزودن موضوع جدید، باید نگاشت موضوع به گروه محصول، منبع معتبر و تست مرتبط اضافه شود. بازگشت با revert همین PR ممکن است؛ state و صف انتشار نباید reset شوند.

**وضعیت:** کد و تست‌ها روی شاخهٔ PR #226 اصلاح شده‌اند؛ ادغام به main منوط به سبزشدن دوبارهٔ Documentation Gate است.

## ۲۰۲۶-۱۱-۱۷ — حذف لینک‌های عمومی تحریریه و فاصلهٔ مشترک شناور ۳۱ تا ۴۷ دقیقه

**هدف:** تبدیل خروجی تحریریه به محتوای مستقل و غیرتجاری، کاهش تراکم پست‌های کانال و حفظ غلبهٔ پیشنهادهای محصول بدون دورزدن فاصلهٔ انتشار.

**تغییر/اقدام:**
- رندر عمومی تحریریه، پوستر/کاور و متن داخل تصویر/ویدئو و توضیحات ویدئویی، خطوط منبع، لینک مقاله، CTA «مشاهدهٔ پیشنهاد مرتبط»، لینک همکاری در فروش و خطوط دارای URL را حذف می‌کند؛ metadata منبع و ادعاها در بانک/ledger داخلی حفظ می‌شوند.
- گارد مشترک محصول/تحریریه از حداقل ۲۱ دقیقه به حداقل سخت ۳۱ دقیقه تغییر کرد؛ تابع deterministic و مبتنی بر sequence/شناسه، فاصلهٔ هر slot را بین ۳۱ تا ۴۷ دقیقه انتخاب می‌کند تا بازاجرای planner زمان همان slot را بی‌دلیل تغییر ندهد.
- زمان‌بندی مجدد صف محصول از فاصله‌های متغیر استفاده می‌کند و وجود تحریریهٔ رزروشده را در reflow حفظ می‌کند. ازدست‌رفتن slot با burst جبران نمی‌شود.
- سقف تحریریه همان یک مطلب پس از شش پست محصولِ تأییدشده باقی ماند؛ در مصرف کامل آن، ترکیب خروجی حدود ۸۵٫۷٪ محصول و ۱۴٫۳٪ تحریریه است.
- برای درج یک تحریریه، یک فاصلهٔ ۳۱–۴۷ دقیقه‌ای قبل و یک فاصلهٔ ۳۱–۴۷ دقیقه‌ای بعد رزرو می‌شود. بنابراین فاصلهٔ محصول‌به‌محصول در همان نوبت می‌تواند ۶۲–۹۴ دقیقه باشد. رزرو در صورت تهدید deadline محصول انجام نمی‌شود؛ اگر تحریریه بدون رسید کانالی نهایی شود، رزرو آزاد و زمان محصولات بعدی بازگردانی می‌شود.
- اسناد سیاست تحریریه و handbook با این رفتار همسو شدند. ارزیابی اثر سیاست برای ۱۴ روز پس از rollout تعریف شد؛ quiet-hours ثابت به‌علت نبود دادهٔ معتبر ساعت‌به‌ساعت هنوز فعال نشده است.

**فایل‌ها/سامانه‌ها:** `affilio_radar/publication_policy.py`، `affilio_radar/content_delivery.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/test_content_delivery.py`، `affilio_radar/test_editorial_publisher.py`، `affilio_radar/test_affilio.py`، `.github/workflows/offerchin-editorial-contract.yml`، `docs/OFFERCHIN_DIGIKALA_MAG_SOURCE_POLICY_FA.md`، handbook و changelog.

**آزمون و نتیجه:** regression برای فاصلهٔ متغیر، حفظ slot تحریریه در reflow، پاک‌سازی نمونهٔ واقعی منبع/افیلیت از کپشن، پوستر/کاور، متن داخل ویدئو و توضیحات ویدئو و آزادسازی رزرو در شکست تحریریه اضافه/به‌روزرسانی شد. اجرای GitHub Actions و Documentation Gate پس از بازشدن PR باید نتیجهٔ واقعی را تعیین کند؛ در زمان ثبت این ورودی، CI هنوز ادعا نشده است. هیچ پست عمومی در این تغییر ارسال یا حذف نشده است.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-31-47m-editorial-cleanup-20261117`؛ commitهای این شاخه در PR مستقل ثبت خواهند شد.

**ریسک/بازگشت:** درج تحریریه به‌عنوان یک محتوای واقعی می‌تواند فاصلهٔ میان دو پست محصول را در آن چرخه تا ۹۴ دقیقه افزایش دهد؛ این رفتار برای حفظ فاصلهٔ مشترک و ترکیب ۶:۱ آگاهانه است. کاهش خودسرانهٔ فاصله یا فشرده‌کردن queue rollback محسوب نمی‌شود و مجاز نیست. rollback فقط با revert کد/سیاست PR انجام شود؛ state، صف، ledger، رسید انتشار و پست‌های عمومی reset یا دستکاری نشوند.

**وضعیت:** تغییرات روی شاخهٔ مستقل ثبت شده‌اند؛ PR/CI، ادغام در main و rollout عملیاتی هنوز انجام/تأیید نشده‌اند.

**تکمیل بازبینی زمان‌بند — ۱۷ نوامبر ۲۰۲۶:** projection ویدئو به‌جای محاسبهٔ نقطهٔ میانی، زمان رزروشدهٔ واقعی تحریریه را منتشر می‌کند؛ ساعت برنامه‌ریزی محصول از ساعت آخرین انتشار عمومی جداست، اما guard مشترک پس از هر پست (حتی تحریریه) پابرجاست. ناشر محصول نیز پس از اولین تحویل عمومی در هر اجرای Workflow، ارسال محتوای تازهٔ بعدی را متوقف می‌کند؛ retry همان مقصدهای یک آیتم قبلاً منتشرشده جداگانه پردازش می‌شود و هیچ backlog با burst تخلیه نمی‌شود. آزمون قرارداد این رفتار را به‌صورت static guard نگه می‌دارد.


## ۲۰۲۶-۱۱-۱۷ — رفع توقف زودهنگام صف محصول و گرسنگی fan-out ویدئو

**هدف:** بازگرداندن ظرفیت انتشار کانال به سقف مصوب پروژه و جلوگیری از معطل‌ماندن دائمی ویدئوهای انتخاب‌شده پشت صف اسکن مستقل کاتالوگ، بدون به‌هم‌زدن FIFO یا تقدم نوبت محصول.

**مشاهدهٔ مبنا:** در اجرای ناشر \`44125163267\`، شمارندهٔ سقف روزانه روی ۵۵ متوقف شد؛ در همان اجرا ۱۳ نامزد واجد شرایط وجود داشت اما \`available_slots=0\`، \`queued=0\` و \`PUBLISHER_QUEUE_EMPTY\` ثبت شد. درحالی‌که handbook و سیاست عملیاتی سقف ۷۲ پست روزانه را ثبت کرده‌اند، مقدار پیش‌فرض و دو override اجرایی هنوز ۵۵ بودند. sidecar نیز ۱۲۲ رکورد ویدئویی داشت که ۱۲۱ مورد برای YouTube/Aparat/Filo در وضعیت pending بودند. Worker dispatch ویدئو را علاوه بر قفل ناشر، به صفرشدن \`pending_page_count\`، پایان کامل cycle و idle بودن workflow کاتالوگ وابسته کرده بود؛ اسکنر از concurrency group و ledger مستقل استفاده می‌کند و این شرط می‌توانست صف ویدئو را گرسنه نگه دارد.

**تغییر/اقدام:**
- سقف پیش‌فرض و هر دو override انتخاب/تحویل از ۵۵ به ۷۲ همسان شدند؛ سقف روزانه همچنان سخت و بر اساس روز ایران است.
- تست regression اضافه شد تا مقدار پیش‌فرض، مقدار runtime و دو override Workflow از هم جدا نشوند.
- گیت ویدئو از وابستگی به وضعیت/صف اجرای کاتالوگ جدا شد. fan-out فقط در صورت خالی‌بودن صف ویدئو، نبود نوبت کانالی برنامه‌ریزی‌شده و فعال‌نبودن ناشر اصلی dispatch می‌شود.
- serialization مشترک ناشر/ویدئو، ترتیب FIFO، سقف تلاش و preflight مستقل مقصدها حفظ شد. اسکن کاتالوگ فقط به‌خاطر وجود صف ویدئو متوقف نمی‌شود.

**فایل‌ها/سامانه‌ها:** \`affilio_radar/publication_policy.py\`، \`affilio_radar/test_affilio.py\`، \`.github/workflows/offerchin-publisher.yml\`، \`cloudflare/affilio-minute-dispatcher.js\`، \`cloudflare/affilio-minute-dispatcher.test.mjs\`، \`docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md\` و همین changelog.

**آزمون و نتیجه:** تست‌های regression برای یکسان‌بودن سقف روزانه و عدم گرسنگی fan-out اضافه شدند. نتیجهٔ نهایی Node/Worker، Wrangler dry-run، Documentation Gate و تست‌های Python باید از اجرای PR گزارش شود؛ در این ورودی موفقیت آن‌ها یا انتشار عمومی جدید ادعا نمی‌شود.

**شواهد/شناسه:** مبنای تشخیص: GitHub Actions publisher run \`44125163267\` و video sidecar تولیدشده در \`2026-11-17T16:35:56Z\`. شاخهٔ اصلاحی: \`fix/offerchin-publication-cap-video-dispatch-20261117\`.

**ریسک/بازگشت:** افزایش سقف از ۵۵ به ۷۲ می‌تواند تعداد پست‌های روزانه را افزایش دهد، اما هیچ محصولی بدون عبور از گیت‌های فعلی قیمت، موجودی، تخفیف، لینک و تقاضا منتشر نمی‌شود. fan-out موازی با اسکنر فقط روی checkpointهای مستقل انجام می‌شود و با قفل ناشر اصلی هم‌زمان نمی‌شود. rollback با revert همین تغییر کد/پیکربندی ممکن است؛ state، صف، ledger، شناسه‌های پست و محتوای عمومی نباید reset یا دستکاری شوند.

**وضعیت:** اصلاحات در شاخهٔ مستقل ثبت شده‌اند؛ PR، CI، ادغام و Deploy عملیاتی در انتظار تأیید هستند.


## تکمیل قراردادهای CI برای اصلاح انتشار — ۱۷ نوامبر ۲۰۲۶

در اجرای نخست PR #229 دو تست ایستا با رفتار جدید ناسازگار بودند: Editorial Contract هنوز مقدار ۵۵ را به‌عنوان مقدار ثابت انتظار داشت؛ Unified Video Fan-out نیز الزام می‌کرد dispatch ویدئو وضعیت اجرای کاتالوگ را بررسی کند. این دو assertion با سیاست ۷۲ پست روزانه و جداسازی صف/قفل کاتالوگ از dispatch ویدئو همسو شدند. گیت جدید همچنان فعال‌بودن ناشر اصلی، نوبت کانالی برنامه‌ریزی‌شده و حفظ کنترل‌های مستقل اسکن کاتالوگ را بررسی می‌کند. فایل‌های CI اصلاح‌شده: `.github/workflows/offerchin-editorial-contract.yml` و `.github/workflows/offerchin-video-fanout-validation.yml`. اجرای نهایی CI پس از این اصلاح باید نتیجهٔ قطعی را مشخص کند.


## اصلاح تکمیلی تست سقف روزانه — ۱۷ نوامبر ۲۰۲۶

اجرای push/PR نشان داد متن regex چندخطیِ تست جدید سقف روزانه هنگام درج در فایل Python به خط بعد شکسته شده بود و SyntaxError می‌داد. تست به استخراج خط‌محور متغیرهای `AFFILIO_MAX_DAILY_CHANNEL_POSTS` تغییر کرد؛ حالا مقدار پیش‌فرض، مقدار runtime و هر دو override انتخاب/تحویل را بدون regex و با مقایسهٔ صریح ۷۲ می‌سنجد. این اصلاح فقط تست است؛ صف، state و منطق ارسال تغییر نمی‌کنند.


## کاهش زمان checkout در Documentation Gate — ۱۷ نوامبر ۲۰۲۶

گیت مستندات برای اعتبارسنجی SHA دقیق PR base/head دیگر کل تاریخچهٔ مخزن را دریافت نمی‌کند؛ عمق ۵۰ commit انتخاب شد، چون اختلاف مبنای PR #229 با head بسیار کمتر از این مقدار است. این کار محتوای اعتبارسنجی را تغییر نمی‌دهد و دسترسی به هر دو commit لازم را حفظ می‌کند؛ فقط دانلود تاریخچهٔ قدیمی snapshotهای حجیم را حذف می‌کند. فایل اصلاح‌شده: `.github/workflows/offerchin-documentation-gate.yml`.


## محدودسازی فایل‌های checkout در Documentation Gate — ۱۷ نوامبر ۲۰۲۶

بهینه‌سازی depth=50 به‌تنهایی کافی نبود؛ checkout هنوز blobهای حجیم catalog/state را برای گیتی دریافت می‌کرد که فقط handbook/changelog را اعتبارسنجی می‌کند. actions/checkout اکنون از filter=blob:none و sparse-checkout محدود به پوشه‌های scripts و docs استفاده می‌کند. git diff و git show برای SHAهای دقیق base/head همچنان مبنای اعتبارسنجی هستند. این تغییر مسیر انتشار یا state عملیاتی را لمس نمی‌کند.


## ۲۰۲۶-۱۱-۱۷ — رفع گرسنگی دائمی fan-out ویدئوی OfferChin، به‌ویژه فیلو

**هدف:** رفع توقف دائمی صف ویدئو در زمان‌بند دقیقه‌ای، بدون کاهش اولویت انتشار کانال و بدون موازی‌کردن نویسندگان state مشترک.

**تغییر/اقدام:**
- Worker فقط زمانی fan-out ویدئو را defer می‌کند که نوبت کانال/تحریریه در ۳۰ دقیقهٔ آینده باشد یا ناشر کانال فعال باشد؛ slot دورتر به‌تنهایی مانع dispatch نیست.
- سقف Workflow ویدئو ۲۰ دقیقه و تعداد محصول هر اجرا یک مورد شد؛ زمان‌بند دقیقه‌ای FIFO را در پنجره‌های امن بعدی ادامه می‌دهد.
- تست رگرسیون برای slotهای ۰، ۱۰، ۲۹، ۳۰ و ۳۱ دقیقه و نوبت تحریریه اضافه شد.
- شواهد، محدودیت رسانه‌ها و معیار تأیید انتشار در Handbook و گزارش رخداد ثبت شدند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `.github/workflows/offerchin-video-publisher.yml`، `docs/OFFERCHIN_PUBLICATION_STARVATION_FIX_2026-11-17_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`، `README.md` و همین changelog.

**آزمون و نتیجه:** Node syntax، تست‌های Cloudflare Worker و Wrangler dry-run در PR #230 موفق شدند. گیت مستندات در اجرای نخست به‌علت قالب‌بندی ناقص changelog رد شد؛ قالب این مدخل مطابق قرارداد validator اصلاح شد و باید نتیجهٔ اجرای جدید گیت بررسی شود. انتشار عمومی تازه هنوز ادعا نمی‌شود.

**شواهد/شناسه:** snapshot با زمان `2026-11-17T17:19:45Z`: ۱۱۹ رکورد؛ Telegram/Bale/Rubika هرکدام ۱۱۹ `sent`؛ Filo/YouTube/video generation هرکدام ۱۱۹ `pending`؛ Eitaa تعداد ۱۱۹ `not_connected`؛ Aparat تعداد ۱۱۸ `skipped_unverified_deadline` و یک `pending`. ورود Filo در `2026-11-17T16:51:37Z` تأییدشده بود. PR: #230، شاخهٔ `fix/offerchin-video-queue-starvation-20261117`.

**ریسک/بازگشت:** یک محصول در هر اجرای حداکثر ۲۰ دقیقه‌ای پردازش می‌شود؛ در نتیجه تخلیهٔ backlog نسبت به batch چهارمحصولی کندتر است، اما زمان کانال رزروشده را اشغال نمی‌کند. Aparat بدون deadline تأییدشده مسدود می‌ماند و Eitaa بدون اعتبارنامه متصل نمی‌شود. rollback با revert کد/Workflow همین PR انجام می‌شود؛ state، صف، ledger و رسیدهای انتشار نباید reset یا دستکاری شوند.

**وضعیت:** اصلاح کد، تست و مستندات در PR #230 ثبت شده‌اند. ادغام در main و Deploy Worker تا موفقیت همهٔ گیت‌ها و مشاهدهٔ استقرار انجام‌شده تلقی نمی‌شود؛ انتشار عمومی ویدئو پس از استقرار باید از روی رسید و شناسه/URL هر مقصد تأیید شود.


## ۲۰۲۶-۱۱-۱۷ — استقلال زمان‌بندی و اجرای مقصدهای رسانه‌ای OfferChin

**هدف:** هیچ رسانه‌ای به زمان‌بندی، موفقیت یا failure رسانهٔ دیگر وابسته نباشد.

**تغییر/اقدام:**
- Worker دیگر وجود نوبت کانال/تحریریه یا فعال‌بودن ناشر کانال را برای Dispatch ویدئو بررسی نمی‌کند؛ YouTube، Aparat و Filo با due check مستقل به workflowهای جداگانه فرستاده می‌شوند.
- Workflowهای کانال، Filo، YouTube و Aparat concurrency group مستقل دارند؛ workflow یکپارچهٔ ویدئو از مسیر خودکار کنار گذاشته شد.
- ارسال عکس در Telegram، Bale، Rubika و Eitaa هم‌زمان آغاز می‌شود. هر adapter روی نسخهٔ خصوصی entry/record خود کار می‌کند و فقط receipt/status خودش را merge می‌کند؛ state مشترک هنگام ارسال شبکه‌ای نوشته نمی‌شود.
- ابزار سه‌طرفهٔ ادغام JSON و تست‌های آن افزوده شد تا commitهای هم‌زمان مقصدهای مستقل، receipt یا status یکدیگر را حذف نکنند.
- تست‌های مستقل‌سازی photo delivery و تست‌های regression زمان‌بند به CI اضافه شدند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`, `cloudflare/affilio-minute-dispatcher.test.mjs`, `affilio_radar/publisher.py`, `affilio_radar/merge_state_conflicts.py`, `affilio_radar/test_merge_state_conflicts.py`, `affilio_radar/test_independent_media_dispatch.py`, `affilio_radar/test_content_delivery.py` و چهار Workflow مستقل رسانه.

**آزمون و نتیجه:** اجرای نخست CI دو مشکل را آشکار کرد: mockهای قدیمی آرگومان جدید `persist` را نمی‌پذیرفتند و changelog برچسب‌های الزامی validator را نداشت. mockها و قالب changelog اصلاح شدند. اجرای بعدی باید موفقیت این اصلاحات را ثابت کند؛ تا آن زمان نتیجهٔ تست نهایی تأییدشده نیست.

**شواهد/شناسه:** PR #231، شاخهٔ `fix/offerchin-independent-media-dispatch-20261117`. Worker سه workflow ویدئویی مجزا را بررسی می‌کند و ارسال چهار مقصد عکس در threadهای مستقل آغاز می‌شود. snapshot قبلی ۱۱۹ رکورد pending برای Filo/YouTube/تولید ویدئو و ارسال موفق ۱۱۹ مورد در Telegram/Bale/Rubika را نشان می‌داد.

**ریسک/بازگشت:** ارسال هم‌زمان ممکن است زمان تکمیل کل run را به کندترین مقصد وابسته کند، اما شروع و ارسال مقصدهای دیگر را معطل نمی‌کند. برای stateهای هم‌زمان از merge سه‌طرفه استفاده می‌شود. Aparat بدون deadline معتبر فقط برای خود Aparat skip می‌شود؛ نبود credential یا rate limit نیز فقط همان مقصد را تحت تأثیر قرار می‌دهد. rollback با revert PR #231 انجام می‌شود؛ state و رسیدهای واقعی نباید پاک شوند.

**وضعیت:** تغییرات در PR #231 منتظر CI و گیت مستندات هستند. ادغام و Deploy تا سبزشدن گیت‌ها انجام‌شده تلقی نمی‌شود؛ انتشار عمومی هر مقصد فقط با شناسه یا URL قابل‌راستی‌آزمایی تأیید خواهد شد.


## ۲۰۲۶-۱۱-۱۷ — همسان‌سازی مسیر اضطراری با استقلال مقصدها

**هدف:** مسیر اضطراری انتشار نیز نباید دوباره ویدئوها را در یک workflow مشترک یا وابسته به یکدیگر اجرا کند.

**تغییر/اقدام:** ناشر اضطراری سه workflow مستقل YouTube، Aparat و Filo را Dispatch می‌کند؛ ثبت state و projection ویدئو با retry و merge سه‌طرفه انجام می‌شود. ارجاع خودکار به workflow یکپارچه حذف شد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/affilio-publisher.yml`، `.github/workflows/offerchin-video-fanout-validation.yml`، `affilio_radar/merge_state_conflicts.py`، Handbook و Changelog.

**آزمون و نتیجه:** گیت CI اکنون بررسی می‌کند که مسیر اضطراری هر سه workflow مستقل را فراخوانی و workflow یکپارچه را فراخوانی نکند؛ نتیجهٔ نهایی پس از اجرای جدید CI ثبت می‌شود.

**شواهد/شناسه:** PR #231، شاخهٔ `fix/offerchin-independent-media-dispatch-20261117`.

**ریسک/بازگشت:** در صورت شکست یک dispatch فقط همان مقصد retry می‌شود؛ state مقصدهای دیگر نباید reset شود. rollback با revert همین تغییر انجام می‌شود.

**وضعیت:** در PR #231 ثبت شد؛ ادغام/استقرار تا سبزشدن همهٔ گیت‌ها انجام‌شده تلقی نمی‌شود.


## ۲۰۲۶-۱۱-۱۷ — جداسازی احراز هویت فیلو از صف آپلود

**هدف:** تست ورود فیلو نباید صف آپلود فیلو یا انتشار رسانه‌های دیگر را متوقف کند.

**تغییر/اقدام:** push-trigger از Workflow آپلود فیلو حذف شد؛ Workflow مستقل login verification با تغییر فایل آپلود فیلو فعال می‌شود. مرحلهٔ persistence احراز هویت concurrency group اختصاصی و merge سه‌طرفهٔ state دارد.

**فایل‌ها/سامانه‌ها:** `.github/workflows/filo-video-upload.yml`، `.github/workflows/filo-login-verification.yml`، `.github/workflows/offerchin-video-fanout-validation.yml`، Handbook و Changelog.

**آزمون و نتیجه:** گیت رگرسیون بررسی می‌کند که workflow آپلود فیلو push-trigger نداشته باشد و login-state persistence از concurrency group ناشر رسانه‌ها استفاده نکند. نتیجهٔ CI پس از اجرای PR ثبت می‌شود.

**شواهد/شناسه:** PR پیگیری روی شاخهٔ `fix/offerchin-filo-login-isolation-20261117`؛ PR اصلی استقلال رسانه‌ها #231 ادغام شده است.

**ریسک/بازگشت:** login verification می‌تواند هم‌زمان با آپلود شروع شود، اما فقط فیلدهای احراز هویت را در state ادغام می‌کند. در صورت شکست persistence، login status قبلی حفظ می‌شود و Workflow آپلود از کار نمی‌افتد. rollback با revert این PR انجام می‌شود.

**وضعیت:** تغییرات در PR پیگیری و منتظر تست‌های خودکار هستند؛ ادغام تا سبزشدن گیت‌ها انجام نمی‌شود.


## ۲۰۲۶-۱۱-۱۷ — حذف گیت اختصاصی deadline آپارات برای استقلال انتشار

**هدف:** آپارات به‌دلیل نداشتن timer خرده‌فروش در انتظار نماند، در حالی که صحت و تازگی آفر حفظ شود.

**تغییر/اقدام:** گیت `verified_expiry_required` برای Aparat حذف شد. آفرهای فاقد timer با last-mile price/stock validation ناشر، integrity audit مستقل و سقف تازگی ۲۴ساعته منتشرشدنی هستند. آفر دارای زمان انقضای معتبر که داخل buffer ایمن باشد همچنان در همهٔ مقصدها متوقف می‌شود. وضعیت‌های قبلی `skipped_unverified_deadline` برای Aparat requeue می‌شوند. Worker نیز این موارد را مستقل Dispatch می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/test_filo_upload_schedule.py`، `affilio_radar/test_shared_selection_media_routing.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، Handbook و سیاست استقلال رسانه‌ها.

**آزمون و نتیجه:** تست‌ها برای requeue شدن Aparat بدون timer، حفظ گیت انقضای واقعی و استقلال Worker به‌روزرسانی شدند. نتیجهٔ CI پس از PR ثبت می‌شود.

**شواهد/شناسه:** snapshot عملیاتی ۱۷ نوامبر شامل ۱۱۸ رکورد Aparat با وضعیت `skipped_unverified_deadline` و یک رکورد pending بود؛ علت این توقف، سیاست داخلی deadline بود، نه خطای خود پلتفرم. PR #233.

**ریسک/بازگشت:** در نبود timer، انقضای طبیعی خرده‌فروش به‌صورت زمان دقیق قابل زمان‌بندی نیست؛ ریسک با last-mile price/stock، integrity audit و تازگی ۲۴ساعته کاهش می‌یابد. known near-expiry همچنان fail-closed است. در صورت مشاهدهٔ stale offer، rollback با revert این PR و بازگرداندن گیت انجام می‌شود.

**وضعیت:** تغییر در PR #233 منتظر CI است؛ تا ادغام و Deploy، این گیت در نسخهٔ زنده هنوز فعال است.


## ۲۰۲۶-۱۱-۱۷ — حذف گیت اختصاصی deadline آپارات برای استقلال انتشار

**هدف:** آپارات به‌دلیل نداشتن timer خرده‌فروش در انتظار نماند، در حالی که صحت و تازگی آفر حفظ شود.

**تغییر/اقدام:** گیت `verified_expiry_required` برای Aparat حذف شد. آفرهای فاقد timer با last-mile price/stock validation ناشر، integrity audit مستقل و سقف تازگی ۲۴ساعته منتشرشدنی هستند. آفر دارای زمان انقضای معتبر که داخل buffer ایمن باشد همچنان در همهٔ مقصدها متوقف می‌شود. وضعیت‌های قبلی `skipped_unverified_deadline` برای Aparat requeue می‌شوند. Worker نیز این موارد را مستقل Dispatch می‌کند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/short_video.py`، `affilio_radar/test_filo_upload_schedule.py`، `affilio_radar/test_shared_selection_media_routing.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، Handbook و سیاست استقلال رسانه‌ها.

**آزمون و نتیجه:** تست‌ها برای requeue شدن Aparat بدون timer، حفظ گیت انقضای واقعی و استقلال Worker به‌روزرسانی شدند. نتیجهٔ CI پس از PR ثبت می‌شود.

**شواهد/شناسه:** snapshot عملیاتی ۱۷ نوامبر شامل ۱۱۸ رکورد Aparat با وضعیت `skipped_unverified_deadline` و یک رکورد pending بود؛ علت این توقف، سیاست داخلی deadline بود، نه خطای خود پلتفرم. PR #233.

**ریسک/بازگشت:** در نبود timer، انقضای طبیعی خرده‌فروش به‌صورت زمان دقیق قابل زمان‌بندی نیست؛ ریسک با last-mile price/stock، integrity audit و تازگی ۲۴ساعته کاهش می‌یابد. known near-expiry همچنان fail-closed است. در صورت مشاهدهٔ stale offer، rollback با revert این PR و بازگرداندن گیت انجام می‌شود.

**وضعیت:** تغییر در PR #233 منتظر CI است؛ تا ادغام و Deploy، این گیت در نسخهٔ زنده هنوز فعال است.


## ۲۰۲۶-۱۱-۱۷ — فعال‌سازی مستقل ایتا

**هدف:** ایتا به‌دلیل پیش‌فرض خاموش داخلی، از چرخهٔ انتشار حذف نشود.

**تغییر/اقدام:** پیش‌فرض `EITAA_ENABLE_PUBLISHING` در ناشر اصلی، ناشر تحریریه و مسیر اضطراری به `true` تغییر کرد؛ مقدار صریح Repository Variable همچنان قابل احترام است. مسیر اضطراری نیز Rubika و Eitaa را مانند ناشر اصلی به محیط خود اضافه کرد. تست‌های فعال‌سازی، خاموش‌کردن صریح و نبود اعتبارنامه افزوده شدند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `.github/workflows/affilio-publisher.yml`، `affilio_radar/publisher.py`، `affilio_radar/editorial_publisher.py`، `affilio_radar/test_content_delivery.py`، Handbook و سیاست استقلال رسانه‌ها.

**آزمون و نتیجه:** تست‌ها تأیید می‌کنند که با وجود token/channel ID ایتا فعال است، با مقدار صریح false خاموش می‌شود و نبود اعتبارنامه فقط همان مقصد را غیرفعال می‌کند. نتیجهٔ CI در PR #234 ثبت می‌شود.

**شواهد/شناسه:** snapshot قبلی ایتا را برای همهٔ ۱۱۷ رکورد `not_connected` نشان می‌داد؛ متغیر enable در Workflow پیش‌فرض false بود. PR #234.

**ریسک/بازگشت:** اگر token یا channel ID در GitHub Secrets تعریف نشده باشد، ایتا همچنان نمی‌تواند ارسال کند؛ هیچ secretی از طریق چت خوانده یا افشا نمی‌شود. rollback با تنظیم صریح `EITAA_ENABLE_PUBLISHING=false` یا revert PR انجام می‌شود.

**وضعیت:** تغییرات در PR #234 منتظر CI هستند؛ فعال‌شدن عملی ایتا پس از اجرای Workflow و تأیید receipt سنجیده می‌شود.


## ۲۰۲۶-۱۱-۱۷ — حفظ صف یوتیوب و retry پس از cooldown سهمیه

**هدف:** پاسخ واقعی daily quota یوتیوب فقط همان مقصد را موقتاً متوقف کند؛ آیتم‌ها حذف یا terminal نشوند و پس از reset خودکار برگردند.

**تغییر/اقدام:** وضعیت `skipped_platform_limit` برای daily quota به `retry` با `youtube_next_attempt_at` تبدیل شد. Worker pause سراسری یوتیوب را فقط برای YouTube اعمال می‌کند و retry timestamp هر مقصد را رعایت می‌کند. پس از cooldown، legacy skipها نیز به‌صورت خودکار requeue می‌شوند. HTTP 429 غیرروزانه backoff ۱۵ دقیقه‌ای دارد. Aparat/Filo/کانال‌ها در زمان pause یوتیوب ادامه می‌دهند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_shared_selection_media_routing.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، Handbook و سیاست استقلال رسانه‌ها.

**آزمون و نتیجه:** تست‌های daily quota، حفظ صف چندمحصولی، resume پس از cooldown و عدم اثر pause یوتیوب بر Aparat افزوده شدند. نتیجهٔ CI در PR #236 ثبت می‌شود.

**شواهد/شناسه:** اجرای زندهٔ ۱۷ نوامبر پس از ۶ آپلود موفق YouTube، پاسخ `rateLimitExceeded / Video Uploads per day` و cooldown تا `2026-11-18T18:39:32Z` ثبت کرد. این محدودیت از API مقصد بود، نه قفل مشترک رسانه‌ها. PR #236.

**ریسک/بازگشت:** انتشار بیشتر در cooldown واقعی YouTube ممکن نیست؛ دورزدن سهمیه مجاز/قابل اتکا نیست. اصلاح فقط صف را حفظ می‌کند تا در اولین زمان مجاز ادامه یابد. rollback با revert PR و بازگرداندن رفتار قدیمی انجام می‌شود.

**وضعیت:** تغییر در PR #236 منتظر CI است؛ انتشار YouTube تا reset سهمیهٔ API متوقف می‌ماند، ولی سایر رسانه‌ها مستقل‌اند.


## ۲۰۲۶-۱۱-۱۷ — حفظ صف یوتیوب و retry پس از cooldown سهمیه

**هدف:** پاسخ واقعی daily quota یوتیوب فقط همان مقصد را موقتاً متوقف کند؛ آیتم‌ها حذف یا terminal نشوند و پس از reset خودکار برگردند.

**تغییر/اقدام:** وضعیت `skipped_platform_limit` برای daily quota به `retry` با `youtube_next_attempt_at` تبدیل شد. Worker pause سراسری یوتیوب را فقط برای YouTube اعمال می‌کند و retry timestamp هر مقصد را رعایت می‌کند. پس از cooldown، legacy skipها نیز به‌صورت خودکار requeue می‌شوند. HTTP 429 غیرروزانه backoff ۱۵ دقیقه‌ای دارد. Aparat/Filo/کانال‌ها در زمان pause یوتیوب ادامه می‌دهند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `affilio_radar/test_shared_selection_media_routing.py`، `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، Handbook و سیاست استقلال رسانه‌ها.

**آزمون و نتیجه:** تست‌های daily quota، حفظ صف چندمحصولی، resume پس از cooldown و عدم اثر pause یوتیوب بر Aparat افزوده شدند. نتیجهٔ CI در PR #236 ثبت می‌شود.

**شواهد/شناسه:** اجرای زندهٔ ۱۷ نوامبر پس از ۶ آپلود موفق YouTube، پاسخ `rateLimitExceeded / Video Uploads per day` و cooldown تا `2026-11-18T18:39:32Z` ثبت کرد. این محدودیت از API مقصد بود، نه قفل مشترک رسانه‌ها. PR #236.

**ریسک/بازگشت:** انتشار بیشتر در cooldown واقعی YouTube ممکن نیست؛ دورزدن سهمیه قابل اتکا نیست. اصلاح فقط صف را حفظ می‌کند تا در اولین زمان مجاز ادامه یابد. rollback با revert PR و بازگرداندن رفتار قدیمی انجام می‌شود.

**وضعیت:** تغییر در PR #236 منتظر CI است؛ انتشار YouTube تا reset سهمیهٔ API متوقف می‌ماند، ولی سایر رسانه‌ها مستقل‌اند.


## ۲۰۲۶-۱۱-۱۸ — جلوگیری دائمی از تکرار محتوای تحریریه و حفظ رسیدها

**هدف:** جلوگیری از بازنشر یک مطلب ثابت پس از پایان cooldown ۲۴ساعته و رفع ازبین‌رفتن شواهد ارسال‌های تکراری میان Telegram، Bale و سایر مقصدها.

**تغییر/اقدام:** انتخاب‌گر دیگر چرخهٔ بانک را پس از اتمام reset نمی‌کند تا همان مطالب دوباره ارسال شوند. شناسهٔ مطلب، fingerprint دقیق و متن‌های مشابهِ قبلاً تحویل‌شده در ledger پایدار ثبت و در تمام چرخه‌های بعدی حذف می‌شوند. اگر محتوای تازهٔ تأییدشده‌ای باقی نمانده باشد، فقط slot تحریریه رد می‌شود؛ صف محصول و workflowهای مستقل رسانه‌ها تغییر نمی‌کنند. تاریخچهٔ تحویل بر مبنای content_id + sequence_number رویدادمحور شده و receiptهای مقصدهای مختلف برای یک event ادغام می‌شوند؛ ارسال بعدی در sequence تازه، تاریخچهٔ قبلی را بازنویسی نمی‌کند.

**فایل‌ها/سامانه‌ها:** affilio_radar/editorial_content.py، affilio_radar/test_editorial_content.py، docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md، docs/OFFERCHIN_EDITORIAL_FALLBACK_FA.md، docs/CHANGELOG_FA.md.

**آزمون و نتیجه:** OfferChin Editorial Contract Tests با run ID 44192952185 موفق شد؛ شامل compile ماژول‌ها، اعتبارسنجی بانک، shadow read-only و تست‌های editorial content/queue/render/retry. OfferChin Documentation Gate در run اولیه 44192952131 به‌علت نبود handbook/changelog جدید شکست خورد؛ پس از افزودن مستندات باید مجدداً اجرا شود.

**شواهد/شناسه:** PR #238؛ head SHA ff54fd71b631f13de39cd6fbcf6f04362a45e0e3. ممیزی state فعلی، برای check-delivery-window یک history row با published_at=2026-11-16T18:09:46Z و رسیدهای مقصد به‌روزشده در 2026-11-17T22:13Z نشان می‌دهد؛ این اختلاف ارسال مجدد را تأیید می‌کند، ولی به‌سبب بازنویسی receipt قبلی، شمارش کامل همهٔ پیام‌های تاریخی ممکن نیست.

**ریسک/بازگشت:** پس از مصرف بانک تأییدشده، محتوای تحریریه موقتاً منتشر نمی‌شود تا مطلب تازه تأیید شود؛ این رفتار عمداً از اسپم جلوگیری می‌کند و صف محصول را متوقف نمی‌کند. rollback با revert PR ممکن است، اما سیاست قدیمیِ تکرار ۲۴ساعته را بازمی‌گرداند. هیچ state زنده‌ای پاک یا reset نشده است.

**وضعیت:** تغییر و آزمون قراردادی روی PR #238 ثبت شده؛ ادغام نشده و گیت مستندات پس از افزودن این ورودی در انتظار اجرای مجدد است.


## ۲۰۲۶-۱۱-۱۸ — اصلاح تحویل مستقل ویدئوی تحریریه به همهٔ مقصدها

**هدف:** رفع گیرکردن صف تحریریه در هر هفت رسانه و جلوگیری از وابستگی مقصدها به یکدیگر؛ حفظ رسیدها و حذف ریسک ارسال مجدد هنگام اجرای موازی.

**تغییر/اقدام:** دو صف مستقل editorial_channel_queue و editorial_video_queue به projection زمان‌بند اضافه شدند. Cloudflare فقط receiptهای failed/retry یا ارسال‌های sending منقضی‌شدهٔ Telegram، Bale، Rubika و Eitaa را از طریق یک Workflow matrix با job و concurrency جداگانه بازیابی می‌کند؛ وضعیت pending اولیه در اختیار ناشر اصلی می‌ماند و مسیر جبرانی هنگام فعال‌بودن ناشر اصلی dispatch نمی‌شود؛ YouTube، Aparat و Filo نیز سه Workflow ویدئویی مستقل خودشان را دارند. هر worker فقط مقصد خودش را پردازش می‌کند و FIFO صف محصول نیز برای همان مقصد اعمال می‌شود. ناشر پیش از تلاش مجدد، receiptهای sent/manual_review را از تاریخچه بازیابی می‌کند. merge_state_conflicts.py تاریخچه تحریریه را با delivery_event_id و ledger را با content_fingerprint ادغام می‌کند تا receiptهای هم‌زمان در یک رویداد جمع شوند، نه اینکه history تکثیر شود. خطای quota روزانهٔ YouTube با retry زمان‌دار ثبت می‌شود و فقط YouTube را تا پایان pause متوقف می‌کند.

**فایل‌ها/سامانه‌ها:** affilio_radar/affilio_radar.py، affilio_radar/editorial_publisher.py، affilio_radar/merge_state_conflicts.py، سه فایل آزمون Python شامل test_editorial_publisher.py، test_shared_selection_media_routing.py و test_merge_state_conflicts.py، cloudflare/affilio-minute-dispatcher.js، cloudflare/affilio-minute-dispatcher.test.mjs، .github/workflows/offerchin-editorial-channel-upload.yml، .github/workflows/offerchin-editorial-contract.yml، سه Workflow ویدئویی YouTube/Aparat/Filo و docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md.

**آزمون و نتیجه:** آزمون‌های projection مستقل صف تصویری و ویدئویی، due/retry مقصدی، watchdog ارسال نامطمئن، انتخاب مقصد، بازیابی receipt و merge هم‌زمان event/ledger اضافه شده‌اند. اجرای اولیهٔ CI گیت مستندات را به‌علت قالب ناقص changelog رد کرد؛ قالب اصلاح شد. اجرای CI روی آخرین commit پس از تکمیل workerهای تصویری باید نتیجهٔ نهایی را تأیید کند؛ تا آن زمان قبولی نهایی ادعا نمی‌شود.

**شواهد/شناسه:** PR #239؛ شاخه fix/offerchin-editorial-video-destinations-20261118. مسیرهای عمومی فقط پس از receipt همان پلتفرم موفق تلقی می‌شوند؛ workflow success به‌تنهایی اثبات انتشار عمومی نیست.

**ریسک/بازگشت:** چهار job تصویری ممکن است هم‌زمان state بنویسند؛ ادغام سه‌طرفه اکنون receiptهای یک delivery_event_id را در یک ردیف ادغام می‌کند. Filo فقط پس از احراز ورود تلاش می‌کند و manual_review یا انتظار تأیید، انتشار عمومی نیست. هیچ پیام قدیمی حذف و هیچ state زنده reset نشده است. بازگشت با revert همین PR ممکن است؛ در آن صورت بازیابی مستقل صف‌های تحریریه غیرفعال می‌شود.

**وضعیت:** PR #239 باز است و ادغام/استقرار نشده؛ منتظر CI نهایی و بررسی آخرین رسیدهاست.


**اصلاح تکمیلی در همان شاخه:** مسیر جبرانی تصویری به receiptهای ناموفق/قابل retry و تلاش‌های sending منقضی‌شده محدود شد؛ ارسال pending اولیه فقط توسط ناشر اصلی انجام می‌شود. زمان‌بند قبل از شروع بازیابی، dispatch/فعال‌بودن ناشر اصلی را کنترل می‌کند. علاوه بر آن، ناشر اصلی، ناشر اضطراری و Workflow جبرانی کانال‌ها قفل سراسری مشترک `offerchin-channel-publisher` دارند؛ چهار job مقصدی همچنان داخل همان اجرای matrix می‌توانند موازی باشند. فاصلهٔ زمانی کانال فقط برای رزرو محتوای تحریریهٔ جدید اعمال می‌شود؛ رویداد فعال باید بتواند مقصدهای باقی‌مانده را مستقل تکمیل کند. تست قرارداد، گروه قفل هر سه مسیر را بررسی می‌کند و انتظار قدیمی نام قفل اصلاح شده است.


## ۲۰۲۶-۱۱-۱۸ — موازی‌سازی واقعی انتشار اولیهٔ تحریریه در کانال‌های تصویری

**هدف:** جلوگیری از اینکه کندی یا خطای Telegram، Bale، Rubika یا Eitaa شروع ارسال مطلب تحریریه به مقصدهای دیگر را به تأخیر بیندازد.

**تغییر/اقدام:** چهار مقصد تصویری تحریریه اکنون هم‌زمان اجرا می‌شوند. هر worker یک کپی خصوصی از state دارد و هیچ‌کدام state زنده را نمی‌نویسد. پس از پایان درخواست‌ها، تغییرات هر مقصد با `three_way_merge` ادغام می‌شود تا message ID، وضعیت retry و history مشترک حفظ شوند. سیاست فاصله‌گذاری پست‌های کانالی و مسیر مستقل ویدئو دست‌نخورده باقی مانده‌اند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_publisher.py`، `affilio_radar/test_editorial_publisher.py`، `merge_state_conflicts.py` (استفادهٔ مجدد از merge موجود)، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** یک تست چهاردسته‌ای مبتنی بر `threading.Barrier` اضافه شد که اثبات می‌کند هر چهار ارسال هم‌زمان آغاز شده‌اند؛ همچنین چهار receipt باید در state و یک ردیف history باقی بمانند و هیچ worker موازی نباید `_save` را صدا بزند. نتیجهٔ GitHub Actions پس از بازشدن PR ثبت خواهد شد.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-editorial-parallel-photo-delivery-20261118`؛ PR پس از push ایجاد می‌شود. تا پیش از موفقیت CI، این تغییر ادغام‌شده محسوب نمی‌شود.

**ریسک/بازگشت:** اگر API یک مقصد timeout بدهد، همان مقصد طبق سیاست قبلی `manual_review` یا retry می‌شود و نتیجهٔ سه مقصد دیگر حفظ می‌شود. در صورت بروز اختلاف merge، تغییر را می‌توان با revert همین PR بازگرداند؛ هیچ state زنده یا پیام قبلی reset یا حذف نمی‌شود.

**وضعیت:** تغییر در شاخهٔ اصلاحی آمادهٔ CI؛ انتشار عمومی دستی برای آزمون انجام نمی‌شود.

## 2026-11-18 — بازیابی تحریریه‌های یتیم و حفاظت صف مقصدها

**هدف:** جلوگیری از گم‌شدن مقصدهای تکمیل‌نشدهٔ یک تحریریه در اثر حذف صف فعال، و تکمیل مستقل ویدئوها بدون بازنشر عکس‌های موفق.

**تغییر/اقدام:** PR #239 پیش‌تر در همین تاریخ با commit `f1f34e8c70bc7f3614d61f6de5a50d0bd14b73d0` ادغام شد و Cloudflare Worker با اجرای `44225402804` مستقر شد. ممیزی پس از استقرار نشان داد رویداد اخیر `measure-room-size` در history دارای رسید موفق Telegram/Bale/Rubika و وضعیت pending در YouTube/Aparat/Filo است، اما صف فعال متناظر وجود ندارد. در PR #241 بازیابی محدود به ۲۴ ساعت و حداکثر ۲۰ رویداد اضافه شده است؛ بازیابی فقط با receipt تصویری موفق، وجود محتوای معتبر در بانک بازبینی‌شده، fingerprint سازگار، مقصد ویدئویی pending و نبود terminal attempt انجام می‌شود. رسیدها و message IDهای قبلی حفظ می‌شوند؛ هیچ پست تصویری موفق دوباره ارسال نمی‌شود و مقصد فاقد receipt به‌صورت pending فرض نمی‌شود. رویداد تصویریِ ارسال‌شده پس از پایان slot محصول نیز برای تکمیل مقصدهای باقیمانده فعال می‌ماند. merge state صف فعال را حفظ می‌کند مگر terminal attempt همان content_id/sequence ثبت شده باشد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_publisher.py`، `affilio_radar/merge_state_conflicts.py`، `affilio_radar/test_editorial_publisher.py`، `affilio_radar/test_merge_state_conflicts.py`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** تست‌های بازیابی رویداد یتیم، جلوگیری از replay مقصد تصویری، projection مستقل صف ویدئو، رد رویداد قدیمی‌تر از ۲۴ ساعت، رد terminal attempt، حفظ صف در ادغام هم‌زمان و اجازهٔ حذف پس از terminal اضافه شده‌اند. نتیجهٔ CI مربوط به PR #241 هنوز در انتظار است و تا سبزشدن کامل، این اصلاح ادغام‌شده محسوب نمی‌شود.

**شواهد/شناسه:** PR #241؛ شاخه `fix/offerchin-orphaned-editorial-recovery-20261118`؛ آخرین وضعیت زندهٔ ممیزی‌شده `measure-room-size` با sequence 1554 و رسیدهای photo موفق / video pending.

**ریسک/بازگشت:** فقط eventهای ۲۴ ساعت اخیر eligible هستند؛ eventهای قدیمی‌تر خودکار replay نمی‌شوند. هیچ پیام قبلی حذف یا ارسال تصویری موفق تکرار نمی‌شود. برگشت با revert PR #241 ممکن است و منطق بازیابی event یتیم و حفاظت صف را غیرفعال می‌کند.

**وضعیت:** PR #239 ادغام و Worker مستقر شده است؛ PR #241 باز است و منتظر CI نهایی می‌باشد.


## 2026-11-18 — کامل‌کردن گزارش انتشار رسانه‌ها و کاهش زمان checkout

**هدف:** جلوگیری از حذف آماری مقصدهای جدید از گزارش عملکرد و کاهش زمان آماده‌سازی گردش‌کارهای روزانه‌ای که کل تاریخچه و تمام شاخه‌های Git را دریافت می‌کردند.

**تغییر/اقدام:** شمارش `published_posts_by_platform` اکنون از رجیستری مرکزی `PLATFORM_NAMES` استفاده می‌کند؛ بنابراین Telegram، Bale، Rubika، Eitaa، YouTube، Aparat و Filo همگی در گزارش لحاظ می‌شوند و با اضافه‌شدن مقصد جدید، فهرست دومِ دستی ایجاد نمی‌شود. در پنج workflow دارای persist/rebase یعنی `affilio-radar.yml`، `filo-video-upload.yml`، `aparat-video-upload.yml`، `offerchin-integrity-audit.yml` و `offerchin-editorial-channel-upload.yml`، عمق checkout از تاریخچهٔ کامل به ۱۰۰ commit محدود شد. ناشر اصلی و ویدئوی مشترک قبلاً همین عمق ۱۰۰ را دارند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py` و پنج workflow نام‌برده، به‌علاوهٔ همین changelog و handbook پروژه.

**آزمون و نتیجه:** تست رگرسیون گزارش عملکرد توسعه یافت تا انتشار مستقل در Rubika، Eitaa و Filo را نیز بشمارد؛ خروجی مورد انتظار همچنان فقط مقصدهای واقعاً دارای receipt موفق را شامل می‌شود. CI شاخهٔ اصلاحی باید نتیجه را تأیید کند. عمق ۱۰۰ مطابق الگوی قبلاً ادغام‌شدهٔ PR #210 انتخاب شده تا rebase معمول state را پشتیبانی کند.

**مرز ایمنی:** لینک خرید همچنان مستقیماً به پیوند معتبر Affilio می‌رود؛ واسطهٔ Cloudflare، cadence، انتخاب کالا، state زنده و ارسال عمومی تغییر نکرده‌اند. این گزارش تعداد مقصدهای دارای receipt را می‌شمارد و آن را با کلیک، سفارش یا فروش اشتباه نمی‌گیرد.

**ریسک/بازگشت:** اگر بین checkout و persist بیش از ۱۰۰ commit هم‌زمان ایجاد شود، rebase ممکن است به عمق بیشتری نیاز داشته باشد؛ retry/خطا باید آشکار بماند و force-push یا بازنویسی state مجاز نیست. بازگشت با برگرداندن عمق checkout به صفر یا revert تغییر گزارش ممکن است.

**شواهد/شناسه:** PR #242؛ لاگ‌های Filo run `44227173014`، Aparat run `44227169652` و Integrity Audit run `44226947712` در تاریخ ۱۸ نوامبر ۲۰۲۶، که checkout کامل و حدود سه دقیقه دریافت refها را نشان می‌دهند.

**وضعیت:** در شاخهٔ `perf/offerchin-runner-checkout-and-platform-report-20261118`؛ در انتظار CI و ادغام.


## ۲۰۲۶-۱۱-۱۸ — مقاوم‌سازی ثبت رسیدهای رسانه در برابر هم‌زمانی GitHub Actions

**هدف:** جلوگیری از خطای ذخیره‌سازی state پس از ارسال عمومی موفق، وقتی چند workflow مستقل هم‌زمان فایل‌های `state.json` و `video_upload_dispatch_state.json` را تغییر می‌دهند.

**شاهد:** اجرای ناشر #44228258776 مقصدهای اصلی تلگرام و بله را با موفقیت اجرا کرد، اما مرحلهٔ Persist در push نهایی پس از سه تلاش با race/rejected push شکست خورد؛ دو فایل وضعیت هنگام rebase دارای conflict شدند. اجرای قبلی #44228147318 موفق بود. این خطا به معنی رد پست توسط تلگرام/بله نیست.

**تغییر/اقدام:** در شاخهٔ اصلاحی مستقل، شش مسیر نوشتن وضعیت ناشر اصلی، ناشر ویدئویی، Filo، Aparat، YouTube و تحریریه از ۳ تلاش ثابت به ۱۰ تلاش با backoff افزایشی و jitter تغییر کردند. اسکن اصلی افیلیو نیز merge سه‌طرفهٔ فایل‌های JSON را هنگام conflict انجام می‌دهد و تا ۱۰ بار push را تکرار می‌کند؛ پاک‌سازی انقضا نیز retry و merge امن state می‌گیرد. قفل سراسری انتشار اضافه نشد تا استقلال زمان اجرای رسانه‌ها حفظ شود. منطق سه‌طرفهٔ موجود همچنان receipts مقصدها را merge می‌کند.

**فایل‌ها/سامانه‌ها:** `.github/workflows/offerchin-publisher.yml`، `offerchin-video-publisher.yml`، `filo-video-upload.yml`، `aparat-video-upload.yml`، `youtube-video-upload.yml`، `offerchin-editorial-channel-upload.yml`، `affilio-radar.yml`، `affilio-expiration-cleanup.yml`، `affilio_radar/merge_state_conflicts.py`.

**آزمون و نتیجه:** تست‌های موجود `test_merge_state_conflicts.py` هم‌جوشی رسیدهای مستقل مقصدها، ledger و صف تحریریه را پوشش می‌دهند. workflowهای تغییرکرده پس از بازشدن PR نیازمند CI تازه هستند؛ پیش از آن موفقیت نهایی ادعا نمی‌شود.

**شواهد/شناسه:** اجرای ناموفق #44228258776؛ اجرای قبلی موفق #44228147318؛ شاخهٔ `fix/offerchin-state-persistence-retries-20261118`.

**ریسک/بازگشت:** retry بیشتر ممکن است زمان پایان job را در رقابت شدید افزایش دهد، اما انتشار موازی را متوقف نمی‌کند. سقف ۱۰ تلاش و backoff jittered محدود است؛ rollback با revert همین PR ممکن است.

**وضعیت:** تغییرات شاخه‌ای ثبت شد؛ CI و ادغام در main در انتظار.
## 2026-11-18 — بهبود صحت ممیزی، انتساب و استقلال رسانه‌ها

**هدف:** سالم‌سازی ممیزی قیمت/موجودی و زمان آفر، جلوگیری از انتساب اشتباه کلیک و فروش، و قفل‌کردن استقلال خطای هر مقصد انتشار تصویری.

**تغییر/اقدام:**
- ممیزی زندهٔ دیجی‌کالا از endpoint فعلی جزئیات محصول و helper مشترک استفاده می‌کند؛ مسیرهای قدیمی v1/v2 حذف شده‌اند، HTML fallback محدود به یک تلاش است و دادهٔ نامعلوم هرگز موجب حذف پست نمی‌شود.
- deadlineهای آفر از کارت MCP با تطبیق دقیق product ID می‌آیند؛ فید REST بازنشسته فراخوانی نمی‌شود.
- گزارش عملکرد مشخص می‌کند CTA فعلی مستقیم Aflo را باز می‌کند و از Worker عبور نمی‌کند؛ رویدادهای Worker یا تخصیص آزمایش به‌عنوان کلیک CTA، سفارش یا فروش ثبت نمی‌شوند.
- Worker و helper آزمایشی هفت source رسانه‌ای را می‌شناسند؛ لینک مستقیم زندهٔ خرید تغییر نکرده است.
- دامنهٔ شواهد پرفروش/رشد نظر در فروشگاه دیجی‌کالا با `digikala_store_only` برچسب می‌خورد؛ ترب فقط مقایسهٔ قیمت و MeMarket یک feed مستقل آفر است، نه سنجهٔ تقاضای کل بازار.
- سیاست نگهداری پست‌های تصویری محصول/آفر Telegram و Bale به ۷ روز تغییر می‌کند؛ محتوای evergreen و ویدئوها مستثنا هستند.
- چهار مقصد تصویری در تابع مستقل اجرا می‌شوند: هر adapter state copy خودش را دارد؛ خطای یک future فقط همان مقصد را failed/retry می‌کند و بقیه ادامه می‌دهند.
- workflow رگرسیون، تست استقلال مقصدهای تصویری و تست Node هفت source را اجرا می‌کند.
- playbook الگوبرداری از HotUKDeals، Wirecutter و Impact.com و بررسی اولیهٔ Deema/Dayan اضافه شد؛ هیچ شبکهٔ جدیدی به انتشار زنده متصل نشده است.

**فایل‌ها/سامانه‌ها:** `.github/workflows/affilio-expiration-cleanup.yml`، `.github/workflows/affilio-radar.yml`، `affilio_radar/expiration_monitor.py`، `affilio_radar/test_expiration_monitor.py`، `affilio_radar/affiliate-deal-radar-worker.js`، `affilio_radar/test_affiliate_deal_radar_worker.mjs`، `affilio_radar/affilio_radar.py`، `affilio_radar/test_affilio.py`، `affilio_radar/publisher.py`، `affilio_radar/test_independent_media_dispatch.py`، `affilio_radar/AFFILIO_REPORTING_ACCESS.md`، Handbook، Growth Playbook و Network Review.

**آزمون و نتیجه:** اجرای نهایی رادار #44324690868 روی کد commit `3742a1e4` موفق شد: ۶۰۱ تست Python با ۲ مورد skip و ۴ تست Node با ۴ موفقیت. تمام ۱۰ check مربوط به PR #246 نیز روی همین snapshot کد موفق شدند؛ شامل Documentation Gate، قرارداد تحریریه، چهارعامل رتبه‌بندی، تست catalog sweep، adapterها، fallback، لوگو، ویدئو و رگرسیون Top-100/DigiPay. این تست‌ها صحت مسیرهای کد و شبیه‌سازی‌ها را نشان می‌دهند، نه ارسال عمومی یا فروش واقعی.

**شواهد/شناسه:** شاخهٔ `codex/offerchin-optimization-2026-11-18-refresh2`؛ PR #246؛ مبنای شاخه commit `3b5272f71b9be6ed57d0bd8cad28a4310551c155`. PR قدیمی #245 مبنای ادغام نیست.

**ریسک/بازگشت:** تغییر ممیزی قیمت fail-closed است و در صورت ابهام حذف نمی‌کند؛ بازگشت از طریق revert فایل ممیزی ممکن است. ۷روزه‌کردن حذف Telegram برای پیام‌های قدیمی‌تر از ۴۸ ساعت به Secrets معتبر MTProto نیاز دارد و باید پیش از استقرار بررسی شود. چهار مقصد تصویری هنوز یک runner مشترک دارند؛ crash/timeout خود runner می‌تواند همه را متوقف کند، هرچند exception یک adapter مانع سه مقصد دیگر نیست. لینک خرید، secret و deployment در این شاخه تغییر نکرده‌اند.

**وضعیت:** شاخه‌ای و در انتظار تکمیل CI و بازبینی PR؛ هیچ merge، deployment، حذف پست عمومی یا فعال‌سازی شبکهٔ جدید انجام نشده است.


## ۱۴۰۵/۰۸/۲۷ — تکمیل بستهٔ بهینه‌سازی و الگوبرداری رشد افیلیت

- **هدف:** تکمیل اصلاحات ممیزی محصول و انتشار چندرسانه‌ای، شفاف‌سازی انتساب فروش و مستندسازی روش رشد مبتنی بر ناشران موفق.
- **تغییر/اقدام:** endpoint ممیزی قیمت/موجودی دیجی‌کالا به مسیر فعلی منتقل شد؛ feed منسوخ deadline کنار گذاشته شد؛ eventهای Worker از کلیک CTA مستقیم Aflo تفکیک شدند؛ دامنهٔ شواهد تقاضا به digikala_store_only محدود شد؛ ارسال عکس Telegram/Bale/Rubika/Eitaa دارای state و exception boundary مستقل شد؛ retention هدف‌گذاری‌شدهٔ هفت‌روزه و محدودیت MTProto مستند شد.
- **فایل‌ها/سامانه‌ها:** ۱۷ فایل کد، تست و مستندات در PR #248؛ شاخه codex/offerchin-optimization-2026-11-18-refresh4.
- **الگوبرداری:** مدل جامعه‌محور HotUKDeals، دیوار استقلال تحریریه/تجارت Wirecutter و تفکیک مرحلهٔ تحقیق/تبدیل در Benchmark 2025 impact.com به playbook تبدیل شد. Deema/Dayan فقط نامزد شبکه‌اند؛ فعال‌سازی بدون اثبات SubID، گزارش سفارش و health-check انجام نمی‌شود.
- **آزمون و نتیجه:** هر ۹ Workflow اختصاصی PR #248 روی head c4775fbb227243d65736d9c4f0137bc096bc3fde با موفقیت پایان یافت. این نتیجه فقط تست کد است؛ فروش، انتشار عمومی یا افزایش درآمد را اثبات نمی‌کند.
- **شواهد/شناسه:** PR #248؛ ۹ Workflow موفق؛ PRهای جایگزین #246 و #247 بدون ادغام بسته شدند.
- **ایمنی rollout:** main، Workerهای زنده، secrets، CTA مستقیم، پست‌های عمومی و شبکه‌های افیلیت خارجی تغییر یا فعال نشدند. PR #248 Draft باقی ماند.


## 2026-11-18 — بازیابی صف انتشار و شفاف‌سازی اتصال رسانه‌ها

**هدف:** رفع توقف چرخهٔ انتشار وقتی صف محصولات خالی شده اما زمان‌بندی قدیمیِ تحریریه هنوز به‌عنوان slot معتبر تفسیر می‌شود؛ و جلوگیری از گزارش یا تلاش انتشار برای رسانه‌ای که اتصال واقعی ندارد.

**تغییر/اقدام:**
- Cloudflare dispatcher و گیت زودهنگام Python اکنون timestamp انتشار را فقط وقتی معتبر می‌دانند که صف محصول pending یا صف تحریریهٔ کانالی واقعاً فعال باشد. زمان‌های یتیم با صف خالی دیگر مسیر discovery را مسدود نمی‌کنند؛ throttle سه‌دقیقه‌ای پرکردن صف حفظ شده و صف واقعی همچنان اولویت انتشار دارد.
- پیش‌فرض Eitaa در ناشر محصول، ناشر تحریریه و workflow به خاموش تغییر کرد. فعال‌سازی فقط با `EITAA_ENABLE_PUBLISHING=true` و اعتبارنامهٔ واقعی انجام می‌شود؛ secret یا channel ID جدیدی ساخته/تغییر داده نشد.
- کد خطای امن Filo به log و sidecar تشخیصی اضافه شد؛ وضعیت تعداد تلاش، نیاز به بررسی، زمان ارسال و visibility نیز قابل مشاهده است. وضعیت pending approval یا submit نامشخص همچنان انتشار عمومی تأییدشده نیست و retry کورکورانه به آن اضافه نشده است.
- راهنمای آمادگی Deema ثبت شد. لینک عمومی آزمایش‌شده به صفحهٔ اصلی خانومی redirect شد و پارامترهای clickid/affiliate در مقصد مشاهده شد؛ ثبت کلیک در پنل، سفارش، کمیسیون و deep-link محصول تأیید نشده‌اند. به‌دلیل مشاهدهٔ media «پیندو» در ردیف‌های پنل، Deema فعال نشد و CTAهای Aflo تغییر نکردند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، تست Worker، `affilio_radar/publication_due_gate.py` و تست‌های آن، `publisher.py`، `editorial_publisher.py`، `affilio_radar.py`، تست‌های اتصال پیام‌رسان و Filo، `.github/workflows/offerchin-publisher.yml`، Handbook و `docs/DEEMA_AFFILIATE_PILOT_READINESS_FA.md`.

**آزمون و نتیجه:** در اجرای اولیهٔ PR، تست Worker/Wrangler، adapterها، قرارداد تحریریه، fallback، catalog sweep، ranking و logo در آخرین snapshot بررسی‌شده موفق شدند؛ گیت مستندات فقط به‌دلیل نداشتن changelog entry جدید شکست خورد. یک تست قدیمی نیز پیش‌فرض ایتای فعال را انتظار داشت؛ اصلاح شد تا پیش‌فرض خاموش و opt-in صریح را بررسی کند. پس از افزودن این entry، CI باید دوباره روی آخرین head اجرا شود؛ تا پایان آن، موفقیت کامل بسته ادعا نمی‌شود.

**شواهد/شناسه:** PR #249؛ شاخهٔ `codex/offerchin-publication-starvation-eitaa-filo-diagnostics-2026-11-18`. آخرین snapshot پیش از این changelog، commit `7cd5ab0d8cfa8a168278a3219199a0eb4b28bca8` بود.

**ریسک/بازگشت:** گیت جدید عمداً فقط timestamp یتیم را نادیده می‌گیرد؛ اگر sidecar اشتباهاً صف فعال را صفر گزارش کند، discovery به‌جای delivery-only اجرا می‌شود و همچنان قیمت/موجودی/لینک را در مرحلهٔ آخر دوباره اعتبارسنجی می‌کند. بازگشت با revert PR #249 ممکن است. تغییر پیش‌فرض ایتا ممکن است انتشار آن را تا ثبت opt-in معتبر متوقف نگه دارد؛ این وضعیت با قطع ارتباط واقعی فعلی سازگار است. Filo cadence، صف تأیید، یوتیوب/آپارات، لینک مستقیم خرید و secretها در این PR تغییر نکرده‌اند.

**وضعیت:** PR #249 باز است و هنوز merge یا production deployment انجام نشده است. پس از عبور همهٔ checkها، ادغام و استقرار Worker به‌صورت جداگانه تأیید می‌شود؛ تا آن زمان این اصلاحات روی main/live فعال نیستند.


## 2026-11-19 — تعمیر صف ویدئو و آزادسازی FIFO تحریریه

**هدف:** جلوگیری از مسدود شدن صف ویدئو و محتوای تحریریه توسط رکوردهای محصولی که از پنجرهٔ تازگی ۲۴ساعته عبور کرده‌اند، بدون دور زدن اعتبارسنجی آفر یا ایجاد ارسال تکراری.

**تغییر/اقدام:**
- اسکریپت مستقل `video_queue_maintenance.py` برای سه مقصد YouTube، Aparat و Filo افزوده شد.
- pending/retryهای دارای timestamp نامعتبر یا قدیمی‌تر از ۲۴ ساعت به وضعیت terminal مقصد منتقل می‌شوند؛ رکورد محصول و رسیدهای قبلی حذف نمی‌شوند.
- `skipped_unavailable` فقط برای رکورد تازه و فقط پس از حاضر شدن اعتبارنامهٔ همان مقصد و عبور مجدد از گیت eligibility به `pending` برمی‌گردد.
- workflowهای مستقل سه پلتفرم پیش از صف تحریریه maintenance مقصد خود را اجرا می‌کنند؛ مسیر Filo فقط پس از login verification موفق این مرحله را انجام می‌دهد.
- وضعیت‌های آپلودشده و submitهای فیلو در انتظار تأیید یا دارای نتیجهٔ نامشخص هرگز retry کورکورانه نمی‌شوند.
- regression testهای مستقل به CI مربوط به video fan-out افزوده شدند.

**فایل‌ها/سامانه‌ها:** `affilio_radar/video_queue_maintenance.py`، `affilio_radar/test_video_queue_maintenance.py`، `.github/workflows/youtube-video-upload.yml`، `.github/workflows/aparat-video-upload.yml`، `.github/workflows/filo-video-upload.yml`، `.github/workflows/offerchin-video-fanout-validation.yml`، Handbook و Changelog.

**آزمون و نتیجه:** compile ماژول جدید در اجرای PR #250 موفق شد. تست‌های مستقل صف و regressionهای FIFO در Workflow مربوط به Video Fan-out در حال اجرا هستند؛ نتیجهٔ نهایی تا پایان همان CI ادعا نمی‌شود. Documentation Gate اولیه به‌درستی به‌دلیل فقدان این Handbook/Changelog entry شکست خورد؛ این ورودی برای عبور از گیت افزوده شده است.

**شواهد/شناسه:** PR #250؛ اجرای اولیهٔ Video Fan-out Validation #44399662126؛ Documentation Gate اولیه #44399662130.

**ریسک/بازگشت:** ویدئوی محصول قدیمی عمداً از صف فعال خارج می‌شود و به‌صورت خودکار بارگذاری مجدد نمی‌شود؛ فقط انتخاب تازه و اعتبارسنجی مجدد می‌تواند آن را دوباره وارد چرخه کند. rollback با revert همین PR ممکن است؛ در آن صورت stale pendingها ممکن است دوباره FIFO تحریریه را مسدود کنند. هیچ credential، secret، Worker زنده، CTA افیلیو یا انتشار عمومی در این PR تغییر نکرده است.

**وضعیت:** تغییرات فقط در شاخهٔ PR #250 قرار دارند؛ هنوز merge یا production deployment نشده‌اند. پس از CI و merge، خروجی اجرای واقعی هر مقصد جداگانه بررسی خواهد شد.


## 2026-11-19 — راستی‌آزمایی عملیاتی پس از ادغام تعمیر صف ویدئو

**هدف:** ثبت شواهد production پس از ادغام PR #251 و تفکیک دقیق ارسال عمومی، submission در انتظار تأیید، پیمایش کاتالوگ و اندازه‌گیری فروش.

**تغییر/اقدام:**
- PR #251 با commit `52ae2e4af60690f090c6db07a6156339c766ffd0` ادغام شد؛ سه CI مربوط به Video Fan-out، Platform Logo Regression و Documentation Gate روی PR سبز بودند.
- maintenance صف Aparat در اجرای #44401294845 تعداد ۹۹۲ stale را terminal کرد؛ اجرای #44401641439 یک ویدئوی محصول را با visibility عمومی منتشر کرد.
- maintenance یوتیوب در اجرای #44401453230 تعداد ۹۷۳ stale را terminal و ۲۲ رکورد تازه را requeue کرد. در سه اجرای ویدئویی مجموعاً شش Shorts با URL عمومی ثبت شدند؛ شناسه‌ها و URLها در Handbook درج شده‌اند.
- maintenance فیلو در اجرای #44401649144 تعداد ۶۸۶ stale را terminal کرد. یک ویدئو به فیلو submit شد اما فقط `submitted_pending_approval` است؛ انتشار عمومی اثبات نشده است.
- اسکن دیجی‌کالا در اجرای #44403171521 تعداد ۱٬۲۰۱ صفحه و ۲۳٬۷۷۵ ردیف محصول را در سه batch پردازش کرد؛ ۵۵۹ دستهٔ برگ وجود دارد اما چرخهٔ جاری کامل نشده است.
- گزارش عملکردِ آخرین snapshot همچنان فاقد سفارش/فروش/کمیسیون قابل انتساب است؛ CTA مستقیم Aflo مسیر Worker را دور می‌زند.

**فایل‌ها/سامانه‌ها:** `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`؛ شواهد runtime از `affilio_radar/video_upload_dispatch_state.json`، `affilio_radar/catalog_sweep_status.json` و `affilio_radar/performance_report.json`؛ GitHub Actions runs #44400967721، #44400967774، #44400967797، #44401294845، #44401453230، #44401641439، #44401649144 و #44403171521.

**آزمون و نتیجه:** سه CI پیش از merge موفق شدند. پس از merge، workflowهای Aparat، YouTube و Filo هرکدام maintenance مقصدی را اجرا کردند؛ آپارات و یوتیوب رسیدهای عمومی ثبت کردند، فیلو submission در انتظار بررسی ثبت کرد. اسکن کاتالوگ نیز بدون خطای rate-limit در batch گزارش‌شده کامل شد، ولی چرخهٔ جامع هنوز ادامه دارد.

**شواهد/شناسه:** PR #251؛ merge commit `52ae2e4af60690f090c6db07a6156339c766ffd0`. نمونهٔ عمومی Aparat: https://www.aparat.com/v/dim4054. نمونه‌های عمومی YouTube و وضعیت Filo در Handbook ثبت شده‌اند.

**ریسک/بازگشت:** `submitted_pending_approval` در Filo نباید به‌عنوان انتشار عمومی یا دلیل retry تلقی شود. کاتالوگ هنوز پیمایش کامل جاری ندارد. گزارش عملکرد آخرین نسخهٔ مشاهده‌شده قدیمی و انتساب سفارش/کمیسیون unavailable است؛ هیچ نرخ تبدیل یا درآمدی از کلیک استنباط نمی‌شود. rollback تعمیر صف با revert PR #251 ممکن است، اما stale pendingها می‌توانند دوباره صف تحریریه را مسدود کنند.

**وضعیت:** کد تعمیر صف در `main` فعال و اثر آن در workflowهای زنده تأیید شده است. آپارات و یوتیوب نمونه‌های انتشار عمومی دارند؛ فیلو فقط submission در انتظار تأیید دارد. اتصال دیما، Eitaa و انتساب رسمی خرید/کمیسیون همچنان فعال نشده‌اند.
## ۲۰۲۶-۱۱-۱۹ — جلوگیری از dispatch زودهنگام ناشر در فاصلهٔ مشترک کانال

**هدف:** جلوگیری از فراخوانی‌های بی‌نتیجهٔ GitHub Actions وقتی نوبت محصول/تحریریه طبق timestamp برنامه‌ریزی‌شده رسیده، اما فاصلهٔ سخت مشترک از آخرین انتشار واقعی کانال هنوز کامل نشده است.

**مشاهده:** Worker ابری فقط timestamp صف و midpoint تحریریه را می‌سنجید؛ ناشر Python سپس اجرای زودهنگام را با `PUBLISHER_SHARED_CHANNEL_SPACING_GUARD` متوقف می‌کرد. در نتیجه Worker می‌توانست Workflow را در هر tick دوباره dispatch کند، بدون آنکه نوبت انتشار قابل اجرا باشد.

**تغییر/اقدام:** `nextPublisherDueAt` اکنون زمان برنامه‌ریزی‌شده را با `last_channel_published_at + 31 minutes` مقایسه می‌کند و زمان دیرتر را مبنای dispatch قرار می‌دهد. در نبود زمان انتشار معتبر، رفتار قبلی حفظ می‌شود. حداقل ۳۱ دقیقه و فاصلهٔ متغیر ۳۱ تا ۴۷ دقیقه تغییر نکرده‌اند؛ ساعت برنامه‌ریزی، سقف روزانهٔ ۷۲ پست، سهمیهٔ ویدئو و گاردهای ضدتکرار نیز دست‌نخورده‌اند.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs` و همین changelog.

**آزمون و نتیجه:** تست جدید تأیید می‌کند نوبت محصول/تحریریه پیش از تکمیل ۳۱ دقیقه dispatch نشود و دقیقاً در مرز مجاز دوباره due شود. تست کامل Worker و بررسی Wrangler باید در GitHub Actions روی PR اجرا شود؛ تا دریافت نتیجه، موفقیت CI یا Deploy ادعا نمی‌شود.

**شواهد/شناسه:** PR #253؛ شاخهٔ `fix/offerchin-publisher-spacing-dispatch-guard-20261119`؛ اجرای واقعی ناشر #44455625622 در ۱۹ نوامبر، لاگ `PUBLISHER_SHARED_CHANNEL_SPACING_GUARD` با `remaining_seconds=1157` و `minimum_gap_seconds=1860`.

**ریسک/بازگشت:** در صورت ناقص یا قدیمی بودن timestamp آخرین انتشار، dispatch ممکن است به زمان دیرتری موکول شود؛ این محافظه‌کاری از ارسال زودهنگام جلوگیری می‌کند. rollback با revert همین تغییر Worker و تست انجام می‌شود؛ state، صف و رسیدهای عمومی نباید reset شوند.

**وضعیت:** تغییر در شاخهٔ مستقل آماده شده است؛ PR، CI و Deploy تولیدی هنوز تأیید نشده‌اند.

## ۲۰۲۶-۱۱-۱۹ — بی‌اعتبارسازی زمان تحریریهٔ منقضی در زمان‌بند

**هدف:** جلوگیری از dispatch تکراری ناشر به‌علت midpoint تحریریه‌ای که پیش از آخرین انتشار قطعی کانال برنامه‌ریزی شده و دیگر slot فعالی نیست.

**مشاهده:** پس از اصلاح فاصلهٔ مشترک، Worker هنوز در هر tick قدیمی‌ترین مقدار `next_editorial_planning_at` را انتخاب می‌کرد. در snapshot زندهٔ `2026-11-19T04:24:34Z`، این مقدار به `2026-11-18T03:07:19Z` تعلق داشت؛ درحالی‌که آخرین ارسال عمومی `2026-11-19T03:51:47Z` و slot بعدی محصول `2026-11-19T04:28:47Z` بود.

**تغییر/اقدام:** Worker midpoint را فقط در صورتی در محاسبهٔ next due می‌آورد که از آخرین ارسال قطعی کانال جدیدتر باشد. گیت Python نیز midpoint قدیمی‌تر/هم‌زمان با آخرین انتشار را نادیده می‌گیرد. صف بازیابی واقعی تحریریه مستقل باقی می‌ماند و از این فیلتر حذف نمی‌شود.

**فایل‌ها/سامانه‌ها:** `cloudflare/affilio-minute-dispatcher.js`، `cloudflare/affilio-minute-dispatcher.test.mjs`، `affilio_radar/publication_due_gate.py`، `affilio_radar/test_publication_due_gate.py`، handbook و changelog.

**آزمون و نتیجه:** تست Node سناریوی midpoint روز قبل را در برابر آخرین انتشار روز جاری و slot محصول آینده بازسازی می‌کند. تست Python نیز هم stale midpoint و هم midpoint معتبر پس از آخرین ارسال را می‌سنجد. نتیجهٔ CI و Deploy پس از PR ثبت خواهد شد؛ هنوز موفقیت آن‌ها ادعا نمی‌شود.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-stale-editorial-dispatch-timestamp-20261119`؛ sidecar زندهٔ `2026-11-19T04:24:34Z`؛ اجراهای ناشر #44457962647 و #44458078954.

**ریسک/بازگشت:** فقط midpointی که قبل از آخرین رسید کانال بوده از محاسبهٔ dispatch اصلی کنار می‌رود. مطلب تحریریهٔ واقعاً معوق باید در صف recovery مستقل ثبت شده باشد. rollback با revert تغییرات همین PR ممکن است؛ state/queue/receipt reset یا حذف نمی‌شود.

**وضعیت:** تغییر در شاخهٔ جداگانه قرار دارد؛ PR/CI/Deploy هنوز انجام نشده است.


## ۲۰۲۶-۱۱-۱۹ — اعمال واقعی فاصلهٔ موضوعی چهار‌ساعته برای محتوای تحریریه

**هدف:** جلوگیری از تکرار بیش‌ازحد یک موضوع در مطالب تحریریه، حتی وقتی شناسه و متن مقالهٔ بعدی متفاوت است؛ بدون متوقف‌کردن انتشار محصول.

**تغییر/اقدام:** انتخاب‌گر تحریریه اکنون جدیدترین زمان تحویل تأییدشده برای هر موضوع را از تاریخچه می‌خواند و تا پایان cooldown پیش‌فرض چهار ساعت، گزینه‌های همان موضوع را کنار می‌گذارد. مقدار صفر برای غیرفعال‌کردن صریح cooldown حفظ شده است. اگر موضوع جایگزین مناسبی وجود نداشته باشد، فقط slot تحریریه رد می‌شود؛ صف مستقل محصولات تغییر نمی‌کند. هیچ state، رسید یا پست زنده‌ای بازنویسی یا حذف نشد.

**فایل‌ها/سامانه‌ها:** `affilio_radar/editorial_content.py`، `affilio_radar/test_editorial_content.py`، `docs/CHANGELOG_FA.md`، `docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md`.

**آزمون و نتیجه:** دو آزمون رگرسیون برای مسدودبودن موضوع تکراری در ساعت سوم، مجازشدن پس از ساعت پنجم، و غیرفعال‌سازی صریح cooldown اضافه شد. نتیجهٔ CI شاخه پس از ایجاد PR در انتظار اجراست؛ تا ثبت نتیجه، تغییر در وضعیت آمادهٔ ادغام نیست.

**شواهد/شناسه:** شاخهٔ `fix/offerchin-enforce-editorial-topic-cooldown-20261119`؛ commit کد `801f1137839cf246226a209631221aeeb9eaaf0e`؛ commit آزمون `2bebaa357a38f9160dbd493c7cc406f97fc10a46`.

**ریسک/بازگشت:** اگر بانک محتوای تأییدشده فقط یک موضوع قابل‌استفاده داشته باشد، نوبت تحریریه تا آماده‌شدن موضوع دیگر منتشر نمی‌شود؛ انتشار محصول مستقل می‌ماند. rollback با revert همین تغییر کد انجام می‌شود؛ فایل‌های state و history نباید reset شوند.

**وضعیت:** پیاده‌سازی و آزمون‌های رگرسیون ثبت شدند؛ در انتظار CI و بازبینی PR.


## 2026-11-19 — آماده‌سازی انتساب تبدیل و کمیسیون افیلیو

**هدف:** ثبت فروش و کمیسیون تأییدشدهٔ افیلیو در OfferChin به‌صورت قابل اتکا؛ تفکیک کلیک از خرید و ایجاد مسیر امن برای postback.

**تغییر/اقدام:**
- مستندات رسمی Public Publisher API و Conversion Postback افیلیو بررسی و در راهنمای دسترسی ثبت شد. جست‌وجوی کاتالوگ نیازمند publisher_uid، media_uid و IP مجاز است؛ لینک affiliate_link باید بدون بازسازی پارامترهای امضاشده استفاده شود. aff_sub می‌تواند شناسهٔ رسانه/محصول را در postback بازگرداند.
- مسیر امن POST /postback/affilio به Worker موجود اضافه شد. دریافت فقط با secret اختصاصی X-Affilio-Token، اعتبارسنجی payload و ذخیرهٔ append-only انجام می‌شود.
- رویدادهای pending، approved و declined با idempotency بر پایهٔ conversion_id + status نگهداری می‌شوند. pending درآمد نهایی نیست؛ approved نیازمند payout معتبر و declined نیازمند payout صفر است.
- route تا تنظیم secret غیرفعال می‌ماند؛ هیچ CTA، لینک Aflo یا انتشار زنده تغییر نکرد. Product Search و دیما هنوز به‌دلیل شناسه‌ها/دسترسی‌های تأییدنشده فعال نشده‌اند.

**فایل‌ها/سامانه‌ها:** affilio_radar/affiliate-deal-radar-worker.js؛ affilio_radar/test_affiliate_deal_radar_worker.mjs؛ affilio_radar/AFFILIO_REPORTING_ACCESS.md؛ .github/workflows/affilio-postback-tests.yml؛ docs/OFFERCHIN_PROJECT_HANDBOOK_FA.md؛ Worker affiliate-deal-radar و KV binding CLICKS.

**آزمون و نتیجه:** تست syntax و postback روی PR #256، revision fe36490660d31367038af9ffce07ea1e40b47028، در Actions run #44577000547 موفق شد. اجرای نهایی Documentation Gate پس از ثبت این changelog در انتظار است؛ تا آن زمان عبور کامل CI ادعا نمی‌شود.

**شواهد/شناسه:** PR #256؛ شاخه docs/affilio-api-postback-integration؛ run تست postback #44577000547؛ commit آخر کد/تست fe36490660d31367038af9ffce07ea1e40b47028.

**ریسک/بازگشت:** رویدادهای تبدیل با prefix جدا در KV کلیک ذخیره می‌شوند و retention یک‌ساله دارند. افزایش مصرف KV باید پایش شود. تا زمان دریافت token رسمی و تأیید افیلیو هیچ تبدیل تولیدی دریافت نمی‌شود. توقف اضطراری با حذف secret AFFILIO_POSTBACK_TOKEN یا revert کد ممکن است؛ لینک‌های خرید و تاریخچهٔ انتشار حذف یا بازنویسی نمی‌شوند.

**وضعیت:** کد و تست اختصاصی موفق در PR باز؛ گیت مستندات منتظر اجرای دوباره؛ merge، deploy، ثبت webhook و ثبت فروش/کمیسیون واقعی هنوز انجام نشده‌اند.
