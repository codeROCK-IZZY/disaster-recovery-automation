# 1. Spend restore tests where silent failures are likely and costly

## Context

A full restore test takes real time and capacity. The simulated estates allow 6 a week across 60 systems, so each
system gets tested about every ten weeks. Meanwhile backups break silently, and the job status never shows it. Which
systems should get this week's tests?

## Decision

Score every system each week and test the highest scores:

```
tier weight (4 / 2 / 1) x (weeks since the last verified restore + 1)
  x (1 + rotation weight if its encryption key rotated since then)
  x (1 + near-RTO weight x max(projected restore time in 4 weeks / RTO - 0.7, 0))
```

Every input is something a platform knows: tiers, the rotation log, and measured data size and restore throughput.
The score never looks at whether a backup is actually broken.

The two weights were chosen on the 10 tuning estates (failed tier-1 restores / RTO breaches / RPO breaches):

| rotation \ near-RTO | 0 | 1.5 | 3 | 6 |
|---|---|---|---|---|
| 0 | 29 / 175 / 49 | 27 / 173 / 46 | 32 / 185 / 52 | 29 / 186 / 46 |
| 1 | 28 / 146 / 39 | 25 / 140 / 43 | 23 / 152 / 47 | 24 / 155 / 47 |
| **2** | 26 / 132 / 39 | 25 / 125 / 40 | **24 / 127 / 40** | 28 / 144 / 50 |
| 4 | 32 / 145 / 44 | 34 / 146 / 43 | 32 / 142 / 43 | 30 / 141 / 45 |

Rotation 2 and near-RTO 3 were frozen. The rotation weight does most of the work: without it, RTO breaches go up by
about 40%, because a key missing in the recovery region is the commonest way a backup fails. The near-RTO weight
barely matters; 1.5 would have done as well.

## Consequences

- On 30 held-out estates: 80 failed tier-1 restores against 127 for round robin and 331 for trusting the job status.
- On a held-back estate of a different shape (more corruption, fewer key failures, 120 systems), the advantage
  disappears: 80 against 86 on tier 1, and more RPO breaches than round robin. The score knows nothing that predicts
  corruption, so it spends tests on rotations that rarely fail there. An estate whose failures look like that should
  lower the rotation weight or mix in round-robin slots. The gate allows risk-based testing to be up to 5% worse than
  round robin on that estate, so a change that made it clearly worse would fail CI.
