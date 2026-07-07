"""Command-line interface.

    scheduleiq analyze update1.xer update2.xer update3.xer -o out/
    scheduleiq analyze projectA.xer projectB.mpp --benchmark -o out/
    scheduleiq matrix                # print the check matrix
    scheduleiq gui                   # launch the desktop app
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="scheduleiq",
        description="Schedule quality, health, trend, and change analysis "
                    "(.xer, MSPDI .xml, .mpp).")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("analyze", help="analyze one or more schedule files")
    a.add_argument("files", nargs="+")
    a.add_argument("-o", "--out", default="scheduleiq_output",
                   help="output directory")
    a.add_argument("--profile", default=None,
                   help="threshold override profile (YAML/JSON: {CHECK-ID: value})")
    a.add_argument("--paper", choices=["letter", "a4"], default="letter")
    a.add_argument("--no-pdf", action="store_true")
    a.add_argument("--benchmark", action="store_true",
                   help="treat files as separate projects (side-by-side "
                        "benchmarking instead of a time series)")
    a.add_argument("--events", default=None,
                   help="delay-event CSV (event_id, title, start, finish, keywords, "
                        "responsibility) for the intake delay-event mapper")
    a.add_argument("--responsibility", default=None,
                   help="responsibility-mapping CSV (pattern, scope [wbs|activity], "
                        "party) for the intake responsibility overlay")
    a.add_argument("--no-cockpit", action="store_true",
                   help="skip the interactive network cockpit HTML artifact "
                        "(overrides --profile's config: {cockpit: true})")
    a.add_argument("--internal-workbook", action="store_true",
                   help="write the INTERNAL_PRIVILEGED_ workbook (LI-11..LI-15 "
                        "provocative indices) — overrides --profile's config: "
                        "{internal_workbook: false}")

    sub.add_parser("matrix", help="print the metric matrix")
    sub.add_parser("gui", help="launch the desktop application")

    ns = ap.parse_args(argv)
    if ns.cmd == "matrix":
        from .metrics.engine import load_matrix
        for c in load_matrix():
            thr = "info" if c.threshold is None else \
                f"{'<=' if c.direction == 'max' else '>='} {c.threshold:g}"
            print(f"{c.id:9} {c.category:32} {c.name:48} {thr:12} "
                  f"[{'; '.join(c.references)}]")
        return 0
    if ns.cmd == "gui" or ns.cmd is None:
        from .gui.app import run_gui
        return run_gui()

    from .runner import run
    rr = run(ns.files, ns.out, profile=ns.profile, paper=ns.paper,
             make_pdf=not ns.no_pdf, benchmark=ns.benchmark,
             events_csv=ns.events, responsibility_csv=ns.responsibility,
             no_cockpit=ns.no_cockpit, internal_workbook=ns.internal_workbook,
             progress=lambda m: print(f"  {m}"))
    print("\nOutputs:")
    for p in rr.outputs:
        print(f"  {p}")
    for m in rr.messages:
        print(f"\nNote: {m}")
    for w in rr.analysis.warnings:
        print(f"\nSeries warning: {w.message}")
    latest = rr.analysis.assessments[-1]
    print(f"\nLatest health score: {latest.health_score:.0f}/100  "
          f"(FAIL {latest.counts.get('FAIL', 0)}, "
          f"WARNING {latest.counts.get('WARNING', 0)}, "
          f"PASS {latest.counts.get('PASS', 0)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
