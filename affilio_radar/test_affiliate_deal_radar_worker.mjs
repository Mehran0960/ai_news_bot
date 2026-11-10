import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { webcrypto } from "node:crypto";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

const workerSource = await readFile(
  new URL("./affiliate-deal-radar-worker.js", import.meta.url),
  "utf8",
);
const moduleUrl = "data:text/javascript;base64," + Buffer.from(workerSource).toString("base64");
const { default: worker } = await import(moduleUrl);

function mockKV() {
  const values = new Map();
  return {
    values,
    async get(key, type) {
      const value = values.get(key);
      if (value == null) return null;
      return type === "json" && typeof value === "string" ? JSON.parse(value) : value;
    },
    async put(key, value) {
      values.set(key, value);
    },
    async list({ prefix }) {
      return {
        keys: [...values.keys()]
          .filter((key) => key.startsWith(prefix))
          .map((name) => ({ name })),
        list_complete: true,
      };
    },
  };
}

test("health advertises experiment attribution support", async () => {
  const response = await worker.fetch(
    new Request("https://worker.example/health"),
    { CLICKS: mockKV() },
  );
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.ok, true);
  assert.equal(body.clickStoreReady, true);
  assert.equal(body.experimentAttribution, true);
  assert.equal(body.captionExperimentAttribution, true);
});

test("product redirects store source and A/B attribution and expose it in stats", async () => {
  const CLICKS = mockKV();
  const productId = "dkp-123456";
  const productUrl = "https://www.digikala.com/product/dkp-123456/";
  const affiliateUrl = "https://aflo.ir/QekEYTRg?p=" + encodeURIComponent(productUrl);
  const request = new Request(
    "https://worker.example/p/" + productId +
      "?u=" + encodeURIComponent(affiliateUrl) +
      "&src=telegram&exp=creative-test-1&variant=b&cexp=caption-test-1&cvariant=a",
    { headers: { "user-agent": "Mozilla/5.0 test browser" } },
  );
  const response = await worker.fetch(request, { CLICKS });
  assert.equal(response.status, 302);
  assert.equal(response.headers.get("location"), affiliateUrl);

  const keys = [...CLICKS.values.keys()].filter((key) => key.startsWith("click:"));
  assert.equal(keys.length, 1);
  assert.match(keys[0], /:dkp-123456:telegram:v:creative-test-1:b:c:caption-test-1:a:/);
  const event = JSON.parse(CLICKS.values.get(keys[0]));
  assert.equal(event.product_id, productId);
  assert.equal(event.channel, "telegram");
  assert.equal(event.experiment, "creative-test-1");
  assert.equal(event.variant, "B");
  assert.equal(event.caption_experiment, "caption-test-1");
  assert.equal(event.caption_variant, "A");

  const statsResponse = await worker.fetch(
    new Request("https://worker.example/stats"),
    { CLICKS },
  );
  assert.equal(statsResponse.status, 200);
  const stats = await statsResponse.json();
  assert.equal(stats.complete, true);
  assert.equal(stats.products[productId], 1);
  assert.equal(stats.sources.telegram, 1);
  assert.equal(stats.experimentVariants["creative-test-1:B"], 1);
  assert.equal(stats.visualExperimentVariants["creative-test-1:B"], 1);
  assert.equal(stats.captionExperimentVariants["caption-test-1:A"], 1);
  assert.equal(stats.productCaptionExperimentVariants[productId]["caption-test-1:A"], 1);
});

test("HEAD validation does not create a click event", async () => {
  const CLICKS = mockKV();
  const productUrl = "https://snappshop.ir/product/snp-123456";
  const affiliateUrl = "https://aflo.ir/QekEYTRg?p=" + encodeURIComponent(productUrl);
  const response = await worker.fetch(
    new Request(
      "https://worker.example/p/snp-123456?u=" + encodeURIComponent(affiliateUrl) + "&src=bale",
      { method: "HEAD" },
    ),
    { CLICKS },
  );
  assert.equal(response.status, 302);
  assert.equal(CLICKS.values.size, 0);
});


function mockD1() {
  const events = new Map();
  const current = new Map();
  function aggregate(rows) {
    return rows.reduce((acc, row) => ({
      confirmedOrderCount: acc.confirmedOrderCount + 1,
      unitsSold: acc.unitsSold + Number(row.units_sold || 0),
      salesAmountToman: acc.salesAmountToman + Number(row.amount_toman || 0),
      approvedCommissionToman: acc.approvedCommissionToman + Number(row.payout_toman || 0),
    }), { confirmedOrderCount: 0, unitsSold: 0, salesAmountToman: 0, approvedCommissionToman: 0 });
  }
  return {
    events,
    current,
    prepare(sql) {
      let params = [];
      return {
        bind(...values) { params = values; return this; },
        async run() {
          if (sql.startsWith("INSERT OR IGNORE INTO affilio_conversion_events")) {
            const key = String(params[0]) + "|" + String(params[1]);
            if (!events.has(key)) events.set(key, [...params]);
            return { success: true };
          }
          if (sql.startsWith("INSERT INTO affilio_conversion_current")) {
            const row = {
              conversion_id: params[0], status: params[1], status_rank: params[2],
              timestamp_ms: params[3], conversion_type: params[4], aff_sub: params[5],
              product_id: params[6], channel: params[7], creative_experiment_id: params[8],
              creative_variant: params[9], caption_experiment_id: params[10],
              caption_variant: params[11], payout_toman: params[12], amount_toman: params[13],
              units_sold: params[14], items_json: params[15], received_at_ms: params[16],
            };
            const previous = current.get(row.conversion_id);
            if (!previous || row.timestamp_ms > previous.timestamp_ms ||
                (row.timestamp_ms === previous.timestamp_ms &&
                 (row.status_rank > previous.status_rank ||
                  (row.status_rank === previous.status_rank && row.received_at_ms > previous.received_at_ms)))) {
              current.set(row.conversion_id, row);
            }
            return { success: true };
          }
          throw new Error("unexpected mock D1 write");
        },
        async all() {
          const since = Number(params[0] || 0);
          const rows = [...current.values()].filter((row) => row.timestamp_ms >= since);
          if (sql.startsWith("SELECT status,conversion_type,COUNT(*)")) {
            const grouped = new Map();
            for (const row of rows) {
              const key = row.conversion_type + ":" + row.status;
              grouped.set(key, (grouped.get(key) || 0) + 1);
            }
            return { results: [...grouped.entries()].map(([key, count]) => {
              const [conversion_type, status] = key.split(":");
              return { conversion_type, status, count };
            }) };
          }
          if (sql.startsWith("SELECT COUNT(*) AS confirmedOrderCount")) {
            const approved = rows.filter((row) => row.conversion_type === "sale" && row.status === "approved");
            return { results: [aggregate(approved)] };
          }
          if (sql.includes("GROUP BY")) {
            const approved = rows.filter((row) => row.conversion_type === "sale" && row.status === "approved");
            const grouped = new Map();
            for (const row of approved) {
              let key = null;
              if (sql.includes("GROUP BY product_id")) key = row.product_id;
              else if (sql.includes("GROUP BY channel")) key = row.channel;
              else if (sql.includes("GROUP BY creative_experiment_id")) {
                key = row.creative_experiment_id && row.creative_variant
                  ? row.creative_experiment_id + ":" + row.creative_variant : null;
              } else if (sql.includes("GROUP BY caption_experiment_id")) {
                key = row.caption_experiment_id && row.caption_variant
                  ? row.caption_experiment_id + ":" + row.caption_variant : null;
              }
              if (!key) continue;
              if (!grouped.has(key)) grouped.set(key, []);
              grouped.get(key).push(row);
            }
            return { results: [...grouped.entries()].map(([group_key, groupRows]) => ({
              group_key, ...aggregate(groupRows),
            })) };
          }
          throw new Error("unexpected mock D1 query");
        },
      };
    },
  };
}

function postbackRequest(payload, token = "test-shared-token") {
  return new Request("https://worker.example/affilio/postback", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Affilio-Token": token,
    },
    body: JSON.stringify(payload),
  });
}

test("Affilio postback requires token and returns retryable status until configured", async () => {
  const payload = {
    conversion_id: "conversion-unauthenticated",
    type: "sale",
    status: "pending",
    timestamp: new Date().toISOString(),
    payout: null,
    amount: 1000,
    items: [],
  };
  const noSecret = await worker.fetch(postbackRequest(payload), { CONVERSIONS: mockD1() });
  assert.equal(noSecret.status, 503);
  const wrongSecret = await worker.fetch(postbackRequest(payload, "wrong"), {
    CONVERSIONS: mockD1(),
    AFFILIO_POSTBACK_TOKEN: "test-shared-token",
  });
  assert.equal(wrongSecret.status, 401);
  const badContentType = await worker.fetch(new Request("https://worker.example/affilio/postback", {
    method: "POST",
    headers: { "X-Affilio-Token": "test-shared-token", "content-type": "text/plain" },
    body: "not-json",
  }), { CONVERSIONS: mockD1(), AFFILIO_POSTBACK_TOKEN: "test-shared-token" });
  assert.equal(badContentType.status, 415);
});

test("Affilio postbacks deduplicate conversion/status and apply newer status despite out-of-order delivery", async () => {
  const CONVERSIONS = mockD1();
  const env = { CONVERSIONS, AFFILIO_POSTBACK_TOKEN: "test-shared-token" };
  const now = Date.now();
  const affSub = "oc1-dkp-123456-telegram-v-creative-test-1-b-c-caption-test-1-a";
  const base = {
    conversion_id: "conversion-sale-001",
    type: "sale",
    timestamp: new Date(now - 90000).toISOString(),
    aff_sub: affSub,
    payout: null,
    amount: 87000,
    items: [{ quantity: 2, price: 65000 }],
  };
  const pending = { ...base, status: "pending" };
  const approved = {
    ...base,
    status: "approved",
    timestamp: new Date(now - 60000).toISOString(),
    payout: 12500,
  };
  for (const body of [pending, approved, approved, pending]) {
    const response = await worker.fetch(postbackRequest(body), env);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).accepted, true);
  }
  assert.equal(CONVERSIONS.events.size, 2, "duplicate status pairs must be stored once");
  assert.equal(CONVERSIONS.current.size, 1);
  const latest = CONVERSIONS.current.get("conversion-sale-001");
  assert.equal(latest.status, "approved", "late pending must not overwrite a newer approved state");
  assert.equal(latest.product_id, "dkp-123456");
  assert.equal(latest.channel, "telegram");
  assert.equal(latest.creative_experiment_id, "creative-test-1");
  assert.equal(latest.creative_variant, "B");
  assert.equal(latest.caption_experiment_id, "caption-test-1");
  assert.equal(latest.caption_variant, "A");

  const statsResponse = await worker.fetch(new Request("https://worker.example/conversions/stats", {
    headers: { "X-Affilio-Token": "test-shared-token" },
  }), env);
  assert.equal(statsResponse.status, 200);
  const stats = await statsResponse.json();
  assert.equal(stats.complete, true);
  assert.equal(stats.days, 30);
  assert.equal(stats.summary.confirmedOrderCount, 1);
  assert.equal(stats.summary.unitsSold, 2);
  assert.equal(stats.summary.salesAmountToman, 87000);
  assert.equal(stats.summary.approvedCommissionToman, 12500);
  assert.equal(stats.byProduct["dkp-123456"].confirmedOrderCount, 1);
  assert.equal(stats.byChannel.telegram.confirmedOrderCount, 1);
  assert.equal(stats.byCreativeVariant["creative-test-1:B"].confirmedOrderCount, 1);
  assert.equal(stats.byCaptionVariant["caption-test-1:A"].confirmedOrderCount, 1);

  const declined = {
    ...base,
    status: "declined",
    timestamp: new Date(now - 30000).toISOString(),
    payout: 0,
  };
  const declinedResponse = await worker.fetch(postbackRequest(declined), env);
  assert.equal(declinedResponse.status, 200);
  const afterDecline = await (await worker.fetch(new Request("https://worker.example/conversions/stats", {
    headers: { "X-Affilio-Token": "test-shared-token" },
  }), env)).json();
  assert.equal(afterDecline.summary.confirmedOrderCount, 0, "declined sale must be removed from confirmed purchase totals");
  assert.equal(afterDecline.summary.declinedSaleCount, 1);
});

test("Affilio non-sale actions and invalid attribution never inflate product purchase totals", async () => {
  const CONVERSIONS = mockD1();
  const env = { CONVERSIONS, AFFILIO_POSTBACK_TOKEN: "test-shared-token" };
  const action = {
    conversion_id: "conversion-action-001",
    type: "action",
    status: "approved",
    timestamp: new Date().toISOString(),
    aff_sub: "oc1-dkp-123456-telegram",
    payout: 8000,
  };
  const actionResponse = await worker.fetch(postbackRequest(action), env);
  assert.equal(actionResponse.status, 200);
  const invalid = await worker.fetch(postbackRequest({
    ...action,
    conversion_id: "conversion-invalid-sub",
    aff_sub: "bad sub value",
  }), env);
  assert.equal(invalid.status, 400);
  const stats = await (await worker.fetch(new Request("https://worker.example/conversions/stats", {
    headers: { "X-Affilio-Token": "test-shared-token" },
  }), env)).json();
  assert.equal(stats.summary.confirmedOrderCount, 0);
  assert.equal(stats.summary.approvedActionCount, 1);
  assert.equal(stats.byProduct["dkp-123456"], undefined);
});
