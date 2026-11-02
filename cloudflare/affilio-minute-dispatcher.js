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

async function runScheduledCheck(env, scheduledTime) {
  if (!env.GITHUB_TOKEN) {
    console.error("CHANNEL_DISPATCH_BLOCKED: GITHUB_TOKEN Worker secret is not configured.");
    return;
  }
  const tick = Number.isFinite(Number(scheduledTime)) ? new Date(Number(scheduledTime)) : new Date();
  const minute = tick.getUTCMinutes();
  const offset = minute % 5;

  // The crawler, publisher, and integrity auditor have separate workflow locks.
  // Dispatch them in fixed minute offsets within each five-minute window.
  if (offset === 1) {
    try {
      await dispatchWorkflowIfIdle(CATALOG_API, env.GITHUB_TOKEN, CATALOG_WORKFLOW, 18, 8);
    } catch (error) {
      console.error("OFFERCHIN_CATALOG_SWEEP_DISPATCH_FAILED", String(error).slice(0, 900));
    }
    return;
  }

  // Retailer validation traffic stays separate from the publication slot.
  if (offset === 2) {
    try {
      await dispatchWorkflowIfIdle(AUDIT_API, env.GITHUB_TOKEN, AUDIT_WORKFLOW, 8, 4);
    } catch (error) {
      console.error("OFFERCHIN_INTEGRITY_AUDIT_DISPATCH_FAILED", String(error).slice(0, 900));
    }
    return;
  }

  if (offset !== 0) {
    console.log("CHANNEL_DISPATCH_SKIPPED: UTC minute " + minute + " reserved; publisher runs at :00, catalog sweep at :01, and audit at :02 in each five-minute window.");
    return;
  }

  try {
    await dispatchWorkflowIfIdle(PUBLISHER_API, env.GITHUB_TOKEN, PUBLISHER_WORKFLOW, 20, 6);
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