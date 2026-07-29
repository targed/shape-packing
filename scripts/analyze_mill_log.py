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
