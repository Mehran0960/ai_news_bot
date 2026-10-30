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
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { "Allow": "GET, HEAD" } });
    }
    if (url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "affiliate-deal-radar",
        clickStoreReady: !!env.CLICKS,
        routes: ["/health", "/stats", "/p/<dkp-or-snp-product-id>?u=<verified-aflo-link>&src=<telegram|bale|youtube|aparat>"],
        stats: "Aggregated product and source click counts for the last 30 days only"
      });
    }
    if (url.pathname === "/stats") {
      if (!env.CLICKS) return jsonResponse({ok:false,error:"click_store_unavailable"},503);
      const cacheKey = "analytics:clicks:30d:v2";
      try {
        const cached = await env.CLICKS.get(cacheKey, "json");
        if (
          cached &&
          cached.ok === true &&
          cached.updatedAt &&
          cached.products && typeof cached.products === "object"
        ) {
          return jsonResponse(cached);
        }
      } catch (_) {}

      const now = new Date();
      const today = now.toISOString().slice(0, 10);
      const products = Object.create(null);
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
            const match = String(key.name || "").match(/^click:(\d{4}-\d{2}-\d{2}):((?:dkp-\d{1,12})|(?:snp-\d{1,20}))(?::(?:telegram|bale|youtube|aparat|unknown))?:/);
            if (match) {
              const productId = match[2];
              products[productId] = (products[productId] || 0) + 1;
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
        products
      };
      try {
        await env.CLICKS.put(cacheKey, JSON.stringify(result), {expirationTtl:120});
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

    const ua = request.headers.get("user-agent") || "";
    const likelyPreviewBot = /(telegrambot|facebookexternalhit|whatsapp|slackbot|discordbot|twitterbot|linkedinbot|googlebot|bingbot|yandexbot|crawler|spider|\bbot\b)/i.test(ua);
    if (request.method === "GET" && !likelyPreviewBot && env.CLICKS) {
      const now = new Date();
      const stamp = now.toISOString();
      const day = stamp.slice(0, 10);
      const eventKey = "click:" + day + ":" + productId + ":" + source + ":" + now.getTime() + "-" + crypto.randomUUID();
      try {
        // Store only product ID, timestamp and a fixed source label; no IPs, referrers or full affiliate URLs.
        await env.CLICKS.put(eventKey, JSON.stringify({
          product_id: productId,
          clicked_at: stamp,
          channel: source
        }), {expirationTtl:15552000});
      } catch (error) {
        console.error("CLICK_WRITE_FAILED", productId, String(error).slice(0,100));
      }
    }
    return Response.redirect(destination.toString(), 302);
  }
};