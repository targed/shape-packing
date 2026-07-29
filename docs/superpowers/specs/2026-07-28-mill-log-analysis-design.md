# Mill Log Analysis Script Design

## Objective
Create a Python script (`scripts/analyze_mill_log.py`) that parses output logs from the parallel shape-packing autoresearch runner (e.g. `results/mill-2330986.out`), aggregates statistics using `pandas`, generates charts using `matplotlib`, and outputs a comprehensive Markdown report.

## Input
- A path to the log file (e.g. `results/mill-2330986.out`).

## Output
An `analysis/` folder generated in the root repository containing:
1. `report.md`: The detailed Markdown text report.
2. `*.png`: Several PNG charts embedded in the Markdown report.

## Architecture

### 1. Data Parsing (`parse_log`)
We will read the log file line-by-line and use Regular Expressions to extract:
- **Starts**: `[{problem}] Starting ({attempts} attempts)`
- **Successes**: `[{problem}] Success!`
- **Score completions**: `[Main] Worker finished {problem} with score {score}`

Each event will be stored in a list of dictionaries, which is then converted into a `pandas.DataFrame` for aggregation.

### 2. Feature Extraction (`extract_features`)
For each problem (e.g. `12_3_in_5`), we will extract:
- `N` (number of inner shapes, e.g. 12)
- `inner_sides` (e.g. 3)
- `container_sides` (e.g. 5)
- `problem_family` (e.g. `3_in_5`)

### 3. Analytics & Aggregation
Using Pandas, we will compute:
- **Total problems run**: Unique list of problems.
- **Run frequency**: How many times each problem was attempted.
- **Success rates**: The percentage of runs that resulted in a "Success!".
- **Score Improvements**: Extract the final scores logged by the main worker.
- **Distribution metrics**: Group runs by `problem_family`, `N`, `inner_sides`, and `container_sides`.

### 4. Graph Generation (`generate_charts`)
We will use Matplotlib (and optionally seaborn if available) to create:
- A bar chart of the top 15 most frequently run problems.
- A pie chart or bar chart of attempts by `problem_family`.
- A histogram/bar chart of runs distributed by `N` (number of shapes).
- A scatter plot of `N` vs `Success Rate` (to see if higher N is harder to succeed).

### 5. Report Generation (`write_report`)
We will compile the statistics and embed the image paths into a formatted `analysis/report.md` file.

## Error Handling
- If a line is malformed, the parser will ignore it.
- If `pandas` or `matplotlib` is not installed, the script will catch the `ImportError` and instruct the user to `pip install pandas matplotlib`.
