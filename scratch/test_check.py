import json
from pathlib import Path

ROOT = Path("packingVerification")
entries = []
for f in sorted(ROOT.glob("*.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    for e in data:
        entries.append(e)

prob_3in3 = [e for e in entries if e.get("problem_family") in ("3_in_3", "triintri")]
for e in prob_3in3[:15]:
    print(f"N={e['N']}: best_value={e['best_value']} ({type(e['best_value']).__name__}), status={e['status']}")
