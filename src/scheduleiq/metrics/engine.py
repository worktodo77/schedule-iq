"""Matrix-driven metrics engine.

The authoritative check inventory lives in ``matrix.yaml`` (rendered to
docs/METRIC_MATRIX.md).  Each matrix row carries an ID, category, definition,
default threshold, comparison direction, and its literature reference(s).
Check implementations register against matrix IDs; the engine walks the matrix
so that (a) nothing runs that isn't documented, and (b) anything documented but
unimplemented is reported as NOT EVALUATED rather than silently skipped.

Threshold profiles: the matrix defaults mirror the published standards
(DCMA-style tripwires); analysts may override per-run with a profile YAML/JSON,
and every result records BOTH the threshold applied and its provenance
(standard default vs. analyst override) for defensibility.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..ingest.model import Schedule

MATRIX_PATH = os.path.join(os.path.dirname(__file__), "matrix.yaml")


@dataclass
class CheckDef:
    id: str
    name: str
    category: str
    description: str
    formula: str
    unit: str                      # percent | count | ratio | index | days | info
    threshold: Optional[float]     # None -> informational metric
    direction: str                 # max (value must be <=), min (>=), info
    severity: str                  # critical | warning | info
    references: list[str]
    fuse_equivalent: str = ""
    applies_to: str = "all"        # all | update (needs progress) | series
    notes: str = ""


@dataclass
class Finding:
    """One offending object (activity / relationship / calendar)."""
    object_id: str
    object_name: str = ""
    detail: str = ""


@dataclass
class MetricResult:
    check: CheckDef
    value: Optional[float] = None            # the computed metric value
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    threshold_applied: Optional[float] = None
    threshold_source: str = "standard default"
    status: str = "PASS"                     # PASS | FAIL | WARNING | INFO | NOT EVALUATED | N/A
    findings: list[Finding] = field(default_factory=list)
    narrative: str = ""                      # one-sentence result statement

    @property
    def display_value(self) -> str:
        if self.value is None:
            return "—"
        if self.check.unit == "percent":
            return f"{self.value:.1f}%"
        if self.check.unit in ("ratio", "index"):
            return f"{self.value:.2f}"
        if self.check.unit == "days":
            return f"{self.value:.1f}"
        return f"{self.value:.0f}"


@dataclass
class ScheduleAssessment:
    schedule: Schedule
    results: list[MetricResult] = field(default_factory=list)

    def by_category(self) -> dict[str, list[MetricResult]]:
        out: dict[str, list[MetricResult]] = {}
        for r in self.results:
            out.setdefault(r.check.category, []).append(r)
        return out

    def result(self, check_id: str) -> Optional[MetricResult]:
        for r in self.results:
            if r.check.id == check_id:
                return r
        return None

    @property
    def counts(self) -> dict[str, int]:
        c = {"PASS": 0, "FAIL": 0, "WARNING": 0, "INFO": 0,
             "NOT EVALUATED": 0, "N/A": 0}
        for r in self.results:
            c[r.status] = c.get(r.status, 0) + 1
        return c

    @property
    def health_score(self) -> float:
        """0-100 weighted score across evaluated pass/fail checks (critical
        checks weigh 2x warnings).  Documented in METHODOLOGY.md — this is a
        triage aid, not an opinion on schedule adequacy."""
        num = den = 0.0
        for r in self.results:
            if r.status not in ("PASS", "FAIL", "WARNING"):
                continue
            w = 2.0 if r.check.severity == "critical" else 1.0
            den += w
            if r.status == "PASS":
                num += w
            elif r.status == "WARNING":
                num += w * 0.5
        return round(100.0 * num / den, 1) if den else 100.0


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
CheckFn = Callable[[Schedule, "CheckDef", Optional[float]], MetricResult]
_REGISTRY: dict[str, CheckFn] = {}


def register(check_id: str):
    def deco(fn: CheckFn):
        _REGISTRY[check_id] = fn
        return fn
    return deco


def _parse_simple_yaml(text: str) -> list[dict]:
    """Minimal YAML-subset reader for matrix.yaml (list of flat mappings with
    optional list-valued 'references').  Avoids a hard PyYAML dependency; if
    PyYAML is installed it is used instead."""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        return data["checks"]
    except ImportError:
        pass
    checks: list[dict] = []
    cur: dict | None = None
    key = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if raw.startswith("checks:"):
            continue
        if raw.startswith("  - "):
            cur = {}
            checks.append(cur)
            raw = "    " + raw[4:]
        if cur is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and key:
            cur.setdefault(key, [])
            cur[key].append(stripped[2:].strip().strip('"'))
            continue
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            key = k.strip()
            v = v.strip()
            if v == "":
                cur[key] = []
            else:
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif v == "null":
                    v = None
                else:
                    try:
                        v = float(v) if "." in v else int(v)
                    except (ValueError, TypeError):
                        pass
                cur[key] = v
    return checks


def load_matrix(path: str = MATRIX_PATH) -> list[CheckDef]:
    with open(path, encoding="utf-8") as f:
        rows = _parse_simple_yaml(f.read())
    defs = []
    for r in rows:
        thr = r.get("threshold")
        defs.append(CheckDef(
            id=str(r["id"]), name=r["name"], category=r["category"],
            description=r.get("description", ""), formula=r.get("formula", ""),
            unit=r.get("unit", "count"),
            threshold=float(thr) if thr is not None else None,
            direction=r.get("direction", "max"),
            severity=r.get("severity", "warning"),
            references=list(r.get("references", [])),
            fuse_equivalent=r.get("fuse_equivalent", ""),
            applies_to=r.get("applies_to", "all"),
            notes=r.get("notes", ""),
        ))
    return defs


def load_profile(path: str | None) -> dict[str, float]:
    """Analyst threshold overrides: {check_id: threshold}."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        if path.endswith(".json"):
            return {str(k): float(v) for k, v in json.load(f).items()}
        overrides = {}
        for line in f:
            line = line.split("#", 1)[0].strip()
            if ":" in line:
                k, _, v = line.partition(":")
                try:
                    overrides[k.strip()] = float(v)
                except ValueError:
                    continue
        return overrides


def evaluate(sched: Schedule, matrix: list[CheckDef] | None = None,
             overrides: dict[str, float] | None = None) -> ScheduleAssessment:
    matrix = matrix if matrix is not None else load_matrix()
    overrides = overrides or {}
    assessment = ScheduleAssessment(schedule=sched)
    for cd in matrix:
        thr = overrides.get(cd.id, cd.threshold)
        fn = _REGISTRY.get(cd.id)
        if cd.applies_to == "series":
            res = MetricResult(check=cd, status="N/A",
                               narrative="Series metric — evaluated in trend analysis "
                                         "when multiple updates are ingested.")
        elif fn is None:
            res = MetricResult(check=cd, status="NOT EVALUATED",
                               narrative="No automated implementation; review manually.")
        else:
            try:
                res = fn(sched, cd, thr)
            except Exception as e:      # a broken check must never sink the run
                res = MetricResult(check=cd, status="NOT EVALUATED",
                                   narrative=f"Evaluation error: {e}")
        res.threshold_applied = thr
        if cd.id in overrides:
            res.threshold_source = "analyst override"
        assessment.results.append(res)
    return assessment


def judge(cd: CheckDef, value: float, thr: float | None,
          findings: list[Finding], num=None, den=None,
          narrative: str = "") -> MetricResult:
    """Standard pass/fail arithmetic used by most checks."""
    if thr is None or cd.direction == "info":
        status = "INFO"
    elif cd.direction == "max":
        status = "PASS" if value <= thr else ("FAIL" if cd.severity == "critical" else "WARNING")
    else:
        status = "PASS" if value >= thr else ("FAIL" if cd.severity == "critical" else "WARNING")
    return MetricResult(check=cd, value=value, numerator=num, denominator=den,
                        findings=findings, status=status, narrative=narrative)
