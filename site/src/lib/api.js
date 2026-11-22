// site/src/lib/api.js
// JavaScript companion for Node standard test runner and SSG

export function getDefaultCoordinatorUrl() {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const queryOverride = params.get('coordinator');
    if (queryOverride) {
      return queryOverride.replace(/\/$/, '');
    }
    const stored = window.localStorage.getItem('shape_packing_coordinator_url');
    if (stored) {
      return stored.replace(/\/$/, '');
    }
  }
  return 'http://localhost:8000';
}

export async function fetchClusterStats(baseUrl, fetchFn = fetch) {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/stats`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = await response.json();
    const data = {
      total_problems: Number(raw.total_problems || 0),
      active_workers: Number(raw.active_workers || 0),
      total_workers: Number(raw.total_workers || 0),
      total_attempts: Number(raw.total_attempts ?? raw.total_cluster_attempts ?? 0),
      records_broken: Number(raw.records_broken ?? raw.total_records_broken ?? 0),
      verified_solutions: Number(raw.verified_solutions ?? 0),
    };
    return { ok: true, data };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function fetchLeaderboard(baseUrl, fetchFn = fetch) {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/leaderboard`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = await response.json();
    const data = (Array.isArray(raw) ? raw : []).map((entry) => ({
      username: String(entry.username || 'anonymous'),
      total_attempts: Number(entry.total_attempts || 0),
      records_broken: Number(entry.records_broken || 0),
    }));
    return { ok: true, data };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}
