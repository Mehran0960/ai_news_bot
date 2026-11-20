import { chromium } from "playwright";

const PANEL_ORIGIN = "https://publisher.affilio.ir";
const REPORT_PAGES = [
  "/performance",
  "/performance/overview",
  "/performance/links",
  "/performance/products",
];
const RELEVANT_PATH = /(api|graphql|report|performance|commission|transaction|order|click|analytics|statistic|sales|conversion|payout|earning|affiliate|publisher|finance|revenue|dashboard|overview|summary|metric|link|product)/i;

function isOfficialHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host === "publisher.affilio.ir" || host.endsWith(".affilio.ir") || host.endsWith(".digiwise.ir");
}

function sanitizePath(pathname) {
  return String(pathname || "/").split("/").map((segment) => {
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(segment)) return "{id}";
    if (/^\d{5,}$/.test(segment)) return "{id}";
    if (/^[A-Za-z0-9_-]{28,}$/.test(segment)) return "{opaque}";
    return segment;
  }).join("/").slice(0, 220);
}

function safeRoute(urlString) {
  let parsed;
  try { parsed = new URL(urlString); } catch { return null; }
  if (parsed.protocol !== "https:" || !isOfficialHost(parsed.hostname)) return null;
  if (parsed.pathname.startsWith("/realms/") || parsed.pathname.includes("/login-actions/")) return null;
  const path = sanitizePath(parsed.pathname);
  if (!RELEVANT_PATH.test(path) && parsed.hostname !== "api.affilio.ir") return null;
  return parsed.hostname + path;
}

function safeQueryKeys(urlString) {
  try {
    const parsed = new URL(urlString);
    return [...new Set([...parsed.searchParams.keys()])].sort().slice(0, 30);
  } catch {
    return [];
  }
}

function describeSchema(value, depth = 0) {
  if (value === null) return "null";
  if (Array.isArray(value)) {
    if (value.length === 0) return "array<unknown>";
    return "array<" + describeSchema(value[0], depth + 1) + ">";
  }
  if (typeof value === "object") {
    if (depth >= 6) return "object";
    const keys = Object.keys(value).sort().slice(0, 24);
    return "{" + keys.map((key) => key + ":" + describeSchema(value[key], depth + 1)).join(",") + "}";
  }
  return typeof value;
}

async function main() {
  const username = process.env.AFFILIO_USER || "";
  const password = process.env.AFFILIO_PASS || "";
  console.log("AFFILIO_USER_SECRET_PRESENT=" + (username ? "yes" : "no"));
  console.log("AFFILIO_PASS_SECRET_PRESENT=" + (password ? "yes" : "no"));
  if (!username || !password) {
    console.log("AFFILIO_BROWSER_AUDIT_RESULT=blocked_missing_secret");
    process.exitCode = 2;
    return;
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ locale: "fa-IR", timezoneId: "Asia/Tehran" });
  const page = await context.newPage();
  const observed = new Map();
  const responseTasks = new Set();

  page.on("request", (request) => {
    const kind = request.resourceType();
    if (kind !== "xhr" && kind !== "fetch") return;
    const route = safeRoute(request.url());
    if (!route) return;
    const method = request.method().toUpperCase();
    const key = method + " " + route;
    const queryKeys = safeQueryKeys(request.url());
    if (!observed.has(key)) {
      observed.set(key, { method, route, queryKeys, status: "pending", contentType: "unknown" });
    } else {
      const record = observed.get(key);
      record.queryKeys = [...new Set([...(record.queryKeys || []), ...queryKeys])].sort().slice(0, 30);
    }
  });

  page.on("requestfailed", (request) => {
    const kind = request.resourceType();
    if (kind !== "xhr" && kind !== "fetch") return;
    const route = safeRoute(request.url());
    if (!route) return;
    const key = request.method().toUpperCase() + " " + route;
    const record = observed.get(key);
    if (record && record.status === "pending") record.status = "network_failed";
  });

  page.on("response", (response) => {
    const task = (async () => {
      const request = response.request();
      const kind = request.resourceType();
      if (kind !== "xhr" && kind !== "fetch") return;
      const route = safeRoute(request.url());
      if (!route) return;
      const key = request.method().toUpperCase() + " " + route;
      const record = observed.get(key);
      if (!record) return;
      record.status = String(response.status());
      const contentType = response.headers()["content-type"] || "unknown";
      record.contentType = contentType.split(";")[0].slice(0, 80);
      record.schema = "not_json";
      if (record.contentType.includes("json")) {
        try {
          const body = await response.json();
          record.schema = describeSchema(body);
        } catch {
          record.schema = "json_parse_unavailable";
        }
      }
    })();
    responseTasks.add(task);
    task.finally(() => responseTasks.delete(task));
  });



  try {
    await page.goto(PANEL_ORIGIN, { waitUntil: "domcontentloaded", timeout: 45000 });
    const usernameField = page.locator('input[name="username"]');
    const passwordField = page.locator('input[name="password"]');
    if (await usernameField.count().catch(() => 0)) {
      await usernameField.fill(username);
      await passwordField.fill(password);
      await page.locator("form#kc-form-login").evaluate((form) => form.requestSubmit());
      await page.waitForURL((url) => url.protocol === "https:" && url.hostname === "publisher.affilio.ir", { timeout: 60000 }).catch(() => null);
    }
    await page.waitForLoadState("domcontentloaded", { timeout: 15000 }).catch(() => null);
    await page.waitForTimeout(2000);
    if (new URL(page.url()).hostname !== "publisher.affilio.ir") {
      console.log("AFFILIO_BROWSER_AUDIT_RESULT=login_rejected_or_additional_challenge");
      process.exitCode = 3;
      return;
    }
    if (await page.locator("form#kc-form-login").count().catch(() => 0)) {
      console.log("AFFILIO_BROWSER_AUDIT_RESULT=login_form_still_visible");
      process.exitCode = 4;
      return;
    }

    for (const route of REPORT_PAGES) {
      try {
        await page.goto(PANEL_ORIGIN + route, { waitUntil: "domcontentloaded", timeout: 30000 });
        await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => null);
        await page.waitForTimeout(1200);
        if (new URL(page.url()).hostname !== "publisher.affilio.ir") {
          console.log("AFFILIO_BROWSER_AUDIT_RESULT=session_lost_during_report_navigation");
          process.exitCode = 5;
          return;
        }
        console.log("AFFILIO_UI_ROUTE_VISITED=" + route);
      } catch {
        console.log("AFFILIO_UI_ROUTE_VISIT=unavailable:" + route);
      }
    }

    await Promise.allSettled([...responseTasks]);
    const records = [...observed.values()].sort((a, b) => (a.route + a.method).localeCompare(b.route + b.method));
    console.log("AFFILIO_BROWSER_AUDIT_RESULT=authenticated_read_only");
    console.log("AFFILIO_XHR_FETCH_ROUTE_COUNT=" + records.length);
    for (const record of records.slice(0, 80)) {
      console.log("AFFILIO_NETWORK_ROUTE=" + record.method + " " + record.route + " status=" + record.status + " type=" + record.contentType + " params=" + ((record.queryKeys || []).join(",") || "none") + " schema=" + (record.schema || "not_observed"));
    }
    console.log("AFFILIO_NETWORK_QUERY_KEYS_RECORDED=yes");
    console.log("AFFILIO_NETWORK_QUERY_VALUES_RECORDED=no");
    console.log("AFFILIO_NETWORK_HEADERS_OR_BODIES_RECORDED=no");
    console.log("AFFILIO_RESPONSE_VALUES_RECORDED=no");
    console.log("AFFILIO_REPORT_ROWS_CAPTURED=no");
    console.log("AFFILIO_BROWSER_STATE_PERSISTED=no");
  } finally {
    await context.close().catch(() => null);
    await browser.close().catch(() => null);
  }
}

main().catch(() => {
  console.log("AFFILIO_BROWSER_AUDIT_RESULT=unexpected_error");
  process.exitCode = 10;
});