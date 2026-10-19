const OWNER = "Mehran0960";
const REPO = "ai_news_bot";
const WORKFLOW = "affilio-radar.yml";
const API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`;
const COUNTDOWN_WORKFLOW = "affilio-countdown-refresh.yml";
const COUNTDOWN_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${COUNTDOWN_WORKFLOW}`;
const CLEANUP_WORKFLOW = "affilio-expiration-cleanup.yml";
const CLEANUP_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${CLEANUP_WORKFLOW}`;
const CHANNEL_WORKFLOWS = [
  { name: COUNTDOWN_WORKFLOW, api: COUNTDOWN_API },
  { name: WORKFLOW, api: API },
  { name: CLEANUP_WORKFLOW, api: CLEANUP_API }
];

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
  // "pending" is important too: GitHub reports concurrency-blocked runs that way.
  for (const status of ["queued", "pending", "in_progress"]) {
    const query = new URLSearchParams({ branch: "main", status, per_page: "1" });
    const data = await githubRequest(`${api}/runs?${query}`, token);
    if (Array.isArray(data.workflow_runs) && data.workflow_runs.length > 0) {
      return status;
    }
  }
  return "";
}

async function runScheduledCheck(env, scheduledTime) {
  if (!env.GITHUB_TOKEN) {
    console.error("COUNTDOWN_DISPATCH_BLOCKED: GITHUB_TOKEN Worker secret is not configured.");
    return;
  }

  const now = Number.isFinite(Number(scheduledTime)) ? new Date(Number(scheduledTime)) : new Date();
  const minute = now.getUTCMinutes();
  const offset = minute % 5;

  // Reserve :02/:07/... for GitHub's native product-radar schedule.
  // Countdown edits run inside the cleanup workflow; avoid a separate countdown job
  // competing for the same channel-mutation lock.
  if (offset === 2) {
    console.log(`CHANNEL_DISPATCH_SKIPPED: reserving UTC minute ${minute} for native product-radar schedule.`);
    return;
  }
  // Cleanup is the priority job at :00; :01 and :04 remain quiet to avoid creating
  // a new run that overlaps cleanup or the five-minute radar slot.
  if (offset !== 0 && offset !== 3) {
    console.log(`CHANNEL_DISPATCH_SKIPPED: no standalone countdown dispatch at UTC minute ${minute}; cleanup refreshes active captions.`);
    return;
  }

  try {
    // Every channel-mutating workflow shares one concurrency group. Avoid overlap and queue buildup.
    for (const workflow of CHANNEL_WORKFLOWS) {
      const status = await findActiveWorkflow(workflow.api, env.GITHUB_TOKEN);
      if (status) {
        console.log(`CHANNEL_DISPATCH_SKIPPED: ${workflow.name} is already ${status}.`);
        return;
      }
    }

    const cleanupDispatch = offset === 0;
    const radarFallback = offset === 3;
    const targetApi = cleanupDispatch ? CLEANUP_API : (radarFallback ? API : COUNTDOWN_API);
    const payload = radarFallback
      ? { ref: "main", inputs: { external_scheduler: true } }
      : { ref: "main" };

    await githubRequest(`${targetApi}/dispatches`, env.GITHUB_TOKEN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const dispatchMessage = cleanupDispatch
      ? "EXPIRATION_CLEANUP_DISPATCH_ACCEPTED"
      : (radarFallback ? "PRODUCT_RADAR_FALLBACK_DISPATCH_ACCEPTED" : "COUNTDOWN_DISPATCH_ACCEPTED");
    console.log(dispatchMessage);
  } catch (error) {
    // Never keep queuing failed dispatch attempts; the next one-minute tick can retry.
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
