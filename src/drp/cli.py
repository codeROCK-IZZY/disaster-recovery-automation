"""Command line: this week's restore tests, a recovery plan, a runbook check, the console, and the evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="drp", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schedule", help="this week's restore tests in the demo estate, and why")
    p = sub.add_parser("plan", help="a recovery plan for some systems of the demo estate")
    p.add_argument("systems", nargs="*", help="system names (default: zone A)")
    rb = sub.add_parser("runbook", help="turn a runbook file into a checked plan with Claude (needs ANTHROPIC_API_KEY)")
    rb.add_argument("file")
    s = sub.add_parser("serve", help="the DR console with the demo estate")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    ev = sub.add_parser("evaluate", help="restore-test policies and orchestration on held-out estates")
    ev.add_argument("--out", default="eval/reports")
    ev.add_argument("--gate", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "evaluate":
        from .evaluate import run, save

        result = run()
        save(result, Path(args.out))
        print((Path(args.out) / "report.md").read_text(encoding="utf-8"))
        return 1 if args.gate and not result["ok"] else 0
    if args.cmd == "serve":
        import uvicorn

        from .app import demo_app

        uvicorn.run(demo_app(), host=args.host, port=args.port)
        return 0

    from .app import NOW, demo_console

    console = demo_console()
    if args.cmd == "schedule":
        for name, parts in console.schedule():
            print(json.dumps({"system": name, **{k: round(v, 2) for k, v in parts.items()}}))
        return 0
    if args.cmd == "plan":
        from .orchestrate import plan

        systems = args.systems or console.scenario("zone-a")
        unknown = [x for x in systems if x not in console.est.systems]
        if unknown:
            print("unknown systems:", ", ".join(unknown), file=sys.stderr)
            return 2
        rec = plan(console.est, systems, NOW)
        for st in sorted(rec.steps, key=lambda x: x.start):
            rto = console.est.systems[st.system].rto
            print(
                f"{st.start / 60:6.1f}h -> {st.end / 60:6.1f}h  {st.system:10s} "
                f"{'within RTO' if st.end <= rto else 'late'}"
            )
        print(f"everything back after {rec.total / 60:.1f} h")
        return 0
    from .runbook import Converter

    checked = Converter().convert(console.est, Path(args.file).read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "executable": checked.executable,
                "problems": checked.problems,
                "steps": [st.__dict__ for st in checked.steps],
            },
            indent=2,
        )
    )
    return 0 if checked.executable else 1


if __name__ == "__main__":
    sys.exit(main())
