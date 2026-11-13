"""The simulated estate, restore-test policies, recovery orchestration and runbook checks."""

from __future__ import annotations

from drp.estate import WEEKS, Estate
from drp.orchestrate import manual, plan, wave_plan, waves
from drp.runbook import PlanStep, check
from drp.verify import POLICIES, replay, score_parts, simulate


def test_estate_is_deterministic_and_has_every_failure_mode() -> None:
    a, b = Estate(3), Estate(3)
    assert [(x.system, x.mode, x.start) for x in a.breaks] == [(x.system, x.mode, x.start) for x in b.breaks]
    modes = {x.mode for s in range(1, 6) for x in Estate(s).breaks}
    assert modes == {"corruption", "key_missing", "chain_broken", "too_slow"}
    for s in a.systems.values():
        assert all(d in a.systems and d != s.name for d in s.depends_on)


def test_too_slow_starts_when_the_restore_outgrows_the_rto() -> None:
    est = Estate(5)
    for b in (x for x in est.breaks if x.mode == "too_slow"):
        s = est.systems[b.system]
        w = int(b.start)
        assert s.restore_minutes(w) > s.rto and (w == 0 or s.restore_minutes(w - 1) <= s.rto)


def test_trusting_the_job_status_never_finds_anything_before_a_disaster() -> None:
    r = simulate(Estate(2), "status_only")
    assert r["found_by_tests"] == 0
    assert r["restored_cleanly"] < r["disaster_restores"]


def test_every_policy_runs_the_same_number_of_tests() -> None:
    for p in POLICIES[1:]:
        run = replay(Estate(4), p, capacity=6)
        assert sum(x["kind"] == "test" for x in run.log) == 6 * WEEKS


def test_risk_score_rises_with_tier_age_rotation_and_restore_time() -> None:
    est = Estate(1)
    t1 = next(n for n, s in est.systems.items() if s.tier == 1)
    t3 = next(n for n, s in est.systems.items() if s.tier == 3)
    est.systems[t1].rotation_weeks = set()
    est.systems[t3].rotation_weeks = set()
    assert score_parts(est, t1, 10.5, 5.5)["score"] > score_parts(est, t3, 10.5, 5.5)["score"]
    assert score_parts(est, t1, 10.5, 0.5)["score"] > score_parts(est, t1, 10.5, 9.5)["score"]
    plain = score_parts(est, t1, 10.5, 5.5)
    est.systems[t1].rotation_weeks = {8}
    rotated = score_parts(est, t1, 10.5, 5.5)
    assert rotated["key_rotated"] == 1 and rotated["score"] > plain["score"]
    est.systems[t1].size_gb *= 3  # a restore now close to (or past) the RTO
    assert score_parts(est, t1, 10.5, 5.5)["score"] > rotated["score"]


def test_risk_based_tests_beat_status_on_tier_one() -> None:
    est = [Estate(s) for s in (1, 2, 3)]
    risk = sum(simulate(e, "risk")["tier1_failed_restores"] for e in est)
    status = sum(simulate(e, "status_only")["tier1_failed_restores"] for e in est)
    assert risk < status


def test_plan_respects_dependencies_and_parallelism() -> None:
    est = Estate(7)
    hit = sorted(est.systems)[:30]
    rec = plan(est, hit, 10, parallel=4)
    done = {s.system: s for s in rec.steps}
    assert set(done) == set(hit)
    for s in rec.steps:
        for d in est.systems[s.system].depends_on:
            if d in done:
                assert done[d].end <= s.start + 1e-9
    for s in rec.steps:  # never more than 4 running at once
        assert sum(1 for x in rec.steps if x.start <= s.start < x.end) <= 4


def test_plan_is_never_slower_than_waves_and_beats_manual() -> None:
    est = Estate(8)
    hit = sorted(est.systems)
    assert plan(est, hit, 20).total <= wave_plan(est, hit, 20).total
    assert plan(est, hit, 20).total < manual(est, hit, 20).total


def test_waves_put_dependencies_first() -> None:
    est = Estate(9)
    level = {s: i for i, w in enumerate(waves(est, list(est.systems))) for s in w}
    for name, s in est.systems.items():
        assert all(level[d] < level[name] for d in s.depends_on)


def test_runbook_check_catches_unknown_systems_bad_order_and_invented_quotes() -> None:
    est = Estate(42)
    top = next(n for n in sorted(est.systems) if len(est.systems[n].depends_on) == 2)
    a, b = est.systems[top].depends_on
    text = f"Restore {a}. Restore {b}. Restore {top}. Restore old-billing."
    good = [
        PlanStep(1, a, "restore_backup", (), f"Restore {a}"),
        PlanStep(2, b, "restore_backup", (), f"Restore {b}"),
        PlanStep(3, top, "restore_backup", (1, 2), f"Restore {top}"),
    ]
    assert check(est, good, text) == []
    bad = [
        PlanStep(1, a, "restore_backup", (), f"Restore {a}"),
        PlanStep(2, b, "restore_backup", (), f"Restore {b}"),
        PlanStep(3, top, "restore_backup", (1, 9), f"Restore {top} quickly"),
        PlanStep(4, "old-billing", "reboot", (), "Restore old-billing"),
    ]
    problems = " | ".join(check(est, bad, text))
    assert "old-billing is not in the inventory" in problems
    assert "reboot is not an action" in problems
    assert "step 9, which does not exist" in problems
    assert "its quote is not in the runbook" in problems
    assert f"without waiting for {b}" in problems


def test_runbook_check_follows_waits_transitively() -> None:
    est = Estate(42)
    top = next(n for n in sorted(est.systems) if len(est.systems[n].depends_on) == 1)
    (dep,) = est.systems[top].depends_on
    text = f"Restore {dep}. Check it. Restore {top}."
    steps = [
        PlanStep(1, dep, "restore_backup", (), f"Restore {dep}"),
        PlanStep(2, dep, "verify_restore", (1,), "Check it"),
        PlanStep(3, top, "restore_backup", (2,), f"Restore {top}"),
    ]
    assert check(est, steps, text) == []
