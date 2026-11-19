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
  assert.equal(body.conversionPostbackConfigured, false);
  assert.match(body.routes.join(" "), /postback\\/affilio/);
  assert.match(
    body.routes.join(" "),
    /telegram\|bale\|rubika\|eitaa\|youtube\|aparat\|filo/,
  );
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

test("all seven OfferChin media retain distinct click-source attribution", async () => {
  const CLICKS = mockKV();
  const productId = "dkp-123456";
  const productUrl = "https://www.digikala.com/product/dkp-123456/";
  const affiliateUrl = "https://aflo.ir/QekEYTRg?p=" + encodeURIComponent(productUrl);
  const channels = ["telegram", "bale", "rubika", "eitaa", "youtube", "aparat", "filo"];

  for (const channel of channels) {
    const response = await worker.fetch(
      new Request(
        "https://worker.example/p/" + productId +
          "?u=" + encodeURIComponent(affiliateUrl) + "&src=" + channel,
        { headers: { "user-agent": "Mozilla/5.0 test browser" } },
      ),
      { CLICKS },
    );
    assert.equal(response.status, 302, channel);
    assert.equal(response.headers.get("location"), affiliateUrl, channel);
  }

  const statsResponse = await worker.fetch(
    new Request("https://worker.example/stats"),
    { CLICKS },
  );
  const stats = await statsResponse.json();
  assert.equal(stats.totalClicks, channels.length);
  for (const channel of channels) {
    assert.equal(stats.sources[channel], 1, channel);
    assert.equal(stats.productSources[productId][channel], 1, channel);
  }
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


test("Affilio postback stays disabled until a secret is configured", async () => {
  const response = await worker.fetch(
    new Request("https://worker.example/postback/affilio", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "anything" },
      body: JSON.stringify({ conversion_id: "conv-1", type: "sale", status: "pending", timestamp: "2026-11-19T17:00:00Z", payout: null, amount: 1000 })
    }),
    { CLICKS: mockKV() },
  );
  assert.equal(response.status, 503);
  assert.equal((await response.json()).error, "postback_not_configured");
});

test("Affilio postback rejects invalid tokens and malformed conversion data", async () => {
  const CLICKS = mockKV();
  const payload = {
    conversion_id: "conv-2026-1",
    type: "sale",
    status: "pending",
    timestamp: "2026-11-19T17:00:00Z",
    aff_sub: "oc_dkp123_telegram",
    payout: null,
    amount: 125000,
    items: [{ quantity: 1, price: 125000 }]
  };
  const unauthorized = await worker.fetch(
    new Request("https://worker.example/postback/affilio", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "wrong" },
      body: JSON.stringify(payload)
    }),
    { CLICKS, AFFILIO_POSTBACK_TOKEN: "correct-secret" },
  );
  assert.equal(unauthorized.status, 401);
  assert.equal(CLICKS.values.size, 0);

  const malformed = await worker.fetch(
    new Request("https://worker.example/postback/affilio", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "correct-secret" },
      body: JSON.stringify({ ...payload, aff_sub: "invalid source!" })
    }),
    { CLICKS, AFFILIO_POSTBACK_TOKEN: "correct-secret" },
  );
  assert.equal(malformed.status, 400);
  assert.equal(CLICKS.values.size, 0);
});

test("Affilio postback stores pending, approved and declined events idempotently", async () => {
  const CLICKS = mockKV();
  const token = "test-postback-secret";
  const base = {
    conversion_id: "conv-2026-2",
    type: "sale",
    timestamp: "2026-11-19T17:00:00Z",
    aff_sub: "oc_dkp123_bale",
    amount: 250000,
    items: [{ quantity: 2, price: 125000 }]
  };
  const send = async (status, payout) => worker.fetch(
    new Request("https://worker.example/postback/affilio", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": token },
      body: JSON.stringify({ ...base, status, payout })
    }),
    { CLICKS, AFFILIO_POSTBACK_TOKEN: token },
  );

  const pending = await send("pending", null);
  assert.equal(pending.status, 202);
  assert.deepEqual(await pending.json(), { ok: true, accepted: true, duplicate: false });

  const duplicatePending = await send("pending", null);
  assert.equal(duplicatePending.status, 200);
  assert.deepEqual(await duplicatePending.json(), { ok: true, accepted: true, duplicate: true });

  const approved = await send("approved", 18000);
  assert.equal(approved.status, 202);
  const declined = await send("declined", 0);
  assert.equal(declined.status, 202);

  assert.equal(CLICKS.values.size, 3);
  const pendingEvent = JSON.parse(CLICKS.values.get("affilio:conversion:v1:conv-2026-2:pending"));
  const approvedEvent = JSON.parse(CLICKS.values.get("affilio:conversion:v1:conv-2026-2:approved"));
  const declinedEvent = JSON.parse(CLICKS.values.get("affilio:conversion:v1:conv-2026-2:declined"));
  assert.equal(pendingEvent.payout, null);
  assert.equal(approvedEvent.payout, 18000);
  assert.equal(approvedEvent.status, "approved");
  assert.equal(approvedEvent.aff_sub, "oc_dkp123_bale");
  assert.equal(declinedEvent.payout, 0);
  assert.equal(declinedEvent.status, "declined");
});

test("Affilio postback endpoint accepts POST only and returns retryable failure when persistence is unavailable", async () => {
  const wrongMethod = await worker.fetch(
    new Request("https://worker.example/postback/affilio"),
    { CLICKS: mockKV(), AFFILIO_POSTBACK_TOKEN: "secret" },
  );
  assert.equal(wrongMethod.status, 405);
  assert.equal(wrongMethod.headers.get("allow"), "POST");

  const noStore = await worker.fetch(
    new Request("https://worker.example/postback/affilio", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Affilio-Token": "secret" },
      body: JSON.stringify({
        conversion_id: "conv-3",
        type: "lead",
        status: "pending",
        timestamp: "2026-11-19T17:00:00Z",
        payout: null
      })
    }),
    {
      AFFILIO_POSTBACK_TOKEN: "secret",
      CLICKS: { async get() { return null; }, async put() { throw new Error("kv unavailable"); } }
    },
  );
  assert.equal(noStore.status, 503);
  assert.equal((await noStore.json()).error, "conversion_persistence_failed");
});
