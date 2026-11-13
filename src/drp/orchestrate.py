"""Recovering after a disaster: in what order to restore, how much at once, and how long it takes.

`plan` starts each restore as soon as everything it depends on is back, up to `parallel` at once, most important
first; anything a tier-1 system needs inherits tier 1's priority. Each restore is checked automatically (checksums
and a smoke test) before its dependants start. (`wave_plan`, which restores in whole dependency waves, was the first
version: the same share of tier-1 systems met their RTO on the tuning estates, but everything took 40% longer.)

`manual` is the runbook done by hand: the steps in the runbook's order (written by team, not by dependency), one at
a time, each with an operator's overhead, and a chance a step goes wrong and is redone; a system whose dependencies
are not back yet waits for them, which in practice means someone notices and goes back.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from .estate import Estate

CHECK_MIN = 5
OPERATOR_MIN = 12
MANUAL_ERROR = 0.08


@dataclass
class Step:
    system: str
    wave: int
    start: float
    end: float


@dataclass
class Recovery:
    steps: list[Step] = field(default_factory=list)

    @property
    def total(self) -> float:
        return max((s.end for s in self.steps), default=0.0)

    def done_at(self, system: str) -> float:
        return next(s.end for s in self.steps if s.system == system)


def waves(est: Estate, systems: list[str]) -> list[list[str]]:
    """Dependency order among `systems` (dependencies outside the set are assumed to be up)."""
    todo = set(systems)
    out: list[list[str]] = []
    done: set[str] = set()
    while todo:
        ready = sorted(
            (s for s in todo if all(d in done or d not in todo for d in est.systems[s].depends_on)),
            key=lambda s: (est.systems[s].tier, s),
        )
        if not ready:  # a cycle: break it at the most important system
            ready = [min(todo, key=lambda s: (est.systems[s].tier, s))]
        out.append(ready)
        done |= set(ready)
        todo -= set(ready)
    return out


def wave_plan(est: Estate, systems: list[str], week: int, parallel: int = 6) -> Recovery:
    rec = Recovery()
    t = 0.0
    for i, wave in enumerate(waves(est, systems)):
        lanes = [t] * min(parallel, len(wave))
        heapq.heapify(lanes)
        for s in wave:
            start = heapq.heappop(lanes)
            end = start + est.systems[s].restore_minutes(week) + CHECK_MIN
            rec.steps.append(Step(s, i, start, end))
            heapq.heappush(lanes, end)
        t = max(lanes)
    return rec


def plan(est: Estate, systems: list[str], week: int, parallel: int = 6) -> Recovery:
    """Restores start as soon as their dependencies are back, most important first; anything a tier-1 system needs
    inherits tier 1's priority."""
    chosen = set(systems)
    effective = {s: est.systems[s].tier for s in systems}
    changed = True
    while changed:  # push each system's tier down to what it depends on
        changed = False
        for s in systems:
            for d in est.systems[s].depends_on:
                if d in chosen and effective[d] > effective[s]:
                    effective[d] = effective[s]
                    changed = True
    done: dict[str, float] = {}
    running: list[tuple[float, str]] = []
    rec = Recovery()
    t = 0.0
    pending = set(systems)
    while pending or running:
        ready = sorted(
            (s for s in pending if all(d in done or d not in chosen for d in est.systems[s].depends_on)),
            key=lambda s: (effective[s], est.systems[s].restore_minutes(week)),
        )
        while ready and len(running) < parallel:
            s = ready.pop(0)
            end = t + est.systems[s].restore_minutes(week) + CHECK_MIN
            heapq.heappush(running, (end, s))
            rec.steps.append(Step(s, effective[s], t, end))
            pending.discard(s)
        if not running:  # only cycles left: start the most important one anyway
            s = min(pending, key=lambda x: (effective[x], x))
            end = t + est.systems[s].restore_minutes(week) + CHECK_MIN
            heapq.heappush(running, (end, s))
            rec.steps.append(Step(s, effective[s], t, end))
            pending.discard(s)
        t, s = heapq.heappop(running)
        done[s] = t
    return rec


def manual(est: Estate, systems: list[str], week: int, seed: int = 0) -> Recovery:
    g = np.random.default_rng(seed)
    order = sorted(systems)  # the runbook lists systems team by team, not by dependency
    rec = Recovery()
    t = 0.0
    finished: dict[str, float] = {}
    pending = list(order)
    while pending:
        progressed = False
        for s in list(pending):
            deps = [d for d in est.systems[s].depends_on if d in systems]
            if any(d not in finished for d in deps):
                continue
            duration = OPERATOR_MIN + est.systems[s].restore_minutes(week)
            if g.random() < MANUAL_ERROR:
                duration *= 2  # a step went wrong and was redone
            rec.steps.append(Step(s, 0, t, t + duration))
            t += duration
            finished[s] = t
            pending.remove(s)
            progressed = True
        if not progressed:  # waiting on something: someone notices and restores it out of order
            s = pending.pop(0)
            duration = OPERATOR_MIN * 2 + est.systems[s].restore_minutes(week)
            rec.steps.append(Step(s, 0, t, t + duration))
            t += duration
            finished[s] = t
    return rec
