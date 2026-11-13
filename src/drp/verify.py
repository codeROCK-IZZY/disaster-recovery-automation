"""Which backups to test-restore this week, and what that does to the next disaster.

Every policy gets the same capacity: `capacity` restore tests a week across the whole estate.
- `status_only`: trust the backup job's "succeeded" status; never test a restore.
- `random`: test `capacity` random systems a week.
- `round_robin`: test the systems verified longest ago.
- `risk` (this platform): score each system by its tier, the weeks since it was last verified, whether its encryption
  key was rotated since then, and how close its projected restore time is to its recovery time objective; test the
  highest scores. These are things a platform knows (rotations are logged; data size and restore throughput are
  measured), not the hidden state of the backups.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .estate import TIER_RPO_H, TIER_WEIGHT, WEEKS, Break, Estate

FIX_WEEKS = 2 / 7
KEY_RECOVERY_H = 24.0
POLICIES = ("status_only", "random", "round_robin", "risk")


@dataclass(frozen=True)
class Weights:
    rotation: float = 2.0  # extra weight when the key was rotated since the last verified restore
    near_rto: float = 3.0  # extra weight as the projected restore time approaches the RTO


@dataclass
class Outcome:
    restores: int = 0
    ok: int = 0
    rpo_breach: int = 0  # had to go back to an older backup: data lost beyond the RPO
    rto_breach: int = 0  # restored, but later than the RTO
    tier1_failures: int = 0


def score_parts(est: Estate, name: str, t: float, last: float, w: Weights | None = None) -> dict[str, float]:
    """The risk score and what it is made of (all things the platform knows)."""
    w = w or Weights()
    s = est.systems[name]
    rotated = any(last < r <= t for r in s.rotation_weeks)
    projected = s.restore_minutes(min(int(t) + 4, WEEKS - 1)) / s.rto
    score = (
        TIER_WEIGHT[s.tier] * (t - last + 1) * (1 + w.rotation * rotated) * (1 + w.near_rto * max(projected - 0.7, 0))
    )
    return {
        "score": score,
        "weeks_since_verified": t - last,
        "key_rotated": float(rotated),
        "projected_restore_vs_rto": projected,
    }


def _score(est: Estate, name: str, t: float, last: float, w: Weights) -> float:
    return score_parts(est, name, t, last, w)["score"]


@dataclass
class Run:
    est: Estate
    last: dict[str, float]
    outcome: Outcome
    log: list[dict[str, Any]] = field(default_factory=list)


def choose(run: Run, policy: str, t: float, capacity: int, w: Weights, g: np.random.Generator) -> list[str]:
    names = list(run.est.systems)
    if policy == "random":
        return [str(x) for x in g.choice(names, size=capacity, replace=False)]
    if policy == "round_robin":
        return sorted(names, key=lambda n: run.last[n])[:capacity]
    if policy == "risk":
        return sorted(names, key=lambda n: -_score(run.est, n, t, run.last[n], w))[:capacity]
    return []


def replay(
    estate: Estate, policy: str, capacity: int = 6, w: Weights | None = None, seed: int = 0, until: int = WEEKS
) -> Run:
    """Run the year (or up to week `until`) and keep the state and an event log."""
    w = w or Weights()
    est = copy.deepcopy(estate)
    g = np.random.default_rng(seed)
    run = Run(est, {n: -float(g.uniform(0, 26)) for n in est.systems}, Outcome())  # last verified before the year
    disasters = list(est.disasters)
    for week in range(until):
        t = week + 0.5
        while disasters and disasters[0][0] < t:  # disasters before this week's tests
            _disaster(run, *disasters.pop(0))
        for name in choose(run, policy, t, capacity, w, g):
            found = est.open_breaks(name, t)
            for b in found:
                b.found, b.fixed = t, t + FIX_WEEKS
            run.last[name] = t
            run.log.append({"t": t, "kind": "test", "system": name, "found": sorted(b.mode for b in found)})
        while disasters and disasters[0][0] < week + 1:
            _disaster(run, *disasters.pop(0))
    return run


def simulate(estate: Estate, policy: str, capacity: int = 6, w: Weights | None = None, seed: int = 0) -> dict[str, Any]:
    run = replay(estate, policy, capacity, w, seed)
    return _summary(run.est, run.outcome)


def _disaster(run: Run, t: float, hit: list[str]) -> None:
    est, out = run.est, run.outcome
    for name in hit:
        s = est.systems[name]
        out.restores += 1
        problems = est.open_breaks(name, t)
        modes = {b.mode for b in problems}
        rpo_lost_h = max(
            ((t - b.start) * 7 * 24 for b in problems if b.mode in ("corruption", "chain_broken")), default=0.0
        )
        late = "too_slow" in modes or "key_missing" in modes
        if rpo_lost_h > TIER_RPO_H[s.tier]:
            out.rpo_breach += 1
        if late:
            out.rto_breach += 1
        if not problems:
            out.ok += 1
        elif s.tier == 1:
            out.tier1_failures += 1
        for b in problems:  # a disaster finds them the hard way
            b.found, b.fixed = t, t + FIX_WEEKS
        run.log.append({"t": t, "kind": "disaster", "system": name, "found": sorted(modes)})


def _summary(est: Estate, out: Outcome) -> dict[str, Any]:
    undetected = []
    for b in est.breaks:
        end = b.found if b.found is not None else WEEKS
        if end > b.start:
            undetected.append((end - b.start) * 7)
    return {
        "silent_failures": len(est.breaks),
        "mean_days_undetected": round(float(np.mean(undetected)) if undetected else 0.0, 1),
        "found_by_tests": sum(1 for b in est.breaks if b.found is not None and b.found == b.found and _by_test(b)),
        "disaster_restores": out.restores,
        "restored_cleanly": out.ok,
        "rpo_breaches": out.rpo_breach,
        "rto_breaches": out.rto_breach,
        "tier1_failed_restores": out.tier1_failures,
    }


def _by_test(b: Break) -> bool:
    # tests happen at the middle of a week; disasters at any other time
    return b.found is not None and abs(b.found - int(b.found) - 0.5) < 1e-9
