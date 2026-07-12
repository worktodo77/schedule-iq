"""Wave-0 wiring regressions (docs/audit/LI-02-10_audit_matrix_2026-07-12.md
FR1 / W1 / W2).

Every test here drives ``li_series_results`` (the wiring), NOT the metric
layer — the FR1 class of defect lived exactly between a correct metric and
the scored/reported surface, which is why metric-layer tests never caught it
(non-circularity rule D2).
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,  # noqa: E402
                                     Relationship, ResourceAssignment,
                                     Schedule, WbsNode)
from scheduleiq.compare.diff import compare                                   # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis                            # noqa: E402
from scheduleiq.analytics.li_wiring import li_series_results                  # noqa: E402
from scheduleiq.metrics.engine import load_matrix                             # noqa: E402

H = 8.0
ALL_LI = {f"LI-{i:02d}" for i in range(1, 11)}


def _a(uid, code, tf, *, atype=ActivityType.TASK,
       status=ActivityStatus.NOT_STARTED, od=10, rem=10, ef=None, af=None,
       wbs=None, res=None):
    a = Activity(uid=uid, code=code, atype=atype, status=status,
                 total_float_hours=None if tf is None else tf * H,
                 original_duration_hours=od * H, remaining_duration_hours=rem * H,
                 early_start=(ef - timedelta(days=od)) if ef else None,
                 early_finish=ef, actual_finish=af, wbs_uid=wbs)
    if res:
        a.resources = res
    return a


def _m(uid, code, tf=0.0, ef=None):
    return _a(uid, code, tf, atype=ActivityType.FINISH_MILESTONE, od=0, rem=0, ef=ef)


def _s(dd, acts, rels, wbs=None):
    sc = Schedule(project_id="P", data_date=dd,
                  activities={a.uid: a for a in acts})
    sc.relationships = list(rels)
    if wbs:
        sc.wbs = {n.uid: n for n in wbs}
    return sc


def _sa(scheds):
    css = [compare(scheds[i], scheds[i + 1]) for i in range(len(scheds) - 1)]
    return SeriesAnalysis(schedules=scheds, changesets=css)


@pytest.fixture(scope="module")
def matrix():
    return load_matrix()


def _by_id(sa, matrix):
    return {r.check.id: r for r in li_series_results(sa, matrix) if r}


# ---------------------------------------------------------------- FR1 (LI-03)
def test_fr1_li03_band_width_is_real_not_fabricated_zero(matrix):
    """Two resolved forecasts with working-day errors {0, +10}: the 0-30d
    bucket reads P10=1.0 / P90=9.0 (linear-interpolated percentiles), so the
    wired LI-03 value must be exactly 8.0 — not the fabricated 0 the old
    getattr(b, "p90", 0) - getattr(b, "p10", 0) read produced."""
    dd = datetime(2025, 1, 13, 8)
    f = datetime(2025, 2, 3, 17)                      # horizon 21d -> 0-30d bucket
    fin = datetime(2025, 12, 1, 17)
    e_acts = [_a("F0", "F0", 5.0, ef=f), _a("F1", "F1", 5.0, ef=f),
              _m("T", "T", ef=fin)]
    l_acts = [_a("F0", "F0", 5.0, ef=None, af=f, rem=0,
                 status=ActivityStatus.COMPLETED),
              _a("F1", "F1", 5.0, ef=None, af=f + timedelta(days=14), rem=0,
                 status=ActivityStatus.COMPLETED),   # +10 working days
              _m("T", "T", ef=fin)]
    rels = [Relationship("F0", "T"), Relationship("F1", "T")]
    sa = _sa([_s(dd, e_acts, rels), _s(datetime(2025, 3, 3, 8), l_acts, rels)])
    res = _by_id(sa, matrix)

    li03 = res["LI-03"]
    assert li03.value == pytest.approx(8.0)
    assert "width 8 working days" in li03.narrative
    detail = li03.findings[0].detail
    assert "bias +5.0d" in detail and "P10 +1.0d" in detail and "P90 +9.0d" in detail
    # the FR1 signature (fabricated zeros) must never reappear
    assert "bias +0.0d, band P10 +0.0d" not in detail

    # cross-check against the metric layer (the independent oracle)
    from scheduleiq.analytics.li_record import forecast_reliability_band
    frb = forecast_reliability_band(sa)
    b = next(x for x in frb.buckets if x.n > 0)
    assert li03.value == pytest.approx(b.p90_days - b.p10_days)


# ------------------------------------------------------------------ W1 (None)
def test_w1_none_pci_window_degrades_one_cell_not_all_ten(matrix):
    """A schedule with no relationships yields a None PCI window; that must
    render as an em dash in one finding — not raise and blank all ten
    indices via the pipeline's blanket guard."""
    dd = datetime(2025, 1, 6, 8)
    s0 = _s(dd, [_a("X", "X", 0.0, ef=dd + timedelta(days=30)),
                 _m("T", "T", ef=dd + timedelta(days=30))], [])
    s1 = _s(dd + timedelta(days=28),
            [_a("X", "X", 0.0, ef=dd + timedelta(days=30)),
             _m("T", "T", ef=dd + timedelta(days=30))],
            [Relationship("X", "T")])
    res = _by_id(_sa([s0, s1]), matrix)
    assert set(res) == ALL_LI
    li04 = res["LI-04"]
    assert any("PCI —" in f.detail for f in li04.findings)
    assert not any("wiring degraded" in r.narrative for r in res.values())


def test_w1_none_bwi_density_row_renders_dash(matrix):
    """A BWI target with no usable finish in a later update yields a None
    density/bwi row; the finding renders dashes instead of raising.  (The
    original Wave-0 fixture used a re-code to produce the None row; the
    ported B2 UID pinning now survives a re-code — the intended improvement —
    so the None row is produced by a lost finish date instead.)"""
    dd = datetime(2025, 1, 6, 8)
    w0 = _a("W", "W", 2.0, ef=datetime(2025, 5, 30, 17))
    t0 = _m("MS", "MS", ef=datetime(2025, 6, 1, 17))
    t1 = _m("MS", "MS", ef=None)                     # finish lost in update 2
    s0 = _s(dd, [w0, t0], [Relationship("W", "MS")])
    s1 = _s(datetime(2025, 2, 6, 8), [w0, t1], [Relationship("W", "MS")])
    res = _by_id(_sa([s0, s1]), matrix)
    assert set(res) == ALL_LI
    li09 = res["LI-09"]
    assert any("density —; BWI —" in f.detail for f in li09.findings)


# ------------------------------------------------------------------ W2 (text)
def _rdi_capable_series():
    dd = datetime(2025, 1, 6, 8)
    fin = datetime(2025, 12, 31, 17)
    mk = lambda d: _s(d, [_a("X", "X", 0.0, ef=fin), _m("T", "T", ef=fin)],
                      [Relationship("X", "T")])
    s0, s1 = mk(dd), mk(dd + timedelta(days=28))
    s0.finish_date = s1.finish_date = fin
    return _sa([s0, s1])


def test_w2_li05_findings_carry_real_required_pace(matrix):
    res = _by_id(_rdi_capable_series(), matrix)
    details = [f.detail for f in res["LI-05"].findings]
    # required pace = 10 remaining days / working days to the project finish —
    # nonzero; the old getattr(row, "required", 0) printed 0.00 and the old
    # getattr(row, "demonstrated", None) printed nan
    assert details and not any("required 0.00 vs demonstrated nan" in d
                               for d in details)
    assert any("demonstrated —" in d or "demonstrated 0." in d for d in details)
    assert not any(" nan" in d for d in details)


def test_w2_li07_findings_carry_real_dwell_share(matrix):
    res = _by_id(_rdi_capable_series(), matrix)
    details = [f.detail for f in res["LI-07"].findings]
    assert details
    # X and T split each update's unit of dwell; shares must be real numbers,
    # not the fabricated 0.0% of getattr(e, "share", 0)
    assert any("dwell share 50.0%" in d for d in details)


def test_w2_li10_basis_is_named_not_question_mark(matrix):
    dd0, dd1, dd2 = (datetime(2025, 1, 6, 8), datetime(2025, 2, 3, 8),
                     datetime(2025, 3, 3, 8))
    root = WbsNode(uid="R", parent_uid=None, code="ROOT", name="root")
    civ = WbsNode(uid="W1", parent_uid="R", code="CIV", name="civil")

    def act(uid, au):
        return _a(uid, uid, 5.0, wbs="W1", ef=dd2 + timedelta(days=30),
                  res=[ResourceAssignment(activity_uid=uid, resource_uid="r1",
                                          actual_units=au)])

    s0 = _s(dd0, [act("A", 0.0)], [], wbs=[root, civ])
    s1 = _s(dd1, [act("A", 100.0)], [], wbs=[root, civ])
    s2 = _s(dd2, [act("A", 250.0)], [], wbs=[root, civ])
    res = _by_id(_sa([s0, s1, s2]), matrix)
    details = [f.detail for f in res["LI-10"].findings]
    assert details
    assert all("basis ?" not in d for d in details)
    assert any("basis resource" in d for d in details)


# ------------------------------------------------------- per-index isolation
def test_one_bundle_failure_degrades_its_indices_only(matrix, monkeypatch):
    """If run_li_record ever raised, its five indices must degrade with a
    reasoned placeholder while the five li_indices-backed rows still report
    (the old blanket guard in trend/series dropped all ten)."""
    import scheduleiq.analytics.li_record as li_record

    def boom(sa, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(li_record, "run_li_record", boom)
    res = _by_id(_rdi_capable_series(), matrix)
    assert set(res) == ALL_LI
    degraded = {cid for cid, r in res.items() if "wiring degraded" in r.narrative}
    assert degraded == {"LI-02", "LI-03", "LI-06", "LI-08", "LI-10"}
    for cid in degraded:
        assert res[cid].value is None
    assert res["LI-05"].narrative and "wiring degraded" not in res["LI-05"].narrative
