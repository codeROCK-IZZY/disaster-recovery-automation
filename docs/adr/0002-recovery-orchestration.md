# 2. Recover by priority scheduling over the dependency graph

## Context

When a zone or region goes, a third of the estate or more must be restored from backup. Runbooks list systems team
by team, and people work through them one step at a time. A system restored before the database it needs either
fails its checks or waits, and someone has to go back.

## Decision

Restore in dependency order, up to 6 at once:

- A restore starts as soon as everything it depends on is back and has passed its automatic check (checksums and a
  smoke test, 5 minutes).
- Among the restores that are ready, the most important start first. Anything a tier-1 system depends on inherits
  tier 1's priority, so a tier-3 queue that the payments API needs is not left until last.
- Shorter restores go first within a priority, so lanes free up sooner.
- Dependency cycles are broken at the most important system.

The first version restored in whole waves: all systems with no outstanding dependencies, then the next level, and so
on. On the tuning estates both versions got the same share of tier-1 systems back within their RTO (61.9%). But
waves made every restore wait for the slowest one in its level, so everything took 40% longer (a median of 45 hours
against 31). Priority scheduling replaced it. Waves are still shown as "dependency levels" in the console.

## Consequences

- On held-out estates: 65.4% of tier-1 systems back within RTO against 8.5% for the manual runbook, and everything
  back in a median of 32 hours against 133.
- The manual baseline is a model: one operator, 12 minutes of overhead per step, an 8% chance a step is redone, and
  the runbook's order. Real teams work in parallel, so the real gap is smaller. The comparison shows what ordering and
  parallelism are worth, not a measured saving.
- A third of tier-1 systems still miss their RTO, because their full restore alone is close to it. No ordering fixes
  that. Those systems need faster recovery (snapshots, warm standbys), and the console flags them as restores
  projected near or past their RTO.
