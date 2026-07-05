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
