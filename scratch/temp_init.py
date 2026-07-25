import sys, random, json

random.seed(42)
N = 15
L = 8.0

positions = []
used = []

def is_ok(x, y):
    for (ux, uy) in used:
        dx, dy = x - ux, y - uy
        if dx*dx + dy*dy < 2.5:
            return False
    return True

attempts = 0
while len(positions) < N * 3 and attempts < 5000:
    x = random.uniform(0.5, L - 0.5)
    y = random.uniform(0.5, L - 0.5)
    if is_ok(x, y):
        used.append((x, y))
        theta = random.uniform(0, 6.28318530718)
        positions.extend([x, y, theta])
    attempts += 1

with open(sys.argv[1], 'w') as f:
    json.dump(positions, f)
