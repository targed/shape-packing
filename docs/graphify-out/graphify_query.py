#!/usr/bin/env python3
"""
graphify_query.py - Thin router for graphify operations in this repo.

Modes:
  init <path>                     Build/update graph (uses graphify CLI or internal scripts).
  query "<question>"               Answer from graph via BFS traversal.
  path "A" "B"                     Shortest path between two concepts.
  explain "Node"                   Explain a node and its connections.
"""

import argparse
import json
import os
import sys
import subprocess
import re
from pathlib import Path

GRAPHIFY_OUT = Path("graphify-out")
PYTHON_FILE = GRAPHIFY_OUT / ".graphify_python"
GRAPH_FILE = GRAPHIFY_OUT / "graph.json"


def ensure_python() -> str:
    """Ensure we have a graphify-capable Python and return its path."""
    if PYTHON_FILE.exists():
        py = PYTHON_FILE.read_text().strip()
        if py:
            return py
    # Fallback
    for candidate in ["python3", "python"]:
        try:
            r = subprocess.run(
                [candidate, "-c", "import graphify"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                return candidate
        except Exception:
            continue
    # If all else fails
    return "python3"


def run_py_script(py: str, code: str):
    """Run a Python snippet using the graphify Python."""
    r = subprocess.run(
        [py, "-c", code],
        capture_output=True,
        text=True,
    )
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        sys.exit(r.returncode)


def has_graphify_cli() -> bool:
    try:
        r = subprocess.run(["which", "graphify"], capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def cmd_init(args):
    target = args.path or "."
    # Fast path: try using the CLI
    if has_graphify_cli():
        subprocess.run(
            ["graphify", target],
            check=False,
        )
        return
    # Fallback: inline pipeline from SKILL.md (minimal, same-dir only).
    py = ensure_python()
    GRAPHIFY_OUT.mkdir(parents=True, exist_ok=True)

    # 1) detect
    detect_code = f'''
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path("{target}"))
Path("graphify-out/.graphify_detect.json").write_text(json.dumps(result, ensure_ascii=False))
print("Detect done.")
'''
    run_py_script(py, detect_code)

    detect = json.loads((GRAPHIFY_OUT / ".graphify_detect.json").read_text())
    total_files = detect.get("total_files", 0)
    if total_files == 0:
        print("No supported files found in", target)
        sys.exit(1)

    # 2) AST (if code files)
    ast_code = f'''
import json
from graphify.extract import collect_files, extract
from pathlib import Path

code_files = []
detect = json.loads(Path("graphify-out/.graphify_detect.json").read_text(encoding="utf-8"))
for f in detect.get("files", {{}}).get("code", []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    result = extract(code_files, cache_root=Path("{target}"))
    Path("graphify-out/.graphify_ast.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False))
    print(f"AST: {{len(result['nodes'])}} nodes, {{len(result['edges'])}} edges")
else:
    Path("graphify-out/.graphify_ast.json").write_text(
        json.dumps({{"nodes":[], "edges":[], "input_tokens":0, "output_tokens":0}}))
    print("No code files - skipping AST extraction")
'''
    run_py_script(py, ast_code)

    # 3) semantic (fast path: code-only corpus => empty)
    has_semantic = False
    for cat in ("document", "paper", "image"):
        if detect.get("files", {}).get(cat):
            has_semantic = True
            break
    if not has_semantic:
        sem_code = '''
import json
from pathlib import Path
Path("graphify-out/.graphify_semantic.json").write_text(
    json.dumps({{"nodes":[], "edges":[], "hyperedges":[], "input_tokens":0, "output_tokens":0}})
)
'''
        run_py_script(py, sem_code)
    else:
        # For non-code files, we rely on user running full /graphify with LLM or
        # manually using the SKILL.md flow. For now, create minimal file to avoid errors.
        sem_code = '''
import json
from pathlib import Path
Path("graphify-out/.graphify_semantic.json").write_text(
    json.dumps({{"nodes":[], "edges":[], "hyperedges":[], "input_tokens":0, "output_tokens":0}})
)
print("Semantic extraction skipped in graphify_query.py (non-code files require full SKILL.md flow).")
'''
        run_py_script(py, sem_code)

    # 4) merge AST + semantic
    merge_code = f'''
import json
from pathlib import Path

ast = json.loads(Path("graphify-out/.graphify_ast.json").read_text(encoding="utf-8"))
sem = json.loads(Path("graphify-out/.graphify_semantic.json").read_text(encoding="utf-8"))

seen = {{n["id"] for n in ast["nodes"]}}
merged_nodes = list(ast["nodes"])
for n in sem["nodes"]:
    if n["id"] not in seen:
        merged_nodes.append(n)
        seen.add(n["id"])

merged = {{
    "nodes": merged_nodes,
    "edges": ast["edges"] + sem["edges"],
    "hyperedges": sem.get("hyperedges", []),
    "input_tokens": sem.get("input_tokens", 0),
    "output_tokens": sem.get("output_tokens", 0),
}}
Path("graphify-out/.graphify_extract.json").write_text(
    json.dumps(merged, indent=2, ensure_ascii=False))
print(f"Merged: {{len(merged_nodes)}} nodes, {{len(merged['edges'])}} edges")
'''
    run_py_script(py, merge_code)

    # 5) build + cluster + analyze
    build_code = f'''
import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from pathlib import Path

extraction = json.loads(Path("graphify-out/.graphify_extract.json").read_text(encoding="utf-8"))
detection  = json.loads(Path("graphify-out/.graphify_detect.json").read_text(encoding="utf-8"))

G = build_from_json(extraction, root="{target}", directed=False)

if G.number_of_nodes() == 0:
    print("ERROR: Graph is empty - extraction produced no nodes.")
    sys.exit(1)

communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {{"input": extraction.get("input_tokens", 0), "output": extraction.get("output_tokens", 0)}}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {{cid: "Community " + str(cid) for cid in communities}}
questions = suggest_questions(G, communities, labels)

wrote = to_json(G, communities, "graphify-out/graph.json")
if not wrote:
    print("ERROR: graph.json write refused (shrink guard).")
    sys.exit(1)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "{target}", suggested_questions=questions)
Path("graphify-out/GRAPH_REPORT.md").write_text(report, encoding="utf-8")

analysis = {{
    "communities": {{str(k): v for k, v in communities.items()}},
    "cohesion": {{str(k): v for k, v in cohesion.items()}},
    "gods": gods,
    "surprises": surprises,
    "questions": questions,
}}
Path("graphify-out/.graphify_analysis.json").write_text(
    json.dumps(analysis, indent=2, ensure_ascii=False))

print(f"Graph: {{G.number_of_nodes()}} nodes, {{G.number_of_edges()}} edges, {{len(communities)}} communities")
'''
    run_py_script(py, build_code)

    # 6) HTML visualization
    html_code = f'''
import json, graphify
from graphify.build import build_from_json
from graphify.cluster import cluster
from pathlib import Path

extract = json.loads(Path("graphify-out/.graphify_extract.json").read_text(encoding="utf-8"))
G = build_from_json(extract, root="{target}", directed=False)
communities = cluster(G)
labels = {{cid: "Community " + str(cid) for cid in communities}}
graphify.to_html(G, communities, "graphify-out/index.html", community_labels=labels)
print("OK: index.html written")
'''
    run_py_script(py, html_code)

    print("Graph complete. Open graphify-out/index.html in a browser.")


def load_graph():
    if not GRAPH_FILE.exists():
        print("No graph found at", GRAPH_FILE, "- run: graphify_query.py init .")
        sys.exit(1)
    import networkx as nx
    from networkx.readwrite import json_graph
    data = json.loads(GRAPH_FILE.read_text())
    G = json_graph.node_link_graph(data, edges="links")
    return G


def build_vocab(G):
    vocab = set()
    for n in G.nodes:
        label = G.nodes[n].get("label", "") or ""
        for c in re.findall(r"[^\W\d_]+", label, re.UNICODE):
            parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", c) or [c]
            for p in parts:
                t = p.lower()
                if 3 <= len(t) <= 30:
                    vocab.add(t)
    return vocab


def expand_query_tokens(query: str, vocab: set) -> list[str]:
    """Expand user query into up to 12 tokens from graph vocabulary."""
    tokens = set(re.findall(r"[^\W\d_]+", query.lower(), re.UNICODE))
    expanded = []
    for t in tokens:
        if t in vocab and len(expanded) < 12:
            expanded.append(t)
        else:
            # Try prefix/substring match
            for v in vocab:
                if v.startswith(t) and len(expanded) < 12:
                    expanded.append(v)
                    break
    return expanded


def cmd_query(args):
    G = load_graph()
    question = args.question
    mode = "bfs" if not args.dfs else "dfs"
    budget = args.budget or 2000
    char_budget = budget * 4

    # Build vocab and expand tokens
    vocab = build_vocab(G)
    expanded = expand_query_tokens(question, vocab)
    print(f"Query expanded to (from graph vocab): {expanded}")
    if not expanded:
        print("No matching vocabulary for the question.")
        sys.exit(0)

    terms = [t.lower() for t in expanded if len(t) >= 3]
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "") or ""
        score = sum(1 for t in terms if t in label.lower())
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:3]]
    if not start_nodes:
        print("No matching nodes found for query terms:", terms)
        sys.exit(0)

    subgraph_nodes = set()
    subgraph_edges = []

    if mode == "dfs":
        visited = set()
        stack = [(n, 0) for n in reversed(start_nodes)]
        while stack:
            node, depth = stack.pop()
            if node in visited or depth > 6:
                continue
            visited.add(node)
            subgraph_nodes.add(node)
            for neighbor in G.neighbors(node):
                if neighbor not in visited:
                    stack.append((neighbor, depth + 1))
                    subgraph_edges.append((node, neighbor))
    else:
        frontier = set(start_nodes)
        subgraph_nodes = set(start_nodes)
        for _ in range(3):
            next_frontier = set()
            for n in frontier:
                for neighbor in G.neighbors(n):
                    if neighbor not in subgraph_nodes:
                        next_frontier.add(neighbor)
                        subgraph_edges.append((n, neighbor))
            subgraph_nodes.update(next_frontier)
            frontier = next_frontier

    def relevance(nid):
        label = G.nodes[nid].get("label", "") or ""
        return sum(1 for t in terms if t in label.lower())

    ranked_nodes = sorted(subgraph_nodes, key=relevance, reverse=True)

    lines = [
        f"Traversal: {mode.upper()} | "
        f"Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | "
        f"{len(subgraph_nodes)} nodes"
    ]

    for nid in ranked_nodes:
        d = G.nodes[nid]
        label = d.get("label", nid)
        src = d.get("source_file", "")
        loc = d.get("source_location", "")
        lines.append(f"  NODE {label} [src={src} loc={loc}]")

    for u, v in subgraph_edges:
        if u in subgraph_nodes and v in subgraph_nodes:
            _raw = G[u][v]
            if isinstance(_raw, dict):
                # Single-edge Graph
                d = _raw
            else:
                # MultiGraph or node_link with edge objects
                d = next(iter(_raw.values()), {}) if _raw else {}
            rel = d.get("relation", "") if isinstance(d, dict) else ""
            conf = d.get("confidence", "") if isinstance(d, dict) else ""
            ul = G.nodes[u].get("label", u)
            vl = G.nodes[v].get("label", v)
            lines.append(f"  EDGE {ul} --{rel} [{conf}]--> {vl}")

    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated at ~{budget} token budget)"
    print(output)


def cmd_path(args):
    G = load_graph()

    a_term = args.a
    b_term = args.b

    def find_node(term):
        term_l = term.lower()
        scored = sorted(
            (
                (
                    sum(1 for w in term_l.split() if w in (G.nodes[n].get("label", "") or "").lower()),
                    n,
                )
                for n in G.nodes()
            ),
            reverse=True,
        )
        return scored[0][1] if scored and scored[0][0] > 0 else None

    src = find_node(a_term)
    tgt = find_node(b_term)

    if not src or not tgt:
        print(f"Could not find nodes matching: {a_term!r} or {b_term!r}")
        sys.exit(0)

    import networkx as nx

    try:
        path = nx.shortest_path(G, src, tgt)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
        print(f"No path found between {a_term!r} and {b_term!r}: {e}")
        return

    print(f"Shortest path ({len(path) - 1} hops):")
    for i, nid in enumerate(path):
        label = G.nodes[nid].get("label", nid)
        if i < len(path) - 1:
            _raw = G[nid][path[i + 1]]
            edge = next(iter(_raw.values()), {}) if isinstance(_raw, dict) and len(_raw) == 1 else _raw
            rel = edge.get("relation", "")
            conf = edge.get("confidence", "")
            print(f"  {label} --{rel}--> [{conf}]")
        else:
            print(f"  {label}")


def cmd_explain(args):
    G = load_graph()
    term = args.node
    term_l = term.lower()

    scored = sorted(
        (
            (
                sum(1 for w in term_l.split() if w in (G.nodes[n].get("label", "") or "").lower()),
                n,
            )
            for n in G.nodes()
        ),
        reverse=True,
    )

    if not scored or scored[0][0] == 0:
        print(f"No node matching {term!r}")
        sys.exit(0)

    nid = scored[0][1]
    d = G.nodes[nid]
    label = d.get("label", nid)
    src_file = d.get("source_file", "unknown")
    file_type = d.get("file_type", "unknown")
    degree = G.degree(nid)

    print(f"NODE: {label}")
    print(f"  source: {src_file}")
    print(f"  type: {file_type}")
    print(f"  degree: {degree}")
    print()
    print("CONNECTIONS:")
    for neighbor in G.neighbors(nid):
        _raw = G[nid][neighbor]
        edge = next(iter(_raw.values()), {}) if isinstance(_raw, dict) and len(_raw) == 1 else _raw
        nlabel = G.nodes[neighbor].get("label", neighbor)
        rel = edge.get("relation", "")
        conf = edge.get("confidence", "")
        nf = G.nodes[neighbor].get("source_file", "")
        print(f"  --{rel}--> {nlabel} [{conf}] ({nf})")


def main():
    p = argparse.ArgumentParser(
        description="graphify_query - thin router for graphify in this repo"
    )
    s = p.add_subparsers(dest="command", required=True)

    # init
    p_init = s.add_parser("init", help="Build/update graph for a path")
    p_init.add_argument("path", nargs="?", default=".", help="Path to analyze")

    # query
    p_query = s.add_parser("query", help="Query the graph")
    p_query.add_argument("question", help="Question to ask the graph")
    p_query.add_argument("--dfs", action="store_true", help="Use DFS traversal instead of BFS")
    p_query.add_argument("--budget", type=int, default=2000, help="Token budget for output")

    # path
    p_path = s.add_parser("path", help="Shortest path between two concepts")
    p_path.add_argument("a", help="First concept")
    p_path.add_argument("b", help="Second concept")

    # explain
    p_explain = s.add_parser("explain", help="Explain a node in the graph")
    p_explain.add_argument("node", help="Node label or term")

    args = p.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "path":
        cmd_path(args)
    elif args.command == "explain":
        cmd_explain(args)


if __name__ == "__main__":
    main()