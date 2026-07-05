# Auto-Agent Orchestrator Design

## Goal
To build a highly constrained, token-efficient autonomous research loop for a local LLM (Qwen 27B). The system isolates the LLM from manual file I/O, terminal parsing, and complex state management, while allowing it to tune hyperparameters and write Python initialization scripts for the fast Rust backend.

## Architecture

The system is composed of three main layers:

### 1. The CLI Layer (`src/shape_packing/cli.py`)
A robust command-line tool that abstracts away the heavy lifting so the orchestrator doesn't have to manage raw scripts, git, or TSVs.
- **`cli.py suggest`**: Reads `results.tsv` and `PACKING_REFERENCE.tsv`, applies diversity rules, and outputs a highly summarized state (e.g., "Stuck on 8_3_in_5. Best: 1.86. Recommend switching or radical change.").
- **`cli.py run`**: Accepts arguments like `--problem`, `--attempts`, and `--init-script`. 
  - If `--init-script` is provided, it executes the Python script to generate `initial_positions.json`.
  - It calls the Rust solver (`packer_rs`), passing the initial positions.
  - It parses the output score, appends the result to `results.tsv`, and automatically commits to git.

### 2. The Rust Backend Interface
- Update `packer_rs` to accept an `--initial-positions <file.json>` flag.
- When provided, Rust skips its internal random/grid initialization and uses the provided coordinates as the starting state for optimization.

### 3. The Orchestrator (`auto_agent.py`)
A continuous Python script that acts as the bridge between the local LLM (`llama.cpp` on port 8080) and the CLI.
- **Prompt Generation**: Uses `cli.py suggest` to build a tiny, context-efficient prompt containing the current problem state and a menu of options.
- **JSON API Communication**: Sends the prompt to the local LLM and demands a JSON response.
- **Action Space**:
  - `run_experiment`: The LLM provides hyperparameters and an optional Python script string to generate initial coordinates. The orchestrator writes the script to a temp file and runs `cli.py run`.
  - `request_architectural_change`: If the LLM determines it is globally stuck (based on the prompt's context), it can request a core system upgrade (e.g., "Implement simulated annealing in Rust"). 
- **Breakout Mechanism**: When `request_architectural_change` is triggered, the orchestrator halts the loop, logs the detailed request to `RESEARCH_REQUESTS.md`, and exits so the human (or a larger LLM via Cline) can safely perform the refactor.

## Constraints & Error Handling
- **Invalid JSON**: The orchestrator will catch invalid JSON from the LLM and issue a simple retry prompt ("Invalid JSON, try again").
- **LLM Safety**: The local LLM never runs arbitrary `bash` commands and never reads raw TSV/log files. Its context window remains tightly controlled (<2k tokens).
