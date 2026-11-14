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
const RUNS_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/runs`;
const FILO_REPO = "Goushibaaz";
const FILO_WORKFLOW = "filo-native-republish.yml";
const FILO_API = `https://api.github.com/repos/${OWNER}/${FILO_REPO}/actions/workflows/${FILO_WORKFLOW}`;
const VIDEO_PUBLISHER_WORKFLOW = "offerchin-video-publisher.yml";
const VIDEO_PUBLISHER_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${VIDEO_PUBLISHER_WORKFLOW}`;

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

export const PUBLISHER_INTERVAL_MS = 27 * 60 * 1000;
export const PUBLISHER_STANDALONE_EDITORIAL_GAP_MS = 55 * 60 * 1000;
const PUBLISHER_RETRY_GAP_MS = 3 * 60 * 1000;

export function nextPublisherDueAt(state, lastPublishedAt) {
  const scheduledAt = Date.parse(String(state && state.next_channel_content_due_at || ""));
  const editorialPlanningAt = Date.parse(String(state && state.next_editorial_planning_at || ""));
  const lastPost = Number.isFinite(lastPublishedAt) ? lastPublishedAt : null;
  const plannedTimes = [scheduledAt, editorialPlanningAt].filter(Number.isFinite);

  let dueAt = plannedTimes.length
    ? Math.min(...plannedTimes)
    : lastPost !== null
      ? lastPost + PUBLISHER_STANDALONE_EDITORIAL_GAP_MS
      : null;

  if (dueAt !== null && lastPost !== null) {
    dueAt = Math.max(dueAt, lastPost + PUBLISHER_INTERVAL_MS);
  }
  return dueAt;
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

async function readLatestPublisherAttempt(token) {
  try {
    const query = new URLSearchParams({ branch: "main", per_page: "10" });
    const data = await githubRequest(`${PUBLISHER_API}/runs?${query}`, token);
    const rows = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
    return rows.find(run => run && run.event === "workflow_dispatch" && run.head_branch === "main") || null;
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
    return;
  }

  if (!state) {
    console.warn("OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=publication_state_unavailable");
    return;
  }

  const [latestAttempt, catalogStatus] = await Promise.all([
    readLatestPublisherAttempt(env.GITHUB_TOKEN),
    readCatalogSweepStatus(env.GITHUB_TOKEN),
  ]);
  const lastPublishedAt = readLastChannelPublicationAt(state);
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
    } else {
      console.log(
        "OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=no_valid_clean_catalog_snapshot" +
        " latest_attempt_status=" + String(catalogStatus && catalogStatus.last_cycle_status || "unknown") +
        " last_clean_cycle_at=" + String(catalogStatus && catalogStatus.last_clean_cycle_completed_at || "unknown")
      );
      return;
    }
  } else {
    // Reuse the last immutable clean snapshot while the next full scan runs.
    // A new full scan is not required between two 27-minute publication slots.
    console.log(
      "OFFERCHIN_PUBLISHER_USING_CLEAN_SNAPSHOT cycle=" +
      String(catalogStatus.last_clean_cycle_completed_at) +
      " candidates=" + String(catalogStatus.completed_candidates_count) +
      " unscanned_new_categories=" + String(catalogStatus.unscanned_new_category_count || 0) +
      "/" + String(catalogStatus.unscanned_new_category_budget || 0)
    );
  }
  const now = tick.getTime();
  const nextDueAt = nextPublisherDueAt(state, lastPublishedAt);
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

  // A clean new catalog cycle refreshes the product cohort even while the next
  // product slot is in the future. This reflows the floating plan without posting early.
  if (!newCleanCycleReady && nextDueAt !== null && now < nextDueAt) {
    console.log("OFFERCHIN_PUBLISHER_NOT_DUE seconds_remaining=" +
      Math.ceil((nextDueAt - now) / 1000) +
      " next_content_due_at=" + new Date(nextDueAt).toISOString());
    return;
  }
  // New-scan refreshes may happen before a product slot, but never bypass the
  // hard minimum spacing between two public channel posts.
  if (lastPublishedAt !== null && now - lastPublishedAt < PUBLISHER_INTERVAL_MS) {
    console.log("OFFERCHIN_PUBLISHER_MINIMUM_GAP seconds_remaining=" +
      Math.ceil((PUBLISHER_INTERVAL_MS - (now - lastPublishedAt)) / 1000));
    return;
  }

  const attemptAt = Date.parse(String(
    latestAttempt && (latestAttempt.updated_at || latestAttempt.run_started_at || latestAttempt.created_at) || ""
  ));
  const retryGap = degradedLiveFallback ? PUBLISHER_INTERVAL_MS : PUBLISHER_RETRY_GAP_MS;
  if (Number.isFinite(attemptAt) && now - attemptAt < retryGap) {
    console.log("OFFERCHIN_PUBLISHER_RETRY_WINDOW seconds_remaining=" +
      Math.ceil((retryGap - (now - attemptAt)) / 1000));
    return;
  }

  await dispatchWorkflowIfIdle(
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 28
  );
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
  if (!["pending", "generated", "skipped_expiring_soon", "skipped_unverified_deadline"].includes(generation)) {
    return false;
  }

  const expiry = dateValue(record.expires_at);
  if (expiry !== null && expiry <= timestamp + 10 * 60 * 1000) return false;
  const verifiedExpiry = hasVerifiedVideoExpiry(record);

  if (platform === "aparat" && !verifiedExpiry) return false;

  if (generation === "skipped_expiring_soon") {
    // Only a directly verified, still-live deadline can reactivate an old skip.
    return verifiedExpiry && (
      VIDEO_PENDING_STATUSES.has(status) || status === "skipped_expiring_soon"
    );
  }

  if (generation === "skipped_unverified_deadline") {
    // YouTube's policy changed: its already-published channel item can be uploaded
    // without a retailer timer. Aparat remains deadline-gated; Filo is not awakened
    // from this terminal generation state by the minute dispatcher.
    if (platform === "youtube") {
      return VIDEO_PENDING_STATUSES.has(status) || status === "skipped_unverified_deadline";
    }
    if (platform === "aparat") {
      return verifiedExpiry && (
        VIDEO_PENDING_STATUSES.has(status) || status === "skipped_unverified_deadline"
      );
    }
    return false;
  }

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

export function hasDueVideoRecord(state, platform, now) {
  const published = state && state.published && typeof state.published === "object"
    ? state.published : {};
  // The compact dispatcher sidecar already caps this at the 250 most recent
  // selected-product records. Do not inspect only the newest six: that can
  // hide an older pending upload behind six newer completed uploads.
  return Object.values(published).some(record => videoRecordDue(record, platform, now));
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
  if (!state || typeof state !== "object" || !state.published || typeof state.published !== "object") {
    return false;
  }
  const timestamp = Number.isFinite(Number(now)) ? Number(now) : Date.now();
  return Object.values(state.published).some((record) => {
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
        // Dispatch even when a platform-specific preflight will skip it; Python
        // records that terminal result and still advances the other destinations.
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
}

async function dispatchVideoUploadsWhenDue(env, tick, state) {
  if (!state || !env.GITHUB_TOKEN) return;
  // The unified Python workflow performs fresh per-platform preflight checks,
  // including Filo login verification and Aparat deadline checks. Dispatch based
  // on persisted pending statuses so those checks can terminally skip unavailable
  // destinations instead of making an ineligible record block the FIFO forever.
  if (!hasPendingVideoQueue(state)) return;
  await dispatchWorkflowIfIdle(
    VIDEO_PUBLISHER_API,
    env.GITHUB_TOKEN,
    VIDEO_PUBLISHER_WORKFLOW,
    45,
    30
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

  // Check the catalog workflow on every one-minute tick. The idle/stale-run
  // guard below prevents overlap; dispatching only at offset 1 used to leave
  // several minutes of avoidable idle time after a short successful batch.
  try {
    await dispatchWorkflowIfIdle(
      CATALOG_API,
      env.GITHUB_TOKEN,
      CATALOG_WORKFLOW,
      18,
      8,
      { ignoreOrphanedNoJobs: true }
    );
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

  try {
    await dispatchPublisherWhenDue(env, tick, state);
  } catch (error) {
    console.error("OFFERCHIN_PUBLISHER_DISPATCH_FAILED", String(error).slice(0, 900));
  }

  // One unified event-driven video workflow consumes the shared FIFO; the minute
  // poll is a recovery path for any queue items left after a bounded workflow batch.
  await dispatchVideoUploadsWhenDue(env, tick, state);
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