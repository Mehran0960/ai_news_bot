function decodeBase64Url(value) {
  try {
    const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(normalized);
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch (_) { return ""; }
}
function isSameProductUrl(raw, productId) {
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "https:" ||
        parsed.pathname.replace(/\/$/, "") !== "/product/" + productId) return false;
    if (/^dkp-\d{1,12}$/.test(productId)) return parsed.hostname === "www.digikala.com";
    if (/^snp-\d{1,20}$/.test(productId)) return parsed.hostname === "snappshop.ir";
    return false;
  } catch (_) { return false; }
}
function validateDestination(raw, productId) {
  let target;
  try { target = new URL(raw); } catch (_) { return null; }
  if (target.protocol !== "https:") return null;

  // The publisher's currently verified tracking URL is aflo.ir/QekEYTRg?p=<product URL>.
  // Validate the embedded destination exactly; never accept a generic/open redirect.
  if (target.hostname === "aflo.ir" && target.pathname === "/QekEYTRg") {
    const destinations = target.searchParams.getAll("p");
    if (destinations.length === 1 && isSameProductUrl(destinations[0], productId)) return target;
    return null;
  }

  if (target.hostname === "www.digikala.com" && isSameProductUrl(target.href, productId)) {
    const expected = {
      utm_source: "19166",
      utm_medium: "Affilio",
      utm_id: "14657",
      affid: "OTgxYTY0OTAtODJhNS00MDNkLTg0NDItMWE0MGVkOGI1Yjhj"
    };
    for (const [key, value] of Object.entries(expected)) {
      if (target.searchParams.get(key) !== value) return null;
    }
    return target;
  }

  if (target.hostname === "migmig.affilio.ir" && /\/api\/v1\/click\/b\//i.test(target.pathname)) {
    const candidates = [];
    const queryValue = target.searchParams.get("b64");
    if (queryValue) candidates.push(queryValue);
    const match = target.pathname.match(/\/api\/v1\/click\/b\/(.+)$/i);
    if (match) {
      const pieces = match[1].split("/");
      if (pieces.length >= 2) candidates.push(pieces.slice(1).join("/"));
    }
    for (const candidate of candidates) {
      const decoded = decodeBase64Url(candidate);
      if (decoded && isSameProductUrl(decoded, productId)) return target;
    }
  }
  return null;
}
function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, max-age=0"
    }
  });
}
function constantTimeEqual(left, right) {
  const encoder = new TextEncoder();
  const a = encoder.encode(String(left || ""));
  const b = encoder.encode(String(right || ""));
  let difference = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index++) {
    difference |= (a[index] || 0) ^ (b[index] || 0);
  }
  return difference === 0;
}

function parseAffilioSubId(value) {
  const raw = String(value || "");
  if (!raw || raw.length > 255 || !/^[A-Za-z0-9_-]+$/.test(raw)) return {};
  const match = raw.match(
    /^oc1-(dkp-\d{1,12}|snp-\d{1,20})-(telegram|bale|youtube|aparat|unknown)(?:-v-([a-z0-9_-]{1,32})-([ab]))?(?:-c-([a-z0-9_-]{1,32})-([ab]))?$/i
  );
  if (!match) return {};
  return {
    product_id: match[1].toLowerCase(),
    channel: match[2].toLowerCase(),
    creative_experiment_id: String(match[3] || "").toLowerCase(),
    creative_variant: String(match[4] || "").toUpperCase(),
    caption_experiment_id: String(match[5] || "").toLowerCase(),
    caption_variant: String(match[6] || "").toUpperCase()
  };
}

function normalizeAffilioConversion(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("invalid_payload");
  }
  const conversionId = String(payload.conversion_id || "").trim();
  const type = String(payload.type || "").trim().toLowerCase();
  const status = String(payload.status || "").trim().toLowerCase();
  const timestamp = String(payload.timestamp || "").trim();
  const timestampMs = Date.parse(timestamp);
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(conversionId)) throw new Error("invalid_conversion_id");
  if (!["sale", "lead", "action"].includes(type)) throw new Error("invalid_conversion_type");
  if (!["pending", "approved", "declined"].includes(status)) throw new Error("invalid_conversion_status");
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(timestamp) || !Number.isFinite(timestampMs)) {
    throw new Error("invalid_conversion_timestamp");
  }
  const affSub = payload.aff_sub == null ? "" : String(payload.aff_sub);
  if (affSub && (affSub.length > 255 || !/^[A-Za-z0-9_-]+$/.test(affSub))) {
    throw new Error("invalid_aff_sub");
  }
  const payout = payload.payout == null ? null : payload.payout;
  if (payout !== null && (!Number.isSafeInteger(payout) || payout < 0)) {
    throw new Error("invalid_payout");
  }
  let amount = null;
  let items = [];
  let unitsSold = 0;
  if (type === "sale") {
    if (!Number.isSafeInteger(payload.amount) || payload.amount < 0) throw new Error("invalid_sale_amount");
    amount = payload.amount;
    if (payload.items != null && !Array.isArray(payload.items)) throw new Error("invalid_sale_items");
    const rawItems = Array.isArray(payload.items) ? payload.items : [];
    if (rawItems.length > 50) throw new Error("too_many_sale_items");
    for (const item of rawItems) {
      if (!item || typeof item !== "object" || Array.isArray(item) ||
          !Number.isSafeInteger(item.quantity) || item.quantity < 1 || item.quantity > 10000 ||
          !Number.isSafeInteger(item.price) || item.price < 0) {
        throw new Error("invalid_sale_item");
      }
      unitsSold += item.quantity;
      if (unitsSold > 1000000) throw new Error("sale_quantity_limit");
      items.push({ quantity: item.quantity, price: item.price });
    }
  }
  return {
    conversion_id: conversionId,
    status,
    status_rank: status === "pending" ? 1 : 2,
    conversion_type: type,
    timestamp,
    timestamp_ms: timestampMs,
    aff_sub: affSub || null,
    ...parseAffilioSubId(affSub),
    payout_toman: payout,
    amount_toman: amount,
    units_sold: unitsSold,
    items_json: JSON.stringify(items),
    received_at_ms: Date.now()
  };
}

async function requireAffilioWebhookAuth(request, env) {
  const expected = String(env.AFFILIO_POSTBACK_TOKEN || "");
  if (!expected) return { ok: false, status: 503, error: "postback_token_not_configured" };
  const supplied = String(request.headers.get("X-Affilio-Token") || "");
  if (!constantTimeEqual(supplied, expected)) return { ok: false, status: 401, error: "unauthorized" };
  return { ok: true };
}

async function handleAffilioPostback(request, env) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "POST" } });
  }
  if (!env.CONVERSIONS) return jsonResponse({ ok: false, error: "conversion_store_unavailable" }, 503);
  const auth = await requireAffilioWebhookAuth(request, env);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error }, auth.status);
  const contentType = String(request.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) {
    return jsonResponse({ ok: false, error: "application_json_required" }, 415);
  }
  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 32768) return jsonResponse({ ok: false, error: "payload_too_large" }, 413);
  let payload;
  try {
    const raw = await request.text();
    if (raw.length > 32768) return jsonResponse({ ok: false, error: "payload_too_large" }, 413);
    payload = JSON.parse(raw);
  } catch (_) {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }
  let event;
  try {
    event = normalizeAffilioConversion(payload);
  } catch (error) {
    return jsonResponse({ ok: false, error: String(error.message || "invalid_payload") }, 400);
  }

  const values = [
    event.conversion_id, event.status, event.timestamp_ms, event.conversion_type,
    event.aff_sub, event.product_id || null, event.channel || null,
    event.creative_experiment_id || null, event.creative_variant || null,
    event.caption_experiment_id || null, event.caption_variant || null,
    event.payout_toman, event.amount_toman, event.units_sold, event.items_json,
    event.received_at_ms
  ];
  try {
    await env.CONVERSIONS.prepare(
      "INSERT OR IGNORE INTO affilio_conversion_events " +
      "(conversion_id,status,timestamp_ms,conversion_type,aff_sub,product_id,channel," +
      "creative_experiment_id,creative_variant,caption_experiment_id,caption_variant," +
      "payout_toman,amount_toman,units_sold,items_json,received_at_ms) " +
      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    ).bind(...values).run();

    await env.CONVERSIONS.prepare(
      "INSERT INTO affilio_conversion_current " +
      "(conversion_id,status,status_rank,timestamp_ms,conversion_type,aff_sub,product_id,channel," +
      "creative_experiment_id,creative_variant,caption_experiment_id,caption_variant," +
      "payout_toman,amount_toman,units_sold,items_json,received_at_ms) " +
      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) " +
      "ON CONFLICT(conversion_id) DO UPDATE SET " +
      "status=excluded.status,status_rank=excluded.status_rank,timestamp_ms=excluded.timestamp_ms," +
      "conversion_type=excluded.conversion_type,aff_sub=excluded.aff_sub,product_id=excluded.product_id," +
      "channel=excluded.channel,creative_experiment_id=excluded.creative_experiment_id," +
      "creative_variant=excluded.creative_variant,caption_experiment_id=excluded.caption_experiment_id," +
      "caption_variant=excluded.caption_variant,payout_toman=excluded.payout_toman," +
      "amount_toman=excluded.amount_toman,units_sold=excluded.units_sold,items_json=excluded.items_json," +
      "received_at_ms=excluded.received_at_ms " +
      "WHERE excluded.timestamp_ms > affilio_conversion_current.timestamp_ms " +
      "OR (excluded.timestamp_ms = affilio_conversion_current.timestamp_ms " +
      "AND (excluded.status_rank > affilio_conversion_current.status_rank " +
      "OR (excluded.status_rank = affilio_conversion_current.status_rank " +
      "AND excluded.received_at_ms > affilio_conversion_current.received_at_ms)))"
    ).bind(
      event.conversion_id, event.status, event.status_rank, event.timestamp_ms,
      event.conversion_type, event.aff_sub, event.product_id || null, event.channel || null,
      event.creative_experiment_id || null, event.creative_variant || null,
      event.caption_experiment_id || null, event.caption_variant || null,
      event.payout_toman, event.amount_toman, event.units_sold, event.items_json,
      event.received_at_ms
    ).run();
  } catch (error) {
    console.error("AFFILIO_POSTBACK_STORE_FAILED", String(error && error.message || error).slice(0, 120));
    return jsonResponse({ ok: false, error: "conversion_store_write_failed" }, 503);
  }
  return jsonResponse({ ok: true, accepted: true });
}

function rowsToMap(rows, keyBuilder) {
  const result = Object.create(null);
  for (const row of rows || []) {
    const key = keyBuilder(row);
    if (!key) continue;
    result[key] = {
      confirmedOrderCount: Number(row.confirmedOrderCount || 0),
      unitsSold: Number(row.unitsSold || 0),
      salesAmountToman: Number(row.salesAmountToman || 0),
      approvedCommissionToman: Number(row.approvedCommissionToman || 0)
    };
  }
  return result;
}

async function handleConversionStats(request, env) {
  if (request.method !== "GET") {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "GET" } });
  }
  if (!env.CONVERSIONS) return jsonResponse({ ok: false, error: "conversion_store_unavailable" }, 503);
  const auth = await requireAffilioWebhookAuth(request, env);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error }, auth.status);
  const since = Date.now() - 30 * 86400000;
  const salesWhere = "timestamp_ms >= ? AND conversion_type='sale' AND status='approved'";
  const aggregateSql = (groupBy, whereExtra = "") =>
    "SELECT " + groupBy + " AS group_key,COUNT(*) AS confirmedOrderCount," +
    "COALESCE(SUM(units_sold),0) AS unitsSold," +
    "COALESCE(SUM(amount_toman),0) AS salesAmountToman," +
    "COALESCE(SUM(payout_toman),0) AS approvedCommissionToman " +
    "FROM affilio_conversion_current WHERE " + salesWhere +
    (whereExtra ? " AND " + whereExtra : "") + " GROUP BY " + groupBy;
  try {
    const [summaryResult, statusesResult, productResult, channelResult, creativeResult, captionResult] = await Promise.all([
      env.CONVERSIONS.prepare(
        "SELECT COUNT(*) AS confirmedOrderCount,COALESCE(SUM(units_sold),0) AS unitsSold," +
        "COALESCE(SUM(amount_toman),0) AS salesAmountToman," +
        "COALESCE(SUM(payout_toman),0) AS approvedCommissionToman " +
        "FROM affilio_conversion_current WHERE " + salesWhere
      ).bind(since).all(),
      env.CONVERSIONS.prepare(
        "SELECT status,conversion_type,COUNT(*) AS count FROM affilio_conversion_current " +
        "WHERE timestamp_ms >= ? GROUP BY status,conversion_type"
      ).bind(since).all(),
      env.CONVERSIONS.prepare(aggregateSql("product_id", "product_id IS NOT NULL")).bind(since).all(),
      env.CONVERSIONS.prepare(aggregateSql("channel", "channel IS NOT NULL")).bind(since).all(),
      env.CONVERSIONS.prepare(aggregateSql("creative_experiment_id || ':' || creative_variant", "creative_experiment_id IS NOT NULL AND creative_variant IS NOT NULL")).bind(since).all(),
      env.CONVERSIONS.prepare(aggregateSql("caption_experiment_id || ':' || caption_variant", "caption_experiment_id IS NOT NULL AND caption_variant IS NOT NULL")).bind(since).all()
    ]);
    const first = (summaryResult && summaryResult.results && summaryResult.results[0]) || {};
    const statusCounts = Object.create(null);
    for (const row of (statusesResult && statusesResult.results) || []) {
      statusCounts[row.conversion_type + ":" + row.status] = Number(row.count || 0);
    }
    const mapRows = result => rowsToMap(result && result.results, row => row.product_id || row.channel || row["creative_experiment_id || ':' || creative_variant"] || row["caption_experiment_id || ':' || caption_variant"]);
    const productRows = (productResult && productResult.results) || [];
    const channelRows = (channelResult && channelResult.results) || [];
    const creativeRows = (creativeResult && creativeResult.results) || [];
    const captionRows = (captionResult && captionResult.results) || [];
    const creativeMap = Object.create(null);
    for (const row of creativeRows) creativeMap[row["creative_experiment_id || ':' || creative_variant"]] = {
      confirmedOrderCount: Number(row.confirmedOrderCount || 0), unitsSold: Number(row.unitsSold || 0),
      salesAmountToman: Number(row.salesAmountToman || 0), approvedCommissionToman: Number(row.approvedCommissionToman || 0)
    };
    const captionMap = Object.create(null);
    for (const row of captionRows) captionMap[row["caption_experiment_id || ':' || caption_variant"]] = {
      confirmedOrderCount: Number(row.confirmedOrderCount || 0), unitsSold: Number(row.unitsSold || 0),
      salesAmountToman: Number(row.salesAmountToman || 0), approvedCommissionToman: Number(row.approvedCommissionToman || 0)
    };
    return jsonResponse({
      ok: true, complete: true, days: 30, from: new Date(since).toISOString(),
      updatedAt: new Date().toISOString(),
      summary: {
        confirmedOrderCount: Number(first.confirmedOrderCount || 0),
        unitsSold: Number(first.unitsSold || 0),
        salesAmountToman: Number(first.salesAmountToman || 0),
        approvedCommissionToman: Number(first.approvedCommissionToman || 0),
        pendingSaleCount: statusCounts["sale:pending"] || 0,
        declinedSaleCount: statusCounts["sale:declined"] || 0,
        approvedLeadCount: statusCounts["lead:approved"] || 0,
        approvedActionCount: statusCounts["action:approved"] || 0
      },
      byProduct: rowsToMap(productRows, row => row.product_id),
      byChannel: rowsToMap(channelRows, row => row.channel),
      byCreativeVariant: creativeMap,
      byCaptionVariant: captionMap
    });
  } catch (error) {
    console.error("AFFILIO_CONVERSION_STATS_FAILED", String(error && error.message || error).slice(0, 120));
    return jsonResponse({ ok: false, error: "conversion_stats_unavailable" }, 503);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/affilio/postback") {
      return handleAffilioPostback(request, env);
    }
    if (url.pathname === "/conversions/stats") {
      return handleConversionStats(request, env);
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { "Allow": "GET, HEAD" } });
    }
    if (url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "affiliate-deal-radar",
        clickStoreReady: !!env.CLICKS,
        conversionStoreReady: !!env.CONVERSIONS,
        conversionPostbackReady: !!env.CONVERSIONS && !!env.AFFILIO_POSTBACK_TOKEN,
        experimentAttribution: true,
        captionExperimentAttribution: true,
        routes: ["/health", "/stats", "/p/<dkp-or-snp-product-id>", "/affilio/postback", "/conversions/stats"],
        stats: "Aggregated product and source click counts for the last 30 days only",
        conversions: "Affilio-approved sales and attribution; requires D1 and X-Affilio-Token"
      });
    }
    if (url.pathname === "/stats") {
      if (!env.CLICKS) return jsonResponse({ok:false,error:"click_store_unavailable"},503);
      const cacheKey = "analytics:clicks:30d:v4";
      try {
        const cached = await env.CLICKS.get(cacheKey, "json");
        const cacheAgeMs = cached && cached.updatedAt
          ? Date.now() - Date.parse(cached.updatedAt)
          : Number.POSITIVE_INFINITY;
        if (
          cached &&
          cached.ok === true &&
          Number.isFinite(cacheAgeMs) &&
          cacheAgeMs >= 0 &&
          cacheAgeMs < 2 * 60 * 60 * 1000 &&
          cached.products && typeof cached.products === "object"
        ) {
          return jsonResponse(cached);
        }
      } catch (_) {}

      const now = new Date();
      const today = now.toISOString().slice(0, 10);
      const products = Object.create(null);
      const sources = Object.create(null);
      const variants = Object.create(null);
      const experiments = Object.create(null);
      const experimentVariants = Object.create(null);
      const visualExperimentVariants = Object.create(null);
      const captionExperimentVariants = Object.create(null);
      const productSources = Object.create(null);
      const productExperimentVariants = Object.create(null);
      const productVisualExperimentVariants = Object.create(null);
      const productCaptionExperimentVariants = Object.create(null);
      let complete = true;
      try {
        // Day-scoped prefixes avoid scanning old keys first as the namespace grows.
        // One page per date is enough for normal channel volumes; flag partial days honestly.
        const prefixes = [];
        for (let offset = 0; offset < 30; offset++) {
          const day = new Date(now.getTime() - offset * 86400000).toISOString().slice(0, 10);
          prefixes.push({day, prefix: "click:" + day + ":"});
        }
        const pages = await Promise.all(prefixes.map(({prefix}) => env.CLICKS.list({prefix, limit:1000})));
        for (let index = 0; index < pages.length; index++) {
          const page = pages[index];
          for (const key of page.keys || []) {
            const keyName = String(key.name || "");
            const dual = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20})):((?:telegram|bale|youtube|aparat|unknown)):v:([a-z0-9][a-z0-9_-]{0,31}):([ab]):c:([a-z0-9][a-z0-9_-]{0,31}):([ab]):/);
            const current = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20})):((?:telegram|bale|youtube|aparat|unknown)):([a-z0-9][a-z0-9_-]{0,31}):([ab]):/);
            const legacy = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20}))(?::(telegram|bale|youtube|aparat|unknown))?:/);
            if (dual || current || legacy) {
              const productId = dual ? dual[2] : current ? current[2] : legacy[2];
              const source = dual ? dual[3] : current ? current[3] : (legacy[3] || "unknown");
              products[productId] = (products[productId] || 0) + 1;
              sources[source] = (sources[source] || 0) + 1;
              productSources[productId] = productSources[productId] || Object.create(null);
              productSources[productId][source] = (productSources[productId][source] || 0) + 1;
              if (dual || current) {
                const experiment = dual ? dual[4] : current[4];
                const variant = (dual ? dual[5] : current[5]).toUpperCase();
                const experimentKey = experiment + ":" + variant;
                variants[variant] = (variants[variant] || 0) + 1;
                experiments[experiment] = (experiments[experiment] || 0) + 1;
                experimentVariants[experimentKey] = (experimentVariants[experimentKey] || 0) + 1;
                visualExperimentVariants[experimentKey] = (visualExperimentVariants[experimentKey] || 0) + 1;
                productExperimentVariants[productId] = productExperimentVariants[productId] || Object.create(null);
                productExperimentVariants[productId][experimentKey] =
                  (productExperimentVariants[productId][experimentKey] || 0) + 1;
                productVisualExperimentVariants[productId] = productVisualExperimentVariants[productId] || Object.create(null);
                productVisualExperimentVariants[productId][experimentKey] =
                  (productVisualExperimentVariants[productId][experimentKey] || 0) + 1;
              }
              if (dual) {
                const captionExperiment = dual[6];
                const captionVariant = dual[7].toUpperCase();
                const captionKey = captionExperiment + ":" + captionVariant;
                captionExperimentVariants[captionKey] = (captionExperimentVariants[captionKey] || 0) + 1;
                productCaptionExperimentVariants[productId] = productCaptionExperimentVariants[productId] || Object.create(null);
                productCaptionExperimentVariants[productId][captionKey] =
                  (productCaptionExperimentVariants[productId][captionKey] || 0) + 1;
              }
            }
          }
          if (page.list_complete === false) complete = false;
        }
      } catch (error) {
        console.error("CLICK_STATS_READ_FAILED", String(error).slice(0,120));
        return jsonResponse({ok:false,error:"click_stats_unavailable"},503);
      }
      const result = {
        ok: true,
        days: 30,
        from: new Date(now.getTime() - 29 * 86400000).toISOString().slice(0,10),
        to: today,
        updatedAt: now.toISOString(),
        complete,
        totalClicks: Object.values(products).reduce((sum, count) => sum + count, 0),
        products,
        sources,
        variants,
        experiments,
        experimentVariants,
        visualExperimentVariants,
        captionExperimentVariants,
        productSources,
        productExperimentVariants,
        productVisualExperimentVariants,
        productCaptionExperimentVariants
      };
      try {
        await env.CLICKS.put(cacheKey, JSON.stringify(result), {expirationTtl:7200});
      } catch (error) {
        console.error("CLICK_STATS_CACHE_WRITE_FAILED", String(error).slice(0,120));
      }
      return jsonResponse(result);
    }

    const match = url.pathname.match(/^\/p\/((?:dkp-\d{1,12})|(?:snp-\d{1,20}))\/?$/);
    if (!match) return new Response("Not found", { status: 404 });
    const productId = match[1];
    const destination = validateDestination(url.searchParams.get("u") || "", productId);
    if (!destination) return new Response("Invalid or mismatched product destination", { status: 400 });
    const allowedSources = new Set(["telegram", "bale", "youtube", "aparat"]);
    const requestedSource = String(url.searchParams.get("src") || "unknown").toLowerCase();
    const source = allowedSources.has(requestedSource) ? requestedSource : "unknown";
    const rawExperiment = String(url.searchParams.get("exp") || "").toLowerCase();
    const experiment = /^[a-z0-9][a-z0-9_-]{0,31}$/.test(rawExperiment) ? rawExperiment : "";
    const rawVariant = String(url.searchParams.get("variant") || "").toLowerCase();
    const variant = experiment && (rawVariant === "a" || rawVariant === "b") ? rawVariant : "";
    const rawCaptionExperiment = String(url.searchParams.get("cexp") || "").toLowerCase();
    const captionExperiment = /^[a-z0-9][a-z0-9_-]{0,31}$/.test(rawCaptionExperiment) ? rawCaptionExperiment : "";
    const rawCaptionVariant = String(url.searchParams.get("cvariant") || "").toLowerCase();
    const captionVariant = captionExperiment && (rawCaptionVariant === "a" || rawCaptionVariant === "b")
      ? rawCaptionVariant : "";

    const ua = request.headers.get("user-agent") || "";
    const likelyPreviewBot = /(telegrambot|facebookexternalhit|whatsapp|slackbot|discordbot|twitterbot|linkedinbot|googlebot|bingbot|yandexbot|crawler|spider|\bbot\b)/i.test(ua);
    if (request.method === "GET" && !likelyPreviewBot && env.CLICKS) {
      const now = new Date();
      const stamp = now.toISOString();
      const day = stamp.slice(0, 10);
      const attributionParts = [];
      if (experiment && variant) attributionParts.push("v", experiment, variant);
      if (captionExperiment && captionVariant) attributionParts.push("c", captionExperiment, captionVariant);
      const attribution = attributionParts.length ? ":" + attributionParts.join(":") : "";
      const eventKey = "click:" + day + ":" + productId + ":" + source + attribution + ":" + now.getTime() + "-" + crypto.randomUUID();
      try {
        // Store only product ID, timestamp, fixed source and optional visual/caption A/B labels;
        // no IPs, referrers or full affiliate URLs are retained.
        await env.CLICKS.put(eventKey, JSON.stringify({
          product_id: productId,
          clicked_at: stamp,
          channel: source,
          experiment: experiment || "",
          variant: variant ? variant.toUpperCase() : "",
          caption_experiment: captionExperiment || "",
          caption_variant: captionVariant ? captionVariant.toUpperCase() : ""
        }), {expirationTtl:15552000});
      } catch (error) {
        console.error("CLICK_WRITE_FAILED", productId, String(error).slice(0,100));
      }
    }
    return Response.redirect(destination.toString(), 302);
  }
};