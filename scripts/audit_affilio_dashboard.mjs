import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";

const LOGIN_URL = "https://publisher.affilio.ir/";
const REPORT_WORDS = /گزارش|عملکرد|درآمد|فروش|کلیک|سفارش|آمار|کمیسیون|پورسانت|report|statistic|analytics|click|sale|order|commission|earning|income/i;
const EXCLUDED_PATH = /(openid|token|userinfo|auth|login|logout|session|csrf|refresh)/i;
const METRIC_KEY = /^(clicks?|click_count|total_clicks|sales?|sales_count|total_sales|orders?|orders_count|total_orders|commission|commission_amount|approved_commission|pending_commission|rejected_commission|total_commission|sales_amount|revenue|total_revenue|gmv|total_gmv|conversion_rate|ctr|impressions|visits|total_visits|approved_sales|cancelled_sales|rejected_sales)$/i;

const user = (process.env.AFFILIO_USER || "").trim();
const pass = process.env.AFFILIO_PASS || "";
const output = {
  created_at: new Date().toISOString(),
  portal: LOGIN_URL,
  authentication: "not_attempted",
  pages: [],
  report_links: [],
  api_responses: [],
  metric_observations: [],
  report_data: {
    dashboard_summary: null,
    wallet_summary: null,
    revenue_status: null,
    clicks_trend: [],
    revenue_trend: [],
    revenue_basket_trend: [],
    link_rows: [],
    link_analytics_total: null,
    link_analytics_total_is_capped: null,
    media_totals: [],
    top_earning_products: []
  },
  notes: [
    "Read-only diagnostic: login plus GET navigation and report-tab inspection only.",
    "No cookies, tokens, headers, usernames, account identifiers or full page bodies are stored.",
    "Income-basket and income-item counts are retained under their panel field names and are not re-labelled as confirmed orders."
  ]
};

function safePath(rawUrl) {
  try {
    const u = new URL(rawUrl);
    return { host: u.hostname, path: u.pathname };
  } catch {
    return { host: "invalid", path: "/" };
  }
}

function numericValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const normalized = value
      .replace(/[۰-۹]/g, d => "۰۱۲۳۴۵۶۷۸۹".indexOf(d))
      .replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d))
      .replace(/[٬,\s]/g, "");
    if (/^-?\d+(\.\d+)?$/.test(normalized)) return Number(normalized);
  }
  return null;
}

function val(obj, key) {
  return obj && typeof obj === "object" ? numericValue(obj[key]) : null;
}

function walkMetrics(value, parent = "", depth = 0) {
  if (!value || typeof value !== "object" || depth > 8 || output.metric_observations.length >= 180) return;
  if (Array.isArray(value)) {
    value.slice(0, 100).forEach(item => walkMetrics(item, parent, depth + 1));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (METRIC_KEY.test(key)) {
      const number = numericValue(child);
      if (number !== null) {
        output.metric_observations.push({ field: parent ? parent + "." + key : key, value: number });
      }
    }
    if (child && typeof child === "object") walkMetrics(child, parent ? parent + "." + key : key, depth + 1);
  }
}

function captureKnownMetrics(path, payload) {
  const d = payload?.data || {};
  if (path === "/api/v1/dashboard/summary-statistics") {
    output.report_data.dashboard_summary = {
      total_income_toman: val(d.total_income, "current_value"),
      income_basket_count: val(d.total_income_count, "current_value"),
      total_clicks: val(d.total_clicks, "current_value"),
      previous_total_income_toman: val(d.total_income, "previous_value"),
      previous_income_basket_count: val(d.total_income_count, "previous_value"),
      previous_total_clicks: val(d.total_clicks, "previous_value")
    };
  } else if (path === "/api/v1/users/me/wallet-summary") {
    output.report_data.wallet_summary = {
      finalized_income_toman: val(d, "finalized_income_amount"),
      wallet_balance_toman: val(d, "wallet_balance_amount")
    };
  } else if (path === "/api/v1/dashboard/statistics") {
    const normalizeTrend = rows => Array.isArray(rows) ? rows.map(x => ({
      date: typeof x.date === "string" ? x.date : null,
      approved_revenue_toman: val(x, "approved_revenue"),
      pending_revenue_toman: val(x, "pending_revenue"),
      bonus_revenue_toman: val(x, "bonus_revenue"),
      total_revenue_toman: val(x, "total_revenue")
    })) : [];
    output.report_data.revenue_status = {
      approved_revenue_toman: val(d.approved_revenue, "amount"),
      pending_revenue_toman: val(d.pending_revenue, "amount"),
      bonus_revenue_toman: val(d.bonus_revenue, "amount"),
      daily: normalizeTrend(d.daily_revenue),
      weekly: normalizeTrend(d.weekly_revenue),
      monthly: normalizeTrend(d.monthly_revenue)
    };
  } else if (path === "/api/v1/dashboard/clicks-trend" && Array.isArray(d.clicks_trend)) {
    output.report_data.clicks_trend = d.clicks_trend.map(x => ({
      date: typeof x.date === "string" ? x.date : null,
      total_clicks: val(x, "total_clicks")
    }));
  } else if (path === "/api/v1/dashboard/revenue-trend" && Array.isArray(d.revenue_trend)) {
    output.report_data.revenue_trend = d.revenue_trend.map(x => ({
      date: typeof x.date === "string" ? x.date : null,
      approved_revenue_toman: val(x, "approved_revenue"),
      pending_revenue_toman: val(x, "pending_revenue"),
      total_revenue_toman: val(x, "total_revenue")
    }));
  } else if (path === "/api/v1/dashboard/revenue-basket" && Array.isArray(d.revenue_basket)) {
    output.report_data.revenue_basket_trend = d.revenue_basket.map(x => ({
      date: typeof x.date === "string" ? x.date : null,
      total_income_baskets: val(x, "total_incomes")
    }));
  } else if (path === "/api/v1/links/analytics" && Array.isArray(d.items)) {
    output.report_data.link_analytics_total = val(d, "total");
    output.report_data.link_analytics_total_is_capped = d.total_is_capped === true;
    output.report_data.link_rows = d.items.slice(0, 200).map(x => ({
      link_uid: typeof x.link_uid === "string" ? x.link_uid : null,
      media_uid: typeof x.media_uid === "string" ? x.media_uid : null,
      media_name: typeof x.media_name === "string" ? x.media_name : null,
      publisher_name: typeof x.publisher_name === "string" ? x.publisher_name : null,
      link_title: typeof x.link_title === "string" ? x.link_title : null,
      title_is_fallback: x.title_is_fallback === true,
      advertiser_name: typeof x.advertiser_name === "string" ? x.advertiser_name : null,
      link_type: typeof x.link_type === "string" ? x.link_type : null,
      link_kind: typeof x.link_kind === "string" ? x.link_kind : null,
      utm_campaign: typeof x.utm_campaign === "string" ? x.utm_campaign : null,
      utm_content: typeof x.utm_content === "string" ? x.utm_content : null,
      click_count: val(x, "click_count"),
      income_items_count: val(x, "income_items_count"),
      total_income_toman: val(x, "total_income"),
      conversion_rate: val(x, "conversion_rate"),
      revenue_share_percentage: val(x, "revenue_share"),
      first_click_date: typeof x.first_click_date === "string" ? x.first_click_date : null,
      created_at: typeof x.created_at === "string" ? x.created_at : null
    }));
  } else if (path === "/api/v1/dashboard/top-earning-products" && Array.isArray(d.products)) {
    output.report_data.top_earning_products = d.products.slice(0, 30).map(x => ({
      product_code: typeof x.product_code === "string" ? x.product_code : null,
      product_name: typeof x.product_name === "string" ? x.product_name : null,
      advertiser_name: typeof x.advertiser_name === "string" ? x.advertiser_name : null,
      media_name: typeof x.media_name === "string" ? x.media_name : null,
      landing_url: typeof x.landing_url === "string" ? x.landing_url : null,
      total_earnings_toman: val(x, "total_earnings"),
      revenue_share_percentage: val(x, "revenue_share_percentage")
    }));
  }
}

function shapeOf(value, depth = 0) {
  if (depth > 3 || value === null || typeof value !== "object") return typeof value;
  if (Array.isArray(value)) {
    return { type: "array", length: value.length, item: value.length ? shapeOf(value[0], depth + 1) : null };
  }
  const keys = Object.keys(value).slice(0, 80);
  const shape = {};
  for (const key of keys) shape[key] = shapeOf(value[key], depth + 1);
  return shape;
}

function summarizeShape(value, prefix = "$", output = [], limit = 120) {
  if (output.length >= limit) return output;
  if (value && typeof value === "object" && value.type === "array") {
    output.push({ path: prefix, type: "array", length: value.length });
    if (value.item !== null && value.item !== undefined) {
      summarizeShape(value.item, prefix + "[]", output, limit);
    }
    return output;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) output.push({ path: prefix, type: "object" });
    for (const [key, child] of entries) {
      summarizeShape(child, prefix + "." + key, output, limit);
      if (output.length >= limit) break;
    }
    return output;
  }
  output.push({ path: prefix, type: String(value) });
  return output;
}

async function inspectExactVisibleText(page, label) {
  return page.evaluate(target => {
    const normalized = value => String(value || "").trim().replace(/\s+/g, " ");
    const elements = [...document.querySelectorAll("body *")]
      .filter(el => normalized(el.childElementCount === 0 ? el.textContent : "") === target)
      .filter(el => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      })
      .slice(0, 12);
    return elements.map(el => {
      let node = el;
      const ancestors = [];
      for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
        ancestors.push({
          tag: node.tagName.toLowerCase(),
          role: node.getAttribute("role") || "",
          tabindex: node.getAttribute("tabindex"),
          ariaSelected: node.getAttribute("aria-selected"),
          ariaCurrent: node.getAttribute("aria-current"),
          dataState: node.getAttribute("data-state"),
          hasOnclick: typeof node.onclick === "function",
          classTokens: String(node.className || "").split(/\s+/).filter(Boolean).slice(0, 5)
        });
      }
      return {
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        tabindex: el.getAttribute("tabindex"),
        ancestors
      };
    });
  }, label);
}

async function snapshotPage(page, label) {
  const info = await page.evaluate(() => {
    const text = el => (el.innerText || el.getAttribute("aria-label") || el.getAttribute("title") || "")
      .trim().replace(/\s+/g, " ").slice(0, 100);
    const headings = [...document.querySelectorAll("h1,h2,h3,[role=heading]")]
      .map(text).filter(Boolean).slice(0, 30);
    const controls = [...document.querySelectorAll("a[href],button,[role=menuitem],[role=tab]")]
      .map(el => ({
        label: text(el),
        href: el.tagName === "A" ? (() => {
          try {
            const u = new URL(el.href, location.href);
            return { origin: u.origin, pathname: u.pathname };
          } catch { return null; }
        })() : null,
        role: el.getAttribute("role") || ""
      }))
      .filter(x => x.label).slice(0, 150);
    const dateLabels = controls.map(x => x.label)
      .filter(x => /\d{1,2}\s*(مهر|آبان|آذر|دی|بهمن|اسفند|فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور)/.test(x));
    const tabs = [...document.querySelectorAll('[role="tab"],[role="tablist"] button,button[aria-selected],button[aria-current]')]
      .map(el => ({
        label: text(el),
        role: el.getAttribute("role") || "",
        selected: el.getAttribute("aria-selected"),
        current: el.getAttribute("aria-current"),
        disabled: Boolean(el.disabled)
      }))
      .filter(x => x.label).slice(0, 50);
    const tables = [...document.querySelectorAll("table")].slice(0, 20).map(table => ({
      headers: [...table.querySelectorAll("thead th,thead td")].map(text).filter(Boolean).slice(0, 30),
      body_row_count: table.querySelectorAll("tbody tr").length
    }));
    const grids = [...document.querySelectorAll('[role="grid"],[role="table"]')].slice(0, 10).map(grid => ({
      role: grid.getAttribute("role"),
      row_count: grid.querySelectorAll('[role="row"]').length,
      headers: [...grid.querySelectorAll('[role="columnheader"]')].map(text).filter(Boolean).slice(0, 30)
    }));
    return { title: document.title || "", pathname: location.pathname, headings, controls, dateLabels, tabs, tables, grids };
  });
  const reportLinks = [];
  for (const item of info.controls) {
    if (!REPORT_WORDS.test(item.label) && !REPORT_WORDS.test(item.href || "")) continue;
    if (!item.href || typeof item.href.pathname !== "string") continue;
    try {
      const target = new URL(item.href.pathname, item.href.origin);
      if (target.origin === "https://publisher.affilio.ir" && !EXCLUDED_PATH.test(target.pathname)) {
        reportLinks.push({ label: item.label, url: target.origin + target.pathname });
      }
    } catch {}
  }
  output.pages.push({
    label,
    url: safePath(page.url()),
    title: info.title,
    headings: info.headings,
    date_range_labels: info.dateLabels,
    controls: info.controls,
    tables: info.tables,
    interactive: info.interactive
  });
  output.report_links.push(...reportLinks);
}

if (!user || !pass) {
  output.authentication = "missing_github_secret";
  await writeFile("affilio-dashboard-diagnostic.json", JSON.stringify(output, null, 2));
  throw new Error("AFFILIO_USER_or_AFFILIO_PASS_secret_missing");
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ locale: "fa-IR", timezoneId: "Asia/Tehran" });
  const page = await context.newPage();
  const pendingCaptures = [];

  page.on("response", response => {
    pendingCaptures.push((async () => {
      const status = response.status();
      const path = safePath(response.url());
      const allowedHost = /(^|\.)affilio\.ir$/i.test(path.host) ||
        (/digiwise\.ir$/i.test(path.host) && !/^sso\./i.test(path.host));
      const contentType = (response.headers()["content-type"] || "").toLowerCase();
      if (!allowedHost || EXCLUDED_PATH.test(path.path) || !contentType.includes("application/json")) return;
      let payload;
      try { payload = await response.json(); } catch { return; }
      output.api_responses.push({ host: path.host, path: path.path, status, shape: shapeOf(payload) });
      captureKnownMetrics(path.path, payload);
      walkMetrics(payload);
    })().catch(() => {}));
  });

  await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.locator("#username").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#username").fill(user);
  await page.locator("#password").fill(pass);
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 45000 }).catch(() => null),
    page.locator('#kc-form-login button[type="submit"]').click()
  ]);
  await page.waitForTimeout(9000);

  const currentHost = safePath(page.url()).host;
  const otpVisible = await page.locator('input[autocomplete="one-time-code"],input[name*="otp" i],input[name*="code" i]').count().catch(() => 0);
  const loginFormVisible = await page.locator("#kc-form-login").count().catch(() => 0);

  if (otpVisible > 0) {
    output.authentication = "otp_required_manual_followup";
  } else if (loginFormVisible > 0 || /^sso\./i.test(currentHost)) {
    output.authentication = "login_not_completed_check_credentials_or_identity_policy";
  } else {
    output.authentication = "authenticated_session_established";
    await snapshotPage(page, "dashboard_landing");

    const candidates = [...new Map(output.report_links.map(x => [x.url, x])).values()].slice(0, 8);
    for (const target of candidates) {
      try {
        await page.goto(target.url, { waitUntil: "domcontentloaded", timeout: 30000 });
        await page.waitForTimeout(1800);
        if (!/^sso\./i.test(safePath(page.url()).host)) {
          await snapshotPage(page, "report_navigation");
          // Income detail and invoice sections are tabs in this panel. Click only
          // their explicit tab controls; never click buttons that mutate account data.
          const tabs = target.url.endsWith("/performance") || target.url.endsWith("/performance/links")
            ? ["نگاه کلی"]
            : ["جزئیات درآمد", "فاکتورها"];
          for (const label of tabs) {
            const tab = page.getByText(label, { exact: true }).last();
            const tabCount = await tab.count().catch(() => 0);
            const suffix = label === "فاکتورها" ? "invoices" :
              label === "جزئیات درآمد" ? "details" : "overview";
            if (tabCount === 0) {
              output.notes.push("Read-only tab not found: " + suffix);
              output.pages.push({
                label: "tab_diagnostic_" + suffix,
                url: safePath(page.url()),
                exact_text_matches: []
              });
              continue;
            }
            const beforeUrl = safePath(page.url());
            const beforeMatch = await inspectExactVisibleText(page, label).catch(() => []);
            const clickResult = await tab.click({ timeout: 4000 }).then(() => "clicked").catch(error => "click_failed:" + String(error?.name || "Error"));
            await page.waitForTimeout(1800);
            const afterUrl = safePath(page.url());
            const afterMatch = await inspectExactVisibleText(page, label).catch(() => []);
            output.pages.push({
              label: "tab_diagnostic_" + suffix,
              url_before: beforeUrl,
              url_after: afterUrl,
              click_result: clickResult,
              exact_text_matches_before: beforeMatch,
              exact_text_matches_after: afterMatch
            });
            await snapshotPage(page, (target.url.includes("/performance") ? "performance_tab_" : "income_tab_") + suffix);
          }
        }
      } catch {
        output.notes.push("A report route or read-only tab could not be opened.");
      }
    }
  }

  await Promise.allSettled(pendingCaptures);
  await page.waitForTimeout(500);
  await Promise.allSettled(pendingCaptures);
  await context.close();
} catch (error) {
  output.authentication = output.authentication === "not_attempted" ? "diagnostic_error" : output.authentication;
  output.notes.push("Diagnostic stopped: " + String(error?.name || "Error"));
} finally {
  if (browser) await browser.close().catch(() => {});
  await writeFile("affilio-dashboard-diagnostic.json", JSON.stringify(output, null, 2));
}

const mediaTotals = new Map();
for (const row of output.report_data.link_rows) {
  const key = row.media_uid || row.media_name || "unknown_media";
  const current = mediaTotals.get(key) || {
    media_uid: row.media_uid,
    media_name: row.media_name || "نامشخص",
    links: 0,
    clicks: 0,
    income_items_count: 0,
    total_income_toman: 0,
    weighted_conversion_rate_numerator: 0,
    weighted_conversion_rate_denominator: 0,
    weighted_conversion_rate: null
  };
  const clicks = row.click_count || 0;
  current.links += 1;
  current.clicks += clicks;
  current.income_items_count += row.income_items_count || 0;
  current.total_income_toman += row.total_income_toman || 0;
  if (row.conversion_rate !== null && clicks > 0) {
    current.weighted_conversion_rate_numerator += row.conversion_rate * clicks;
    current.weighted_conversion_rate_denominator += clicks;
  }
  mediaTotals.set(key, current);
}
output.report_data.media_totals = [...mediaTotals.values()].map(row => ({
  ...row,
  weighted_conversion_rate: row.weighted_conversion_rate_denominator
    ? row.weighted_conversion_rate_numerator / row.weighted_conversion_rate_denominator
    : null
}));

// Re-write after all aggregation has completed.
await writeFile("affilio-dashboard-diagnostic.json", JSON.stringify(output, null, 2));
console.log("AFFILIO_DIAGNOSTIC_STATUS=" + output.authentication);
console.log("AFFILIO_DIAGNOSTIC_PAGES=" + output.pages.length);
console.log("AFFILIO_DIAGNOSTIC_JSON_ENDPOINTS=" + output.api_responses.length);
console.log("AFFILIO_DIAGNOSTIC_METRIC_OBSERVATIONS=" + output.metric_observations.length);
console.log("AFFILIO_DIAGNOSTIC_MEDIA_ROWS=" + output.report_data.link_rows.length);
// Log only API paths, HTTP statuses and JSON key/type/array-shape summaries.
// Numeric/string values, query parameters, response bodies, cookies and credentials are never logged.
for (const response of output.api_responses.slice(0, 80)) {
  console.log("AFFILIO_ENDPOINT_SHAPE=" + JSON.stringify({
    host: response.host,
    path: response.path,
    status: response.status,
    fields: summarizeShape(response.shape)
  }));
}
// Page/route discovery is also sanitized: only labels, headings and same-origin route paths.
for (const snapshot of output.pages.slice(0, 30)) {
  console.log("AFFILIO_PAGE_SHAPE=" + JSON.stringify({
    label: snapshot.label,
    url: snapshot.url,
    title: snapshot.title,
    headings: snapshot.headings,
    tabs: snapshot.tabs || [],
    tables: snapshot.tables || [],
    grids: snapshot.grids || [],
    controls: (snapshot.controls || []).map(item => ({
      label: item.label,
      role: item.role,
      path: item.href && typeof item.href.pathname === "string" ? item.href.pathname : null
    })).slice(0, 80)
  }));
}
console.log("AFFILIO_REPORT_ROUTES=" + JSON.stringify(
  output.report_links.slice(0, 30).map(item => ({ label: item.label, url: item.url }))
));
if (output.authentication !== "authenticated_session_established") process.exitCode = 1;
