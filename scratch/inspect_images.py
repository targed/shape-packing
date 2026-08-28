import os
import json
from PIL import Image

def main():
    fp_path = "src/shape_packing/family_properties.json"
    with open(fp_path, "r") as f:
        family_properties = json.load(f)
    
    img_dir = "docs/erich-friedman.github.io/packing-with-images"
    subdirs = {d.lower(): d for d in os.listdir(img_dir) if os.path.isdir(os.path.join(img_dir, d))}
    
    total_images = 0
    variable_dim_families = []
    uniform_dim_families = []
    
    image_catalog = {}
    
    for fam_key, fam_cfg in family_properties.items():
        f_lower = fam_key.lower()
        if f_lower not in subdirs:
            print(f"Family {fam_key} NOT FOUND in image directory")
            continue
        
        folder_name = subdirs[f_lower]
        full_folder_path = os.path.join(img_dir, folder_name)
        
        files = [
            f for f in os.listdir(full_folder_path)
            if f.lower().endswith(('.png', '.gif', '.jpg', '.jpeg')) and not f.startswith('.')
        ]
        
        dims_seen = set()
        fam_images = {}
        
        for f in files:
            file_path = os.path.join(full_folder_path, f)
            try:
                with Image.open(file_path) as img:
                    w, h = img.size
                    fmt = img.format
                    dims_seen.add((w, h))
                    fam_images[f] = {
                        "width": w,
                        "height": h,
                        "format": fmt.lower() if fmt else "unknown",
                        "size_bytes": os.path.getsize(file_path),
                    }
            except Exception as e:
                print(f"Error opening {file_path}: {e}")
        
        total_images += len(fam_images)
        image_catalog[fam_key] = {
            "folder": folder_name,
            "count": len(fam_images),
            "unique_dimensions": list(dims_seen),
            "is_variable": len(dims_seen) > 1,
            "images": fam_images,
        }
        
        if len(dims_seen) > 1:
            variable_dim_families.append((fam_key, folder_name, len(fam_images), dims_seen))
        else:
            uniform_dim_families.append((fam_key, folder_name, len(fam_images), dims_seen))

    print("=" * 60)
    print(f"Total matched families: {len(image_catalog)}")
    print(f"Total images scanned: {total_images}")
    print(f"Uniform dimension families: {len(uniform_dim_families)}")
    print(f"Variable dimension families: {len(variable_dim_families)}")
    print("=" * 60)
    
    print("\nVariable Dimension Families Sample:")
    for fam, folder, count, dims in variable_dim_families[:10]:
        print(f"  - {fam} ({folder}): {count} images, unique dimensions: {dims}")

if __name__ == "__main__":
    main()
