# Exact Image Dimensions Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract exact pixel dimensions from all 2,040+ local Friedman packing images in `docs/erich-friedman.github.io/packing-with-images/` and generate an exhaustive `images` mapping inside `src/shape_packing/family_properties.json` with per-$N$ lookup support.

**Architecture:**
- Standalone generator script `scripts/generate_image_properties.py` using PIL to parse headers of all images across 74 packing families.
- Augmented `src/shape_packing/family_properties.json` containing per-image `{width, height, filename}` records alongside family median fallbacks.
- Enhanced `get_family_properties` and new `get_problem_image_dimensions` functions in `src/shape_packing/packing_config.py`.

**Tech Stack:** Python 3.10+, PIL/Pillow, JSON, pytest.

## Global Constraints

- Must parse all 74 matched folders in `docs/erich-friedman.github.io/packing-with-images/`.
- Must retain all existing family color codes (`inner`, `container`), format, and template fields.
- Must pass all 318+ tests in `pytest tests/` with zero regressions.

---

### Task 1: Create Image Properties Generator Script & Build Database

**Files:**
- Create: `scripts/generate_image_properties.py`
- Modify: `src/shape_packing/family_properties.json`

**Interfaces:**
- Produces: Updated `family_properties.json` containing `images: Dict[str, Dict[str, Any]]` under every family.

- [ ] **Step 1: Write `scripts/generate_image_properties.py`**

```python
from __future__ import annotations

import os
import re
import json
import statistics
from typing import Dict, Any, Tuple, Optional, Set
from PIL import Image

def extract_n_from_filename(filename: str, template: str) -> Optional[int]:
    """Extract integer N from filename based on template pattern."""
    base, _ = os.path.splitext(filename)
    
    # Try direct digits in filename
    digits = re.findall(r"\d+", base)
    if digits:
        return int(digits[-1])
    return None

def generate_database(
    family_json_path: str = "src/shape_packing/family_properties.json",
    images_root: str = "docs/erich-friedman.github.io/packing-with-images",
    output_json_path: Optional[str] = None,
) -> Dict[str, Any]:
    if output_json_path is None:
        output_json_path = family_json_path
        
    with open(family_json_path, "r", encoding="utf-8") as f:
        family_props = json.load(f)
        
    subdirs = {
        d.lower(): d
        for d in os.listdir(images_root)
        if os.path.isdir(os.path.join(images_root, d))
    }
    
    total_images = 0
    updated_catalog = {}
    
    for fam_key, fam_cfg in family_props.items():
        f_lower = fam_key.lower()
        if f_lower not in subdirs:
            print(f"[WARN] No image folder for family '{fam_key}'. Keeping existing config.")
            updated_catalog[fam_key] = fam_cfg
            continue
            
        folder_name = subdirs[f_lower]
        full_dir = os.path.join(images_root, folder_name)
        
        files = sorted([
            f for f in os.listdir(full_dir)
            if f.lower().endswith(('.png', '.gif', '.jpg', '.jpeg')) and not f.startswith('.')
        ])
        
        images_dict = {}
        widths = []
        heights = []
        
        template = fam_cfg.get("filename_template", "{n}.png")
        
        for f in files:
            file_path = os.path.join(full_dir, f)
            try:
                with Image.open(file_path) as img:
                    w, h = img.size
                    fmt = img.format.lower() if img.format else "png"
            except Exception as e:
                print(f"[ERROR] Failed to read {file_path}: {e}")
                continue
                
            n_val = extract_n_from_filename(f, template)
            img_entry = {
                "width": w,
                "height": h,
                "filename": f,
                "format": fmt,
            }
            
            # Store by filename
            images_dict[f] = img_entry
            
            # Store by N if extracted
            if n_val is not None:
                images_dict[str(n_val)] = img_entry
                widths.append(w)
                heights.append(h)
                
            total_images += 1
            
        median_w = int(statistics.median(widths)) if widths else (fam_cfg.get("width") or 240)
        median_h = int(statistics.median(heights)) if heights else (fam_cfg.get("height") or 240)
        unique_dims = set(zip(widths, heights))
        
        updated_entry = {
            "inner": fam_cfg.get("inner", "#b5b5b5"),
            "container": fam_cfg.get("container", "#ffffff"),
            "width": median_w,
            "height": median_h,
            "file_format": fam_cfg.get("file_format", "png"),
            "filename_template": template,
            "variable_dimensions": len(unique_dims) > 1,
            "manual_check_required": False,
            "images": images_dict,
        }
        updated_catalog[fam_key] = updated_entry
        
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(updated_catalog, f, indent=2)
        
    print(f"[SUCCESS] Scanned {total_images} images across {len(updated_catalog)} families -> saved to {output_json_path}")
    return updated_catalog

if __name__ == "__main__":
    generate_database()
```

- [ ] **Step 2: Run script to generate the comprehensive database**

Run: `python scripts/generate_image_properties.py`
Expected: Processes all 2,040+ images and writes `src/shape_packing/family_properties.json`.

- [ ] **Step 3: Commit generator script and updated database**

```bash
git add scripts/generate_image_properties.py src/shape_packing/family_properties.json
git commit -m "feat(config): generate per-image exact dimensions database across 2040+ images"
```

---

### Task 2: Update Accessor Functions in `src/shape_packing/packing_config.py`

**Files:**
- Modify: `src/shape_packing/packing_config.py:146-245`
- Test: `tests/test_family_colors.py`

**Interfaces:**
- Produces: `get_family_properties(inner_or_family, container=None, N=None, json_path=None)` and `get_problem_image_dimensions(problem: str) -> Tuple[int, int]`.

- [ ] **Step 1: Enhance `get_family_properties` to accept optional `N` and check `images` mapping**

```python
def get_family_properties(
    inner_or_family: str,
    container: Optional[str] = None,
    N: Optional[int] = None,
    json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get full properties for a given shape family (colors, dimensions, format, filename template).
    If N is provided, returns exact dimensions for that specific image if available.
    """
    props_map = load_family_properties(json_path)

    # Normalize family key ...
    if family_key in props_map:
        cfg = props_map[family_key]
        width = cfg.get("width")
        height = cfg.get("height")
        file_format = cfg.get("file_format", "png").lower()
        template = cfg.get("filename_template", "{n}.png")
        images = cfg.get("images", {})

        # If N is specified and available in image catalog, use exact dimensions
        if N is not None and str(N) in images:
            img_info = images[str(N)]
            width = img_info.get("width", width)
            height = img_info.get("height", height)
            file_format = img_info.get("format", file_format)
        elif N is not None and cfg.get("variable_dimensions", False):
            # Only warn if uncataloged variable dimension
            pass

        return {
            "family_code": family_key,
            "inner": cfg.get("inner", RENDER_INNER_FACE_COLOR),
            "container": cfg.get("container", RENDER_BG_COLOR or "#FFFFFF"),
            "width": width or 240,
            "height": height or 240,
            "file_format": file_format,
            "filename_template": template,
            "variable_dimensions": cfg.get("variable_dimensions", False),
            "manual_check_required": cfg.get("manual_check_required", False),
            "images": images,
        }
```

- [ ] **Step 2: Add `get_problem_image_dimensions` helper**

```python
def get_problem_image_dimensions(
    problem: str,
    json_path: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Get exact (width, height) in pixels for a problem (e.g. '21_DOMINO_in_5' -> (240, 240)).
    """
    raw = problem.strip()
    if "_in_" in raw:
        parts = raw.split("_in_")
        container = parts[1]
        n_part, inner = parts[0].split("_", 1)
        try:
            n_val = int(n_part)
        except ValueError:
            n_val = None
        props = get_family_properties(inner, container, N=n_val, json_path=json_path)
    else:
        props = get_family_properties(raw, json_path=json_path)
    return props["width"], props["height"]
```

---

### Task 3: Unit Tests & Verification

**Files:**
- Modify: `tests/test_family_colors.py`
- Test: `pytest tests/test_family_colors.py`

- [ ] **Step 1: Write unit tests verifying exact per-N dimensions across sample families**

```python
def test_exact_image_dimensions_per_n():
    from src.shape_packing.packing_config import get_family_properties, get_problem_image_dimensions
    
    # cirinhex: N=1 is 180x156, N=2 is 181x159, N=21 is 183x160
    p1 = get_family_properties("cirinhex", N=1)
    assert (p1["width"], p1["height"]) == (180, 156)
    
    p2 = get_family_properties("cirinhex", N=2)
    assert (p2["width"], p2["height"]) == (181, 159)
    
    p21 = get_family_properties("cirinhex", N=21)
    assert (p21["width"], p21["height"]) == (183, 160)
    
    # Problem string lookup
    w, h = get_problem_image_dimensions("21_CIRCLE_in_6")
    assert (w, h) == (183, 160)
```

- [ ] **Step 2: Run pytest to verify all tests pass**

Run: `python -m pytest tests/`
Expected: All 318+ tests pass.

- [ ] **Step 3: Commit unit tests and packing config updates**

```bash
git add src/shape_packing/packing_config.py tests/test_family_colors.py
git commit -m "feat(config): add exact per-N image dimension lookup APIs and unit tests"
```

---

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_family_colors.py`: Verifies exact dimension lookups.
- `python -m pytest tests/`: Full regression suite.

### Manual Verification
- Random sample cross-check script comparing JSON entries with `PIL.Image.open(...)` on disk.
