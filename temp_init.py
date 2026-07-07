import sys, json, math
out = sys.argv[1]
n = 8
positions = []
for i in range(n):
    theta = 2 * math.pi * i / n
    positions += [2.5 + 2.5 * math.cos(theta), 2.5 + 2.5 * math.sin(theta)]
with open(out, 'w') as f:
    json.dump(positions, f)