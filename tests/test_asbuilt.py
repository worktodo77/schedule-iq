"""Tests for as-built path reconstruction (ANALYTICS_PROPOSAL.md §2 item 6).

Schedules are built IN MEMORY (ingest-model objects direct — no XER round-trip).
Every workday number asserted below is hand-computed in the comments against a
Mon-Fri 8h calendar anchored on Mon 2025-01-06.

Workday numbering used throughout (Mon-Fri, weekends skipped):
    Jan 06 Mon = 1   Jan 07 Tue = 2   Jan 08 Wed = 3   Jan 09 Thu = 4
    Jan 10 Fri = 5   (11-12 weekend) Jan 13 Mon = 6   Jan 14 Tue = 7
    Jan 15 Wed = 8   Jan 16 Thu = 9   Jan 17 Fri = 10  (18-19 weekend)
    Jan 20 Mon = 11  Jan 21 Tue = 12  Jan 22 Wed = 13
Lag differences are origin-independent, so only the spacing matters.
"""
import os
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest.model import (                                   # noqa: E402
    Activity, ActivityStatus, ActivityType, Calendar, RelType,
    Relationship, Schedule, WorkPattern)
from scheduleiq.analytics.asbuilt import (                              # noqa: E402
    reconstruct_asbuilt_paths, AsBuiltReconstruction, LABEL)


# ---------------------------------------------------------------------------
# in-memory builders
# ---------------------------------------------------------------------------
def _dt(y, m, d):
    return datetime(y, m, d, 8, 0)


def cal5(uid="C5", default=True):
    """Mon-Fri 8h (empty work_patterns -> bridge defaults to Mon-Fri)."""
    return Calendar(uid=uid, name="5-Day", hours_per_day=8.0, is_default=default)


def cal7(uid="C7"):
    """7-day, 10h calendar (all seven weekdays working, 10h spans)."""
    wp = {i: WorkPattern(weekday=i, spans=[("08:00", "18:00")]) for i in range(1, 8)}
    return Calendar(uid=uid, name="7-Day-10h", hours_per_day=10.0, work_patterns=wp)


def act(uid, code=None, cal="C5", status="C", AS=None, AF=None,
        atype=ActivityType.TASK):
    st = {"C": ActivityStatus.COMPLETED, "P": ActivityStatus.IN_PROGRESS,
          "N": ActivityStatus.NOT_STARTED}[status]
    return Activity(uid=uid, code=code or uid, atype=atype, status=st,
                    calendar_uid=cal, actual_start=AS, actual_finish=AF)


def rel(p, s, rt=RelType.FS, lag_h=0.0):
    return Relationship(pred_uid=p, succ_uid=s, rtype=rt, lag_hours=lag_h)


def sched(acts, rels, cals=None, data_date=_dt(2025, 1, 6)):
    s = Schedule()
    s.data_date = data_date
    for c in (cals or [cal5()]):
        s.calendars[c.uid] = c
    for a in acts:
        s.activities[a.uid] = a
    s.relationships = list(rels)
    return s


# ---------------------------------------------------------------------------
# 1. Linear FS chain, fully actualized, exact planned lags -> tightness 0
# ---------------------------------------------------------------------------
def _linear():
    # A finishes Jan08(wd3); B starts Jan08(wd3) -> FS actual_lag = 3-3 = 0.
    # B finishes Jan10(wd5); C starts Jan10(wd5) -> 5-5 = 0.
    # C finishes Jan14(wd7); D starts Jan14(wd7) -> 7-7 = 0.
    acts = [
        act("A", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("B", AS=_dt(2025, 1, 8), AF=_dt(2025, 1, 10)),
        act("C", AS=_dt(2025, 1, 10), AF=_dt(2025, 1, 14)),
        act("D", AS=_dt(2025, 1, 14), AF=_dt(2025, 1, 16)),
    ]
    rels = [rel("A", "B"), rel("B", "C"), rel("C", "D")]
    return sched(acts, rels)


def test_linear_chain_tightness_zero_and_span():
    r = reconstruct_asbuilt_paths(_linear())
    assert r.label == LABEL
    assert r.end_anchor_code == "D"
    assert "latest actual finish" in r.end_anchor_resolution
    assert len(r.chains) == 1
    chain = r.chains[0]
    assert chain.activity_codes == ["A", "B", "C", "D"]
    assert [l.tightness_wd for l in chain.links] == [0.0, 0.0, 0.0]
    assert all(l.rel_type == "FS" for l in chain.links)
    # span = wd(D.AF=Jan16=9) - wd(A.AS=Jan06=1) = 8 workdays in D's calendar
    assert chain.span_workdays == 8.0
    assert chain.break_reason == "no actualized predecessor link"
    assert r.summary["actualized_relationships"] == 3
    assert r.summary["contradicted_relationships"] == 0
    assert r.summary["actualized_activities"] == 4
    assert r.summary["unreached_started_activities"] == 0
    # every link carries its two anchoring actual dates + the lag calendar
    for l in chain.links:
        assert l.pred_anchor_date and l.succ_anchor_date
        assert l.lag_calendar is not None


# ---------------------------------------------------------------------------
# 2. Merge: tight (0) vs loose (+8) -> chain follows the tight predecessor
# ---------------------------------------------------------------------------
def test_merge_follows_tight_link():
    # Z starts Jan20 (wd11). P finishes Jan20 (wd11) -> FS tightness 11-11 = 0.
    # Q finishes Jan08 (wd3) -> FS actual_lag 11-3 = 8, tightness +8 (loose).
    acts = [
        act("P", AS=_dt(2025, 1, 13), AF=_dt(2025, 1, 20)),
        act("Q", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("Z", AS=_dt(2025, 1, 20), AF=_dt(2025, 1, 22)),
    ]
    rels = [rel("P", "Z"), rel("Q", "Z")]
    r = reconstruct_asbuilt_paths(sched(acts, rels))
    assert r.end_anchor_code == "Z"
    assert len(r.chains) == 1
    chain = r.chains[0]
    assert chain.activity_codes == ["P", "Z"]
    assert "Q" not in chain.activity_codes
    # the loose Q->Z link is absent from the chain but present in link records
    qz = [l for l in r.links if l.pred_code == "Q" and l.succ_code == "Z"]
    assert len(qz) == 1
    assert qz[0].tightness_wd == 8.0
    assert qz[0].actual_lag_wd == 8.0
    assert qz[0].is_gap is True                # +8 wd > default 5 wd gap threshold
    # both consistent links recorded; Q is a started activity never reached
    assert r.summary["actualized_relationships"] == 2
    assert r.summary["unreached_started_activities"] == 1


# ---------------------------------------------------------------------------
# 3. Gap flag: sole predecessor has +7 wd actual lag (> default 5) -> flagged
# ---------------------------------------------------------------------------
def test_gap_flag_continues_but_flags():
    # W finishes Jan06 (wd1). V starts Jan15 (wd8) -> FS actual_lag 8-1 = 7 > 5.
    acts = [
        act("W", AS=_dt(2025, 1, 2), AF=_dt(2025, 1, 6)),
        act("V", AS=_dt(2025, 1, 15), AF=_dt(2025, 1, 17)),
    ]
    rels = [rel("W", "V")]
    r = reconstruct_asbuilt_paths(sched(acts, rels))
    assert r.end_anchor_code == "V"
    chain = r.chains[0]
    # chain still continues through the gap (both activities present)
    assert chain.activity_codes == ["W", "V"]
    assert chain.links[0].tightness_wd == 7.0
    assert chain.links[0].is_gap is True
    assert chain.gap_flags, "gap should be flagged"
    assert "+7" in chain.gap_flags[0]


# ---------------------------------------------------------------------------
# 4. Contradicted logic: FS where succ.AS < pred.AF -> contradicted, not chain
# ---------------------------------------------------------------------------
def test_contradicted_logic_excluded_from_chain():
    # P finishes Jan10 (wd5). S starts Jan06 (wd1) -> FS actual_lag 1-5 = -4 (OOS).
    acts = [
        act("P", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 10)),
        act("S", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
    ]
    rels = [rel("P", "S")]
    # anchor explicitly on S so the contradicted incoming link is seen at a node
    r = reconstruct_asbuilt_paths(sched(acts, rels), end="S")
    assert r.end_anchor_code == "S"
    # the P->S link is contradicted, listed separately, and not an actualized link
    assert r.summary["contradicted_relationships"] == 1
    assert r.summary["actualized_relationships"] == 0
    assert [l.pred_code for l in r.contradicted_links] == ["P"]
    assert r.contradicted_links[0].tightness_wd == -4.0
    assert not r.links
    chain = r.chains[0]
    assert chain.activity_codes == ["S"]
    assert "P" not in chain.activity_codes
    # contradicted link surfaced at the chain node as evidence
    assert [l.pred_code for l in chain.contradicted_links] == ["P"]


# ---------------------------------------------------------------------------
# 5. Multi-calendar: pred 5d/8h, succ 7d/10h, lag counted in pred calendar
# ---------------------------------------------------------------------------
def test_multicalendar_lag_in_predecessor_calendar():
    # Pred P on Mon-Fri; finishes Fri Jan10. Succ S on 7-day; starts Mon Jan13.
    # In the PREDECESSOR (Mon-Fri) calendar the weekend is skipped:
    #   wd(Jan13) - wd(Jan10) = 6 - 5 = 1 workday.
    # (A continuous 7-day count would give 3 — asserting 1 proves pred-calendar.)
    acts = [
        act("P", cal="C5", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 10)),
        act("S", cal="C7", AS=_dt(2025, 1, 13), AF=_dt(2025, 1, 15)),
    ]
    rels = [rel("P", "S")]
    r = reconstruct_asbuilt_paths(sched(acts, rels, cals=[cal5(), cal7()]))
    assert r.end_anchor_code == "S"
    chain = r.chains[0]
    assert chain.activity_codes == ["P", "S"]
    link = chain.links[0]
    assert link.actual_lag_wd == 1.0          # pred-calendar workday count
    assert link.planned_lag_wd == 0.0
    assert link.tightness_wd == 1.0
    assert link.is_gap is False               # 1 <= 5
    assert link.lag_calendar == "C5"          # measured in the predecessor's calendar


# ---------------------------------------------------------------------------
# 6. End-anchor resolution: auto, explicit, deterministic tie-break
# ---------------------------------------------------------------------------
def test_end_anchor_auto_latest_finish():
    acts = [
        act("A", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("B", AS=_dt(2025, 1, 8), AF=_dt(2025, 1, 16)),   # latest finish
    ]
    r = reconstruct_asbuilt_paths(sched(acts, [rel("A", "B")]))
    assert r.end_anchor_code == "B"
    assert r.end_anchor_resolution == "latest actual finish"


def test_end_anchor_explicit():
    acts = [
        act("A", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("B", AS=_dt(2025, 1, 8), AF=_dt(2025, 1, 16)),
    ]
    r = reconstruct_asbuilt_paths(sched(acts, [rel("A", "B")]), end="A")
    assert r.end_anchor_uid == "A"
    assert "explicit" in r.end_anchor_resolution


def test_end_anchor_tiebreak_deterministic():
    # identical actual dates; smallest uid must win the tie (deterministic)
    acts = [
        act("T2", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 10)),
        act("T1", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 10)),
    ]
    r = reconstruct_asbuilt_paths(sched(acts, []))
    assert r.end_anchor_uid == "T1"


def test_explicit_end_not_started_falls_back():
    acts = [
        act("A", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("U", status="N"),                        # not started
    ]
    r = reconstruct_asbuilt_paths(sched(acts, [rel("A", "U")]), end="U")
    assert r.end_anchor_code == "A"                  # fell back to latest AF
    assert "not found or not started" in r.end_anchor_resolution


# ---------------------------------------------------------------------------
# 7. Unstarted / LOE exclusion; empty schedules degrade gracefully
# ---------------------------------------------------------------------------
def test_loe_and_unstarted_excluded():
    acts = [
        act("A", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 8)),
        act("B", AS=_dt(2025, 1, 8), AF=_dt(2025, 1, 10)),
        act("L", cal="C5", status="C", AS=_dt(2025, 1, 6), AF=_dt(2025, 1, 10),
            atype=ActivityType.LOE),                 # LOE: excluded from population
        act("U", status="N"),                        # not started: excluded
    ]
    rels = [rel("A", "B")]
    r = reconstruct_asbuilt_paths(sched(acts, rels))
    # only A and B are actualized real activities
    assert r.summary["actualized_activities"] == 2
    codes = {c for chain in r.chains for c in chain.activity_codes}
    assert "L" not in codes and "U" not in codes
    assert all(l.pred_code != "L" and l.succ_code != "L" for l in r.links)


def test_empty_no_actuals():
    acts = [act("A", status="N"), act("B", status="N")]
    r = reconstruct_asbuilt_paths(sched(acts, [rel("A", "B")]))
    assert isinstance(r, AsBuiltReconstruction)
    assert r.chains == []
    assert r.reason
    assert r.disclosures
    assert r.summary["actualized_activities"] == 0


def test_empty_schedule():
    r = reconstruct_asbuilt_paths(sched([], []))
    assert r.chains == []
    assert r.reason
    assert r.to_dict()["chains"] == []


# ---------------------------------------------------------------------------
# 8. Determinism: two runs -> identical to_dict()
# ---------------------------------------------------------------------------
def test_determinism_identical_to_dict():
    s1 = _linear()
    s2 = _linear()
    d1 = reconstruct_asbuilt_paths(s1).to_dict()
    d2 = reconstruct_asbuilt_paths(s2).to_dict()
    assert d1 == d2
    # and re-running on the same object is stable too
    assert reconstruct_asbuilt_paths(s1).to_dict() == d1


def test_to_dict_is_json_serializable():
    import json
    r = reconstruct_asbuilt_paths(_linear())
    json.dumps(r.to_dict())        # must not raise
