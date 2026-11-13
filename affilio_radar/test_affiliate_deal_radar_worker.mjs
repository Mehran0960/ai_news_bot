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


function mockD1() {
  const rows = new Map();
  return {
    rows,
    prepare(sql) {
      let params = [];
      return {
        bind(...values) {
          params = values;
          return this;
        },
        async run() {
          assert.match(sql, /INSERT INTO affilio_conversions/);
          const [conversionId, status, type, timestamp, affSub, payout, amount, items, receivedAt] = params;
          const key = conversionId + ":" + status;
          const previous = rows.get(key);
          if (previous && previous.timestamp >= timestamp) return { meta: { changes: 0 } };
          rows.set(key, {
            conversion_id: conversionId,
            status,
            type,
            timestamp,
            aff_sub: affSub,
            payout_toman: payout,
            amount_toman: amount,
            items_json: items,
            received_at: receivedAt,
          });
          return { meta: { changes: 1 } };
        },
        async all() {
          assert.match(sql, /FROM affilio_conversions/);
          const [since] = params;
          const latest = new Map();
          for (const row of rows.values()) {
            if (row.timestamp < since) continue;
            const previous = latest.get(row.conversion_id);
            const priority = (status) => status === "approved" ? 3 : status === "declined" ? 2 : 1;
            if (
              !previous ||
              row.timestamp > previous.timestamp ||
              (row.timestamp === previous.timestamp && priority(row.status) > priority(previous.status))
            ) latest.set(row.conversion_id, row);
          }
          return { results: [...latest.values()] };
        },
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
  assert.equal(body.conversionPostbackReady, false);
  assert.equal(body.conversionReportingReady, false);
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


test("Affilio postback stores pending and approved events idempotently and attributes by aff_sub", async () => {
  const DB = mockD1();
  const env = {
    CLICKS: mockKV(),
    DB,
    AFFILIO_POSTBACK_TOKEN: "postback-secret",
    AFFILIO_REPORT_TOKEN: "report-secret",
  };
  const pending = {
    conversion_id: "conv-2026-001",
    type: "sale",
    status: "pending",
    timestamp: "2026-11-13T10:00:00.000Z",
    aff_sub: "oc1_telegram_dkp-123456",
    payout: null,
    amount: 2_000_000,
    items: [{ quantity: 1, unit_price: 2_000_000 }],
  };
  const send = (payload) => worker.fetch(
    new Request("https://worker.example/affilio/postback", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Affilio-Token": "postback-secret",
      },
      body: JSON.stringify(payload),
    }),
    env,
  );
  const first = await send(pending);
  assert.equal(first.status, 200);
  assert.equal((await first.json()).stored, true);
  const duplicate = await send(pending);
  assert.equal(duplicate.status, 200);
  assert.equal((await duplicate.json()).duplicate_or_older_event, true);
  assert.equal(DB.rows.size, 1);

  const approved = {
    ...pending,
    status: "approved",
    timestamp: "2026-11-13T11:00:00.000Z",
    payout: 80_000,
  };
  const finalEvent = await send(approved);
  assert.equal(finalEvent.status, 200);
  assert.equal((await finalEvent.json()).stored, true);

  // A delayed/older pending retry must not overwrite the approved event.
  const lateRetry = await send(pending);
  assert.equal(lateRetry.status, 200);
  assert.equal((await lateRetry.json()).duplicate_or_older_event, true);

  const reportResponse = await worker.fetch(
    new Request("https://worker.example/affilio/report?days=30", {
      headers: { authorization: "Bearer report-secret" },
    }),
    env,
  );
  assert.equal(reportResponse.status, 200);
  const report = await reportResponse.json();
  assert.equal(report.ok, true);
  assert.equal(report.totals.conversions, 1);
  assert.equal(report.totals.sales_pending, 0);
  assert.equal(report.totals.sales_approved, 1);
  assert.equal(report.totals.sales_amount_approved_toman, 2_000_000);
  assert.equal(report.totals.commission_approved_toman, 80_000);
  assert.equal(report.by_source.telegram.sales_approved, 1);
  assert.equal(report.by_product["dkp-123456"].commission_approved_toman, 80_000);
  assert.equal(report.by_aff_sub["oc1_telegram_dkp-123456"].sales_approved, 1);
});

test("Affilio postback rejects invalid credentials, malformed payloads and unsupported statuses", async () => {
  const DB = mockD1();
  const env = { DB, AFFILIO_POSTBACK_TOKEN: "postback-secret" };
  const url = "https://worker.example/affilio/postback";
  const payload = {
    conversion_id: "conv-002",
    type: "sale",
    status: "pending",
    timestamp: "2026-11-13T10:00:00.000Z",
    amount: 500_000,
  };
  const unauthorized = await worker.fetch(
    new Request(url, {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "wrong" },
      body: JSON.stringify(payload),
    }),
    env,
  );
  assert.equal(unauthorized.status, 401);
  assert.equal(DB.rows.size, 0);

  const malformed = await worker.fetch(
    new Request(url, {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "postback-secret" },
      body: JSON.stringify({ ...payload, status: "completed" }),
    }),
    env,
  );
  assert.equal(malformed.status, 400);
  assert.equal(DB.rows.size, 0);
});

test("Affilio conversion report requires its own read-only secret", async () => {
  const response = await worker.fetch(
    new Request("https://worker.example/affilio/report?days=30"),
    { DB: mockD1(), AFFILIO_REPORT_TOKEN: "report-secret" },
  );
  assert.equal(response.status, 401);
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
