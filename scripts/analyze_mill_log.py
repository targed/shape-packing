import argparse
import glob
import os
import re
import sys
import json
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
try:
    from shape_packing.packing_config import ANALYSIS_PLOT_DPI
except ImportError:
    from src.shape_packing.packing_config import ANALYSIS_PLOT_DPI

import numpy as np
import pandas as pd

def parse_args():
    parser = argparse.ArgumentParser(description="Advanced Log Analysis & Visualization for Shape Packing Slurm Runs")
    default_out = "data/analysis" if os.path.exists("data/analysis") else "analysis"
    parser.add_argument("--output-dir", type=str, default=default_out, help="Directory to save report and generated charts (default: data/analysis)")
    parser.add_argument("--top-n", type=int, default=15, help="Number of items to show in top tables and charts (default: 15)")
    parser.add_argument("--min-runs", type=int, default=1, help="Filter out problems with total runs < MIN_RUNS (default: 1)")
    parser.add_argument("--family", type=str, default=None, help="Filter by specific problem family (e.g. '3_in_5')")
    parser.add_argument("--min-n", type=int, default=None, help="Filter problems with N < MIN_N")
    parser.add_argument("--max-n", type=int, default=None, help="Filter problems with N > MAX_N")
    return parser.parse_args()

def find_latest_log():
    log_files = glob.glob(os.path.join("data", "results", "mill-*.out")) + glob.glob(os.path.join("results", "mill-*.out"))
    if not log_files:
        raise FileNotFoundError("No log files matching 'data/results/mill-*.out' or 'results/mill-*.out' were found.")
    log_files.sort(key=os.path.getmtime, reverse=True)
    return log_files[0]

def parse_log(filepath):
    events = []
    
    # Strict regex patterns for problem names [N_shape_in_container]
    start_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Starting \((\d+) attempts\)")
    success_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Success!")
    score_re = re.compile(r"\[Main\] Worker finished ([a-zA-Z0-9_]+) with score ([\d\.]+)")
    fail_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Search failed")
    no_improve_re = re.compile(r"\[([a-zA-Z0-9_]+)\] Solution valid but NOT an improvement")
    worker_fail_re = re.compile(r"\[Main\] Worker failed on ([a-zA-Z0-9_]+):")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            for m_start in start_re.finditer(line):
                events.append({"problem": m_start.group(1), "type": "start", "attempts": int(m_start.group(2)), "score": None})
                
            for m_success in success_re.finditer(line):
                events.append({"problem": m_success.group(1), "type": "success", "attempts": None, "score": None})
                
            for m_score in score_re.finditer(line):
                events.append({"problem": m_score.group(1), "type": "score", "attempts": None, "score": float(m_score.group(2))})
                
            for m_fail in fail_re.finditer(line):
                events.append({"problem": m_fail.group(1), "type": "fail", "attempts": None, "score": None})
                
            for m_no in no_improve_re.finditer(line):
                events.append({"problem": m_no.group(1), "type": "no_improvement", "attempts": None, "score": None})

            for m_wfail in worker_fail_re.finditer(line):
                events.append({"problem": m_wfail.group(1), "type": "worker_fail", "attempts": None, "score": None})

    return pd.DataFrame(events)

def extract_features(df, args):
    if df.empty:
        return pd.DataFrame()

    starts = df[df['type'] == 'start'].groupby('problem').agg(
        total_starts=('type', 'count'),
        total_attempts=('attempts', 'sum')
    ).reset_index()
    
    successes = df[df['type'] == 'success'].groupby('problem').size().reset_index(name='total_successes')
    no_improves = df[df['type'] == 'no_improvement'].groupby('problem').size().reset_index(name='total_no_improvement')
    fails = df[df['type'] == 'fail'].groupby('problem').size().reset_index(name='total_fails')
    scores = df[df['type'] == 'score'].groupby('problem')['score'].agg(
        best_score='min',
        avg_score='mean'
    ).reset_index()
    
    agg_df = pd.merge(starts, successes, on='problem', how='left')
    agg_df = pd.merge(agg_df, no_improves, on='problem', how='left')
    agg_df = pd.merge(agg_df, fails, on='problem', how='left')
    agg_df = pd.merge(agg_df, scores, on='problem', how='left')
    
    agg_df['total_successes'] = agg_df['total_successes'].fillna(0)
    agg_df['total_no_improvement'] = agg_df['total_no_improvement'].fillna(0)
    agg_df['total_fails'] = agg_df['total_fails'].fillna(0)
    agg_df['success_rate'] = agg_df['total_successes'] / agg_df['total_starts']
    
    def parse_prob(p):
        parts = str(p).split('_')
        if len(parts) >= 4 and parts[2] == 'in':
            try:
                n = int(parts[0])
            except ValueError:
                n = None
            return pd.Series([n, parts[1], parts[3], f"{parts[1]}_in_{parts[3]}"])
        return pd.Series([None, None, None, p])
        
    agg_df[['N', 'inner_sides', 'container_sides', 'problem_family']] = agg_df['problem'].apply(parse_prob)

    # Apply CLI filters
    if args.min_runs > 1:
        agg_df = agg_df[agg_df['total_starts'] >= args.min_runs]
    if args.family:
        agg_df = agg_df[agg_df['problem_family'].str.lower() == args.family.lower()]
    if args.min_n is not None:
        agg_df = agg_df[agg_df['N'] >= args.min_n]
    if args.max_n is not None:
        agg_df = agg_df[agg_df['N'] <= args.max_n]

    return agg_df

def generate_charts(agg_df, df, output_dir="analysis", top_n=15):
    os.makedirs(output_dir, exist_ok=True)
    plt.style.use('ggplot')

    # Chart 1: Top Most Frequently Run Problems
    top_runs = agg_df.sort_values('total_starts', ascending=False).head(top_n)
    plt.figure(figsize=(10, 6))
    plt.bar(top_runs['problem'], top_runs['total_starts'], color='#3498db', edgecolor='black')
    plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.title(f'Top {top_n} Most Frequently Run Problems', fontsize=14, fontweight='bold')
    plt.xlabel('Problem Name')
    plt.ylabel('Total Execution Runs')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_problems.png'), dpi=ANALYSIS_PLOT_DPI)
    plt.close()

    # Chart 2: Top Problem Families (Donut Chart)
    fam_runs = agg_df.groupby('problem_family')['total_starts'].sum().sort_values(ascending=False).head(10)
    plt.figure(figsize=(8, 8))
    colors = plt.cm.Paired(np.linspace(0, 1, len(fam_runs)))
    plt.pie(fam_runs, labels=fam_runs.index, autopct='%1.1f%%', startangle=140, colors=colors, wedgeprops=dict(width=0.4, edgecolor='w'))
    plt.title('Top Problem Families Distribution', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'family_distribution.png'), dpi=ANALYSIS_PLOT_DPI)
    plt.close()

    # Chart 3: N vs Success Rate Scatter Plot with Trend Line
    valid = agg_df.dropna(subset=['N'])
    if not valid.empty:
        plt.figure(figsize=(10, 6))
        plt.scatter(valid['N'], valid['success_rate'] * 100, alpha=0.6, color='#9b59b6', edgecolors='k', s=60)
        
        # Fit trend line if enough points
        if len(valid) > 2:
            z = np.polyfit(valid['N'], valid['success_rate'] * 100, 1)
            p = np.poly1d(z)
            x_seq = np.linspace(valid['N'].min(), valid['N'].max(), 100)
            plt.plot(x_seq, p(x_seq), "r--", alpha=0.8, label=f"Trend (slope: {z[0]:.2f}%/N)")
            plt.legend()

        plt.title('Problem Size (N) vs. Success Rate', fontsize=14, fontweight='bold')
        plt.xlabel('N (Number of Inner Shapes)')
        plt.ylabel('Success Rate (%)')
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'n_vs_success.png'), dpi=ANALYSIS_PLOT_DPI)
        plt.close()

    # Chart 4: Best Score Scaling per Problem Family
    top_families = agg_df.groupby('problem_family')['total_starts'].sum().nlargest(5).index
    fam_valid = agg_df[agg_df['problem_family'].isin(top_families)].dropna(subset=['N', 'best_score'])
    if not fam_valid.empty:
        plt.figure(figsize=(10, 6))
        for family, group in fam_valid.groupby('problem_family'):
            sorted_g = group.sort_values('N')
            plt.plot(sorted_g['N'], sorted_g['best_score'], marker='o', label=family, linewidth=2)
        plt.title('Best Objective Score Scaling vs N (Top Families)', fontsize=14, fontweight='bold')
        plt.xlabel('N (Number of Inner Shapes)')
        plt.ylabel('Best Objective Score (Lower is Better)')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'score_by_family.png'), dpi=ANALYSIS_PLOT_DPI)
        plt.close()

    # Chart 5: Attempts Distribution Requested
    start_events = df[df['type'] == 'start']
    if not start_events.empty:
        plt.figure(figsize=(9, 5))
        counts = start_events['attempts'].value_counts().sort_index()
        counts.plot(kind='bar', color='#2ecc71', edgecolor='black')
        plt.title('Requested Search Attempts Per Run Distribution', fontsize=14, fontweight='bold')
        plt.xlabel('Attempts Requested')
        plt.ylabel('Frequency')
        plt.xticks(rotation=0)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'attempts_distribution.png'), dpi=ANALYSIS_PLOT_DPI)
        plt.close()

def write_report(agg_df, df, log_file, output_dir="analysis", top_n=15):
    os.makedirs(output_dir, exist_ok=True)
    
    total_problems = len(agg_df)
    total_starts = agg_df['total_starts'].sum()
    total_successes = int(agg_df['total_successes'].sum())
    total_attempts_calc = agg_df['total_attempts'].sum()
    overall_success = total_successes / total_starts if total_starts > 0 else 0
    unique_families = agg_df['problem_family'].nunique()
    
    # General score statistics
    scores_valid = agg_df['best_score'].dropna()
    mean_score = scores_valid.mean() if not scores_valid.empty else 0
    median_score = scores_valid.median() if not scores_valid.empty else 0
    min_score = scores_valid.min() if not scores_valid.empty else 0
    max_score = scores_valid.max() if not scores_valid.empty else 0

    md = f"""# Advanced Shape Packing Log Analysis Report

**Target Log File:** `{log_file}`  
**Generated On:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}`

---

## 1. High-Level Executive Summary

| Metric | Value |
| :--- | :--- |
| **Total Unique Problems Evaluated** | `{total_problems}` |
| **Total Parallel Runs Executed** | `{total_starts}` |
| **Total Solver Attempts Requested** | `{total_attempts_calc:,.0f}` |
| **Total Successful Improvements** | `{total_successes}` |
| **Overall Success Rate** | `{overall_success:.2%}` |
| **Distinct Problem Families** | `{unique_families}` |

### Global Objective Score Statistics
- **Minimum Score (Best Found):** `{min_score:.6f}`
- **Mean Best Score:** `{mean_score:.6f}`
- **Median Best Score:** `{median_score:.6f}`
- **Maximum Best Score:** `{max_score:.6f}`

---

## 2. Visual Analytics & Charts

### A. Most Frequently Run Problems
![Top Problems](top_problems.png)

### B. Problem Family Workload Distribution
![Problem Families](family_distribution.png)

### C. Scaling & Difficulty: Problem Size (N) vs. Success Rate
![N vs Success](n_vs_success.png)

### D. Objective Score Growth Across Shapes (N)
![Score by Family](score_by_family.png)

### E. Distribution of Search Attempts Requested Per Run
![Attempts Distribution](attempts_distribution.png)

---

## 3. Problem Family Breakdown

Aggregated metrics across shape categories:

| Family | Total Problems | Total Runs | Total Compute Attempts | Avg Success Rate | Best Score Range |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

    family_summary = agg_df.groupby('problem_family').agg(
        prob_count=('problem', 'count'),
        total_runs=('total_starts', 'sum'),
        sum_attempts=('total_attempts', 'sum'),
        avg_success=('success_rate', 'mean'),
        min_score=('best_score', 'min'),
        max_score=('best_score', 'max')
    ).sort_values('total_runs', ascending=False)

    for fam, row in family_summary.iterrows():
        b_range = f"{row['min_score']:.3f} - {row['max_score']:.3f}" if pd.notnull(row['min_score']) else "N/A"
        md += f"| **{fam}** | {row['prob_count']} | {row['total_runs']} | {row['sum_attempts']:,.0f} | {row['avg_success']:.1%} | {b_range} |\n"

    md += f"""
---

## 4. Top {top_n} Best Improvements (Lowest Score)

The best packing density configurations discovered during execution:

| Problem | Family | N | Total Runs | Success Rate | Best Score | Avg Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    best_df = agg_df.dropna(subset=['best_score']).sort_values('best_score').head(top_n)
    for _, row in best_df.iterrows():
        md += f"| `{row['problem']}` | `{row['problem_family']}` | {row['N']} | {row['total_starts']} | {row['success_rate']:.1%} | **{row['best_score']:.6f}** | {row['avg_score']:.6f} |\n"

    md += f"""
---

## 5. Highest Volume Problems (Most Compute Workload)

Problems consuming the most total search iterations:

| Problem | Total Runs | Total Attempts | Success Rate | Best Score |
| :--- | :--- | :--- | :--- | :--- |
"""
    vol_df = agg_df.sort_values('total_attempts', ascending=False).head(top_n)
    for _, row in vol_df.iterrows():
        b_score = f"{row['best_score']:.6f}" if pd.notnull(row['best_score']) else "N/A"
        md += f"| `{row['problem']}` | {row['total_starts']} | {row['total_attempts']:,.0f} | {row['success_rate']:.1%} | {b_score} |\n"

    md += f"""
---

## 6. Hardest Problems (Lowest Success Rates)

Problems with the lowest ratio of successful improvements:

| Problem | Total Runs | Successes | Success Rate | Best Score |
| :--- | :--- | :--- | :--- | :--- |
"""
    hard_df = agg_df.sort_values(['success_rate', 'total_starts'], ascending=[True, False]).head(top_n)
    for _, row in hard_df.iterrows():
        b_score = f"{row['best_score']:.6f}" if pd.notnull(row['best_score']) else "N/A"
        md += f"| `{row['problem']}` | {row['total_starts']} | {int(row['total_successes'])} | {row['success_rate']:.1%} | {b_score} |\n"

    with open(os.path.join(output_dir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(md)

def main():
    args = parse_args()
    log_file = args.log_file or find_latest_log()
    print(f"[Analyzer] Processing log file: {log_file}")
    
    df = parse_log(log_file)
    if df.empty:
        print("[Analyzer] Error: Parsed log file is empty or contains no recognized event patterns.")
        return

    agg_df = extract_features(df, args)
    if agg_df.empty:
        print("[Analyzer] Warning: No problem records matched the given filters.")
        return

    print(f"[Analyzer] Extracted {len(agg_df)} unique problem records matching criteria.")
    generate_charts(agg_df, df, output_dir=args.output_dir, top_n=args.top_n)
    write_report(agg_df, df, log_file, output_dir=args.output_dir, top_n=args.top_n)
    print(f"[Analyzer] Report & visualizations generated successfully in '{args.output_dir}/'.")

if __name__ == "__main__":
    main()
