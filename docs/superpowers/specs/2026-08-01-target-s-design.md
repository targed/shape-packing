# Design Spec: Enforcing Target S (Funneled Approach)

## 1. Goal
When running the autonomous loop, the system should not start from scratch in massively oversized containers. It should use the currently known `best_score` for the target problem to aggressively "short-circuit" the optimization, forcing the solver to focus purely on attempting to beat the world record.

## 2. Approach: Funneled Targeting

We will use a "funnel" approach to balance aggression and randomness:

- **Target Calculation:** The python loop will convert the `best_score` (a Friedman metric) into its native circumradius value ($S$) and pass it to the solver.
- **Initial Start:** The solver starts the container at exactly `1.05 * target_s`.
- **Randomness Preserved:** Shapes are still scattered completely randomly within this 5% larger boundary.
- **Early Abort:** If the shapes get "stuck" (i.e. the solver fails to find a valid packing at the current size step) and the current container size $S$ is still larger than `target_s`, the attempt is considered a failure and aborted immediately. We do not want to record or waste time on packings that are worse than what we already have.

## 3. Architecture Changes

### A. `packer_rs/src/main.rs` (Rust Solver)
- Add a new `--target-s <f64>` optional argument.
- If `--target-s` is provided:
  - Modify `dynamic_s` calculation in `run_attempt` to start at `target_s * 1.05`.
  - Add logic at the end of the `run_attempt` loop: if the solver halts at a `last_valid_s` that is $>=$ `target_s`, it should yield `f64::INFINITY` (failure) so it doesn't even bother trying to update the global `best_s` mutex.
  - *Caution:* We must ensure that the early abort triggers *after* attempting perturbations, so it doesn't accidentally abort a solve that just needed a tiny nudge. The existing perturbation loop handles this.

### B. `src/shape_packing/cli.py` (Python Loop)
- In `handle_run`, if `best_score` is not "None":
  - Import the inverse logic of `compute_friedman_metric` (we may need to write a quick helper function for this in `solution_tools.py`, e.g., `inverse_friedman_metric(friedman_metric, inner_token, container_token) -> S`).
  - Calculate `target_s`.
  - Pass `--target-s {target_s}` to the Rust subprocess.

## 4. Future Consideration: The Hybrid Approach

*Note: Documented here for future exploration.*
If we find that the 1.05x funnel is still too slow, or conversely, if we find it prevents the solver from discovering deeply hidden configurations, we can transition to a **Hybrid Approach**. This would allocate a percentage of solver attempts to a "Strict Cutoff" (starting exactly at `target_s` for rapid stochastic sampling) while maintaining a percentage of attempts for the funneled approach (starting larger to give shapes room to untangle).
