import os
import re

for file_name in ["test_geometry.py", "test_geometry_coverage.py", "test_geometry_extra.py"]:
    path = os.path.join("tests", file_name)
    with open(path, "r") as f:
        content = f.read()
    
    # 1. get_shape_geometry
    content = content.replace("sides, vertices, vectors, apothem = get_shape_geometry", "sides, vertices, vectors, edge_radii = get_shape_geometry")
    
    # test_domino_shape
    content = content.replace("assert abs(apothem - 0.5) < 1e-9", "assert abs(edge_radii[0] - 0.5) < 1e-9\n        assert abs(edge_radii[1] - 1.0) < 1e-9")
    
    # test_tan_shape
    content = content.replace("assert apothem > 0.0", "assert edge_radii[0] > 0.0")
    
    # GeoConfig
    content = content.replace("unit_container_apothem", "unit_container_radii")
    if "np.all(g.unit_container_radii == 1.0)" not in content:
        content = content.replace("g.unit_container_radii == 1.0", "np.all(g.unit_container_radii == 1.0)")
    
    # Fix apothem = 1.0 -> edge_radii = np.ones(...)
    # In tests, container vectors is usually length 4
    content = content.replace("apothem = 1.0", "edge_radii = np.ones(4)")
    content = content.replace("apothem = 0.5", "edge_radii = np.full(4, 0.5)")
    if "unit_container_radii = np.ones(4)" not in content:
        content = content.replace("unit_container_radii = 1.0", "unit_container_radii = np.ones(4)")
    
    # Fix argument passing
    content = content.replace("unit_container_vectors, apothem", "unit_container_vectors, edge_radii")
    content = content.replace("cv, apothem", "cv, edge_radii")
    content = content.replace("unit_container_vectors, unit_container_apothem", "unit_container_vectors, edge_radii")
    content = content.replace("container_vectors, apothem", "container_vectors, edge_radii")

    with open(path, "w") as f:
        f.write(content)

print("Tests patched.")
