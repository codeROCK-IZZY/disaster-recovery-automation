# Known limitations

- **Simulated estates.** Failure rates, data growth, restore throughput and disasters are generated. The policies
  would need tuning against a real estate's restore-test history before the weights mean anything.
- **A restore test finds everything.** In the simulation, one restore test finds every problem a system has.
  Real tests can miss partial corruption or a problem that only shows under load.
- **Risk-based testing depends on what fails.** On the held-back estate with more corruption and fewer key
  failures, it only tied round robin on tier 1 and lost on data loss (ADR 1). It has no signal that predicts corruption.
- **The manual baseline is a model** (one operator, fixed overhead, a fixed error rate). Real teams work in parallel,
  so the gap between orchestrated and manual recovery is overstated (ADR 2).
- **Recovery assumes infinite room in the recovery region.** It also ignores network limits shared between parallel
  restores and partial failures during a restore. Parallelism is a fixed 6.
- **Point-in-time recovery is not modelled.** RPO breaches are counted when a restore has to go back past a corrupt
  or broken backup, but choosing a restore point is not part of the plan.
- **Runbook conversion is not evaluated for accuracy.** The checks catch unknown systems, invented steps and unsafe
  order, but there is no labelled set of real runbooks to measure how often Claude misreads one (ADR 3).
- **The console is a demo.** It is in memory with one estate at week 30, has no authentication, and runs no real
  restores.
