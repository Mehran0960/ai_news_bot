# راهنمای جامع و نقطهٔ بازیابی OfferChin

> **سند مرجع پروژه برای انسان و هر هوش مصنوعیِ ادامه‌دهندهٔ کار.** در صورت تعارض با READMEها یا دفترهای قدیمی، این سند مرجع سیاست اجرایی جاری است. آخرین به‌روزرسانی: ۶ نوامبر ۲۰۲۶.

> **قرارداد قطعی محصول (۶ نوامبر ۲۰۲۶):** بالاترین درصد تخفیف از میان محصولات تازه، زنده و واجدشرایط دیجی‌کالا انتخاب می‌شود؛ اما ابتدا گاردهای rolling 24h خانواده، برند و شباهت و کنترل‌های سخت قیمت/موجودی/لینک/ایمنی اعمال می‌شوند. اگر گزینهٔ بالاتر به‌علت هر یک از سه گارد تکرار رد شود، بالاترین گزینهٔ بعدیِ مجاز بررسی می‌شود. در درصد برابر، مبلغ صرفه‌جویی بیشتر مقدم است. تقاضا، فروش، محبوبیت، review، رتبهٔ پرفروش و قیمت تاریخی/مقایسهٔ بازار هیچ نقشی در رتبه یا eligibility ندارند. هر سه گارد ۲۴ساعته شرط واقعی انتشارند، نه telemetry و نه score رتبه‌بندی.

> **محدودهٔ ادعا:** تا وقتی صف pagination خالی، checkpoint تکمیل چرخه ثبت و پوشش shortlist/handoff اثبات نشده، عبارت دقیق «بالاترین تخفیفِ مشاهده‌شده و واجدشرایط» است؛ نه تضمین رتبهٔ جهانیِ تمام SKUها در همان لحظه. API عمومی DigiKala sort مستقیمِ بیشترین تخفیف ندارد.

> **ثبت تغییرات:** هر تغییر دستی در کد، تست، تنظیمات، workflow، Worker، secret/variable، سرویس بیرونی یا رویهٔ عملیاتی باید همراه به‌روزرسانی این handbook و یک ورودی جدید در [دفتر تغییرات](CHANGELOG_FA.md) ثبت شود. دفتر append-only است؛ مقدار محرمانه هرگز ثبت نمی‌شود. اجرای خودکار زمان‌بندی‌شده فقط از طریق شواهد run/log ثبت می‌شود، مگر اینکه تنظیم یا رفتار آن تغییر داده شود.

## 1. هویت، مأموریت و چشم‌انداز

- نام پروژه: **OfferChin / آفِرچین**.
- مخزن اصلی: `Mehran0960/ai_news_bot`، شاخهٔ `main`.
- مأموریت: پایش مستمر کاتالوگ عمومی دیجی‌کالا، کشف تخفیف‌های واقعی و انتخاب **بالاترین تخفیف‌های کل کاتالوگ** برای توزیع در همهٔ رسانه‌های متصل.
- معیار رتبه‌بندی جاری: **درصد تخفیف واقعی از بیشترین به کمترین؛ در درصد مساوی، مبلغ صرفه‌جویی از بیشترین به کمترین**.
- محبوبیت، تقاضا، تعداد نظر، رتبهٔ پرفروش، Google Trends، دسته، برند، تنوع، کلیک کانال و آمار رسانه نباید کالایی با تخفیف کمتر را بالاتر از تخفیف بیشتر قرار دهند.
- ترتیب discount-first در انتخاب زنده برقرار است؛ اما گاردهای مستقل rolling 24h خانواده، برند و شباهت در مرحلهٔ انتخاب نهایی/انتشار اعمال می‌شوند. candidate تکراری حذف و بالاترین گزینهٔ بعدیِ مجاز بررسی می‌شود. تکرار همان SKUِ بدون بهبود، همچنان طبق cooldown مستقل مهار می‌شود.
- هیچ حداقل تبلیغاتی ۵۰٪/۴۵٪/۴۰٪/۳۵٪ وجود ندارد. هر کاهش قیمت واقعی از ۱٪ به بالا امکان رقابت دارد.
- چشم‌انداز: یک خط لولهٔ مستقل از مقصد که کل کاتالوگ را اسکن کند، پیشنهادهای معتبر را بر اساس تخفیف مرتب کند و همان hand-off را به همهٔ مقصدهای فعال و آینده برساند.

## 2. تعریف اجرایی اسکن جامع

1. دریافت درخت دسته‌بندی عمومی دیجی‌کالا و شناسه‌های دسته‌ها.
2. شروع چرخه از **اولین دسته و صفحهٔ ۱**؛ cursor قدیمی ناقص و صف‌های قدیمیِ top-60 حتی اگر قبلاً initialized شده باشند، با شناسهٔ سیاست `all_categories_all_pages_v2` یک‌بار از نو seed می‌شوند.
3. ساخت صف پایدار صفحه برای صفحهٔ اول تمام دسته‌ها و سپس تمام صفحه‌های بعدی.
4. دنبال‌کردن تمام صفحه‌های اعلام‌شده در pagination API؛ هیچ سقف ۳ صفحه/۶۰ محصول یا سقف عمق ثابتی در مسیر موازی فعال وجود ندارد. مسیر قدیمی ترتیبی نیز اکنون همین قاعده را دارد.
5. اگر API تعداد صفحه‌ها را اعلام نکند، ادامهٔ صفحه‌به‌صفحه تا رسیدن به صفحهٔ خالی.
6. خطای شبکه، پاسخ خراب، timeout یا HTTP 429 صفحه را از صف حذف نمی‌کند؛ همان صفحه در اجرای بعد retry می‌شود.
7. پس از تمام‌شدن زنجیرهٔ همهٔ دسته‌ها، چرخهٔ تازه از دستهٔ اول/صفحهٔ اول آغاز می‌شود. دسته‌های جدید در refresh بعدی به صف افزوده می‌شوند.
8. درخواست API برای ترتیب دریافت از `sort=7` استفاده می‌کند که در پاسخ عمومی زنده «پرفروش‌ترین» است؛ این فقط ترتیب traversal است و هیچ اثری بر رتبهٔ انتشار ندارد. در پاسخ زندهٔ API بررسی‌شده در ۶ نوامبر، sort مستقیمی برای «بیشترین تخفیف» وجود نداشت. `BEST_SELLING_MAX_PAGES_PER_CATEGORY=3` فقط سقف سیگنال تشخیصی ۶۰ مورد اول پرفروش است و محدودیت crawler نیست. هیچ صفحه‌ای به‌دلیل رتبهٔ پرفروش حذف نمی‌شود؛ shortlist و انتخاب نهایی با درصد تخفیف نزولی و سپس saving نزولی مرتب می‌شوند.

### محدودیت فنی مهم

- API عمومی دیجی‌کالا تضمین رسمی نمی‌دهد که تمام SKUهای موجود را در هر لحظه و بدون نقص نشان دهد. گزارش سیستم باید دربارهٔ «تمام صفحه‌های قابل‌دسترسی و موفق ثبت‌شده» صحبت کند، نه ادعای اثبات‌نشدهٔ مشاهدهٔ تک‌تک کالاها در هر لحظه.
- ظرفیت workflow اسکن: حداکثر ۴۸۰ صفحه در هر اجرا؛ سقف درخواستی concurrency برابر ۱۶ worker است. مقدار اجرایی از سقف ذخیره‌شدهٔ تطبیقی آغاز می‌شود؛ batch بدون خطا یک worker به ظرفیت بعدی می‌افزاید، هر پاسخ 429 منفرد یک worker از ظرفیت بعدی کم می‌کند و سه یا بیش از سه پاسخ 429 آن را نصف می‌کند. شمار workerهای تخصیص‌یافته به batch از سقف پیشنهادی batch بعدی جدا ثبت می‌شود. Cloudflare Worker هر دقیقه وضعیت را می‌سنجد و فقط در حالت idle اسکن را dispatch می‌کند؛ زمان واقعی چرخه تابع latency و نرخ محدودسازی API است.
- sidecar کاندیداها حداکثر ۳٬۰۰۰ کارت برترِ دارای مشاهده در بازهٔ ۷۲ ساعت را نگه می‌دارد تا Git به انبار میلیون‌ها رکورد تبدیل نشود. **این سقف فقط shortlist ذخیره‌شده است، نه سقف اسکن.** بااین‌حال، تا وقتی آزمون نشان ندهد این shortlist هیچ نامزد برترِ دیررس/دسته‌های دیگر را حذف نمی‌کند، ادعای تضمین بیشترین تخفیف کل کاتالوگ کامل نیست. تاریخچهٔ دائمی قیمت/موجودی تک‌تک SKUها در این نسخه ذخیره نمی‌شود؛ برای آن در آینده storage مستقل مانند Cloudflare D1/R2 لازم است.

## 3. رتبه‌بندی و قواعد انتخاب

### ترتیب قطعی اجرا
1. کنترل‌های سخت محصول را اعمال کن: شناسه/URL، قیمت زنده، موجودی، تخفیف مثبت، لینک افیلیت، عنوان/تصویر، deadline و ایمنی.
2. گاردهای rolling 24h خانواده، برند و شباهت را روی تاریخچهٔ پایدار انتشار اعمال کن. محصول تکراری حذف می‌شود؛ هیچ fallback حق relax کردن این guardها را ندارد.
3. در میان گزینه‌های عبورکرده از هر دو مرحلهٔ قبل، discount_percent نزولی مرتب کن.
4. اگر درصد برابر بود، savings_toman نزولی.
5. اگر درصد و saving برابر باشند، ترتیب پایدار ورودی حفظ می‌شود؛ زمان، انقضا، محبوبیت یا هر signal دیگری tie-breaker نیست. انقضا فقط شرط اعتبار/قابلیت انتشار است.
6. کاندیدای پذیرفته‌شدهٔ یک batch نیز به تاریخچهٔ موقت افزوده می‌شود؛ بنابراین batch نمی‌تواند دو محصول با خانواده، برند یا شباهت مشمول guard را پشت‌سرهم تحویل دهد.

### مواردی که score یا tie-breaker نیستند
- رشد/تعداد نظر و امتیاز محصول.
- رتبهٔ پرفروش/پربازدید و سابقهٔ محبوبیت.
- Google Trends و گزارش‌های سالانهٔ بازار.
- دسته و retailer به‌عنوان score یا سهمیه‌بندی تنوع.
- برند و خانواده score رتبه نیستند، اما گاردهای مستقل ۲۴ساعته‌اند.
- شباهت معنایی عنوان score رتبه نیست، اما گارد ۲۴ساعته است.
- کلیک‌های OfferChin یا آمار بازدید رسانه.
- کف‌های تبلیغاتی ۵۰٪/۴۵٪/۴۰٪/۳۵٪.

### کنترل‌های سخت و ضروری انتشار

«فارغ از فیلترهای تقاضا و دسته‌بندی» به معنی انتشار اطلاعات غلط یا کالای ناموجود نیست. کنترل‌های صحت و ایمنی باقی می‌مانند:
- شناسه و URL معتبر محصول، عنوان قابل‌استفاده و تصویر قابل‌دریافت.
- موجودی و قیمت فعلی که در آخرین مرحله دوباره بررسی شده باشد.
- تخفیف مثبت واقعی بر مبنای قیمت فعلی و قیمت اصلی؛ حد محاسباتی حداقل ۱٪.
- لینک همکاری در فروش معتبر و قابل‌انتساب.
- آفر منقضی‌شده یا کالای ناموجود منتشر نمی‌شود.
- اقلام صراحتاً ممنوع/غیرمجاز یا ناقض محدودیت‌های ایمنی/حقوقی منتشر نمی‌شوند.
- ارسال تکراری همان پیشنهاد بدون تغییر مهار می‌شود. hand-off آخرین snapshot قیمت/قیمت اصلی/درصد تخفیف/موجودی را با fingerprint ثبت می‌کند. اگر fingerprint تغییر کند، کارت حتی پیش از پایان TTL دوباره وارد مسیر بررسی می‌شود؛ این قاعده حتی وقتی SKU از قبل در `discovery_queue` قرار دارد نیز اجرا می‌شود: اطلاعات لیست به‌روز، `next_check_at` پاک و بررسی زنده زودهنگام می‌شود. تغییر کارت فقط علامت نیاز به بررسی است و به‌تنهایی مجوز انتشار یا اثبات موجودی/قیمت نهایی نیست؛ بررسی عمیق صفحهٔ محصول همچنان مرجع تصمیم است. کارت بدون تغییر تا TTL دو روزه از deep-check تکراری مصون است. کارت‌های به‌تعویق‌افتادهٔ hand-off نیز fingerprint دارند؛ تغییر واقعی fingerprint می‌تواند انتظار retry را دور بزند، اما کارت بدون تغییر پس از زمان retry دوباره بررسی می‌شود. رکوردهای legacy فاقد fingerprint یک بار برای ساخت baseline عبور می‌کنند. پیشنهاد دارای بهبود واقعی قیمت/تخفیف می‌تواند حتی داخل cooldown انتشار دوباره رقابت کند. تحویل مقصدهای نیمه‌تمام همچنان duplicate نمی‌شود.

بنابراین: **بالاترین درصد تخفیف و سپس saving، فقط در میان گزینه‌های عبورکرده از کنترل‌های سخت و هر سه guard مستقل ۲۴ساعته.** گاردهای خانواده/برند/شباهت را دور نزن؛ تکرار همان SKU بدون بهبود و idempotency نیز مهار می‌شود.

**وضعیت پیاده‌سازی hand-off در main:** PR #77 با commit ادغام `b997cf88cf59f81e5605ccc49f879bd4ee9b9aa6` ادغام شد. تغییر fingerprint برای کارت‌های hand-offشده، SKUهای موجود در `discovery_queue` و رکوردهای deferred باعث recheck زودهنگام می‌شود؛ این تغییر فقط بررسی زنده را جلو می‌اندازد و گاردهای ۲۴ساعته و اعتبارسنجی سخت را دور نمی‌زند.

## 4. مسیر داده از کاتالوگ تا انتشار

`DigiKala category dictionaries`
→ `parallel_catalog_sweep.py` و صف پایدار صفحه‌ها
→ `catalog_sweep_candidates.json` (shortlist حداکثر ۳٬۰۰۰ کارت برتر اخیر)
→ `load_catalog_candidates_for_handoff` (batch حداکثر ۱۰۰ در هر hand-off)
→ `discovery_queue` و بررسی عمیق محصول با اولویت سراسری درصد تخفیف و مبلغ صرفه‌جویی
→ اعتبارسنجی قیمت/موجودی/markdown/affiliate
→ `select_discount_fallback_candidates` (درصد نزولی، سپس saving نزولی)
→ `content_delivery_queue`
→ `publisher.py` و آداپترهای مقصد.

کشف، انتخاب و تحویل جدا هستند. شکست یک مقصد نباید اسکن یا مقصدهای دیگر را متوقف کند. مقصد موفق دوباره ارسال نمی‌گیرد؛ مقصد ناموفق مستقل retry می‌شود.

## 5. رسانه‌ها و توسعهٔ آینده

Registry مرکزی: `affilio_radar/platform_registry.py`. مقصدهای فعلی: Telegram، Bale، YouTube و Aparat.

برای مقصد جدید:
1. نام و نوع رسانه در `PLATFORM_REGISTRY` ثبت شود.
2. آداپتر در publisher/uploader پیاده شود.
3. credential در GitHub Secrets/Vars ثبت شود؛ هیچ Secret در سند یا log درج نشود.
4. تست idempotency، retry، ثبت شناسه و استقلال خطاها اضافه شود.
5. همین handbook به‌روز شود.

**سیاست نگهداری YouTube:** کد OfferChin نباید ویدئوی YouTube را خودکار حذف یا private کند؛ guardهای قبلی این مسیرها را غیرفعال کرده‌اند. این سیاست در برابر حذف/محدودسازی توسط خود YouTube، صاحب حساب یا takedown بیرونی تضمین ایجاد نمی‌کند.

## 6. زمان‌بندی و ظرفیت جاری

- Worker زمان‌بندی: `cloudflare/affilio-minute-dispatcher.js`.
- Worker هر دقیقه بررسی می‌شود؛ scanner در هر tick، اگر اجرای قبلی آزاد باشد، dispatch می‌شود. Integrity Audit همچنان در offset مستقل پنج‌دقیقه‌ای اجرا می‌شود؛ Filo و publisher نیز زمان‌بندی مستقل دارند.
- Workflow اسکن: `.github/workflows/offerchin-digikala-catalog-sweep.yml`.
- برای کاهش سربار fetch تاریخچهٔ بزرگ مخزن، checkout اسکنر به ۲۰ commit اخیر محدود شده است. **آزمون واقعی پس از merge PR #80 موفق بود:** checkout در run `42188770582` از `08:36:43` تا `08:36:45.736 UTC`، حدود ۲٫۶۵ ثانیه طول کشید (در run پیشین `42188254294` با تاریخچهٔ کامل، حدود ۴۳ ثانیه). اسکن ۲۸۰/۲۸۰ صفحه را با ۷ worker، صفر retry و صفر 429 انجام داد؛ `git pull --rebase origin main` و push checkpoint نیز در تلاش اول موفق و `CATALOG_SWEEP_STATE_PERSISTED attempt=1` ثبت شد. منطق سه تلاش retry حفظ است. در صورت مشاهدهٔ شکست shallow-history در آینده، fetch-depth به ۰ برگردد.
- ظرفیت scanner: ۴۸۰ صفحه/اجرا، سقف درخواستی ۱۶ worker، backoff تطبیقی برای هر HTTP 429، retry پایدار و timeout برابر ۱۲ دقیقه؛ پوشش تمام دسته‌ها و صفحات و رتبه‌بندی تخفیف‌محور بدون تغییر حفظ می‌شوند.
- **Rollout واقعی Cloudflare در ۶ نوامبر ۲۰۲۶، ساعت ۰۸:۲۲:۲۱ UTC:** Worker `affilio-minute-dispatcher` با deployment ID `a20fdab9edea4cbaab00c2eecc9a0cba` به نسخهٔ dispatch یک‌دقیقه‌ایِ idle-only ارتقا یافت. cron همچنان `* * * * *` است؛ secret bindingهای `GITHUB_TOKEN` و `FILO_GITHUB_TOKEN` حفظ شدند و observability/logging روشن باقی ماند. slot پنج‌دقیقه‌ای Integrity Audit، Filo، publisher و ویدئوها تغییر نکرد. این Rollout هیچ اسکن هم‌زمانی ایجاد نمی‌کند؛ dispatch فقط پس از آزادشدن workflow و با قفل concurrency انجام می‌شود.
- **اولین اندازه‌گیری موفق پس از rollout:** run `42187132905` در ۶ نوامبر موفق شد؛ ۲۸۴/۲۸۴ صفحه، ۸ worker واقعی، صفر retry، صفر HTTP 429، ۵٬۶۷۳ ردیف محصول و ۲۸۳ صفحهٔ pending؛ job از `08:22:47` تا `08:24:16 UTC` یعنی ۸۹ ثانیه اجرا شد. صف لحظهٔ اجرا فقط ۲۸۴ صفحه داشت؛ بنابراین batch limit=۴۸۰ تنظیم شده بود اما هنوز batch کامل ۴۸۰تایی آزمایش نشده است. `completed_cycles=0` و چرخهٔ کامل هنوز تأیید نشده.
- **تأیید رفتار dispatch یک‌دقیقه‌ای:** پس از پایان job اول در `08:24:16 UTC`، Worker در tick بعدی run `42187536920` را در `08:25:11 UTC` dispatch کرد؛ فاصلهٔ بیکاری ۵۵ ثانیه بود. اجرای دوم نیز موفق شد: ۲۸۳/۲۸۳ صفحه، ۹ worker، صفر retry/429، ۵٬۶۴۹ ردیف محصول و ۲۸۲ صفحهٔ pending؛ job از `08:25:15` تا `08:26:27 UTC`، یعنی ۷۲ ثانیه طول کشید. در مجموع دو batch پس از rollout، ۵۶۷ صفحه را بدون retry/429 در ۱۶۱ ثانیهٔ کاری پردازش کردند؛ فاصلهٔ شروع batchها ۱۴۴ ثانیه بود. این هنوز آزمایش batch کامل ۴۸۰تایی نیست و full-cycle هم کامل نشده است.
- ناشر: `.github/workflows/offerchin-publisher.yml`; کشف با `--select-only` پست عمومی نمی‌فرستد؛ `publisher.py` صف تحویل را جدا پردازش می‌کند.
- حداقل فاصلهٔ Telegram/Bale حدود ۲۳ دقیقه و سقف فعلی ۷۲ پست در روز است. این cadence محدودیت مقصد است، نه فیلتر تخفیف.
- cadence فعلی YouTube/Aparat حدود ۳ ساعت و مسیر مستقل دارد. Aparat عمومی هنوز شرط deadline تأییدشدهٔ مخصوص خود را دارد.

## 7. فایل‌ها و وضعیت‌های حیاتی

| مسیر | نقش |
|---|---|
| `affilio_radar/catalog_sweep.py` | دریافت دسته‌ها، استخراج کارت‌ها و رتبه‌بندی تخفیف |
| `affilio_radar/parallel_catalog_sweep.py` | صف صفحه‌ها، concurrency، retry و آمار چرخه |
| `affilio_radar/catalog_sweep_state.json` | دسته‌ها، صف صفحه‌های مانده و آمار چرخه |
| `affilio_radar/catalog_sweep_candidates.json` | shortlist ۳٬۰۰۰ کارت اخیر برتر از نظر تخفیف |
| `affilio_radar/affilio_radar.py` | کشف، اعتبارسنجی و انتخاب discount-first |
| `affilio_radar/state.json` | صف کشف/انتشار و وضعیت مقصدها؛ `catalog_sweep_handoff.seen_ids` اثر انگشت قیمت/موجودی آخرین hand-off را نگه می‌دارد |
| `affilio_radar/content_delivery.py` | صف تحویل و وضعیت per-platform |
| `affilio_radar/platform_registry.py` | فهرست مرکزی مقصدها |
| `affilio_radar/publisher.py` | اعتبارسنجی نهایی و آداپترها |
| `cloudflare/affilio-minute-dispatcher.js` | dispatch زمان‌بندی‌شده |
| `.github/workflows/offerchin-digikala-catalog-sweep.yml` | اجرای scanner |
| `.github/workflows/offerchin-publisher.yml` | انتخاب و تحویل |

## 8. تست و اثبات عملیاتی

بعد از تغییر scanner:
```bash
python -m py_compile affilio_radar/catalog_sweep.py affilio_radar/parallel_catalog_sweep.py
python -m unittest affilio_radar.test_catalog_sweep affilio_radar.test_parallel_catalog_sweep -v
```

بعد از تغییر ranking/publisher:
```bash
python -m py_compile affilio_radar/affilio_radar.py affilio_radar/publisher.py
python -m unittest affilio_radar.test_affilio affilio_radar.test_selection_evidence affilio_radar.test_content_delivery -v
```

موفقیت نهایی فقط با نتیجهٔ واقعی GitHub Actions تأیید می‌شود. از لاگ‌ها این شاخص‌ها ثبت شوند: `pages_attempted`, `pages_ok`, `retries`, `rate_limited`, `pending_pages`, `cycle_categories_complete`, `cycle_categories_unqueryable`, `cycle_pages`، تعداد محصول‌ها و timestamp چرخه. ادعای full cycle فقط وقتی مجاز است که صف صفحه‌ها خالی شده و timestamp تکمیل ثبت شده باشد.

## 9. دفتر تغییرات و نقطهٔ ادامه

### ۴ نوامبر ۲۰۲۶ — تغییر به full-catalog / discount-first
- حذف سقف سه صفحه برای هر دسته؛ pagination تا پایان صفحه‌های اعلام‌شده/صفحهٔ خالی ادامه می‌یابد.
- مهاجرت صف اولیه به صفحهٔ اول همهٔ دسته‌ها؛ cursor قدیمی نیمه‌کاره دسته‌های قبلی را حذف نمی‌کند.
- حذف pruning صفحات عمیق و حفظ retryها.
- checkpoint پوشش دسته‌ها، صفحات موفق و کارت‌های بررسی‌شده.
- تغییر shortlist و رتبه‌بندی نهایی به درصد تخفیف نزولی، سپس مبلغ صرفه‌جویی.
- حذف تقدم demand/popularity و category/brand/family diversity cooldown از ranking.
- سیاست جدید `discount_first_catalog_v2` تا آخرین مرحلهٔ ناشر، demand یا price-comparison proxy را شرط انتشار نکند.
- پیشنهاد دارای بهبود واقعی می‌تواند با وجود پست قبلی دوباره رقابت کند؛ hand-off نیمه‌تمام دوباره ایجاد نمی‌شود.
- hand-off با fingerprint قیمت/موجودی تغییرها را فوری recheck می‌کند؛ کالاهای بدون تغییر دو روز از deep-check تکراری معاف می‌مانند.
- تغییر رتبه‌بندی ویدئو به تخفیف و saving؛ حذف demand/click از ranking.

### کارهای باقی‌مانده
- بررسی SHA commit و نتیجهٔ CI پس از rollout.
- بررسی لاگ اولین اجرای scanner جدید و تأیید retry/no-page-cap.
- تکمیل یک چرخهٔ واقعی و ثبت دسته‌های complete/unqueryable، صفحات/محصول‌ها و زمان چرخه.
- بررسی اینکه بالاترین تخفیف‌های مشاهده‌شده به deep-check و صف انتشار می‌رسند.
- برای تاریخچهٔ دائمی قیمت/موجودی هر SKU، طرح جداگانهٔ D1/R2 لازم است؛ این قابلیت هنوز پیاده نشده است.

## 10. دستور برای AI ادامه‌دهنده
1. ابتدا این handbook، آخرین commit `main` و آخرین Actions را بخوان.
2. سیاست جاری: **تمام صفحه‌های قابل‌دسترسی کاتالوگ + discount percentage DESC + savings DESC**.
3. به demand-first یا category diversity ranking برنگرد.
4. ادعای scan هم‌زمان real-time نکن؛ فقط صفحات موفق، retryها، pending و آخرین full-cycle را گزارش بده.
5. stock، live price، affiliate link، positive markdown و safety را دور نزن.
6. خطای یک مقصد نباید مقصدهای دیگر یا scanner را متوقف کند.
7. YouTube توسط کد خود OfferChin حذف/private نشود.
8. Secretها را در سند/کد عمومی/log ننویس.
9. هر تغییر را همراه تست، commit SHA، Actions run ID و نتیجهٔ دقیق در همین handbook ثبت کن.


### ۴ نوامبر ۲۰۲۶ — اصلاح ممیزی hand-off و شمارندهٔ چرخه
- fingerprint hand-off اکنون در کد اجرایی ذخیره می‌شود؛ قیمت جاری/اصلی، درصد تخفیف و وضعیت موجودی در صورت ارائهٔ صریح از API کارت، مبنای تشخیص تغییر هستند.
- تغییر fingerprint باعث recheck فوری می‌شود؛ کارت بدون تغییر تا TTL دو روزه از deep-check تکراری معاف می‌ماند. legacy record بدون fingerprint یک بار برای ایجاد baseline دوباره hand-off می‌شود.
- مقدار `completed_cycles` از سیاست top-60 قبلی به شمارندهٔ full-catalog تبدیل می‌شود؛ شمارندهٔ قدیمی حفظ و برچسب‌گذاری می‌شود، اما صف جاری و پیشرفت صفحات reset نمی‌شود.


### ۴ نوامبر ۲۰۲۶ — حذف تنوع دسته از مسیر بررسی عمیق
- مسیر فعال `select_discovery_records_for_check` اکنون صف مرتب‌شده را مستقیماً با معیار درصد تخفیف و مبلغ صرفه‌جویی برمی‌دارد؛ تابع قدیمی تنوع برای سازگاری/تست باقی مانده اما دیگر در این مسیر استفاده نمی‌شود.
- انتخاب پیشنهادهای Incredible Offers نیز ترتیب سراسری discount/savings را حفظ می‌کند و دیگر با سابقهٔ دسته/خانواده جابه‌جا نمی‌شود.
- تست رگرسیونِ صف بررسی عمیق اضافه و به workflow ناشر متصل شد.
- متن گزارش runtime، گزارش سیاست تقاضا و مقایسهٔ بازار اصلاح شد: demand، review/bestseller، trends، کلیک و market/history فقط telemetry هستند و شرط انتشار یا عامل رتبه‌بندی نیستند.
- کنترل‌های اجباری stock/live price، تخفیف واقعی ≥۱٪، لینک Affilio معتبر، عنوان/تصویر، deadline، جلوگیری از تکرار و ایمنی حفظ شدند.
- وضعیت CI و SHA نهایی commit پس از اجرا در همین سند ثبت می‌شود.


### ۴ نوامبر ۲۰۲۶ — هم‌راستاسازی دور تند و صف ویدئو
- شرط demand از تشخیص پیشنهاد فوری حذف شد؛ popularity/reviewها نمی‌توانند به انتشار سریع‌تر کمک کنند.
- فقط اولین پیشنهاد در رتبه‌بندی سراسری درصد تخفیف/مبلغ صرفه‌جویی اجازهٔ عبور از فاصلهٔ زمانی انتشار را دارد؛ پیشنهاد کم‌تخفیف‌تر با deadline نزدیک نمی‌تواند صف را دور بزند.
- صف مستقل تولید/آپلود ویدئوهای YouTube و Aparat نیز ابتدا بر اساس درصد تخفیف و مبلغ صرفه‌جویی مرتب می‌شود؛ پرچم تعمیر ویدئوی قدیمی فقط در حالت برابری این دو معیار tie-breaker است.
- تست‌های رگرسیون برای حذف demand از دور فوری، جلوگیری از سبقت پیشنهاد کم‌رتبه و اولویت تخفیف در صف ویدئو اضافه شدند.
- مسیر عادی photo/video همچنان همان محصول منتخب اصلی را به مقصدهای مستقل تحویل می‌دهد؛ cadence و quota هر پلتفرم مستقل باقی می‌ماند.


### ۴ نوامبر ۲۰۲۶ — حذف سقف قدیمی از اسکن ترتیبی
- سقف `MAX_PAGES_PER_CATEGORY=3` از مسیر legacy اسکن ترتیبی حذف شد؛ این مسیر نیز اکنون تا صفحهٔ پایانی اعلام‌شده یا صفحهٔ خالی ادامه می‌دهد.
- مقدار `BEST_SELLING_MAX_PAGES_PER_CATEGORY=3` فقط برای نگهداری سیگنال تشخیصی «۶۰ رتبهٔ اول پرفروش» باقی است و دیگر به محدودیت crawler تبدیل نمی‌شود.
- تست رگرسیون اضافه شد که اجرای اسکن ترتیبی را از صفحهٔ ۴ آغاز می‌کند و اثبات می‌کند همان صفحه fetch شده و cursor به صفحهٔ ۵ می‌رود.
- اجرای واقعی موازیِ ۴ نوامبر ۲۰۲۶: ۳۰۰/۳۰۰ صفحه موفق، ۵٬۸۸۴ کارت محصول، ۰ retry، ۰ HTTP 429، ۴٬۹۱۳ دسته، ۴٬۶۶۷ leaf category، ۲٬۲۷۶ دستهٔ تکمیل‌شده در چرخهٔ جاری، ۰ دستهٔ غیرقابل‌دسترسی و ۲٬۶۳۷ صفحهٔ در صف. چرخهٔ کامل هنوز تکمیل نشده است؛ این اعداد یک batch واقعی‌اند، نه پوشش نهایی کل کاتالوگ.
NaN

## 10. دستور برای AI ادامه‌دهنده
1. ابتدا [منشور پروژه](PROJECT_CHARTER_FA.md)، این handbook، [دفتر تغییرات](CHANGELOG_FA.md)، آخرین commit `main) و آخرین Actions را بررسی کن.
2. میان «هدف محصول»، «رفتار فعلی کد» و «کارِ برنامه‌ریزی‌شده» تمایز صریح بگذار؛ هیچ‌کدام را به جای دیگری گزارش نکن.
3. اسکن جامع یعنی ادامهٔ pagination همهٔ دسته‌ها و صفحه‌های قابل‌دسترسی با retry؛ تا وقتی صف خالی و checkpoint تکمیل ثبت نشده، ادعای full cycle نکن.
4. رتبه‌بندی زنده در میان گزینه‌های مجاز فقط discount_percent DESC و سپس savings_toman DESC است. هر سه گارد خانواده/برند/شباهت ۲۴ساعته باید در final selector اعمال شوند و هرگز با fallback relax نشوند. تست تغییر ranking باید block شدن در هر guard، انقضای guard پس از ۲۴ ساعت، انتخاب بهترین گزینهٔ بعدی، تکرار درون batch، exact-SKU cooldown و idempotency مقصدها را پوشش دهد؛ demand/value/diversity score رتبه نیست.
5. قیمت جاری، موجودی، لینک افیلیت معتبر، تخفیف واقعی، deadline و ایمنی را دور نزن.
6. خطای یک مقصد نباید مقصدهای دیگر یا scanner را متوقف کند؛ ارسال موفق نباید دوباره ارسال شود.
7. YouTube توسط کد خود OfferChin حذف/private نشود.
8. لینک رسمی دریافتی از API افیلیو را در صورت پیاده‌سازی، بدون دستکاری پارامترهای امضاشده مصرف کن؛ API را تا تأیید whitelist، media UID و قرارداد لینک، منبع فعال انتشار نکن.
9. Secretها، توکن، کوکی، لینک‌های حاوی شناسهٔ حساس یا دادهٔ خصوصی ناشر را در کد/سند عمومی/log ننویس.
10. هر تغییر فنی یا عملیاتی را طبق [سیاست مستندسازی](CHANGELOG_FA.md) ثبت کن؛ PR باید از Documentation Gate عبور کند.
11. ادعاهای موفقیت فقط با شواهد واقعی Actions، شناسهٔ پست منتشرشده یا پاسخ معتبر سرویس پذیرفته‌اند؛ سبز بودن یک workflow به‌تنهایی اثبات انتشار عمومی نیست.

## 11. حاکمیت مستندات و تغییرات
- هر فایل trackشده در مخزن، از کد و workflow تا config، asset و مستندات، مشمول الزام مستندسازی است؛ تنها `docs/CHANGELOG_FA.md` به‌صورت append-only با کنترل جداگانه بررسی می‌شود. بنابراین افزودن مسیر/ماژول جدید هم از Gate عبور می‌کند و خارج از پوشش نمی‌ماند.
- اجرای زمان‌بندی‌شدهٔ عادی که فقط فایل‌های state/candidate/report مشخص‌شده را تغییر می‌دهد، به‌علت `paths-ignore` اجراهای بی‌فایدهٔ Gate ایجاد نمی‌کند؛ اما PR دستی که همان فایل‌ها را تغییر دهد، الزام مستندسازی دارد.
- دفتر تغییرات append-only است؛ Gate بازنویسی/حذف سوابق قبلی را رد می‌کند، تاریخ جدید و همهٔ فیلدهای لازم را می‌سنجد و حذف فایل‌های پروژه را هم تغییر محسوب می‌کند. تغییر handbook، منشور، README، الگوی PR، source، config، assets و workflowهای OfferChin نیز مشمول مستندسازی است. اجرای زمان‌بندی‌شدهٔ عادی که فقط state/cursor تولید می‌کند، از طریق Actions ردیابی می‌شود؛ ویرایش دستی آن stateها داخل PR مشمول Gate است. هر ورودی باید هدف، اقدام، فایل‌ها، آزمون/نتیجه، شواهد و ریسک/روش بازگشت داشته باشد.
- stateهای تولیدشده مانند `state.json`، `*_state.json`، `*_candidates.json` و `*_report.json` از الزام ثبت تک‌به‌تک مستثنا هستند؛ اجرای عملی آن‌ها باید در Actions ثبت شود و تغییر دستی‌شان مشمول مستندسازی کامل است.
- تغییر workflow، تنظیم secret/variable، تنظیم Worker یا تغییر پنل افیلیو نیز تغییر عملیاتی محسوب می‌شود و باید با شناسهٔ اجرا و بدون افشای مقدار محرمانه ثبت شود.
- PR باید از `OfferChin Documentation Gate` عبور کند. برای جلوگیری قطعی از bypass با push مستقیم، باید در تنظیمات GitHub شاخهٔ `main`، همین check به‌عنوان Required status check تعیین و direct push محدود شود. این تنظیم branch protection را از اتصال فعلی نمی‌توانم تأیید/تغییر دهم؛ وضعیتش در منشور به‌عنوان نیاز مدیریتی ثبت شده است.


در منشور، بخش ۱۱ خط زمانی نقاط عطف، تصمیم‌های تاریخی، وضعیت رتبه‌بندی و موارد باز را یک‌جا ثبت می‌کند. هنگام ادامهٔ کار، این خط زمانی را همراه دفتر append-only بخوانید؛ برای تاریخ دقیق هر اقدام، PR/commit و اجرای Actions همان اقدام مرجع است.


## 12. سابقهٔ Shadow ranking — ۵ نوامبر ۲۰۲۶ (تاریخی و superseded)

- تابع selection_policy_shadow_sort_key در آن تاریخ ترتیب آزمایشی demand/value را محاسبه می‌کرد و فقط log می‌نوشت؛ خروجی آن هیچ تغییری در انتخاب زنده ایجاد نمی‌کرد.
- نمونهٔ واقعی run 42073608036: تعداد ۷۴ کاندیدا، ۶ مورد دارای سیگنال تقاضای تازه و صفر مورد دارای شواهد مستقل ارزش؛ پنج گزینهٔ اول live و shadow متفاوت بودند و top-1 نیز تغییر می‌کرد.
- همان نمونه ۴۳ family-deferred، چهار similarity-deferred و صفر brand-deferred را نشان می‌داد؛ Torob پاسخ HTTP 490 ضدربات داد و دادهٔ مقایسهٔ مستقل فراهم نشد.
- queued=0 و publisher_invoked=false بود؛ آن اجرا هیچ انتشار عمومی‌ای را اثبات نکرد.
- نتیجه: Shadow صرفاً یک آزمایش تاریخی بود. تصمیم قطعی ۶ نوامبر آن را برای رتبه‌بندی کنار گذاشت؛ این کد/لاگ فقط برای traceability نگهداری می‌شود و نباید به‌عنوان roadmap demand-first یا rank زنده تعبیر شود.

## 13. وضعیت و تصمیم نهایی — ۶ نوامبر ۲۰۲۶

### تغییر اجرایی ادغام‌شده در main
- PR #75 ادغام‌شده در `main`؛ merge commit: `36367fe4df27b33ab01ed155adc0d03b557c7fb9`. شاخهٔ کاری: `docs/discount-first-charter-and-operating-rules-2026-11-06`.
- PR #75 به‌طور موقت guardها را telemetry-only کرده بود؛ PR #76 با merge commit `49b13f486d6412806c0c35d74c039c3b7d7cb9bc` آن را supersede کرد و guard واقعی rolling 24h برای خانواده/برند/شباهت را به main برگرداند. کاندیدای تکراری رد و رتبهٔ بعدیِ مجاز انتخاب می‌شود.
- آزمون‌های affilio_radar/test_affilio.py در PR #75 موقتاً انتظار telemetry-only را تثبیت کردند؛ اصلاحیهٔ PR #76 این دو انتظار را معکوس و تست‌های جدید ۲۴ساعته برای family/brand/similarity، آزادشدن پس از ۲۴ ساعت و batch داخلی اضافه می‌کند.
- کنترل تکرار همان SKUِ بدون بهبود، hand-off فعال، ارسال تکراری مقصد، قیمت/موجودی، لینک، deadline و ایمنی دست‌نخورده‌اند.
- merge commit نهایی: `49b13f486d6412806c0c35d74c039c3b7d7cb9bc`; source commit قبل از merge: `19405ca12bf2510f72ffa9bd16fa54877ec7e533`; test fixture commit: `5642211d8c5cabace63ab31d60e4f242268363a2`.

### شواهد اجرایی
- Catalog Sweep run 42167917939: pages_attempted=300، pages_ok=300، products=5986، workers=9، retries=0، rate_limited=0، pending_pages=321، candidates=3000.
- checkpoint: categories=4917، leaf_categories=4671، cycle_categories_complete=4597، cycle_categories_unqueryable=0، cycle_pages=159486، pages_total=286999، completed_cycles=0. ردیف‌های محصول الزاماً SKU یکتا نیستند و full-cycle هنوز اثبات نشده است.
- Integrity Audit run 42168017640: از ۱۵۸ مورد سررسیدشده فقط ۸ محصول بررسی قیمت شدند؛ پس نتیجهٔ «همهٔ پست‌ها تازه و تأییدشده‌اند» مجاز نیست. ۳۳۲ از ۳۴۴ deadline نیز unresolved ماند.
- بررسی API عمومی DigiKala در ۶ نوامبر: sort=7 پرفروش‌ترین است؛ sort مستقیمی برای بیشترین تخفیف وجود ندارد. رتبهٔ تخفیف باید پس از اسکن صفحات در سیستم محاسبه شود.

### مستندسازی و ادامهٔ کار
- منشور محصول، handbook فنی و changelog به تصمیم discount-first تغییر می‌کنند؛ سابقهٔ Shadow در بخش ۱۲ فقط برای traceability باقی است.
- اولویت باز: full-cycle، بررسی ۳٬۰۰۰ کاندیدا/TTL ۷۲ ساعت و اطمینان از hand-off نشدنِ نامزدهای برتر.
- PR #76 ادغام‌شده و guardهای ۲۴ساعته روی main فعال‌اند. CI مربوط به PR: Catalog Sweep run `42180472166`، Top-100/DigiPay run `42180472274` و Documentation Gate run `42180472333` همگی success؛ suite کامل Affilio Product Radar run `42180439592` نیز ۴۲۱ تست و ۲ skip را با نتیجه OK گذراند. full-cycle کاتالوگ همچنان اثبات نشده است.

## 14. تصمیم نهایی کاربر و اصلاح گاردها — ۶ نوامبر ۲۰۲۶

### قرارداد نهایی
- هدف: بالاترین تخفیف از کل محصولات قابل‌دسترسی دیجی‌کالا؛ در درصد برابر، مبلغ صرفه‌جویی بیشتر.
- **قید قطعی:** guard خانواده، برند و شباهت هرکدام ۲۴ ساعت باقی می‌مانند. آن‌ها score نیستند؛ veto eligibility هستند.
- ترتیب: صحت/ایمنی و قیمت زنده → family 24h + brand 24h + semantic similarity 24h → discount_percent DESC → savings_toman DESC.
- candidate مسدودشده را رد کن و بالاترین candidate بعدی را بررسی کن. اگر همهٔ candidateها مسدود یا نامعتبر شدند، هیچ پستی ارسال نشود. fallback حق عبور از guard را ندارد.
- candidate پذیرفته‌شدهٔ همان batch به guard history افزوده می‌شود تا دو پیشنهاد هم‌خانواده/هم‌برند/مشابه در همان batch قرار نگیرند.
- category diversity، تقاضا، فروش، review، bestseller و market/history، امتیاز یا veto نیستند.

### اصلاح فنی
- PR #75 در ۶ نوامبر family/brand/similarity را موقتاً به telemetry-only تبدیل کرده بود؛ کاربر با توضیح تکمیلی خواستار حفظ صریح هر سه guard ۲۴ساعته شد.
- در main پس از PR #76، تابع _filter_recent_publication_repeats هر سه گارد را enforce می‌کند؛ BRAND_REPEAT_COOLDOWN_HOURS از ۱۲ به ۲۴ افزایش یافته است؛ family و similarity نیز ۲۴ ساعت‌اند.
- آزمون‌ها پوشش می‌دهند: block شدن کاندیدای تکراری در هر یک از سه guard، آزادشدن پس از گذشت ۲۴ ساعت، انتخاب بهترین رتبهٔ بعدی، و جلوگیری از تکرار در یک batch.
- وضعیت main: PR #76 ادغام‌شده با commit `49b13f486d6412806c0c35d74c039c3b7d7cb9bc`. سه check اصلی PR موفق‌اند؛ Affilio Product Radar run `42180439592` نیز ۴۲۱ تست و ۲ skip را با موفقیت گذراند.

### تکمیل اصلاحیهٔ برند و آزمون‌های رگرسیون
- نرمال‌سازی brand در _publication_diversity_group اکنون idempotent است؛ brand slug ذخیره‌شده در publication history دوباره prefix نمی‌گیرد و با brand همان کاندیدا قابل مقایسه می‌ماند.
- expectationهای قدیمی که family/brand repeat را مجاز می‌شمردند به رفتار درست تغییر کردند: candidate تکراری رد و گزینهٔ بعدی انتخاب می‌شود. نام تست‌ها نیز با قرارداد guard ۲۴ساعته هم‌راستا شد.
- commits اصلاحی پیش از merge: source `19405ca12bf2510f72ffa9bd16fa54877ec7e533`، test fixture `5642211d8c5cabace63ab31d60e4f242268363a2`؛ merge commit نهایی `49b13f486d6412806c0c35d74c039c3b7d7cb9bc`.
- اجرای نخست پس از بازگرداندن guardها، ۱۲ failure در expectationهای قدیمی/تطبیق brand نشان داد؛ پس از اصلاح normalization برند و expectationها، suite نهایی ۴۲۱ تست و ۲ skip را با موفقیت گذراند.

### حفظ برند صریح در تاریخچهٔ پایدار
- `ensure_publication_ledger` اکنون `brand` و `brand_name` را از رکورد انتشار در ledger نگه می‌دارد.
- `ensure_recent_publications` برای ساخت رکورد history، نام برند صریح را همراه عنوان به `_publication_diversity_group` می‌دهد؛ بنابراین برندهایی که در متن عنوان نیامده‌اند نیز پس از بازسازی state برای guard ۲۴ساعته باقی می‌مانند.
- تست regression جدید ثابت می‌کند برند metadata-only پس از ledger/history rebuild هنوز candidate هم‌برند را block می‌کند و گزینهٔ بعدی با برند دیگر را انتخاب می‌کند.
- commits تکمیلی پیش از merge: source `19405ca12bf2510f72ffa9bd16fa54877ec7e533`، tests `e43ad9c33f1f6bc90aa29cda4743ab751c3d167f`.

- Regression fixture مربوط به حفظ brand metadata با شناسهٔ معتبر DigiKala (`dkp-123456`) اصلاح شد؛ شناسهٔ قبلی خارج از الگوی SKU بود و به‌درستی توسط ledger رد می‌شد. این اصلاح فقط fixture آزمون را تصحیح می‌کند. آخرین آزمون کامل: ۴۲۱ تست، ۲ skip، OK.

## 15. بازیابی اسکن کاتالوگ پس از اجرای یتیم GitHub Actions — ۶ نوامبر ۲۰۲۶

### تشخیص مستندشده
- Cloudflare Worker با Cron یک‌دقیقه‌ای فعال بود؛ telemetry نشان می‌داد invocationهای affilio-minute-dispatcher هر دقیقه اجرا می‌شوند.
- آخرین اجرای سالم مشاهده‌شدهٔ اسکن، run 42196432894، با موفقیت و مدت ۶۷ ثانیه تمام شده بود.
- اجرای بعدی، run 42196544516 (شمارهٔ workflow run برابر ۱۰۹۳، ساخته‌شده در 09:38 UTC)، در GitHub با وضعیت queued باقی ماند؛ endpoint مربوط به jobs برای آن آرایهٔ خالی برگرداند.
- تلاش Worker برای لغو آن به‌صورت مکرر با HTTP 409 و پیام Cannot cancel a workflow run that has not been queued yet شکست خورد. در نتیجه، guard بازیابی به‌جای dispatch بعدی روی رکورد یتیم متوقف می‌شد. این خطا مربوط به مدیریت وضعیت GitHub Actions است، نه خطای درخواست DigiKala یا پاسخ 429.
- اجرای یک‌دقیقه‌ای Cloudflare همچنان سالم بود؛ بنابراین نباید Cron، publisher یا زمان‌بندی مقصدها را برای رفع این مشکل دست‌کاری کرد.

### اصلاح کنترل‌شده روی شاخهٔ کاری
- گروه concurrency اسکن کاتالوگ به offerchin-digikala-catalog-sweep-v2 تغییر می‌کند تا run یتیم قدیمی، حتی در صورت باقی‌ماندن در GitHub، اسکن تازه را مسدود نکند.
- dispatcher فقط برای workflow اسکن کاتالوگ، پس از عبور از آستانهٔ stale، endpoint jobs را بررسی می‌کند. فقط اگر هیچ jobی برای run وجود نداشته باشد، رکورد به‌عنوان orphaned_no_jobs شناخته و از قفل dispatch کنار گذاشته می‌شود.
- برای publisher، integrity audit، YouTube، Aparat و Filo، سیاست قفل و بازیابی قبلی بدون تغییر باقی می‌ماند؛ رکوردهای قدیمی بدون بررسی job هیچ‌گاه مجوز عبور از قفل انتشار نمی‌گیرند.
- اجرای یتیم حذف نمی‌شود و ممکن است همچنان در صفحهٔ Actions دیده شود. تغییر concurrency group صرفاً مانع اثر آن بر اسکن جدید می‌شود؛ پاک‌سازی رکورد قدیمی، در صورت نیاز، موضوع جداگانهٔ پشتیبانی GitHub است.
- اسکنر اکنون زمان fetch موازی، پردازش/مرتب‌سازی محلی، نوشتن shortlist، نوشتن state، نرخ صفحه بر ثانیه و نرخ ردیف محصول بر ثانیه را در summary هر batch ثبت می‌کند. هیچ تغییری در all-categories/all-pages، retry، backoff، سقف عمق صفحه یا ترتیب تخفیف‌اول ایجاد نشده است.

### آزمون و rollout
- شاخهٔ کاری: fix/offerchin-orphaned-catalog-dispatch-2026-11-06.
- فایل‌های تغییرکرده: cloudflare/affilio-minute-dispatcher.js، .github/workflows/offerchin-digikala-catalog-sweep.yml، affilio_radar/parallel_catalog_sweep.py و affilio_radar/test_parallel_catalog_sweep.py.
- نتیجهٔ regression، syntax check، Documentation Gate، merge و استقرار Worker باید پس از اجرای PR ثبت شود؛ تا پیش از آن، اصلاح عملیاتی‌شده محسوب نمی‌شود.
- پس از merge، نسخهٔ جدید Worker باید با حفظ Cron یک‌دقیقه‌ای، secret bindingهای موجود، compatibility date، observability و logging منتشر شود. بعد از deploy، باید dispatch یک اجرای تازه، ایجاد حداقل یک job، persistence موفق cursor و کاهش خطاهای 409 تأیید شود.

### معیار موفقیت
- اجرای تازهٔ scanner بدون وابستگی به run 42196544516 آغاز شود و فقط یک batch اسکن فعال باشد.
- checkpoint جدید در catalog_sweep_state.json و catalog_sweep_candidates.json ثبت و push شود.
- full-cycle فقط با خالی‌شدن صف و ثبت timestamp تکمیل اعلام شود؛ عبور از اجرای یتیم به‌تنهایی به‌معنای تکمیل چرخه نیست.
- سرعت اسکن با سنجه‌های fetch/process/checkpoint مقایسه شود؛ افزایش سرعت بدون دادهٔ اندازه‌گیری‌شده ادعا نشود.


## 16. اصلاح نحوی Worker پس از validation Cloudflare — ۶ نوامبر ۲۰۲۶

- PR #82 با موفقیت در main ادغام شد و Regression Tests و Documentation Gate آن هر دو موفق بودند.
- تلاش نخست برای upload Worker در Cloudflare با HTTP 400 و validation error 10021 رد شد؛ خطا مشخصاً به عبارت regular expression در تبدیل مسیر workflow مربوط بود (Invalid regular expression flags). Cloudflare نسخهٔ جدید را نپذیرفت؛ بنابراین نباید ادعا کرد deployment جدید فعال شده است.
- عبارت route replacement در شاخهٔ اصلاحی به escaped slash استاندارد JavaScript تبدیل شده است. این اصلاح فقط نحوی است و رفتار مسیر API یا سیاست bypass فقط برای catalog workflowهای یتیمِ بدون job را تغییر نمی‌دهد.
- Worker فعال باید تا پس از گذر از Node syntax check و upload موفق، همان نسخهٔ قبلی با deployment ID a20fdab9-edea-4cba-ab00-c2eecc9a0cba باقی بماند. Cron، secret bindingها و observability نباید تغییر کنند.
- نتیجهٔ Node syntax check، Documentation Gate، upload و deployment جدید پس از اجرای PR ثبت خواهد شد.


## 17. ایزوله‌سازی قفل یتیم کاتالوگ و استقرار قابل‌تکرار Worker — ۶ نوامبر ۲۰۲۶

### تشخیص و تصمیم
- اجرای GitHub Actions شمارهٔ 1093، با run ID برابر `42196544516`، از ساعت 09:38 UTC در وضعیت `queued` مانده بود؛ endpoint مربوط به jobs برای آن هیچ jobی برنگرداند. اجرای زندهٔ scanner وجود نداشت.
- dispatcher فعال Cloudflare نسخهٔ 31 بود و در حالت قدیمی برای این run تلاش به cancel می‌کرد؛ GitHub پاسخ HTTP 409 با پیام `Cannot cancel a workflow run that has not been queued yet` می‌داد.
- برای اینکه این run یتیم نتواند دوباره چرخهٔ اسکن را قفل کند، concurrency group اسکن از `offerchin-digikala-catalog-sweep-v2` به `offerchin-digikala-catalog-sweep-v3` منتقل می‌شود. این تغییر فقط پس از تأیید نبود job فعال انجام می‌شود؛ اجرای یتیم قبلی را حذف نمی‌کند.
- کد موجود در main برای Worker، گزینهٔ `ignoreOrphanedNoJobs` را فقط برای workflow اسکن کاتالوگ فعال می‌کند. publisher، audit، YouTube، Aparat و Filo همچنان قفل محافظه‌کارانهٔ خود را دارند؛ این guard مجوز عبور از اجرای انتشار فعال نیست.

### مسیر استقرار Worker
- فایل `cloudflare/wrangler.toml` به‌عنوان تنظیمات نسخه‌پذیر Worker اضافه می‌شود: main module همان فایل dispatcher، compatibility date برابر 2026-10-17، Cron یک‌دقیقه‌ای، subdomain غیرفعال و observability/logging روشن.
- `keep_vars = true` از بازنویسی متغیرهای تعریف‌شده در Dashboard جلوگیری می‌کند. طبق مستندات Cloudflare، deployment با Wrangler Secretهای رمزنگاری‌شدهٔ موجود را حذف نمی‌کند؛ هیچ مقدار Secret در مخزن یا log قرار نمی‌گیرد.
- workflow جدید `.github/workflows/deploy-affilio-minute-dispatcher.yml` ابتدا dry-run و سپس deploy را از روی همین config انجام می‌دهد. به `CLOUDFLARE_API_TOKEN` با مجوز Workers Scripts Write و `CLOUDFLARE_ACCOUNT_ID` در GitHub Actions Secrets نیاز دارد.
- نسخهٔ Cloudflare شمارهٔ 34 با شناسهٔ `306990f4-1918-41b3-a476-8a817f54c352` فقط به‌عنوان نسخهٔ آماده‌سازی‌شده ایجاد شد؛ دو binding محرمانهٔ `GITHUB_TOKEN` و `FILO_GITHUB_TOKEN` را از نسخهٔ فعال 31 به ارث برده و **deploy نشده است**. نسخهٔ فعال در زمان ثبت این بند همچنان 31 است.
- تلاش‌های مستقیم API برای upload کد جدید با خطای validation 10021 و پیام `Unexpected token 'export'` در `worker.js:373` رد شدند؛ هیچ‌یک deployment تولید را تغییر ندادند. مسیر رسمی Wrangler در CI جایگزین این تلاش مستقیم شده است.

### وضعیت قبل از تأیید PR و rollout
- شاخهٔ کاری: `fix/offerchin-dispatcher-production-recovery-2026-11-06`.
- فایل‌های تغییرکرده در این مرحله: `.github/workflows/offerchin-digikala-catalog-sweep.yml`، `.github/workflows/deploy-affilio-minute-dispatcher.yml`، `cloudflare/wrangler.toml`، این handbook و `docs/CHANGELOG_FA.md`.
- تا زمانی که PR، Documentation Gate، dry-run، deployment Wrangler، حفظ Secret bindingها و Cron، dispatch یک run جدید و persistence موفق checkpoint تأیید نشده‌اند، اصلاح production را «مستقرشده» اعلام نکن.
- batch size برابر 480، سقف concurrency درخواستی 12، backoff تطبیقی، retry، پوشش تمام دسته‌ها/صفحات و رتبه‌بندی discount-first در این تغییر دست‌نخورده‌اند. اعداد throughput باید از اجرای واقعی بعد از rollout خوانده شوند؛ افزایش کورکورانهٔ workerها مجاز نیست.

### معیار موفقیت
1. run جدید در concurrency group v3 یک job واقعی ایجاد کند و شروع اسکن آن در GitHub Actions قابل مشاهده باشد.
2. deploy Wrangler نسخه‌ای از source فعلی Worker را با دو Secret binding و Cron یک‌دقیقه‌ای حفظ‌شده فعال کند.
3. Worker پس از پایان batch بعدی، بدون HTTP 409 اسکن بعدی را dispatch کند.
4. state و shortlist با موفقیت commit/push شوند؛ full-cycle فقط پس از خالی‌شدن صف و ثبت timestamp تکمیل اعلام شود.
5. با توجه به baseline آخر: 256 صفحه در 293.59 ثانیه، 8 worker واقعی، صفر retry/429، زمان fetch برابر 293.275 ثانیه، پردازش محلی 0.214 ثانیه و checkpoint حدود 0.089 ثانیه. گلوگاه فعلی درخواست شبکه است؛ tuning بعدی فقط بر مبنای چند batch کامل و نرخ واقعی 429 انجام شود.


## 18. رفع خطای dry-run مربوط به نوع ماژول Wrangler — ۶ نوامبر ۲۰۲۶

- اجرای PR validation شمارهٔ `42242605846` در مرحلهٔ dry-run شکست خورد؛ خطای واقعی Wrangler 4.158.0 برابر `Unexpected export` در `affilio-minute-dispatcher.js:373` بود. این بار خطا از API Cloudflare نبود؛ Wrangler فایل دارای `export default` را به‌علت پسوند `.js`، CommonJS فرض کرده بود.
- مطابق مستندات جاری Wrangler، برای تفسیر فایل `.js` به‌عنوان ES Module باید در config از rule صریح `ESModule` استفاده شود. به `cloudflare/wrangler.toml` یک rule با glob `**/*.js` افزوده شد؛ نام فایل canonical و همهٔ references موجود حفظ شدند و نیازی به کپی/تکثیر فایل سورس نیست.
- فایل تنظیمات اصلاح شده است؛ نتیجهٔ dry-run بعدی هنوز باید در PR جدید/به‌روزشده تأیید شود. تا آن زمان هیچ deployment تولید انجام نشده و Worker نسخهٔ 31 فعال باقی می‌ماند.
- آزمون مستقل catalog regression روی همان PR قبلاً موفق بود؛ Documentation Gate در حال اجرا بود. این خطای dry-run یک مشکل build/config است و هیچ ارتباطی با scanner، API دیجی‌کالا یا HTTP 429 ندارد.


## 19. راه‌حل نهایی entrypoint ماژول در Wrangler — ۶ نوامبر ۲۰۲۶

- اجرای بعدی PR validation، با وجود rule صریح `[[rules]] type = "ESModule"`، همچنان خطای `Unexpected export` در entrypoint دارای پسوند `.js` داد. بنابراین rule به‌تنهایی در build واقعی Wrangler 4.158.0 مشکل entrypoint این پروژه را حل نکرد.
- راه‌حل قطعی بدون تکثیر source در Git: فایل canonical همچنان `cloudflare/affilio-minute-dispatcher.js` است؛ CI قبل از هر dry-run و deploy آن را به فایل موقت `cloudflare/affilio-minute-dispatcher.mjs` کپی می‌کند. `cloudflare/wrangler.toml` اکنون main را روی همین `.mjs` قرار می‌دهد؛ فایل موقت فقط در runner ساخته می‌شود و به مخزن commit نمی‌شود.
- این راه، نام و مسیر منبع فعلی Worker را برای سایر referenceها حفظ می‌کند، از دو نسخهٔ مستقل کد جلوگیری می‌کند و Wrangler را با پسوند صریح ES Module اجرا می‌کند.
- نتیجهٔ dry-run پس از این اصلاح باید از run جدید PR خوانده شود. هیچ deployment تولیدی در دو تلاش قبلی انجام نشد؛ تا زمان تأیید اجرای جدید، نسخهٔ 31 production معتبر است.


## 20. استقرار مستقیم Worker مستقل بدون bundling — ۶ نوامبر ۲۰۲۶

- حتی پس از ساخت ورودی موقت `.mjs`، Wrangler 4.158.0 در bundling همچنان `Unexpected export` را گزارش کرد. پسوند mjs نیز به‌تنهایی برای این پروژه کافی نبود.
- سورس Worker بررسی شد: هیچ `import`، `require()` یا وابستگی npm ندارد و یک فایل JavaScript مستقل است. بنابراین config به `no_bundle = true` تغییر کرد تا Wrangler کد را بدون esbuild bundling مستقیماً بارگذاری کند؛ این قابلیت فقط برای Worker ساده و بدون وابستگی مناسب است.
- `.mjs` موقت و کپی از منبع canonical باقی می‌ماند تا نوع ES Module روشن باشد. نتیجهٔ dry-run بعد از این تغییر تنها معیار ادامه به deploy است؛ تا قبل از آن نسخهٔ production 31 پابرجاست.


## 21. علت ریشه‌ای واقعی خطای Syntax و بازیابی dispatch — ۶ نوامبر ۲۰۲۶

**اصلاح تشخیص قبلی:** توضیحات بخش‌های 18 تا 20 دربارهٔ پسوند فایل و bundling، فرضیه‌های آزموده‌شده بودند و علت اصلی را نشان نمی‌دادند. مقایسهٔ سورس main با کد واقعی نسخهٔ سالم Cloudflare #31 ثابت کرد که تابع `dispatchWorkflowIfIdle` در main پس از بلوک `orphaned_no_jobs` قطع شده بود: فراخوانی `POST /actions/workflows/{workflow}/dispatches` و آکولاد پایانی تابع حذف شده بود. به همین دلیل `export default` درون scope ناتمام قرار می‌گرفت و Wrangler خطای گمراه‌کنندهٔ `Unexpected export` می‌داد.

**اصلاح کد:** همان dispatch call و log پذیرش از نسخهٔ فعال #31 بازیابی شد؛ guard تازهٔ مخصوص run یتیمِ بدون job حفظ شد. برای وضعیت عادی و runهای واقعی، قفل strict برقرار است؛ فقط scanner پس از بررسی stale + صفر بودن jobها از رکورد یتیم عبور می‌کند. این guard در publisher، audit، YouTube، Aparat یا Filo فعال نیست.

**کنترل کیفیت:** سورس پس از درج اصلاح، در parser JavaScript (تبدیل export default به return در wrapper برای آزمون parse) معتبر شد. workflow CI اکنون علاوه بر Wrangler dry-run، اجرای `node --check` روی entrypoint موقت `.mjs` را قبل از dry-run و deploy دارد. نتیجهٔ authoritative همچنان باید از GitHub Actions PR جدید خوانده شود.

**وضعیت تولید:** تا زمان تأیید PR و اجرای deploy workflow، نسخهٔ فعال Cloudflare همان #31 است. این اصلاح هنوز مستقرشده اعلام نمی‌شود.


## 22. تثبیت شناسهٔ حساب Cloudflare در استقرار CI — ۶ نوامبر ۲۰۲۶

- پس از ادغام PR شمارهٔ 84، workflow استقرار روی main، بررسی وجود `CLOUDFLARE_API_TOKEN`، بررسی syntax و Wrangler dry-run را با موفقیت گذراند؛ اما مرحلهٔ deploy از API مسیر `/workers/services/affilio-minute-dispatcher` پاسخ `No access to the specified service` گرفت. بنابراین نسخهٔ production Worker تغییر نکرد و نسخهٔ 31 فعال ماند.
- اتصال مستقیم Cloudflare، حساب حاوی Worker را با شناسهٔ عمومی `10dc992b8d84b77f509975e21ce5499d` تأیید می‌کند. مقدار Secret با نام `CLOUDFLARE_ACCOUNT_ID` در GitHub قابل خواندن نیست؛ برای حذف احتمال عدم تطبیق آن، شناسهٔ عمومی و تأییدشده در `cloudflare/wrangler.toml` ثبت شد و ورودی accountId از Wrangler Action حذف شد تا config مرجع واحد باشد.
- فقط مقدار `CLOUDFLARE_API_TOKEN` به‌صورت Secret باقی می‌ماند. اگر deployment با حساب صحیح همچنان رد شود، محتمل‌ترین مانع بعدی permission توکن است؛ آن باید حداقل اجازهٔ ویرایش/انتشار Cloudflare Workers Scripts در همین حساب را داشته باشد. مقدار توکن هرگز در مخزن یا log چاپ نمی‌شود.
- تغییر روی شاخهٔ `fix/cloudflare-account-target-for-offerchin-dispatcher` و در PR جداگانه ثبت می‌شود. تا زمان عبور CI و مشاهدهٔ deployment با 100% ترافیک روی version جدید، Worker نسخهٔ 31 مرجع production باقی می‌ماند.


## 23. افزایش کنترل‌شدهٔ throughput اسکنر کاتالوگ — ۶ نوامبر ۲۰۲۶

### خط مبنا و تشخیص
- آخرین اجرای بررسی‌شدهٔ اسکنر، run شمارهٔ 1095 با شناسهٔ `42244114680` بود؛ ۲۵۶ صفحه از ۲۵۶ صفحهٔ batch با موفقیت پردازش و checkpoint در تلاش اول ثبت شد.
- زمان شبکه `256.836s` بود، درحالی‌که پردازش محلی `0.323s`، ذخیرهٔ بانک کاندید `0.103s` و ذخیرهٔ state فقط `0.028s` طول کشید. در آن snapshot تعداد ۲۵۵ صفحه باقی مانده و چرخهٔ کامل هنوز تأیید نشده بود.
- telemetry قبلی مقدار `parallel_workers_used` را پس از افزایش/کاهش ظرفیت بعدی می‌نوشت؛ بنابراین آن مقدار همیشه تعداد workerهای تخصیص‌یافته به batch جاری نبود. از این پس ظرفیت batch جاری و سقف پیشنهادی batch بعدی جدا ثبت می‌شوند.

### تغییرات
- سقف درخواستی workerها از ۱۲ به ۱۶ افزایش یافت؛ این سقف به معنی اجبار به استفادهٔ همیشگی از ۱۶ worker نیست. هر اجرا از مقدار ذخیره‌شدهٔ تطبیقی شروع می‌کند.
- پس از batch بدون retry/429، ظرفیت بعدی یک واحد افزایش می‌یابد. یک یا دو پاسخ HTTP 429 ظرفیت batch بعدی را یک واحد کاهش می‌دهد؛ سه یا بیشتر آن را نصف می‌کند. سقف ۱۶ و کف ۲ (جز در اجرای تک‌worker) رعایت می‌شود.
- سقف batch برابر ۴۸۰ صفحه، timeout دوازده‌دقیقه‌ای، صف durable، checkpoint صفحه‌ها، retry خطاهای موقت، پوشش تمام صفحه‌ها و رتبه‌بندی `discount_percent_desc,savings_toman_desc` تغییر نکرده‌اند.
- هیچ تغییری در dispatcher، Cloudflare secrets، publisher، زمان‌بندی کانال‌ها یا ترتیب رتبه‌بندی محصولات اعمال نشده است.

### وضعیت تأیید
- کد و تست‌های رگرسیون در شاخهٔ `perf/offerchin-catalog-throughput-20261106` آمادهٔ بررسی هستند.
- موفقیت تست‌های PR، ادغام در `main` و اندازه‌گیری سرعت batchهای بعدی هنوز باید از runهای واقعی GitHub Actions تأیید شود؛ افزایش سرعت تا زمان مشاهدهٔ دادهٔ جدید ادعا نمی‌شود.
