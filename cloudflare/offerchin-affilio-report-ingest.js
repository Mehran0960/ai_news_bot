const OIDC_ISSUER = "https://token.actions.githubusercontent.com";
const OIDC_AUDIENCE = "offerchin-affilio-report-ingest";
const ALLOWED_REPOSITORY = "Mehran0960/ai_news_bot";
const ALLOWED_WORKFLOW_REF =
  "Mehran0960/ai_news_bot/.github/workflows/affilio-panel-readonly-audit.yml@refs/heads/main";
const MAX_BODY_BYTES = 3 * 1024 * 1024;
const MAX_LINK_ROWS = 2000;
const MAX_BREAKDOWN_ROWS = 100;

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, max-age=0",
      "x-content-type-options": "nosniff"
    }
  });
}

function decodeBase64Url(input) {
  const normalized = String(input || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, function (char) { return char.charCodeAt(0); });
}

function decodeJwtPart(part) {
  return JSON.parse(new TextDecoder().decode(decodeBase64Url(part)));
}

async function verifyGitHubOidcToken(token) {
  const pieces = String(token || "").split(".");
  if (pieces.length !== 3) return null;

  let header;
  let claims;
  try {
    header = decodeJwtPart(pieces[0]);
    claims = decodeJwtPart(pieces[1]);
  } catch (_) {
    return null;
  }

  if (!header || header.alg !== "RS256" || !header.kid) return null;

  const now = Math.floor(Date.now() / 1000);
  if (
    claims.iss !== OIDC_ISSUER ||
    !Array.isArray(claims.aud) && claims.aud !== OIDC_AUDIENCE ||
    Array.isArray(claims.aud) && !claims.aud.includes(OIDC_AUDIENCE) ||
    !Number.isFinite(claims.exp) ||
    claims.exp <= now ||
    Number.isFinite(claims.nbf) && claims.nbf > now + 30 ||
    Number.isFinite(claims.iat) && claims.iat < now - 600 ||
    claims.repository !== ALLOWED_REPOSITORY ||
    claims.ref !== "refs/heads/main" ||
    claims.workflow_ref !== ALLOWED_WORKFLOW_REF ||
    !["push", "workflow_dispatch"].includes(claims.event_name) ||
    claims.sub !== "repo:" + ALLOWED_REPOSITORY + ":ref:refs/heads/main"
  ) {
    return null;
  }

  let jwksResponse;
  try {
    jwksResponse = await fetch(OIDC_ISSUER + "/.well-known/jwks", {
      headers: { accept: "application/json" }
    });
  } catch (_) {
    return null;
  }
  if (!jwksResponse.ok) return null;

  let jwks;
  try {
    jwks = await jwksResponse.json();
  } catch (_) {
    return null;
  }
  const jwk = Array.isArray(jwks.keys)
    ? jwks.keys.find(function (key) { return key.kid === header.kid && key.kty === "RSA"; })
    : null;
  if (!jwk) return null;

  try {
    const publicKey = await crypto.subtle.importKey(
      "jwk",
      jwk,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"]
    );
    const verified = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      publicKey,
      decodeBase64Url(pieces[2]),
      new TextEncoder().encode(pieces[0] + "." + pieces[1])
    );
    return verified ? claims : null;
  } catch (_) {
    return null;
  }
}

function safeText(value, maxLength) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return null;
  return value.slice(0, maxLength || 240);
}

function safeNumber(value, minimum, maximum) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  if (minimum !== undefined && number < minimum) return null;
  if (maximum !== undefined && number > maximum) return null;
  return number;
}

function validDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function validatePayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.schema_version !== 1) return null;
  if (!/^ghrun-[A-Za-z0-9_-]{1,80}$/.test(String(payload.snapshot_id || ""))) return null;
  if (!validDate(payload.window_from) || !validDate(payload.window_to)) return null;
  if (payload.window_from > payload.window_to) return null;
  if (!Array.isArray(payload.links) || payload.links.length > MAX_LINK_ROWS) return null;

  const links = [];
  for (const raw of payload.links) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const linkUid = safeText(raw.link_uid, 160);
    if (!linkUid || !/^[A-Za-z0-9_-]{1,160}$/.test(linkUid)) return null;
    links.push({
      link_uid: linkUid,
      link_title: safeText(raw.link_title, 300),
      advertiser_name: safeText(raw.advertiser_name, 200),
      media_uid: safeText(raw.media_uid, 160),
      media_name: safeText(raw.media_name, 200),
      link_type: safeText(raw.link_type, 80),
      link_kind: safeText(raw.link_kind, 80),
      click_count: safeNumber(raw.click_count, 0, 2147483647),
      conversion_rate: safeNumber(raw.conversion_rate, 0, 1000000),
      income_items_count: safeNumber(raw.income_items_count, 0, 2147483647),
      total_income: safeNumber(raw.total_income, 0),
      revenue_share: safeNumber(raw.revenue_share, 0, 1000),
      first_click_date: safeText(raw.first_click_date, 80),
      created_at: safeText(raw.created_at, 80),
      utm_campaign: safeText(raw.utm_campaign, 240),
      utm_content: safeText(raw.utm_content, 240)
    });
  }

  const wallet = payload.wallet_summary && typeof payload.wallet_summary === "object"
    ? payload.wallet_summary
    : {};
  const performance = payload.performance_by_link_type && typeof payload.performance_by_link_type === "object"
    ? payload.performance_by_link_type
    : {};

  const breakdowns = [];
  for (const metric of ["clicks", "conversions", "revenue"]) {
    const group = performance[metric];
    if (!group || typeof group !== "object") continue;
    const total = safeNumber(group.total, 0);
    if (!Array.isArray(group.breakdown)) continue;
    for (const item of group.breakdown.slice(0, MAX_BREAKDOWN_ROWS)) {
      if (!item || typeof item !== "object") continue;
      const itemType = safeText(item.type, 100);
      if (!itemType) continue;
      breakdowns.push({
        metric: metric,
        item_type: itemType,
        value: safeNumber(item.value, 0),
        percentage: safeNumber(item.percentage, 0, 100)
      });
    }
  }

  return {
    snapshot_id: String(payload.snapshot_id),
    source: "affilio_publisher_panel",
    captured_at: safeText(payload.captured_at, 80) || new Date().toISOString(),
    window_from: payload.window_from,
    window_to: payload.window_to,
    links_total: safeNumber(payload.links_total, 0, 100000000),
    links_total_is_capped: payload.links_total_is_capped === true ? 1 : 0,
    links_pages_fetched: safeNumber(payload.links_pages_fetched, 0, 1000) || 0,
    wallet_finalized_income_amount: safeNumber(wallet.finalized_income_amount, 0),
    wallet_balance_amount: safeNumber(wallet.wallet_balance_amount, 0),
    wallet_days_until_next_invoice: safeNumber(wallet.days_until_next_invoice, 0, 100000),
    dashboard_clicks_total: safeNumber(performance.clicks && performance.clicks.total, 0),
    dashboard_conversions_total: safeNumber(performance.conversions && performance.conversions.total, 0),
    dashboard_revenue_total: safeNumber(performance.revenue && performance.revenue.total, 0),
    links: links,
    breakdowns: breakdowns,
    github_run_id: safeText(payload.github_run_id, 80),
    github_run_attempt: safeNumber(payload.github_run_attempt, 1, 1000000)
  };
}

async function persistReport(env, report) {
  await env.DB.prepare(
    "INSERT INTO oc_affilio_report_snapshots (" +
    "snapshot_id, source, captured_at, window_from, window_to, links_total, " +
    "links_total_is_capped, links_pages_fetched, links_rows_stored, " +
    "wallet_finalized_income_amount, wallet_balance_amount, wallet_days_until_next_invoice, " +
    "dashboard_clicks_total, dashboard_conversions_total, dashboard_revenue_total, " +
    "ingest_status, github_run_id, github_run_attempt" +
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'loading', ?, ?) " +
    "ON CONFLICT(snapshot_id) DO UPDATE SET captured_at=excluded.captured_at, " +
    "window_from=excluded.window_from, window_to=excluded.window_to, links_total=excluded.links_total, " +
    "links_total_is_capped=excluded.links_total_is_capped, links_pages_fetched=excluded.links_pages_fetched, " +
    "links_rows_stored=excluded.links_rows_stored, wallet_finalized_income_amount=excluded.wallet_finalized_income_amount, " +
    "wallet_balance_amount=excluded.wallet_balance_amount, wallet_days_until_next_invoice=excluded.wallet_days_until_next_invoice, " +
    "dashboard_clicks_total=excluded.dashboard_clicks_total, dashboard_conversions_total=excluded.dashboard_conversions_total, " +
    "dashboard_revenue_total=excluded.dashboard_revenue_total, ingest_status='loading', " +
    "github_run_id=excluded.github_run_id, github_run_attempt=excluded.github_run_attempt"
  ).bind(
    report.snapshot_id, report.source, report.captured_at, report.window_from, report.window_to,
    report.links_total, report.links_total_is_capped, report.links_pages_fetched, report.links.length,
    report.wallet_finalized_income_amount, report.wallet_balance_amount, report.wallet_days_until_next_invoice,
    report.dashboard_clicks_total, report.dashboard_conversions_total, report.dashboard_revenue_total,
    report.github_run_id, report.github_run_attempt
  ).run();

  const linkStatements = report.links.map(function (link) {
    return env.DB.prepare(
      "INSERT INTO oc_affilio_link_analytics (" +
      "snapshot_id, link_uid, link_title, advertiser_name, media_uid, media_name, " +
      "link_type, link_kind, click_count, conversion_rate, income_items_count, total_income, " +
      "revenue_share, first_click_date, created_at, utm_campaign, utm_content" +
      ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) " +
      "ON CONFLICT(snapshot_id, link_uid) DO UPDATE SET " +
      "link_title=excluded.link_title, advertiser_name=excluded.advertiser_name, " +
      "media_uid=excluded.media_uid, media_name=excluded.media_name, link_type=excluded.link_type, " +
      "link_kind=excluded.link_kind, click_count=excluded.click_count, " +
      "conversion_rate=excluded.conversion_rate, income_items_count=excluded.income_items_count, " +
      "total_income=excluded.total_income, revenue_share=excluded.revenue_share, " +
      "first_click_date=excluded.first_click_date, created_at=excluded.created_at, " +
      "utm_campaign=excluded.utm_campaign, utm_content=excluded.utm_content"
    ).bind(
      report.snapshot_id, link.link_uid, link.link_title, link.advertiser_name, link.media_uid, link.media_name,
      link.link_type, link.link_kind, link.click_count, link.conversion_rate, link.income_items_count,
      link.total_income, link.revenue_share, link.first_click_date, link.created_at, link.utm_campaign, link.utm_content
    );
  });

  for (let offset = 0; offset < linkStatements.length; offset += 50) {
    await env.DB.batch(linkStatements.slice(offset, offset + 50));
  }

  const breakdownStatements = report.breakdowns.map(function (item) {
    return env.DB.prepare(
      "INSERT INTO oc_affilio_performance_breakdowns (" +
      "snapshot_id, metric, item_type, value, percentage" +
      ") VALUES (?, ?, ?, ?, ?) " +
      "ON CONFLICT(snapshot_id, metric, item_type) DO UPDATE SET " +
      "value=excluded.value, percentage=excluded.percentage"
    ).bind(report.snapshot_id, item.metric, item.item_type, item.value, item.percentage);
  });

  for (let offset = 0; offset < breakdownStatements.length; offset += 50) {
    await env.DB.batch(breakdownStatements.slice(offset, offset + 50));
  }

  await env.DB.prepare(
    "UPDATE oc_affilio_report_snapshots SET ingest_status='complete' WHERE snapshot_id=?"
  ).bind(report.snapshot_id).run();

  return { snapshot_id: report.snapshot_id, link_rows: report.links.length, breakdown_rows: report.breakdowns.length };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return json({ ok: true, service: "offerchin-affilio-report-ingest" }, 200);
    }
    if (url.pathname !== "/ingest/v1/affilio-report") {
      return json({ ok: false, error: "not_found" }, 404);
    }
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
    }
    if (!env.DB) return json({ ok: false, error: "storage_unavailable" }, 503);
    const contentType = String(request.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("application/json")) return json({ ok: false, error: "json_required" }, 415);
    const declaredLength = Number(request.headers.get("content-length") || 0);
    if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) return json({ ok: false, error: "payload_too_large" }, 413);

    const authorization = request.headers.get("authorization") || "";
    const match = authorization.match(/^Bearer\s+(.+)$/i);
    if (!match) return json({ ok: false, error: "unauthorized" }, 401);

    const claims = await verifyGitHubOidcToken(match[1]);
    if (!claims) return json({ ok: false, error: "unauthorized" }, 401);

    let payload;
    try {
      const bytes = await request.arrayBuffer();
      if (bytes.byteLength > MAX_BODY_BYTES) return json({ ok: false, error: "payload_too_large" }, 413);
      payload = JSON.parse(new TextDecoder().decode(bytes));
    } catch (_) {
      return json({ ok: false, error: "invalid_json" }, 400);
    }

    const report = validatePayload(payload);
    if (!report) return json({ ok: false, error: "invalid_report_payload" }, 400);

    try {
      const result = await persistReport(env, report);
      console.log(JSON.stringify({
        event: "affilio_report_ingested",
        snapshot_id: result.snapshot_id,
        link_rows: result.link_rows,
        breakdown_rows: result.breakdown_rows,
        repository: claims.repository,
        workflow_ref: claims.workflow_ref
      }));
      return json({ ok: true, accepted: true, ...result }, 202);
    } catch (_) {
      console.error(JSON.stringify({ event: "affilio_report_persistence_failed", snapshot_id: report.snapshot_id }));
      return json({ ok: false, error: "persistence_failed" }, 503);
    }
  }
};
