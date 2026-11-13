"""The DR console: this week's restore tests and why, every system's recoverability, rehearsed recoveries as a Gantt
chart against the manual runbook, and runbooks turned into checked plans."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .estate import TIER_RPO_H, Estate
from .orchestrate import Recovery, manual, plan, waves
from .runbook import Checked, Converter, PlanStep, check
from .verify import Run, Weights, replay, score_parts

e = html.escape
NOW = 30  # the demo console shows week 30 of the simulated year
CAPACITY = 6
SCENARIOS = {
    "zone-a": "Zone A outage",
    "zone-b": "Zone B outage",
    "zone-c": "Zone C outage",
    "everything": "Whole region lost",
}
TIER_COLOUR = {1: "#7aa2ff", 2: "#b48cff", 3: "#5fb3b3"}

CSS = """
:root{--bg:#0d1117;--panel:#151b24;--line:#263041;--ink:#e8edf4;--ink2:#97a3b6;--ok:#3ccf8e;--bad:#ff6b6b;--mid:#f5b54a;
--acc:#7aa2ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 Inter,system-ui,sans-serif}a{color:inherit}header{padding:14px 26px;border-bottom:1px solid var(--line);
display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}header b{font-size:17px}header nav a{color:var(--ink2);
text-decoration:none;margin-right:14px}main{padding:20px 26px 48px;max-width:1240px;margin:0 auto}.grid{display:grid;
grid-template-columns:repeat(4,1fr);gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:14px 16px}.card b{display:block;font-size:24px}.muted{color:var(--ink2)}table{width:100%;border-collapse:collapse;
background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}th,td{padding:7px 12px;
border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--ink2);font-weight:500;font-size:12px}
.b{display:inline-block;padding:1px 9px;border-radius:99px;font-size:11.5px;font-weight:600}.ok{background:#3ccf8e22;
color:var(--ok)}.warn{background:#f5b54a22;color:var(--mid)}.bad{background:#ff6b6b22;color:var(--bad)}
h1{font-size:22px;margin:0 0 4px}h2{font-size:13px;color:var(--ink2);text-transform:uppercase;letter-spacing:.05em;
margin:24px 0 8px}pre{background:#0f141c;border:1px solid var(--line);border-radius:10px;padding:12px;font-size:12.5px;
overflow:auto;white-space:pre-wrap}textarea{width:100%;min-height:180px;background:#0f141c;color:var(--ink);
border:1px solid var(--line);border-radius:8px;padding:10px;font:12.5px/1.5 ui-monospace,monospace}button{background:var(--acc);
color:#0b1020;border:0;border-radius:6px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}.num{text-align:right;
font-variant-numeric:tabular-nums}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}.tabs a{display:inline-block;
padding:5px 12px;border:1px solid var(--line);border-radius:99px;margin:0 6px 6px 0;text-decoration:none;color:var(--ink2)}
.tabs a.on{background:var(--acc);color:#0b1020;border-color:var(--acc)}.legend span{display:inline-flex;align-items:center;
gap:6px;margin-right:16px;color:var(--ink2);font-size:12.5px}.legend i{width:12px;height:12px;border-radius:3px;
display:inline-block}.scroll{overflow-x:auto}@media(max-width:900px){.grid,.cols{grid-template-columns:1fr 1fr}}
@media(max-width:560px){.grid,.cols{grid-template-columns:1fr}main{padding:16px}}
"""


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>{e(title)}</title><style>{CSS}</style><header><b>DR console</b><nav>"
        "<a href='/'>This week</a><a href='/systems'>Systems</a><a href='/recovery/zone-a'>Recovery rehearsal</a>"
        f"<a href='/runbook'>Runbooks</a></nav><span class='muted'>week {NOW} of the simulated year</span></header>"
        f"<main>{body}</main></html>"
    )


@dataclass
class Console:
    est: Estate
    run: Run
    converter: Converter | None = None

    @property
    def t(self) -> float:
        return NOW + 0.5

    def schedule(self) -> list[tuple[str, dict[str, float]]]:
        parts = {n: score_parts(self.run.est, n, self.t, self.run.last[n], Weights()) for n in self.est.systems}
        return sorted(parts.items(), key=lambda kv: -kv[1]["score"])[:CAPACITY]

    def scenario(self, key: str) -> list[str]:
        names = sorted(self.est.systems)
        if key == "everything":
            return names
        k = "abc".index(key[-1])
        return [n for i, n in enumerate(names) if i % 3 == k]

    def history(self, name: str) -> list[dict[str, Any]]:
        return [x for x in self.run.log if x["system"] == name]


def _gantt(est: Estate, rec: Recovery, scale_min: float, order: list[str], title: str) -> str:
    row, left, width = 18, 92, 860
    h = row * len(order) + 30
    px = width / max(scale_min, 1)
    out = [
        f"<svg viewBox='0 0 {left + width + 10} {h}' width='100%' role='img' aria-label='{e(title)}' "
        "style='font:11px Inter,system-ui,sans-serif'>"
    ]
    step_h = max(1, int(scale_min / 60 / 8))  # about eight hour ticks
    for hr in range(0, int(scale_min / 60) + 1, step_h):
        x = left + hr * 60 * px
        out.append(
            f"<line x1='{x:.1f}' x2='{x:.1f}' y1='0' y2='{h - 20}' stroke='#263041'/><text x='{x:.1f}' "
            f"y='{h - 6}' fill='#97a3b6' text-anchor='middle'>{hr}h</text>"
        )
    by = {s.system: s for s in rec.steps}
    for i, name in enumerate(order):
        s, sysm = by[name], est.systems[name]
        y = i * row + 2
        late = s.end > sysm.rto
        out.append(f"<text x='{left - 6}' y='{y + 12}' fill='#97a3b6' text-anchor='end'>{e(name)}</text>")
        out.append(
            f"<rect x='{left + s.start * px:.1f}' y='{y + 2}' width='{max((s.end - s.start) * px, 2):.1f}' "
            f"height='{row - 6}' rx='3' fill='{TIER_COLOUR[sysm.tier]}'><title>{e(name)} (tier {sysm.tier}): "
            f"{s.start / 60:.1f}h to {s.end / 60:.1f}h, RTO {sysm.rto / 60:.0f}h"
            f"{', late' if late else ''}</title></rect>"
        )
        if sysm.tier == 1:
            x = left + min(sysm.rto, scale_min) * px
            out.append(
                f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{y}' y2='{y + row - 2}' stroke='#ff6b6b' stroke-width='2'/>"
            )
    out.append("</svg>")
    return "".join(out)


EXAMPLE_HEADER = "Recovery runbook: payments platform (last edited two years ago)"


def example_runbook(est: Estate) -> tuple[str, list[PlanStep]]:
    """A wiki runbook for one tier-1 system and its dependencies, and its steps entered by hand, mistakes included."""
    top = next(n for n in sorted(est.systems) if est.systems[n].tier == 1 and len(est.systems[n].depends_on) == 2)
    a, b = est.systems[top].depends_on
    text = (
        f"{EXAMPLE_HEADER}\n\n1. Page the on-call DBA and post in #incident.\n2. Restore {top} from the latest "
        f"backup in the recovery region.\n3. Restore {a} from its nightly backup.\n4. Restore {b} and run the "
        f"verification queries.\n5. Restore ledger-legacy, which was retired last year.\n6. Point the payments DNS "
        f"record at the recovery region."
    )
    steps = [
        PlanStep(1, top, "notify", (), "Page the on-call DBA"),
        PlanStep(2, top, "restore_backup", (1,), f"Restore {top} from the latest backup"),
        PlanStep(3, a, "restore_backup", (1,), f"Restore {a} from its nightly backup"),
        PlanStep(4, b, "restore_backup", (3,), f"Restore {b} and run the verification queries"),
        PlanStep(5, "ledger-legacy", "restore_backup", (4,), "Restore ledger-legacy"),
        PlanStep(6, top, "switch_dns", (2, 4), "Point the payments DNS record at the recovery region"),
    ]
    return text, steps


class PlanBody(BaseModel):
    systems: list[str]


class RunbookBody(BaseModel):
    text: str


def create_app(console: Console) -> FastAPI:
    app = FastAPI(title="DR console")
    est, run = console.est, console.run

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "systems": len(est.systems), "week": NOW, "claude": console.converter is not None}

    @app.get("/api/schedule")
    def api_schedule() -> list[dict[str, Any]]:
        return [{"system": n, **{k: round(v, 3) for k, v in p.items()}} for n, p in console.schedule()]

    @app.post("/api/plan")
    def api_plan(body: PlanBody) -> dict[str, Any]:
        unknown = [s for s in body.systems if s not in est.systems]
        if unknown or not body.systems:
            raise HTTPException(422, f"unknown systems: {', '.join(unknown)}" if unknown else "no systems")
        rec = plan(est, body.systems, NOW)
        return {
            "total_minutes": round(rec.total, 1),
            "steps": [
                {
                    "system": s.system,
                    "start_minutes": round(s.start, 1),
                    "end_minutes": round(s.end, 1),
                    "within_rto": s.end <= est.systems[s.system].rto,
                }
                for s in rec.steps
            ],
        }

    @app.post("/api/runbook")
    def api_runbook(body: RunbookBody) -> dict[str, Any]:
        if console.converter is None:
            raise HTTPException(503, "runbook conversion needs ANTHROPIC_API_KEY")
        c = console.converter.convert(est, body.text)
        return {"executable": c.executable, "problems": c.problems, "steps": [s.__dict__ for s in c.steps]}

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        tests = [x for x in run.log if x["kind"] == "test"]
        found_tests = sum(len(x["found"]) for x in tests)
        found_disasters = sum(len(x["found"]) for x in run.log if x["kind"] == "disaster")
        rows = []
        for n, p in console.schedule():
            s = est.systems[n]
            why = [f"tier {s.tier}", f"{p['weeks_since_verified']:.0f} weeks since a verified restore"]
            if p["key_rotated"]:
                why.append("key rotated since")
            if p["projected_restore_vs_rto"] > 0.7:
                why.append(f"restore projected at {p['projected_restore_vs_rto']:.0%} of its RTO")
            rows.append(
                f"<tr><td><a href='/systems/{e(n)}'>{e(n)}</a></td><td class='num'>{p['score']:.0f}</td>"
                f"<td>{e('; '.join(why))}</td></tr>"
            )
        recent = [x for x in run.log if x["found"]][-12:][::-1]
        events = "".join(
            f"<tr><td>week {int(x['t'])}</td><td>{'restore test' if x['kind'] == 'test' else 'disaster restore'}</td>"
            f"<td><a href='/systems/{e(x['system'])}'>{e(x['system'])}</a></td><td>"
            + " ".join(
                f"<span class='b {'warn' if x['kind'] == 'test' else 'bad'}'>{e(m.replace('_', ' '))}</span>"
                for m in x["found"]
            )
            + "</td></tr>"
            for x in recent
        )
        body = (
            f"<h1>This week's restore tests</h1><p class='muted'>{CAPACITY} restore tests a week across "
            f"{len(est.systems)} systems. Every backup job reports success; only a restore shows whether a backup "
            "can be used. The systems below scored highest on what the platform knows: tier, time since the last "
            "verified restore, key rotations since then, and projected restore time against the RTO.</p>"
            f"<div class='grid'><div class='card'><b>{len(est.systems)}</b><span class='muted'>systems "
            f"({sum(s.tier == 1 for s in est.systems.values())} tier 1)</span></div><div class='card'>"
            f"<b>{len(tests)}</b><span class='muted'>restore tests so far this year</span></div><div class='card'>"
            f"<b>{found_tests}</b><span class='muted'>broken backups found by tests</span></div><div class='card'>"
            f"<b>{found_disasters}</b><span class='muted'>found the hard way, in a disaster restore</span></div>"
            "</div><h2>Scheduled this week</h2><table><tr><th>System</th><th class='num'>Risk score</th>"
            f"<th>Why</th></tr>{''.join(rows)}</table><h2>Recent problems found</h2><table><tr><th>When</th>"
            f"<th>How</th><th>System</th><th>Problem</th></tr>{events}</table>"
        )
        return _page("DR console", body)

    @app.get("/systems", response_class=HTMLResponse)
    def systems() -> str:
        rows = []
        for n in sorted(est.systems, key=lambda x: (est.systems[x].tier, x)):
            s = est.systems[n]
            proj = s.restore_minutes(NOW)
            last = run.last[n]
            cls = "bad" if proj > s.rto else "warn" if proj > 0.7 * s.rto else "ok"
            rows.append(
                f"<tr><td><a href='/systems/{e(n)}'>{e(n)}</a></td><td>{s.tier}</td>"
                f"<td class='num'>{s.rto / 60:.0f}h / {TIER_RPO_H[s.tier]}h</td><td class='num'>"
                f"<span class='b {cls}'>{proj:.0f} min</span></td><td class='num'>"
                f"{'before the year' if last < 0 else f'week {int(last)}'}</td>"
                f"<td>{e(', '.join(s.depends_on)) or '-'}</td></tr>"
            )
        body = (
            "<h1>Systems</h1><p class='muted'>Projected full-restore time from measured data size and restore "
            "throughput, against each system's recovery time objective.</p><div class='scroll'><table><tr>"
            "<th>System</th><th>Tier</th><th class='num'>RTO / RPO</th><th class='num'>Restore now</th>"
            f"<th class='num'>Last verified</th><th>Depends on</th></tr>{''.join(rows)}</table></div>"
        )
        return _page("Systems", body)

    @app.get("/systems/{name}", response_class=HTMLResponse)
    def system(name: str) -> str:
        if name not in est.systems:
            raise HTTPException(404, "no such system")
        s = est.systems[name]
        p = score_parts(run.est, name, console.t, run.last[name], Weights())
        users = sorted(n for n, x in est.systems.items() if name in x.depends_on)
        hist = (
            "".join(
                f"<tr><td>week {int(x['t'])}</td><td>{'restore test' if x['kind'] == 'test' else 'disaster restore'}</td>"
                "<td>"
                + (
                    " ".join(f"<span class='b bad'>{e(m.replace('_', ' '))}</span>" for m in x["found"])
                    or "<span class='b ok'>restored cleanly</span>"
                )
                + "</td></tr>"
                for x in console.history(name)
            )
            or "<tr><td colspan='3' class='muted'>No restores this year.</td></tr>"
        )
        body = (
            f"<h1>{e(name)}</h1><p class='muted'>Tier {s.tier}: back within {s.rto / 60:.0f} h, losing at most "
            f"{TIER_RPO_H[s.tier]} h of data.</p><div class='grid'><div class='card'><b>{s.restore_minutes(NOW):.0f}"
            f" min</b><span class='muted'>projected full restore now</span></div><div class='card'>"
            f"<b>{s.restore_minutes(min(NOW + 13, 51)):.0f} min</b><span class='muted'>in a quarter, at "
            f"{s.growth:.1%} growth a week</span></div><div class='card'><b>{p['weeks_since_verified']:.0f} weeks"
            f"</b><span class='muted'>since a verified restore</span></div><div class='card'><b>{p['score']:.0f}"
            f"</b><span class='muted'>risk score (tests this week go to the top {CAPACITY})</span></div></div>"
            f"<div class='cols'><div><h2>Depends on</h2><p>{e(', '.join(s.depends_on)) or 'nothing'}</p></div><div>"
            f"<h2>Needed by</h2><p>{e(', '.join(users)) or 'nothing'}</p></div></div>"
            f"<h2>Key rotations</h2><p>weeks {e(', '.join(str(w) for w in sorted(s.rotation_weeks)))}</p>"
            f"<h2>Restores this year</h2><table><tr><th>When</th><th>How</th><th>Result</th></tr>{hist}</table>"
        )
        return _page(name, body)

    @app.get("/recovery/{key}", response_class=HTMLResponse)
    def recovery(key: str) -> str:
        if key not in SCENARIOS:
            raise HTTPException(404, "no such scenario")
        hit = console.scenario(key)
        o, m = plan(est, hit, NOW), manual(est, hit, NOW, seed=NOW)
        order = [s.system for s in sorted(o.steps, key=lambda s: (s.start, s.system))]
        scale = max(o.total, m.total)
        t1 = [n for n in hit if est.systems[n].tier == 1]
        met_o = sum(o.done_at(n) <= est.systems[n].rto for n in t1)
        met_m = sum(m.done_at(n) <= est.systems[n].rto for n in t1)
        tabs = "".join(
            f"<a class='{'on' if k == key else ''}' href='/recovery/{k}'>{e(v)}</a>" for k, v in SCENARIOS.items()
        )
        legend = (
            "<p class='legend'>"
            + "".join(f"<span><i style='background:{c}'></i>tier {t}</span>" for t, c in TIER_COLOUR.items())
            + "<span><i style='background:#ff6b6b;width:3px'></i>tier-1 RTO</span></p>"
        )
        wv = waves(est, hit)
        body = (
            f"<h1>Recovery rehearsal: {e(SCENARIOS[key])}</h1><p class='tabs'>{tabs}</p><p class='muted'>"
            f"{len(hit)} systems to restore. The plan starts each restore as soon as what it depends on is back and "
            "checked, six at a time, most important first; anything a tier-1 system needs inherits its priority. "
            "The manual runbook is the same restores one at a time in the runbook's order, with an operator's "
            "overhead per step and the odd step redone.</p><div class='grid'><div class='card'>"
            f"<b>{met_o} of {len(t1)}</b><span class='muted'>tier-1 systems back within RTO (manual: {met_m})"
            f"</span></div><div class='card'><b>{o.total / 60:.1f} h</b><span class='muted'>until everything is "
            f"back (manual: {m.total / 60:.1f} h)</span></div><div class='card'><b>{len(wv)}</b><span "
            "class='muted'>dependency levels</span></div><div class='card'><b>6</b><span class='muted'>restores "
            f"at once</span></div></div><h2>Planned recovery</h2>{legend}<div class='scroll'>"
            f"{_gantt(est, o, scale, order, 'planned recovery')}</div><h2>Manual runbook, same scale</h2>"
            f"<div class='scroll'>{_gantt(est, m, scale, order, 'manual recovery')}</div>"
        )
        return _page("Recovery rehearsal", body)

    def runbook_page(text: str, checked: Checked, note: str) -> str:
        rows = "".join(
            f"<tr><td>{s.id}</td><td>{e(s.system)}</td><td>{e(s.action.replace('_', ' '))}</td><td>"
            f"{e(', '.join(map(str, s.after))) or '-'}</td><td class='muted'>{e(s.quote)}</td></tr>"
            for s in checked.steps
        )
        probs = "".join(f"<li>{e(p)}</li>" for p in checked.problems)
        verdict = (
            "<span class='b ok'>executable</span>"
            if checked.executable
            else f"<span class='b bad'>not executable: {len(checked.problems)} problems</span>"
        )
        form = (
            "<form method='post' action='/runbook'><textarea name='text'>" + e(text) + "</textarea><p><button>"
            "Convert with Claude</button></p></form>"
            if console.converter is not None
            else "<p class='muted'>Converting a new runbook needs an Anthropic API key (ANTHROPIC_API_KEY) when the "
            "console is run from the repository.</p>"
        )
        return _page(
            "Runbooks",
            (
                "<h1>Runbooks into checked plans</h1><p class='muted'>Claude reads a wiki runbook and returns its steps "
                "(system, action, what each waits for, and the words it came from). The platform then checks the plan "
                "against the inventory: systems that exist, actions it can run, quotes that are really in the runbook, and "
                f"no restore before the systems it depends on.</p><p class='muted'>{e(note)}</p><div class='cols'><div>"
                f"<h2>Runbook</h2><pre>{e(text)}</pre></div><div><h2>Plan {verdict}</h2><table><tr><th>#</th><th>System"
                f"</th><th>Action</th><th>After</th><th>From</th></tr>{rows}</table><h2>Problems</h2>"
                f"<ul>{probs or '<li>none</li>'}</ul></div></div><h2>Convert another runbook</h2>{form}"
            ),
        )

    @app.get("/runbook", response_class=HTMLResponse)
    def runbook() -> str:
        text, steps = example_runbook(est)
        return runbook_page(
            text,
            Checked(steps, check(est, steps, text)),
            "Example: the steps below were entered by hand from this runbook; Claude's output goes "
            "through the same checks.",
        )

    @app.post("/runbook", response_class=HTMLResponse)
    def runbook_convert(text: str = Form("")) -> str:
        if console.converter is None:
            raise HTTPException(503, "runbook conversion needs ANTHROPIC_API_KEY")
        if not text.strip():
            raise HTTPException(422, "paste a runbook")
        return runbook_page(text, console.converter.convert(est, text), "Converted by Claude, then checked.")

    return app


def demo_console(converter: Converter | None = None) -> Console:
    est = Estate(42)
    return Console(est, replay(est, "risk", CAPACITY, until=NOW), converter)


def demo_app() -> FastAPI:
    import os

    return create_app(demo_console(Converter() if os.environ.get("ANTHROPIC_API_KEY") else None))
