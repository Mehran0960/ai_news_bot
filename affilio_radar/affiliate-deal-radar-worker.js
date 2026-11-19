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

function constantTimeSecretMatch(expected, provided) {
  const encoder = new TextEncoder();
  const left = encoder.encode(String(expected || ""));
  const right = encoder.encode(String(provided || ""));
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index++) {
    difference |= (left[index] || 0) ^ (right[index] || 0);
  }
  return difference === 0 && left.length > 0;
}

function validMoney(value, nullable = false) {
  return (nullable && value === null) ||
    (Number.isSafeInteger(value) && value >= 0);
}

async function receiveAffilioPostback(request, env) {
  if (!env.AFFILIO_POSTBACK_TOKEN) {
    return jsonResponse({ ok: false, error: "postback_not_configured" }, 503);
  }
  if (!env.CLICKS) {
    return jsonResponse({ ok: false, error: "conversion_store_unavailable" }, 503);
  }
  if (!String(request.headers.get("content-type") || "").toLowerCase().includes("application/json")) {
    return jsonResponse({ ok: false, error: "content_type_must_be_json" }, 415);
  }
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (Number.isFinite(declaredLength) && declaredLength > 65536) {
    return jsonResponse({ ok: false, error: "payload_too_large" }, 413);
  }

  const suppliedToken = request.headers.get("X-Affilio-Token") || "";
  if (!constantTimeSecretMatch(env.AFFILIO_POSTBACK_TOKEN, suppliedToken)) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }

  let payload;
  try {
    const raw = await request.arrayBuffer();
    if (raw.byteLength > 65536) {
      return jsonResponse({ ok: false, error: "payload_too_large" }, 413);
    }
    payload = JSON.parse(new TextDecoder().decode(raw));
  } catch (_) {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return jsonResponse({ ok: false, error: "invalid_payload" }, 400);
  }

  const conversionId = String(payload.conversion_id || "").trim();
  const type = String(payload.type || "").trim();
  const status = String(payload.status || "").trim();
  const timestamp = String(payload.timestamp || "").trim();
  const validTypes = new Set(["sale", "lead", "action"]);
  const validStatuses = new Set(["pending", "approved", "declined"]);
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(conversionId) ||
      !validTypes.has(type) ||
      !validStatuses.has(status) ||
      !timestamp.endsWith("Z") ||
      !Number.isFinite(Date.parse(timestamp))) {
    return jsonResponse({ ok: false, error: "invalid_conversion_fields" }, 400);
  }

  const payout = payload.payout;
  if (!validMoney(payout, true)) {
    return jsonResponse({ ok: false, error: "invalid_payout" }, 400);
  }
  if ((status === "approved" && payout === null) || (status === "declined" && payout !== 0)) {
    return jsonResponse({ ok: false, error: "payout_inconsistent_with_status" }, 400);
  }
  if (type === "sale" && !validMoney(payload.amount)) {
    return jsonResponse({ ok: false, error: "invalid_sale_amount" }, 400);
  }
  const affSub = payload.aff_sub == null ? "" : String(payload.aff_sub);
  if (affSub && !/^[A-Za-z0-9_-]{1,255}$/.test(affSub)) {
    return jsonResponse({ ok: false, error: "invalid_aff_sub" }, 400);
  }

  let items = [];
  if (type === "sale" && payload.items != null) {
    if (!Array.isArray(payload.items) || payload.items.length > 100) {
      return jsonResponse({ ok: false, error: "invalid_sale_items" }, 400);
    }
    for (const item of payload.items) {
      if (!item || !Number.isSafeInteger(item.quantity) || item.quantity < 1 ||
          !validMoney(item.price)) {
        return jsonResponse({ ok: false, error: "invalid_sale_item" }, 400);
      }
      items.push({ quantity: item.quantity, price: item.price });
    }
  }

  // Append-only event keys make repeated callbacks idempotent by conversion_id + status.
  // A later approved/declined status is a separate event and never overwrites history.
  const key = "affilio:conversion:v1:" +
    encodeURIComponent(conversionId) + ":" + status;
  try {
    const existing = await env.CLICKS.get(key);
    if (existing != null) {
      return jsonResponse({ ok: true, accepted: true, duplicate: true }, 200);
    }
    const event = {
      schema_version: 1,
      source: "affilio_postback",
      conversion_id: conversionId,
      type,
      status,
      timestamp,
      aff_sub: affSub || null,
      payout,
      amount: type === "sale" ? payload.amount : null,
      items,
      received_at: new Date().toISOString()
    };
    await env.CLICKS.put(key, JSON.stringify(event), { expirationTtl: 31536000 });
  } catch (_) {
    // Return non-2xx so Affilio retries instead of silently losing a conversion.
    return jsonResponse({ ok: false, error: "conversion_persistence_failed" }, 503);
  }
  return jsonResponse({ ok: true, accepted: true, duplicate: false }, 202);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/postback/affilio") {
      if (request.method !== "POST") {
        return new Response("Method not allowed", { status: 405, headers: { "Allow": "POST" } });
      }
      return receiveAffilioPostback(request, env);
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
        routes: ["/health", "/stats", "/postback/affilio (POST; authenticated; disabled until secret is configured)", "/p/<dkp-or-snp-product-id>?u=<verified-aflo-link>&src=<telegram|bale|rubika|eitaa|youtube|aparat|filo>&exp=<visual-experiment>&variant=<a|b>&cexp=<caption-experiment>&cvariant=<a|b>"],
        conversionPostbackConfigured: Boolean(env.AFFILIO_POSTBACK_TOKEN && env.CLICKS),
        stats: "Aggregated product and source click counts for the last 30 days only"
      });
    }
    if (url.pathname === "/stats") {
      if (!env.CLICKS) return jsonResponse({ok:false,error:"click_store_unavailable"},503);
      const cacheKey = "analytics:clicks:30d:v5";
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
            const dual = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20})):((?:telegram|bale|rubika|eitaa|youtube|aparat|filo|unknown)):v:([a-z0-9][a-z0-9_-]{0,31}):([ab]):c:([a-z0-9][a-z0-9_-]{0,31}):([ab]):/);
            const current = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20})):((?:telegram|bale|rubika|eitaa|youtube|aparat|filo|unknown)):([a-z0-9][a-z0-9_-]{0,31}):([ab]):/);
            const legacy = keyName.match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20}))(?::(telegram|bale|rubika|eitaa|youtube|aparat|filo|unknown))?:/);
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
    const allowedSources = new Set(["telegram", "bale", "rubika", "eitaa", "youtube", "aparat", "filo"]);
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