import os
import re
import pandas as pd
import numpy as np

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

def extract_features(df):
    starts = df[df['type'] == 'start'].groupby('problem').size().reset_index(name='total_starts')
    successes = df[df['type'] == 'success'].groupby('problem').size().reset_index(name='total_successes')
    scores = df[df['type'] == 'score'].groupby('problem')['score'].min().reset_index(name='best_score')
    
    agg_df = pd.merge(starts, successes, on='problem', how='left')
    agg_df = pd.merge(agg_df, scores, on='problem', how='left')
    agg_df['total_successes'] = agg_df['total_successes'].fillna(0)
    agg_df['success_rate'] = agg_df['total_successes'] / agg_df['total_starts']
    
    def parse_prob(p):
        parts = p.split('_')
        if len(parts) >= 4 and parts[2] == 'in':
            try:
                n = int(parts[0])
            except ValueError:
                n = None
            return pd.Series([n, parts[1], parts[3], f"{parts[1]}_in_{parts[3]}"])
        return pd.Series([None, None, None, p])
        
    agg_df[['N', 'inner_sides', 'container_sides', 'problem_family']] = agg_df['problem'].apply(parse_prob)
    return agg_df

if __name__ == "__main__":
    df = parse_log("results/mill-2330986.out")
    agg_df = extract_features(df)
    print(agg_df.head())
    print(f"Total unique problems: {len(agg_df)}")
