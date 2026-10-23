const OWNER = "Mehran0960";
const REPO = "ai_news_bot";
const WORKFLOW = "affilio-radar.yml";
const API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`;
const CLEANUP_WORKFLOW = "affilio-expiration-cleanup.yml";
const CLEANUP_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${CLEANUP_WORKFLOW}`;
const RUNS_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/runs`;

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
  await githubRequest(`${RUNS_API}/${run.id}/cancel`, token, { method: "POST" });
  console.log(
    `CHANNEL_DISPATCH_STALE_CANCEL_REQUESTED workflow=${label} run_id=${run.id} ` +
    `status=${active.status} age_minutes=${Math.floor(ageMinutes)} threshold_minutes=${limit}`
  );
  return { status: "stale_cancelling", run };
}

async function runScheduledCheck(env, scheduledTime) {
  if (!env.GITHUB_TOKEN) {
    console.error("CHANNEL_DISPATCH_BLOCKED: GITHUB_TOKEN Worker secret is not configured.");
    return;
  }

  const tick = Number.isFinite(Number(scheduledTime)) ? new Date(Number(scheduledTime)) : new Date();
  const minute = tick.getUTCMinutes();
  const offset = minute % 5;

  // Keep :02/:07/... for GitHub's native five-minute product-radar schedule.
  if (offset === 2) {
    console.log(`CHANNEL_DISPATCH_SKIPPED: reserving UTC minute ${minute} for native product-radar schedule.`);
    return;
  }
  if (offset !== 0 && offset !== 3) {
    console.log(`CHANNEL_DISPATCH_SKIPPED: reserved UTC minute ${minute}; no dispatch on this tick.`);
    return;
  }

  try {
    const radar = await recoverStaleWorkflow(API, env.GITHUB_TOKEN, WORKFLOW, 18, 8);
    if (radar?.status === "stale_cancelling") return;
    if (radar) {
      console.log(`CHANNEL_DISPATCH_SKIPPED: product radar is already ${radar.status}; preserving publishing priority.`);
      return;
    }

    const cleanup = await recoverStaleWorkflow(CLEANUP_API, env.GITHUB_TOKEN, CLEANUP_WORKFLOW, 12, 8);
    if (cleanup?.status === "stale_cancelling") return;

    const cleanupDispatch = offset === 0;
    const radarFallback = offset === 3;
    if (cleanupDispatch && cleanup) {
      console.log(`CHANNEL_DISPATCH_SKIPPED: expiry cleanup is already ${cleanup.status}.`);
      return;
    }

    // Cleanup refreshes legacy captions only on an explicit one-time repair.
    // Every normal tick must keep fresh product discovery as the first priority.
    if (cleanupDispatch) {
      await githubRequest(CLEANUP_API + "/enable", env.GITHUB_TOKEN, { method: "PUT" });
      console.log("EXPIRATION_CLEANUP_WORKFLOW_ENABLED");
    }

    const targetApi = cleanupDispatch ? CLEANUP_API : API;
    const payload = radarFallback ? { ref: "main", inputs: { external_scheduler: true } } : { ref: "main" };
    await githubRequest(targetApi + "/dispatches", env.GITHUB_TOKEN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    console.log(cleanupDispatch ? "EXPIRATION_CLEANUP_DISPATCH_ACCEPTED" : "PRODUCT_RADAR_FALLBACK_DISPATCH_ACCEPTED");
  } catch (error) {
    console.error("CHANNEL_DISPATCH_FAILED", String(error).slice(0, 900));
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
