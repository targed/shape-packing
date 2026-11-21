// site/src/lib/workers/wasm_packer_worker.ts
import init, { solve_attempt_wasm } from '../../../public/wasm/packer_rs.js';

let isRunning = false;

self.onmessage = async (e: MessageEvent) => {
  const { command, serverUrl, username, workerId, wasmUrl, batchSize } = e.data;

  if (command === 'start') {
    isRunning = true;
    try {
      if (wasmUrl) {
        await init({ module_or_path: wasmUrl });
      } else {
        await init();
      }
      self.postMessage({ type: 'ready' });
      runLoop(serverUrl, username, workerId, batchSize || 500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      self.postMessage({ type: 'error', error: msg });
    }
  } else if (command === 'stop') {
    isRunning = false;
    self.postMessage({ type: 'stopped' });
  }
};

async function runLoop(serverUrl: string, username: string, workerId: string, batchSize: number) {
  while (isRunning) {
    try {
      // 1. Fetch work
      const workRes = await fetch(`${serverUrl}/api/v1/work?worker_id=${encodeURIComponent(workerId)}&cores=1`);
      if (workRes.status === 204) {
        self.postMessage({ type: 'idle', message: 'No pending work from coordinator' });
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      if (!workRes.ok) {
        throw new Error(`Coordinator returned ${workRes.status}`);
      }
      const work = await workRes.json();

      self.postMessage({ type: 'task_started', work });

      // 2. Run solver in Wasm
      const attemptsToRun = Math.max(50, Math.min(work.recommended_attempts || batchSize, batchSize));
      const rawResult = solve_attempt_wasm(
        work.inner_token,
        work.container_token,
        work.n,
        attemptsToRun,
        work.target_s ?? null
      );
      const result = JSON.parse(rawResult);
      const metric_s = result.final_metric ?? result.best_s;

      self.postMessage({
        type: 'iteration_complete',
        work_id: work.work_id,
        problem: work.problem,
        n: work.n,
        best_s: metric_s,
        coordinates: result.values,
        inner_token: work.inner_token,
        container_token: work.container_token,
        success: result.success,
      });

      // 3. Submit improvement if record beaten
      if (result.success && typeof metric_s === 'number' && metric_s > 0 && metric_s < work.target_s) {
        const solRes = await fetch(`${serverUrl}/api/v1/solutions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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

      // 4. Heartbeat
      await fetch(`${serverUrl}/api/v1/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          worker_id: workerId,
          work_id: work.work_id,
          attempts_completed: attemptsToRun,
          best_local_s: typeof metric_s === 'number' && metric_s > 0 ? metric_s : null,
        }),
      });

      self.postMessage({ type: 'attempts_completed', count: attemptsToRun });
      await new Promise((r) => setTimeout(r, 100));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      self.postMessage({ type: 'error', error: msg });
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
}
