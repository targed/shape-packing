# Advanced Shape Packing Log Analysis Report

**Target Log File:** `results/mill-2408269.out`  
**Generated On:** `2026-08-07 08:22:24`

---

## 1. High-Level Executive Summary

| Metric | Value |
| :--- | :--- |
| **Total Unique Problems Evaluated** | `391` |
| **Total Parallel Runs Executed** | `4277` |
| **Total Solver Attempts Requested** | `203,590,000` |
| **Total Successful Improvements** | `4246` |
| **Overall Success Rate** | `99.28%` |
| **Distinct Problem Families** | `20` |

### Global Objective Score Statistics
- **Minimum Score (Best Found):** `1.617633`
- **Mean Best Score:** `4.385470`
- **Median Best Score:** `4.139740`
- **Maximum Best Score:** `8.549801`

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
| **DOMINO_in_8** | 25.0 | 407.0 | 19,495,000 | 100.0% | 1.717 - 4.033 |
| **DOMINO_in_6** | 25.0 | 385.0 | 18,305,000 | 99.6% | 2.443 - 5.260 |
| **5_in_6** | 27.0 | 353.0 | 17,065,000 | 99.7% | 2.219 - 5.100 |
| **5_in_DOMINO** | 18.0 | 287.0 | 13,675,000 | 99.4% | 2.473 - 4.937 |
| **6_in_6** | 22.0 | 262.0 | 12,605,000 | 99.6% | 2.675 - 6.271 |
| **6_in_5** | 27.0 | 254.0 | 12,385,000 | 99.7% | 3.229 - 7.785 |
| **5_in_8** | 27.0 | 244.0 | 11,525,000 | 99.9% | 1.618 - 3.751 |
| **DOMINO_in_CIRCLE** | 12.0 | 218.0 | 10,900,000 | 99.8% | 2.692 - 3.998 |
| **8_in_8** | 26.0 | 200.0 | 9,325,000 | 99.9% | 2.707 - 6.157 |
| **5_in_5** | 19.0 | 184.0 | 8,975,000 | 99.7% | 3.079 - 5.677 |
| **DOMINO_in_5** | 26.0 | 177.0 | 8,175,000 | 100.0% | 2.807 - 6.432 |
| **8_in_5** | 16.0 | 170.0 | 8,050,000 | 99.8% | 4.349 - 8.550 |
| **8_in_DOMINO** | 14.0 | 166.0 | 7,850,000 | 99.8% | 4.288 - 8.368 |
| **6_in_8** | 16.0 | 166.0 | 8,075,000 | 99.8% | 2.183 - 3.921 |
| **8_in_CIRCLE** | 16.0 | 148.0 | 6,725,000 | 99.8% | 3.380 - 6.371 |
| **8_in_6** | 16.0 | 147.0 | 6,675,000 | 99.8% | 3.719 - 6.999 |
| **5_in_CIRCLE** | 20.0 | 147.0 | 6,630,000 | 100.0% | 2.033 - 4.130 |
| **6_in_DOMINO** | 16.0 | 146.0 | 6,625,000 | 99.7% | 3.249 - 6.070 |
| **6_in_CIRCLE** | 19.0 | 134.0 | 6,475,000 | 100.0% | 2.471 - 5.290 |
| **DOMINO_in_DOMINO** | 4.0 | 82.0 | 4,055,000 | 97.2% | 2.927 - 4.988 |

---

## 4. Top 15 Best Improvements (Lowest Score)

The best packing density configurations discovered during execution:

| Problem | Family | N | Total Runs | Success Rate | Best Score | Avg Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `5_5_in_8` | `5_in_8` | 5 | 5 | 100.0% | **1.617633** | 1.624128 |
| `5_DOMINO_in_8` | `DOMINO_in_8` | 5 | 5 | 100.0% | **1.716579** | 1.717568 |
| `6_DOMINO_in_8` | `DOMINO_in_8` | 6 | 5 | 100.0% | **1.753432** | 1.786361 |
| `6_5_in_8` | `5_in_8` | 6 | 5 | 100.0% | **1.780079** | 1.786998 |
| `7_5_in_8` | `5_in_8` | 7 | 5 | 100.0% | **1.823481** | 1.825611 |
| `8_5_in_8` | `5_in_8` | 8 | 5 | 100.0% | **1.959896** | 1.961365 |
| `7_DOMINO_in_8` | `DOMINO_in_8` | 7 | 9 | 100.0% | **2.005200** | 2.005871 |
| `5_5_in_CIRCLE` | `5_in_CIRCLE` | 5 | 5 | 100.0% | **2.032722** | 2.033645 |
| `9_5_in_8` | `5_in_8` | 9 | 5 | 100.0% | **2.095400** | 2.095801 |
| `7_6_in_8` | `6_in_8` | 7 | 5 | 100.0% | **2.182869** | 2.193989 |
| `9_DOMINO_in_8` | `DOMINO_in_8` | 9 | 6 | 100.0% | **2.198141** | 2.200006 |
| `10_5_in_8` | `5_in_8` | 10 | 5 | 100.0% | **2.211504** | 2.211747 |
| `5_5_in_6` | `5_in_6` | 5 | 5 | 100.0% | **2.219498** | 2.225980 |
| `6_5_in_CIRCLE` | `5_in_CIRCLE` | 6 | 6 | 100.0% | **2.231293** | 2.234130 |
| `7_5_in_CIRCLE` | `5_in_CIRCLE` | 7 | 5 | 100.0% | **2.294727** | 2.300444 |

---

## 5. Highest Volume Problems (Most Compute Workload)

Problems consuming the most total search iterations:

| Problem | Total Runs | Total Attempts | Success Rate | Best Score |
| :--- | :--- | :--- | :--- | :--- |
| `19_6_in_8` | 61 | 3,050,000 | 100.0% | 3.589726 |
| `10_8_in_CIRCLE` | 44 | 2,200,000 | 100.0% | 4.731911 |
| `9_5_in_6` | 41 | 2,050,000 | 97.6% | 2.876966 |
| `13_8_in_6` | 40 | 2,000,000 | 100.0% | 5.774077 |
| `29_5_in_6` | 40 | 2,000,000 | 97.5% | 4.929878 |
| `13_6_in_CIRCLE` | 39 | 1,950,000 | 100.0% | 3.832923 |
| `9_6_in_8` | 39 | 1,950,000 | 97.4% | 2.634111 |
| `10_8_in_5` | 39 | 1,950,000 | 97.4% | 6.308601 |
| `13_5_in_8` | 39 | 1,950,000 | 97.4% | 2.505254 |
| `16_5_in_DOMINO` | 38 | 1,900,000 | 97.4% | 4.299528 |
| `18_5_in_DOMINO` | 38 | 1,900,000 | 97.4% | 4.558841 |
| `19_5_in_DOMINO` | 38 | 1,900,000 | 100.0% | 4.686585 |
| `20_5_in_DOMINO` | 38 | 1,900,000 | 100.0% | 4.808766 |
| `20_8_in_DOMINO` | 38 | 1,900,000 | 100.0% | 8.089723 |
| `9_8_in_5` | 38 | 1,900,000 | 100.0% | 5.994171 |

---

## 6. Hardest Problems (Lowest Success Rates)

Problems with the lowest ratio of successful improvements:

| Problem | Total Runs | Successes | Success Rate | Best Score |
| :--- | :--- | :--- | :--- | :--- |
| `19_DOMINO_in_DOMINO` | 24 | 23 | 95.8% | 4.882630 |
| `20_DOMINO_in_DOMINO` | 26 | 25 | 96.2% | 4.988412 |
| `30_DOMINO_in_6` | 27 | 26 | 96.3% | 5.259854 |
| `24_DOMINO_in_6` | 28 | 27 | 96.4% | 4.721959 |
| `29_DOMINO_in_6` | 30 | 29 | 96.7% | 5.196323 |
| `11_DOMINO_in_DOMINO` | 31 | 30 | 96.8% | 3.827282 |
| `25_5_in_5` | 33 | 32 | 97.0% | 5.594858 |
| `27_5_in_6` | 33 | 32 | 97.0% | 4.731800 |
| `28_6_in_6` | 33 | 32 | 97.0% | 5.921583 |
| `31_6_in_5` | 33 | 32 | 97.0% | 7.648736 |
| `32_6_in_5` | 33 | 32 | 97.0% | 7.784901 |
| `19_8_in_CIRCLE` | 34 | 33 | 97.1% | 6.092400 |
| `22_5_in_5` | 34 | 33 | 97.1% | 5.278208 |
| `25_6_in_6` | 34 | 33 | 97.1% | 5.638356 |
| `26_8_in_8` | 34 | 33 | 97.1% | 5.751475 |
