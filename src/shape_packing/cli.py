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

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    suggest_parser = subparsers.add_parser("suggest")
    
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
