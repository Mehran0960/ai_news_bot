import test from "node:test";
import assert from "node:assert/strict";
import {
  isUsableCleanCatalogSnapshot,
  isInitialCatalogWarmup,
  isDegradedLiveFallbackAvailable,
  PUBLISHER_INTERVAL_MS,
  readLastChannelPublicationAt,
} from "./affilio-minute-dispatcher.mjs";
const categoryIds = Array.from({ length: 4917 }, (_, index) => String(index + 1));
// Keep the canonical clean fixture inside the rolling 96-hour freshness window.
const cleanCycleCompletedAt = new Date(Date.now() - 60 * 60 * 1000).toISOString();
const cleanCycleStartedAt = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString();
const cleanStatus = {
  schema_version: 2,
  full_catalog_mode: "all_categories_all_pages",
  scan_policy_version: "all_categories_all_pages_v3_cycle_snapshot",
  last_cycle_status: "in_progress",
  last_clean_cycle_status: "complete",
  completed_candidates_snapshot_present: true,
  completed_candidates_snapshot_valid: true,
  completed_candidates_cycle_at: cleanCycleCompletedAt,
  completed_candidates_count: 3000,
  completed_candidates_sha256: "a".repeat(64),
  last_clean_cycle_started_at: cleanCycleStartedAt,
  last_clean_cycle_completed_at: cleanCycleCompletedAt,
  last_clean_cycle_categories_total: 4917,
  last_clean_cycle_categories_complete: 4917,
  last_clean_cycle_categories_unqueryable: 0,
  last_clean_cycle_category_coverage_percent: 100,
  last_clean_cycle_pages_success: 186820,
  last_clean_cycle_category_ids: categoryIds,
  last_clean_cycle_completed_category_ids: categoryIds,
  last_clean_cycle_unqueryable_category_ids: [],
  catalog_category_count: 4917,
  catalog_category_ids: categoryIds,
  completed_cycles: 1,
};

test("allows the first publication when a clean full-catalog snapshot exists", () => {
  assert.equal(isUsableCleanCatalogSnapshot(cleanStatus), true);
});

test("rejects a clean snapshot after its 96-hour freshness window", () => {
  const completedAt = new Date(Date.now() - 97 * 60 * 60 * 1000).toISOString();
  assert.equal(
    isUsableCleanCatalogSnapshot({
      ...cleanStatus,
      last_clean_cycle_completed_at: completedAt,
      completed_candidates_cycle_at: completedAt,
    }),
    false
  );
});

test("reuses the same clean snapshot after a publication while the next scan is running", () => {
  const status = {
    ...cleanStatus,
    last_cycle_status: "in_progress",
    last_cycle_completed_at: null,
    last_channel_published_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  };
  assert.equal(isUsableCleanCatalogSnapshot(status), true);
});

test("does not discard the last clean snapshot when a later scan has gaps", () => {
  const status = {
    ...cleanStatus,
    last_cycle_status: "complete_with_gaps",
    last_cycle_completed_at: null,
    last_cycle_categories_complete: 4900,
    last_cycle_categories_unqueryable: 17,
  };
  assert.equal(isUsableCleanCatalogSnapshot(status), true);
});

test("blocks a category-set replacement even when the category count is unchanged", () => {
  const changedIds = [...categoryIds];
  changedIds[0] = "new-category-id";
  assert.equal(
    isUsableCleanCatalogSnapshot({ ...cleanStatus, catalog_category_ids: changedIds }),
    false
  );
});

test("allows a small number of new categories while the last clean snapshot is fresh", () => {
  const newIds = [...categoryIds, "4918", "4919"];
  assert.equal(
    isUsableCleanCatalogSnapshot({
      ...cleanStatus,
      catalog_category_count: newIds.length,
      catalog_category_ids: newIds,
    }),
    true
  );
});

test("blocks a new-category backlog above one percent or fifty categories", () => {
  const additions = Array.from({ length: 51 }, (_, index) => String(100000 + index));
  const newIds = [...categoryIds, ...additions];
  assert.equal(
    isUsableCleanCatalogSnapshot({
      ...cleanStatus,
      catalog_category_count: newIds.length,
      catalog_category_ids: newIds,
    }),
    false
  );
});

test("blocks removal of any category covered by the last clean snapshot", () => {
  const removedIds = categoryIds.slice(0, -1);
  assert.equal(
    isUsableCleanCatalogSnapshot({
      ...cleanStatus,
      catalog_category_count: removedIds.length,
      catalog_category_ids: removedIds,
    }),
    false
  );
});

test("blocks incomplete, gapped, or malformed clean snapshots", () => {
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, last_clean_cycle_status: "complete_with_gaps" }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, last_clean_cycle_categories_unqueryable: 1 }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, last_clean_cycle_categories_complete: 4916 }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, last_clean_cycle_category_coverage_percent: 99.98 }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, completed_candidates_snapshot_valid: false }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, completed_candidates_sha256: "invalid" }), false);
});

test("allows legacy discovery only during the first catalog warm-up", () => {
  const warmup = {
    schema_version: 2,
    full_catalog_mode: "all_categories_all_pages",
    scan_policy_version: "all_categories_all_pages_v3_cycle_snapshot",
    completed_cycles: 0,
    last_clean_cycle_status: "unavailable",
    completed_candidates_snapshot_present: false,
    completed_candidates_snapshot_valid: false,
    last_clean_cycle_completed_at: null,
  };
  assert.equal(isInitialCatalogWarmup(warmup), true);
  assert.equal(isInitialCatalogWarmup({ ...warmup, completed_candidates_snapshot_present: true }), false);
  assert.equal(isInitialCatalogWarmup({ ...warmup, completed_cycles: 1 }), false);
  assert.equal(isInitialCatalogWarmup(null), false);
});

test("degraded live fallback requires a complete numeric DigiKala taxonomy registry", () => {
  const degraded = {
    schema_version: 2,
    full_catalog_mode: "all_categories_all_pages",
    scan_policy_version: "all_categories_all_pages_v3_cycle_snapshot",
    last_clean_cycle_status: "unavailable",
    completed_candidates_snapshot_present: true,
    completed_candidates_snapshot_valid: false,
    catalog_category_count: 3,
    catalog_category_ids: ["1", "2", "3"],
  };
  assert.equal(isUsableCleanCatalogSnapshot(degraded), false);
  assert.equal(isDegradedLiveFallbackAvailable(degraded), true);
  assert.equal(isDegradedLiveFallbackAvailable({
    ...degraded, catalog_category_ids: ["1", "2"]
  }), false);
  assert.equal(isDegradedLiveFallbackAvailable({
    ...degraded, catalog_category_ids: ["1", "2", "2"]
  }), false);
  assert.equal(isDegradedLiveFallbackAvailable({
    ...degraded, catalog_category_ids: ["1", "2", "x"]
  }), false);
  assert.equal(isDegradedLiveFallbackAvailable(null), false);
});

test("fails closed on missing, stale-schema, or partial-scan status", () => {
  assert.equal(isUsableCleanCatalogSnapshot(null), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, schema_version: 1 }), false);
  assert.equal(isUsableCleanCatalogSnapshot({ ...cleanStatus, scan_policy_version: "top_60_only" }), false);
});


test("uses a 27-minute channel publication interval", () => {
  assert.equal(PUBLISHER_INTERVAL_MS, 27 * 60 * 1000);
});

test("channel cadence clock recognizes every active publishing channel", () => {
  const publishedAt = Date.parse("2026-11-08T01:00:00Z");
  const base = { ts: publishedAt / 1000 };
  for (const channel of ["telegram", "bale", "rubika", "eitaa"]) {
    assert.equal(
      readLastChannelPublicationAt({
        published: { item: { ...base, delivery_status: { [channel]: "sent" } } },
      }),
      publishedAt,
      channel
    );
  }
  assert.equal(
    readLastChannelPublicationAt({
      published: { item: { ...base, delivery_status: { telegram: "pending" } } },
    }),
    null
  );
  const preciseSendTime = "2026-11-08T01:23:45Z";
  assert.equal(
    readLastChannelPublicationAt({
      last_channel_published_at: preciseSendTime,
      published: { item: base },
    }),
    Date.parse(preciseSendTime),
    "use the actual successful-send time instead of the earlier queue timestamp"
  );
});

