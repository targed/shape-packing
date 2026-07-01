# Graphify Usage

This directory contains:

- A graphify knowledge graph: graphify-out/
- A helper router: graphify_query.py

## What is graphify?

graphify turns a repository into a persistent knowledge graph:

- Nodes: modules, classes, functions, concepts, files.
- Edges: depends_on, calls, imports, relates_to, etc.
- Communities: clusters like "training loop", "rendering", "Rust packer core".

It is used to:
- Understand architecture quickly.
- Ask natural-language questions about the codebase.
- Trace conceptual paths (e.g., "how does X connect to Y?") without reading everything.

## Commands (from project root)

Use graphify_query.py with the graphify Python environment (already installed):

- Build/update graph:
  - python3 graphify_query.py init .
- Query graph:
  - python3 graphify_query.py query "How is the gradient computed?"
  - Optional: --dfs (DFS traversal), --budget N (token budget)
- Shortest path between concepts:
  - python3 graphify_query.py path "train" "render"
- Explain a node:
  - python3 graphify_query.py explain "OptResult"

Example:
- python3 graphify_query.py query "How is packing evaluated?"
- python3 graphify_query.py path "Rust packer" "render_solution"
- python3 graphify_query.py explain "regular_polygon"

## For Cline / AI integration (system prompt snippet)

Paste this into your Cline system prompt so it knows how to use /graphify:

- Treat any message starting with "/graphify" as a graphify command.
- If "/graphify .", "/graphify <path>", or "/graphify" with no args:
  - Run: python3 graphify_query.py init .
  - Report: nodes, edges, communities count.
- If "/graphify query <question>":
  - If graphify-out/graph.json exists, do not rebuild unless explicitly asked.
  - Run: python3 graphify_query.py query "<question>"
  - Answer using only the traversal output; cite nodes/files when relevant.
- If "/graphify path A B":
  - Run: python3 graphify_query.py path "A" "B"
  - Explain the path in plain language.
- If "/graphify explain <node>":
  - Run: python3 graphify_query.py explain "<node>"
  - Provide a 3–5 sentence explanation based on the output.

Notes:
- Do not invent edges or relationships; rely on graph outputs.
- Prefer graph-based answers for architecture questions over general reasoning.
- When in doubt, use graphify_query.py instead of guessing.