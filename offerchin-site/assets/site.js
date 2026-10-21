(() => {
"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const fa = new Intl.NumberFormat("fa-IR");
let products = [];
let lastFeedError = false;
function isActive(p) {
 const until = Date.parse(p.active_until || "");
 return Number.isFinite(until) && until > Date.now() && p.availability === "in_stock" && p.affiliate_url && p.image_url;
}
function esc(v) { return String(v ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch])); }
function toman(v) { return fa.format(Math.max(0, Math.round(Number(v) || 0))); }
function remaining(until) {
 const ms = Date.parse(until) - Date.now();
 if (!Number.isFinite(ms) || ms <= 0) return "مهلت امن خرید تمام شده";
 const minutes = Math.max(0, Math.floor(ms / 60000));
 const hours = Math.floor(minutes / 60), mins = minutes % 60;
 if (hours > 24) return "بیش از " + fa.format(Math.floor(hours / 24)) + " روز";
 if (hours > 0) return fa.format(hours) + " ساعت و " + fa.format(mins) + " دقیقه";
 return fa.format(minutes) + " دقیقه";
}
function buyUrl(raw) { try { const u = new URL(raw); return u.protocol === "https:" ? u.href : "#"; } catch { return "#"; } }
function card(p) {
 const id=esc(p.product_id), title=esc(p.title), img=esc(p.image_url), url=esc(buyUrl(p.affiliate_url)), until=esc(p.active_until);
 const detail="/products/"+encodeURIComponent(p.product_id)+"/";
 return '<article class="deal-card" data-product-id="'+id+'" data-active-until="'+until+'">'+
 '<a class="product-media" href="'+detail+'" aria-label="جزئیات '+title+'"><img src="'+img+'" alt="'+title+'" loading="lazy" decoding="async" onerror="this.style.display=\'none\';this.parentElement.classList.add(\'image-missing\')">'+
 '<span class="discount-badge">'+toman(p.discount_percent)+'٪ تخفیف</span></a><div class="product-body">'+
 '<h3 class="product-title"><a href="'+detail+'">'+title+'</a></h3><div class="price-block">'+
 '<div class="price-now">'+toman(p.current_price)+' <span class="currency">تومان</span></div>'+
 '<div class="price-old">قیمت قبلی: <s>'+toman(p.original_price)+' تومان</s></div>'+
 '<div class="saving">صرفه‌جویی '+toman(p.savings_toman)+' تومان</div></div>'+
 '<div class="deadline"><span aria-hidden="true">◷</span><span>فرصت امن خرید: <strong data-countdown="'+until+'">'+remaining(p.active_until)+'</strong></span></div>'+
 '<div class="card-actions"><a class="buy-link" href="'+url+'" target="_blank" rel="sponsored nofollow noopener noreferrer">مشاهده در دیجی‌کالا ↗</a>'+
 '<a class="details-link" href="'+detail+'">جزئیات پیشنهاد</a></div></div></article>';
}
function renderCatalog() {
 const grid=$("#offerGrid"); if(!grid) return;
 const search=($("#offerSearch")?.value||"").trim().toLocaleLowerCase("fa-IR");
 const sort=$("#offerSort")?.value||"score";
 let visible=products.filter(isActive);
 if(search) visible=visible.filter(p=>String(p.title||"").toLocaleLowerCase("fa-IR").includes(search));
 visible.sort((a,b)=>{
  if(sort==="discount") return (Number(b.discount_percent)||0)-(Number(a.discount_percent)||0);
  if(sort==="saving") return (Number(b.savings_toman)||0)-(Number(a.savings_toman)||0);
  return (Number(b.promo_score)||0)-(Number(a.promo_score)||0)||(Number(b.demand_score)||0)-(Number(a.demand_score)||0);
 });
 grid.innerHTML=visible.length?visible.map(card).join(""):'<div class="empty-state"><strong>'+(search?"پیشنهادی با این عبارت پیدا نشد":"فعلاً پیشنهاد فعالی نداریم")+'</strong>'+(search?"عبارت کوتاه‌تر یا نام دیگری را امتحان کنید.":"پیشنهادهای واجد شرایط به‌صورت خودکار در همین صفحه ظاهر می‌شوند.")+'</div>';
 const count=$("#offerCount"); if(count) count.textContent=fa.format(visible.length);
 const status=$("#feedStatus"); if(status&&!lastFeedError) status.textContent="نمایش "+fa.format(visible.length)+" پیشنهاد معتبر";
}
function deactivateDetail() {
 const content=$("#detailContent"), notice=$("#expiredNotice");
 if(content) content.hidden=true;
 if(notice) notice.hidden=false;
}
function updateDetail(p) {
 if(!document.body.dataset.productId) return;
 if(!p||!isActive(p)){deactivateDetail();return;}
 const content=$("#detailContent"), notice=$("#expiredNotice");
 if(content) content.hidden=false; if(notice) notice.hidden=true;
 const title=$("#detailTitle"), price=$("#detailCurrentPrice"), old=$("#detailOldPrice"), save=$("#detailSaving");
 const badge=$("#detailDiscount"), image=$("#detailImage"), buy=$("#detailBuy"), timer=$("#detailCountdown");
 if(title) title.textContent=p.title;
 if(price) price.textContent=toman(p.current_price)+" تومان";
 if(old) old.textContent=toman(p.original_price)+" تومان";
 if(save) save.textContent="صرفه‌جویی "+toman(p.savings_toman)+" تومان";
 if(badge) badge.textContent=toman(p.discount_percent)+"٪ تخفیف";
 if(image && image.src!==p.image_url) image.src=p.image_url;
 if(buy) buy.href=buyUrl(p.affiliate_url);
 if(timer){timer.dataset.countdown=p.active_until;timer.textContent=remaining(p.active_until);}
}
async function refreshFeed() {
 try {
  const response=await fetch("/products.json?v="+Date.now(),{cache:"no-store",credentials:"same-origin"});
  if(!response.ok) throw new Error("Feed HTTP "+response.status);
  const data=await response.json();
  if(!Array.isArray(data.products)) throw new Error("Invalid product feed");
  products=data.products;lastFeedError=false;renderCatalog();
  const id=document.body.dataset.productId;if(id) updateDetail(products.find(p=>p.product_id===id));
 } catch(error) {
  lastFeedError=true;
  const status=$("#feedStatus");if(status)status.textContent="اتصال به فهرست تازه برقرار نشد؛ پیشنهادها همچنان با زمان اعتبار محدود می‌شوند.";
  if(!products.length){try{products=JSON.parse($("#initialProducts")?.textContent||"[]");renderCatalog();}catch{}}
 }
}
function pruneAndUpdateTimers() {
 const now=Date.now();
 $$("[data-countdown]").forEach(n=>{const t=Date.parse(n.dataset.countdown||"");n.textContent=Number.isFinite(t)?remaining(n.dataset.countdown):"مهلت نامشخص";});
 if(!products.length){$$(".deal-card[data-active-until]").forEach(n=>{const t=Date.parse(n.dataset.activeUntil||"");if(!Number.isFinite(t)||t<=now)n.remove();});}
 else {
  const oldLength=products.length;products=products.filter(isActive);if(products.length!==oldLength)renderCatalog();
  const id=document.body.dataset.productId;if(id&&!products.some(p=>p.product_id===id))deactivateDetail();
 }
}
document.addEventListener("DOMContentLoaded",()=>{
 try{products=JSON.parse($("#initialProducts")?.textContent||"[]");}catch{products=[];}
 if(products.length){renderCatalog();updateDetail(products.find(p=>p.product_id===document.body.dataset.productId));}
 $("#offerSearch")?.addEventListener("input",renderCatalog);$("#offerSort")?.addEventListener("change",renderCatalog);
 refreshFeed();window.setInterval(refreshFeed,60000);window.setInterval(pruneAndUpdateTimers,15000);
});
})();