# CAG Stress Report

Generated from `evals/stress/results.csv`.

## Summary

| scenario | attachment_kb | p50_latency_ms | p95_latency_ms | total_cost_usd | exact_cache_hit_rate | semantic_cache_hit_rate | mean_memory_drift |
| --- | --- | --- | --- | --- | --- | --- | --- |
| growing | 0 | 7457 | 15747 | 0.0000 | 0.00 | 0.00 | 0.00 |

## Curve 1 — latency_ms vs tokens_in

| tokens_in | latency_ms | scenario_name | turn_index |
| --- | --- | --- | --- |
| 2516 | 16668 | growing | 1 |
| 3299 | 7457 | growing | 2 |
| 3388 | 6757 | growing | 3 |

## Curve 2 — cumulative cost_usd vs turn_index

| scenario_name | turn_index | cumulative_cost_usd |
| --- | --- | --- |
| growing | 1 | 0.0000 |
| growing | 2 | 0.0000 |
| growing | 3 | 0.0000 |

## Curve 3 — mean memory drift vs N (turn count)

| scenario_turn_count | mean_memory_drift_score | rows |
| --- | --- | --- |
| 3 | 0.00 | 3 |

## Interpretation

Across 3 observed turns, mean memory drift is 0.00 and recall falls below 0.60 from turn 1 onward in this run. P95 latency reaches 15747 ms while per-turn cost spreads up to 0.0x between the cheapest and most expensive turn.

The dominant degradation dimension in this dataset is latency. Total observed spend is $0.0000 with semantic cache hits at 0.00. A RAG boundary is justified when turn depth routinely exceeds the window while memory drift stays under 0.60 at N>=1 despite stable latency budgets.
