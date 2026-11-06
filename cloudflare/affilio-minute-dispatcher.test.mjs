import test from "node:test";
import assert from "node:assert/strict";
import { isFreshCleanCatalogCycle } from "./affilio-minute-dispatcher.mjs";

const cleanStatus = {
  schema_version: 2,
  full_catalog_mode: "all_categories_all_pages",
  scan_policy_version: "all_categories_all_pages_v3_cycle_snapshot",
  last_cycle_status: "complete",
  completed_candidates_snapshot_valid: true,
  completed_candidates_cycle_at: "2026-11-06T16:00:00Z",
  completed_candidates_count: 3000,
  completed_candidates_sha256: "a".repeat(64),
  last_cycle_categories_total: 4917,
  catalog_category_count: 4917,
  catalog_category_ids: Array.from({ length: 4917 }, (_, index) => String(index + 1)),
  last_cycle_category_ids: Array.from({ length: 4917 }, (_, index) => String(index + 1)),
  last_cycle_completed_category_ids: Array.from({ length: 4917 }, (_, index) => String(index + 1)),
  last_cycle_unqueryable_category_ids: [],
  last_cycle_categories_complete: 4917,
  last_cycle_categories_unqueryable: 0,
  last_cycle_category_coverage_percent: 100,
  last_cycle_pages_success: 186820,
  completed_cycles: 1,
  last_cycle_completed_at: "2026-11-06T16:00:00Z",
};

test("allows the first publication after a clean full-catalog cycle", () => {
  assert.equal(isFreshCleanCatalogCycle(cleanStatus, null), true);
});

test("allows publication only when a clean cycle is newer than the previous post", () => {
  assert.equal(isFreshCleanCatalogCycle(cleanStatus, Date.parse("2026-11-06T15:59:59Z")), true);
  assert.equal(isFreshCleanCatalogCycle(cleanStatus, Date.parse("2026-11-06T16:00:00Z")), false);
  assert.equal(isFreshCleanCatalogCycle(cleanStatus, Date.parse("2026-11-06T16:00:01Z")), false);
});

test("blocks a category-set replacement even when the category count is unchanged", () => {
  const changedIds = [...cleanStatus.catalog_category_ids];
  changedIds[0] = "new-category-id";
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, catalog_category_ids: changedIds }, null), false);
});

test("blocks a previously clean cycle when new catalog categories appear", () => {
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, catalog_category_count: 4918 }, null), false);
});

test("blocks incomplete cycles and any unqueryable category", () => {
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, last_cycle_status: "complete_with_gaps" }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, last_cycle_categories_unqueryable: 1 }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, last_cycle_categories_complete: 4916 }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, last_cycle_category_coverage_percent: 99.98 }, null), false);
});

test("requires the immutable candidate snapshot to match the clean cycle", () => {
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, completed_candidates_snapshot_valid: false }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, completed_candidates_cycle_at: "2026-11-06T15:00:00Z" }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, completed_candidates_count: 0 }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, completed_candidates_sha256: "invalid" }, null), false);
});

test("fails closed on missing, stale-schema, or partial-scan status", () => {
  assert.equal(isFreshCleanCatalogCycle(null, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, schema_version: 1 }, null), false);
  assert.equal(isFreshCleanCatalogCycle({ ...cleanStatus, scan_policy_version: "top_60_only" }, null), false);
});
