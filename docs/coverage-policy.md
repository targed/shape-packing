Test coverage policy and current posture

Goal
- Maintain strong, meaningful test coverage without forcing artificial 100%.
- Prefer:
  - clear, readable tests
  - real edge cases, error paths, and deterministic behavior
  - fast and stable CI behavior
- Avoid:
  - brittle tests written solely to “turn green” obscure lines
  - flaky, heavy, or long-running tests (e.g. real optimizer loops)
  - tightly coupled tests that break whenever internal wiring changes.

What we did
- Ran pytest with coverage (pytest + --cov=shape_packing) and targeted:
  - agent_loop.py: problem selection, history, priority queue, and fallback logic.
  - solution_tools.py:
    - loading values/positions
    - metric scaling verification
    - overlap and container-bounds checks
    - record comparison paths (NEW RECORD vs valid)
  - problems.py:
    - parse_problem edge cases
    - list_problem_families
  - ranker.py:
    - scoring, numeric fallback
    - generate_queue behavior with real-like directory layout
  - optimization.py:
    - PackingProblem setup and short runs (avoid long optimization)
  - geometry.py:
    - geometry utilities and overlap checks (via public functions)
  - cli.py:
    - basic entrypoint and argument handling (via subprocess mocking)

Current coverage (approximate; run with --cov=shape_packing)
- agent_loop.py: ~97%
- solution_tools.py: ~98%
- problems.py: ~98%
- ranker.py: ~98%
- optimization.py: ~92%
- packing_config.py: 100%
- geometry.py: ~56%
- cli.py: ~27%
- Overall: ~82%

Intentionally not 100%: why
- Numba-compiled code (geometry.py):
  - Coverage cannot reliably track execution inside JIT-compiled functions.
  - We call these functions from tests; forcing 100% at the line level is misleading.
- Deep error-handling branches:
  - Some branches exist to defend against malformed external data (bad JSON, corrupted priority queue).
  - We cover the main patterns; extra artificial fixtures to hit every single defensive return add noise.
- Optimization loops (optimization.py):
  - Many lines sit inside long-running BH/PyTorch/scipy loops.
  - We test interfaces, configuration, and short, controlled runs;
    forcing 100% would require either:
    - dangerously long CI times
    - or weird, unrealistic inputs that don’t reflect real usage.
- CLI entrypoints (cli.py):
  - Thin wrappers around subprocess calls; heavily coupled to runtime behavior.
  - We validate argument routing and basic flows;
    fully mocking everything is fragile and low-value.

How to maintain this
- When adding or changing functionality:
  - Add tests for:
    - expected inputs and outputs
    - realistic edge cases
    - obvious error conditions
  - Do not:
    - add tests solely to chase last few percent of coverage in Numba/loops/CLI.
- If coverage drops meaningfully (e.g. >5% overall or >10% in a core module),
  treat it as a signal to add tests, not to chase numbers.
