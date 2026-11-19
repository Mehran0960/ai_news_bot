const OWNER = "Mehran0960";
const REPO = "ai_news_bot";
const WORKFLOW = "affilio-radar.yml";
const API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`;
const PUBLISHER_WORKFLOW = "offerchin-publisher.yml";
const PUBLISHER_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${PUBLISHER_WORKFLOW}`;
const CATALOG_WORKFLOW = "offerchin-digikala-catalog-sweep.yml";
const CATALOG_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${CATALOG_WORKFLOW}`;
const AUDIT_WORKFLOW = "offerchin-integrity-audit.yml";
const AUDIT_API = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/actions/workflows/" + AUDIT_WORKFLOW;
const YOUTUBE_VIDEO_WORKFLOW = "youtube-video-upload.yml";
const YOUTUBE_VIDEO_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${YOUTUBE_VIDEO_WORKFLOW}`;
const APARAT_VIDEO_WORKFLOW = "aparat-video-upload.yml";
const APARAT_VIDEO_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${APARAT_VIDEO_WORKFLOW}`;
const OFFERCHIN_FILO_VIDEO_WORKFLOW = "filo-video-upload.yml";
const OFFERCHIN_FILO_VIDEO_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${OFFERCHIN_FILO_VIDEO_WORKFLOW}`;
const EDITORIAL_CHANNEL_WORKFLOW = "offerchin-editorial-channel-upload.yml";
const EDITORIAL_CHANNEL_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${EDITORIAL_CHANNEL_WORKFLOW}`;
const RUNS_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/runs`;
const FILO_REPO = "Goushibaaz";
const FILO_WORKFLOW = "filo-native-republish.yml";
const FILO_API = `https://api.github.com/repos/${OWNER}/${FILO_REPO}/actions/workflows/${FILO_WORKFLOW}`;

function response(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
  });
}

async function githubRequest(url, token, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "affilio-minute-dispatcher",
      ...(options.headers || {})
    }
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch { data = { raw: text.slice(0, 500) }; }
  if (!res.ok) throw new Error(`GitHub API ${res.status}: ${JSON.stringify(data).slice(0, 600)}`);
  return data;
}

async function findActiveWorkflow(api, token) {
  // Check running jobs first: a queued copy must not hide a hung active execution.
  for (const status of ["in_progress", "pending", "queued"]) {
    const query = new URLSearchParams({ branch: "main", status, per_page: "5" });
    const data = await githubRequest(`${api}/runs?${query}`, token);
    if (Array.isArray(data.workflow_runs) && data.workflow_runs.length > 0) {
      return { status, run: data.workflow_runs[0] };
    }
  }
  return null;
}

async function recoverStaleWorkflow(
  api, token, label, runningLimitMinutes, queuedLimitMinutes, options = {}
) {
  const active = await findActiveWorkflow(api, token);
  if (!active) return null;
  const run = active.run || {};
  const started = Date.parse(run.run_started_at || run.created_at || "");
  if (!run.id || !Number.isFinite(started)) return active;
  const ageMinutes = (Date.now() - started) / 60000;
  const limit = active.status === "in_progress" ? runningLimitMinutes : queuedLimitMinutes;
  if (ageMinutes < limit) return active;

  const runsApi = api.replace(/\/workflows\/[^/]+$/, "/runs");

  // GitHub can expose a run as queued even when its jobs collection is empty.
  // Such orphaned runs may reject cancellation with HTTP 409 ("has not been queued yet").
  // Only the read-only catalog scanner may bypass this stale record after verifying
  // that no job ever started. Publishing workflows retain their strict concurrency lock.
  if (options.ignoreOrphanedNoJobs === true && active.status !== "in_progress") {
    const jobsData = await githubRequest(runsApi + "/" + run.id + "/jobs?per_page=100", token);
    const jobs = Array.isArray(jobsData.jobs) ? jobsData.jobs : [];
    if (jobs.length === 0) {
      console.error(
        "CHANNEL_DISPATCH_ORPHANED_ZERO_JOB_RUN workflow=" + label +
        " run_id=" + run.id + " status=" + active.status +
        " age_minutes=" + Math.floor(ageMinutes) + "; bypassing stale catalog lock"
      );
      return { status: "orphaned_no_jobs", run };
    }
  }

  // For genuine running or queued jobs, retain the existing stale-run cancellation guard.
  await githubRequest(runsApi + "/" + run.id + "/cancel", token, { method: "POST" });
  console.log(
    "CHANNEL_DISPATCH_STALE_CANCEL_REQUESTED workflow=" + label + " run_id=" + run.id +
    " status=" + active.status + " age_minutes=" + Math.floor(ageMinutes) +
    " threshold_minutes=" + limit
  );
  return { status: "stale_cancelling", run };
}

async function dispatchWorkflowIfIdle(
  api, token, label, runningLimitMinutes, queuedLimitMinutes, options = {}
) {
  const active = await recoverStaleWorkflow(
    api, token, label, runningLimitMinutes, queuedLimitMinutes, options
  );
  if (active && active.status === "stale_cancelling") {
    console.log("CHANNEL_DISPATCH_SKIPPED workflow=" + label + " reason=stale_run_cancellation_requested");
    return;
  }
  if (active && active.status !== "orphaned_no_jobs") {
    console.log("CHANNEL_DISPATCH_SKIPPED workflow=" + label + " reason=already_" + active.status + "; independent workflow remains unaffected");
    return;
  }
  if (active && active.status === "orphaned_no_jobs") {
    console.warn(
      "CHANNEL_DISPATCH_ORPHAN_BYPASS workflow=" + label +
      " run_id=" + active.run.id + " reason=zero_jobs_and_stale"
    );
  }
  await githubRequest(api + "/dispatches", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" })
  });
  console.log("CHANNEL_DISPATCH_ACCEPTED workflow=" + label);
}
export function isUsableCleanCatalogSnapshot(status) {
  if (!status || typeof status !== "object" || Number(status.schema_version) !== 2) return false;
  if (status.full_catalog_mode !== "all_categories_all_pages") return false;
  if (status.scan_policy_version !== "all_categories_all_pages_v3_cycle_snapshot") return false;
  if (status.last_clean_cycle_status !== "complete") return false;
  if (status.completed_candidates_snapshot_present !== true) return false;
  if (status.completed_candidates_snapshot_valid !== true) return false;

  const total = Number(status.last_clean_cycle_categories_total);
  const completed = Number(status.last_clean_cycle_categories_complete);
  const unqueryable = Number(status.last_clean_cycle_categories_unqueryable);
  const coverage = Number(status.last_clean_cycle_category_coverage_percent);
  const pages = Number(status.last_clean_cycle_pages_success);
  const completedAt = Date.parse(String(status.last_clean_cycle_completed_at || ""));
  const candidateCycleAt = Date.parse(String(status.completed_candidates_cycle_at || ""));
  const candidateCount = Number(status.completed_candidates_count);
  const candidateHash = String(status.completed_candidates_sha256 || "");
  const snapshotAgeMs = Date.now() - completedAt;
  const maximumSnapshotAgeMs = 96 * 60 * 60 * 1000;
  if (snapshotAgeMs < -15 * 60 * 1000 || snapshotAgeMs > maximumSnapshotAgeMs) return false;

  const currentIds = Array.isArray(status.catalog_category_ids)
    ? status.catalog_category_ids.map(value => String(value)) : [];
  const cleanIds = Array.isArray(status.last_clean_cycle_category_ids)
    ? status.last_clean_cycle_category_ids.map(value => String(value)) : [];
  const completedIds = Array.isArray(status.last_clean_cycle_completed_category_ids)
    ? status.last_clean_cycle_completed_category_ids.map(value => String(value)) : [];
  const unqueryableIds = Array.isArray(status.last_clean_cycle_unqueryable_category_ids)
    ? status.last_clean_cycle_unqueryable_category_ids.map(value => String(value)) : [];
  const currentCategoryCount = Number(status.catalog_category_count);
  const sameIds = (left, right) => {
    if (left.length !== right.length) return false;
    const a = [...left].sort();
    const b = [...right].sort();
    return a.every((value, index) => value === b[index]);
  };
  const currentIdSet = new Set(currentIds);
  const cleanIdSet = new Set(cleanIds);
  const unscannedNewCategoryCount = currentIds.filter(id => !cleanIdSet.has(id)).length;
  const unscannedNewCategoryBudget = Math.max(1, Math.min(50, Math.ceil(currentIds.length * 0.01)));

  if (!Number.isFinite(total) || total < 1 || completed !== total) return false;
  if (!Number.isFinite(currentCategoryCount) || currentIds.length !== currentCategoryCount) return false;
  if (new Set(currentIds).size !== currentIds.length) return false;
  if (currentIds.some(id => !/^\d+$/.test(id)) || cleanIds.some(id => !/^\d+$/.test(id))) return false;
  if (cleanIds.length !== total || new Set(cleanIds).size !== total) return false;
  if (completedIds.length !== total || new Set(completedIds).size !== total) return false;
  // New categories are swept incrementally, but a small bounded backlog must not
  // invalidate the last complete snapshot. Removed/replaced categories still block.
  if ([...cleanIdSet].some(id => !currentIdSet.has(id))) return false;
  if (unscannedNewCategoryCount > unscannedNewCategoryBudget) return false;
  if (!sameIds(cleanIds, completedIds)) return false;
  if (unqueryableIds.length !== 0 || unqueryable !== 0) return false;
  if (!Number.isFinite(coverage) || coverage < 100) return false;
  if (!Number.isFinite(pages) || pages < 1) return false;
  if (!Number.isFinite(completedAt) || !Number.isFinite(candidateCycleAt) || candidateCycleAt !== completedAt) return false;
  if (!Number.isFinite(candidateCount) || candidateCount < 1) return false;
  if (!/^[a-f0-9]{64}$/i.test(candidateHash)) return false;
  return true;
}

export function isDegradedLiveFallbackAvailable(status) {
  if (!status || typeof status !== "object" || Number(status.schema_version) !== 2) return false;
  if (status.full_catalog_mode !== "all_categories_all_pages") return false;
  if (status.scan_policy_version !== "all_categories_all_pages_v3_cycle_snapshot") return false;
  const count = Number(status.catalog_category_count);
  const ids = Array.isArray(status.catalog_category_ids)
    ? status.catalog_category_ids.map(value => String(value)) : [];
  if (!Number.isInteger(count) || count < 1 || ids.length !== count) return false;
  if (new Set(ids).size !== ids.length || ids.some(id => !/^\d+$/.test(id))) return false;
  return true;
}

export function isInitialCatalogWarmup(status) {
  if (!status || typeof status !== "object" || Number(status.schema_version) !== 2) return false;
  if (status.full_catalog_mode !== "all_categories_all_pages") return false;
  if (status.scan_policy_version !== "all_categories_all_pages_v3_cycle_snapshot") return false;
  if (status.completed_candidates_snapshot_present === true) return false;
  if (status.completed_candidates_snapshot_valid === true) return false;
  if (status.last_clean_cycle_status !== "unavailable") return false;
  if (status.last_clean_cycle_completed_at) return false;
  return Number(status.completed_cycles) === 0;
}

// This throttle schedules discovery retries only when no content slot exists.
// It is never applied to a product or editorial publication timestamp.
export const PUBLISHER_DISCOVERY_RETRY_MS = 3 * 60 * 1000;
export const PUBLISHER_DISCOVERY_QUEUE_LOW_WATERMARK = 2;

export function shouldReplenishPublisherQueue(state, latestAttempt, now = Date.now()) {
  const pending = Number(state && state.pending_product_queue_count);
  if (!Number.isFinite(pending) || pending > PUBLISHER_DISCOVERY_QUEUE_LOW_WATERMARK) {
    return false;
  }
  const attemptAt = Date.parse(String(
    latestAttempt && (
      latestAttempt.updated_at ||
      latestAttempt.run_started_at ||
      latestAttempt.created_at
    ) || ""
  ));
  return !Number.isFinite(attemptAt) ||
    now - attemptAt >= PUBLISHER_DISCOVERY_RETRY_MS;
}

export function isEmergencyContinuityAvailable(state, now = Date.now()) {
  const expiresAt = Date.parse(String(state && state.emergency_continuity_expires_at || ""));
  return Boolean(
    state &&
    state.emergency_continuity_active === true &&
    /^[a-f0-9]{64}$/.test(String(state.emergency_continuity_snapshot_sha256 || "")) &&
    String(state.emergency_continuity_baseline_completed_at || "").trim() &&
    Number.isFinite(expiresAt) &&
    expiresAt > now
  );
}

export function hasActiveChannelPublicationWork(state) {
  if (!state || typeof state !== "object") return false;
  const pendingProducts = Number(state.pending_product_queue_count);
  if (Number.isFinite(pendingProducts) && pendingProducts > 0) return true;
  const editorialQueue = Array.isArray(state.editorial_channel_queue)
    ? state.editorial_channel_queue : [];
  return editorialQueue.length > 0;
}

export const MIN_CHANNEL_POST_INTERVAL_MS = 31 * 60 * 1000;

export function nextPublisherDueAt(state) {
  // The dispatch sidecar can outlive the queue snapshot that produced it. Ignore
  // orphaned timestamps when the canonical projection says there is no work.
  if (!hasActiveChannelPublicationWork(state)) return null;
  const scheduledAt = Date.parse(String(state && state.next_channel_content_due_at || ""));
  const editorialPlanningAt = Date.parse(String(state && state.next_editorial_planning_at || ""));
  const lastPublishedAt = readLastChannelPublicationAt(state);
  // A midpoint reserved before the latest confirmed channel post is stale.
  // Actual recovery items remain handled by the independent editorial queue.
  const editorialPlanningIsCurrent = Number.isFinite(editorialPlanningAt) &&
    (lastPublishedAt === null || editorialPlanningAt > lastPublishedAt);
  const plannedTimes = [
    scheduledAt,
    editorialPlanningIsCurrent ? editorialPlanningAt : Number.NaN,
  ].filter(Number.isFinite);
  if (!plannedTimes.length) return null;

  // Mirror the Python publisher's hard shared-channel floor. The planner keeps
  // the deterministic 31–47 minute slot; this check prevents Cloudflare from
  // dispatching a publisher run before the last confirmed public channel receipt
  // has cleared the 31-minute floor. It does not change the planned slot.
  const plannedDueAt = Math.min(...plannedTimes);
  const earliestAllowedAt = lastPublishedAt === null
    ? null
    : lastPublishedAt + MIN_CHANNEL_POST_INTERVAL_MS;
  return earliestAllowedAt === null
    ? plannedDueAt
    : Math.max(plannedDueAt, earliestAllowedAt);
}

export function hasDueScheduledPublication(state, now = Date.now()) {
  const nextDueAt = nextPublisherDueAt(state);
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  return nextDueAt !== null && nextDueAt <= timestamp;
}

async function readOfferChinState(token) {
  try {
    const data = await githubRequest(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/affilio_radar/video_upload_dispatch_state.json?ref=main`,
      token
    );
    const encoded = String(data.content || "").replace(/\s/g, "");
    if (!encoded) throw new Error("state_file_empty");
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch (error) {
    console.error("OFFERCHIN_VIDEO_DISPATCH_STATE_READ_FAILED", String(error).slice(0, 500));
    return null;
  }
}

async function readCatalogSweepStatus(token) {
  try {
    const data = await githubRequest(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/affilio_radar/catalog_sweep_status.json?ref=main`,
      token
    );
    const encoded = String(data.content || "").replace(/\s/g, "");
    if (!encoded || data.encoding !== "base64") throw new Error("catalog_status_content_missing");
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    const status = JSON.parse(new TextDecoder().decode(bytes));
    return status && typeof status === "object" ? status : null;
  } catch (error) {
    console.error("OFFERCHIN_CATALOG_STATUS_READ_FAILED", String(error).slice(0, 500));
    return null;
  }
}

export function readLastChannelPublicationAt(state) {
  if (!state || typeof state !== "object") return null;
  const explicit = Date.parse(String(state.last_channel_published_at || ""));
  if (Number.isFinite(explicit)) return explicit;

  let latest = 0;
  const published = state.published && typeof state.published === "object" ? state.published : {};
  for (const record of Object.values(published)) {
    if (!record || typeof record !== "object") continue;
    const delivery = record.delivery_status && typeof record.delivery_status === "object"
      ? record.delivery_status : {};
    const hasMessage =
      ["telegram", "bale", "rubika", "eitaa"].some(platform => delivery[platform] === "sent") ||
      ["telegram_message_id", "bale_message_id", "rubika_message_id", "eitaa_message_id"]
        .some(field => /^\d+$/.test(String(record[field] || "")));
    const seconds = Number(record.ts || 0);
    if (hasMessage && Number.isFinite(seconds)) latest = Math.max(latest, seconds * 1000);
  }
  return latest > 0 ? latest : null;
}

export function isPublisherAttemptRun(run) {
  return Boolean(
    run &&
    run.head_branch === "main" &&
    (run.event === "workflow_dispatch" || run.event === "push")
  );
}

async function readLatestPublisherAttempt(token) {
  try {
    const query = new URLSearchParams({ branch: "main", per_page: "10" });
    const data = await githubRequest(`${PUBLISHER_API}/runs?${query}`, token);
    const rows = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
    return rows.find(isPublisherAttemptRun) || null;
  } catch (error) {
    console.error("OFFERCHIN_PUBLISHER_ATTEMPT_READ_FAILED", String(error).slice(0, 500));
    return null;
  }
}

async function dispatchPublisherWhenDue(env, tick, state) {
  const active = await recoverStaleWorkflow(
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 28
  );
  if (active) {
    console.log("OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=active_workflow_" + active.status);
    return true;
  }

  if (!state) {
    console.warn("OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=publication_state_unavailable");
    return false;
  }

  const now = tick.getTime();
  const nextDueAt = nextPublisherDueAt(state);
  const hasScheduledContent = nextDueAt !== null;

  if (hasDueScheduledPublication(state, now)) {
    // Previously selected content must not wait for a new clean catalog snapshot.
    // The Python publisher rechecks product identity, price, stock and affiliate link live.
    console.log(
      "OFFERCHIN_PUBLISHER_DUE_QUEUE_PRIORITY next_due_at=" +
      new Date(nextDueAt).toISOString() +
      " clean_snapshot_gate=bypassed live_revalidation=required"
    );
    await dispatchWorkflowIfIdle(
      PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 28
    );
    return true;
  }

  const [latestAttempt, catalogStatus] = await Promise.all([
    readLatestPublisherAttempt(env.GITHUB_TOKEN),
    readCatalogSweepStatus(env.GITHUB_TOKEN),
  ]);
  const lastPublishedAt = readLastChannelPublicationAt(state);
  const emergencyContinuityFallback = isEmergencyContinuityAvailable(state);
  let degradedLiveFallback = false;
  if (!isUsableCleanCatalogSnapshot(catalogStatus)) {
    if (isInitialCatalogWarmup(catalogStatus)) {
      // Initial bootstrap: live discovery remains available until the first full snapshot.
      console.log("OFFERCHIN_PUBLISHER_WARMUP_FALLBACK reason=no_clean_snapshot_yet");
    } else if (isDegradedLiveFallbackAvailable(catalogStatus)) {
      // Do not represent partial scanning as a clean snapshot. The Python publisher
      // restricts this mode to canonical DigiKala/SnappShop IDs and rechecks price,
      // stock, expiry, product identity and affiliate URL before delivery.
      degradedLiveFallback = true;
      console.warn(
        "OFFERCHIN_PUBLISHER_DEGRADED_LIVE_FALLBACK taxonomy_registry_valid=true" +
        " full_catalog_snapshot_valid=false; live_product_revalidation_required=true"
      );
    } else if (emergencyContinuityFallback) {
      console.warn(
        "OFFERCHIN_PUBLISHER_EMERGENCY_CONTINUITY_FALLBACK " +
        "snapshot_lead_only=true live_price_stock_discount_affiliate_recheck_required=true " +
        "baseline=" + String(state.emergency_continuity_baseline_completed_at) +
        " retry_gap_minutes=3"
      );
    } else {
      console.log(
        "OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=no_valid_clean_catalog_snapshot" +
        " latest_attempt_status=" + String(catalogStatus && catalogStatus.last_cycle_status || "unknown") +
        " last_clean_cycle_at=" + String(catalogStatus && catalogStatus.last_clean_cycle_completed_at || "unknown")
      );
      return false;
    }
  } else {
    // Reuse the last immutable clean snapshot while the next full scan runs.
    // A new full scan is not required between already scheduled product slots.
    console.log(
      "OFFERCHIN_PUBLISHER_USING_CLEAN_SNAPSHOT cycle=" +
      String(catalogStatus.last_clean_cycle_completed_at) +
      " candidates=" + String(catalogStatus.completed_candidates_count) +
      " unscanned_new_categories=" + String(catalogStatus.unscanned_new_category_count || 0) +
      "/" + String(catalogStatus.unscanned_new_category_budget || 0)
    );
  }
  const latestCleanCycleAt = Date.parse(String(
    catalogStatus && catalogStatus.last_clean_cycle_completed_at || ""
  ));
  const plannedCleanCycleAt = Date.parse(String(
    state.product_publication_plan_cycle_id ||
    state.product_publication_cadence_cycle_id ||
    ""
  ));
  const newCleanCycleReady = Boolean(
    isUsableCleanCatalogSnapshot(catalogStatus) &&
    Number.isFinite(latestCleanCycleAt) &&
    (!Number.isFinite(plannedCleanCycleAt) || latestCleanCycleAt > plannedCleanCycleAt)
  );

  // Refill the product backlog before it runs dry, while keeping already scheduled
  // product/editorial posts at their independent due timestamps.
  const attemptAt = Date.parse(String(
    latestAttempt && (latestAttempt.updated_at || latestAttempt.run_started_at || latestAttempt.created_at) || ""
  ));
  const queueNeedsReplenishment = shouldReplenishPublisherQueue(state, latestAttempt, now);
  if (!newCleanCycleReady && nextDueAt !== null && now < nextDueAt &&
      !queueNeedsReplenishment) {
    console.log("OFFERCHIN_PUBLISHER_NOT_DUE seconds_remaining=" +
      Math.ceil((nextDueAt - now) / 1000) +
      " next_content_due_at=" + new Date(nextDueAt).toISOString());
    return false;
  }
  if (queueNeedsReplenishment && nextDueAt !== null && now < nextDueAt) {
    console.log(
      "OFFERCHIN_PRODUCT_QUEUE_REPLENISHMENT_DUE " +
      "pending_products=" + String(state.pending_product_queue_count) +
      " next_product_slot=" + new Date(nextDueAt).toISOString() +
      " discovery_retry_minutes=3 product_slot_delay=false"
    );
  }
  // Throttle unscheduled discovery retries only. A due publication and an early
  // queue-replenishment run are never gated by this retry timer.
  if (!hasScheduledContent && !newCleanCycleReady &&
      Number.isFinite(attemptAt) && now - attemptAt < PUBLISHER_DISCOVERY_RETRY_MS) {
    console.log("OFFERCHIN_DISCOVERY_RETRY_WINDOW seconds_remaining=" +
      Math.ceil((PUBLISHER_DISCOVERY_RETRY_MS - (now - attemptAt)) / 1000));
    return false;
  }

  await dispatchWorkflowIfIdle(
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 28
  );
  return true;
}

const VIDEO_PENDING_STATUSES = new Set([
  "pending", "pending_credentials", "retry"
]);

function dateValue(value) {
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function hasChannelDelivery(record) {
  const delivery = record && record.delivery_status && typeof record.delivery_status === "object"
    ? record.delivery_status : {};
  return ["telegram", "bale", "rubika", "eitaa"].some(platform => delivery[platform] === "sent") ||
    ["telegram_message_id", "bale_message_id", "rubika_message_id", "eitaa_message_id"]
      .some(field => /^\d+$/.test(String(record[field] || "")));
}

function hasVideoDispatchEligibility(record) {
  return Boolean(
    record && typeof record === "object" &&
    (
      record.video_dispatch_eligible === true ||
      String(record.distribution_queue_id || "").trim() ||
      hasChannelDelivery(record)
    )
  );
}

function hasVerifiedVideoExpiry(record) {
  const expiry = dateValue(record && record.expires_at);
  if (expiry === null || record.expiry_estimated === true) return false;
  return (
    (
      ["digikala_live_deals_feed", "digikala_product_detail_api"].includes(record.expiry_source) &&
      record.expiry_deadline_verified_directly === true
    ) ||
    (
      record.expiry_source === "digikala_mcp_offer_card" &&
      record.expiry_deadline_verified_from_site_card === true
    )
  );
}

export function videoRecordDue(record, platform, now) {
  if (!hasVideoDispatchEligibility(record)) return false;
  const publishedAt = Number(record.ts || 0) * 1000;
  if (!Number.isFinite(publishedAt) || publishedAt <= 0) return false;

  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  const status = String(record[platform + "_upload_status"] || "").trim().toLowerCase();
  const generation = String(record.video_generation_status || "").trim().toLowerCase();
  const retryAt = dateValue(record[platform + "_next_attempt_at"]);
  if (retryAt !== null && retryAt > timestamp) return false;
  if (!["pending", "generated", "skipped_expiring_soon", "skipped_unverified_deadline"].includes(generation)) {
    return false;
  }

  const expiry = dateValue(record.expires_at);
  if (expiry !== null && expiry <= timestamp + 10 * 60 * 1000) return false;
  const verifiedExpiry = hasVerifiedVideoExpiry(record);

  if (generation === "skipped_expiring_soon") {
    // Only a directly verified, still-live deadline can reactivate an old skip.
    return verifiedExpiry && (
      VIDEO_PENDING_STATUSES.has(status) || status === "skipped_expiring_soon"
    );
  }

  if (generation === "skipped_unverified_deadline") {
    // YouTube and Aparat can use last-mile price/stock validation without a retailer
    // timer. Filo is not awakened from this terminal generation state by the dispatcher.
    if (platform === "youtube") {
      return VIDEO_PENDING_STATUSES.has(status) || status === "skipped_unverified_deadline";
    }
    if (platform === "aparat") {
      return VIDEO_PENDING_STATUSES.has(status) || status === "skipped_unverified_deadline";
    }
    return false;
  }

  if (
    platform === "aparat" &&
    ["pending", "generated"].includes(generation) &&
    status === "skipped_unverified_deadline"
  ) return true;

  if (
    platform === "youtube" &&
    status === "skipped_platform_limit" &&
    ["youtube_daily_quota_pause", "youtube_http_429_rate_limited"].includes(
      String(record.youtube_skip_reason || "")
    )
  ) return true;

  return VIDEO_PENDING_STATUSES.has(status);
}

export function isFiloLoginVerified(state, now) {
  const verifiedAt = dateValue(state && state.filo_login_verified_at);
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  const age = verifiedAt === null ? -1 : timestamp - verifiedAt;
  return Boolean(
    state &&
    state.filo_login_verification_status === "verified" &&
    age >= 0 &&
    age <= 7 * 24 * 60 * 60 * 1000
  );
}

function editorialVideoRecordDue(record, platform, now) {
  if (!record || typeof record !== "object") return false;
  if (["completed", "cancelled", "failed"].includes(String(record.status || "").trim().toLowerCase())) {
    return false;
  }
  const target = record.platforms && typeof record.platforms === "object"
    ? record.platforms[platform] : null;
  if (!target || typeof target !== "object") return false;
  const status = String(target.status || "pending").trim().toLowerCase();
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  let dueAt = dateValue(target.next_attempt_at) ?? dateValue(record.scheduled_at);
  if (status === "sending") {
    const attemptAt = dateValue(target.attempt_started_at);
    dueAt = attemptAt === null ? timestamp : attemptAt + 30 * 60 * 1000;
  } else if (status === "skipped_limit") {
    if (platform !== "youtube") return false;
    // The global YouTube quota pause is checked by hasDueVideoRecord().
  } else if (!["pending", "pending_credentials", "failed", "retry"].includes(status)) {
    return false;
  }
  return dueAt === null || dueAt <= timestamp;
}

function editorialVideoRecordPending(record) {
  if (!record || typeof record !== "object") return false;
  if (["completed", "cancelled", "failed"].includes(String(record.status || "").trim().toLowerCase())) {
    return false;
  }
  const platforms = record.platforms && typeof record.platforms === "object" ? record.platforms : {};
  return ["youtube", "aparat", "filo"].some((platform) => {
    const target = platforms[platform];
    if (!target || typeof target !== "object") return false;
    const status = String(target.status || "").trim().toLowerCase();
    return ["pending", "pending_credentials", "failed", "retry", "sending"].includes(status) ||
      (platform === "youtube" && status === "skipped_limit");
  });
}

export function hasDueVideoRecord(state, platform, now = Date.now()) {
  if (platform === "youtube") {
    const pauseUntil = dateValue(state && state.youtube_uploads_paused_until);
    if (pauseUntil !== null && pauseUntil > now) return false;
  }
  const published = state && state.published && typeof state.published === "object"
    ? state.published : {};
  // Product and editorial queues are independent; either may wake this destination.
  const productDue = Object.values(published).some(record => videoRecordDue(record, platform, now));
  if (productDue) return true;
  const editorialQueue = Array.isArray(state && state.editorial_video_queue)
    ? state.editorial_video_queue : [];
  return editorialQueue.some(record => editorialVideoRecordDue(record, platform, now));
}

async function readLatestWorkflowAttempt(api, token) {
  try {
    const query = new URLSearchParams({ branch: "main", per_page: "10" });
    const data = await githubRequest(`${api}/runs?${query}`, token);
    const rows = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
    return rows.find(run => run && run.event === "workflow_dispatch" && run.head_branch === "main") || null;
  } catch (error) {
    console.error("OFFERCHIN_VIDEO_ATTEMPT_READ_FAILED", String(error).slice(0, 400));
    return null;
  }
}

// Every selected product is fanned out from one shared canonical queue. The unified
// workflow serializes YouTube, Aparat and Filo over the same FIFO, then records each
// platform's own success, rejection, retry exhaustion or uncertain outcome.
export function hasPendingVideoQueue(state, now = Date.now()) {
  if (!state || typeof state !== "object") return false;
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  const published = state.published && typeof state.published === "object" ? state.published : {};
  const pendingProduct = Object.values(published).some((record) => {
    if (!hasVideoDispatchEligibility(record)) return false;
    const created = Number(record.ts || 0) * 1000;
    if (!Number.isFinite(created) || created <= 0) return false;
    const generation = String(record.video_generation_status || "").trim().toLowerCase();
    if (!["pending", "generated", "skipped_expiring_soon", "skipped_unverified_deadline"].includes(generation)) {
      return false;
    }
    const expiry = dateValue(record.expires_at);
    if (expiry !== null && expiry <= timestamp + 10 * 60 * 1000) return false;
    const verifiedExpiry = hasVerifiedVideoExpiry(record);
    return ["youtube", "aparat", "filo"].some((platform) => {
      const status = String(record[platform + "_upload_status"] || "").trim().toLowerCase();
      if (generation === "pending" || generation === "generated") {
        return VIDEO_PENDING_STATUSES.has(status);
      }
      if (generation === "skipped_expiring_soon") {
        return verifiedExpiry && (
          VIDEO_PENDING_STATUSES.has(status) || status === "skipped_expiring_soon"
        );
      }
      return platform === "youtube" && (
        VIDEO_PENDING_STATUSES.has(status) || status === "skipped_unverified_deadline"
      );
    });
  });
  const editorialQueue = Array.isArray(state.editorial_video_queue) ? state.editorial_video_queue : [];
  return pendingProduct || editorialQueue.some(editorialVideoRecordPending);
}

// Destination dispatch is independent: no channel slot, editorial slot,
// catalog scan, or sibling media workflow may defer a healthy destination.
export function videoQueueDispatchDeferReason(state) {
  return hasPendingVideoQueue(state) ? null : "video_queue_empty";
}

async function dispatchVideoUploadsWhenDue(env, tick, state) {
  if (!state || !env.GITHUB_TOKEN) return;

  const destinations = [
    { name: "youtube", api: YOUTUBE_VIDEO_API, due: hasDueVideoRecord(state, "youtube", tick.getTime()), running: 24, queued: 8 },
    { name: "aparat", api: APARAT_VIDEO_API, due: hasDueVideoRecord(state, "aparat", tick.getTime()), running: 18, queued: 8 },
    { name: "filo", api: OFFERCHIN_FILO_VIDEO_API, due: hasDueVideoRecord(state, "filo", tick.getTime()), running: 24, queued: 8 },
  ];

  for (const destination of destinations) {
    if (!destination.due) continue;
    try {
      await dispatchWorkflowIfIdle(
        destination.api,
        env.GITHUB_TOKEN,
        "offerchin-" + destination.name,
        destination.running,
        destination.queued
      );
    } catch (error) {
      console.error(
        "OFFERCHIN_DESTINATION_DISPATCH_FAILED platform=" + destination.name +
        " error=" + String(error).slice(0, 700)
      );
    }
  }
}
export function hasDueEditorialChannelQueue(state, now = Date.now()) {
  const queue = Array.isArray(state && state.editorial_channel_queue)
    ? state.editorial_channel_queue : [];
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  return queue.some((record) => {
    if (!record || typeof record !== "object") return false;
    if (["completed", "cancelled", "failed"].includes(String(record.status || "").trim().toLowerCase())) {
      return false;
    }
    const platforms = record.platforms && typeof record.platforms === "object" ? record.platforms : {};
    return ["telegram", "bale", "rubika", "eitaa"].some((platform) => {
      const target = platforms[platform];
      if (!target || typeof target !== "object") return false;
      const status = String(target.status || "").trim().toLowerCase();
      if (status === "sending") {
        const attemptAt = dateValue(target.attempt_started_at);
        return attemptAt === null || attemptAt + 30 * 60 * 1000 <= timestamp;
      }
      if (!["failed", "retry"].includes(status)) return false;
      const dueAt = dateValue(target.next_attempt_at) ?? dateValue(record.scheduled_at);
      return dueAt === null || dueAt <= timestamp;
    });
  });
}

export function editorialChannelQueueDispatchDeferReason(state, publisherActiveOrDispatched, now = Date.now()) {
  if (publisherActiveOrDispatched) return "publisher_workflow_active_or_dispatched";
  return hasDueEditorialChannelQueue(state, now) ? null : "no_due_editorial_channel_recovery";
}

async function dispatchEditorialChannelUploadsWhenDue(env, tick, state, publisherProtected = false) {
  if (!state || !env.GITHUB_TOKEN) return;
  const deferReason = editorialChannelQueueDispatchDeferReason(
    state, publisherProtected, tick.getTime()
  );
  if (deferReason) {
    if (deferReason === "publisher_workflow_active_or_dispatched") {
      console.log("OFFERCHIN_EDITORIAL_CHANNEL_RECOVERY_DEFERRED reason=" + deferReason);
    }
    return;
  }
  // Recheck GitHub after the same-tick publisher decision: the regular publisher
  // owns first delivery, while this workflow is recovery-only for failed receipts.
  const activePublisher = await findActiveWorkflow(PUBLISHER_API, env.GITHUB_TOKEN);
  if (activePublisher) {
    console.log("OFFERCHIN_EDITORIAL_CHANNEL_RECOVERY_DEFERRED reason=publisher_workflow_" + activePublisher.status);
    return;
  }
  await dispatchWorkflowIfIdle(
    EDITORIAL_CHANNEL_API,
    env.GITHUB_TOKEN,
    "offerchin-editorial-channel-upload",
    18,
    8
  );
}

async function runScheduledCheck(env, scheduledTime) {
  const hasOfferChinToken = Boolean(env.GITHUB_TOKEN);
  const hasFiloToken = Boolean(env.FILO_GITHUB_TOKEN);
  if (!hasOfferChinToken && !hasFiloToken) {
    console.error("SCHEDULED_DISPATCH_BLOCKED: neither GITHUB_TOKEN nor FILO_GITHUB_TOKEN Worker secret is configured.");
    return;
  }

  const tick = Number.isFinite(Number(scheduledTime)) ? new Date(Number(scheduledTime)) : new Date();
  const offset = tick.getUTCMinutes() % 5;

  // Keep Filo independent: its dedicated credential must work even if OfferChin
  // credentials are absent or restricted. OfferChin uses only GITHUB_TOKEN.
  if (hasFiloToken && offset === 3) {
    try {
      await dispatchWorkflowIfIdle(FILO_API, env.FILO_GITHUB_TOKEN, FILO_WORKFLOW, 27, 8);
    } catch (error) {
      console.error("GOUSHIBAAZ_FILO_DISPATCH_FAILED", String(error).slice(0, 900));
    }
  } else if (offset === 3) {
    console.error("GOUSHIBAAZ_FILO_DISPATCH_BLOCKED: FILO_GITHUB_TOKEN is not configured.");
  }

  if (!hasOfferChinToken) return;
  const state = await readOfferChinState(env.GITHUB_TOKEN);

  // Continue persisted catalog pages on every tick. If category discovery is in
  // backoff and no work remains, wait for its retry_after rather than launching a
  // failing full workflow every minute. Catalog status is used only for catalog
  // dispatch; video fan-out has an independent gate and never waits for this scan.
  let catalogStatusForDispatch = null;
  try {
    catalogStatusForDispatch = await readCatalogSweepStatus(env.GITHUB_TOKEN);
    const categoryRetryAt = Date.parse(String(
      catalogStatusForDispatch && catalogStatusForDispatch.category_discovery_retry_after || ""
    ));
    const pendingPages = Math.max(0, Number(catalogStatusForDispatch && catalogStatusForDispatch.pending_page_count || 0));
    if (Number.isFinite(categoryRetryAt) && categoryRetryAt > tick.getTime() && pendingPages === 0) {
      console.log("OFFERCHIN_CATALOG_DISCOVERY_BACKOFF seconds_remaining=" +
        Math.ceil((categoryRetryAt - tick.getTime()) / 1000));
    } else {
      await dispatchWorkflowIfIdle(
        CATALOG_API,
        env.GITHUB_TOKEN,
        CATALOG_WORKFLOW,
        18,
        8,
        { ignoreOrphanedNoJobs: true }
      );
    }
  } catch (error) {
    console.error("OFFERCHIN_CATALOG_SWEEP_DISPATCH_FAILED", String(error).slice(0, 900));
  }

  // Integrity audit retains its independent five-minute slot.
  if (offset === 2) {
    try {
      await dispatchWorkflowIfIdle(AUDIT_API, env.GITHUB_TOKEN, AUDIT_WORKFLOW, 8, 4);
    } catch (error) {
      console.error("OFFERCHIN_INTEGRITY_AUDIT_DISPATCH_FAILED", String(error).slice(0, 900));
    }
  }

  let publisherProtected = false;
  try {
    publisherProtected = await dispatchPublisherWhenDue(env, tick, state) === true;
  } catch (error) {
    // On an uncertain dispatch result, prefer waiting for the next poll over
    // racing the primary publisher with a second sender.
    publisherProtected = true;
    console.error("OFFERCHIN_PUBLISHER_DISPATCH_FAILED", String(error).slice(0, 900));
  }

  // Every video destination has its own due check, workflow and failure boundary.
  // No channel/editorial schedule or sibling media workflow can block it.
  try {
    await dispatchEditorialChannelUploadsWhenDue(env, tick, state, publisherProtected);
  } catch (error) {
    console.error("OFFERCHIN_EDITORIAL_CHANNEL_DISPATCH_FAILED", String(error).slice(0, 900));
  }

  try {
    await dispatchVideoUploadsWhenDue(env, tick, state);
  } catch (error) {
    console.error("OFFERCHIN_VIDEO_DISPATCH_FAILED", String(error).slice(0, 900));
  }
}

export default {
  async scheduled(controller, env, ctx) {
    await runScheduledCheck(env, controller.scheduledTime);
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return response({
        ok: true,
        service: "affilio-minute-dispatcher",
        scheduledFiloDispatcher: true,
        filoCredentialConfigured: Boolean(env.FILO_GITHUB_TOKEN),
        offerChinCredentialConfigured: Boolean(env.GITHUB_TOKEN)
      });
    }
    return response({ ok: false, error: "not_found" }, 404);
  }
};