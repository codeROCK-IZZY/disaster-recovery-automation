"""A simulated estate: systems with recovery targets, backups that silently stop being restorable, and disasters.

Each week every system takes backups, and the backup job reports success whatever happens. Backups can silently
become unusable in four ways:
- `corruption`: a backup chain contains corrupt blocks (a restore with checksums finds it);
- `key_missing`: after a key rotation, the copy in the recovery region was not re-encrypted with a key that exists
  there (a restore in the recovery region finds it);
- `chain_broken`: a retention change deleted a base backup the incrementals depend on;
- `too_slow`: data grew until a full restore takes longer than the system's recovery time objective (RTO).
A restore test run on a system finds every problem it has at that moment; the problem is then fixed within two days.
Disasters (region outages) hit a random third of systems; each must be restored from backup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TIER_RTO_MIN = {1: 60, 2: 240, 3: 1440}
TIER_RPO_H = {1: 1, 2: 4, 3: 24}
TIER_WEIGHT = {1: 4.0, 2: 2.0, 3: 1.0}
MODES = ("corruption", "key_missing", "chain_broken", "too_slow")
WEEKS = 52


@dataclass
class System:
    name: str
    tier: int
    size_gb: float
    growth: float  # weekly
    throughput_gb_min: float
    depends_on: list[str]
    rotation_weeks: set[int]  # weeks with a key rotation

    @property
    def rto(self) -> int:
        return TIER_RTO_MIN[self.tier]

    def restore_minutes(self, week: int) -> float:
        return 10 + self.size_gb * (1 + self.growth) ** week / self.throughput_gb_min


@dataclass
class Break:
    system: str
    mode: str
    start: float  # week (fractional) it broke
    found: float | None = None  # week a restore test found it
    fixed: float | None = None


@dataclass
class Estate:
    seed: int
    n: int = 60
    hazard: dict[str, float] = field(
        default_factory=lambda: {"corruption": 0.004, "chain_broken": 0.003, "key_after_rotation": 0.25}
    )
    systems: dict[str, System] = field(default_factory=dict)
    breaks: list[Break] = field(default_factory=list)  # every silent failure that will happen this year
    disasters: list[tuple[float, list[str]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        g = np.random.default_rng(self.seed)
        names = []
        for i in range(self.n):
            tier = 1 if i < self.n // 4 else 2 if i < self.n * 2 // 3 else 3
            kind = str(g.choice(["db", "svc", "store", "queue", "api"]))
            names.append(f"{kind}-{i:02d}")
            rto = TIER_RTO_MIN[tier]
            throughput = float(g.uniform(2, 12))
            # size starting at 20-75% of what the RTO allows; some grow fast enough to outgrow it this year
            size = (rto - 10) * throughput * float(g.uniform(0.2, 0.75))
            growth = float(g.choice([0.002, 0.005, 0.01, 0.02]))
            rotations = {w for w in range(int(g.integers(0, 13)), WEEKS, 13)}
            deps = (
                [str(x) for x in g.choice(names[:-1], size=min(len(names) - 1, int(g.integers(0, 3))), replace=False)]
                if len(names) > 1
                else []
            )
            self.systems[names[-1]] = System(names[-1], tier, size, growth, throughput, deps, rotations)
        for s in self.systems.values():
            for week in range(WEEKS):
                for mode in ("corruption", "chain_broken"):
                    if g.random() < self.hazard[mode]:
                        self.breaks.append(Break(s.name, mode, week + float(g.random())))
                if week in s.rotation_weeks and g.random() < self.hazard["key_after_rotation"]:
                    self.breaks.append(Break(s.name, "key_missing", week + float(g.random())))
            over = next((w for w in range(WEEKS) if s.restore_minutes(w) > s.rto), None)
            if over is not None:
                self.breaks.append(Break(s.name, "too_slow", float(over)))
        for _ in range(int(g.poisson(6))):
            t = float(g.uniform(4, WEEKS))
            hit = [str(x) for x in g.choice(list(self.systems), size=self.n // 3, replace=False)]
            self.disasters.append((t, hit))
        self.disasters.sort()

    def open_breaks(self, system: str, t: float) -> list[Break]:
        """Problems a restore of `system` at time `t` would run into."""
        return [b for b in self.breaks if b.system == system and b.start <= t and (b.fixed is None or b.fixed > t)]
