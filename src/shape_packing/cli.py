import argparse
import sys
import json
import subprocess
from .agent_loop import load_history, choose_problem, current_best_scores
from .solver_interface import run_solver


def handle_suggest(args, history_cache=None, direct_call=False):
    if history_cache is not None:
        history = history_cache
    else:
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
    
    out = {"problem": problem, "best_score": best_score}
    if direct_call:
        return out
    print(json.dumps(out))

def handle_run(args, history_cache=None, direct_call=False):
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
            err = "Init script failed:\n" + res.stderr
            eprint(err)
            if direct_call:
                return {"success": False, "error": err, "returncode": 1}
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
    
    from .solution_tools import inverse_friedman_metric
    from .agent_loop import load_history, current_best_scores


    target_s = None
    try:
        if history_cache is not None:
            history = history_cache
        else:
            history = load_history("results.tsv")
            
        history = [
            r for r in history
            if r.commit.lower() not in ("verify", "auto-verify", "test")
            and "verify" not in (r.description or "").lower()
        ]
        best = current_best_scores(history)
        best_score = best.get(args.problem, "None")
        
        if best_score != "None":
            target_s = inverse_friedman_metric(float(best_score), inner, container)
            eprint(f"Injecting --target-s {target_s} (from Friedman best_score {best_score})")
    except Exception as e:
        eprint(f"Could not inject target_s: {e}")

    init_positions_list = None
    if init_json_path and os.path.exists(init_json_path):
        try:
            with open(init_json_path, "r") as f:
                init_positions_list = json.load(f)
        except Exception:
            pass

    res = run_solver(
        n_shapes=N,
        inner_shape=str(inner),
        container_shape=str(container),
        attempts=args.attempts,
        initial_positions=init_positions_list,
        target_s=target_s,
        solution_file=solution_file,
        no_build=getattr(args, "no_build", False),
    )

    if not res.get("success"):
        if res.get("output") and "No valid packing found" in res.get("output"):
            eprint("Solver reported: No valid packing found. Refusing to log 0.0 score.")
            if direct_call:
                return {"success": False, "error": "No valid packing found", "returncode": 42}
            sys.exit(0)
        
        err = f"Rust solver failed: {res.get('error', 'Unknown error')}"
        eprint(err)
        if direct_call:
            return {"success": False, "error": err, "returncode": res.get("returncode", 1)}
        sys.exit(1)

    score = res.get("score", 0.0)

            
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
    
    out = {"score": score}
    if direct_call:
        return {"success": True, "score": score, "returncode": 0}
    print(json.dumps(out))

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
