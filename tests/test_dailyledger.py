"""Tests for the daily-resolution delay ledger (N3, ANALYTICS_PROPOSAL.md §8.3)
— scheduleiq.analytics.dailyledger.

Schedules are built IN MEMORY (ingest-model objects direct, the test_asbuilt
pattern).  In-memory schedules carry no stored tool-of-record CPM dates, so the
ADR-0007 handshake has nothing to validate against — every in-memory test runs
with handshake="skip", and test_handshake_skip_disclosure asserts the bypass is
disclosed.  Refusal propagation is exercised against the demo_cpm_divergent.xer
fixture (the one path that needs an XER).

Every workday number asserted below is hand-computed against a Mon-Fri 8h
calendar.  Workday numbering (weekends skipped; local origin Jan 06 = 1):
    Jan 06 Mon = 1   Jan 07 Tue = 2   Jan 08 Wed = 3   Jan 09 Thu = 4
    Jan 10 Fri = 5   (11-12 wkend)   Jan 13 Mon = 6   Jan 14 Tue = 7
    Jan 15 Wed = 8   Jan 16 Thu = 9   Jan 17 Fri = 10  (18-19 wkend)
    Jan 20 Mon = 11  Jan 21 = 12  Jan 22 = 13  Jan 23 = 14  Jan 24 = 15
    Jan 27 = 16  Jan 28 = 17  Jan 29 = 18  Jan 30 = 19  Jan 31 = 20
    Feb 03 = 21 ... Feb 07 = 25 ... Feb 13 = 29

Window in every pair: earlier DD = Mon 2025-01-06 (w=0), later DD = Mon
2025-01-20 (w=10): 10 workdays, 14 calendar rows (Jan 07 .. Jan 20).

Engine conventions the hand-calcs rely on (bridge defaults):
  * P6_COMPATIBILITY: FS lag 0 -> successor ES workday = pred EF workday + 1.
  * In-progress pin: ES pinned at AS; remaining work resumes at the day's data
    date d -> wd(EF) = wd(d) + RD - 1.
  * Interpolation clock w(d) is the FORWARD-adjusted workday index (weekend
    day -> next Monday's index), so weekend rows carry the following Monday's
    state and zero deltas; the engine likewise adjusts a weekend project_start
    forward.  RD(w) = RD0 + (RD1-RD0)*w/W rounded half up, floored at 0.
"""
import os
import subprocess
import sys
from datetime import date, datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest.model import (                                   # noqa: E402
    Activity, ActivityStatus, ActivityType, Calendar, RelType,
    Relationship, Schedule)
from scheduleiq.analytics.dailyledger import (                          # noqa: E402
    DailyLedger, LABEL, _DAY_CAP, capped_day_range, run_daily_ledger)
from scheduleiq.cpm.handshake import (HandshakeRefusal,                 # noqa: E402
                                      clear_handshake_cache)
from scheduleiq.intake.events import EventMapResult, EventMapping       # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(CPM_DIV):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(autouse=True)
def _fresh_handshake_cache():
    # the handshake cache keys in-memory schedules by id(); clear per test so a
    # recycled object id can never surface another schedule's cached summary.
    clear_handshake_cache()
    yield
    clear_handshake_cache()


# ---------------------------------------------------------------------------
# in-memory builders
# ---------------------------------------------------------------------------
def _dt(y, m, d):
    return datetime(y, m, d, 8, 0)


def cal5(uid="C5"):
    """Mon-Fri 8h (empty work_patterns -> Mon-Fri default in ingest + bridge)."""
    return Calendar(uid=uid, name="5-Day", hours_per_day=8.0, is_default=True)


def act(uid, status, od_h, rem_h, AS=None, AF=None, atype=ActivityType.TASK):
    st = {"C": ActivityStatus.COMPLETED, "P": ActivityStatus.IN_PROGRESS,
          "N": ActivityStatus.NOT_STARTED}[status]
    return Activity(uid=uid, code=uid, atype=atype, status=st,
                    calendar_uid="C5", original_duration_hours=od_h,
                    remaining_duration_hours=rem_h,
                    actual_start=AS, actual_finish=AF)


def sched(acts, rels, dd):
    s = Schedule()
    s.project_id = "DLT"
    s.data_date = dd
    s.calendars["C5"] = cal5()
    for a in acts:
        s.activities[a.uid] = a
    s.relationships = [Relationship(pred_uid=p, succ_uid=q, rtype=RelType.FS)
                       for p, q in rels]
    return s


D0 = _dt(2025, 1, 6)     # earlier data date (Mon, w=0)
DN = _dt(2025, 1, 20)    # later data date (Mon, w=10)

# A is completed before the window in every pair: AS Dec 23, AF Fri Dec 27.
def _done_A():
    return act("A", "C", 40, 0, AS=_dt(2024, 12, 23), AF=_dt(2024, 12, 27))


# ---------------------------------------------------------------------------
# pair 1 — slip: B's RD interpolates 10 -> 5 wd over the 10-workday window
# ---------------------------------------------------------------------------
# Chain A -> B -> C (all FS 0).  B in progress (AS Dec 30, before the window);
# C not started, OD 3 wd.  RD(w) = 10 - w/2 rounded half up:
#   w : 0  1  2  3  4  5  6  7  8  9  10
#   RD: 10 10 9  9  8  8  7  7  6  6  5
# For day d with forward workday index i (= w+1):
#   wd(EF_B) = i + RD - 1;  wd(ES_C) = wd(EF_B) + 1 (FS, P6 offset);
#   wd(EF_C) = wd(ES_C) + 2  ->  g = i + RD + 2 = w + RD + 3.
#   g: w0 13, w1 14, w2 14, w3 15, w4 15, w5 16, w6 16, w7 17, w8 17,
#      w9 18, w10 18.
# Calendar rows Jan07..Jan20 (weekend rows repeat the following Monday state):
#   Jan07 +1, Jan08 0, Jan09 +1, Jan10 0, Jan11(Sat,w5) +1, Jan12 0, Jan13 0,
#   Jan14 0, Jan15 +1, Jan16 0, Jan17 +1, Jan18(Sat,w10) 0, Jan19 0, Jan20 0.
#   Sum = 5 = g(w10) - g(w0) = 18 - 13.  EF(d0) = wd 13 = Jan 22;
#   EF(dN) = wd 18 = Jan 29.
def _pair_slip():
    earlier = sched([_done_A(),
                     act("B", "P", 120, 80, AS=_dt(2024, 12, 30)),   # RD0 = 10
                     act("C", "N", 24, 24)],
                    [("A", "B"), ("B", "C")], D0)
    later = sched([_done_A(),
                   act("B", "P", 120, 40, AS=_dt(2024, 12, 30)),     # RD1 = 5
                   act("C", "N", 24, 24)],
                  [("A", "B"), ("B", "C")], DN)
    return earlier, later


EXPECTED_SLIP = [1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0]


def test_slip_daily_pattern_and_endpoints():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    assert dl.computable is True
    assert [r.day for r in dl.rows] == [date(2025, 1, 6 + k) for k in range(1, 15)]
    assert [r.delta_workdays for r in dl.rows] == EXPECTED_SLIP
    # endpoints hand-computed above
    assert dl.arithmetic_check["ef_target_day0"] == "2025-01-22"
    assert dl.arithmetic_check["ef_target_last"] == "2025-01-29"
    assert dl.rows[-1].ef_target == date(2025, 1, 29)
    # B is the target's binding predecessor every day
    assert all(r.controlling_code == "B" for r in dl.rows)
    # cumulative series ends at the total
    assert dl.rows[-1].cumulative_workdays == 5
    assert dl.cumulative_series[-1]["cumulative_workdays"] == 5


def test_slip_arithmetic_check_exact():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    blk = dl.arithmetic_check
    assert blk["sum_of_daily_deltas_wd"] == 5
    assert blk["endpoint_delta_wd"] == 5
    assert blk["exact"] is True


def test_slip_reconciliation_matches_as_imported_runs():
    # Interpolation at the endpoints reproduces both as-imported states here:
    # at dN the interpolated RD equals later's RD (5); at d0 it equals
    # earlier's RD (10) and C's not-started duration is earlier's RD (3 wd,
    # same as later's OD) -> both reconciliation deltas are exactly 0.
    # Earlier as-imported: wd(EF_B) = 1+10-1 = 10, C ES 11, EF 13 -> Jan 22.
    # Later as-imported:   wd(EF_B) = 11+5-1 = 15, C ES 16, EF 18 -> Jan 29.
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    rec = dl.reconciliation
    assert rec["earlier_as_imported_ef"] == "2025-01-22"
    assert rec["earlier_as_imported_vs_interp_wd"] == 0
    assert rec["later_as_imported_ef"] == "2025-01-29"
    assert rec["later_as_imported_vs_interp_wd"] == 0
    # in-memory files store no record dates: record reconciliation degrades
    # with a disclosure rather than silently
    assert rec["earlier_record_ef"] is None
    assert rec["record_movement_wd"] is None
    assert any("record finish dates missing" in d for d in dl.disclosures)


def test_slip_event_annotation():
    earlier, later = _pair_slip()
    ev = EventMapResult(events=[EventMapping(
        event_id="EV-1", title="Storm",
        start=_dt(2025, 1, 8), finish=_dt(2025, 1, 10))])
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip",
                          events=ev)
    by_day = {r.day: r.event_ids for r in dl.rows}
    assert by_day[date(2025, 1, 7)] == []
    assert by_day[date(2025, 1, 8)] == ["EV-1"]
    assert by_day[date(2025, 1, 9)] == ["EV-1"]
    assert by_day[date(2025, 1, 10)] == ["EV-1"]
    assert by_day[date(2025, 1, 11)] == []


def test_slip_framing_and_notstarted_choice_disclosed():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    assert any("LATER file's network" in d for d in dl.disclosures)
    assert any("D9 half-step" in d for d in dl.disclosures)
    assert any("not-yet-started activities" in d for d in dl.disclosures)
    assert dl.label == LABEL


# ---------------------------------------------------------------------------
# pair 2 — recovery: B's RD interpolates 22 -> 2 (2 wd of recovery per workday)
# ---------------------------------------------------------------------------
# RD(w) = 22 - 2w (exact, no rounding).  g = i + RD + 2 = w + RD + 3:
#   w0 25, w1 24, ..., w10 15  ->  -1 on every workday step, 0 on repeated
#   weekend/Monday states.  Rows: Jan07..Jan11 = -1 (5 steps, Sat Jan11 is
#   w5's first appearance), Jan12/13 = 0, Jan14..Jan17 = -1 (4), Jan18 = -1,
#   Jan19/20 = 0.  Sum = -10 = 15 - 25.
#   EF(d0) = wd 25 = Feb 07; EF(dN) = wd 15 = Jan 24.
def _pair_recovery():
    earlier = sched([_done_A(),
                     act("B", "P", 200, 176, AS=_dt(2024, 12, 30)),  # RD0 = 22
                     act("C", "N", 24, 24)],
                    [("A", "B"), ("B", "C")], D0)
    later = sched([_done_A(),
                   act("B", "P", 200, 16, AS=_dt(2024, 12, 30)),     # RD1 = 2
                   act("C", "N", 24, 24)],
                  [("A", "B"), ("B", "C")], DN)
    return earlier, later


def test_recovery_negative_deltas():
    earlier, later = _pair_recovery()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    expected = [-1, -1, -1, -1, -1, 0, 0, -1, -1, -1, -1, -1, 0, 0]
    assert [r.delta_workdays for r in dl.rows] == expected
    assert dl.arithmetic_check["sum_of_daily_deltas_wd"] == -10
    assert dl.arithmetic_check["endpoint_delta_wd"] == -10
    assert dl.arithmetic_check["exact"] is True
    assert dl.arithmetic_check["ef_target_day0"] == "2025-02-07"
    assert dl.arithmetic_check["ef_target_last"] == "2025-01-24"


# ---------------------------------------------------------------------------
# pair 3 — controlling-chain flip: B1 (growing RD) overtakes B2 (static RD)
# ---------------------------------------------------------------------------
# Two parallel in-progress chains into finish milestone M (FS 0 both):
#   B1: RD 8 -> 18  =>  RD(w) = 8 + w;   wd(EF_B1) = i + RD - 1 = 2w + 8
#   B2: RD 12 (static);                  wd(EF_B2) = i + 11     = w + 12
#   wd(EF_M) = max(...) + 1 (FS offset; milestone span 0):
#   w : 0   1   2   3   4    5   6   7   8   9   10
#   M : 13  14  15  16  17   19  21  23  25  27  29
#   ctl: B2  B2  B2  B2  B2* B1  B1  B1  B1  B1  B1   (*tie at w4: both bind;
#        tie-break = greatest predecessor id -> B2)
# Rows: Jan07..Jan10 = +1 (B2), Jan11(Sat,w5) = +2 (B1), Jan12/13 = 0 (B1),
# Jan14..Jan17 = +2 (B1), Jan18(Sat,w10) = +2 (B1), Jan19/20 = 0 (B1).
# Sum = 4*1 + 6*2 = 16 = 29 - 13.  EF(dN) = wd 29 = Feb 13.
def _pair_flip():
    earlier = sched([act("B1", "P", 160, 64, AS=_dt(2024, 12, 30)),   # RD0 = 8
                     act("B2", "P", 160, 96, AS=_dt(2024, 12, 30)),   # RD0 = 12
                     act("M", "N", 0, 0, atype=ActivityType.FINISH_MILESTONE)],
                    [("B1", "M"), ("B2", "M")], D0)
    later = sched([act("B1", "P", 160, 144, AS=_dt(2024, 12, 30)),    # RD1 = 18
                   act("B2", "P", 160, 96, AS=_dt(2024, 12, 30)),     # RD1 = 12
                   act("M", "N", 0, 0, atype=ActivityType.FINISH_MILESTONE)],
                  [("B1", "M"), ("B2", "M")], DN)
    return earlier, later


def test_controlling_activity_flips():
    earlier, later = _pair_flip()
    dl = run_daily_ledger(earlier, later, target="M", handshake="skip")
    deltas = [r.delta_workdays for r in dl.rows]
    ctl = [r.controlling_code for r in dl.rows]
    assert deltas == [1, 1, 1, 1, 2, 0, 0, 2, 2, 2, 2, 2, 0, 0]
    assert ctl == ["B2", "B2", "B2", "B2",
                   "B1", "B1", "B1", "B1", "B1", "B1", "B1", "B1", "B1", "B1"]
    assert dl.arithmetic_check["sum_of_daily_deltas_wd"] == 16
    assert dl.arithmetic_check["exact"] is True
    assert dl.arithmetic_check["ef_target_last"] == "2025-02-13"


def test_responsibility_subtotals_by_controlling_activity():
    earlier, later = _pair_flip()
    dl = run_daily_ledger(earlier, later, target="M", handshake="skip",
                          responsibility={"B1": "Contractor", "B2": "Owner"})
    sub = dl.responsibility_subtotals
    assert "OBSERVATIONAL" in sub["note"]
    assert "reserved to the expert" in sub["note"]
    # B2-controlled days: Jan07-10 (+1 each); B1-controlled: Jan11-20 (sum 12)
    assert sub["by_party"] == {
        "Owner": {"delta_workdays": 4, "days": 4},
        "Contractor": {"delta_workdays": 12, "days": 10},
    }
    assert dl.rows[0].controlling_party == "Owner"
    assert dl.rows[-1].controlling_party == "Contractor"


def test_responsibility_untagged_fallback():
    earlier, later = _pair_flip()
    dl = run_daily_ledger(earlier, later, target="M", handshake="skip",
                          responsibility={"B1": "Contractor"})   # B2 untagged
    sub = dl.responsibility_subtotals["by_party"]
    assert sub["Untagged"] == {"delta_workdays": 4, "days": 4}
    assert sub["Contractor"] == {"delta_workdays": 12, "days": 10}


def test_no_responsibility_overlay_reason():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    assert dl.responsibility_subtotals == {
        "reason": "no responsibility overlay provided"}


# ---------------------------------------------------------------------------
# pair 4 — completion pins mid-window: B finishes Fri Jan 10
# ---------------------------------------------------------------------------
# A -> B -> C.  Later: B COMPLETED (AS Dec 30, AF Jan 10); C not started,
# OD 5 wd.  Earlier: B in progress, RD0 = 10; RD1 = 0 (completed) ->
# RD(w) = 10 - w while d < AF (w <= 3).
#   d < Jan10:  g = i + RD + 4 = w + RD + 5 = 15 (flat: RD drops 1/workday).
#   d >= Jan10: B pinned at AF Jan10 (wd 5); C ES = max(wd(d), 6);
#               g = max(6, i) + 4:
#     Jan10 -> 10 (delta -5: the actual finish outruns the interpolation),
#     Jan11/12/13 -> 10, Jan14..Jan17 -> 11..14 (+1 each: C is unstarted and
#     slips with the advancing data date), Jan18(Sat) -> 15 (+1), Jan19/20 0.
# Sum = -5 + 5 = 0 exactly; EF(d0) = EF(dN) = wd 15 = Jan 24.
def _pair_completed_midwindow():
    earlier = sched([_done_A(),
                     act("B", "P", 80, 80, AS=_dt(2024, 12, 30)),     # RD0 = 10
                     act("C", "N", 40, 40)],
                    [("A", "B"), ("B", "C")], D0)
    later = sched([_done_A(),
                   act("B", "C", 80, 0, AS=_dt(2024, 12, 30),
                       AF=_dt(2025, 1, 10)),
                   act("C", "N", 40, 40)],
                  [("A", "B"), ("B", "C")], DN)
    return earlier, later


def test_completed_midwindow_pins_on_the_right_day():
    earlier, later = _pair_completed_midwindow()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    expected = [0, 0, 0, -5, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0]
    assert [r.delta_workdays for r in dl.rows] == expected
    by_day = {r.day: r for r in dl.rows}
    assert by_day[date(2025, 1, 10)].newly_completed == ["B"]
    assert by_day[date(2025, 1, 10)].delta_workdays == -5
    assert all(r.newly_completed == [] for r in dl.rows
               if r.day != date(2025, 1, 10))
    # net-zero window still checks exactly
    assert dl.arithmetic_check["sum_of_daily_deltas_wd"] == 0
    assert dl.arithmetic_check["endpoint_delta_wd"] == 0
    assert dl.arithmetic_check["exact"] is True
    assert dl.arithmetic_check["ef_target_day0"] == "2025-01-24"
    assert dl.arithmetic_check["ef_target_last"] == "2025-01-24"


# ---------------------------------------------------------------------------
# pair 5 — mid-window start: B starts Wed Jan 08 (newly_started)
# ---------------------------------------------------------------------------
# A -> B, target B.  Earlier: B not started (RD 10 wd).  Later: B in progress,
# AS Jan 08, RD1 = 5.  Before Jan 08 B is unpinned at the earlier-RD duration
# (10 wd): wd(EF_B) = i + 9.  From Jan 08 it pins and interpolates
# RD(w) = 10 - w/2 (same table as pair 1): wd(EF_B) = i + RD - 1.
#   Jan06 10, Jan07 11(+1), Jan08 11(0: 3+9-1), Jan09 12(+1), Jan10 12(0),
#   Jan11(w5) 13(+1), Jan12/13 0, Jan14 13(0), Jan15 14(+1), Jan16 14(0),
#   Jan17 15(+1), Jan18(w10) 15(0), Jan19/20 0.   Sum = 5 = 15 - 10.
def _pair_midwindow_start():
    earlier = sched([_done_A(), act("B", "N", 80, 80)],
                    [("A", "B")], D0)
    later = sched([_done_A(),
                   act("B", "P", 80, 40, AS=_dt(2025, 1, 8))],
                  [("A", "B")], DN)
    return earlier, later


def test_newly_started_midwindow():
    earlier, later = _pair_midwindow_start()
    dl = run_daily_ledger(earlier, later, target="B", handshake="skip")
    expected = [1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0]
    assert [r.delta_workdays for r in dl.rows] == expected
    by_day = {r.day: r for r in dl.rows}
    assert by_day[date(2025, 1, 8)].newly_started == ["B"]
    assert all(r.newly_started == [] for r in dl.rows
               if r.day != date(2025, 1, 8))
    assert dl.arithmetic_check["exact"] is True
    assert dl.arithmetic_check["sum_of_daily_deltas_wd"] == 5


# ---------------------------------------------------------------------------
# handshake semantics
# ---------------------------------------------------------------------------
def test_handshake_skip_disclosure():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(earlier, later, target="C", handshake="skip")
    assert any("skip" in d.lower() and "bypass" in d.lower()
               for d in dl.disclosures)
    # in-memory schedules have no stored record dates, which is exactly why
    # these tests must use the documented skip escape hatch
    assert dl.handshake_earlier is not None
    assert dl.handshake_later is not None


def test_handshake_refusal_propagates_on_divergent_xer():
    from scheduleiq.ingest import load
    div = load(CPM_DIV)[0]
    with pytest.raises(HandshakeRefusal):
        run_daily_ledger(div, div)                 # default handshake="require"


def test_bad_handshake_mode_raises():
    earlier, later = _pair_slip()
    with pytest.raises(ValueError):
        run_daily_ledger(earlier, later, target="C", handshake="maybe")


# ---------------------------------------------------------------------------
# window edge cases
# ---------------------------------------------------------------------------
def test_same_data_date_yields_empty_exact_ledger():
    earlier, _ = _pair_slip()
    earlier2, _ = _pair_slip()
    dl = run_daily_ledger(earlier, earlier2, target="C", handshake="skip")
    assert dl.computable is True
    assert dl.rows == []
    assert dl.arithmetic_check["sum_of_daily_deltas_wd"] == 0
    assert dl.arithmetic_check["endpoint_delta_wd"] == 0
    assert dl.arithmetic_check["exact"] is True


def test_reversed_data_dates_refused_with_disclosure():
    earlier, later = _pair_slip()
    dl = run_daily_ledger(later, earlier, target="C", handshake="skip")
    assert dl.computable is False
    assert "after later data date" in dl.blocking
    assert dl.rows == []


# ---------------------------------------------------------------------------
# day cap (unit-tested directly: a >400-day engine sweep would be too slow)
# ---------------------------------------------------------------------------
def test_day_cap_logic_unit():
    days, capped = capped_day_range(date(2025, 1, 1), date(2025, 3, 1))
    assert capped is False
    assert len(days) == 60                                     # 59 days + d0
    assert days[0] == date(2025, 1, 1) and days[-1] == date(2025, 3, 1)

    d0 = date(2025, 1, 1)
    days, capped = capped_day_range(d0, date(2026, 12, 31))    # 729-day span
    assert capped is True
    assert len(days) == _DAY_CAP + 1
    assert days[-1] == d0.fromordinal(d0.toordinal() + _DAY_CAP)


# ---------------------------------------------------------------------------
# determinism + serialization
# ---------------------------------------------------------------------------
def test_determinism_identical_to_dict():
    e1, l1 = _pair_slip()
    d1 = run_daily_ledger(e1, l1, target="C", handshake="skip").to_dict()
    clear_handshake_cache()
    e2, l2 = _pair_slip()
    d2 = run_daily_ledger(e2, l2, target="C", handshake="skip").to_dict()
    assert d1 == d2


def test_to_dict_shape_and_json_serializable():
    import json
    earlier, later = _pair_flip()
    dl = run_daily_ledger(earlier, later, target="M", handshake="skip",
                          responsibility={"B1": "Contractor", "B2": "Owner"})
    d = dl.to_dict()
    assert set(d) >= {"label", "presentation_rule", "sign_convention", "pair",
                      "target", "handshake_earlier", "handshake_later",
                      "computable", "window", "rows", "cumulative_series",
                      "arithmetic_check", "reconciliation",
                      "responsibility_subtotals", "disclosures"}
    assert d["label"] == LABEL
    assert "PRELIMINARY" in d["label"]
    assert d["window"]["capped"] is False
    json.dumps(d)                                              # must not raise
    assert isinstance(dl, DailyLedger)
