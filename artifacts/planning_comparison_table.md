| Method | Evaluated Cases | Task Success | Avg LLM Calls | Avg Tokens | Avg Latency | Avg Cost / Run |
|---|---:|---:|---:|---:|---:|---:|
| **Decomposition-First** | 7 | 5/7 (71.4%) | 1 | 260 | 96.401s | $0.000039 |
| **Dynamic Decomposition** | 7 | 7/7 (100.0%) | 3.9 | 610 | 18.018s | $0.000091 |
| **Plan-and-Solve** | 11 | 0/11 (0.0%) | 1 | 220 | 2.996s | $0.000033 |
| **Tree of Thoughts** | 11 | 0/11 (0.0%) | 16 | 952 | 29.646s | $0.000143 |
| **LATS (Ungrounded)** | 11 | 9/11 (81.8%) | 6 | 730 | 4.799s | $0.000109 |
| **LATS (Grounded)** | 11 | 6/11 (54.5%) | 7.1 | 901 | 12.124s | $0.000135 |
| **Self-Refine** | 4 | 2/4 (50.0%) | 3 | 904 | 16.561s | $0.000136 |
| **Reflexion** | 4 | 4/4 (100.0%) | 4.8 | 760 | 9.319s | $0.000114 |