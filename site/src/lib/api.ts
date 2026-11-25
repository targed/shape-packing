// site/src/lib/api.ts

export interface ClusterStats {
  total_problems: number;
  active_workers: number;
  total_workers?: number;
  total_attempts: number;
  records_broken: number;
  verified_solutions: number;
}

export interface LeaderboardEntry {
  username: string;
  total_attempts: number;
  records_broken: number;
}

export interface RecentSolution {
  id: number;
  problem_id: string;
  n: number;
  inner_token: string;
  container_token: string;
  metric_s: number;
  reference_s?: number;
  diff?: number;
  is_current_record: boolean;
  worker_username: string;
  verified_at: string;
}

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

export function getDefaultCoordinatorUrl(): string {
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
  return 'https://shape-packing.azurewebsites.net';
}

export async function fetchClusterStats(
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<ClusterStats>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/stats`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = (await response.json()) as any;
    const data: ClusterStats = {
      total_problems: Number(raw.total_problems || 0),
      active_workers: Number(raw.active_workers || 0),
      total_workers: Number(raw.total_workers || 0),
      total_attempts: Number(raw.total_attempts ?? raw.total_cluster_attempts ?? 0),
      records_broken: Number(raw.records_broken ?? raw.total_records_broken ?? 0),
      verified_solutions: Number(raw.verified_solutions ?? 0),
    };
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function fetchRecentSolutions(
  limit: number = 20,
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<RecentSolution[]>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/recent_solutions?limit=${limit}`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = (await response.json()) as any[];
    const data: RecentSolution[] = (Array.isArray(raw) ? raw : []).map((entry) => ({
      id: Number(entry.id || 0),
      problem_id: String(entry.problem_id || ''),
      n: Number(entry.n || 0),
      inner_token: String(entry.inner_token || ''),
      container_token: String(entry.container_token || ''),
      metric_s: Number(entry.metric_s || 0),
      reference_s: entry.reference_s !== null && entry.reference_s !== undefined ? Number(entry.reference_s) : undefined,
      diff: entry.diff !== null && entry.diff !== undefined ? Number(entry.diff) : undefined,
      is_current_record: Boolean(entry.is_current_record),
      worker_username: String(entry.worker_username || 'anonymous'),
      verified_at: String(entry.verified_at || ''),
    }));
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function fetchLeaderboard(
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<LeaderboardEntry[]>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/leaderboard`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = (await response.json()) as any[];
    const data: LeaderboardEntry[] = (Array.isArray(raw) ? raw : []).map((entry) => ({
      username: String(entry.username || 'anonymous'),
      total_attempts: Number(entry.total_attempts || 0),
      records_broken: Number(entry.records_broken || 0),
    }));
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function fetchRecentSolutions(
  limit: number = 20,
  baseUrl?: string,
  fetchFn: typeof fetch = fetch
): Promise<ApiResult<RecentSolution[]>> {
  const url = `${baseUrl || getDefaultCoordinatorUrl()}/api/v1/recent_solutions?limit=${limit}`;
  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 3500) : null;
    const response = await fetchFn(url, { signal: controller ? controller.signal : undefined });
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}: ${response.statusText}` };
    }
    const raw = (await response.json()) as any[];
    const data: RecentSolution[] = (Array.isArray(raw) ? raw : []).map((entry) => ({
      id: Number(entry.id || 0),
      problem_id: String(entry.problem_id || ''),
      n: Number(entry.n || 0),
      inner_token: String(entry.inner_token || ''),
      container_token: String(entry.container_token || ''),
      metric_s: Number(entry.metric_s || 0),
      reference_s: entry.reference_s !== null && entry.reference_s !== undefined ? Number(entry.reference_s) : undefined,
      diff: entry.diff !== null && entry.diff !== undefined ? Number(entry.diff) : undefined,
      is_current_record: Boolean(entry.is_current_record),
      worker_username: String(entry.worker_username || 'anonymous'),
      verified_at: String(entry.verified_at || ''),
    }));
    return { ok: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}
