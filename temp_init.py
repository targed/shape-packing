import sys, json, math
out_path = sys.argv[1]
N = 11
L = 6.0
spacing = 1.0
points = []
row = 0
while len(points) < N:
    col = 0
    while len(points) < N:
        x = col * spacing * 1.5 + (L/2 - 3)
        y = row * spacing * math.sqrt(3)/2 + (L/2 - 3)
        if 0.5 <= x <= L-0.5 and 0.5 <= y <= L-0.5:
            points.append((x, y))
        col += 1
    row += 1
flat = []
for p in points[:N]:
    flat.extend(p)
with open(out_path, 'w') as f:
    json.dump(flat, f)