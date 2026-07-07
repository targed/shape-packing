import json
import subprocess
import time
import urllib.request
import sys

import os

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("llm_decisions.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

def get_state():
    cmd = [sys.executable, "-m", "src.shape_packing.cli", "suggest"]
    
    if os.path.exists("filter.json"):
        try:
            with open("filter.json", "r") as f:
                filters = json.load(f)
            
            # Map json keys to CLI args
            mapping = {
                "min_n": "--min-n", "max_n": "--max-n", "equal_n": "--equal-n",
                "include_inner": "--include-inner", "exclude_inner": "--exclude-inner",
                "include_container": "--include-container", "exclude_container": "--exclude-container",
                "min_inner_sides": "--min-inner-sides", "max_inner_sides": "--max-inner-sides",
                "min_container_sides": "--min-container-sides", "max_container_sides": "--max-container-sides"
            }
            
            for k, v in filters.items():
                if k in mapping and v is not None:
                    cmd.extend([mapping[k], str(v)])
        except Exception as e:
            logging.error(f"Error reading filter.json: {e}")
            
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        logging.error(f"Error parsing CLI output: {res.stdout}")
        return {"problem": "8_3_in_5", "best_score": "None"}

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
        logging.error(f"LLM error: {e}")
        return None

def run_loop():
    logging.info("Starting Auto Agent Loop...")
    while True:
        state = get_state()
        logging.info(f"--- Iteration ---")
        logging.info(f"Target Problem: {state['problem']} (Best score: {state['best_score']})")
        
        prompt = f"""
Current problem: {state['problem']}
Best score so far: {state['best_score']}

Respond with a JSON object containing:
- "action": either "run_experiment" or "request_architectural_change"
- "attempts": integer (if run_experiment)
- "init_script": optional string containing python code. If provided, the code should write an array of floats to 'initial_positions.json'. The script will receive the output file path as sys.argv[1].
- "reasoning": string explaining your choice
"""
        logging.info("Querying LLM for decision...")
        response = call_llm(prompt)
        if not response:
            logging.warning("No response from LLM, retrying in 5s...")
            time.sleep(5)
            continue
            
        try:
            decision = json.loads(response)
            logging.info(f"LLM Decision:\n{json.dumps(decision, indent=2)}")
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON returned by LLM:\n{response}")
            time.sleep(5)
            continue
            
        if decision.get("action") == "request_architectural_change":
            with open("RESEARCH_REQUESTS.md", "a") as f:
                f.write(f"\n## Request\n{decision.get('reasoning')}\n")
            logging.info("Architectural change requested. Halting loop.")
            sys.exit(0)
            
        # Run experiment
        attempts = decision.get("attempts", 1000)
        script_code = decision.get("init_script")
        
        cmd = [sys.executable, "-m", "src.shape_packing.cli", "run", "--problem", state['problem'], "--attempts", str(attempts)]
        
        if script_code:
            logging.info("LLM provided an init_script. Writing to temp_init.py.")
            with open("temp_init.py", "w") as f:
                f.write(script_code)
            cmd.extend(["--init-script", "temp_init.py"])
            
        logging.info(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd)
        logging.info("Experiment run complete. Sleeping 2s...")
        time.sleep(2)

if __name__ == "__main__":
    run_loop()
