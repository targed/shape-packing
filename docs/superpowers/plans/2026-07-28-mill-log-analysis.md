# Mill Log Analysis Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Python script using pandas and matplotlib to parse the supercomputer log output, aggregate statistics on shape packing attempts, and output a detailed Markdown report with embedded charts.

**Architecture:** A single Python script `scripts/analyze_mill_log.py` that sequentially performs parsing (regex extraction into list of dicts), feature extraction (converting shapes to sizes), data aggregation via pandas, and visualization via matplotlib.

**Tech Stack:** Python 3, Pandas, Matplotlib, Regex

## Global Constraints
- Target log file: `results/mill-2330986.out`
- Output directory: `analysis/`
- Output report: `analysis/report.md`
- Script path: `scripts/analyze_mill_log.py`

---

### Task 1: Scaffolding and Basic Parsing

**Files:**
- Create: `scripts/analyze_mill_log.py`
- Test: (We will test by running the script locally against the actual log file)

**Interfaces:**
- Consumes: The `results/mill-2330986.out` log file.
- Produces: A pandas DataFrame containing `problem`, `status` (start, success, fail), `score`, and parsed parameters.

- [ ] **Step 1: Write the parsing logic**

```python
import os
import re
import pandas as pd

def parse_log(filepath):
    events = []
    
    # Regex patterns
    start_re = re.compile(r"\[(.*?)\] Starting \((.*?) attempts\)")
    success_re = re.compile(r"\[(.*?)\] Success!")
    score_re = re.compile(r"\[Main\] Worker finished (.*?) with score ([\d\.]+)")
    fail_re = re.compile(r"\[(.*?)\] Search failed")
    no_improve_re = re.compile(r"\[(.*?)\] Solution valid but NOT an improvement")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            m_start = start_re.search(line)
            if m_start:
                events.append({"problem": m_start.group(1), "type": "start", "attempts": int(m_start.group(2)), "score": None})
                continue
                
            m_success = success_re.search(line)
            if m_success:
                events.append({"problem": m_success.group(1), "type": "success", "attempts": None, "score": None})
                continue
                
            m_score = score_re.search(line)
            if m_score:
                events.append({"problem": m_score.group(1), "type": "score", "attempts": None, "score": float(m_score.group(2))})
                continue
                
            m_fail = fail_re.search(line)
            if m_fail:
                events.append({"problem": m_fail.group(1), "type": "fail", "attempts": None, "score": None})
                continue
                
            m_no = no_improve_re.search(line)
            if m_no:
                events.append({"problem": m_no.group(1), "type": "no_improvement", "attempts": None, "score": None})
                continue

    return pd.DataFrame(events)

if __name__ == "__main__":
    df = parse_log("results/mill-2330986.out")
    print(df.head())
    print(f"Total events: {len(df)}")
```

- [ ] **Step 2: Run test to verify parsing works**

Run: `python scripts/analyze_mill_log.py`
Expected: Output showing the DataFrame head and total events (should be thousands).

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_mill_log.py
git commit -m "feat: parse mill log into pandas dataframe"
```

---

### Task 2: Feature Extraction and Aggregation

**Files:**
- Modify: `scripts/analyze_mill_log.py:44-55`

**Interfaces:**
- Consumes: The `df` DataFrame from Task 1.
- Produces: An aggregated DataFrame with `success_rate`, `total_starts`, `N`, `inner_sides`, `container_sides`.

- [ ] **Step 1: Write feature extraction and aggregation**

```python
import numpy as np

def extract_features(df):
    # Create an aggregated dataframe grouped by problem
    
    starts = df[df['type'] == 'start'].groupby('problem').size().reset_index(name='total_starts')
    successes = df[df['type'] == 'success'].groupby('problem').size().reset_index(name='total_successes')
    scores = df[df['type'] == 'score'].groupby('problem')['score'].min().reset_index(name='best_score')
    
    agg_df = pd.merge(starts, successes, on='problem', how='left')
    agg_df = pd.merge(agg_df, scores, on='problem', how='left')
    agg_df['total_successes'] = agg_df['total_successes'].fillna(0)
    agg_df['success_rate'] = agg_df['total_successes'] / agg_df['total_starts']
    
    # Extract properties from problem string (e.g. 12_3_in_5)
    def parse_prob(p):
        parts = p.split('_')
        if len(parts) >= 4 and parts[2] == 'in':
            return pd.Series([int(parts[0]), parts[1], parts[3], f"{parts[1]}_in_{parts[3]}"])
        return pd.Series([None, None, None, p])
        
    agg_df[['N', 'inner_sides', 'container_sides', 'problem_family']] = agg_df['problem'].apply(parse_prob)
    return agg_df

# Update main:
if __name__ == "__main__":
    df = parse_log("results/mill-2330986.out")
    agg_df = extract_features(df)
    print(agg_df.head())
```

- [ ] **Step 2: Run script to verify aggregation**

Run: `python scripts/analyze_mill_log.py`
Expected: Output showing the grouped DataFrame with N, inner, and container shapes.

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_mill_log.py
git commit -m "feat: aggregate shape packing stats and extract features"
```

---

### Task 3: Matplotlib Chart Generation

**Files:**
- Modify: `scripts/analyze_mill_log.py:65-90`

**Interfaces:**
- Consumes: The `agg_df` from Task 2.
- Produces: PNG charts saved to `analysis/`.

- [ ] **Step 1: Write chart generation logic**

```python
import matplotlib.pyplot as plt

def generate_charts(agg_df, output_dir="analysis"):
    os.makedirs(output_dir, exist_ok=True)
    
    # Chart 1: Top 15 Most Frequently Run Problems
    top_runs = agg_df.sort_values('total_starts', ascending=False).head(15)
    plt.figure(figsize=(10, 6))
    plt.bar(top_runs['problem'], top_runs['total_starts'])
    plt.xticks(rotation=45, ha='right')
    plt.title('Top 15 Most Frequently Run Problems')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_problems.png'))
    plt.close()
    
    # Chart 2: Attempts by Problem Family
    fam_runs = agg_df.groupby('problem_family')['total_starts'].sum().sort_values(ascending=False).head(10)
    plt.figure(figsize=(8, 8))
    plt.pie(fam_runs, labels=fam_runs.index, autopct='%1.1f%%')
    plt.title('Top 10 Problem Families by Total Runs')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'family_distribution.png'))
    plt.close()
    
    # Chart 3: N vs Success Rate Scatter
    valid = agg_df.dropna(subset=['N'])
    plt.figure(figsize=(10, 6))
    plt.scatter(valid['N'], valid['success_rate'], alpha=0.5)
    plt.title('Number of Shapes (N) vs Success Rate')
    plt.xlabel('N (Number of Inner Shapes)')
    plt.ylabel('Success Rate')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'n_vs_success.png'))
    plt.close()

# Update main:
if __name__ == "__main__":
    df = parse_log("results/mill-2330986.out")
    agg_df = extract_features(df)
    generate_charts(agg_df)
    print("Charts generated in analysis/")
```

- [ ] **Step 2: Run script to verify images**

Run: `python scripts/analyze_mill_log.py`
Expected: Output showing "Charts generated in analysis/". Verify 3 PNGs exist in `analysis/`.

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_mill_log.py
git commit -m "feat: generate matplotlib charts for log analysis"
```

---

### Task 4: Markdown Report Generation

**Files:**
- Modify: `scripts/analyze_mill_log.py:90-110`

**Interfaces:**
- Consumes: The `agg_df` from Task 2.
- Produces: `analysis/report.md` text file.

- [ ] **Step 1: Write report generation logic**

```python
def write_report(agg_df, output_dir="analysis"):
    total_problems = len(agg_df)
    total_starts = agg_df['total_starts'].sum()
    total_successes = agg_df['total_successes'].sum()
    overall_success = total_successes / total_starts if total_starts > 0 else 0
    
    md = f"""# Mill Log Analysis Report

## High-Level Summary
- **Total Unique Problems Run:** {total_problems}
- **Total Individual Attempts (Starts):** {total_starts}
- **Total Successes Found:** {total_successes}
- **Overall Success Rate:** {overall_success:.2%}

## Visualizations

### Most Frequently Run Problems
![Top Problems](top_problems.png)

### Distribution by Problem Family
![Problem Families](family_distribution.png)

### Difficulty Scaling (N vs Success Rate)
![N vs Success](n_vs_success.png)

## Top 10 Best Improvements
"""
    
    # Add table of best improvements
    best_df = agg_df.dropna(subset=['best_score']).sort_values('best_score').head(10)
    md += "| Problem | Total Runs | Success Rate | Best Score |\n"
    md += "|---------|------------|--------------|------------|\n"
    for _, row in best_df.iterrows():
        md += f"| {row['problem']} | {row['total_starts']} | {row['success_rate']:.1%} | {row['best_score']} |\n"
        
    with open(os.path.join(output_dir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(md)

# Update main:
if __name__ == "__main__":
    df = parse_log("results/mill-2330986.out")
    agg_df = extract_features(df)
    generate_charts(agg_df)
    write_report(agg_df)
    print("Report generated at analysis/report.md")
```

- [ ] **Step 2: Run script to verify final output**

Run: `python scripts/analyze_mill_log.py`
Expected: Output showing "Report generated at analysis/report.md".

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_mill_log.py
git commit -m "feat: generate markdown report summarizing shape packing analytics"
```
