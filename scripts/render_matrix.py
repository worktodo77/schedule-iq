"""Render matrix.yaml -> docs/METRIC_MATRIX.md (run after editing the matrix)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from scheduleiq.metrics.engine import load_matrix  # noqa: E402

OUT = os.path.join(HERE, "..", "docs", "METRIC_MATRIX.md")


def main():
    matrix = load_matrix()
    lines = [
        "# ScheduleIQ Metric & Heuristic Matrix",
        "",
        "*Generated from `src/scheduleiq/metrics/matrix.yaml` by "
        "`scripts/render_matrix.py` — edit the YAML, not this file.*",
        "",
        "This matrix is the authoritative inventory of every check ScheduleIQ "
        "runs.  The engine runs nothing that is not defined here, and reports "
        "anything defined but unimplemented as NOT EVALUATED.  Default "
        "thresholds are the published standard values; analysts may override "
        "them per run via a threshold profile, and every output records the "
        "threshold applied and its provenance.  Full citations for the "
        "reference keys are in [REFERENCES.md](REFERENCES.md).",
        "",
        f"**{len(matrix)} checks.**",
        "",
    ]
    by_cat: dict[str, list] = {}
    for c in matrix:
        by_cat.setdefault(c.category, []).append(c)
    for cat, checks in by_cat.items():
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| ID | Check | Definition | Formula (as implemented) | "
                     "Default threshold | Severity | References | "
                     "Fuse equivalent |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in checks:
            if c.threshold is None:
                thr = "informational"
            else:
                op = "≤" if c.direction == "max" else "≥"
                sfx = "%" if c.unit == "percent" else ""
                thr = f"{op} {c.threshold:g}{sfx}"
            refs = "; ".join(c.references)
            desc = c.description + (f"  *{c.notes}*" if c.notes else "")
            lines.append(
                f"| {c.id} | {c.name} | {desc} | {c.formula} | {thr} | "
                f"{c.severity} | {refs} | {c.fuse_equivalent or '—'} |")
        lines.append("")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(matrix)} checks)")


if __name__ == "__main__":
    main()
