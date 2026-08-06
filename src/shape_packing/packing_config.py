"""
packing_config.py

Helper configuration for the packing autoresearch loop.
The agent (you / Cline) uses this to:
- map problem tokens to polygon sides
- choose problems from the catalog
- understand conventions

You can edit this file to add new shape families or tune defaults.
"""

# ---------------------------------------------------------------------------
# Shape token -> side count (for regular polygons).
# CIRCLE is approximated as a high-sided polygon.
# ---------------------------------------------------------------------------

CIRCLE_SIDES = 32

SHAPE_TO_SIDES = {
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "8": 8,
    "CIRCLE": CIRCLE_SIDES,
    "SQUARE": 4,
    "TRIANGLE": 3,
    "PENTAGON": 5,
    "HEXAGON": 6,
    "OCTAGON": 8,
}

# Non-regular or composite shapes that require custom logic in polygon_packer.py.
# The agent must extend polygon_packer.py to support these.
SPECIAL_SHAPES = {
    "TAN",      # classic tangram parallelogram/trapezoid set
    "DOMINO",   # 1x2 rectangle
    "L",        # L-tromino / L-shape
}

# ---------------------------------------------------------------------------
# Problem naming convention
# ---------------------------------------------------------------------------
#
# Format: {N}_{inner}_in_{container}
#
# Examples:
#   20_3_in_CIRCLE      -> 20 triangles in circle
#   30_4_in_6           -> 30 squares in hexagon
#   15_8_in_8           -> 15 octagons in octagon
#   10_TAN_in_CIRCLE
#   12_DOMINO_in_4
#   10_L_in_6

# ---------------------------------------------------------------------------
# Sample problem catalog (for agent guidance)
# ---------------------------------------------------------------------------
#
# The agent should:
# - Pick a family.
# - Choose N.
# - Set CURRENT_PROBLEM in train.py accordingly.
#
# Catalog families:

CIRCLE_FAMILIES = [
    "Circles in Circles",
    "Triangles in Circles",
    "Squares in Circles",
    "Pentagons in Circles",
    "Hexagons in Circles",
    "Octagons in Circles",
    "Tans in Circles",
    "Dominoes in Circles",
    "L's in Circles",
]

TRIANGLE_FAMILIES = [
    "Circles in Triangles",
    "Triangles in Triangles",
    "Squares in Triangles",
    "Pentagons in Triangles",
    "Hexagons in Triangles",
    "Octagons in Triangles",
    "Tans in Triangles",
    "Dominoes in Triangles",
    "L's in Triangles",
]

SQUARE_FAMILIES = [
    "Circles in Squares",
    "Triangles in Squares",
    "Squares in Squares",
    "Pentagons in Squares",
    "Hexagons in Squares",
    "Octagons in Squares",
    "Tans in Squares",
    "Dominoes in Squares",
    "L's in Squares",
]

PENTAGON_FAMILIES = [
    "Circles in Pentagons",
    "Triangles in Pentagons",
    "Squares in Pentagons",
    "Pentagons in Pentagons",
    "Hexagons in Pentagons",
    "Octagons in Pentagons",
    "Tans in Pentagons",
    "Dominoes in Pentagons",
    "L's in Pentagons",
]

HEXAGON_FAMILIES = [
    "Circles in Hexagons",
    "Triangles in Hexagons",
    "Squares in Hexagons",
    "Pentagons in Hexagons",
    "Hexagons in Hexagons",
    "Octagons in Hexagons",
    "Tans in Hexagons",
    "Dominoes in Hexagons",
    "L's in Hexagons",
]

OCTAGON_FAMILIES = [
    "Circles in Octagons",
    "Triangles in Octagons",
    "Squares in Octagons",
    "Pentagons in Octagons",
    "Hexagons in Octagons",
    "Octagons in Octagons",
    "Tans in Octagons",
    "Dominoes in Octagons",
    "L's in Octagons",
]

TAN_FAMILIES = [
    "Circles in Tans",
    "Triangles in Tans",
    "Squares in Tans",
    "Pentagons in Tans",
    "Hexagons in Tans",
    "Octagons in Tans",
    "Tans in Tans",
    "Dominoes in Tans",
    "L's in Tans",
]

DOMINO_FAMILIES = [
    "Circles in Dominoes",
    "Triangles in Dominoes",
    "Squares in Dominoes",
    "Pentagons in Dominoes",
    "Hexagons in Dominoes",
    "Octagons in Dominoes",
    "Tans in Dominoes",
    "Dominoes in Dominoes",
    "L's in Dominoes",
]

L_FAMILIES = [
    "Circles in L's",
    "Triangles in L's",
    "Squares in L's",
    "Pentagons in L's",
    "Hexagons in L's",
    "Octagons in L's",
    "Tans in L's",
    "Dominoes in L's",
    "L's in L's",
]

ALL_FAMILIES = (
    CIRCLE_FAMILIES
    + TRIANGLE_FAMILIES
    + SQUARE_FAMILIES
    + PENTAGON_FAMILIES
    + HEXAGON_FAMILIES
    + OCTAGON_FAMILIES
    + TAN_FAMILIES
    + DOMINO_FAMILIES
)

# ---------------------------------------------------------------------------
# Default experiment knobs (used as starting point; agent can override)
# ---------------------------------------------------------------------------

DEFAULT_EXPERIMENT_KWARGS = {
    "attempts": 1000,
    "tolerance": 1e-8,
    "finalstep": 0.0001,
}

# ===========================================================================
# SECTION 2: Solver — Rust Backend (packer_rs)
# ===========================================================================

#: Path to compiled Rust solver binary.
RUST_BINARY: str = "packer_rs/target/release/packer_rs"

#: Convergence tolerance passed to Rust L-BFGS-B solver via --tolerance flag.
RUST_TOLERANCE: str = "1e-28"

#: Default number of solver restart attempts per run (overridden by loop scripts and CLI).
RUST_DEFAULT_ATTEMPTS: int = 1000

#: Default time limit in seconds for a single Rust solver run.
RUST_DEFAULT_TIME_LIMIT: int = 1000

# ===========================================================================
# SECTION 3: Solver — Python Backend (scipy/optimization.py)
# ===========================================================================

#: Default number of basinhopping attempts in the Python optimizer.
OPTIMIZER_ATTEMPTS: int = 1000

#: Convergence tolerance for scipy L-BFGS-B. Lower = more precise, slower.
OPTIMIZER_TOLERANCE: float = 1e-8

#: Final step size for the optimizer's local refinement stage.
OPTIMIZER_FINAL_STEP: float = 0.0001

#: Number of parallel jobs for joblib. -1 = all cores, 1 = serial.
OPTIMIZER_N_JOBS: int = -1

# ===========================================================================
# SECTION 4: Verification Tolerances
# ===========================================================================

#: Maximum allowed SAT penetration depth when verifying boundary containment
#: in solution_tools.verify_solution(). Small positive value to allow float rounding.
VERIFY_SAT_TOLERANCE: float = 1e-5

#: Tolerance when comparing computed Friedman metric against stored final_metric in JSON.
VERIFY_METRIC_TOLERANCE: float = 1e-6

#: Tolerance used inside geometry.sat_check_overlap() for separating axis projection.
#: Tighter than VERIFY_SAT_TOLERANCE since this is an internal math primitive.
GEOMETRY_SAT_TOLERANCE: float = 1e-12

#: Physical validity floor for circle problem scores. Scores below this value
#: are treated as corrupt legacy metrics (old broken formula) and ignored.
MIN_VALID_CIRCLE_SCORE: float = 0.1

# ===========================================================================
# SECTION 5: Loop & Scheduling (autoresearch and parallel loops)
# ===========================================================================

#: Seconds to sleep between successful solver runs in run_autoresearch_loop.py.
LOOP_SLEEP_BETWEEN_RUNS: int = 2

#: Maximum number of consecutive failures before applying exponential backoff.
LOOP_MAX_CONSECUTIVE_FAILURES: int = 5

#: Starting backoff duration in seconds after a failure.
LOOP_BASE_BACKOFF: int = 5

#: Maximum backoff duration cap in seconds.
LOOP_MAX_BACKOFF: int = 120

#: Default solver attempts for "normal" difficulty problems in the parallel loop.
LOOP_DEFAULT_ATTEMPTS: int = 5000

#: N threshold above which a problem is considered "hard" (more attempts allocated).
LOOP_HIGH_N_THRESHOLD: int = 8

#: Solver attempts for hard problems (N >= LOOP_HIGH_N_THRESHOLD).
LOOP_HIGH_N_ATTEMPTS: int = 50000

#: Solver attempts for "stuck" problems (status='stuck' returned by suggest).
LOOP_STUCK_ATTEMPTS: int = 500000

#: Number of parallel swarm workers dispatched for stuck problems.
LOOP_STUCK_SWARM_COUNT: int = 20

#: Number of parallel swarm workers dispatched for hard problems.
LOOP_HARD_SWARM_COUNT: int = 5

# ===========================================================================
# SECTION 6: Priority Queue & Problem Selection
# ===========================================================================

#: Fallback problem key used if priority_queue.json is missing or empty.
QUEUE_FALLBACK_PROBLEM: str = "8_3_in_5"

#: Window size for recent_problems() diversity check.
QUEUE_RECENT_WINDOW: int = 10

#: Soft run cap per problem — beyond this, mild score penalty applied.
QUEUE_PROBLEM_CAP1: int = 60

#: Hard run cap per problem — beyond this, strong score penalty applied.
QUEUE_PROBLEM_CAP2: int = 100

#: Soft run cap per problem family — beyond this, mild score penalty applied.
QUEUE_FAMILY_CAP1: int = 400

#: Hard run cap per problem family — beyond this, strong score penalty applied.
QUEUE_FAMILY_CAP2: int = 800

# ===========================================================================
# SECTION 7: File Paths (relative to project root)
# ===========================================================================

#: Path to the experiment history TSV file.
RESULTS_TSV_PATH: str = "results.tsv"

#: Directory where per-run result subdirectories are saved.
RESULTS_DIR: str = "results"

#: Path to the JSON priority queue file.
PRIORITY_QUEUE_PATH: str = "priority_queue.json"

#: Directory containing benchmark verification JSON files.
PACKING_VERIFICATION_DIR: str = "packingVerification"

#: Path to the optional runtime filter JSON file.
FILTER_JSON_PATH: str = "filter.json"

#: Path to the legacy PACKING_REFERENCE.tsv file.
PACKING_REFERENCE_TSV: str = "PACKING_REFERENCE.tsv"

# ===========================================================================
# SECTION 8: Rendering & Output
# ===========================================================================

#: DPI for solution.png renders (solution_tools.render_solution).
RENDER_DPI: int = 300

#: Matplotlib figure size in inches for solution renders.
RENDER_FIGURE_SIZE: tuple = (6, 6)

#: DPI for analysis charts produced by scripts/analyze_mill_log.py.
ANALYSIS_PLOT_DPI: int = 200
