import test from "node:test";
import assert from "node:assert/strict";
import {
  isUsableCleanCatalogSnapshot,
  isInitialCatalogWarmup,
  isDegradedLiveFallbackAvailable,
  hasDueVideoRecord,
  hasPendingVideoQueue,
  videoRecordDue,
  isFiloLoginVerified,
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

test("video destinations accept the canonical selected product without waiting for a photo-channel success", () => {
  const now = Date.now();
  const record = {
    ts: (now - 60_000) / 1000,
    video_dispatch_eligible: true,
    distribution_queue_id: "dkp-selected:2026-11-11T20:00:00Z",
    delivery_status: { telegram: "pending", bale: "pending", rubika: "pending", eitaa: "pending" },
    youtube_upload_status: "pending",
    aparat_upload_status: "pending",
    filo_upload_status: "pending",
    video_generation_status: "pending",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 4 * 60 * 60 * 1000).toISOString(),
  };
  const state = { published: { "dkp-selected": record } };
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(videoRecordDue(record, platform, now), true, platform);
    assert.equal(hasDueVideoRecord(state, platform, now), true, platform);
  }
  assert.equal(videoRecordDue({
    ...record,
    video_dispatch_eligible: false,
    distribution_queue_id: "",
  }, "youtube", now), false);
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

test("a successful channel post immediately makes the same product eligible for every video destination", () => {
  const now = Date.now();
  const record = {
    ts: (now - 60_000) / 1000,
    delivery_status: { telegram: "sent" },
    youtube_upload_status: "pending",
    aparat_upload_status: "pending",
    filo_upload_status: "pending",
    video_generation_status: "pending",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 4 * 60 * 60 * 1000).toISOString(),
  };
  const state = { published: { "dkp-channel-event": record } };
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(videoRecordDue(record, platform, now), true, platform);
    assert.equal(hasDueVideoRecord(state, platform, now), true, platform);
  }
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
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" }, video_generation_status: "skipped_unverified_deadline" } } }, "filo", now),
    false,
    "a skipped deadline is terminal and must not create a minute-by-minute dispatch loop"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: { ...base, delivery_status: { telegram: "sent" }, ts: (now - 10 * 24 * 60 * 60_000) / 1000 } } }, "filo", now),
    true,
    "old selected items remain eligible; only actual offer expiry blocks them"
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

test("pending video projection dispatches old items regardless of platform preflight gates", () => {
  const oldTs = (Date.now() - 60 * 24 * 60 * 60 * 1000) / 1000;
  const state = {
    published: {
      oldest: {
        ts: oldTs,
        video_dispatch_eligible: true,
        video_generation_status: "generated",
        aparat_upload_status: "pending",
        youtube_upload_status: "uploaded",
        filo_upload_status: "skipped_unavailable",
        expiry_deadline_verified_directly: false,
      },
    },
  };
  assert.equal(hasPendingVideoQueue(state), true);
});

test("pending editorial video queue entries trigger the shared video workflow", () => {
  const state = {
    editorial_delivery_queue: {
      "editorial:buyer-checklist": {
        status: "partial",
        scheduled_at: new Date(Date.now() - 60_000).toISOString(),
        sequence_number: 12,
        platforms: {
          youtube: { status: "pending" },
          aparat: { status: "not_connected" },
          filo: { status: "manual_review" },
        },
      },
    },
  };
  assert.equal(hasPendingVideoQueue(state), true);
});

test("future editorial retry timestamps do not trigger premature video dispatch", () => {
  const state = {
    editorial_delivery_queue: {
      "editorial:buyer-checklist": {
        status: "partial",
        scheduled_at: new Date(Date.now() - 60_000).toISOString(),
        platforms: {
          youtube: { status: "retry", next_attempt_at: new Date(Date.now() + 60 * 60_000).toISOString() },
          aparat: { status: "not_connected" },
          filo: { status: "manual_review" },
        },
      },
    },
  };
  assert.equal(hasPendingVideoQueue(state), false);
});

test("pending video projection ignores terminal statuses so completed queue entries do not occupy the sidecar", () => {
  const ts = Date.now() / 1000;
  const state = {
    published: {
      skipped: {
        ts,
        video_dispatch_eligible: true,
        youtube_upload_status: "skipped_platform_limit",
        aparat_upload_status: "skipped_unverified_deadline",
        filo_upload_status: "skipped_after_retries",
      },
      uploaded: {
        ts: ts - 1,
        video_dispatch_eligible: true,
        youtube_upload_status: "uploaded",
        aparat_upload_status: "uploaded",
        filo_upload_status: "published",
      },
    },
  };
  assert.equal(hasPendingVideoQueue(state), false);
});

test("unified video queue ignores legacy age and retry timestamps for all platforms", () => {
  const now = Date.now();
  const oldRecord = {
    ts: (now - 10 * 24 * 60 * 60 * 1000) / 1000,
    delivery_status: { telegram: "sent" },
    youtube_upload_status: "pending",
    aparat_upload_status: "pending",
    filo_upload_status: "pending",
    video_generation_status: "generated",
    youtube_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    aparat_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    filo_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    video_generation_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 48 * 60 * 60 * 1000).toISOString(),
  };
  const state = { published: { old_but_valid: oldRecord } };
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(videoRecordDue(oldRecord, platform, now), true, platform);
    assert.equal(hasDueVideoRecord(state, platform, now), true, platform);
  }
});

test("terminally skipped video destinations are not redispatched", () => {
  const now = Date.now();
  const base = {
    ts: (now - 30 * 24 * 60 * 60 * 1000) / 1000,
    delivery_status: { telegram: "sent" },
    video_generation_status: "generated",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 48 * 60 * 60 * 1000).toISOString(),
  };
  for (const status of ["skipped_after_retries", "skipped_unavailable", "skipped_platform_limit", "skipped_generation_failed"]) {
    assert.equal(
      hasDueVideoRecord({ published: { item: { ...base, youtube_upload_status: status } } }, "youtube", now),
      false,
      status
    );
  }
});
