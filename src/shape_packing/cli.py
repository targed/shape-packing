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
    
    problem = choose_problem(history, prefer_different=True, filters=filters)
    best_score = best.get(problem, "None")
    print(json.dumps({"problem": problem, "best_score": best_score}))

def handle_run(args):
    # 1. Run init script if provided
    init_json_path = None
    if args.init_script:
        init_json_path = "initial_positions.json"
        res = subprocess.run([sys.executable, args.init_script, init_json_path], capture_output=True, text=True)
        if res.returncode != 0:
            print("Init script failed:\n" + res.stderr)
            sys.exit(1)
            
    # 2. Extract problem parts
    from .problems import parse_problem, shape_token_to_sides
    p = parse_problem(args.problem)
    N = p.N
    inner = shape_token_to_sides(p.inner_token)
    container = shape_token_to_sides(p.container_token)
    
    import os
    os.makedirs("results", exist_ok=True)
    solution_file = f"results/{args.problem}_best.json"
    
    # 3. Call Rust solver
    cmd = [
        "packer_rs/target/release/packer_rs",
        str(N), str(inner), str(container),
        "--attempts", str(args.attempts),
        "--solution-file", solution_file
    ]
    if init_json_path:
        cmd.extend(["--initial-positions", init_json_path])
        
    proc = subprocess.run(cmd, capture_output=True, text=True)
    
    score = 0.0
    for line in proc.stdout.splitlines():
        if "Final side length:" in line:
            score = float(line.split(":")[1].strip())
            
    # Verify and render
    if os.path.exists(solution_file):
        verify_cmd = [sys.executable, "verify_solution.py", solution_file]
        subprocess.run(verify_cmd)
        
        render_cmd = [sys.executable, "render_solution.py", solution_file, f"results/{args.problem}_best.png"]
        subprocess.run(render_cmd)
            
    # 4. Log to TSV
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
    
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--problem", required=True)
    run_parser.add_argument("--attempts", type=int, default=1000)
    run_parser.add_argument("--init-script", type=str)
    
    args = parser.parse_args()
    if args.command == "suggest":
        handle_suggest(args)
    elif args.command == "run":
        handle_run(args)
        
if __name__ == "__main__":
    main()
