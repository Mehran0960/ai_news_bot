import test from "node:test";
import assert from "node:assert/strict";
import {
  isUsableCleanCatalogSnapshot,
  isInitialCatalogWarmup,
  hasDueVideoRecord,
  isFiloLoginVerified,
  PUBLISHER_INTERVAL_MS,
  readLastChannelPublicationAt,
} from "./affilio-minute-dispatcher.mjs";

const categoryIds = Array.from({ length: 4917 }, (_, index) => String(index + 1));
const cleanStatus = {
  schema_version: 2,
  full_catalog_mode: "all_categories_all_pages",
  scan_policy_version: "all_categories_all_pages_v3_cycle_snapshot",
  last_cycle_status: "in_progress",
  last_clean_cycle_status: "complete",
  completed_candidates_snapshot_present: true,
  completed_candidates_snapshot_valid: true,
  completed_candidates_cycle_at: "2026-11-06T16:00:00Z",
  completed_candidates_count: 3000,
  completed_candidates_sha256: "a".repeat(64),
  last_clean_cycle_started_at: "2026-11-06T12:00:00Z",
  last_clean_cycle_completed_at: "2026-11-06T16:00:00Z",
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
    last_channel_published_at: "2026-11-06T17:00:00Z",
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

test("blocks newly added catalog categories until a matching clean snapshot exists", () => {
  assert.equal(
    isUsableCleanCatalogSnapshot({ ...cleanStatus, catalog_category_count: 4918 }),
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
});

test("video dispatcher sees an older pending upload beyond the newest six records", () => {
  const now = Date.now();
  const published = {};
  for (let index = 0; index < 6; index += 1) {
    published[`completed-${index}`] = {
      ts: (now - index * 60_000) / 1000,
      delivery_status: { telegram: "sent" },
      youtube_upload_status: "uploaded",
      video_generation_status: "generated",
    };
  }
  published.older_pending = {
    ts: (now - 7 * 60_000) / 1000,
    delivery_status: { telegram: "sent" },
    youtube_upload_status: "pending",
    video_generation_status: "generated",
  };
  assert.equal(hasDueVideoRecord({ published }, "youtube", now), true);
});

test("Filo login must be explicitly verified and no older than seven days", () => {
  const now = Date.now();
  assert.equal(isFiloLoginVerified({}, now), false);
  assert.equal(isFiloLoginVerified({
    filo_login_verification_status: "verified",
    filo_login_verified_at: new Date(now - 60 * 60 * 1000).toISOString(),
  }, now), true);
  assert.equal(isFiloLoginVerified({
    filo_login_verification_status: "verified",
    filo_login_verified_at: new Date(now - 8 * 24 * 60 * 60 * 1000).toISOString(),
  }, now), false);
  assert.equal(isFiloLoginVerified({
    filo_login_verification_status: "failed",
    filo_login_verified_at: new Date(now).toISOString(),
  }, now), false);
});

test("Filo accepts every confirmed channel delivery without requiring a retailer expiry timer", () => {
  const now = Date.now();
  const base = {
    ts: (now - 5 * 60_000) / 1000,
    filo_upload_status: "pending",
    video_generation_status: "generated",
  };
  for (const channel of ["telegram", "bale", "rubika", "eitaa"]) {
    assert.equal(
      hasDueVideoRecord({ published: { item: { ...base, delivery_status: { [channel]: "sent" } } } }, "filo", now),
      true,
      channel
    );
  }
  assert.equal(
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" }, expires_at: new Date(now + 5 * 60_000).toISOString() } } }, "filo", now),
    false,
    "known near-expiry offer must remain blocked"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" }, ts: (now - 25 * 60 * 60_000) / 1000 } } }, "filo", now),
    false,
    "stale videos remain blocked after 24 hours"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" } } } }, "aparat", now),
    false,
    "Aparat's stricter verified-expiry rule must remain in place"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" }, expiry_deadline_verified_directly: true } } }, "aparat", now),
    true
  );
});

test("Filo does not retry accepted or outcome-unknown submissions", () => {
  const now = Date.now();
  const base = {
    ts: (now - 5 * 60_000) / 1000,
    delivery_status: { bale: "sent" },
    video_generation_status: "generated",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 4 * 60 * 60 * 1000).toISOString(),
  };
  for (const status of ["published", "submitted_pending_approval", "submitted_unconfirmed", "upload_result_unknown", "rejected_by_filo"]) {
    assert.equal(
      hasDueVideoRecord({ published: { item: { ...base, filo_upload_status: status } } }, "filo", now),
      false
    );
  }
});

test("video dispatcher still excludes products older than the 24-hour freshness window", () => {
  const now = Date.now();
  const state = {
    published: {
      stale: {
        ts: (now - 25 * 60 * 60 * 1000) / 1000,
        delivery_status: { telegram: "sent" },
        youtube_upload_status: "pending",
        video_generation_status: "pending",
      },
    },
  };
  assert.equal(hasDueVideoRecord(state, "youtube", now), false);
});
