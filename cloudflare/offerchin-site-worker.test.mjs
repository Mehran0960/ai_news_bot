import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(new URL("./offerchin-site-worker.mjs", import.meta.url), "utf8");
const htmlMatch = source.match(/const PAGE_HTML = String\\.raw\`([\\s\\S]*?)\`;\\nconst ROBOTS/);
assert.ok(htmlMatch, "Worker must keep the storefront HTML in PAGE_HTML");
const page = htmlMatch[1];

test("legacy Worker purchase CTA uses the original Affilio URL, not a tracker", () => {
  assert.doesNotMatch(page, /affiliate-deal-radar|TRACKER|trackedUrl/);
  assert.match(page, /function validAffilioUrl/);
  assert.match(page, /clickUrl = directVerified \? candidate\.affiliate_url/);
  assert.match(page, /href=\\"' \+ escapeHtml\(o\.click_url\)/);
});

test("embedded validator accepts only the public Affilio link for the matching product", () => {
  const helperMatch = page.match(
    /function canonicalProductUrl\(raw, id\)\{[\\s\\S]*?\\n      \}\\n      function validAffilioUrl\(id, raw\)\{[\\s\\S]*?\\n      \}/
  );
  assert.ok(helperMatch, "canonical destination and Affilio validators must be present");
  const validAffilioUrl = new Function(`${helperMatch[0]}; return validAffilioUrl;`)();

  const valid = "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-123456%2F";
  const tracker = "https://affiliate-deal-radar.m-hoseyni-6966.workers.dev/p/dkp-123456?u=" + encodeURIComponent(valid);
  const wrongProduct = "https://aflo.ir/QekEYTRg?p=https%3A%2F%2Fwww.digikala.com%2Fproduct%2Fdkp-999999%2F";

  assert.equal(validAffilioUrl("dkp-123456", valid), true);
  assert.equal(validAffilioUrl("dkp-123456", tracker), false);
  assert.equal(validAffilioUrl("dkp-123456", wrongProduct), false);
});

test("legacy Worker orders by demand before deal appeal and never by clicks", () => {
  assert.match(page, /items\.sort\(function\(a,b\)\{return b\.demand_score-a\.demand_score/);
  assert.doesNotMatch(page, /click_count_30d/);
});
