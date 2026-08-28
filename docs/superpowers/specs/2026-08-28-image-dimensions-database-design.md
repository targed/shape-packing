# Exact Image Dimensions Database Design

## Goal
Generate and integrate an exhaustive, per-image pixel dimension database into `src/shape_packing/family_properties.json` from the 2,040+ local images in `docs/erich-friedman.github.io/packing-with-images/`, eliminating hardcoded family-wide dimensions and supporting exact per-$N$ rendering across all benchmark families.

## Architecture

### 1. Data Schema (`src/shape_packing/family_properties.json`)
Each shape family entry contains both family-level defaults and an `images` dictionary mapping each $N$ count and image filename to its exact width and height:

```json
{
  "cirinhex": {
    "inner": "#b5b5b5",
    "container": "#ffffff",
    "width": 181,
    "height": 156,
    "file_format": "gif",
    "filename_template": "hc{n}.gif",
    "variable_dimensions": true,
    "manual_check_required": false,
    "images": {
      "1": { "width": 180, "height": 156, "filename": "hc1.gif" },
      "2": { "width": 181, "height": 159, "filename": "hc2.gif" },
      "21": { "width": 183, "height": 160, "filename": "hc21.gif" }
    }
  }
}
```

### 2. Generator Script (`scripts/generate_image_properties.py`)
- Traverses `docs/erich-friedman.github.io/packing-with-images/`.
- Resolves case-insensitive directory names (`Linhex`, `dominpen`, `dominL`, etc.).
- Uses regex pattern matching against `filename_template` to extract shape count $N$ from filenames (`hc21.gif` $\rightarrow N=21$, `pent.5.png` $\rightarrow N=5$, `12.png` $\rightarrow N=12$).
- Reads image binary headers via PIL to extract exact pixel `(width, height)`.
- Calculates median dimensions for family-level fallback values.
- Writes back clean, sorted JSON to `src/shape_packing/family_properties.json`.

### 3. API Updates in `src/shape_packing/packing_config.py`
- Updated `get_family_properties(inner_or_family, container=None, N=None)`:
  - When `N` is passed, retrieves `{width, height}` directly from `images[str(N)]`.
  - When `N` is omitted or uncataloged, falls back to the family's median dimensions.
- Added `get_problem_image_dimensions(problem: str) -> Tuple[int, int]`:
  - Direct helper for problem strings (e.g. `"21_DOMINO_in_5"` $\rightarrow `(240, 240)`).

### 4. Verification Plan
- Automated unit tests in `tests/test_family_colors.py` asserting exact dimensions for variable families (`cirinhex`, `cirinel`, `dominpen`, `cirincir`).
- Cross-validation script comparing extracted dimensions in JSON against direct PIL reads of disk images.
- Full pytest suite execution (318+ tests passing).
