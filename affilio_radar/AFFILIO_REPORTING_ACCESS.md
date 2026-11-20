# دسترسی امن به API و گزارش‌های افیلیو — OfferChin

آخرین بازبینی مستندات رسمی عمومی: ۱۹ نوامبر ۲۰۲۶.

## تفکیک مهم: API کاتالوگ با API گزارش عملکرد یکی نیست

افیلیو اکنون یک **Public Publisher API مستند** دارد که برای دریافت کاتالوگ محصولات، قیمت زنده و لینک افیلیت استفاده می‌شود. این API به‌خودی‌خود جایگزین گزارش عملکرد ناشر نیست. در مستندات عمومی بررسی‌شده، endpoint برای واکشی تاریخچهٔ کلیک‌ها/سفارش‌ها یا گزارش مالی کامل ناشر پیدا نشد؛ اما **Conversion Postback** رسمی برای ارسال تغییر وضعیت تبدیل‌ها به سرور ناشر مستند شده است.

مراجع رسمی:
- مستندات اصلی: https://public.affilio.ir/api/public/docs/
- Products API: https://public.affilio.ir/api/public/docs/products
- Publisher Package: https://public.affilio.ir/api/public/docs/publisher-package
- Conversion Postback: https://public.affilio.ir/api/public/docs/postback
- پنل ناشران: https://publisher.affilio.ir/

## ۱) API عمومی کاتالوگ و لینک افیلیت

### جست‌وجوی محصولات

- endpoint: `GET https://public.affilio.ir/api/public/products`
- برای این endpoint هر دو پارامتر `publisher_uid` و `media_uid` الزامی‌اند؛ شناسه‌ها باید از تیم افیلیو دریافت شوند.
- مستندات می‌گوید درخواست‌ها باید از IPهای ازپیش‌تأییدشده (whitelisted) ارسال شوند.
- محدودیت اعلام‌شده: ۱۰۰ درخواست در دقیقه به‌ازای هر `publisher_uid`.
- صفحه‌بندی عادی حداکثر تا ۱۰٬۰۰۰ نتیجه را پوشش می‌دهد؛ برای صفحات عمیق باید از `cursor` برگشتی و همان `sort_by` استفاده شود.
- فیلترهای مستندشده شامل فروشگاه، دسته، نام/کد، موجودبودن، پروموشن، بازهٔ قیمت و مرتب‌سازی `best_selling` هستند.
- پاسخ محصول، فیلدهای `code`، `rrp_price`، `price_amount`، `price_discount`، `discount_percent`، `is_available`، `is_in_promotion`، `image_url` و `affiliate_link` را ارائه می‌کند.
- **قانون حیاتی:** لینک `affiliate_link` برگشتی را همان‌طور که افیلیو ساخته استفاده کن؛ پارامترهای امضاشده/رهگیری آن را بازسازی یا جایگزین نکن.

### قیمت زنده و فهرست فروشگاه/دسته

- `GET /api/public/categories` و `GET /api/public/advertisers` طبق مستندات عمومی نیاز به احراز هویت ندارند.
- `POST /api/public/products/prices` قیمت زندهٔ حداکثر ۱۰۰ کد محصول را در هر درخواست می‌دهد؛ این endpoint در Publisher Package به‌عنوان بدون نیاز به احراز هویت معرفی شده است.
- قیمت‌ها در واحد پولی کوچک اعلام می‌شوند؛ مستندات برای IRR مثال تومان را ذکر می‌کند. قبل از هر تبدیل یا نمایش، مقیاس و واحد پاسخ واقعی باید با نمونهٔ زنده تطبیق داده شود.

### برچسب‌گذاری کلیک و انتساب

- روی لینک برگشتی می‌توان `utm_source` و `utm_medium` را در سطح outer affiliate URL اضافه کرد. این برچسب‌ها برای ثبت منبع/کانال کلیک هستند و نباید در URL مقصد فروشگاه قرار گیرند.
- این دو UTM به‌تنهایی گزارش قابل واکشی ایجاد نمی‌کنند؛ مستندات صریحاً می‌گوید endpoint گزارش‌گیری برای این labelها ارائه نشده است.
- پارامتر رسمی `aff_sub` را می‌توان به لینک برگشتی افزود تا در Conversion Postback به سرور ناشر بازگردد. کاراکترهای مجاز `A-Z a-z 0-9 _ -` و سقف طول ۲۵۵ کاراکتر است.
- `aff_sub` و UTMها نباید لینک امضاشدهٔ افیلیو را خراب کنند. پارامترها باید با URL parser به query بیرونی اضافه شوند، نه با دستکاری رشته‌ایِ کور.

## ۲) Conversion Postback — مبنای ثبت فروش و کمیسیون

افیلیو می‌تواند پس از ثبت تبدیل و تغییر وضعیت آن، به endpoint HTTPS ناشر درخواست `POST` بزند.

برای فعال‌سازی:
1. یک URL HTTPS تحت کنترل OfferChin به پشتیبانی افیلیو معرفی می‌شود.
2. افیلیو توکن مشترک `X-Affilio-Token` را تحویل می‌دهد.
3. توکن فقط به‌صورت Cloudflare Worker Secret نگهداری می‌شود؛ نه در Git، فایل عمومی، چت یا log.
4. endpoint فقط درخواست دارای توکن معتبر را می‌پذیرد و پس از ذخیرهٔ پایدار رویداد، پاسخ 2xx می‌دهد.

فیلدهای مستندشده:
- `conversion_id`: شناسه یکتای تبدیل
- `type`: `sale`، `lead` یا `action`
- `status`: `pending`، `approved` یا `declined`
- `timestamp`: زمان UTC
- `aff_sub`: در صورت استفاده در لینک
- `payout`: کمیسیون به تومان؛ در حالت pending ممکن است null باشد
- `amount` و `items`: برای sale

قواعد ضروری:
- `pending` فروش/کمیسیون قطعی نیست.
- فقط `approved` مبنای ثبت کمیسیون قطعی است.
- `declined` باید درآمد قبلی همان تبدیل را خنثی کند.
- کلید idempotency باید ترکیب `conversion_id + status` باشد؛ افیلیو ممکن است یک رویداد را چند بار ارسال کند.
- در صورت پاسخ غیر 2xx، retryهای مستندشده در ۱ دقیقه، ۵ دقیقه، ۳۰ دقیقه، ۲ ساعت و ۱۲ ساعت انجام می‌شود.
- دادهٔ postback، مرجع اصلی خرید/کمیسیون تأییدشده است؛ کلیک Worker یا بازدید کانال جای سفارش را نمی‌گیرد.

## ۳) محدودیت IP و زیرساخت بدون VPS

مستندات فعلی الزام allowlist IP را برای Product Search اعلام می‌کند. GitHub-hosted runner معمولی IP خروجی ثابت اختصاصی ندارد و نباید فرض کنیم IP هر اجرای workflow ثابت است. Cloudflare Dedicated Egress IP نیز قابلیت عادیِ رایگان Workers نیست و باید شرایط/هزینهٔ فعلی آن جداگانه بررسی شود.

بنابراین:
- فعلاً برای دورزدن allowlist از پراکسی ناشناس، VPN ناپایدار یا ثبت IP تصادفی در هر اجرا استفاده نکن.
- از پشتیبانی افیلیو کتبی بپرس آیا CIDRهای GitHub Actions، allowlist منعطف/چند IP، یا راهکار رسمی دیگری را می‌پذیرند.
- اگر راهکار بدون VPS و قابل‌قبول ارائه نشد، API Product Search را در production فعال نکن؛ لینک عمومی تأییدشدهٔ فعلی افیلیو را حفظ کن و از API قیمت/دسته/فروشگاه فقط در محدوده‌ای استفاده کن که شرایط دسترسی آن مجاز است.
- هیچ secret، publisher UID یا media UID را در مخزن عمومی ذخیره نکن.

## ۴) اقدام‌های پیگیری از پشتیبانی افیلیو

موضوع: فعال‌سازی Public Publisher API و Conversion Postback برای OfferChin

لطفاً این موارد را کتبی تأیید کنید:
1. `publisher_uid` و `media_uid` مربوط به رسانهٔ OfferChin چیست؟
2. آیا برای تلگرام، بله، یوتیوب و آپارات باید `media_uid` مجزا ثبت شود یا یک شناسه برای همه کافی است؟
3. چه روش IP allowlisting بدون VPS و بدون IP خروجی ثابت برای GitHub Actions/Cloudflare را می‌پذیرید؟ آیا CIDRهای رسمی GitHub-hosted runners قابل ثبت هستند؟
4. لطفاً URL و نمونهٔ درخواست رسمی `/api/public/products` و `/api/public/products/prices` را برای حساب ناشر ما تأیید کنید.
5. لطفاً مسیر ثبت HTTPS Conversion Postback، دریافت `X-Affilio-Token)، فیلدهای payload و امکان درج `aff_sub` در لینک اختصاصی OfferChin را فعال/تأیید کنید.
6. آیا امکان دریافت CSV یا API گزارش تاریخی کلیک، سفارش، لغو/مرجوعی و کمیسیون وجود دارد؟ UTMهای ثبت‌شده چگونه در پنل گزارش می‌شوند؟

## ۵) مسیر موقت تا دریافت پاسخ

1. لینک عمومی فعلی افیلیو را تغییر نده.
2. یک کلیک کنترل‌شده از هر رسانهٔ فعال ایجاد و زمان/محصول/رسانه را ثبت کن؛ کلیک آزمایشی را با خرید اشتباه نگیر.
3. گزارش پنل را برای ۳۰ و ۹۰ روز اخیر به‌صورت CSV/XLSX بگیر، اگر گزینهٔ خروجی دارد.
4. فایل گزارش را بدون رمز، کوکی، OTP یا توکن ضمیمه کن تا سفارش‌ها و کمیسیون‌ها با محصولات OfferChin تطبیق داده شوند.
5. پس از دریافت دسترسی رسمی، ابتدا روی چند محصول و یک رسانه پایلوت کن؛ سپس به کل کاتالوگ و رسانه‌های دیگر گسترش بده.

## ۶) دامنهٔ واقعی ردیاب داخلی OfferChin

ردیاب داخلی Cloudflare، رویدادهایی را که واقعاً از مسیر Worker عبور می‌کنند به تفکیک محصول و source ذخیره می‌کند و IP یا URL کامل افیلیو را نگه نمی‌دارد. اما مسیر CTA زندهٔ فعلی هنوز لینک مستقیم Aflo را باز می‌کند و از Worker عبور نمی‌کند. بنابراین آمار `/stats` فقط رخدادهای مسیر Worker را پوشش می‌دهد؛ نه تعداد کلیک واقعی دکمه‌های خرید یا فروش.

Worker sourceهای `telegram`، `bale`، `rubika`، `eitaa`، `youtube`، `aparat` و `filo` را می‌شناسد؛ این قابلیت به معنی فعال بودن redirect برای CTA زنده نیست.

تا زمان دریافت postback و ثبت سفارش واقعی، نرخ تبدیل یا کمیسیون به تفکیک رسانه را تخمین نزن. گزارش رسمی `approved` و `declined` مبنای سنجش درآمد خواهد بود.

---

## ممیزی وضعیت اجرایی و اتصال پنل — ۲۰ نوامبر ۲۰۲۶

این بخش از snapshot زندهٔ مخزن و Cloudflare تهیه شده و باید در تغییرات بعدی با شواهد جدید به‌روزرسانی شود.

### وضعیت مشاهده‌شده

- آخرین snapshot گزارش عملکرد بررسی‌شده: `2026-11-20T06:51:38Z`.
- در این snapshot، `live_purchase_link_mode=direct_affilio_link`، `live_purchase_click_tracking_enabled=false` و `live_purchase_source_attribution_available=false` است.
- مقادیر `orders`، `approved_commission`، `sales_amount`، `impressions` و `ctr` در گزارش موجود، `null` هستند؛ بنابراین گزارش فعلی هنوز مبنای محاسبهٔ EPC/EPM یا اعلام درآمد نیست.
- در Cloudflare Worker با نام `affiliate-deal-radar`، آخرین deployment مشاهده‌شده در `2026-11-19T17:41:30Z` بوده است. تنها binding مشاهده‌شده `CLICKS` از نوع KV است.
- نام Secretهای Worker در snapshot بررسی‌شده خالی بود؛ به‌طور مشخص `AFFILIO_POSTBACK_TOKEN` وجود نداشت. در نتیجه `POST /postback/affilio` با وضعیت 503 غیرفعال می‌ماند و هیچ ادعایی دربارهٔ دریافت Postback تولیدی مجاز نیست.
- پایگاه D1 موجود با نام `affiliate-deal-radar` دارای جدول‌های کاتالوگ/قیمت/تنظیمات است؛ در schema مشاهده‌شده جدول دفتر تبدیل وجود ندارد و این D1 به Worker فعلی نیز binding نشده است.
- در دو workflow اصلی بررسی‌شده، یعنی `.github/workflows/affilio-radar.yml` و `.github/workflows/affilio-publisher.yml`، مرحله‌ای برای ورود به پنل Affilio یا دریافت/پردازش خروجی مالی پنل مشاهده نشد. secretهای ارجاع‌شده در همین دو فایل نیز شامل credential آشکارِ پنل نبودند. این بررسی **وجود یا عدم وجود Secretهای دیگر در تنظیمات GitHub را اثبات نمی‌کند**؛ ابزار جاری امکان خواندن مقدار یا فهرست کامل GitHub Secrets را ندارد.
- پس باید ادعای «دسترسی پنل در GitHub وجود دارد» از «یک workflow فعال گزارش پنل را می‌خواند» تفکیک شود. مسیر مصرف عملیاتی credential هنوز نیازمند شناسایی دقیق و آزمون واقعی است.

### اقدام اجرایی لازم برای اتصال پنل

1. نام دقیق GitHub Secret/Variables و workflowای که آن را مصرف می‌کند از تنظیمات مخزن بررسی شود؛ مقدار secret هرگز چاپ یا echo نشود.
2. اگر دسترسی صرفاً برای login وب است، روش رسمی/مجاز خروجی CSV/XLSX یا API پنل مشخص شود. استفاده از scraping شکننده، دورزدن MFA، یا ذخیرهٔ cookie/session در فایل ممنوع است.
3. گزارش واقعی ۳۰ و ۹۰ روزه (در صورت موجودبودن) به‌صورت ورودی خصوصی دریافت شود. فایل خام و شناسه‌های حساس به مخزن عمومی commit نشوند؛ فقط گزارش aggregate و بدون دادهٔ شخصی/محرمانه در repository ثبت شود.
4. نام ستون‌ها، timezone، واحد پول و تعریف هر status با خود پنل تطبیق داده شود.
5. تعداد سفارش، مجموع مبلغ سفارش و مجموع payout هر وضعیت با پنل تطبیق داده شود؛ رکوردهای فاقد کلید تطبیق در گروه `unattributed` بمانند، نه اینکه به محصول یا رسانه‌ای حدس زده شوند.
6. پس از مشخص‌شدن روش دسترسی، workflow خودکار با least privilege و بدون چاپ credential ساخته شود. اگر پنل API یا export خودکار نمی‌دهد، ورود دستیِ ساختاریافته و امن بهتر از automation شکننده است.

### وضعیت Postback و storage

کد receiver موجود است، اما secret تولیدی و ثبت URL در پنل افیلیو هنوز مشاهده/تأیید نشده‌اند. قبل از فعال‌سازی:
- endpoint عمومی HTTPS باید از سوی Affilio ثبت و token آن صادر شود؛
- token فقط در Cloudflare Worker Secret بماند؛
- schema دفتر تبدیل و binding پایدار D1 پیاده‌سازی و تست شود؛
- مسیر ذخیره‌سازی باید duplicate، status transition، رویداد دیررس و retry را پوشش دهد؛
- یک رویداد واقعی با گزارش پنل تطبیق داده شود.

**توقف امن:** تا پیش از اثبات end-to-end، Postback receiver یا گزارش داخلی نباید به‌عنوان منبع فروش قطعی معرفی شود. CTA خرید مستقل و مستقیم باقی می‌ماند.
 
---

## Secretهای پنل و ممیزی ورود read-only — ۲۰ نوامبر ۲۰۲۶

دو نام GitHub Secret برای ورود پنل معرفی شدند:
- `AFFILIO_USER`
- `AFFILIO_PASS`

workflow مستقل `.github/workflows/affilio-panel-readonly-audit.yml` این دو مقدار را فقط در environment همان step دریافت می‌کند. اسکریپت `affilio_radar/affilio_panel_audit.py`:
- فقط به `https://publisher.affilio.ir/` و login action دقیق `https://sso.digiwise.ir/realms/services/login-actions/authenticate` متصل می‌شود؛
- فقط یک تلاش login انجام می‌دهد و هیچ MFA/CAPTCHA یا challenge را دور نمی‌زند؛
- کوکی را فقط در حافظهٔ process نگه می‌دارد؛
- هیچ مقدار credential، cookie، token، HTML خام، مشخصات حساب، سفارش یا payout را چاپ، commit یا upload نمی‌کند؛
- فقط نتیجهٔ login، شمار assetها، وجود واژه‌های گزارش و routeهای هم‌مبدأِ پاک‌سازی‌شده را در log می‌نویسد؛
- از workflow artifact استفاده نمی‌کند.

**محدودیت فعلی:** این ممیزی هنوز خودش گزارش مالی را استخراج نمی‌کند؛ اول باید ورود واقعی و مسیرهای گزارش/فیلتر/خروجی در پنل شناسایی شوند. پس از موفقیت login، مسیر دریافت باید فقط از API/export رسمی یا قابلیت رسمی پنل پیاده‌سازی شود. اگر MFA، CAPTCHA یا تغییر SSO لازم باشد، عملیات امن متوقف می‌شود و نیاز به اقدام مجاز مالک حساب دارد.

مستند عمومی فعلی API افیلیو endpoint گزارش تاریخی کلیک/سفارش/کمیسیون ناشر را معرفی نمی‌کند؛ بنابراین تا مشاهدهٔ مسیر واقعی پنل، endpoint گزارش ساخته یا حدس زده نمی‌شود.
 
### اصلاح روش ورود — ۲۰ نوامبر ۲۰۲۶

در اجرای نخست GitHub Actions، هر دو Secret در دسترس بودند؛ اما GET سادهٔ `publisher.affilio.ir/` در HTML خام runner، فرم ورود را نداشت. برای حذف وابستگی به JavaScript مرورگر، ممیزی به OIDC Authorization Code + PKCE/S256 روی realm رسمی دیجی‌وایز تغییر یافته است:
- درخواست authorization با state و verifier تازه ساخته می‌شود؛
- فرم فقط وقتی به مقصد ثابت `sso.digiwise.ir/realms/services/login-actions/authenticate` ارسال می‌شود که host/path دقیقاً مطابق allowlist باشند؛
- callback فقط با host ثبت‌شدهٔ `publisher.affilio.ir` و state منطبق پذیرفته می‌شود؛
- token endpoint رسمی با code و verifier فراخوانی می‌شود؛
- access token، code، cookie و گزارش‌ها در log/artifact/repository قرار نمی‌گیرند.

این تغییر هنوز یک روش ورود در حال آزمون است؛ تا اجرای موفق workflow، احراز هویت یا دسترسی گزارش را تأییدشده تلقی نکن.

### نتیجهٔ اجرای واقعی ممیزی پنل — ۲۰ نوامبر ۲۰۲۶

GitHub Actions run `44696134790` ورود OIDC/PKCE را با هر دو Secret (`AFFILIO_USER` و `AFFILIO_PASS`) با موفقیت انجام داد. مسیرهای UI کشف‌شده:
- `/performance`
- `/performance/overview`
- `/performance/links`
- `/performance/products`

این‌ها مسیرهای صفحهٔ پنل هستند؛ هنوز endpoint API یا export مالی تأیید نشده‌اند. هیچ ردیف سفارش/کمیسیون دانلود یا چاپ نشده است و هیچ artifact خامی وجود ندارد. مرحلهٔ بعد باید با بررسی assetهای هم‌مبدأ و response schemaها، endpointهای رسمی را شناسایی کند و فقط پس از تعیین semantics، گزارش را بخواند.
