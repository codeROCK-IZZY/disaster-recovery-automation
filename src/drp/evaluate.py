"""Evaluation: which restore tests catch broken backups before a disaster, and how fast recovery is orchestrated.

    drp evaluate [--gate] [--out DIR]

Banks of simulated estates, a year each:
- `dev` (seeds 1-10, 60 systems, 6 restore tests a week): the risk weights and the scheduling design were chosen here;
- `heldout` (seeds 101-130, same shape), run after freezing;
- `different` (seeds 201-210): 120 systems, 8 tests a week, twice the corruption and broken chains, fewer key
  failures, also run after freezing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .estate import Estate
from .orchestrate import manual, plan
from .verify import POLICIES, simulate

DIFFERENT = {"corruption": 0.008, "chain_broken": 0.006, "key_after_rotation": 0.15}
BANKS: dict[str, tuple[range, int, int, dict[str, float] | None]] = {
    "dev": (range(1, 11), 60, 6, None),
    "heldout": (range(101, 131), 60, 6, None),
    "different": (range(201, 211), 120, 8, DIFFERENT),
}


def estates(name: str) -> tuple[list[Estate], int]:
    seeds, n, cap, hazard = BANKS[name]
    return [Estate(s, n=n, hazard=hazard) if hazard else Estate(s, n=n) for s in seeds], cap


def bank(name: str) -> dict[str, Any]:
    es, cap = estates(name)
    out: dict[str, Any] = {
        "estates": len(es),
        "systems": len(es[0].systems),
        "tests_per_week": cap,
        "silent_failures": sum(len(e.breaks) for e in es),
        "disasters": sum(len(e.disasters) for e in es),
    }
    for p in POLICIES:
        rows = [simulate(e, p, capacity=cap) for e in es]
        out[p] = {
            k: (
                round(float(np.mean([r[k] for r in rows])), 1)
                if k == "mean_days_undetected"
                else int(sum(r[k] for r in rows))
            )
            for k in rows[0]
            if k != "silent_failures"
        }
    met = {"orchestrated": 0, "manual": 0}
    totals: dict[str, list[float]] = {"orchestrated": [], "manual": []}
    tier1 = 0
    for i, e in enumerate(es):
        for t, hit in e.disasters:
            o, m = plan(e, hit, int(t)), manual(e, hit, int(t), seed=i)
            totals["orchestrated"].append(o.total)
            totals["manual"].append(m.total)
            for x in hit:
                if e.systems[x].tier == 1:
                    tier1 += 1
                    met["orchestrated"] += o.done_at(x) <= e.systems[x].rto
                    met["manual"] += m.done_at(x) <= e.systems[x].rto
    out["recovery"] = {
        k: {
            "tier1_within_rto": round(met[k] / max(tier1, 1), 3),
            "median_hours_to_full_recovery": round(float(np.median(totals[k])) / 60, 1),
        }
        for k in met
    }
    out["recovery"]["tier1_restores"] = tier1
    return out


GATE: dict[str, float] = {
    "heldout_tier1_failures_vs_status_max": 0.35,
    "heldout_tier1_failures_vs_round_robin_max": 0.8,
    "different_tier1_failures_vs_round_robin_max": 1.05,
    "heldout_tier1_within_rto_min": 0.55,
}


def run() -> dict[str, Any]:
    banks = {b: bank(b) for b in BANKS}
    h, d = banks["heldout"], banks["different"]

    def ratio(x: dict[str, Any], a: str, b: str) -> float:
        return round(float(x[a]["tier1_failed_restores"]) / max(int(x[b]["tier1_failed_restores"]), 1), 3)

    checks = {
        "heldout_tier1_failures_vs_status_max": ratio(h, "risk", "status_only"),
        "heldout_tier1_failures_vs_round_robin_max": ratio(h, "risk", "round_robin"),
        "different_tier1_failures_vs_round_robin_max": ratio(d, "risk", "round_robin"),
        "heldout_tier1_within_rto_min": h["recovery"]["orchestrated"]["tier1_within_rto"],
    }
    passed = {k: (v <= GATE[k] if k.endswith("_max") else v >= GATE[k]) for k, v in checks.items()}
    return {"banks": banks, "checks": checks, "gate": GATE, "passed": passed, "ok": all(passed.values())}


def save(result: dict[str, Any], out: Path) -> None:
    from .report import html_report, markdown

    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    (out / "report.md").write_text(markdown(result), encoding="utf-8", newline="\n")
    (out / "report.html").write_text(html_report(result), encoding="utf-8", newline="\n")
