"""
generate_image_properties.py

Extracts exact pixel dimensions from all local Friedman packing images in
docs/erich-friedman.github.io/packing-with-images/ and builds an exhaustive
per-image and per-family image properties database into src/shape_packing/family_properties.json.
"""

from __future__ import annotations

import os
import re
import json
import statistics
from typing import Dict, Any, Tuple, Optional, Set, List
from PIL import Image


def extract_n_from_filename(filename: str, template: str) -> Optional[int]:
    """Extract integer N from filename based on template pattern or digits."""
    base, _ = os.path.splitext(filename)
    
    # Check for known template prefixes
    # e.g. "hc21" -> 21, "pent.21" -> 21, "ccc5" -> 5, "t4" -> 4, "ts6" -> 6
    # If the file is just a number like "21.png" -> 21
    if base.isdigit():
        return int(base)
        
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
        
    if not os.path.exists(images_root):
        raise FileNotFoundError(f"Image directory not found at '{images_root}'")

    subdirs = {
        d.lower(): d
        for d in os.listdir(images_root)
        if os.path.isdir(os.path.join(images_root, d))
    }
    
    total_images_scanned = 0
    updated_catalog = {}
    
    for fam_key, fam_cfg in family_props.items():
        f_lower = fam_key.lower()
        if f_lower not in subdirs:
            print(f"[WARN] No image folder found for family '{fam_key}'. Preserving existing config.")
            updated_catalog[fam_key] = fam_cfg
            continue
            
        folder_name = subdirs[f_lower]
        full_dir = os.path.join(images_root, folder_name)
        
        files = sorted([
            f for f in os.listdir(full_dir)
            if f.lower().endswith(('.png', '.gif', '.jpg', '.jpeg')) and not f.startswith('.')
        ])
        
        images_dict: Dict[str, Dict[str, Any]] = {}
        widths: List[int] = []
        heights: List[int] = []
        
        template = fam_cfg.get("filename_template", "{n}.png")
        
        for f in files:
            file_path = os.path.join(full_dir, f)
            try:
                with Image.open(file_path) as img:
                    w, h = img.size
                    fmt = (img.format or "PNG").lower()
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
            
            # Store by exact filename (e.g. "hc21.gif")
            images_dict[f] = img_entry
            
            # Store by string N (e.g. "21")
            if n_val is not None:
                images_dict[str(n_val)] = img_entry
                widths.append(w)
                heights.append(h)
                
            total_images_scanned += 1
            
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
        
    print(f"[SUCCESS] Scanned {total_images_scanned} images across {len(updated_catalog)} families -> saved to {output_json_path}")
    return updated_catalog


if __name__ == "__main__":
    generate_database()
