// site/src/lib/workers/wasm_packer_worker.ts
import init, { solve_attempt_wasm } from '../../../public/wasm/packer_rs.js';

let isRunning = false;
let currentSecret = '';

function fetchWithTimeout(url: string, initObj: RequestInit = {}, timeoutMs = 15000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...initObj, signal: controller.signal }).finally(() => clearTimeout(timer));
}

self.onmessage = async (e: MessageEvent) => {
  const { command, serverUrl, username, workerId, workerSecret, wasmUrl, batchSize, pacingDelay } = e.data;

  if (command === 'set_secret' && typeof workerSecret === 'string') {
    currentSecret = workerSecret;
    return;
  }

  if (command === 'start') {
    isRunning = true;
    currentSecret = typeof workerSecret === 'string' ? workerSecret : '';
    try {
      if (wasmUrl) {
        await init({ module_or_path: wasmUrl });
      } else {
        await init();
      }
      self.postMessage({ type: 'ready' });
      runLoop(serverUrl, username, workerId, batchSize || 500, typeof pacingDelay === 'number' ? pacingDelay : 800);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      self.postMessage({ type: 'error', error: msg });
    }
  } else if (command === 'stop') {
    isRunning = false;
    self.postMessage({ type: 'stopped' });
  }
};

async function runLoop(
  serverUrl: string,
  username: string,
  workerId: string,
  batchSize: number,
  pacingDelay: number
) {
  while (isRunning) {
    try {
      const authHeaders: Record<string, string> = {};
      if (currentSecret) {
        authHeaders['Authorization'] = `Bearer ${currentSecret}`;
      }

      // 1. Fetch work
      const workRes = await fetchWithTimeout(
        `${serverUrl}/api/v1/work?worker_id=${encodeURIComponent(workerId)}&cores=1`,
        { headers: authHeaders }
      );
      if (workRes.status === 204) {
        self.postMessage({ type: 'idle', message: 'No pending work from coordinator' });
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      if (!workRes.ok) {
        throw new Error(`Coordinator returned ${workRes.status}`);
      }
      const work = await workRes.json();
      if (
        !work ||
        typeof work.problem !== 'string' ||
        !work.problem ||
        !Number.isInteger(work.n) ||
        work.n < 1 ||
        work.n > 200
      ) {
        throw new Error('Invalid work assignment received from coordinator');
      }

      self.postMessage({ type: 'task_started', work });

      // 2. Run solver in Wasm
      const attemptsToRun = Math.max(50, Math.min(Number(work.recommended_attempts) || batchSize, batchSize, 100000));
      const targetS = typeof work.target_s === 'number' && Number.isFinite(work.target_s) && work.target_s > 0
        ? work.target_s
        : null;
      const rawResult = solve_attempt_wasm(
        String(work.inner_token || '3'),
        String(work.container_token || 'CIRCLE'),
        work.n,
        attemptsToRun,
        targetS
      );
      const result = JSON.parse(rawResult);
      const metric_s = result.final_metric ?? result.best_s;
      const container_s = result.circumradius_s ?? result.best_s;

      self.postMessage({
        type: 'iteration_complete',
        work_id: work.work_id,
        problem: work.problem,
        n: work.n,
        best_s: metric_s,
        container_s: container_s,
        coordinates: result.values,
        inner_token: work.inner_token,
        container_token: work.container_token,
        success: result.success,
      });

      // 3. Submit improvement if record beaten (or no prior record exists)
      const improvesTarget = targetS === null || (typeof metric_s === 'number' && metric_s < targetS);
      if (result.success && typeof metric_s === 'number' && Number.isFinite(metric_s) && metric_s > 0 && improvesTarget) {
        const solRes = await fetchWithTimeout(`${serverUrl}/api/v1/solutions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders },
          body: JSON.stringify({
            work_id: work.work_id,
            worker_id: workerId,
            problem: work.problem,
            s: metric_s,
            coordinates: result.values,
          }),
        });

        if (solRes.ok) {
          const solData = await solRes.json();
          if (solData.verified) {
            self.postMessage({
              type: 'record_beaten',
              problem: work.problem,
              best_s: metric_s,
              coordinates: result.values,
            });
          }
        }
      }

      // 4. Heartbeat (must include Bearer authHeaders so coordinator credits attempts)
      const hbRes = await fetchWithTimeout(`${serverUrl}/api/v1/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          worker_id: workerId,
          work_id: work.work_id,
          attempts_completed: attemptsToRun,
          best_local_s: typeof metric_s === 'number' && metric_s > 0 ? metric_s : null,
        }),
      });
      if (!hbRes.ok) {
        throw new Error(`Heartbeat failed (${hbRes.status})`);
      }

      self.postMessage({ type: 'attempts_completed', count: attemptsToRun });
      await new Promise((r) => setTimeout(r, Math.max(50, pacingDelay)));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      self.postMessage({ type: 'error', error: msg });
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
}
