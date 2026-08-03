Got it. I’ll go through each non-shape-family requirements file, compare against the actual code, and call out what’s correct, what’s wrong/aspirational, and what should be adjusted.

I’ll do them in order.

1) 00-system-overview.md

Checks:

- “The system SHALL do this using deterministic, mathematically verifiable optimization — no ML.”
    - Confirmed: pyproject.toml and all main modules (agent_loop, geometry, optimization, cli, run_*.py) use only numerical optimization, no ML libraries.
    - Verdict: OK.

- “WHEN a packing is claimed as improved THEN it SHALL be provably valid by SAT-style checks at or better than 1e-15 tolerance.”
    - geometry.py: bh_objective uses SAT-style checks.
    - solution_tools.py: verify_solution uses sat_check_overlap with TOLERANCE=1e-15.
    - Verdict: OK.

- “Mode 1 (pure-code autoresearch) via run_autoresearch_loop.py or run_parallel_loop.py, no LLM.”
    - run_autoresearch_loop.py: loops suggest + run, no LLM.
    - run_parallel_loop.py: parallel dispatch via ProcessPoolExecutor, no LLM.
    - Verdict: OK.

- “Mode 2 (LLM-assisted) via program.md + train.py; geometric validation and metric comparison SHALL remain unchanged.”
    - program.md defines LLM-assisted loop that edits polygon_packer.py/train.py but never changes verification.
    - Verdict: OK (at policy level).

- “WHEN a packing is marked as valid THEN: no overlaps beyond tolerance; all shapes contained.”
    - solution_tools.py verify_solution checks overlaps (SAT) and container bounds.
    - Verdict: OK.

- “IF floating-point anomalies could cause false records THEN system SHALL enforce tight tolerances, avoid relaxing constraints.”
    - Tolerances are fixed (1e-15), not adaptive.
    - Verdict: OK in spirit; could be tighter as an explicit rule: “TOLERANCE SHALL NOT be increased to accept otherwise invalid packings.”

- “WHEN comparing to known results (Friedman) THEN comparisons SHALL use metrics explicitly aligned.”
    - compare_results.py and verify_solution.py do compare; they rely on final_metric which we know is misaligned for some families.
    - Verdict: Requirement is correct but not fully enforced in code.
    - Suggested change: add “WHEN a metric is derived via sin-scaling, it SHALL NOT be compared directly to Friedman unless proven equivalent for that family.”

- “IF a family uses incompatible metrics (e.g., circles) THEN treat as incomparable until conversion is implemented and documented.”
    - Code currently does not fully enforce this (some circle families may still compare).
    - Verdict: Currently aspirational.
    - Suggested change: phrase as: “System SHALL treat them as incomparable; if code currently does not enforce this, this is an open defect.”

Issues/updates for 00-system-overview.md:

- Clarify:
    - “TOLERANCE SHALL NOT be increased to accept otherwise invalid packings.”
- Strengthen Friedman comparison:
    - “SHALL NOT use sin-scaled final_metric for Friedman comparison unless explicitly validated for that family.”
- Mark circle-incomparability as a known requirement, not just a policy note.

2) 10-solver-core.md

I’ll check each section.

- “WHEN a regular polygon is specified by its side count THEN geometry.py SHALL compute vertices using circumradius-based construction, compute outward edge normals.”
    - Confirmed: regular_polygon_vertices uses radius*cos/sin; regular_polygon_outward_normals matches.
    - Verdict: OK.

- “WHEN a special shape token (TAN, DOMINO, L) is specified THEN SHALL use an explicitly defined set of vertices and edge normals, SHALL NOT fall back to regular-polygon formulas.”
    - geometry.py:
    - TAN: explicit.
    - DOMINO: explicit.
    - L: not implemented.
    - Verdict: PARTIALLY MET.
    - Fix: change to “(TAN, DOMINO) and, when implemented, L-tromino” or mark L as a future requirement.

- “WHEN a shape’s geometry is used both in Python and Rust THEN both SHALL define the same vertices, normals, and apothem within 1e-12.”
    - packer_rs has its own get_shape_geometry; values appear aligned conceptually but:
    - No test enforcing 1e-12.
    - Verdict: Requirement is too strong as written.
    - Fix: change to: “SHOULD match within 1e-12 and MUST be validated by dedicated cross-language tests for TAN, DOMINO, and key regular polygons.”

- “WHEN computing the objective THEN solver SHALL include penalties for overlaps via SAT-style projections and poking penalty.”
    - Confirmed in geometry.py bh_objective.
    - Verdict: OK.

- “WHEN verifying packings for record consideration THEN tolerance ≤ 1e-15; overlapping beyond that is invalid.”
    - Confirmed in solution_tools.py verify_solution.
    - Verdict: OK.

- “WHEN a problem is being solved THEN solver MAY use gradient-based/global-search/multiple restarts; SHALL NOT alter geometry/tolerances.”
    - optimization.py: L-BFGS-B, basinhopping, many attempts.
    - Verdict: OK.

- “IF local minima trap the solver THEN system SHALL allow more attempts, perturbations, swarm.”
    - run_all_attempts: many attempts; run_parallel_loop.py: swarm mode for stuck.
    - Verdict: OK.

- “WHEN packer_rs is invoked THEN it SHALL implement the same geometric definitions and tolerances; produce solution.json with N, inner_token, container_token, S, final_metric, shape positions; record
metrics consistently.”
    - packer_rs/src/main.rs:
    - Has geometry and produces solution JSON with needed fields.
    - Consistency is assumed but not tested.
    - Verdict: Mostly OK, but:
    - Strengthen with: “Rust implementation MUST NOT silently change tolerances or unit sizes to fabricate better metrics.”

Summary for 10-solver-core.md:

- Soften L-tromino to “when implemented.”
- Soften Python/Rust 1e-12 to “SHOULD” + “verified by tests.”
- Explicitly forbid tolerance loosening for “better” metrics.

3) 20-autoresearch-loop.md

I’ll verify each section against agent_loop.py, run_autoresearch_loop.py, run_parallel_loop.py.

- “WHEN the autoresearch loop selects the next problem THEN it SHALL consult PACKING_REFERENCE/history; prefer best_known over trivial/proved_optimal.”
    - agent_loop.py:
    - load_priority_queue + choose_problem read a queue that encodes reference info.
    - is_reference_blocked uses status trivial/proved_optimal.
    - is_preferred_reference marks best_known/human-found.
    - Verdict: OK in spirit, but:
    - Current code no longer directly loads_packing_reference in choose_problem; it trusts the queue.
    - Fix: rephrase to “consult reference information (via priority_queue or PACKING_REFERENCE)” instead of implying direct read.

- “IF a problem has been attempted excessively THEN scheduler SHALL increase its penalty.”
    - choose_problem: problem_runs tracked; penalty increases; hard caps at 60/100.
    - Verdict: OK.

- “WHEN a problem family has consumed too many runs THEN scheduler SHALL penalize further selection.”
    - family_runs tracked; penalty at 400/800 caps.
    - Verdict: OK.

- “WHEN a problem has zero or very few attempts THEN it SHALL receive a bonus so it is tried at least once.”
    - penalty -= 3.0 when total_runs == 0.
    - Verdict: OK.

- “WHEN compact/shorthand names appear THEN they SHALL be normalized into canonical N_X_in_Y before evaluation.”
    - normalize_problem_name exists and is used in choose_problem.
    - Verdict: OK.

- “WHEN problems are scored THEN bonuses based on distance to best_value SHALL be bounded and not dominate selection.”
    - Code uses distance_to_best_value and gap_bonus, capped by caps (e.g., best_value_gap_cap).
    - Verdict: OK.

- “WHEN run_autoresearch_loop.py is running THEN it SHALL operate fully automatically (no LLM); log to results.tsv; update PACKING_REFERENCE if confirmed.”
    - run_autoresearch_loop.py:
    - Pure code loop.
    - Logs via CLI run (which calls log_result).
    - PACKING_REFERENCE updates are done by scripts/CLI.
    - Verdict: OK.

- “WHEN run_parallel_loop.py starts on a SLURM node THEN it SHALL discover CPUs_ON_NODE; launch that many workers.”
    - run_parallel_loop.py:
    - get_available_cores uses SLURM_CPUS_ON_NODE; ProcessPoolExecutor(max_workers=num_cores).
    - Verdict: OK.

- “WHEN workers are running THEN they SHALL NOT write directly to shared disk files; main thread handles writes, PACKING_REFERENCE updates, and git.”
    - run_parallel_loop.py:
    - worker_task uses --no-commit --json-out.
    - process_result in main thread calls log_result.
    - Verdict: OK.

- “WHEN SLURM sends SIGTERM THEN graceful shutdown: stop dispatching, let in-progress tasks finish, flush writes, exit cleanly.”
    - run_parallel_loop.py:
    - SIGTERM handler sets _SHUTDOWN = True.
    - run_loop stops dispatching and waits for executor (running futures).
    - Verdict: OK.

- “IF a problem is stuck THEN system MAY increase attempts, use swarm mode.”
    - analyze_difficulty:
    - status == "stuck" → attempts = 500k, swarm_count = 20.
    - Verdict: OK.

- “WHEN an experiment is completed THEN a row SHALL be recorded with problem, score/metric, commit, status (keep/discard/crash).”
    - agent_loop.py:
    - log_result appends to results.tsv with TSV_COLUMNS (commit, score, memory_gb, status, problem, description).
    - Verdict: OK.

Summary for 20-autoresearch-loop.md:

- Minor fixes:
    - Clarify “consult reference information via priority_queue or PACKING_REFERENCE.”
    - Everything else aligns well with current implementation.

4) 30-verification-and-comparison.md

Now I’ll check against solution_tools.py and compare_results.py.

- “WHEN a solution JSON is passed to verify_solution.py THEN reconstruct shapes, check:
    - all inside container
    - no overlaps (SAT, ≤ 1e-15)
    - metrics internally consistent.”
    - solution_tools.py verify_solution does:
    - metric scaling check vs final_metric.
    - container bounds check.
    - pairwise SAT overlaps.
    - Verdict: OK.

- “IF violation THEN mark invalid with clear reason.”
    - Errors appended: “out of bounds”, “overlap”, “Metric scaling is incorrect.”
    - Verdict: OK.

- “WHEN verifying circle containers THEN do not assume final_metric = r unless explicitly derived.”
    - Code currently:
    - For circles: calc_metric = S (assuming S ≈ r), then compare.
    - But historically, that mapping was wrong for some families.
    - Verdict: Requirement is correct but not fully enforced.
    - Fix: rephrase to: “For circle containers, final_metric SHALL be treated as suspect unless an explicit per-family conversion is implemented; compare_results MUST NOT accept NEW_BEST for circle
families without such mapping.”

- “WHEN a solution claims a metric THEN it SHALL match deterministic calculation from S, inner/container; no ad-hoc adjustments.”
    - verify_solution enforces this via calc_metric vs final_metric diff.
    - Verdict: OK.

- “WHEN comparing to Friedman THEN metric SHALL be aligned; avoid NEW_BEST when incomparable.”
    - compare_results.py:
    - normalize_final_metric handles circle vs polygon differently.
    - But still uses final_metric directly for non-circles.
    - Verdict: Requirement is right; code is only partially compliant.
    - Fix: add: “For special shapes (TAN, DOMINO, L, TTT), the system SHALL NOT compare final_metric directly to Friedman unless explicitly mapped; otherwise treat as incomparable.”

- “WHEN NEW_BEST THEN must be geometrically valid + correct, explicitly comparable metric.”
    - This is a policy requirement not strictly enforced.
    - Verdict: OK as a requirement; mark code as “partially compliant.”

Summary for 30-verification-and-comparison.md:

- Strengthen:
    - Circle and special-shape incomparability.
- Add:
    - “WHEN a NEW_BEST is claimed for a family with uncertain metric alignment THEN it SHALL be reviewed and NOT automatically committed as authoritative.”

5) 40-cli-and-scripts.md

Check against cli.py and scripts.

- “WHEN CLI invoked with solve/run THEN parse N_X_in_Y, validate tokens, pass to solver without silently altering geometry.”
    - cli.py:
    - run command builds PackingProblem from problem.
    - Geometry via shape_token_to_sides + get_shape_geometry.
    - Verdict: OK.

- “WHEN CLI outputs results THEN include problem, N, S, final_metric, status, no fabricated metrics.”
    - cli.py:
    - Outputs JSON with those fields.
    - final_metric is computed consistently.
    - Verdict: OK.

- “IF mode flags (--no-commit, --json-out) THEN behavior SHALL be deterministic and match documented mode.”
    - cli.py:
    - --no-commit: disables commit.
    - --json-out: prints JSON instead of interactive output.
    - Verdict: OK.

- “verify_solution.py SHALL use same geometry and tolerance (≤1e-15); report valid, overlaps, out-of-bounds, NEW_BEST status.”
    - verify_solution.py:
    - Thin wrapper around solution_tools.verify_solution.
    - Verdict: OK.

- “compare_results.py SHALL load PACKING_REFERENCE; ensure metric alignment; avoid NEW_BEST when incomparable.”
    - compare_results.py:
    - Loads reference and compares.
    - Has circle-specific handling but still trusting final_metric.
    - Verdict: Requirement correct; code partially compliant (see 30).

- “analyze_mill_log.py SHALL extract stats without altering logs or solution files.”
    - analyze_mill_log.py:
    - Reads logs; prints tables/analysis.
    - Verdict: OK.

- “render_solution.py SHALL use same geometry and be consistent.”
    - render_solution.py:
    - Uses solution_tools to_plot_data.
    - Verdict: OK.

Summary for 40-cli-and-scripts.md:

- Mostly accurate.
- Minor update:
    - Add: “WHEN compare_results.py detects a potential NEW_BEST for a special shape or circle family, it SHALL flag it as ‘NEEDS_REVIEW’ unless metric alignment is explicitly implemented.”

6) 50-test-coverage.md

Check against our coverage policy and existing tests.

- “The system SHALL have an automated test suite runnable via pytest.”
    - pyproject.toml + tests/ directory confirm this.
    - Verdict: OK.

- “Meaningful correctness checks prioritized over forcing 100%.”
    - Matches coverage-policy.md and our explicit decision.
    - Verdict: OK.

- “WHEN geometry.py is changed THEN tests SHALL confirm regular polygons, special shapes, overlap checks.”
    - We have test_geometry*.py covering these.
    - Verdict: OK.

- “WHEN solution_tools.py / verify_solution.py is changed THEN tests for valid/overlap/out-of-bounds/metric-mismatch.”
    - We have test_solution_tools.py with these scenarios.
    - Verdict: OK.

- “WHEN agent_loop.py or ranker.py is changed THEN tests for selection, fairness, normalization.”
    - test_agent_loop, test_ranker cover many of these.
    - Verdict: OK.

- “WHEN optimization.py is changed THEN tests for initialization, objective consistency, safe wrapping of external solvers.”
    - We have lightweight tests and mocks.
    - Verdict: OK as a requirement; could be strengthened.

- “WHEN a new problem family is added THEN at least one test for geometry and validity.”
    - This is a good forward-looking requirement and not fully automated.
    - Verdict: OK as a policy; should be enforced in contribution rules.

Summary for 50-test-coverage.md:

- Accurate and aligned.
- Optional: add:
    - “No test SHALL silently ignore failures (e.g., via broad try/except) unless explicitly documenting why.”

If you’d like, next I’ll:
- Apply these fixes as patches to the non-shape-family requirements files so they’re fully consistent with the actual codebase.









I’ll verify every family doc systematically and report real discrepancies.

I’ll do this in batches but list each family clearly.

Batch 1: L families (LinL, Lindom, Linhex, Linoct, Linpen, Lintan, Lintri)

Check: L-tromino is not fully implemented.

- Code: geometry.py has no "L" token. packer_rs also lacks L-tromino.
- Docs claim:
    - "canonical L-tromino definition"
    - "both shall use canonical definitions"
    - "scaling from S via documented rule"
- Verdict (all 7):
    - Currently ASPIRATIONAL, not implemented.
    - Fix: change each doc’s Geometry section to:
    - “L-tromino support is planned. When implemented, it SHALL use a canonical L-tromino definition; until then, L-family problems SHALL be excluded or handled via explicit TODO logic.”

Batch 2: cirin* families (cirinel, cirinhex, cirinoct, cirinl, cirinpen, cirinsqu, cirintan, cirintri, cirinttt)

These are “circles in [container]” families.

- Code:
    - Geometry: circles modeled via high-sided polygons (usually 32) in get_shape_geometry; special token handling in compare_results and solution_tools.
    - Tolerance/validity: same SAT + bounds checks as other polygons.
    - Friedman metric: compare_results.py treats circles specially but still uses final_metric or S-based conversion; metric alignment is uncertain.
- Docs claim:
    - “circles SHALL be represented consistently”
    - “scaling derived from S via documented rule”
    - “NEW_BEST only if geometry and metric alignment are confirmed”
- Verdict:
    - Mostly accurate in intent.
    - Issue: none of these docs currently enforce “metric alignment confirmed” in code.
    - Fix (all 9):
    - Add: “Until explicit per-family conversion is implemented, circle-in-container problems SHALL be marked as needing review when NEW_BEST is detected.”

Batch 3: dom* families (dominL, domincir, domindom, dominhex, dominoct, dominpen, domintan, domintri)

Domino is implemented (geometry.py and packer_rs have explicit domino definitions).

- Geometry:
    - Python: explicit vertices/normal in get_shape_geometry.
    - Rust: explicit domino geometry.
    - Matches “canonical domino.”
- Validity:
    - Standard SAT checks; same tolerance.
- Friedman:
    - Docs: “explicit, documented conversion from S; NEW_BEST only if alignment confirmed.”
    - Code: compare_results uses final_metric directly for many non-circle families, including domino.
- Verdict:
    - Geometry/validity: OK.
    - Metric rule: ASPIRATIONAL.
    - Fix (all 8):
    - Add: “For domino families, final_metric SHALL NOT be assumed equivalent to Friedman’s metric unless explicitly validated.”

Batch 4: hexin* families (hexinL, hexincir, hexindom, hexinhex, hexinoct, hexinpen, hexintan, hexintri)

- Geometry:
    - Hexagon is regular polygon with 6 sides; implemented consistently.
    - hexinL: L not implemented (same as Batch 1).
- Validity:
    - SAT checks OK.
- Friedman:
    - Same issue: docs require explicit conversion; code uses final_metric.
- Verdict:
    - hexinL: geometry for L is missing → ASPIRATIONAL.
    - Others: geometry OK; metric rule ASPIRATIONAL.
    - Fix:
    - hexinL: same note as L families.
    - Others: add “final_metric SHALL NOT be treated as Friedman-equivalent without explicit validation.”

Batch 5: lincir, linsqu

- Geometry:
    - L-tromino not implemented.
    - Container shapes (circle/square) are implemented.
- Verdict:
    - Both: ASPIRATIONAL for L-tromino; otherwise OK for container/validity.
    - Fix: same “planned L-tromino” note.

Batch 6: minrect

- Code:
    - No specific “minrect” family handling in geometry.py/optimization.py.
    - No rectangle-only container mode documented in current solver.
- Verdict:
    - Mostly ASPIRATIONAL.
    - Fix:
    - Mark “minrect is a conceptual family; when supported, container SHALL be a rectangle with adjustable dimensions and documented metric alignment.”

Batch 7: octin* families (octinL, octincir, octindom, octinhex, octinoct, octinpen, octinsqu, octintan, octintri)

- Geometry:
    - Octagon = regular polygon with 8 sides; implemented.
    - octinL uses L → not implemented.
- Validity:
    - SAT checks consistent.
- Friedman:
    - Same final_metric issue.
- Verdict:
    - octinL: ASPIRATIONAL (L missing).
    - Others: geometry OK; metric rule ASPIRATIONAL.
    - Fix: same pattern.

Batch 8: penin* families (peninL, penincir, penindom, peninhex, peninoct, peninpen, peninsqu, penintan, penintri)

- Geometry:
    - Pentagon = 5-sided regular polygon; implemented.
    - peninL: L missing.
- Validity:
    - OK.
- Friedman:
    - Same issue.
- Verdict:
    - peninL: ASPIRATIONAL for L.
    - Others: geometry OK; metric rule ASPIRATIONAL.

Batch 9: rigid, squRcir, squcosqu, tricosqu

These are more specialized/niche.

- rigid:
    - No special “rigid” mode in current code; all shapes are inherently rigid.
    - Verdict: ASPIRATIONAL but harmless.
    - Fix: clarify: “Rigid is default: all shapes are rigid; no deformation allowed.”

- squRcir, squcosqu, tricosqu:
    - Not explicitly handled in geometry/optimization as separate modes.
    - Verdict: ASPIRATIONAL / conceptual.
    - Fix: mark them as: “If implemented, these SHALL follow the same SAT-based validity and explicit Friedman mapping rules; currently they are conceptual families to be defined in code if used.”

Batch 10: squin* families (squincir, squindom, squinhex, squinl, squinoct, squinpen, squintan, squintri)

- Geometry:
    - Square (4-gon) is implemented.
    - squinl: uses L → missing.
- Validity:
    - OK.
- Friedman:
    - Same final_metric issue.
- Verdict:
    - squinl: ASPIRATIONAL for L.
    - Others: geometry OK; metric rule ASPIRATIONAL.

Batch 11: tanin* families (taninL, tanincir, tanindom, taninhex, taninoct, taninpen, taninsqu, tanintan, tanintri)

- Geometry:
    - TAN implemented in Python and Rust with explicit vertices.
    - taninL uses L → missing.
- Validity:
    - OK.
- Friedman:
    - Critical family (we know the metric mismatch issue).
    - Docs: “explicit, documented conversion from S; NEW_BEST only if geometry and metric alignment are confirmed.”
    - Code: compare_results.py currently uses final_metric; incorrect for TAN-in-SQUARE.
- Verdict:
    - taninL: ASPIRATIONAL for L.
    - Others: geometry OK; metric requirement is CORRECT but NOT enforced.
    - Fix:
    - For taninsqu specifically, explicitly state: “For TAN-in-SQUARE, Friedman metric SHALL be s = S * sqrt(2); final_metric SHALL NOT be used for comparison.”

Batch 12: triin* families (triinL, triincir, triindom, triinhex, triinoct, triintan, triintri)

(Exclude triinpen, triinsqu which were already done earlier.)

- Geometry:
    - Triangles are 3-sided regular polygons; implemented.
    - triinL: L missing.
- Validity:
    - OK.
- Friedman:
    - Same final_metric issue.
- Verdict:
    - triinL: ASPIRATIONAL.
    - Others: geometry OK; metric rule ASPIRATIONAL.

Now, concrete fixes I’ll apply (concise):

I’ll:
- Update all L-family docs to mark L-tromino as not yet implemented.
- Add a uniform note to all families about metric alignment: “final_metric SHALL NOT be assumed equivalent to Friedman unless explicitly validated; potential NEW_BEST for such families SHALL be flagged as
NEEDS_REVIEW.”
- For TAN-in-SQUARE, explicitly codify the correct metric rule we discovered.
- Clarify minrect, rigid, squRcir, squcosqu, tricosqu as conceptual/currently unimplemented.

If that’s OK, I’ll proceed with patches now.