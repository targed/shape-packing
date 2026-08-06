import argparse
import sys
import json
import subprocess
from .agent_loop import load_history, choose_problem, current_best_scores

def handle_suggest(args):
    history = load_history("results.tsv")
    best = current_best_scores(history)
    
    filters = {}
    if args.min_n is not None: filters["min_n"] = args.min_n
    if args.max_n is not None: filters["max_n"] = args.max_n
    if args.equal_n is not None: filters["equal_n"] = args.equal_n
    if args.include_inner is not None: filters["include_inner"] = args.include_inner.split(",")
    if args.exclude_inner is not None: filters["exclude_inner"] = args.exclude_inner.split(",")
    if args.include_container is not None: filters["include_container"] = args.include_container.split(",")
    if args.exclude_container is not None: filters["exclude_container"] = args.exclude_container.split(",")
    if args.min_inner_sides is not None: filters["min_inner_sides"] = args.min_inner_sides
    if args.max_inner_sides is not None: filters["max_inner_sides"] = args.max_inner_sides
    if args.min_container_sides is not None: filters["min_container_sides"] = args.min_container_sides
    if args.max_container_sides is not None: filters["max_container_sides"] = args.max_container_sides

    exclude_problems = None
    if getattr(args, 'exclude_problems', None) is not None:
        exclude_problems = set(args.exclude_problems.split(","))
    
    problem = choose_problem(history, prefer_different=True, filters=filters, exclude_problems=exclude_problems)
    best_score = best.get(problem, "None")
    print(json.dumps({"problem": problem, "best_score": best_score}))

def handle_run(args):
    def eprint(*a, **kw):
        if args.json_out:
            kw["file"] = sys.stderr
        print(*a, **kw)

    # 1. Run init script if provided
    init_json_path = None
    if args.init_script:
        init_json_path = "initial_positions.json"
        res = subprocess.run([sys.executable, args.init_script, init_json_path], capture_output=True, text=True)
        if res.returncode != 0:
            eprint("Init script failed:\n" + res.stderr)
            sys.exit(1)
            
    # 2. Extract problem parts
    from .problems import parse_problem, shape_token_to_sides
    p = parse_problem(args.problem)
    N = p.N
    inner = p.inner_token
    container = p.container_token
    
    import os
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = os.path.join("results", args.problem, timestamp)
    os.makedirs(result_dir, exist_ok=True)
    solution_file = os.path.join(result_dir, "solution.json")
    
    # 3. Call Rust solver
    if not getattr(args, "no_build", False):
        eprint("Compiling Rust solver...")
        subprocess.run(
            ["cargo", "build", "--release"],
            cwd="packer_rs",
            check=True,
            stdout=subprocess.DEVNULL,
        )
    
    cmd = [
        "packer_rs/target/release/packer_rs",
        str(N), str(inner), str(container),
        "--attempts", str(args.attempts),
        "--solution-file", solution_file
    ]
    if init_json_path:
        cmd.extend(["--initial-positions", init_json_path])
        
    from .solution_tools import inverse_friedman_metric
    from .agent_loop import load_history, current_best_scores
    
    # Fetch best score and inject target-s
    try:
        history = load_history("results.tsv")
        # Ignore fake/verification rows so we never inject an impossible target-s.
        history = [
            r for r in history
            if r.commit.lower() not in ("verify", "auto-verify", "test")
            and "verify" not in (r.description or "").lower()
        ]
        best = current_best_scores(history)
        best_score = best.get(args.problem, "None")
        
        if best_score != "None":
            target_s = inverse_friedman_metric(float(best_score), inner, container)
            cmd.extend(["--target-s", str(target_s)])
            eprint(f"Injecting --target-s {target_s} (from Friedman best_score {best_score})")
    except Exception as e:
        eprint(f"Could not inject target_s: {e}")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    
    if proc.returncode != 0:
        eprint(f"Rust solver failed with exit code {proc.returncode}")
        eprint(proc.stderr)
        sys.exit(1)

    # Detect if solver reported no valid packing.
    solver_output = proc.stdout.strip()
    if "No valid packing found" in solver_output:
        eprint("Solver reported: No valid packing found. Refusing to log 0.0 score.")
        sys.exit(0)

    # Extract score
    score = 0.0
    found_score = False
    for line in solver_output.splitlines():
        if "Final side length:" in line:
            score = float(line.split(":")[1].strip())
            found_score = True

    if not found_score:
        eprint("Warning: 'Final side length' not found in solver output.")
            
    # Verify and render
    if os.path.exists(solution_file):
        verify_cmd = [sys.executable, os.path.join("scripts", "verify_solution.py"), solution_file, args.problem]
        subprocess.run(verify_cmd)
        
        if not getattr(args, "no_png", False):
            render_cmd = [sys.executable, os.path.join("scripts", "render_solution.py"), solution_file, os.path.join(result_dir, "solution.png")]
            subprocess.run(render_cmd)
            
    # 4. Log to TSV
    if not args.no_commit:
        from .agent_loop import log_result
        log_result(None, args.problem, score, 0.0, f"Auto run attempts={args.attempts}", commit="auto")
        
        # 5. Git commit
        subprocess.run(["git", "add", "results.tsv", "results/"])
        subprocess.run(["git", "commit", "-m", f"auto: run {args.problem} score {score}"])
    
    print(json.dumps({"score": score}))

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    suggest_parser = subparsers.add_parser("suggest")
    suggest_parser.add_argument("--min-n", type=int)
    suggest_parser.add_argument("--max-n", type=int)
    suggest_parser.add_argument("--equal-n", type=int)
    suggest_parser.add_argument("--include-inner", type=str)
    suggest_parser.add_argument("--exclude-inner", type=str)
    suggest_parser.add_argument("--include-container", type=str)
    suggest_parser.add_argument("--exclude-container", type=str)
    suggest_parser.add_argument("--min-inner-sides", type=int)
    suggest_parser.add_argument("--max-inner-sides", type=int)
    suggest_parser.add_argument("--min-container-sides", type=int)
    suggest_parser.add_argument("--max-container-sides", type=int)
    suggest_parser.add_argument("--exclude-problems", type=str, help="Comma-separated list of problems to exclude")
    
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--problem", required=True)
    run_parser.add_argument("--attempts", type=int, default=1000)
    run_parser.add_argument("--init-script", type=str)
    run_parser.add_argument("--no-commit", action="store_true")
    run_parser.add_argument("--json-out", action="store_true")
    run_parser.add_argument("--no-png", action="store_true", help="Skip generating solution.png image to save disk space")
    run_parser.add_argument("--no-build", action="store_true", help="Skip compiling the Rust solver")
    
    args = parser.parse_args()
    if args.command == "suggest":
        handle_suggest(args)
    elif args.command == "run":
        handle_run(args)
        
if __name__ == "__main__":
    main()
