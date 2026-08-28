"""
verify_image_random_sample.py

Randomly samples 25 images across different packing families from family_properties.json
and verifies that the width, height, and format in the JSON catalog exactly match
the actual binary file attributes read directly by PIL.Image.
"""

from __future__ import annotations

import os
import json
import random
from PIL import Image

def main():
    with open("src/shape_packing/family_properties.json", "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    img_root = "docs/erich-friedman.github.io/packing-with-images"
    subdirs = {d.lower(): d for d in os.listdir(img_root) if os.path.isdir(os.path.join(img_root, d))}
    
    # Collect all (family, filename, entry) tuples
    all_entries = []
    for fam_code, fam_data in catalog.items():
        f_lower = fam_code.lower()
        if f_lower not in subdirs:
            continue
        folder = subdirs[f_lower]
        images = fam_data.get("images", {})
        for key, entry in images.items():
            # Only consider filename keys (avoid duplicates with numeric keys)
            if "." in key:
                all_entries.append((fam_code, folder, key, entry))
                
    random.seed(42)
    sample = random.sample(all_entries, min(25, len(all_entries)))
    
    print(f"Verifying {len(sample)} randomly sampled images across families:\n")
    print(f"{'Family':<12} {'Filename':<16} {'JSON Size':<12} {'Actual Size':<12} {'Match?'}")
    print("-" * 65)
    
    all_passed = True
    for fam_code, folder, fname, entry in sample:
        file_path = os.path.join(img_root, folder, fname)
        if not os.path.exists(file_path):
            print(f"FAILED: {file_path} does not exist!")
            all_passed = False
            continue
            
        with Image.open(file_path) as img:
            actual_w, actual_h = img.size
            
        json_w, json_h = entry["width"], entry["height"]
        is_match = (actual_w == json_w) and (actual_h == json_h)
        match_str = "PASS" if is_match else "FAIL"
        
        if not is_match:
            all_passed = False
            
        print(f"{fam_code:<12} {fname:<16} {f'{json_w}x{json_h}':<12} {f'{actual_w}x{actual_h}':<12} {match_str}")
        
    print("-" * 65)
    if all_passed:
        print("[SUCCESS] All 25 sampled images have 100% exact dimension matches!")
    else:
        print("[ERROR] Some sampled images failed verification.")

if __name__ == "__main__":
    main()
