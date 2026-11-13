"""Markdown and HTML versions of the evaluation."""

from __future__ import annotations

import html
from typing import Any

BANK = {"dev": "Tuning estates", "heldout": "Held-out estates", "different": "Different estate (held back)"}
POLICY = {
    "status_only": "Trust the job status",
    "random": "Random restore tests",
    "round_robin": "Round robin",
    "risk": "Risk-based (this platform)",
}


def markdown(r: dict[str, Any]) -> str:
    out = [
        "# Automated disaster recovery: evaluation",
        "",
        "Simulated estates over a year: backups that silently stop being restorable, a fixed number of restore tests "
        "a week, and region outages that force restores.",
        "",
    ]
    for b, bl in BANK.items():
        x = r["banks"][b]
        out += [
            f"## {bl}: {x['estates']} estates of {x['systems']} systems, {x['tests_per_week']} tests a week, "
            f"{x['silent_failures']:,} silent failures, {x['disasters']} disasters",
            "",
            "| Testing | Days a broken backup goes unnoticed | Found by tests | Restores in disasters | Clean | "
            "RPO breaches | RTO breaches | Tier-1 restores that failed |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for p, pl in POLICY.items():
            s = x[p]
            out.append(
                f"| {pl} | {s['mean_days_undetected']} | {s['found_by_tests']:,} | {s['disaster_restores']:,} | "
                f"{s['restored_cleanly']:,} | {s['rpo_breaches']} | {s['rto_breaches']} | "
                f"{s['tier1_failed_restores']} |"
            )
        rec = x["recovery"]
        out += [
            "",
            f"Recovery ({rec['tier1_restores']} tier-1 restores): orchestrated "
            f"{rec['orchestrated']['tier1_within_rto']:.1%} within RTO, everything back in a median "
            f"{rec['orchestrated']['median_hours_to_full_recovery']} h; manual runbook "
            f"{rec['manual']['tier1_within_rto']:.1%}, {rec['manual']['median_hours_to_full_recovery']} h.",
            "",
        ]
    out += ["## Gate (regression limits, not targets)", ""]
    for k, v in r["checks"].items():
        out.append(f"- {'PASS' if r['passed'][k] else 'FAIL'} {k}: {v} (limit {r['gate'][k]})")
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#0d1016;--panel:#151b24;--line:#263042;--ink:#e8edf4;--ink2:#97a3b6;--ok:#3ccf8e;--bad:#ff6b6b;--mid:#f5b54a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.5;font-family:Inter,system-ui,
sans-serif}main{max-width:1180px;margin:0 auto;padding:34px 28px 56px}h1{font-size:28px;margin:0 0 4px}h2{font-size:18px;
margin:28px 0 12px}.sub{color:var(--ink2);margin:0 0 20px}.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}.tile b{display:block;
font-size:28px}.tile span{color:var(--ink2);font-size:13px}table{width:100%;border-collapse:collapse;background:var(--panel);
border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}th,td{padding:8px 12px;
border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);
font-weight:500;font-size:12px}td:not(:first-child){white-space:nowrap}.good{color:var(--ok);font-weight:600}
.bad{color:var(--bad);font-weight:600}@media(max-width:800px){.tiles{grid-template-columns:1fr 1fr}}
"""


def html_report(r: dict[str, Any]) -> str:
    e = html.escape
    h = r["banks"]["heldout"]
    tiles = [
        (
            f"{h['risk']['tier1_failed_restores']} vs {h['status_only']['tier1_failed_restores']}",
            "tier-1 restores that failed in disasters: risk-based tests vs trusting the job status",
        ),
        (
            f"{h['risk']['mean_days_undetected']:.0f} days",
            f"a broken backup goes unnoticed (job status: {h['status_only']['mean_days_undetected']:.0f})",
        ),
        (
            f"{h['recovery']['orchestrated']['tier1_within_rto']:.0%}",
            f"of tier-1 systems back within their RTO "
            f"(manual runbook: {h['recovery']['manual']['tier1_within_rto']:.0%})",
        ),
        (
            f"{h['recovery']['orchestrated']['median_hours_to_full_recovery']:.0f} h",
            f"median to recover everything (manual: {h['recovery']['manual']['median_hours_to_full_recovery']:.0f} h)",
        ),
    ]
    out = [
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
        f"initial-scale=1'><title>Disaster recovery evaluation</title><style>{CSS}</style><main>"
        "<h1>Automated disaster recovery: evaluation</h1><p class='sub'>Backups that silently stop being restorable, "
        "limited restore tests, and disasters. Weights chosen on separate estates.</p><div class='tiles'>"
    ]
    out += [f"<div class='tile'><b>{e(v)}</b><span>{e(t)}</span></div>" for v, t in tiles]
    out.append("</div>")
    for b, bl in BANK.items():
        if b == "dev":
            continue
        x = r["banks"][b]
        out.append(
            f"<h2>{e(bl)}</h2><table><tr><th>Testing</th><th>Days unnoticed</th><th>Clean restores</th>"
            "<th>RPO breaches</th><th>RTO breaches</th><th>Tier-1 failed</th></tr>"
        )
        best = min(x[p]["tier1_failed_restores"] for p in POLICY)
        for p, pl in POLICY.items():
            s = x[p]
            cls = "good" if s["tier1_failed_restores"] == best else ""
            out.append(
                f"<tr><td>{e(pl)}</td><td>{s['mean_days_undetected']}</td><td>{s['restored_cleanly']:,} of "
                f"{s['disaster_restores']:,}</td><td>{s['rpo_breaches']}</td><td>{s['rto_breaches']}</td>"
                f"<td class='{cls}'>{s['tier1_failed_restores']}</td></tr>"
            )
        out.append("</table>")
    out.append(
        "<h2>Gate (regression limits)</h2><table><tr><th>Check</th><th>Value</th><th>Limit</th><th>Result</th></tr>"
    )
    for k, v in r["checks"].items():
        ok = r["passed"][k]
        out.append(
            f"<tr><td>{e(k)}</td><td>{e(str(v))}</td><td>{e(str(r['gate'][k]))}</td>"
            f"<td class='{'good' if ok else 'bad'}'>{'pass' if ok else 'fail'}</td></tr>"
        )
    out.append("</table></main></html>")
    return "".join(out) + "\n"
