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

async function recoverStaleWorkflow(api, token, label, runningLimitMinutes, queuedLimitMinutes) {
  const active = await findActiveWorkflow(api, token);
  if (!active) return null;
  const run = active.run || {};
  const started = Date.parse(run.run_started_at || run.created_at || "");
  if (!run.id || !Number.isFinite(started)) return active;
  const ageMinutes = (Date.now() - started) / 60000;
  const limit = active.status === "in_progress" ? runningLimitMinutes : queuedLimitMinutes;
  if (ageMinutes < limit) return active;

  // A stuck run owns the shared channel-mutation concurrency lock. Cancel it so
  // a future tick can recover; never let an old worker block publishing forever.
  const runsApi = api.replace(/\/workflows\/[^/]+$/, "/runs");
  await githubRequest(`${runsApi}/${run.id}/cancel`, token, { method: "POST" });
  console.log(
    `CHANNEL_DISPATCH_STALE_CANCEL_REQUESTED workflow=${label} run_id=${run.id} ` +
    `status=${active.status} age_minutes=${Math.floor(ageMinutes)} threshold_minutes=${limit}`
  );
  return { status: "stale_cancelling", run };
}

async function dispatchWorkflowIfIdle(api, token, label, runningLimitMinutes, queuedLimitMinutes) {
  const active = await recoverStaleWorkflow(api, token, label, runningLimitMinutes, queuedLimitMinutes);
  if (active && active.status === "stale_cancelling") {
    console.log("CHANNEL_DISPATCH_SKIPPED workflow=" + label + " reason=stale_run_cancellation_requested");
    return;
  }
  if (active) {
    console.log("CHANNEL_DISPATCH_SKIPPED workflow=" + label + " reason=already_" + active.status + "; independent workflow remains unaffected");
    return;
  }
  await githubRequest(api + "/dispatches", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" })
  });
  console.log("CHANNEL_DISPATCH_ACCEPTED workflow=" + label);
}

const PUBLISHER_INTERVAL_MS = 17 * 60 * 1000;
const PUBLISHER_RETRY_GAP_MS = 3 * 60 * 1000;

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

function readLastChannelPublicationAt(state) {
  if (!state || typeof state !== "object") return null;
  const explicit = Date.parse(String(state.last_channel_published_at || ""));
  if (Number.isFinite(explicit)) return explicit;

  let latest = 0;
  const published = state.published && typeof state.published === "object" ? state.published : {};
  for (const record of Object.values(published)) {
    if (!record || typeof record !== "object") continue;
    const hasMessage =
      /^\d+$/.test(String(record.telegram_message_id || "")) ||
      /^\d+$/.test(String(record.bale_message_id || ""));
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

  const [latestAttempt] = await Promise.all([
    readLatestPublisherAttempt(env.GITHUB_TOKEN),
  ]);
  const lastPublishedAt = readLastChannelPublicationAt(state);
  const now = tick.getTime();
  if (lastPublishedAt !== null && now - lastPublishedAt < PUBLISHER_INTERVAL_MS) {
    console.log("OFFERCHIN_PUBLISHER_NOT_DUE seconds_remaining=" +
      Math.ceil((PUBLISHER_INTERVAL_MS - (now - lastPublishedAt)) / 1000));
    return;
  }

  const attemptAt = Date.parse(String(
    latestAttempt && (latestAttempt.updated_at || latestAttempt.run_started_at || latestAttempt.created_at) || ""
  ));
  if (Number.isFinite(attemptAt) && now - attemptAt < PUBLISHER_RETRY_GAP_MS) {
    console.log("OFFERCHIN_PUBLISHER_RETRY_WINDOW seconds_remaining=" +
      Math.ceil((PUBLISHER_RETRY_GAP_MS - (now - attemptAt)) / 1000));
    return;
  }

  await dispatchWorkflowIfIdle(
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 28
  );
}

const VIDEO_WORKFLOW_RETRY_GAP_MS = 5 * 60 * 1000;
const VIDEO_UPLOAD_CANDIDATE_LIMIT = 6;
const VIDEO_UPLOAD_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const VIDEO_PENDING_STATUSES = new Set([
  "pending", "pending_credentials", "retry", "skipped_unverified_deadline"
]);

function dateValue(value) {
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function hasChannelDelivery(record) {
  const delivery = record && record.delivery_status && typeof record.delivery_status === "object"
    ? record.delivery_status : {};
  return delivery.telegram === "sent" || delivery.bale === "sent" ||
    /^\d+$/.test(String(record.telegram_message_id || "")) ||
    /^\d+$/.test(String(record.bale_message_id || ""));
}

function videoRecordDue(record, platform, now) {
  if (!record || typeof record !== "object" || !hasChannelDelivery(record)) return false;
  const publishedAt = Number(record.ts || 0) * 1000;
  if (!Number.isFinite(publishedAt) || publishedAt <= 0 || now - publishedAt > VIDEO_UPLOAD_MAX_AGE_MS) return false;
  const status = String(record[platform + "_upload_status"] || "pending");
  if (!VIDEO_PENDING_STATUSES.has(status)) return false;
  const generation = String(record.video_generation_status || "pending");
  if (!["", "pending", "generated"].includes(generation)) return false;

  const generationRetry = dateValue(record.video_generation_next_attempt_at);
  if (generationRetry !== null && generationRetry > now) return false;
  const platformRetry = dateValue(record[platform + "_next_attempt_at"]);
  if (platformRetry !== null && platformRetry > now) return false;

  const expiry = dateValue(record.expires_at);
  if (expiry !== null && expiry <= now + 10 * 60 * 1000) return false;

  if (platform === "aparat") {
    const verifiedExpiry =
      record.expiry_deadline_verified_directly === true ||
      (record.expiry_source === "digikala_mcp_offer_card" &&
        record.expiry_deadline_verified_from_site_card === true);
    if (!verifiedExpiry) return false;
  }
  return true;
}

function hasDueVideoRecord(state, platform, now) {
  const published = state && state.published && typeof state.published === "object"
    ? state.published : {};
  const recent = Object.values(published)
    .sort((left, right) => {
      const leftTs = Number(left && left.ts || 0);
      const rightTs = Number(right && right.ts || 0);
      return (Number.isFinite(rightTs) ? rightTs : 0) - (Number.isFinite(leftTs) ? leftTs : 0);
    })
    .slice(0, VIDEO_UPLOAD_CANDIDATE_LIMIT);
  return recent.some(record => videoRecordDue(record, platform, now));
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

async function dispatchVideoPlatformWhenDue(env, tick, state, platform) {
  const config = platform === "youtube"
    ? { api: YOUTUBE_VIDEO_API, workflow: YOUTUBE_VIDEO_WORKFLOW, slot: "youtube_next_upload_at", pause: "youtube_uploads_paused_until" }
    : { api: APARAT_VIDEO_API, workflow: APARAT_VIDEO_WORKFLOW, slot: "aparat_next_upload_at", pause: null };

  const now = tick.getTime();
  const nextSlot = dateValue(state && state[config.slot]);
  const pauseUntil = config.pause ? dateValue(state && state[config.pause]) : null;
  if (nextSlot !== null && now < nextSlot) return;
  if (pauseUntil !== null && now < pauseUntil) return;
  if (!hasDueVideoRecord(state, platform, now)) return;

  const latestAttempt = await readLatestWorkflowAttempt(config.api, env.GITHUB_TOKEN);
  const attemptAt = dateValue(latestAttempt &&
    (latestAttempt.updated_at || latestAttempt.run_started_at || latestAttempt.created_at));
  if (attemptAt !== null && now - attemptAt < VIDEO_WORKFLOW_RETRY_GAP_MS) return;

  // Each platform owns its own workflow and saved due slot. Video jobs share
  // the channel publisher's state-writer lock to prevent concurrent state loss.
  await dispatchWorkflowIfIdle(config.api, env.GITHUB_TOKEN, config.workflow, 35, 30);
}

async function dispatchVideoUploadsWhenDue(env, tick, state) {
  if (!state) return;
  for (const platform of ["youtube", "aparat"]) {
    try {
      await dispatchVideoPlatformWhenDue(env, tick, state, platform);
    } catch (error) {
      console.error(
        "OFFERCHIN_" + platform.toUpperCase() + "_VIDEO_DISPATCH_FAILED",
        String(error).slice(0, 700)
      );
    }
  }
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
    await dispatchWorkflowIfIdle(CATALOG_API, env.GITHUB_TOKEN, CATALOG_WORKFLOW, 18, 8);
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

  // Video destinations are dispatched from their own saved upload clocks.
  // Neither media schedule reads or reserves the Telegram/Bale posting interval.
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