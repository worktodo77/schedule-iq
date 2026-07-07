#!/usr/bin/env python3
"""LI Schedule Report Card — minimal independent reference scorer.

NOT YET PUBLISHED (see README.md in this directory).  This is deliberately
NOT the ScheduleIQ scoring engine (that lives in scheduleiq.scorecard) — it
is a short, dependency-light (PyYAML only) demonstration that the published
curve formula in scorecard.yaml, applied to a plain CSV of check results,
reproduces one file-card category's score from nothing but public inputs.

CSV input columns (one row per check in the category you are scoring):
    id         matrix check ID, e.g. DCMA-01
    value      the measured value (blank/empty for N/A or NOT EVALUATED)
    status     PASS | FAIL | WARNING | INFO | N/A | NOT EVALUATED
    threshold  the published threshold for this check (blank if none)
    direction  max | min | info
    unit       percent | count | ratio | index | days | info
    severity   critical | warning | info

(These seven fields are exactly what a results workbook's "Metric Results"
sheet already records for every check — see report/excel.py in the
ScheduleIQ source — so building this CSV from a delivered workbook is a
five-minute spreadsheet export, not a re-implementation.)

Usage:
    python reference_scorer.py results.csv scorecard.yaml logic_network
"""
from __future__ import annotations

import csv
import sys

import yaml

EPS = 1e-9


def piecewise_score(value: float, points: list) -> float:
    pts = sorted((float(x), float(y)) for x, y in points)
    if value <= pts[0][0]:
        return pts[0][1]
    if value >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 - EPS <= value <= x1 + EPS:
            if abs(x1 - x0) < EPS:
                return y0
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return pts[-1][1]


def default_points(row: dict, override: dict, spec: dict) -> list | None:
    if override and "points" in override:
        return override["points"]
    thr = row["threshold"]
    if thr is None or row["direction"] not in ("max", "min"):
        return None
    dc = spec["default_curve"]
    mult = dc["fail_ceiling_multiplier"]
    zt = dc["zero_tolerance_defaults"]
    if row["direction"] == "max":
        ideal = (override or {}).get("ideal", 0.0)
        ceiling = (override or {}).get("fail_ceiling")
        if ceiling is None:
            ceiling = (thr * mult if abs(thr) > EPS else
                      (zt["percent_ceiling"] if row["unit"] == "percent"
                       else zt["count_ceiling"]))
        if abs(ideal - thr) < EPS:
            return [(ideal, 100.0), (ceiling, 0.0)]
        return [(ideal, 100.0), (thr, 70.0), (ceiling, 0.0)]
    ideal = (override or {}).get("ideal", 100.0 if row["unit"] == "percent" else 1.0)
    floor = (override or {}).get("fail_floor",
                                 thr / mult if abs(thr) > EPS else 0.0)
    if abs(ideal - thr) < EPS:
        return [(floor, 0.0), (ideal, 100.0)]
    return [(floor, 0.0), (thr, 70.0), (ideal, 100.0)]


def member_weight(row: dict, spec: dict) -> float:
    sw = spec["severity_weights"]
    if row["severity"] == "critical":
        return sw["critical"]
    if row["severity"] == "warning":
        return sw["warning"]
    return sw["banded_info"] if row["threshold"] is not None else sw["info"]


def load_csv(path: str) -> dict:
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["id"]] = {
                "value": float(row["value"]) if row["value"] not in (None, "") else None,
                "status": row["status"],
                "threshold": float(row["threshold"]) if row["threshold"] not in (None, "") else None,
                "direction": row["direction"],
                "unit": row["unit"],
                "severity": row["severity"],
            }
    return out


def score_category(rows: dict, spec: dict, category_id: str) -> None:
    cat = next(c for c in spec["categories"] if c["id"] == category_id)
    overrides = spec.get("curve_overrides", {})
    total_w, wsum = 0.0, 0.0
    print(f"{cat['name']} ({category_id})")
    for check_id in cat["members"]:
        row = rows.get(check_id)
        if row is None or row["status"] in ("N/A", "NOT EVALUATED") or row["value"] is None:
            print(f"  {check_id:10s}  N/A — excluded (leaves the denominator)")
            continue
        override = overrides.get(check_id)
        points = default_points(row, override, spec)
        weight = member_weight(row, spec)
        score = piecewise_score(row["value"], points) if points else None
        if score is None:
            print(f"  {check_id:10s}  not gradeable by default (no threshold/override)")
            continue
        print(f"  {check_id:10s}  value={row['value']:<8g} weight={weight:<3g} score={score:6.1f}")
        total_w += weight * score
        wsum += weight
    if wsum:
        print(f"\n{cat['name']} score = {total_w / wsum:.2f} / 100  "
             f"(weighted mean of {int(wsum)} weighted points across graded members)")
    else:
        print(f"\n{cat['name']}: no gradeable members in this CSV.")


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    csv_path, spec_path, category_id = sys.argv[1:4]
    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    rows = load_csv(csv_path)
    score_category(rows, spec, category_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
