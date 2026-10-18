const OWNER = "Mehran0960";
const REPO = "ai_news_bot";
const WORKFLOW = "affilio-radar.yml";
const API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`;
const COUNTDOWN_WORKFLOW = "affilio-countdown-refresh.yml";
const COUNTDOWN_API = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${COUNTDOWN_WORKFLOW}`;

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

async function dispatchCountdownRefresh(env) {
  try {
    // Countdown refresh has its own short workflow, so it may run while product discovery is busy.
    for (const status of ["queued", "in_progress"]) {
      const query = new URLSearchParams({ branch: "main", status, per_page: "1" });
      const data = await githubRequest(`${COUNTDOWN_API}/runs?${query}`, env.GITHUB_TOKEN);
      if (Array.isArray(data.workflow_runs) && data.workflow_runs.length > 0) {
        console.log(`COUNTDOWN_DISPATCH_SKIPPED: refresh workflow is already ${status}.`);
        return;
      }
    }

    await githubRequest(`${COUNTDOWN_API}/dispatches`, env.GITHUB_TOKEN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" })
    });
    console.log("COUNTDOWN_DISPATCH_ACCEPTED");
  } catch (error) {
    // Caption refresh should not block the independent product-scanning dispatcher.
    console.error("COUNTDOWN_DISPATCH_FAILED", String(error).slice(0, 900));
  }
}

async function runScheduledCheck(env) {
  if (!env.GITHUB_TOKEN) {
    console.error("DISPATCH_BLOCKED: GITHUB_TOKEN Worker secret is not configured.");
    return;
  }

  // Keep countdown updates independent of the full product scan.
  await dispatchCountdownRefresh(env);

  try {
    // Fail closed: never launch another scan while the previous one is queued or running.
    for (const status of ["queued", "in_progress"]) {
      const query = new URLSearchParams({ branch: "main", status, per_page: "1" });
      const data = await githubRequest(`${API}/runs?${query}`, env.GITHUB_TOKEN);
      if (Array.isArray(data.workflow_runs) && data.workflow_runs.length > 0) {
        console.log(`DISPATCH_SKIPPED: an Affilio workflow is already ${status}.`);
        return;
      }
    }

    const dispatched = await githubRequest(`${API}/dispatches`, env.GITHUB_TOKEN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          external_scheduler: true
        }
      })
    });
    console.log("DISPATCH_ACCEPTED", JSON.stringify(dispatched));
  } catch (error) {
    // No same-tick retry: avoid duplicates if GitHub's response is ambiguous.
    console.error("DISPATCH_FAILED", String(error).slice(0, 1200));
  }
}

export default {
  async scheduled(controller, env, ctx) {
    await runScheduledCheck(env);
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return response({ ok: true, service: "affilio-minute-dispatcher" });
    }
    return response({ ok: false, error: "not_found" }, 404);
  }
};
