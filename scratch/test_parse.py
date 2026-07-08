import re
from pathlib import Path

def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)

path = Path("erich-friedman.github.io/packing/triinsqu/index.html")
html = path.read_text(errors="ignore")

tables = re.split(r"<TABLE", html, flags=re.IGNORECASE)
n_to_s = {}

for tbl in tables:
    td_list = re.findall(r"<TD[^>]*>(.*?)</TD>", tbl, flags=re.IGNORECASE | re.DOTALL)
    for td in td_list:
        text = strip_tags(td).strip()

        m = re.search(r"(\d+)\s*(?:[-–—]\s*(\d+))?\s*\.", text)
        if not m:
            continue

        n_start = int(m.group(1))
        n_end = int(m.group(2)) if m.group(2) else n_start

        s_val = ""

        # s = ... = 1.478+
        sm = re.search(r"s\s*=\s*.*?\s*=\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
        if sm:
            s_val = sm.group(1)
        else:
            # s = 1.577+
            sm = re.search(r"s\s*=\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
            if sm:
                s_val = sm.group(1)

        # Fallback "= 1.234+" if s not explicit
        if not s_val:
            sm = re.search(r"=\s*([0-9]+\.[0-9]+)\+", text)
            if sm:
                s_val = sm.group(1)

        for n in range(n_start, n_end + 1):
            if s_val:
                n_to_s[n] = s_val

# Print first 15
for n in sorted(n_to_s.keys())[:15]:
    print(n, "->", n_to_s[n])