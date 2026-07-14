"""R-ID family identity regression tests.

These tests lock the portable UID-first delta while keeping activity codes as
display labels. A stable UID re-code must survive every affected LI metric;
different present UIDs are a true replacement and remain unmatched.
"""
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scheduleiq.analytics import li_record as lr
from scheduleiq.analytics.li_record import (baseline_dilution_index,
                                             forecast_reliability_band,
                                             intervention_latency,
                                             measured_mile_locator)
from scheduleiq.analytics.paths import DrivingPath, PathStep
from scheduleiq.compare.diff import compare
from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,
                                      Calendar, Relationship, RelType,
                                      ResourceAssignment, Schedule, WbsNode)
from scheduleiq.trend.series import SeriesAnalysis


CAL = Calendar(uid="cal", name="5d", hours_per_day=8.0, is_default=True)


def _act(uid, code, *, status=ActivityStatus.NOT_STARTED, tf=0.0,
         original=80.0, remaining=None, early_finish=None,
         actual_finish=None, wbs_uid=None, resources=None):
    remaining = original if remaining is None else remaining
    return Activity(
        uid=uid, code=code, name=code, atype=ActivityType.TASK,
        status=status, calendar_uid="cal", wbs_uid=wbs_uid,
        original_duration_hours=original, remaining_duration_hours=remaining,
        total_float_hours=tf,
        early_start=datetime(2025, 1, 1),
        early_finish=early_finish or datetime(2025, 2, 1),
        planned_start=datetime(2025, 1, 1),
        planned_finish=early_finish or datetime(2025, 2, 1),
        actual_finish=actual_finish,
        resources=list(resources or []),
    )


def _sched(acts, dd):
    s = Schedule(project_id="R-ID", data_date=dd,
                 calendars={"cal": CAL})
    for act in acts:
        s.activities[act.uid or act.code] = act
    return s


def test_shared_register_matches_uid_recode_and_rejects_replacement():
    e = _sched([_act("u1", "A", original=80), _act("u2", "B")],
               datetime(2025, 1, 1))
    e.relationships = [Relationship("u1", "u2", RelType.FS)]
    renamed = _sched([_act("u1", "A-RENAMED", original=40), _act("u2", "B")],
                     datetime(2025, 2, 1))
    renamed.relationships = [Relationship("u1", "u2", RelType.FS)]

    cs = compare(e, renamed)
    assert not cs.added and not cs.deleted
    assert not cs.logic_changes
    assert cs.duration_changes and cs.duration_changes[0].uid == "u1"
    assert cs.duration_changes[0].code == "A-RENAMED"

    replacement = _sched([_act("u-new", "A"), _act("u2", "B")],
                          datetime(2025, 2, 1))
    replacement.relationships = [Relationship("u-new", "u2", RelType.FS)]
    replaced = compare(e, replacement)
    assert {a.uid for a in replaced.deleted} == {"u1"}
    assert {a.uid for a in replaced.added} == {"u-new"}


def test_frb_resolves_recode_by_uid():
    source = _sched([_act("u1", "A", early_finish=datetime(2025, 1, 8))],
                    datetime(2025, 1, 1))
    resolved = _sched([_act("u1", "A-RENAMED",
                             status=ActivityStatus.COMPLETED,
                             remaining=0,
                             actual_finish=datetime(2025, 1, 9))],
                      datetime(2025, 1, 10))
    frb = forecast_reliability_band(SeriesAnalysis([source, resolved]))
    assert len(frb.observations) == 1
    assert frb.observations[0].code == "A"


def test_bdi_keeps_uid_recode_baseline_original(monkeypatch):
    baseline = _sched([_act("u1", "A")], datetime(2025, 1, 1))
    latest = _sched([_act("u1", "A-RENAMED")], datetime(2025, 2, 1))
    step = PathStep(activity=latest.activities["u1"], driving_rel=None,
                     lag_hours=0.0, calendar_name="5d", constraint="",
                     total_float_days=0.0, pct_complete=0.0)
    monkeypatch.setattr(lr, "driving_path",
                        lambda _schedule: DrivingPath(steps=[step]))
    bdi = baseline_dilution_index(SeriesAnalysis([baseline, latest]))
    assert bdi.steps[0].baseline_original is True
    assert bdi.bdi_pct == 0.0


def test_il_response_survives_uid_recode():
    emergence = _sched([_act("u1", "A", tf=0.0)], datetime(2025, 1, 1))
    negative = _sched([_act("u1", "A-RENAMED", tf=-8.0)],
                      datetime(2025, 2, 1))
    response = _sched([_act("u1", "A-RENAMED", tf=-8.0, original=40.0)],
                      datetime(2025, 3, 1))
    sa = SeriesAnalysis(
        [emergence, negative, response],
        changesets=[compare(emergence, negative), compare(negative, response)],
    )
    il = intervention_latency(sa)
    assert len(il.events) == 1
    assert il.events[0].chain_codes == ["A-RENAMED"]
    assert il.events[0].response_pair_index == 1
    assert "duration decrease" in il.events[0].response_detail


def test_mml_resolves_recode_by_uid():
    root = WbsNode(uid="root", parent_uid=None, code="ROOT", name="Root")
    node = WbsNode(uid="w1", parent_uid="root", code="W1", name="Work")
    earlier = _sched([_act("u1", "A", wbs_uid="w1")], datetime(2025, 1, 1))
    later = _sched([_act(
        "u1", "A-RENAMED", wbs_uid="w1",
        status=ActivityStatus.COMPLETED, remaining=0,
        actual_finish=datetime(2025, 1, 9),
        resources=[ResourceAssignment(activity_uid="u1", resource_uid="r1",
                                      actual_units=10.0)],
    )], datetime(2025, 1, 10))
    earlier.wbs = {"root": root, "w1": node}
    later.wbs = {"root": root, "w1": node}
    mml = measured_mile_locator(SeriesAnalysis([earlier, later]))
    row = mml.wbs_results[0]
    assert row.windows[0].basis == "resource"
    assert row.windows[0].productivity is not None
    assert row.windows[0].productivity > 0.0
