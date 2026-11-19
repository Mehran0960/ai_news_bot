import test from "node:test";
import assert from "node:assert/strict";
import {
  isUsableCleanCatalogSnapshot,
  isInitialCatalogWarmup,
  isDegradedLiveFallbackAvailable,
  hasDueVideoRecord,
  hasPendingVideoQueue,
  hasDueEditorialChannelQueue,
  editorialChannelQueueDispatchDeferReason,
  videoQueueDispatchDeferReason,
  videoRecordDue,
  isFiloLoginVerified,
  PUBLISHER_DISCOVERY_RETRY_MS,
  PUBLISHER_DISCOVERY_QUEUE_LOW_WATERMARK,
  shouldReplenishPublisherQueue,
  isEmergencyContinuityAvailable,
  isPublisherAttemptRun,
  nextPublisherDueAt,
  MIN_CHANNEL_POST_INTERVAL_MS,
  hasActiveChannelPublicationWork,
  hasDueScheduledPublication,
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


test("publisher cadence follows the exact scheduled product timestamp regardless of last post", () => {
  const now = Date.now();
  const productAt = now + 10 * 60 * 1000;
  const state = {
    pending_product_queue_count: 1,
    next_channel_content_due_at: new Date(productAt).toISOString(),
  };
  assert.equal(nextPublisherDueAt(state), productAt);
});

test("publisher chooses the earliest editorial midpoint or product slot", () => {
  const now = Date.now();
  const productAt = now + 3 * 60 * 60 * 1000;
  const editorialAt = now + 47 * 60 * 1000;
  const state = {
    pending_product_queue_count: 1,
    next_channel_content_due_at: new Date(productAt).toISOString(),
    next_editorial_planning_at: new Date(editorialAt).toISOString(),
  };
  assert.equal(nextPublisherDueAt(state), editorialAt);
});

test("already-due selected content is dispatched independently of catalog snapshot readiness", () => {
  const now = Date.now();
  const due = {
    pending_product_queue_count: 1,
    next_channel_content_due_at: new Date(now - 1).toISOString(),
    next_editorial_planning_at: null,
  };
  assert.equal(hasDueScheduledPublication(due, now), true);
  assert.equal(hasDueScheduledPublication({
    next_channel_content_due_at: new Date(now + 60_000).toISOString(),
  }, now), false);
  assert.equal(hasDueScheduledPublication({}, now), false);
});

test("publisher replenishes a low product queue before the next scheduled slot", () => {
  const now = Date.now();
  const recentAttempt = { updated_at: new Date(now - 60 * 1000).toISOString() };
  const staleAttempt = { updated_at: new Date(now - 4 * 60 * 1000).toISOString() };
  const scheduled = {
    pending_product_queue_count: PUBLISHER_DISCOVERY_QUEUE_LOW_WATERMARK,
    next_channel_content_due_at: new Date(now + 57 * 60 * 1000).toISOString(),
  };
  assert.equal(shouldReplenishPublisherQueue(scheduled, recentAttempt, now), false);
  assert.equal(shouldReplenishPublisherQueue(scheduled, staleAttempt, now), true);
  assert.equal(shouldReplenishPublisherQueue({
    pending_product_queue_count: PUBLISHER_DISCOVERY_QUEUE_LOW_WATERMARK + 1,
  }, staleAttempt, now), false);
  assert.equal(shouldReplenishPublisherQueue({}, staleAttempt, now), false);
});

test("stale publication timestamps are ignored when the projected queues are empty", () => {
  const now = Date.now();
  const stale = new Date(now - 60 * 60 * 1000).toISOString();
  const state = {
    pending_product_queue_count: 0,
    editorial_channel_queue: [],
    next_channel_content_due_at: stale,
    next_editorial_planning_at: stale,
  };
  assert.equal(hasActiveChannelPublicationWork(state), false);
  assert.equal(nextPublisherDueAt(state), null);
  assert.equal(hasDueScheduledPublication(state, now), false);
  assert.equal(PUBLISHER_DISCOVERY_RETRY_MS, 3 * 60 * 1000,
    "three minutes is only an unscheduled discovery retry throttle");
});

test("publisher dispatch waits for the hard shared-channel floor after a confirmed send", () => {
  const now = Date.parse("2026-11-19T04:03:30Z");
  const lastPublishedAt = now - 10 * 60 * 1000;
  const plannedAt = now - 60 * 1000;
  const state = {
    pending_product_queue_count: 1,
    last_channel_published_at: new Date(lastPublishedAt).toISOString(),
    next_channel_content_due_at: new Date(plannedAt).toISOString(),
    next_editorial_planning_at: new Date(plannedAt).toISOString(),
  };
  const expectedDueAt = lastPublishedAt + MIN_CHANNEL_POST_INTERVAL_MS;
  assert.equal(nextPublisherDueAt(state), expectedDueAt);
  assert.equal(hasDueScheduledPublication(state, expectedDueAt - 1), false);
  assert.equal(hasDueScheduledPublication(state, expectedDueAt), true);
});

test("stale editorial midpoint before the latest channel receipt is ignored", () => {
  const lastPublishedAt = Date.parse("2026-11-19T03:51:47.023Z");
  const staleEditorialAt = Date.parse("2026-11-18T03:07:19.173Z");
  const nextProductAt = Date.parse("2026-11-19T04:28:47.023Z");
  const state = {
    pending_product_queue_count: 10,
    last_channel_published_at: new Date(lastPublishedAt).toISOString(),
    next_channel_content_due_at: new Date(nextProductAt).toISOString(),
    next_editorial_planning_at: new Date(staleEditorialAt).toISOString(),
  };
  assert.equal(nextPublisherDueAt(state), nextProductAt);
  assert.equal(hasDueScheduledPublication(state, Date.parse("2026-11-19T04:25:00Z")), false);
  assert.equal(hasDueScheduledPublication(state, nextProductAt), true);
});

test("an active editorial channel queue keeps its scheduled midpoint valid", () => {
  const now = Date.now();
  const stale = new Date(now - 1).toISOString();
  const state = {
    pending_product_queue_count: 0,
    editorial_channel_queue: [{content_id: "editorial:retry"}],
    next_editorial_planning_at: stale,
  };
  assert.equal(hasActiveChannelPublicationWork(state), true);
  assert.equal(nextPublisherDueAt(state), Date.parse(stale));
  assert.equal(hasDueScheduledPublication(state, now), true);
});

test("emergency discovery never adds a public posting gap", () => {
  const now = Date.now();
  const scheduled = now + 90_000;
  const state = {
    pending_product_queue_count: 1,
    next_channel_content_due_at: new Date(scheduled).toISOString(),
  };
  assert.equal(nextPublisherDueAt(state), scheduled);
  assert.equal(nextPublisherDueAt({}), null);
});

test("editorial requires a real selected product slot; there is no 55-minute fallback", () => {
  const now = Date.now();
  const state = { last_channel_published_at: new Date(now - 24 * 60 * 60 * 1000).toISOString() };
  assert.equal(nextPublisherDueAt(state), null);
});

test("publisher retry cooldown recognizes guarded push and workflow_dispatch attempts", () => {
  assert.equal(isPublisherAttemptRun({ event: "push", head_branch: "main" }), true);
  assert.equal(isPublisherAttemptRun({ event: "workflow_dispatch", head_branch: "main" }), true);
  assert.equal(isPublisherAttemptRun({ event: "push", head_branch: "feature/preview" }), false);
  assert.equal(isPublisherAttemptRun({ event: "schedule", head_branch: "main" }), false);
  assert.equal(isPublisherAttemptRun(null), false);
});

test("emergency Worker dispatch requires a pinned hash and an unexpired window", () => {
  const now = Date.now();
  const active = {
    emergency_continuity_active: true,
    emergency_continuity_snapshot_sha256: "a".repeat(64),
    emergency_continuity_baseline_completed_at: new Date(now - 90 * 60 * 60 * 1000).toISOString(),
    emergency_continuity_expires_at: new Date(now + 60 * 60 * 1000).toISOString(),
  };
  assert.equal(isEmergencyContinuityAvailable(active, now), true);
  assert.equal(isEmergencyContinuityAvailable({
    ...active, emergency_continuity_expires_at: new Date(now - 1).toISOString(),
  }, now), false);
  assert.equal(isEmergencyContinuityAvailable({
    ...active, emergency_continuity_snapshot_sha256: "invalid",
  }, now), false);
});

test("publisher bootstraps immediately when neither a post nor a scheduled slot exists", () => {
  assert.equal(nextPublisherDueAt({}, null), null);
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
    expiry_source: "digikala_live_deals_feed",
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
    expiry_source: "digikala_live_deals_feed",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 4 * 60 * 60 * 1000).toISOString(),
  };
  const state = { published: { "dkp-channel-event": record } };
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(videoRecordDue(record, platform, now), true, platform);
    assert.equal(hasDueVideoRecord(state, platform, now), true, platform);
  }
});

test("previously skipped expiry records are redispatched only while the verified offer remains live", () => {
  const now = Date.now();
  const active = {
    ts: (now - 60_000) / 1000,
    video_dispatch_eligible: true,
    delivery_status: { telegram: "sent" },
    video_generation_status: "skipped_expiring_soon",
    youtube_upload_status: "skipped_expiring_soon",
    aparat_upload_status: "skipped_expiring_soon",
    expiry_source: "digikala_live_deals_feed",
    expiry_deadline_verified_directly: true,
    expiry_estimated: false,
    expires_at: new Date(now + 20 * 60_000).toISOString(),
  };
  assert.equal(videoRecordDue(active, "youtube", now), true);
  assert.equal(videoRecordDue(active, "aparat", now), true);
  assert.equal(hasPendingVideoQueue({ published: { active } }, now), true);

  const expired = {
    ...active,
    expires_at: new Date(now + 5 * 60_000).toISOString(),
  };
  assert.equal(videoRecordDue(expired, "youtube", now), false);
  assert.equal(hasPendingVideoQueue({ published: { expired } }, now), false);

  const unverified = {
    ...active,
    expiry_deadline_verified_directly: false,
  };
  assert.equal(videoRecordDue(unverified, "youtube", now), false);
});

test("the no-expiry correction requeues YouTube and Aparat independently, not Filo", () => {
  const now = Date.now();
  const record = {
    ts: (now - 60_000) / 1000,
    video_dispatch_eligible: true,
    delivery_status: { telegram: "sent" },
    video_generation_status: "skipped_unverified_deadline",
    youtube_upload_status: "skipped_unverified_deadline",
    aparat_upload_status: "skipped_unverified_deadline",
    filo_upload_status: "pending",
  };
  assert.equal(videoRecordDue(record, "youtube", now), true);
  assert.equal(videoRecordDue(record, "aparat", now), true);
  assert.equal(videoRecordDue(record, "filo", now), false);
  assert.equal(hasPendingVideoQueue({ published: { record } }, now), true);
});

test("Filo accepts every confirmed channel delivery without requiring a retailer expiry timer", () => {
  const now = Date.now();
  const base = {
    ts: (now - 5 * 60_000) / 1000,
    filo_upload_status: "pending",
    aparat_upload_status: "pending",
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
    true,
    "Aparat must not wait for a retailer deadline when the selected product passed last-mile checks"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: {
      ...base,
      delivery_status: { telegram: "sent" },
      video_generation_status: "pending",
      aparat_upload_status: "skipped_unverified_deadline",
    } } }, "aparat", now),
    true,
    "legacy Aparat deadline skips must be requeued"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: {
      ...base,
      delivery_status: { telegram: "sent" },
      video_generation_status: "pending",
      aparat_upload_status: "skipped_unverified_deadline",
    } } }, "aparat", now),
    true,
    "legacy unverified-deadline skips are requeued for Aparat"
  );
  assert.equal(
    hasDueVideoRecord({ published: { item: {
      ...base,
      delivery_status: { telegram: "sent" },
      expiry_source: "digikala_product_detail_api",
      expiry_deadline_verified_directly: true,
      expires_at: new Date(now + 60 * 60_000).toISOString(),
      aparat_upload_status: "pending",
    } } }, "aparat", now),
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

test("video queue ignores legacy age but respects destination-local retry timestamps", () => {
  const now = Date.now();
  const oldRecord = {
    ts: (now - 10 * 24 * 60 * 60 * 1000) / 1000,
    delivery_status: { telegram: "sent" },
    youtube_upload_status: "retry",
    aparat_upload_status: "retry",
    filo_upload_status: "retry",
    video_generation_status: "generated",
    youtube_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    aparat_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    filo_next_attempt_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    expiry_source: "digikala_live_deals_feed",
    expiry_deadline_verified_directly: true,
    expires_at: new Date(now + 48 * 60 * 60 * 1000).toISOString(),
  };
  const state = { published: { old_but_valid: oldRecord } };
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(videoRecordDue(oldRecord, platform, now), false, platform);
    assert.equal(hasDueVideoRecord(state, platform, now), false, platform);
    const dueRecord = { ...oldRecord, [platform + "_next_attempt_at"]: new Date(now - 1).toISOString() };
    assert.equal(videoRecordDue(dueRecord, platform, now), true, platform);
    assert.equal(hasDueVideoRecord({ published: { due: dueRecord } }, platform, now), true, platform);
  }
});

test("YouTube daily quota pause defers only YouTube and automatically resumes", () => {
  const now = Date.parse("2026-11-17T18:00:00Z");
  const record = {
    ts: now / 1000 - 60,
    video_dispatch_eligible: true,
    delivery_status: { telegram: "sent" },
    video_generation_status: "generated",
    youtube_upload_status: "retry",
    youtube_next_attempt_at: new Date(now + 60 * 60_000).toISOString(),
    aparat_upload_status: "pending",
  };
  const paused = {
    published: { item: record },
    youtube_uploads_paused_until: new Date(now + 24 * 60 * 60_000).toISOString(),
  };
  assert.equal(videoRecordDue(record, "youtube", now), false);
  assert.equal(hasDueVideoRecord(paused, "youtube", now), false);
  assert.equal(hasDueVideoRecord(paused, "aparat", now), true, "Aparat must not inherit YouTube's quota pause");
  const globalOnlyRecord = { ...record };
  delete globalOnlyRecord.youtube_next_attempt_at;
  assert.equal(videoRecordDue(globalOnlyRecord, "youtube", now), true);
  assert.equal(hasDueVideoRecord({
    published: { item: globalOnlyRecord },
    youtube_uploads_paused_until: new Date(now + 24 * 60 * 60_000).toISOString(),
  }, "youtube", now), false, "the global quota pause blocks only YouTube");
  const resumedRecord = { ...record, youtube_next_attempt_at: new Date(now - 1).toISOString() };
  const resumed = { published: { item: resumedRecord }, youtube_uploads_paused_until: new Date(now - 1).toISOString() };
  assert.equal(videoRecordDue(resumedRecord, "youtube", now), true);
  assert.equal(hasDueVideoRecord(resumed, "youtube", now), true);
  const legacyQuotaSkip = {
    ...resumedRecord,
    youtube_upload_status: "skipped_platform_limit",
    youtube_skip_reason: "youtube_daily_quota_pause",
  };
  assert.equal(videoRecordDue(legacyQuotaSkip, "youtube", now), true);
});

test("editorial photo channel recovery queue is due per destination", () => {
  const now = Date.now();
  const state = {
    editorial_channel_queue: [{
      content_id: "editorial:delivery-guide",
      sequence_number: 42,
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: {
        telegram: { status: "sent" },
        bale: { status: "failed", attempts: 1, next_attempt_at: new Date(now - 1).toISOString() },
        rubika: { status: "retry", next_attempt_at: new Date(now + 60 * 60_000).toISOString() },
        eitaa: { status: "manual_review" },
      },
    }],
  };
  assert.equal(hasDueEditorialChannelQueue(state, now), true);
  state.editorial_channel_queue[0].platforms.bale.status = "sent";
  assert.equal(hasDueEditorialChannelQueue(state, now), false);
  state.editorial_channel_queue[0].platforms.rubika.next_attempt_at = new Date(now - 1).toISOString();
  assert.equal(hasDueEditorialChannelQueue(state, now), true);
});

test("editorial photo recovery never competes with pending first delivery or the primary publisher", () => {
  const now = Date.now();
  const initial = {
    editorial_channel_queue: [{
      content_id: "editorial:first-delivery",
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: { telegram: { status: "pending", attempts: 0 } },
    }],
  };
  assert.equal(hasDueEditorialChannelQueue(initial, now), false);
  assert.equal(
    editorialChannelQueueDispatchDeferReason(initial, false, now),
    "no_due_editorial_channel_recovery"
  );

  const failed = {
    editorial_channel_queue: [{
      content_id: "editorial:retry",
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: { telegram: { status: "retry", next_attempt_at: new Date(now - 1).toISOString() } },
    }],
  };
  assert.equal(hasDueEditorialChannelQueue(failed, now), true);
  assert.equal(
    editorialChannelQueueDispatchDeferReason(failed, true, now),
    "publisher_workflow_active_or_dispatched"
  );
  assert.equal(editorialChannelQueueDispatchDeferReason(failed, false, now), null);
});

test("editorial photo channel uncertain sends wait for the send watchdog", () => {
  const now = Date.now();
  const state = {
    editorial_channel_queue: [{
      content_id: "editorial:guide",
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: {
        telegram: { status: "sending", attempt_started_at: new Date(now - 5 * 60_000).toISOString() },
      },
    }],
  };
  assert.equal(hasDueEditorialChannelQueue(state, now), false);
  state.editorial_channel_queue[0].platforms.telegram.attempt_started_at =
    new Date(now - 31 * 60_000).toISOString();
  assert.equal(hasDueEditorialChannelQueue(state, now), true);
});

test("editorial video queue dispatches each destination without product records", () => {
  const now = Date.now();
  const state = {
    editorial_video_queue: [{
      content_id: "editorial:delivery-guide",
      sequence_number: 42,
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: {
        youtube: { status: "pending" },
        aparat: { status: "pending" },
        filo: { status: "pending" },
      },
    }],
  };
  assert.equal(hasPendingVideoQueue(state, now), true);
  for (const platform of ["youtube", "aparat", "filo"]) {
    assert.equal(hasDueVideoRecord(state, platform, now), true, platform);
  }
});

test("editorial video retry timestamps are destination-local", () => {
  const now = Date.now();
  const state = {
    editorial_video_queue: [{
      content_id: "editorial:delivery-guide",
      sequence_number: 42,
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: {
        youtube: { status: "retry", next_attempt_at: new Date(now + 60 * 60_000).toISOString() },
        aparat: { status: "pending" },
        filo: { status: "manual_review" },
      },
    }],
  };
  assert.equal(hasPendingVideoQueue(state, now), true);
  assert.equal(hasDueVideoRecord(state, "youtube", now), false);
  assert.equal(hasDueVideoRecord(state, "aparat", now), true);
  assert.equal(hasDueVideoRecord(state, "filo", now), false);
});

test("editorial video sender rechecks an uncertain send only after the watchdog", () => {
  const now = Date.now();
  const state = {
    editorial_video_queue: [{
      content_id: "editorial:guide",
      status: "partial",
      scheduled_at: new Date(now - 60_000).toISOString(),
      platforms: {
        youtube: { status: "sending", attempt_started_at: new Date(now - 5 * 60_000).toISOString() },
      },
    }],
  };
  assert.equal(hasDueVideoRecord(state, "youtube", now), false);
  state.editorial_video_queue[0].platforms.youtube.attempt_started_at =
    new Date(now - 31 * 60_000).toISOString();
  assert.equal(hasDueVideoRecord(state, "youtube", now), true);
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


test("video fan-out is not starved by catalog scans but preserves product priority", () => {
  const now = Date.now();
  const videoState = {
    published: {
      product: {
        ts: now / 1000,
        video_dispatch_eligible: true,
        video_generation_status: "generated",
        youtube_upload_status: "pending",
        aparat_upload_status: "pending",
        filo_upload_status: "pending",
      },
    },
  };

  // Channel/editorial reservations never defer independent video destinations.
  assert.equal(videoQueueDispatchDeferReason(videoState), null);
  assert.equal(videoQueueDispatchDeferReason({
    ...videoState,
    next_channel_content_due_at: new Date(now).toISOString(),
    next_editorial_planning_at: new Date(now).toISOString(),
  }), null);
  assert.equal(videoQueueDispatchDeferReason({ published: {} }), "video_queue_empty");
});
