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

const PUBLISHER_INTERVAL_MS = 23 * 60 * 1000;
const PUBLISHER_RETRY_GAP_MS = 3 * 60 * 1000;

async function readLastChannelPublicationAt(token) {
  try {
    const data = await githubRequest(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/affilio_radar/state.json?ref=main`,
      token
    );
    const encoded = String(data.content || "").replace(/\s/g, "");
    if (!encoded) return null;
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    const state = JSON.parse(new TextDecoder().decode(bytes));
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
  } catch (error) {
    console.error("OFFERCHIN_CHANNEL_CLOCK_READ_FAILED", String(error).slice(0, 500));
    return null;
  }
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

async function dispatchPublisherWhenDue(env, tick) {
  const active = await recoverStaleWorkflow(
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 6
  );
  if (active) {
    console.log("OFFERCHIN_PUBLISHER_NOT_DISPATCHED reason=active_workflow_" + active.status);
    return;
  }

  const [lastPublishedAt, latestAttempt] = await Promise.all([
    readLastChannelPublicationAt(env.GITHUB_TOKEN),
    readLatestPublisherAttempt(env.GITHUB_TOKEN),
  ]);
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
    PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 28, 6
  );
}

async function runScheduledCheck(env, scheduledTime) {
  if (!env.GITHUB_TOKEN) {
    console.error("CHANNEL_DISPATCH_BLOCKED: GITHUB_TOKEN Worker secret is not configured.");
    return;
  }
  const tick = Number.isFinite(Number(scheduledTime)) ? new Date(Number(scheduledTime)) : new Date();
  const offset = tick.getUTCMinutes() % 5;

  // Discovery, audit and Filo remain independent from the actual channel cadence.
  if (offset === 1) {
    try {
      await dispatchWorkflowIfIdle(CATALOG_API, env.GITHUB_TOKEN, CATALOG_WORKFLOW, 18, 8);
    } catch (error) {
      console.error("OFFERCHIN_CATALOG_SWEEP_DISPATCH_FAILED", String(error).slice(0, 900));
    }
  }
  if (offset === 2) {
    try {
      await dispatchWorkflowIfIdle(AUDIT_API, env.GITHUB_TOKEN, AUDIT_WORKFLOW, 8, 4);
    } catch (error) {
      console.error("OFFERCHIN_INTEGRITY_AUDIT_DISPATCH_FAILED", String(error).slice(0, 900));
    }
  }
  if (offset === 3) {
    try {
      await dispatchWorkflowIfIdle(FILO_API, env.GITHUB_TOKEN, FILO_WORKFLOW, 27, 8);
    } catch (error) {
      console.error("GOUSHIBAAZ_FILO_DISPATCH_FAILED", String(error).slice(0, 900));
    }
  }

  try {
    await dispatchPublisherWhenDue(env, tick);
  } catch (error) {
    console.error("OFFERCHIN_PUBLISHER_DISPATCH_FAILED", String(error).slice(0, 900));
  }
}

export default {
  async scheduled(controller, env, ctx) {
    await runScheduledCheck(env, controller.scheduledTime);
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return response({ ok: true, service: "affilio-minute-dispatcher" });
    }
    return response({ ok: false, error: "not_found" }, 404);
  }
};