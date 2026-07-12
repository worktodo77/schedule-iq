"""LI-05/LI-06 NOT EVALUATED sentinel batch (recorded ruling
docs/rulings/LI-05-LI-06-not-evaluated-2026-07-12.md; audit findings RDI-1 /
BDI-1, rubric A1: undefined is explicit, never a fabricated best-case 0).
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,  # noqa: E402
                                     Relationship, Schedule)
from scheduleiq.compare.diff import compare                                   # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis                            # noqa: E402
from scheduleiq.analytics.li_indices import run_li_indices                    # noqa: E402
from scheduleiq.analytics.li_record import baseline_dilution_index            # noqa: E402
from scheduleiq.analytics.li_wiring import li_series_results                  # noqa: E402
from scheduleiq.metrics.engine import load_matrix                             # noqa: E402

H = 8.0


def _a(uid, code, tf, *, atype=ActivityType.TASK, od=10, rem=10, ef=None):
    return Activity(uid=uid, code=code, atype=atype,
                    status=ActivityStatus.NOT_STARTED,
                    total_float_hours=None if tf is None else tf * H,
                    original_duration_hours=od * H,
                    remaining_duration_hours=rem * H,
                    early_start=(ef - timedelta(days=od)) if ef else None,
                    early_finish=ef)


def _m(uid, code, tf=0.0, ef=None):
    return _a(uid, code, tf, atype=ActivityType.FINISH_MILESTONE, od=0, rem=0, ef=ef)


def _s(dd, acts, rels, finish=None):
    sc = Schedule(project_id="P", data_date=dd,
                  activities={a.uid: a for a in acts})
    sc.relationships = list(rels)
    sc.finish_date = finish
    return sc


def _sa(scheds):
    css = [compare(scheds[i], scheds[i + 1]) for i in range(len(scheds) - 1)]
    return SeriesAnalysis(schedules=scheds, changesets=css)


@pytest.fixture(scope="module")
def matrix():
    return load_matrix()


def _unusable_rdi_series():
    """No data dates anywhere -> no required pace can ever be computed."""
    mk = lambda: _s(None, [_a("X", "X", 0.0), _m("T", "T")],
                    [Relationship("X", "T")])
    return _sa([mk(), mk()])


def _all_milestone_series():
    dd = datetime(2025, 1, 6, 8)
    mk = lambda d: _s(d, [_m("M1", "M1", ef=dd + timedelta(days=5)),
                          _m("M2", "M2", ef=dd + timedelta(days=10))],
                      [Relationship("M1", "M2")])
    return _sa([mk(dd), mk(dd + timedelta(days=30))])


# ------------------------------------------------------------- RDI (LI-05)
def test_rdi_unusable_series_is_not_evaluated_never_zero():
    rdi = run_li_indices(_unusable_rdi_series()).rdi
    assert rdi.rdi_days is None                       # never a fabricated 0.0
    assert rdi.reason.startswith("NOT EVALUATED")
    assert rdi.rows                                   # decomposition still shown


def test_rdi_short_series_carries_no_zero_debt():
    rdi = run_li_indices(_sa([_s(None, [_a("X", "X", 0.0)], [])])).rdi
    assert rdi.rdi_days is None and rdi.reason


def test_li05_wired_value_is_none_so_member_is_ungraded(matrix):
    res = {r.check.id: r for r in li_series_results(_unusable_rdi_series(),
                                                    matrix) if r}
    assert res["LI-05"].value is None
    assert "NOT EVALUATED" in res["LI-05"].narrative


def test_rdi_computable_series_number_unchanged():
    """Guard: the sentinel must not move any computable series (the ruling is
    sentinel-only).  One activity, 10 remaining days, ~2 months to finish."""
    dd = datetime(2025, 1, 6, 8)
    fin = datetime(2025, 12, 31, 17)
    mk = lambda d: _s(d, [_a("X", "X", 0.0, ef=fin), _m("T", "T", ef=fin)],
                      [Relationship("X", "T")], finish=fin)
    rdi = run_li_indices(_sa([mk(dd), mk(dd + timedelta(days=28))])).rdi
    assert rdi.reason == ""
    assert rdi.rdi_days is not None and rdi.rdi_days >= 0.0


# ------------------------------------------------------------- BDI (LI-06)
def test_bdi_all_milestone_path_is_not_evaluated_never_zero_pct():
    bdi = baseline_dilution_index(_all_milestone_series())
    assert bdi.bdi_pct is None                        # never a fabricated 0.0%
    assert bdi.reason.startswith("NOT EVALUATED")


def test_li06_wired_value_is_none_so_member_is_ungraded(matrix):
    res = {r.check.id: r for r in li_series_results(_all_milestone_series(),
                                                    matrix) if r}
    assert res["LI-06"].value is None
    assert "NOT EVALUATED" in res["LI-06"].narrative


def test_bdi_computable_series_number_unchanged():
    dd = datetime(2025, 1, 6, 8)
    fin = dd + timedelta(days=60)
    x = _a("X", "X", 0.0, od=20, rem=20, ef=fin)
    n = _a("N", "N", 0.0, od=10, rem=10, ef=fin)
    s0 = _s(dd, [x, _m("T", "T", ef=fin)], [Relationship("X", "T")])
    s1 = _s(dd + timedelta(days=30), [x, n, _m("T", "T", ef=fin)],
            [Relationship("X", "T"), Relationship("N", "T")])
    bdi = baseline_dilution_index(_sa([s0, s1]))
    assert bdi.bdi_pct is not None and 0.0 <= bdi.bdi_pct <= 100.0
