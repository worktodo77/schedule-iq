"""RC2 — the LI Schedule Report Card scoring engine.

Spec-driven: every number this module produces traces back to a line in
``scorecard.yaml`` (RC1, the published spec) plus the check results already
computed by ``metrics.engine.evaluate`` / ``trend.series.analyze_series``.
Nothing here re-implements a check; it only converts existing MetricResult
values to a 0-100 conformance score via the spec's published curves, and
aggregates those scores per the spec's categories, weights, profiles, and
gates.

A small number of series-category members (``SPEC-CADENCE``, the D1 update-
cadence regularity signal; ``SPEC-EVERGREEN``, the D8 percent-complete-creep
count; and ``SPEC-TSPI``, the S3 earned-schedule to-complete index) are not
matrix checks — they have no matrix.yaml row and therefore no MetricResult.
docs/REPORT_CARD_DESIGN.md §4 nonetheless lists them as series-category
members ("cadence (D1)", "evergreen count", "ES/TSPI(t)"), so this module
reads them the same way every other additive report module in this codebase
already reads analytics it does not own (report/paths_report.py,
report/intake_report.py, trend/series.py's own LI-01..10 wiring in
analytics/li_wiring.py): a guarded, read-only import of the analytics
function, never a re-implementation.  Each is flagged as a non-matrix input
in scorecard.yaml and in every score_trace.json this module writes, so nothing
is hidden — see the spec file's header comment.  A failure computing any one
of them degrades that single member to N/A (leaves the denominator; never
sinks the run), matching this codebase's established "additive, never sink"
convention (see runner.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
from dataclasses import dataclass, field
from typing import Optional

import yaml

from .metrics.engine import CheckDef, MetricResult, ScheduleAssessment, load_matrix
from .trend.series import SeriesAnalysis

SPEC_PATH = os.path.join(os.path.dirname(__file__), "scorecard.yaml")

_EPS = 1e-9


# ============================================================================
# Data model
# ============================================================================
@dataclass
class MemberScore:
    check_id: str
    name: str
    value: Optional[float]
    status: str
    weight: float
    score: Optional[float]           # 0-100, or None if not gradeable/N/A
    offender_count: int = 0
    curve_points: list = field(default_factory=list)
    source: str = "matrix"           # "matrix" | "non-matrix"
    rationale: str = ""


@dataclass
class CategoryScore:
    id: str
    name: str
    weight_nominal: float             # spec weight before gate caps
    weight_used: float                # weight actually counted in the overall
                                       # (0 if no member could be graded)
    score_raw: Optional[float]        # weighted mean of member scores, pre-gate
    score: Optional[float]            # post gate-cap
    gate_cap: Optional[float] = None
    members: list = field(default_factory=list)   # list[MemberScore]
    graded: int = 0
    total: int = 0


@dataclass
class GateTrip:
    id: str
    name: str
    rule_text: str
    category_caps: dict = field(default_factory=dict)
    overall_cap: Optional[float] = None


@dataclass
class FileCard:
    schedule_label: str
    profile: str                      # "baseline" | "update"
    spec_version: str
    spec_sha256: str
    categories: list = field(default_factory=list)     # list[CategoryScore]
    overall_raw: float = 0.0
    overall: float = 0.0
    letter: str = "F"
    gates: list = field(default_factory=list)          # list[GateTrip]
    coverage_graded: int = 0
    coverage_total: int = 0
    top_factors: list = field(default_factory=list)     # [(pts_lost, id, n)]
    variant: str = "standard"
    internal_indices: list = field(default_factory=list)


@dataclass
class TrajectoryScore:
    level: Optional[float]
    slope: Optional[float]
    slope_score: Optional[float]
    score: Optional[float]
    weight: float


@dataclass
class SeriesCard:
    file_cards: list                                    # list[FileCard]
    spec_version: str
    spec_sha256: str
    series_categories: list = field(default_factory=list)   # list[CategoryScore]
    trajectory: Optional[TrajectoryScore] = None
    overall_raw: float = 0.0
    overall: float = 0.0
    letter: str = "F"
    gates: list = field(default_factory=list)
    coverage_graded: int = 0
    coverage_total: int = 0
    top_factors: list = field(default_factory=list)
    variant: str = "standard"
    internal_indices: list = field(default_factory=list)
    is_series: bool = False


# ============================================================================
# Spec loading
# ============================================================================
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_spec(path: str = SPEC_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    spec["_sha256"] = _sha256_file(path)
    return spec


# ============================================================================
# Curve arithmetic
# ============================================================================
def _piecewise_score(value: float, points: list) -> float:
    """Piecewise-linear interpolation/clamp over an explicit (x, y) point
    list.  Points need not be sorted; x-values are assumed distinct."""
    pts = sorted((float(x), float(y)) for x, y in points)
    if value <= pts[0][0]:
        return pts[0][1]
    if value >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 - _EPS <= value <= x1 + _EPS:
            if abs(x1 - x0) < _EPS:
                return y0
            frac = (value - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return pts[-1][1]


def _default_points(cd: CheckDef, override: dict, spec: dict) -> Optional[list]:
    """The default_curve rule from scorecard.yaml, or None if the check has
    no threshold and no override (not gradeable by default)."""
    if override and "points" in override:
        return [tuple(p) for p in override["points"]]
    thr = cd.threshold
    if thr is None or cd.direction not in ("max", "min"):
        return None
    dc = spec["default_curve"]
    mult = dc["fail_ceiling_multiplier"]
    zt = dc["zero_tolerance_defaults"]
    if cd.direction == "max":
        ideal = (override or {}).get("ideal", 0.0)
        ceiling = (override or {}).get("fail_ceiling")
        if ceiling is None:
            if abs(thr) < _EPS:
                ceiling = (zt["percent_ceiling"] if cd.unit == "percent"
                          else zt["count_ceiling"])
            else:
                ceiling = thr * mult
        if abs(ideal - thr) < _EPS:
            return [(ideal, 100.0), (ceiling, 0.0)]
        return [(ideal, 100.0), (thr, 70.0), (ceiling, 0.0)]
    else:  # direction == "min"
        ideal = (override or {}).get("ideal")
        if ideal is None:
            ideal = 100.0 if cd.unit == "percent" else 1.0
        floor = (override or {}).get("fail_floor")
        if floor is None:
            floor = thr / mult if abs(thr) > _EPS else 0.0
        if abs(ideal - thr) < _EPS:
            return [(floor, 0.0), (ideal, 100.0)]
        return [(floor, 0.0), (thr, 70.0), (ideal, 100.0)]


def _member_weight(cd: CheckDef, spec: dict, explicit: Optional[float] = None) -> float:
    if explicit is not None:
        return explicit
    sw = spec["severity_weights"]
    if cd.severity == "critical":
        return sw["critical"]
    if cd.severity == "warning":
        return sw["warning"]
    return sw["banded_info"] if cd.threshold is not None else sw["info"]


def _score_result(cd: CheckDef, result: Optional[MetricResult], spec: dict,
                  overrides: dict, weight_override: Optional[float] = None
                  ) -> MemberScore:
    override = overrides.get(cd.id)
    weight = _member_weight(cd, spec, weight_override)
    if result is None or result.status in ("N/A", "NOT EVALUATED") or result.value is None:
        return MemberScore(cd.id, cd.name, None,
                           result.status if result else "N/A", weight, None,
                           0, [], "matrix", (override or {}).get("rationale", ""))
    points = _default_points(cd, override, spec)
    score = _piecewise_score(result.value, points) if points else None
    if points is None:
        weight = 0.0
    return MemberScore(cd.id, cd.name, result.value, result.status, weight, score,
                       len(result.findings), points or [], "matrix",
                       (override or {}).get("rationale", ""))


def _aggregate_category(cat_id: str, name: str, weight_nominal: float,
                        members: list) -> CategoryScore:
    gradeable = [m for m in members if m.score is not None and m.weight > 0]
    wsum = sum(m.weight for m in gradeable)
    score_raw = (sum(m.weight * m.score for m in gradeable) / wsum
                if wsum > 0 else None)
    graded = sum(1 for m in members if m.status not in ("N/A", "NOT EVALUATED"))
    return CategoryScore(cat_id, name, weight_nominal,
                         weight_nominal if score_raw is not None else 0.0,
                         score_raw, score_raw, None, members, graded, len(members))


def _letter(score: float, spec: dict) -> str:
    for band in spec["grade_bands"]["bands"]:
        if score >= band["min"]:
            return band["letter"]
    return "F"


def _top_factors(categories: list, category_weight_sum: float) -> list:
    """points_lost_vs_100 = (category weight share) x (member weight share
    within its category) x (100 - member score), summed to <= 100 across a
    fully-graded card."""
    out = []
    for cat in categories:
        if not cat.members or cat.weight_used <= 0:
            continue
        gradeable = [m for m in cat.members if m.score is not None and m.weight > 0]
        wsum = sum(m.weight for m in gradeable)
        if wsum <= 0:
            continue
        cat_share = cat.weight_used / category_weight_sum if category_weight_sum else 0.0
        for m in gradeable:
            member_share = m.weight / wsum
            pts_lost = cat_share * member_share * (100.0 - m.score)
            if pts_lost > 1e-6:
                out.append((round(pts_lost, 2), m.check_id, m.offender_count))
    out.sort(key=lambda t: -t[0])
    return out


# ============================================================================
# RC2 — score() : per-schedule (file) card
# ============================================================================
def _is_baseline(sched) -> bool:
    for a in sched.real_activities:
        if a.completed or a.in_progress or a.actual_start is not None:
            return False
    return True


def _profile_weights(spec: dict, profile: str) -> dict:
    profiles = spec["profiles"]
    upd = dict(profiles["update"]["weights"])
    if profile == "update":
        return upd
    # baseline: redistribute execution_performance's weight pro-rata across
    # the target categories by their own update-profile weight
    b = profiles["baseline"]
    src = b["redistribute_from"]
    targets = b["redistribute_to"]
    extra = upd.pop(src, 0.0)
    tsum = sum(upd[t] for t in targets)
    out = dict(upd)
    for t in targets:
        out[t] = upd[t] + (extra * upd[t] / tsum if tsum else 0.0)
    out[src] = 0.0
    return out


def score(assessment: ScheduleAssessment, spec: Optional[dict] = None,
         variant: str = "standard") -> FileCard:
    spec = spec or load_spec()
    matrix_by_id = {c.id: c for c in load_matrix()}
    overrides = spec.get("curve_overrides", {})
    profile = "baseline" if _is_baseline(assessment.schedule) else "update"
    weights = _profile_weights(spec, profile)

    categories = []
    for cdef in spec["categories"]:
        cid = cdef["id"]
        w = weights.get(cid, 0.0)
        members = []
        for check_id in cdef["members"]:
            cd = matrix_by_id.get(check_id)
            if cd is None:
                continue
            result = assessment.result(check_id)
            members.append(_score_result(cd, result, spec, overrides))
        categories.append(_aggregate_category(cid, cdef["name"], w, members))

    # gates -----------------------------------------------------------------
    gates_tripped: list[GateTrip] = []
    by_cat = {c.id: c for c in categories}

    def member_score(check_id: str) -> Optional[float]:
        for c in categories:
            for m in c.members:
                if m.check_id == check_id:
                    return m.score
        return None

    def member_value(check_id: str) -> Optional[float]:
        for c in categories:
            for m in c.members:
                if m.check_id == check_id:
                    return m.value
        return None

    for g in spec["gates"]:
        tripped = False
        if g["id"] == "gate_status_integrity":
            s9, s1 = member_score("DCMA-09"), member_score("DAT-01")
            tripped = (s9 is not None and s9 <= _EPS) or (s1 is not None and s1 <= _EPS)
        elif g["id"] == "gate_logic_continuity":
            v12 = member_value("DCMA-12")
            tripped = v12 is not None and v12 > 0
        if tripped:
            gt = GateTrip(g["id"], g["name"], g["trigger"],
                         dict(g.get("category_caps") or {}), g.get("overall_cap"))
            gates_tripped.append(gt)
            for cid, cap in gt.category_caps.items():
                c = by_cat.get(cid)
                if c and c.score is not None:
                    c.gate_cap = cap
                    c.score = min(c.score, cap)

    weight_sum = sum(c.weight_used for c in categories if c.score is not None)
    overall_raw = (sum(c.score * c.weight_used for c in categories if c.score is not None)
                  / weight_sum) if weight_sum else 0.0
    overall = overall_raw
    for gt in gates_tripped:
        if gt.overall_cap is not None:
            overall = min(overall, gt.overall_cap)

    graded = sum(c.graded for c in categories)
    total = sum(c.total for c in categories)
    top = _top_factors(categories, weight_sum)

    card = FileCard(
        schedule_label=assessment.schedule.label(), profile=profile,
        spec_version=spec["spec_version"], spec_sha256=spec["_sha256"],
        categories=categories, overall_raw=overall_raw,
        overall=overall, letter=_letter(overall, spec),
        gates=gates_tripped, coverage_graded=graded, coverage_total=total,
        top_factors=top, variant=variant,
    )
    if variant == "internal":
        card.internal_indices = [
            {"id": nid, **ndef} for nid, ndef in spec["internal_variant"]["members"].items()]
    return card


# ============================================================================
# RC2 — score_series() : series card
# ============================================================================
def _li02_score(sa: SeriesAnalysis, override: dict) -> tuple:
    """Design-specified LHL mapping (branches on churn, per ported audit
    rulings L1 + L10, v0.4.5).  Offender count = relationship deaths
    (changed ties).

    - Months basis unavailable (missing / non-increasing data dates):
      UNGRADEABLE — never scored by any branch (previously, a reached median
      with no usable dates fell into the censoring branch and could score
      100 on a maximally churning series).
    - Median reached: piecewise curve on median months.
    - Median not reached: 100 when fewer than ``deaths_pass_threshold`` of
      relationships DIED (the network is too stable to estimate a
      half-life); else the 70-point placeholder.  (The prior branch tested
      the CENSORED fraction — inverted vs its own published rationale; a
      frozen network scored 70.)  The value reported alongside a not-reached
      score is the longest-follow-up lower bound.
    """
    try:
        from .analytics.li_record import run_li_record
        lhl = run_li_record(sa).lhl
    except Exception:
        return None, None, 0
    ov = lhl.overall
    if not ov or not ov.n:
        return None, None, 0
    deaths = ov.n - ov.censored
    if ov.median_months is None:
        return None, None, deaths          # no valid day/months basis: ungradeable
    if ov.median_reached:
        return ov.median_months, _piecewise_score(ov.median_months, override["points"]), deaths
    deaths_frac = deaths / ov.n
    if deaths_frac < override.get("deaths_pass_threshold", 0.10):
        return ov.median_months, 100.0, deaths
    return ov.median_months, override.get("not_reached_partial_score", 70.0), deaths


def _li08_score(sa: SeriesAnalysis, override: dict) -> tuple:
    """Design-specified Intervention Latency mapping (branches on whether a
    median was observed vs. unresolved-only vs. no events)."""
    try:
        from .analytics.li_record import run_li_record
        il = run_li_record(sa).il
    except Exception:
        return None, None, 0
    if il.median_il_updates is not None:
        return (il.median_il_updates,
               _piecewise_score(il.median_il_updates, override["points"]),
               il.unresolved_count)
    if il.unresolved_count > 0:
        return None, override.get("unresolved_only_score", 20.0), il.unresolved_count
    return None, None, 0


def _spec_cadence(sa: SeriesAnalysis, override: dict) -> tuple:
    try:
        from .intake.scorecard import build_scorecard
        sc = build_scorecard(sa)
        if not sc.intervals_days:
            return None, None, 0
        frac = len(sc.gaps) / len(sc.intervals_days)
        return frac, _piecewise_score(frac, override["points"]), len(sc.gaps)
    except Exception:
        return None, None, 0


def _spec_evergreen(sa: SeriesAnalysis, override: dict) -> tuple:
    try:
        from .intake.evergreen import find_evergreen_activities
        r = find_evergreen_activities(sa)
        pop = len(sa.schedules[-1].real_activities) if sa.schedules else 0
        if not pop:
            return None, None, 0
        pct = 100.0 * len(r.activities) / pop
        return pct, _piecewise_score(pct, override["points"]), len(r.activities)
    except Exception:
        return None, None, 0


def _spec_tspi(sa: SeriesAnalysis, override: dict) -> tuple:
    try:
        from .analytics.earned_schedule import earned_schedule
        r = earned_schedule(sa)
        pts = [p for p in r.points if p.tspi_t is not None]
        if not pts:
            return None, None, 0
        v = pts[-1].tspi_t
        offenders = sum(1 for p in pts if p.tspi_t is not None and p.tspi_t > 1.10)
        return v, _piecewise_score(v, override["points"]), offenders
    except Exception:
        return None, None, 0


def _dat04_series(sa: SeriesAnalysis, matrix_by_id, override: dict) -> tuple:
    cd = matrix_by_id.get("DAT-04")
    vals = [a.result("DAT-04").value for a in sa.assessments
           if a.result("DAT-04") and a.result("DAT-04").value is not None]
    if not vals or cd is None:
        return None, None, 0
    v = statistics.mean(vals)
    offenders = sum(1 for x in vals if cd.threshold is not None and x > cd.threshold)
    return v, _piecewise_score(v, override["points"]), offenders


_NON_MATRIX_HANDLERS = {
    "SPEC-CADENCE": _spec_cadence,
    "SPEC-EVERGREEN": _spec_evergreen,
    "SPEC-TSPI": _spec_tspi,
}
_SPECIAL_HANDLERS = {"LI-02": _li02_score, "LI-08": _li08_score}


def _series_member(check_id: str, sa: SeriesAnalysis, spec: dict,
                   matrix_by_id: dict, weight: float) -> MemberScore:
    override = spec["series_curve_overrides"].get(check_id, {})
    if check_id == "DAT-04":
        value, sc, offenders = _dat04_series(sa, matrix_by_id, override)
        return MemberScore("DAT-04", "Data date currency (series mean)", value,
                           "INFO" if value is not None else "N/A", weight, sc,
                           offenders, override.get("points", []), "matrix",
                           override.get("rationale", ""))
    if check_id in _NON_MATRIX_HANDLERS:
        value, sc, offenders = _NON_MATRIX_HANDLERS[check_id](sa, override)
        name = override.get("name", check_id)
        return MemberScore(check_id, name, value, "INFO" if value is not None else "N/A",
                           weight, sc, offenders, override.get("points", []),
                           "non-matrix", override.get("rationale", ""))
    if check_id in _SPECIAL_HANDLERS:
        value, sc, offenders = _SPECIAL_HANDLERS[check_id](sa, override)
        cd = matrix_by_id.get(check_id)
        name = cd.name if cd else check_id
        return MemberScore(check_id, name, value, "INFO" if value is not None else "N/A",
                           weight, sc, offenders, override.get("points", []), "matrix",
                           override.get("rationale", ""))
    # ordinary series MetricResult
    result = next((r for r in sa.series_results if r.check.id == check_id), None)
    cd = matrix_by_id.get(check_id)
    name = cd.name if cd else check_id
    if result is None or result.value is None:
        return MemberScore(check_id, name, None, result.status if result else "N/A",
                           weight, None, 0, [], "matrix", override.get("rationale", ""))
    points = override.get("points")
    sc = _piecewise_score(result.value, points) if points else None
    return MemberScore(check_id, name, result.value, result.status, weight if points else 0.0,
                       sc, len(result.findings), points or [], "matrix",
                       override.get("rationale", ""))


def _trajectory(file_cards: list, spec: dict) -> TrajectoryScore:
    tspec = spec["trajectory"]
    weight = tspec["weight"]
    levels = [fc.overall for fc in file_cards]
    if not levels:
        return TrajectoryScore(None, None, None, None, weight)
    level = statistics.mean(levels)
    if len(levels) < 2:
        return TrajectoryScore(level, None, None, round(level, 2), weight)
    deltas = [levels[i + 1] - levels[i] for i in range(len(levels) - 1)]
    slope = statistics.mean(deltas)
    slope_score = _piecewise_score(slope, tspec["slope_points"])
    combined = 0.5 * level + 0.5 * slope_score
    return TrajectoryScore(round(level, 2), round(slope, 2), round(slope_score, 2),
                           round(combined, 2), weight)


def score_series(sa: SeriesAnalysis, spec: Optional[dict] = None,
                 variant: str = "standard") -> SeriesCard:
    spec = spec or load_spec()
    matrix_by_id = {c.id: c for c in load_matrix()}
    file_cards = [score(a, spec, variant) for a in sa.assessments]

    if not sa.is_series:
        card = SeriesCard(file_cards=file_cards, spec_version=spec["spec_version"],
                          spec_sha256=spec["_sha256"], variant=variant, is_series=False)
        if file_cards:
            fc = file_cards[-1]
            card.overall_raw, card.overall, card.letter = fc.overall_raw, fc.overall, fc.letter
            card.coverage_graded, card.coverage_total = fc.coverage_graded, fc.coverage_total
            card.top_factors = fc.top_factors
        return card

    categories = []
    for cdef in spec["series_categories"]:
        cid = cdef["id"]
        mweights = cdef.get("member_weights", {})
        members = [_series_member(mid, sa, spec, matrix_by_id, mweights.get(mid, 1.0))
                  for mid in cdef["members"]]
        cat = _aggregate_category(cid, cdef["name"], cdef.get("weight", 0.0), members)
        cat.weight_used = cat.weight_nominal if cat.score is not None else 0.0
        categories.append(cat)

    trajectory = _trajectory(file_cards, spec)
    traj_cat = CategoryScore("trajectory", "File-Quality Trajectory",
                             trajectory.weight,
                             trajectory.weight if trajectory.score is not None else 0.0,
                             trajectory.score, trajectory.score)
    all_categories = categories + [traj_cat]

    # series gate -------------------------------------------------------
    gates_tripped: list[GateTrip] = []
    g = spec["series_gate"]
    trd05 = next((m for c in categories for m in c.members if m.check_id == "TRD-05"), None)
    if trd05 is not None and trd05.value is not None and trd05.value > 0:
        gt = GateTrip(g["id"], g["name"], g["trigger"], dict(g.get("category_caps") or {}),
                     g.get("overall_cap"))
        gates_tripped.append(gt)
        by_id = {c.id: c for c in all_categories}
        for cid, cap in gt.category_caps.items():
            c = by_id.get(cid)
            if c and c.score is not None:
                c.gate_cap = cap
                c.score = min(c.score, cap)

    weight_sum = sum(c.weight_used for c in all_categories if c.score is not None)
    overall_raw = (sum(c.score * c.weight_used for c in all_categories if c.score is not None)
                  / weight_sum) if weight_sum else 0.0
    overall = overall_raw
    for gt in gates_tripped:
        if gt.overall_cap is not None:
            overall = min(overall, gt.overall_cap)

    graded = sum(c.graded for c in categories)   # trajectory isn't a "check"
    total = sum(c.total for c in categories)
    top = _top_factors(categories, weight_sum)   # trajectory excluded from
                                                  # check-level top factors

    card = SeriesCard(
        file_cards=file_cards, spec_version=spec["spec_version"],
        spec_sha256=spec["_sha256"], series_categories=categories,
        trajectory=trajectory, overall_raw=overall_raw,
        overall=overall, letter=_letter(overall, spec),
        gates=gates_tripped, coverage_graded=graded, coverage_total=total,
        top_factors=top, variant=variant, is_series=True,
    )
    if variant == "internal":
        card.internal_indices = [
            {"id": nid, **ndef} for nid, ndef in spec["internal_variant"]["members"].items()]
    return card


# ============================================================================
# RC2 — score_trace()
# ============================================================================
def _member_trace(m: MemberScore) -> dict:
    return {"check_id": m.check_id, "name": m.name, "value": m.value,
           "status": m.status, "weight": m.weight, "score": m.score,
           "offender_count": m.offender_count, "curve_points": m.curve_points,
           "source": m.source, "contribution": (m.weight * m.score
                                                if m.score is not None else 0.0)}


def _category_trace(c: CategoryScore) -> dict:
    return {"id": c.id, "name": c.name, "weight_nominal": c.weight_nominal,
           "weight_used": c.weight_used, "score_raw": c.score_raw,
           "score": c.score, "gate_cap": c.gate_cap, "graded": c.graded,
           "total": c.total, "members": [_member_trace(m) for m in c.members]}


def _file_card_trace(card: FileCard) -> dict:
    return {
        "kind": "file", "schedule_label": card.schedule_label,
        "profile": card.profile, "variant": card.variant,
        "spec_version": card.spec_version, "spec_sha256": card.spec_sha256,
        "categories": [_category_trace(c) for c in card.categories],
        "category_weight_sum": sum(c.weight_used for c in card.categories
                                   if c.score is not None),
        "overall_raw": card.overall_raw,
        "gates_tripped": [{"id": g.id, "name": g.name, "rule_text": g.rule_text,
                          "category_caps": g.category_caps,
                          "overall_cap": g.overall_cap} for g in card.gates],
        "overall_gate_cap": min([g.overall_cap for g in card.gates
                                if g.overall_cap is not None], default=None),
        "overall": card.overall, "letter": card.letter,
        "coverage": {"graded": card.coverage_graded, "total": card.coverage_total},
        "top_factors": card.top_factors,
        "internal_indices": card.internal_indices,
    }


def score_trace(card) -> dict:
    if isinstance(card, FileCard):
        return _file_card_trace(card)
    trace = {
        "kind": "series", "variant": card.variant, "spec_version": card.spec_version,
        "spec_sha256": card.spec_sha256, "is_series": card.is_series,
        "file_cards": [_file_card_trace(fc) for fc in card.file_cards],
    }
    if not card.is_series:
        trace.update({"overall": card.overall, "letter": card.letter,
                      "coverage": {"graded": card.coverage_graded,
                                  "total": card.coverage_total},
                      "top_factors": card.top_factors})
        return trace
    all_cats = list(card.series_categories)
    traj = card.trajectory
    traj_trace = {"id": "trajectory", "name": "File-Quality Trajectory",
                 "level": traj.level, "slope": traj.slope,
                 "slope_score": traj.slope_score, "score": traj.score,
                 "weight": traj.weight}
    trace["series_categories"] = [_category_trace(c) for c in all_cats]
    trace["trajectory"] = traj_trace
    trace["category_weight_sum"] = (
        sum(c.weight_used for c in all_cats if c.score is not None)
        + (traj.weight if traj.score is not None else 0.0))
    trace["overall_raw"] = card.overall_raw
    trace["gates_tripped"] = [{"id": g.id, "name": g.name, "rule_text": g.rule_text,
                              "category_caps": g.category_caps,
                              "overall_cap": g.overall_cap} for g in card.gates]
    trace["overall_gate_cap"] = min([g.overall_cap for g in card.gates
                                     if g.overall_cap is not None], default=None)
    trace["overall"] = card.overall
    trace["letter"] = card.letter
    trace["coverage"] = {"graded": card.coverage_graded, "total": card.coverage_total}
    trace["top_factors"] = card.top_factors
    trace["internal_indices"] = card.internal_indices
    return trace


def write_trace(card, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score_trace(card), f, indent=2, default=str)
    return path
