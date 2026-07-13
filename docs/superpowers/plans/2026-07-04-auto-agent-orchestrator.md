> Archived: Historical design/planning docs.
> Not part of the current workflow; kept for context only.

# Auto-Agent Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stateless orchestrator and CLI tools that allow a 27B local LLM to tune packing hyperparameters and supply initialization scripts without manual file I/O.

**Architecture:** We will modify the Rust solver to accept initial positions, create `cli.py` to abstract terminal commands and TSV operations, and write `auto_agent.py` to manage the LLM prompts and API calls to `localhost:8080`.

**Tech Stack:** Python 3.14 (requests for LLM API), Rust (clap, serde_json)

## Global Constraints

- No modifications to the core geometry / optimization logic in `packer_rs`, only initialization.
- The local LLM prompt must be less than 2000 tokens.

---

### Task 1: Add `--initial-positions` to Rust Solver

**Files:**
- Modify: `packer_rs/Cargo.toml`
- Modify: `packer_rs/src/main.rs`

**Interfaces:**
- Consumes: JSON file containing `[x1, y1, a1, x2, y2, a2, ...]` array.
- Produces: Optimization result starting from those coordinates.

- [ ] **Step 1: Add serde and serde_json to Cargo.toml**

```toml
# Append to dependencies in packer_rs/Cargo.toml
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
```

- [ ] **Step 2: Update Args struct in `main.rs`**

```rust
// Add to Args struct
    #[arg(long)]
    initial_positions: Option<String>,
```

- [ ] **Step 3: Modify `run_attempt` signature and usage in `main.rs`**

Update `run_attempt` to accept `initial_positions: Option<&Vec<f64>>`. Pass it down from `main`.

```rust
// In main.rs, before the par_iter loop, read the initial positions if provided:
    let initial_positions = if let Some(path) = &args.initial_positions {
        let contents = fs::read_to_string(path).expect("Failed to read initial positions file");
        let positions: Vec<f64> = serde_json::from_str(&contents).expect("Invalid JSON in initial positions");
        Some(positions)
    } else {
        None
    };
```

Pass `initial_positions.as_ref()` into `run_attempt`.

- [ ] **Step 4: Use `initial_positions` in `run_attempt`**

In `run_attempt` inside `main.rs`, replace the `x0` initialization:

```rust
    let mut x0: Vec<f64> = if let Some(init_pos) = initial_positions {
        // If provided, use it and add a tiny perturbation so parallel attempts aren't identical
        init_pos.iter().map(|&v| v + (rng.gen::<f64>() - 0.5) * 1e-5).collect()
    } else if rng.gen_bool(0.5) {
        // ... existing random init ...
```

- [ ] **Step 5: Compile and verify**

```bash
cd packer_rs
cargo build --release
```
Expected: successful compilation.

- [ ] **Step 6: Commit**

```bash
git add packer_rs/Cargo.toml packer_rs/src/main.rs
git commit -m "feat: allow packer_rs to accept initial-positions"
```

---

### Task 2: Create `cli.py` (The Heavy-Lifting CLI)

**Files:**
- Create: `src/shape_packing/cli.py`

**Interfaces:**
- Consumes: The `results.tsv` file and `PACKING_REFERENCE.tsv`.
- Produces: A unified terminal command for suggesting problems and running them.

- [ ] **Step 1: Write `cli.py` skeleton and `suggest` command**

```python
import argparse
import sys
import json
import subprocess
from .agent_loop import load_history, choose_problem, current_best_scores

def handle_suggest(args):
    history = load_history("results.tsv")
    best = current_best_scores(history)
    problem = choose_problem(history, prefer_different=True)
    best_score = best.get(problem, "None")
    print(json.dumps({"problem": problem, "best_score": best_score}))

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    suggest_parser = subparsers.add_parser("suggest")
    
    run_parser = subparsers.add_parser("run")
    run_parser.add_parser("run")
    run_parser.add_argument("--problem", required=True)
    run_parser.add_argument("--attempts", type=int, default=1000)
    run_parser.add_argument("--init-script", type=str)
    
    args = parser.parse_args()
    if args.command == "suggest":
        handle_suggest(args)
    elif args.command == "run":
        handle_run(args)
```

- [ ] **Step 2: Implement `handle_run` command**

```python
def handle_run(args):
    # 1. Run init script if provided
    init_json_path = None
    if args.init_script:
        init_json_path = "initial_positions.json"
        res = subprocess.run([sys.executable, args.init_script, init_json_path], capture_output=True)
        if res.returncode != 0:
            print("Init script failed")
            sys.exit(1)
            
    # 2. Extract problem parts
    from .problems import parse_problem, shape_token_to_sides
    p = parse_problem(args.problem)
    N = p.N
    inner = shape_token_to_sides(p.inner_token)
    container = shape_token_to_sides(p.container_token)
    
    # 3. Call Rust solver
    cmd = [
        "packer_rs/target/release/packer_rs",
        str(N), str(inner), str(container),
        "--attempts", str(args.attempts),
    ]
    if init_json_path:
        cmd.extend(["--initial-positions", init_json_path])
        
    proc = subprocess.run(cmd, capture_output=True, text=True)
    
    score = 0.0
    for line in proc.stdout.splitlines():
        if "Final side length:" in line:
            score = float(line.split(":")[1].strip())
            
    # 4. Log to TSV
    from .agent_loop import log_result
    log_result(None, args.problem, score, 0.0, f"Auto run attempts={args.attempts}", commit="auto")
    
    # 5. Git commit
    subprocess.run(["git", "add", "results.tsv"])
    subprocess.run(["git", "commit", "-m", f"auto: run {args.problem} score {score}"])
    
    print(json.dumps({"score": score}))
```

- [ ] **Step 3: Export `cli.py` in `main()`**

```python
if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify `cli.py suggest`**

Run: `python -m shape_packing.cli suggest`
Expected: Outputs a JSON string with `problem` and `best_score`.

- [ ] **Step 5: Commit**

```bash
git add src/shape_packing/cli.py
git commit -m "feat: add unified cli.py for loop execution"
```

---

### Task 3: Create Orchestrator (`auto_agent.py`)

**Files:**
- Create: `auto_agent.py`

**Interfaces:**
- Consumes: Output from `cli.py suggest` and OpenAI-compatible API from `localhost:8080`.
- Produces: LLM-driven execution via `cli.py run`.

- [ ] **Step 1: Write `auto_agent.py` skeleton**

```python
import json
import subprocess
import time
import urllib.request
import sys

def get_state():
    res = subprocess.run([sys.executable, "-m", "shape_packing.cli", "suggest"], capture_output=True, text=True)
    return json.loads(res.stdout)

def call_llm(prompt):
    data = {
        "messages": [
            {"role": "system", "content": "You are an autonomous shape packing AI. Output ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request("http://localhost:8080/v1/chat/completions", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=json.dumps(data).encode('utf-8')) as response:
            return json.loads(response.read())['choices'][0]['message']['content']
    except Exception as e:
        print(f"LLM error: {e}")
        return None
```

- [ ] **Step 2: Write the main orchestration loop**

```python
def run_loop():
    while True:
        state = get_state()
        prompt = f"""
Current problem: {state['problem']}
Best score so far: {state['best_score']}

Respond with a JSON object containing:
- "action": either "run_experiment" or "request_architectural_change"
- "attempts": integer (if run_experiment)
- "init_script": optional string containing python code. If provided, the code should write an array of floats to 'initial_positions.json'. The script will receive the output file path as sys.argv[1].
- "reasoning": string explaining your choice
"""
        response = call_llm(prompt)
        if not response:
            time.sleep(5)
            continue
            
        try:
            decision = json.loads(response)
        except json.JSONDecodeError:
            print("Invalid JSON returned by LLM")
            continue
            
        if decision.get("action") == "request_architectural_change":
            with open("RESEARCH_REQUESTS.md", "a") as f:
                f.write(f"\n## Request\n{decision.get('reasoning')}\n")
            print("Architectural change requested. Halting loop.")
            sys.exit(0)
            
        # Run experiment
        attempts = decision.get("attempts", 1000)
        script_code = decision.get("init_script")
        
        cmd = [sys.executable, "-m", "shape_packing.cli", "run", "--problem", state['problem'], "--attempts", str(attempts)]
        
        if script_code:
            with open("temp_init.py", "w") as f:
                f.write(script_code)
            cmd.extend(["--init-script", "temp_init.py"])
            
        subprocess.run(cmd)
        time.sleep(2)

if __name__ == "__main__":
    run_loop()
```

- [ ] **Step 3: Commit**

```bash
git add auto_agent.py
git commit -m "feat: add autonomous orchestrator auto_agent.py"
```
