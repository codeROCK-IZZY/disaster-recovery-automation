# Automated disaster recovery: evaluation

Simulated estates over a year: backups that silently stop being restorable, a fixed number of restore tests a week, and region outages that force restores.

## Tuning estates: 10 estates of 60 systems, 6 tests a week, 970 silent failures, 65 disasters

| Testing | Days a broken backup goes unnoticed | Found by tests | Restores in disasters | Clean | RPO breaches | RTO breaches | Tier-1 restores that failed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trust the job status | 93.3 | 0 | 1,300 | 850 | 128 | 383 | 110 |
| Random restore tests | 39.8 | 611 | 1,300 | 1,067 | 46 | 202 | 64 |
| Round robin | 29.5 | 706 | 1,300 | 1,116 | 37 | 151 | 45 |
| Risk-based (this platform) | 28.1 | 735 | 1,300 | 1,139 | 40 | 127 | 24 |

Recovery (310 tier-1 restores): orchestrated 61.9% within RTO, everything back in a median 31.3 h; manual runbook 10.6%, 136.7 h.

## Held-out estates: 30 estates of 60 systems, 6 tests a week, 2,918 silent failures, 187 disasters

| Testing | Days a broken backup goes unnoticed | Found by tests | Restores in disasters | Clean | RPO breaches | RTO breaches | Tier-1 restores that failed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trust the job status | 95.3 | 0 | 3,740 | 2,434 | 397 | 1056 | 331 |
| Random restore tests | 39.8 | 1,829 | 3,740 | 3,094 | 177 | 505 | 172 |
| Round robin | 28.8 | 2,134 | 3,740 | 3,222 | 144 | 389 | 127 |
| Risk-based (this platform) | 26.5 | 2,193 | 3,740 | 3,276 | 135 | 342 | 80 |

Recovery (942 tier-1 restores): orchestrated 65.4% within RTO, everything back in a median 31.9 h; manual runbook 8.5%, 132.9 h.

## Different estate (held back): 10 estates of 120 systems, 8 tests a week, 1,897 silent failures, 58 disasters

| Testing | Days a broken backup goes unnoticed | Found by tests | Restores in disasters | Clean | RPO breaches | RTO breaches | Tier-1 restores that failed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trust the job status | 99.5 | 0 | 2,320 | 1,577 | 412 | 461 | 190 |
| Random restore tests | 52.5 | 967 | 2,320 | 1,869 | 238 | 265 | 123 |
| Round robin | 39.6 | 1,229 | 2,320 | 1,965 | 178 | 201 | 86 |
| Risk-based (this platform) | 39.2 | 1,220 | 2,320 | 1,947 | 202 | 194 | 80 |

Recovery (582 tier-1 restores): orchestrated 55.7% within RTO, everything back in a median 56.3 h; manual runbook 6.5%, 281.2 h.

## Gate (regression limits, not targets)

- PASS heldout_tier1_failures_vs_status_max: 0.242 (limit 0.35)
- PASS heldout_tier1_failures_vs_round_robin_max: 0.63 (limit 0.8)
- PASS different_tier1_failures_vs_round_robin_max: 0.93 (limit 1.05)
- PASS heldout_tier1_within_rto_min: 0.654 (limit 0.55)
