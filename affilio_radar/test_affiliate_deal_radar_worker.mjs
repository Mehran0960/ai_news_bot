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
