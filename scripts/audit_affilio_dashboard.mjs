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
  notes: [
    "Read-only diagnostic: login plus GET navigation to report pages only.",
    "No cookies, tokens, headers, usernames, account identifiers or full page bodies are stored."
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
    const normalized = value.replace(/[۰-۹]/g, d => "۰۱۲۳۴۵۶۷۸۹".indexOf(d))
      .replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d))
      .replace(/[٬,\s]/g, "");
    if (/^-?\d+(\.\d+)?$/.test(normalized)) return Number(normalized);
  }
  return null;
}

function walkMetrics(value, parent = "", depth = 0) {
  if (!value || typeof value !== "object" || depth > 8 || output.metric_observations.length >= 120) return;
  if (Array.isArray(value)) {
    value.slice(0, 100).forEach((item, index) => walkMetrics(item, parent, depth + 1));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (METRIC_KEY.test(key)) {
      const number = numericValue(child);
      if (number !== null) {
        output.metric_observations.push({
          field: parent ? parent + "." + key : key,
          value: number
        });
      }
    }
    if (child && typeof child === "object") walkMetrics(child, parent ? parent + "." + key : key, depth + 1);
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

async function snapshotPage(page, label) {
  const info = await page.evaluate(() => {
    const text = el => (el.innerText || el.getAttribute("aria-label") || el.getAttribute("title") || "").trim().replace(/\s+/g, " ").slice(0, 100);
    const headings = [...document.querySelectorAll("h1,h2,h3,[role=heading]")]
      .map(text).filter(Boolean).slice(0, 30);
    const controls = [...document.querySelectorAll("a[href],button,[role=menuitem]")]
      .map(el => ({ label: text(el), href: el.tagName === "A" ? el.getAttribute("href") : null }))
      .filter(x => x.label).slice(0, 120);
    return { title: document.title || "", pathname: location.pathname, headings, controls };
  });
  const reportLinks = [];
  for (const item of info.controls) {
    if (!REPORT_WORDS.test(item.label) && !REPORT_WORDS.test(item.href || "")) continue;
    if (!item.href) continue;
    try {
      const target = new URL(item.href, page.url());
      if (target.origin === "https://publisher.affilio.ir" &&
          !EXCLUDED_PATH.test(target.pathname)) {
        reportLinks.push({ label: item.label, url: target.origin + target.pathname });
      }
    } catch {}
  }
  output.pages.push({ label, url: safePath(page.url()), title: info.title, headings: info.headings, controls: info.controls });
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
      output.api_responses.push({
        host: path.host,
        path: path.path,
        status,
        shape: shapeOf(payload)
      });
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
        if (/^sso\./i.test(safePath(page.url()).host)) continue;
        await snapshotPage(page, "report_navigation");
      } catch {
        output.notes.push("A report route could not be opened; no account data was changed.");
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

console.log("AFFILIO_DIAGNOSTIC_STATUS=" + output.authentication);
console.log("AFFILIO_DIAGNOSTIC_PAGES=" + output.pages.length);
console.log("AFFILIO_DIAGNOSTIC_JSON_ENDPOINTS=" + output.api_responses.length);
console.log("AFFILIO_DIAGNOSTIC_METRIC_OBSERVATIONS=" + output.metric_observations.length);
if (output.authentication !== "authenticated_session_established") {
  process.exitCode = 1;
}
