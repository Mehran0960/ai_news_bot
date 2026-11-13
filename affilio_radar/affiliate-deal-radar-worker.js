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

function constantTimeEqual(leftValue, rightValue) {
  const left = new TextEncoder().encode(String(leftValue || ""));
  const right = new TextEncoder().encode(String(rightValue || ""));
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index++) {
    difference |= (left[index] || 0) ^ (right[index] || 0);
  }
  return difference === 0;
}

function parseAffilioPostback(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const conversionId = String(payload.conversion_id || "").trim();
  const type = String(payload.type || "").trim().toLowerCase();
  const status = String(payload.status || "").trim().toLowerCase();
  const timestampRaw = String(payload.timestamp || "").trim();
  const timestampDate = new Date(timestampRaw);
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(conversionId)) return null;
  if (!new Set(["sale", "lead", "action"]).has(type)) return null;
  if (!new Set(["pending", "approved", "declined"]).has(status)) return null;
  if (!timestampRaw || !Number.isFinite(timestampDate.getTime())) return null;

  const affSub = payload.aff_sub == null ? "" : String(payload.aff_sub).trim();
  if (affSub && !/^[A-Za-z0-9_-]{1,255}$/.test(affSub)) return null;
  const payout = payload.payout == null ? null : Number(payload.payout);
  if (payout !== null && (!Number.isSafeInteger(payout) || payout < 0)) return null;
  if (status === "approved" && payout === null) return null;
  const amount = payload.amount == null ? null : Number(payload.amount);
  if (amount !== null && (!Number.isSafeInteger(amount) || amount < 0)) return null;
  if (type === "sale" && amount === null) return null;

  const itemsRaw = payload.items == null ? [] : payload.items;
  if (!Array.isArray(itemsRaw) || itemsRaw.length > 100) return null;
  const items = [];
  for (const item of itemsRaw) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    const quantity = Number(item.quantity);
    const unitPrice = Number(item.unit_price);
    if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 10000) return null;
    if (!Number.isSafeInteger(unitPrice) || unitPrice < 0) return null;
    items.push({ quantity, unit_price: unitPrice });
  }

  return {
    conversion_id: conversionId,
    type,
    status,
    timestamp: timestampDate.toISOString(),
    aff_sub: affSub,
    payout_toman: payout,
    amount_toman: amount,
    items
  };
}

function parseOfferChinAffSub(value) {
  const match = String(value || "").match(
    /^oc1_(telegram|bale|youtube|aparat)_((?:dkp-\\d{1,12})|(?:snp-\\d{1,20}))(?:_([A-Za-z0-9_-]{1,120}))?$/
  );
  if (!match) return { source: "unknown", product_id: "unknown", campaign: "" };
  return { source: match[1], product_id: match[2], campaign: match[3] || "" };
}

async function receiveAffilioPostback(request, env) {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405, headers: { "Allow": "POST" } });
  }
  if (!env.AFFILIO_POSTBACK_TOKEN) {
    return jsonResponse({ ok: false, error: "postback_not_configured" }, 503);
  }
  if (!constantTimeEqual(request.headers.get("X-Affilio-Token"), env.AFFILIO_POSTBACK_TOKEN)) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }
  if (!env.DB) return jsonResponse({ ok: false, error: "conversion_database_unavailable" }, 503);
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > 65536) return jsonResponse({ ok: false, error: "payload_too_large" }, 413);

  let raw;
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > 65536) {
      return jsonResponse({ ok: false, error: "payload_too_large" }, 413);
    }
    raw = JSON.parse(body);
  } catch (_) {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }

  const conversion = parseAffilioPostback(raw);
  if (!conversion) return jsonResponse({ ok: false, error: "invalid_conversion_payload" }, 400);
  const receivedAt = new Date().toISOString();
  try {
    const result = await env.DB.prepare(
      `INSERT INTO affilio_conversions (
        conversion_id, status, type, timestamp, aff_sub,
        payout_toman, amount_toman, items_json, received_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(conversion_id, status) DO UPDATE SET
        type = excluded.type,
        timestamp = excluded.timestamp,
        aff_sub = excluded.aff_sub,
        payout_toman = excluded.payout_toman,
        amount_toman = excluded.amount_toman,
        items_json = excluded.items_json,
        received_at = excluded.received_at
      WHERE excluded.timestamp > affilio_conversions.timestamp`
    ).bind(
      conversion.conversion_id,
      conversion.status,
      conversion.type,
      conversion.timestamp,
      conversion.aff_sub || null,
      conversion.payout_toman,
      conversion.amount_toman,
      JSON.stringify(conversion.items),
      receivedAt
    ).run();
    const changes = Number(result?.meta?.changes || 0);
    return jsonResponse({
      ok: true,
      stored: changes > 0,
      duplicate_or_older_event: changes === 0,
      conversion_id: conversion.conversion_id,
      status: conversion.status
    });
  } catch (error) {
    console.error("AFFILIO_POSTBACK_WRITE_FAILED", String(error).slice(0, 160));
    return jsonResponse({ ok: false, error: "conversion_storage_failed" }, 503);
  }
}

async function readAffilioConversionReport(request, env) {
  if (request.method !== "GET") {
    return new Response("Method not allowed", { status: 405, headers: { "Allow": "GET" } });
  }
  if (!env.AFFILIO_REPORT_TOKEN) {
    return jsonResponse({ ok: false, error: "conversion_reporting_not_configured" }, 503);
  }
  const authorization = request.headers.get("authorization") || "";
  if (!constantTimeEqual(authorization, "Bearer " + env.AFFILIO_REPORT_TOKEN)) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }
  if (!env.DB) return jsonResponse({ ok: false, error: "conversion_database_unavailable" }, 503);

  const url = new URL(request.url);
  const rawDays = Number(url.searchParams.get("days") || 30);
  const days = Number.isFinite(rawDays) ? Math.max(1, Math.min(365, Math.floor(rawDays))) : 30;
  const since = new Date(Date.now() - days * 86400000).toISOString();
  try {
    const result = await env.DB.prepare(
      `SELECT conversion_id, type, status, timestamp, aff_sub, payout_toman, amount_toman
       FROM (
         SELECT conversion_id, type, status, timestamp, aff_sub, payout_toman, amount_toman,
           ROW_NUMBER() OVER (
             PARTITION BY conversion_id
             ORDER BY timestamp DESC,
               CASE status WHEN 'approved' THEN 3 WHEN 'declined' THEN 2 ELSE 1 END DESC
           ) AS latest_rank
         FROM affilio_conversions
         WHERE timestamp >= ?
       )
       WHERE latest_rank = 1
       ORDER BY timestamp DESC`
    ).bind(since).all();
    const rows = Array.isArray(result?.results) ? result.results : [];
    const totals = {
      conversions: rows.length,
      sales_pending: 0,
      sales_approved: 0,
      sales_declined: 0,
      sales_amount_pending_toman: 0,
      sales_amount_approved_toman: 0,
      commission_pending_toman: 0,
      commission_approved_toman: 0,
      commission_declined_toman: 0,
      commission_unknown_count: 0
    };
    const bySource = Object.create(null);
    const byProduct = Object.create(null);
    const byAffSub = Object.create(null);
    const getGroup = (container, key) => {
      if (!container[key]) {
        container[key] = {
          conversions: 0, sales_pending: 0, sales_approved: 0, sales_declined: 0,
          sales_amount_approved_toman: 0, commission_approved_toman: 0,
          commission_pending_toman: 0
        };
      }
      return container[key];
    };
    for (const row of rows) {
      const attribution = parseOfferChinAffSub(row.aff_sub);
      const source = attribution.source;
      const productId = attribution.product_id;
      const groups = [
        getGroup(bySource, source),
        getGroup(byProduct, productId),
        getGroup(byAffSub, row.aff_sub || "unattributed")
      ];
      totals.conversions += 0;
      for (const group of groups) group.conversions += 1;
      if (row.type === "sale") {
        const statusKey = row.status === "approved" ? "sales_approved"
          : row.status === "declined" ? "sales_declined" : "sales_pending";
        totals[statusKey] += 1;
        for (const group of groups) group[statusKey] += 1;
        if (row.amount_toman != null) {
          if (row.status === "approved") {
            totals.sales_amount_approved_toman += Number(row.amount_toman) || 0;
            for (const group of groups) group.sales_amount_approved_toman += Number(row.amount_toman) || 0;
          } else if (row.status === "pending") {
            totals.sales_amount_pending_toman += Number(row.amount_toman) || 0;
          }
        }
      }
      if (row.payout_toman == null) {
        totals.commission_unknown_count += 1;
      } else if (row.status === "approved") {
        totals.commission_approved_toman += Number(row.payout_toman) || 0;
        for (const group of groups) group.commission_approved_toman += Number(row.payout_toman) || 0;
      } else if (row.status === "pending") {
        totals.commission_pending_toman += Number(row.payout_toman) || 0;
        for (const group of groups) group.commission_pending_toman += Number(row.payout_toman) || 0;
      } else if (row.status === "declined") {
        totals.commission_declined_toman += Number(row.payout_toman) || 0;
      }
    }
    return jsonResponse({
      ok: true,
      source: "affilio_conversion_postback",
      currency: "Toman",
      days,
      since,
      generated_at: new Date().toISOString(),
      totals,
      by_source: bySource,
      by_product: byProduct,
      by_aff_sub: byAffSub,
      note: "Approved commission only; pending and declined conversions are reported separately."
    });
  } catch (error) {
    console.error("AFFILIO_CONVERSION_REPORT_FAILED", String(error).slice(0, 160));
    return jsonResponse({ ok: false, error: "conversion_report_unavailable" }, 503);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/affilio/postback") {
      return receiveAffilioPostback(request, env);
    }
    if (url.pathname === "/affilio/report") {
      return readAffilioConversionReport(request, env);
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { "Allow": "GET, HEAD" } });
    }
    if (url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "affiliate-deal-radar",
        clickStoreReady: !!env.CLICKS,
        experimentAttribution: true,
        captionExperimentAttribution: true,
        conversionPostbackReady: !!env.DB && !!env.AFFILIO_POSTBACK_TOKEN,
        conversionReportingReady: !!env.DB && !!env.AFFILIO_REPORT_TOKEN,
        routes: ["/health", "/stats", "/affilio/postback (POST)", "/affilio/report (authenticated GET)", "/p/<dkp-or-snp-product-id>?u=<verified-aflo-link>&src=<telegram|bale|youtube|aparat>&exp=<visual-experiment>&variant=<a|b>&cexp=<caption-experiment>&cvariant=<a|b>"],
        stats: "Clicks remain separate from Affilio orders, sales and approved commission"
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