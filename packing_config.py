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

CIRCLE_SIDES = 128

SHAPE_TO_SIDES = {
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "8": 8,
    "CIRCLE": CIRCLE_SIDES,
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
    + L_FAMILIES
)

# ---------------------------------------------------------------------------
# Default experiment knobs (used as starting point; agent can override)
# ---------------------------------------------------------------------------

DEFAULT_EXPERIMENT_KWARGS = {
    "attempts": 1000,
    "tolerance": 1e-8,
    "finalstep": 0.0001,
}