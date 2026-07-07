"""Generate synthetic .xer fixtures with seeded, documented defects.

Three sequential updates of one project (baseline + two updates) exercising
every metric family: open ends, leads/lags, hard constraints, high/negative
float, long durations, invalid dates, out-of-sequence progress, LOE/summary
exclusions, unresourced activities, milestone abuse, calendar anomalies, and
between updates: added/deleted activities, logic churn, retroactive actual-date
changes ("rewriting history"), and float erosion.

Run:  python make_fixtures.py  (writes into this directory).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
# Make ``scheduleiq`` importable when this script is run directly (the CPM
# handshake fixtures below build their stored values by running the ported
# engine).  Harmless when PYTHONPATH already points at src.
_SRC = os.path.abspath(os.path.join(HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
D0 = datetime(2025, 1, 6, 8, 0)          # project start (a Monday)

CAL_5D = "100"    # standard 5-day
CAL_7D = "101"    # 7-day, 10h  (calendar anomaly)


def dt(s: datetime | None) -> str:
    return s.strftime("%Y-%m-%d %H:%M") if s else ""


def wd(start: datetime, days: float) -> datetime:
    """Add working days (5d calendar) — good enough for fixtures."""
    cur, left = start, days
    while left > 0:
        step = min(left, 1.0)
        cur += timedelta(days=1)
        while cur.isoweekday() > 5:
            cur += timedelta(days=1)
        left -= step
    return cur


class Xer:
    def __init__(self):
        self.lines = ["ERMHDR\t19.12\t2025-06-01\tProject\tadmin\tAdmin User"
                      "\tdbxDatabaseNoName\tProject Management\tUSD"]

    def table(self, name: str, fields: list[str], rows: list[list]):
        self.lines.append("%T\t" + name)
        self.lines.append("%F\t" + "\t".join(fields))
        for r in rows:
            self.lines.append("%R\t" + "\t".join("" if v is None else str(v) for v in r))

    def write(self, path: str):
        with open(path, "w", encoding="cp1252", newline="\r\n") as f:
            f.write("\n".join(self.lines) + "\n%E\n")


def cal_blob_5d(extra_holidays: list[int] = []) -> str:
    days = "".join(
        f"(0||{d}()(" + ("" if d in (1, 7) else "(0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())") + "))"
        for d in range(1, 8))
    holidays = [45658] + list(extra_holidays)        # 2025-01-01 + any extras
    exc = "".join(f"(0||0(d|{h})())" for h in holidays)
    exc = f"(0||Exceptions()({exc}))"
    return f"(0||CalendarData()((0||DaysOfWeek()({days}))" + exc + "))"


def cal_blob_7d() -> str:
    days = "".join(f"(0||{d}()((0||0(s|07:00|f|17:00)())))" for d in range(1, 8))
    return f"(0||CalendarData()((0||DaysOfWeek()({days}))))"


# --------------------------------------------------------------------------
# Activity plan: (uid, code, name, type, dur_days, cal, wbs)
# Chain A is the intended critical path.
# --------------------------------------------------------------------------
ACTS = [
    (1000, "MS-000", "Notice to Proceed",        "TT_Mile",    0,  CAL_5D, 20),
    (1010, "A1010", "Mobilization",              "TT_Task",    10, CAL_5D, 20),
    (1020, "A1020", "Site Clearing",             "TT_Task",    15, CAL_5D, 20),
    (1030, "A1030", "Excavation",                "TT_Task",    20, CAL_5D, 21),
    (1040, "A1040", "Foundations Area 1",        "TT_Task",    25, CAL_5D, 21),
    (1050, "A1050", "Foundations Area 2",        "TT_Task",    25, CAL_5D, 21),
    (1060, "A1060", "Structural Steel Area 1",   "TT_Task",    30, CAL_5D, 22),
    (1070, "A1070", "Structural Steel Area 2",   "TT_Task",    30, CAL_5D, 22),
    (1080, "A1080", "Long-Lead Procurement",     "TT_Task",    60, CAL_5D, 23),  # long duration
    (1090, "A1090", "Equipment Setting",         "TT_Task",    15, CAL_7D, 22),  # odd calendar
    (1100, "A1100", "Piping Install",            "TT_Task",    35, CAL_5D, 22),
    (1110, "A1110", "Electrical Rough-In",       "TT_Task",    25, CAL_5D, 22),
    (1120, "A1120", "Instrumentation",           "TT_Task",    20, CAL_5D, 22),
    (1130, "A1130", "Insulation",                "TT_Task",    15, CAL_5D, 22),
    (1140, "A1140", "Punchlist / Pre-Comm",      "TT_Task",    10, CAL_5D, 24),
    (1150, "A1150", "Commissioning",             "TT_Task",    15, CAL_5D, 24),
    (1160, "MS-100", "Substantial Completion",   "TT_FinMile", 0,  CAL_5D, 24),
    (1170, "A1170", "Project Management",        "TT_LOE",     0,  CAL_5D, 20),  # LOE
    (1180, "A1180", "Dangling SS Activity",      "TT_Task",    12, CAL_5D, 22),  # dangling finish
    (1190, "A1190", "Orphan Activity",           "TT_Task",    5,  CAL_5D, 23),  # no pred, no succ
    (1200, "A1200", "Constrained Milestone",     "TT_FinMile", 0,  CAL_5D, 24),  # hard constraint
]

# (pred, succ, type, lag_hours)
RELS = [
    (1000, 1010, "PR_FS", 0),
    (1010, 1020, "PR_FS", 0),
    (1020, 1030, "PR_FS", 0),
    (1030, 1040, "PR_FS", 0),
    (1030, 1050, "PR_SS", 40),          # SS+lag
    (1040, 1060, "PR_FS", 0),
    (1050, 1070, "PR_FS", -16),         # negative lag (lead)
    (1060, 1090, "PR_FS", 0),
    (1070, 1090, "PR_FS", 0),
    (1080, 1090, "PR_FS", 200),         # excessive lag (25d)
    (1090, 1100, "PR_FS", 0),
    (1100, 1110, "PR_SS", 24),
    (1100, 1130, "PR_FS", 0),
    (1110, 1120, "PR_FS", 0),
    (1120, 1140, "PR_FS", 0),
    (1130, 1140, "PR_FS", 0),
    (1140, 1150, "PR_FS", 0),
    (1150, 1160, "PR_FS", 0),
    (1150, 1160, "PR_FF", 0),           # redundant duplicate pair
    (1000, 1080, "PR_FS", 0),
    (1000, 1180, "PR_SS", 0),           # 1180 has no successor -> dangling finish
    (1150, 1200, "PR_FS", 0),
    (1120, 1140, "PR_SF", 0),           # SF relationship (rare/flagged)
]


def schedule_dates(pct: dict[int, float], dd: datetime):
    """Crude forward pass for fixture purposes (5d calendar)."""
    dur = {a[0]: a[4] for a in ACTS}
    es: dict[int, datetime] = {}
    ef: dict[int, datetime] = {}

    def compute(uid, stack=()):
        if uid in ef:
            return
        if uid in stack:
            return
        preds = [(p, t, lag) for p, s, t, lag in RELS if s == uid]
        start = D0
        for p, t, lag in preds:
            compute(p, stack + (uid,))
            if p not in ef:
                continue
            if t == "PR_FS":
                cand = ef[p] + timedelta(hours=lag * 3)  # spread lags in calendar time
            elif t == "PR_SS":
                cand = es[p] + timedelta(hours=lag * 3)
            elif t == "PR_FF":
                cand = ef[p] + timedelta(hours=lag * 3) - timedelta(days=dur[uid] * 1.4)
            else:
                cand = ef[p]
            start = max(start, cand)
        start = max(start, dd)
        es[uid] = start
        ef[uid] = wd(start, dur[uid]) if dur[uid] else start

    for a in ACTS:
        compute(a[0])
    return es, ef


def build(path: str, dd: datetime, pct: dict[int, float],
          extra_acts=(), removed=(), extra_rels=(), removed_rels=(),
          float_shift: float = 0.0, actual_overrides: dict[int, datetime] = {},
          finish_early: dict[int, float] = {}, rd_override: dict[int, float] = {},
          af_before_as: set = frozenset(), extreme_float: dict[int, float] = {},
          wbs_override: dict[int, int] = {}, retained_logic: str = "Y",
          extra_holidays: list[int] = []):
    x = Xer()
    x.table("CALENDAR",
            ["clndr_id", "clndr_name", "clndr_type", "day_hr_cnt", "week_hr_cnt",
             "default_flag", "clndr_data"],
            [[CAL_5D, "Standard 5-Day", "CA_Base", 8, 40, "Y",
              cal_blob_5d(extra_holidays)],
             [CAL_7D, "7-Day 10hr Shift", "CA_Project", 10, 70, "N", cal_blob_7d()]])
    x.table("PROJECT",
            ["proj_id", "proj_short_name", "plan_start_date", "plan_end_date",
             "scd_end_date", "last_recalc_date"],
            [[1, "DEMO-PLANT", dt(D0), dt(datetime(2025, 12, 19, 17, 0)),
              dt(datetime(2025, 12, 5, 17, 0)), dt(dd)]])
    x.table("SCHEDOPTIONS",
            ["schedoptions_id", "proj_id", "sched_retained_logic",
             "sched_progress_override", "sched_open_critical_flag",
             "sched_critical_float_hr_cnt", "sched_use_expect_end_flag",
             "sched_calendar_on_relationship_lag"],
            [[1, 1, retained_logic, "N", "N", 0, "Y", "rcal_Predecessor"]])
    x.table("PROJWBS",
            ["wbs_id", "proj_id", "parent_wbs_id", "wbs_short_name", "wbs_name",
             "proj_node_flag"],
            [[19, 1, "", "DEMO", "Demo Plant Project", "Y"],
             [20, 1, 19, "GEN", "General", "N"],
             [21, 1, 19, "CIV", "Civil", "N"],
             [22, 1, 19, "MECH", "Mechanical", "N"],
             [23, 1, 19, "PROC", "Procurement", "N"],
             [24, 1, 19, "COMM", "Completion", "N"]])
    x.table("RSRC", ["rsrc_id", "rsrc_short_name", "rsrc_name", "rsrc_type"],
            [[1, "CIV-CRW", "Civil Crew", "RT_Labor"],
             [2, "MECH-CRW", "Mech Crew", "RT_Labor"]])

    acts = [a for a in list(ACTS) + list(extra_acts) if a[0] not in removed]
    rels = [r for r in list(RELS) + list(extra_rels)
            if (r[0], r[1], r[2]) not in removed_rels
            and r[0] not in removed and r[1] not in removed]
    es, ef = schedule_dates(pct, dd)

    rows = []
    for uid, code, name, ttype, dur, cal, wbs in acts:
        wbs = wbs_override.get(uid, wbs)             # DEFECT hook: WBS re-parenting
        p = pct.get(uid, 0.0)
        hpd = 10 if cal == CAL_7D else 8
        od_h = dur * hpd
        if uid in finish_early:
            od_h = finish_early[uid] * hpd
        rem_h = od_h * (1 - p / 100.0)
        est, eft = es.get(uid, D0), ef.get(uid, D0)
        a_start = a_finish = None
        if p > 0:
            a_start = actual_overrides.get(uid) or min(est, dd) - timedelta(days=max(1, dur * p / 100))
            if a_start >= dd:
                a_start = dd - timedelta(days=1)
        if p >= 100:
            a_finish = a_start + timedelta(days=dur * 1.4) if dur else a_start
            if uid == 1020:              # DEFECT: actual finish after data date
                a_finish = dd + timedelta(days=3)
            if uid in af_before_as:      # DEFECT: actual finish before actual start
                a_finish = a_start - timedelta(days=2)
            status = "TK_Complete"
            rem_h = 0
        elif p > 0:
            status = "TK_Active"
        else:
            status = "TK_NotStart"
        if uid == 1050 and 0 < p < 100:
            a_start = None               # DEFECT: in-progress without actual start
        if uid in rd_override:           # DEFECT: RD compression without progress
            rem_h = rd_override[uid]
        tf_h = 40.0
        if uid in (1190,):
            tf_h = 90 * 8                # DEFECT: high float (90d)
        if uid in (1080,):
            tf_h = 55 * 8
        if uid in (1000, 1010, 1020, 1030, 1040, 1060, 1090, 1100, 1110, 1120,
                   1140, 1150, 1160):
            tf_h = 0.0 + float_shift * 8
        if uid in extreme_float:         # DEFECT: float exceeding remaining duration
            tf_h = extreme_float[uid]
        cstr_t, cstr_d = "", None
        if uid == 1200:
            cstr_t, cstr_d = "CS_MANDFIN", datetime(2025, 12, 15, 17, 0)
        if uid == 1080:
            cstr_t, cstr_d = "CS_MSOA", datetime(2025, 2, 3, 8, 0)
        rows.append([uid, 1, wbs, cal, code, name, ttype, status,
                     od_h, rem_h,
                     dt(a_start), dt(a_finish),
                     dt(max(est, dd) if status != "TK_Complete" else est),
                     dt(max(eft, dd) if status != "TK_Complete" else eft),
                     dt(max(est, dd) - timedelta(hours=-tf_h)),
                     dt(max(eft, dd) + timedelta(hours=tf_h * 3) if status != "TK_Complete" else eft),
                     dt(es.get(uid, D0)), dt(ef.get(uid, D0)),
                     tf_h if status != "TK_Complete" else "",
                     max(0.0, tf_h - 16) if status != "TK_Complete" else "",
                     cstr_t, dt(cstr_d), "", "",
                     p if 0 < p < 100 else (100 if p >= 100 else 0),
                     # 1070 is explicitly Physical % so its percent is reported
                     # independently of RD/OD — required for the DUR-04 branch-2
                     # seed (Duration-% activities are excluded from branch 2)
                     "CP_Phys" if uid == 1070
                     else ("CP_Drtn" if uid % 2 == 0 else "CP_Phys"),
                     "", "", ""])
    x.table("TASK",
            ["task_id", "proj_id", "wbs_id", "clndr_id", "task_code", "task_name",
             "task_type", "status_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
             "act_start_date", "act_end_date", "early_start_date", "early_end_date",
             "late_start_date", "late_end_date", "target_start_date",
             "target_end_date", "total_float_hr_cnt", "free_float_hr_cnt",
             "cstr_type", "cstr_date", "cstr_type2", "cstr_date2",
             "phys_complete_pct", "complete_pct_type", "suspend_date",
             "resume_date", "expect_end_date"],
            rows)
    x.table("TASKPRED",
            ["task_pred_id", "task_id", "pred_task_id", "pred_type", "lag_hr_cnt"],
            [[i + 1, s, p, t, lag] for i, (p, s, t, lag) in enumerate(rels)])
    # resources on only a few activities -> unresourced findings
    x.table("TASKRSRC",
            ["taskrsrc_id", "task_id", "rsrc_id", "target_qty", "remain_qty",
             "act_reg_qty", "target_cost", "act_reg_cost", "remain_cost"],
            [[1, 1030, 1, 800, 400, 400, 80000, 40000, 40000],
             [2, 1040, 1, 1000, 1000, 0, 100000, 0, 100000],
             [3, 1100, 2, 1400, 1400, 0, 210000, 0, 210000],
             [4, 1160, 2, 40, 40, 0, 0, 0, 0]])   # DEFECT: resourced milestone
    x.write(path)


# ==========================================================================
# CPM validation-handshake fixtures (ADR-0007, SET-02).
#
# demo_cpm.xer and demo_cpm_divergent.xer are a compact, CPM-CONSISTENT project
# whose stored tool-of-record early/late/float values are produced by RUNNING
# the ported engine (scheduleiq.cpm) through the bridge on the in-memory model,
# then written back into the file.  The circularity is DELIBERATE: this fixture
# validates the integration PLUMBING (bridge -> engine -> compare -> handshake),
# not engine correctness.  Engine CORRECTNESS is validated separately by the
# hand-computed tests under tests/cpm/.  demo_cpm therefore handshakes at 100%;
# demo_cpm_divergent is identical except exactly three activities' stored
# early/late dates are shifted (+5 workdays) with their floats left stale, so
# the handshake lands deterministically below the 99% threshold.
# ==========================================================================

CPM_CAL_5D = "200"    # standard 5-day, 8h
CPM_CAL_7D = "201"    # 7-day, 10h (a non-dominant calendar)

# (uid, code, name, xer_type, dur_workdays, cal)
CPM_ACTS = [
    (2000, "MS-START", "Project Start",          "TT_Mile",    0,  CPM_CAL_5D),
    (2010, "A10",  "Mobilization",                "TT_Task",    5,  CPM_CAL_5D),
    (2020, "A20",  "Site Preparation",            "TT_Task",    8,  CPM_CAL_5D),
    (2030, "A30",  "Excavation (in progress)",    "TT_Task",    10, CPM_CAL_5D),
    (2040, "A40",  "Foundations (7-day crew)",    "TT_Task",    6,  CPM_CAL_7D),
    (2050, "A50",  "Underground Services",        "TT_Task",    4,  CPM_CAL_5D),
    (2060, "A60",  "Structural Steel",            "TT_Task",    7,  CPM_CAL_5D),
    (2070, "A70",  "Cladding (7-day crew)",       "TT_Task",    5,  CPM_CAL_7D),
    (2080, "A80",  "MEP Rough-In",                "TT_Task",    3,  CPM_CAL_5D),
    (2090, "A90",  "Fit-Out",                     "TT_Task",    6,  CPM_CAL_5D),
    (2100, "A100", "Commissioning",               "TT_Task",    4,  CPM_CAL_5D),
    (2110, "MS-END", "Substantial Completion",    "TT_FinMile", 0,  CPM_CAL_5D),
]

# (pred, succ, xer_type, lag_hours) — FS/SS/FF incl. a negative lead.
CPM_RELS = [
    (2000, 2010, "PR_FS", 0),
    (2010, 2020, "PR_FS", 0),
    (2020, 2030, "PR_FS", 0),
    (2030, 2040, "PR_FS", 0),
    (2030, 2050, "PR_SS", 16),      # SS + 2wd (8h/day)
    (2040, 2060, "PR_FS", -16),     # negative lead, -2wd
    (2050, 2060, "PR_FS", 0),
    (2060, 2070, "PR_FF", 8),       # FF + 1wd
    (2060, 2080, "PR_FS", 0),
    (2070, 2090, "PR_FS", 0),
    (2080, 2090, "PR_FS", 0),
    (2090, 2100, "PR_FS", 0),
    (2100, 2110, "PR_FS", 0),
    (2040, 2110, "PR_FS", 0),
]

CPM_DD = datetime(2025, 3, 24, 8, 0)     # data date (a Monday)

# Actuals (all before the data date).  Completed: 2010, 2020.  In progress: 2030.
CPM_ACTUALS = {
    2010: (datetime(2025, 3, 3, 8, 0),  datetime(2025, 3, 7, 17, 0)),   # 5 wd
    2020: (datetime(2025, 3, 10, 8, 0), datetime(2025, 3, 19, 17, 0)),  # 8 wd
    2030: (datetime(2025, 3, 20, 8, 0), None),                          # in progress
}
CPM_STATUS = {2010: "TK_Complete", 2020: "TK_Complete", 2030: "TK_Active"}
CPM_REMAIN_WD = {2030: 6}                # in-progress remaining duration (workdays)

# One SNET (start no earlier than) and one FNLT (finish no later than).
CPM_CONSTRAINTS = {
    2050: ("CS_MSOA", datetime(2025, 4, 7, 8, 0)),    # SNET, real forward effect
    2080: ("CS_MEOB", datetime(2025, 7, 31, 17, 0)),  # FNLT (benign; logged)
}

# The three activities whose stored dates are corrupted in the divergent file.
CPM_DIVERGENT_UIDS = (2060, 2090, 2100)

_CPM_TASK_FIELDS = [
    "task_id", "proj_id", "wbs_id", "clndr_id", "task_code", "task_name",
    "task_type", "status_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    "act_start_date", "act_end_date", "early_start_date", "early_end_date",
    "late_start_date", "late_end_date", "target_start_date", "target_end_date",
    "total_float_hr_cnt", "free_float_hr_cnt", "cstr_type", "cstr_date",
    "cstr_type2", "cstr_date2", "phys_complete_pct", "complete_pct_type",
    "suspend_date", "resume_date", "expect_end_date",
]


def _cpm_hpd(cal: str) -> int:
    return 10 if cal == CPM_CAL_7D else 8


def _dtd(d, finish: bool = False) -> str:
    """A cpm engine ``date`` -> XER datetime string (time is cosmetic; the
    handshake reads only the .date())."""
    if d is None:
        return ""
    hh = "17:00" if finish else "08:00"
    return f"{d.isoformat()} {hh}"


def _cpm_common_tables(x: "Xer", dd: datetime) -> None:
    x.table("CALENDAR",
            ["clndr_id", "clndr_name", "clndr_type", "day_hr_cnt", "week_hr_cnt",
             "default_flag", "clndr_data"],
            [[CPM_CAL_5D, "CPM Standard 5-Day", "CA_Base", 8, 40, "Y", cal_blob_5d()],
             [CPM_CAL_7D, "CPM 7-Day 10hr", "CA_Project", 10, 70, "N", cal_blob_7d()]])
    x.table("PROJECT",
            ["proj_id", "proj_short_name", "plan_start_date", "plan_end_date",
             "scd_end_date", "last_recalc_date"],
            [[1, "DEMO-CPM", dt(datetime(2025, 3, 3, 8, 0)),
              dt(datetime(2025, 9, 1, 17, 0)), dt(datetime(2025, 8, 1, 17, 0)), dt(dd)]])
    # rcal_Predecessor lag calendar; retained logic; progress override off; the
    # critical-float threshold is intentionally left EMPTY so the record does not
    # assert per-activity criticality (is_critical is then skipped in the compare,
    # keeping the plumbing fixture free of the longest-path-vs-TF=0 question).
    x.table("SCHEDOPTIONS",
            ["schedoptions_id", "proj_id", "sched_retained_logic",
             "sched_progress_override", "sched_open_critical_flag",
             "sched_critical_float_hr_cnt", "sched_use_expect_end_flag",
             "sched_calendar_on_relationship_lag"],
            [[1, 1, "Y", "N", "N", "", "N", "rcal_Predecessor"]])
    x.table("PROJWBS",
            ["wbs_id", "proj_id", "parent_wbs_id", "wbs_short_name", "wbs_name",
             "proj_node_flag"],
            [[30, 1, "", "CPM", "CPM Demo Project", "Y"]])


def _cpm_task_rows(stored: dict) -> list:
    """Assemble TASK rows.  ``stored`` maps uid -> dict(es, ef, ls, lf, tf_hr,
    ff_hr) of the values to write into the tool-of-record date/float fields."""
    rows = []
    for uid, code, name, ttype, dur, cal in CPM_ACTS:
        hpd = _cpm_hpd(cal)
        od_h = dur * hpd
        status = CPM_STATUS.get(uid, "TK_NotStart")
        a_start, a_finish = CPM_ACTUALS.get(uid, (None, None))
        if status == "TK_Complete":
            rem_h = 0
            phys = 100
        elif status == "TK_Active":
            rem_wd = CPM_REMAIN_WD.get(uid, dur)
            rem_h = rem_wd * hpd
            phys = int(round(100 * (1 - rem_wd / dur))) if dur else 0
        else:
            rem_h = od_h
            phys = 0
        sv = stored[uid]
        cstr_t, cstr_d = CPM_CONSTRAINTS.get(uid, ("", None))
        rows.append([
            uid, 1, 30, cal, code, name, ttype, status, od_h, rem_h,
            dt(a_start), dt(a_finish),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            _dtd(sv["ls"]), _dtd(sv["lf"], finish=True),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            sv["tf_hr"], sv["ff_hr"],
            cstr_t, dt(cstr_d), "", "", phys, "CP_Drtn", "", "", "",
        ])
    return rows


def _write_cpm_xer(path: str, stored: dict) -> None:
    x = Xer()
    _cpm_common_tables(x, CPM_DD)
    x.table("TASK", _CPM_TASK_FIELDS, _cpm_task_rows(stored))
    x.table("TASKPRED",
            ["task_pred_id", "task_id", "pred_task_id", "pred_type", "lag_hr_cnt"],
            [[i + 1, s, p, t, lag] for i, (p, s, t, lag) in enumerate(CPM_RELS)])
    x.write(path)


def _engine_stored_values() -> dict:
    """Run the ported engine (via the bridge) on the CPM fixture model and return
    the computed ES/EF/LS/LF/TF/FF per uid, encoded for the XER date/float fields.

    A throwaway XER (with placeholder stored values) is written, parsed, and fed
    through the exact bridge+engine path the handshake uses, so the values written
    back are guaranteed self-consistent with the handshake."""
    from scheduleiq.ingest import load
    from scheduleiq.cpm.bridge import build_engine_inputs
    from scheduleiq.cpm.engine import run_analysis

    placeholder = {uid: {"es": None, "ef": None, "ls": None, "lf": None,
                        "tf_hr": "", "ff_hr": ""} for uid, *_ in CPM_ACTS}
    tmp = os.path.join(HERE, "_demo_cpm_tmp.xer")
    _write_cpm_xer(tmp, placeholder)
    try:
        sched = load(tmp)[0]
        ei = build_engine_inputs(sched)
        result = run_analysis(
            activities=ei.activities, relationships=ei.relationships,
            project_start=ei.project_start, workday_table=ei.workday_table,
            calendar=ei.calendar, convention=ei.convention,
            calendar_registry=ei.calendar_registry, lag_strategy=ei.lag_strategy,
            constraints=ei.constraints or None, statusing_mode=ei.statusing_mode,
        )
        if not result.is_valid:
            issues = [i.issue_code for i in result.validation.issues if i.blocking]
            raise RuntimeError(f"demo_cpm engine run is invalid (blocking: {issues}); "
                               "fixture network must be CPM-consistent.")
        hpd_by_cal = {uid: _cpm_hpd(cal) for uid, _c, _n, _t, _d, cal in CPM_ACTS}
        stored = {}
        for uid_int, _c, _n, _t, _d, _cal in CPM_ACTS:
            sa = result.scheduled[str(uid_int)]
            hpd = hpd_by_cal[uid_int]
            stored[uid_int] = {
                "es": sa.early_start, "ef": sa.early_finish,
                "ls": sa.late_start, "lf": sa.late_finish,
                "tf_hr": sa.total_float * hpd, "ff_hr": sa.free_float * hpd,
            }
        return stored
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_cpm_fixtures() -> None:
    """Write demo_cpm.xer (handshake 100%) and demo_cpm_divergent.xer (< 99%)."""
    stored = _engine_stored_values()
    _write_cpm_xer(os.path.join(HERE, "demo_cpm.xer"), stored)

    # Divergent: shift exactly three activities' stored dates by +5 workdays
    # (= +7 calendar days on the 5-day calendar), leaving their floats stale.
    divergent = {uid: dict(v) for uid, v in stored.items()}
    for uid in CPM_DIVERGENT_UIDS:
        for k in ("es", "ef", "ls", "lf"):
            if divergent[uid][k] is not None:
                divergent[uid][k] = divergent[uid][k] + timedelta(days=7)
    _write_cpm_xer(os.path.join(HERE, "demo_cpm_divergent.xer"), divergent)


# ==========================================================================
# Issue-impact fixture (ADR-0007 A2/A4/P5 — the impact.py analytics module).
#
# demo_impact.xer follows the SAME engine-of-record pattern as demo_cpm: a
# placeholder file is written, parsed, run through the bridge+engine BASELINE
# (constraints on, retained logic), and the engine's ES/EF/LS/LF/TF/FF are
# written back as the stored tool-of-record values — so the ADR-0007 handshake
# passes at 100% and the impact scenarios measure real diagnostic deltas.
#
# Topology (three chains merging into the finish milestone MS-IMP, plus two
# genuinely open-ended incomplete activities), engineered so every impact
# scenario has a NONZERO, mechanism-explained delta.  See the mechanism map in
# tests/test_impact.py.  In one line each:
#   * Chain A (IA30..IA60) is the sole baseline controller — NO date constraint
#     sits on it, so both the out-of-sequence override and the lead-zeroing
#     propagate cleanly to MS-IMP.  It carries the genuine OOS (IA40 started
#     before its in-progress predecessor IA30 finished), a -16h lead
#     (IA40->IA50) and a +80h lag (IA50->IA60, on the 7-day/10h calendar).
#   * Chain B (IB10..IB20) has a very long true logic length but a MANDATORY
#     FINISH pins IB20 far earlier than logic, hiding chain B below chain A in
#     the baseline; releasing constraints lets chain B spring back PAST chain A,
#     so MS-IMP moves LATER (a positive constraints-released delta — the classic
#     "the Mandatory Finish was masking chain B" story).
#   * Chain C (IC10..IC20) carries the SNET (holds IC15 beyond its logic date =>
#     float absorbed) and the EXPECTED_FINISH (on IC20); it stays below chain A,
#     so its per-constraint target deltas are ~0 (=> per-constraint deltas
#     differ from chain B's).
#   * ID10 (chain D, feeds MS-IMP) carries an SNLT whose date the schedule cannot
#     meet (start no later than a date before the data date), so with constraints
#     it has NEGATIVE total float (manufactured-critical) but positive float once
#     released.  The SNLT is a late-side (backward) constraint, so it does not
#     move MS-IMP's early finish and never masks the chain-A deltas.
# ==========================================================================

IMP_CAL_5D = "210"    # standard 5-day, 8h (default)
IMP_CAL_7D = "211"    # 7-day, 10h (a non-dominant calendar)

# (uid, code, name, xer_type, dur_workdays, cal)
IMP_ACTS = [
    (3000, "IMS-START", "Project Start",             "TT_Mile",    0,  IMP_CAL_5D),
    (3010, "IA10", "Mobilization",                   "TT_Task",    5,  IMP_CAL_5D),
    (3020, "IA20", "Earthworks",                     "TT_Task",    8,  IMP_CAL_5D),
    (3030, "IA30", "Foundations (in progress)",      "TT_Task",    10, IMP_CAL_5D),
    (3040, "IA40", "Steel Erection (OOS)",           "TT_Task",    8,  IMP_CAL_5D),
    (3050, "IA50", "Cladding (7-day crew)",          "TT_Task",    8,  IMP_CAL_7D),
    (3060, "IA60", "Fit-Out",                        "TT_Task",    10, IMP_CAL_5D),
    (3070, "IB10", "Long-Lead Procurement",          "TT_Task",    30, IMP_CAL_5D),
    (3075, "IB15", "Off-Site Fabrication",           "TT_Task",    25, IMP_CAL_5D),
    (3080, "IB20", "Equipment Install (mand. fin.)", "TT_Task",    15, IMP_CAL_5D),
    (3090, "IC10", "Commissioning Prep (in prog.)",  "TT_Task",    8,  IMP_CAL_5D),
    (3095, "IC15", "System Integration (SNET)",      "TT_Task",    4,  IMP_CAL_5D),
    (3100, "IC20", "Testing (expected finish)",      "TT_Task",    5,  IMP_CAL_5D),
    (3110, "ID10", "Regulatory Submittal (SNLT)",    "TT_Task",    6,  IMP_CAL_5D),
    (3120, "IE10", "Isolated Permitting (open end)", "TT_Task",    6,  IMP_CAL_5D),
    (3130, "IE20", "Spare-Parts Storage (open end)", "TT_Task",    5,  IMP_CAL_5D),
    (3200, "MS-IMP", "Mechanical Completion",        "TT_FinMile", 0,  IMP_CAL_5D),
]

# (pred, succ, xer_type, lag_hours)
IMP_RELS = [
    # chain A (sole baseline controller; no date constraint on it)
    (3000, 3010, "PR_FS", 0),
    (3010, 3020, "PR_FS", 0),
    (3020, 3030, "PR_FS", 0),
    (3030, 3040, "PR_FS", 0),      # OOS pair: IA40 started before IA30 finished
    (3040, 3050, "PR_FS", -16),    # LEAD: -16h @ 8h/day (IA40 cal) -> -2 wd
    (3050, 3060, "PR_FS", 80),     # LAG: +80h @ 10h/day (IA50 7-day cal) -> +8 wd
    (3060, 3200, "PR_FS", 0),
    # chain B (long true logic; MANDATORY FINISH hides it below chain A)
    (3000, 3070, "PR_FS", 0),
    (3070, 3075, "PR_FS", 0),
    (3075, 3080, "PR_FS", 0),
    (3080, 3200, "PR_FS", 0),
    # chain C (SNET + EXPECTED_FINISH; stays below chain A)
    (3000, 3090, "PR_FS", 0),
    (3090, 3095, "PR_FS", 0),
    (3095, 3100, "PR_FS", 0),
    (3100, 3200, "PR_FS", 0),
    # chain D (feeds MS-IMP; SNLT manufactures negative float off the early-date
    # driving path)
    (3010, 3110, "PR_FS", 0),
    (3110, 3200, "PR_FS", 0),
    # open ends (no forward path to MS-IMP)
    (3000, 3120, "PR_FS", 0),
    (3010, 3130, "PR_FS", 0),
]

IMP_DD = datetime(2025, 4, 14, 8, 0)     # data date, mid-project (a Monday)

# Actuals (all before the data date).  Completed: IA10, IA20.
# In progress: IA30 (foundations), IA40 (steel — OOS), IC10, IE20.
IMP_ACTUALS = {
    3010: (datetime(2025, 3, 3, 8, 0),  datetime(2025, 3, 7, 17, 0)),    # 5 wd
    3020: (datetime(2025, 3, 10, 8, 0), datetime(2025, 3, 19, 17, 0)),   # 8 wd
    3030: (datetime(2025, 3, 20, 8, 0), None),                           # in progress
    3040: (datetime(2025, 4, 2, 8, 0),  None),                           # OOS (started
    #      2025-04-02, before its in-progress predecessor IA30 will finish)
    3090: (datetime(2025, 4, 7, 8, 0),  None),                           # in progress
    3130: (datetime(2025, 4, 8, 8, 0),  None),                           # in progress
}
IMP_STATUS = {3010: "TK_Complete", 3020: "TK_Complete", 3030: "TK_Active",
              3040: "TK_Active", 3090: "TK_Active", 3130: "TK_Active"}
IMP_REMAIN_WD = {3030: 6, 3040: 6, 3090: 5, 3130: 3}     # remaining workdays

# Constraints.  MANDATORY_FINISH on IB20 (early — masks chain B); SNET on IC15
# (holds it beyond its logic date); EXPECTED_FINISH on IC20 (a not-started
# activity, so the engine actually applies it — pinned activities ignore XF).
IMP_CONSTRAINTS = {
    3080: ("CS_MANDFIN", datetime(2025, 4, 25, 17, 0)),     # MF, early -> hides B
    3095: ("CS_MSOA", datetime(2025, 5, 5, 8, 0)),          # SNET -> float absorbed
    3110: ("CS_MSOB", datetime(2025, 3, 25, 8, 0)),         # SNLT, unmeetable ->
    #      manufactured-critical (negative float with the constraint only)
}
IMP_EXPECT = {3100: datetime(2025, 5, 16, 17, 0)}           # EXPECTED_FINISH (XF)


def _imp_hpd(cal: str) -> int:
    return 10 if cal == IMP_CAL_7D else 8


def _imp_common_tables(x: "Xer", dd: datetime) -> None:
    x.table("CALENDAR",
            ["clndr_id", "clndr_name", "clndr_type", "day_hr_cnt", "week_hr_cnt",
             "default_flag", "clndr_data"],
            [[IMP_CAL_5D, "IMP Standard 5-Day", "CA_Base", 8, 40, "Y", cal_blob_5d()],
             [IMP_CAL_7D, "IMP 7-Day 10hr", "CA_Project", 10, 70, "N", cal_blob_7d()]])
    x.table("PROJECT",
            ["proj_id", "proj_short_name", "plan_start_date", "plan_end_date",
             "scd_end_date", "last_recalc_date"],
            [[1, "DEMO-IMPACT", dt(datetime(2025, 3, 3, 8, 0)),
              dt(datetime(2025, 10, 1, 17, 0)), dt(datetime(2025, 9, 1, 17, 0)),
              dt(dd)]])
    # Retained logic; progress override off; critical-float threshold left empty
    # (record does not assert per-activity criticality -> is_critical skipped in
    # the compare, keeping the handshake plumbing clean).  Predecessor lag cal.
    x.table("SCHEDOPTIONS",
            ["schedoptions_id", "proj_id", "sched_retained_logic",
             "sched_progress_override", "sched_open_critical_flag",
             "sched_critical_float_hr_cnt", "sched_use_expect_end_flag",
             "sched_calendar_on_relationship_lag"],
            [[1, 1, "Y", "N", "N", "", "Y", "rcal_Predecessor"]])
    x.table("PROJWBS",
            ["wbs_id", "proj_id", "parent_wbs_id", "wbs_short_name", "wbs_name",
             "proj_node_flag"],
            [[40, 1, "", "IMP", "Impact Demo Project", "Y"]])


def _imp_task_rows(stored: dict) -> list:
    rows = []
    for uid, code, name, ttype, dur, cal in IMP_ACTS:
        hpd = _imp_hpd(cal)
        od_h = dur * hpd
        status = IMP_STATUS.get(uid, "TK_NotStart")
        a_start, a_finish = IMP_ACTUALS.get(uid, (None, None))
        if status == "TK_Complete":
            rem_h, phys = 0, 100
        elif status == "TK_Active":
            rem_wd = IMP_REMAIN_WD.get(uid, dur)
            rem_h = rem_wd * hpd
            phys = int(round(100 * (1 - rem_wd / dur))) if dur else 0
        else:
            rem_h, phys = od_h, 0
        sv = stored[uid]
        cstr_t, cstr_d = IMP_CONSTRAINTS.get(uid, ("", None))
        expect = IMP_EXPECT.get(uid)
        rows.append([
            uid, 1, 40, cal, code, name, ttype, status, od_h, rem_h,
            dt(a_start), dt(a_finish),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            _dtd(sv["ls"]), _dtd(sv["lf"], finish=True),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            sv["tf_hr"], sv["ff_hr"],
            cstr_t, dt(cstr_d), "", "", phys, "CP_Drtn", "", "", dt(expect),
        ])
    return rows


def _write_imp_xer(path: str, stored: dict) -> None:
    x = Xer()
    _imp_common_tables(x, IMP_DD)
    x.table("TASK", _CPM_TASK_FIELDS, _imp_task_rows(stored))
    x.table("TASKPRED",
            ["task_pred_id", "task_id", "pred_task_id", "pred_type", "lag_hr_cnt"],
            [[i + 1, s, p, t, lag] for i, (p, s, t, lag) in enumerate(IMP_RELS)])
    x.write(path)


def _imp_run_once(stored_for_file: dict) -> dict:
    """Write a temp impact XER carrying ``stored_for_file``, parse it, run the
    bridge+engine BASELINE (constraints on, retained logic), and return the
    engine's ES/EF/LS/LF/TF/FF per uid encoded for the XER fields."""
    from scheduleiq.ingest import load
    from scheduleiq.cpm.bridge import build_engine_inputs
    from scheduleiq.cpm.engine import run_analysis

    tmp = os.path.join(HERE, "_demo_impact_tmp.xer")
    _write_imp_xer(tmp, stored_for_file)
    try:
        sched = load(tmp)[0]
        ei = build_engine_inputs(sched)
        result = run_analysis(
            activities=ei.activities, relationships=ei.relationships,
            project_start=ei.project_start, workday_table=ei.workday_table,
            calendar=ei.calendar, convention=ei.convention,
            calendar_registry=ei.calendar_registry, lag_strategy=ei.lag_strategy,
            constraints=ei.constraints or None, statusing_mode=ei.statusing_mode,
        )
        if not result.is_valid:
            issues = [i.issue_code for i in result.validation.issues if i.blocking]
            raise RuntimeError(f"demo_impact engine run is invalid (blocking: {issues}); "
                               "fixture network must be CPM-consistent.")
        hpd_by_cal = {uid: _imp_hpd(cal) for uid, _c, _n, _t, _d, cal in IMP_ACTS}
        stored = {}
        for uid_int, _c, _n, _t, _d, _cal in IMP_ACTS:
            sa = result.scheduled[str(uid_int)]
            hpd = hpd_by_cal[uid_int]
            stored[uid_int] = {
                "es": sa.early_start, "ef": sa.early_finish,
                "ls": sa.late_start, "lf": sa.late_finish,
                "tf_hr": sa.total_float * hpd, "ff_hr": sa.free_float * hpd,
            }
        return stored
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _imp_engine_stored_values() -> dict:
    """Two-pass, so the stored values are self-consistent with the handshake.

    The bridge sizes its workday tables from the DATES present in the parsed
    file.  A placeholder file (no stored early/late dates) yields a narrower
    range than the final file, and CROSS-CALENDAR free float is sensitive to
    the table anchor — so a single placeholder pass leaves free float slightly
    off (the handshake would then land below 100%).  The engine DATES are
    range-independent, so pass 1 (from the placeholder) fixes the dates; pass 2
    runs against a file already carrying those dates, giving the exact range the
    handshake will see and thus range-consistent free floats.  A file written
    with pass-2 values re-parses to the identical date range, so pass 2 is a
    fixpoint (asserted below)."""
    placeholder = {uid: {"es": None, "ef": None, "ls": None, "lf": None,
                        "tf_hr": "", "ff_hr": ""} for uid, *_ in IMP_ACTS}
    s1 = _imp_run_once(placeholder)     # correct dates (range-independent)
    s2 = _imp_run_once(s1)              # correct range -> correct free float
    s3 = _imp_run_once(s2)              # fixpoint check
    if s2 != s3:
        raise RuntimeError("demo_impact stored values did not reach a fixpoint; "
                           "the fixture would not handshake at 100%.")
    return s2


def build_impact_fixture() -> None:
    """Write demo_impact.xer (handshake 100%; the A2/A4/P5 impact fixture)."""
    stored = _imp_engine_stored_values()
    _write_imp_xer(os.path.join(HERE, "demo_impact.xer"), stored)


# ==========================================================================
# MIP 3.4 half-step fixture pair (backlog D9 — analytics/halfstep.py).
#
# demo_hs1.xer / demo_hs2.xer are TWO consecutive updates of one project,
# each built with the SAME engine-of-record two-pass pattern as demo_impact
# (stored tool-of-record values produced by the ported engine, so BOTH files
# handshake at 100%).  Single 5-day/8h calendar so every asserted delta is
# clean workday arithmetic.
#
# Designed mechanisms (each asserted in tests/test_halfstep.py):
#
#   PROGRESS (hs1 -> hs2, overlaid onto hs1's network = the half-step H):
#     * HA30 Foundations finished LATE: hs1 forecast EF 2025-04-11 (RD 5 at
#       DD 2025-04-07); hs2 actual finish 2025-04-18 (5 wd slow).
#     * HA40 Steel started late (AS 2025-04-21) and still carries RD 4 at the
#       hs2 DD 2025-05-05 — the chain-P slip drives MS-HS from the E_n engine
#       EF 2025-05-28 to the half-step EF 2025-06-10: progress_effect = +9 wd.
#     * Chain Q progressed roughly to plan (HB10, HB15 complete).
#
#   REVISIONS (hs2's network vs hs1's — the named attribution classes, each
#   re-applied ALONE on top of H; deltas at MS-HS on the 5-day calendar):
#     * logic_added   — new tie HB20 -> HA50 (FS): the envelope now waits for
#       equipment install ("reroute": part of the path now runs through chain
#       Q).  Alone on H: HA50 ES 2025-05-09 -> 2025-05-19 => +6 wd.
#     * logic_deleted — the old tie HB20 -> HA70 (FS) is removed (the other
#       half of the reroute).  It was NOT binding in H (chain Q float) => 0 wd
#       — a genuine revision whose isolated effect is honestly zero.
#     * duration_changed — HA50 Envelope OD 8 -> 12 wd (scope growth on the
#       controlling chain).  Alone on H: +4 wd.
#     * constraint_changed — SNET 2025-05-26 added on HA60 Fit-Out.  Alone on
#       H (HA60 ES 2025-05-21): +3 wd.  In the FULL hs2 network the other
#       revisions push HA60 past the SNET, so the constraint contributes
#       nothing to E_n1 — the designed INTERACTION that makes the attribution
#       residual nonzero (sum of classes +21 vs revision_effect +18 => -3).
#     * new_activities — HD10 "Owner Change – Additional Testing" (8 wd)
#       inserted HA60 -> HD10 -> HA70 (its incident ties are attributed to
#       this class, not to logic_added).  Alone on H: +8 wd.
#     * deleted_activities — HX10 Temporary Works (3 wd, high float, present
#       only in hs1) is descoped in hs2; its removal is off-path => 0 wd, and
#       in the half-step it keeps hs1's unprogressed state (disclosed).
#
#   IDENTITY (exact by construction, asserted): total = progress + revision;
#   E_n MS-HS 2025-05-28, H 2025-06-10, E_n1 2025-07-04 => +9 / +18 / +27 wd.
# ==========================================================================

HS_CAL_5D = "230"    # the pair's single calendar: standard 5-day, 8h

# (uid, code, name, xer_type, dur_workdays)
HS_ACTS_1 = [
    (4000, "HMS-START", "Project Start",            "TT_Mile",    0),
    (4010, "HA10", "Mobilization",                  "TT_Task",    5),
    (4020, "HA20", "Groundworks",                   "TT_Task",   10),
    (4030, "HA30", "Foundations",                   "TT_Task",   10),
    (4040, "HA40", "Steel Erection",                "TT_Task",   10),
    (4050, "HA50", "Envelope",                      "TT_Task",    8),
    (4060, "HA60", "Fit-Out",                       "TT_Task",   10),
    (4070, "HA70", "Commissioning",                 "TT_Task",    5),
    (4100, "HB10", "Procurement",                   "TT_Task",   20),
    (4105, "HB15", "Fabrication",                   "TT_Task",    8),
    (4110, "HB20", "Equipment Install",             "TT_Task",   10),
    (4120, "HC10", "Landscaping",                   "TT_Task",    6),
    (4130, "HC20", "Signage",                       "TT_Task",    4),
    (4150, "HX10", "Temporary Works",               "TT_Task",    3),
    (4200, "MS-HS", "Mechanical Completion",        "TT_FinMile", 0),
]

# hs2: HX10 descoped (deleted); HD10 added (owner change order); HA50 OD 8->12.
HS_ACTS_2 = ([a for a in HS_ACTS_1 if a[0] not in (4050, 4150)]
             + [(4050, "HA50", "Envelope", "TT_Task", 12),
                (4140, "HD10", "Owner Change - Additional Testing", "TT_Task", 8)])

# (pred, succ, xer_type, lag_hours)
HS_RELS_1 = [
    # chain P — the controlling chain to MS-HS
    (4000, 4010, "PR_FS", 0),
    (4010, 4020, "PR_FS", 0),
    (4020, 4030, "PR_FS", 0),
    (4030, 4040, "PR_FS", 0),
    (4040, 4050, "PR_FS", 0),
    (4050, 4060, "PR_FS", 0),
    (4060, 4070, "PR_FS", 0),
    (4070, 4200, "PR_FS", 0),
    # chain Q — procurement/equipment, modest float
    (4000, 4100, "PR_FS", 0),
    (4100, 4105, "PR_FS", 0),
    (4105, 4110, "PR_FS", 0),
    (4110, 4070, "PR_FS", 0),
    # chain R — high float
    (4010, 4120, "PR_FS", 0),
    (4120, 4130, "PR_FS", 0),
    (4130, 4200, "PR_FS", 0),
    # HX10 — off-path temporary works (deleted in hs2)
    (4010, 4150, "PR_FS", 0),
]

HS_RELS_2 = ([r for r in HS_RELS_1
              if r[:2] not in ((4110, 4070),      # logic_deleted (reroute, half 2)
                               (4010, 4150))]     # goes with the deleted HX10
             + [(4110, 4050, "PR_FS", 0),         # logic_added (reroute, half 1)
                (4060, 4140, "PR_FS", 0),         # new-activity ties (HD10)
                (4140, 4070, "PR_FS", 0)])

HS1_DD = datetime(2025, 4, 7, 8, 0)    # data date, early project (a Monday)
HS2_DD = datetime(2025, 5, 5, 8, 0)    # one reporting period later (a Monday)

# hs1 progress: HA10/HA20 complete on plan; HA30 + HB10 in progress on plan.
HS1_ACTUALS = {
    4010: (datetime(2025, 3, 3, 8, 0),  datetime(2025, 3, 7, 17, 0)),    # 5 wd
    4020: (datetime(2025, 3, 10, 8, 0), datetime(2025, 3, 21, 17, 0)),   # 10 wd
    4030: (datetime(2025, 3, 24, 8, 0), None),                           # in prog
    4100: (datetime(2025, 3, 3, 8, 0),  None),                           # in prog
}
HS1_STATUS = {4010: "TK_Complete", 4020: "TK_Complete",
              4030: "TK_Active", 4100: "TK_Active"}
HS1_REMAIN_WD = {4030: 5, 4100: 4}
HS1_CONSTRAINTS: dict = {}

# hs2 progress: HA30 finished LATE (2025-04-18 vs the 2025-04-11 forecast);
# HA40 started late and is mid-flight; chain Q complete through HB15.
HS2_ACTUALS = {
    4010: (datetime(2025, 3, 3, 8, 0),  datetime(2025, 3, 7, 17, 0)),
    4020: (datetime(2025, 3, 10, 8, 0), datetime(2025, 3, 21, 17, 0)),
    4030: (datetime(2025, 3, 24, 8, 0), datetime(2025, 4, 18, 17, 0)),   # SLOW
    4040: (datetime(2025, 4, 21, 8, 0), None),                           # in prog
    4100: (datetime(2025, 3, 3, 8, 0),  datetime(2025, 4, 10, 17, 0)),
    4105: (datetime(2025, 4, 11, 8, 0), datetime(2025, 4, 22, 17, 0)),
}
HS2_STATUS = {4010: "TK_Complete", 4020: "TK_Complete", 4030: "TK_Complete",
              4040: "TK_Active", 4100: "TK_Complete", 4105: "TK_Complete"}
HS2_REMAIN_WD = {4040: 4}
HS2_CONSTRAINTS = {4060: ("CS_MSOA", datetime(2025, 5, 26, 8, 0))}   # SNET added


def _hs_common_tables(x: "Xer", dd: datetime) -> None:
    x.table("CALENDAR",
            ["clndr_id", "clndr_name", "clndr_type", "day_hr_cnt", "week_hr_cnt",
             "default_flag", "clndr_data"],
            [[HS_CAL_5D, "HS Standard 5-Day", "CA_Base", 8, 40, "Y", cal_blob_5d()]])
    x.table("PROJECT",
            ["proj_id", "proj_short_name", "plan_start_date", "plan_end_date",
             "scd_end_date", "last_recalc_date"],
            [[1, "DEMO-HS", dt(datetime(2025, 3, 3, 8, 0)),
              dt(datetime(2025, 9, 1, 17, 0)), dt(datetime(2025, 8, 1, 17, 0)),
              dt(dd)]])
    # Retained logic; progress override off; critical-float threshold left empty
    # (record does not assert per-activity criticality); predecessor lag cal —
    # same plumbing choices as the demo_cpm/demo_impact fixtures.
    x.table("SCHEDOPTIONS",
            ["schedoptions_id", "proj_id", "sched_retained_logic",
             "sched_progress_override", "sched_open_critical_flag",
             "sched_critical_float_hr_cnt", "sched_use_expect_end_flag",
             "sched_calendar_on_relationship_lag"],
            [[1, 1, "Y", "N", "N", "", "N", "rcal_Predecessor"]])
    x.table("PROJWBS",
            ["wbs_id", "proj_id", "parent_wbs_id", "wbs_short_name", "wbs_name",
             "proj_node_flag"],
            [[50, 1, "", "HS", "Half-Step Demo Project", "Y"]])


def _hs_task_rows(acts, stored, status_map, actuals, remain_wd, constraints) -> list:
    rows = []
    for uid, code, name, ttype, dur in acts:
        od_h = dur * 8
        status = status_map.get(uid, "TK_NotStart")
        a_start, a_finish = actuals.get(uid, (None, None))
        if status == "TK_Complete":
            rem_h, phys = 0, 100
        elif status == "TK_Active":
            rem = remain_wd.get(uid, dur)
            rem_h = rem * 8
            phys = int(round(100 * (1 - rem / dur))) if dur else 0
        else:
            rem_h, phys = od_h, 0
        sv = stored[uid]
        cstr_t, cstr_d = constraints.get(uid, ("", None))
        rows.append([
            uid, 1, 50, HS_CAL_5D, code, name, ttype, status, od_h, rem_h,
            dt(a_start), dt(a_finish),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            _dtd(sv["ls"]), _dtd(sv["lf"], finish=True),
            _dtd(sv["es"]), _dtd(sv["ef"], finish=True),
            sv["tf_hr"], sv["ff_hr"],
            cstr_t, dt(cstr_d), "", "", phys, "CP_Drtn", "", "", "",
        ])
    return rows


_HS_CFGS = {
    "hs1": dict(acts=HS_ACTS_1, rels=HS_RELS_1, dd=HS1_DD, actuals=HS1_ACTUALS,
                status=HS1_STATUS, remain=HS1_REMAIN_WD,
                constraints=HS1_CONSTRAINTS),
    "hs2": dict(acts=HS_ACTS_2, rels=HS_RELS_2, dd=HS2_DD, actuals=HS2_ACTUALS,
                status=HS2_STATUS, remain=HS2_REMAIN_WD,
                constraints=HS2_CONSTRAINTS),
}


def _write_hs_xer(path: str, cfg: dict, stored: dict) -> None:
    x = Xer()
    _hs_common_tables(x, cfg["dd"])
    x.table("TASK", _CPM_TASK_FIELDS,
            _hs_task_rows(cfg["acts"], stored, cfg["status"], cfg["actuals"],
                          cfg["remain"], cfg["constraints"]))
    x.table("TASKPRED",
            ["task_pred_id", "task_id", "pred_task_id", "pred_type", "lag_hr_cnt"],
            [[i + 1, s, p, t, lag] for i, (p, s, t, lag) in enumerate(cfg["rels"])])
    x.write(path)


def _hs_run_once(cfg: dict, stored_for_file: dict) -> dict:
    """Write a temp half-step XER carrying ``stored_for_file``, parse it, run the
    bridge+engine baseline, and return ES/EF/LS/LF/TF/FF per uid (same
    engine-of-record plumbing as _imp_run_once)."""
    from scheduleiq.ingest import load
    from scheduleiq.cpm.bridge import build_engine_inputs
    from scheduleiq.cpm.engine import run_analysis

    tmp = os.path.join(HERE, "_demo_hs_tmp.xer")
    _write_hs_xer(tmp, cfg, stored_for_file)
    try:
        sched = load(tmp)[0]
        ei = build_engine_inputs(sched)
        result = run_analysis(
            activities=ei.activities, relationships=ei.relationships,
            project_start=ei.project_start, workday_table=ei.workday_table,
            calendar=ei.calendar, convention=ei.convention,
            calendar_registry=ei.calendar_registry, lag_strategy=ei.lag_strategy,
            constraints=ei.constraints or None, statusing_mode=ei.statusing_mode,
        )
        if not result.is_valid:
            issues = [i.issue_code for i in result.validation.issues if i.blocking]
            raise RuntimeError(f"demo_hs engine run is invalid (blocking: {issues}); "
                               "fixture network must be CPM-consistent.")
        stored = {}
        for uid_int, _c, _n, _t, _d in cfg["acts"]:
            sa = result.scheduled[str(uid_int)]
            stored[uid_int] = {
                "es": sa.early_start, "ef": sa.early_finish,
                "ls": sa.late_start, "lf": sa.late_finish,
                "tf_hr": sa.total_float * 8, "ff_hr": sa.free_float * 8,
            }
        return stored
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _hs_engine_stored_values(cfg: dict) -> dict:
    """Two-pass + fixpoint check, exactly like _imp_engine_stored_values (the
    workday-table range depends on the dates written into the file, and free
    float is range-sensitive across tables)."""
    placeholder = {uid: {"es": None, "ef": None, "ls": None, "lf": None,
                        "tf_hr": "", "ff_hr": ""} for uid, *_ in cfg["acts"]}
    s1 = _hs_run_once(cfg, placeholder)
    s2 = _hs_run_once(cfg, s1)
    s3 = _hs_run_once(cfg, s2)
    if s2 != s3:
        raise RuntimeError("demo_hs stored values did not reach a fixpoint; "
                           "the fixture would not handshake at 100%.")
    return s2


def build_halfstep_fixtures() -> None:
    """Write demo_hs1.xer + demo_hs2.xer (both handshake at 100%; the MIP 3.4
    half-step update pair)."""
    for name, cfg in _HS_CFGS.items():
        stored = _hs_engine_stored_values(cfg)
        _write_hs_xer(os.path.join(HERE, f"demo_{name}.xer"), cfg, stored)


def main():
    # Baseline: no progress, DD = project start
    build(os.path.join(HERE, "demo_baseline.xer"), dd=D0, pct={})
    # Update 1 @ 2025-04-07: progress; defects 1020 (AF>DD), 1050 (no AS),
    # 1010 (AF<AS, DAT-05), zombie TASKPRED row referencing task 9999 (REL-01).
    # 1070 starts progressing here (20%, explicitly written as CP_Phys — see
    # the pct-type expression in build()) so update2 can show RD compression
    # without further percent movement (DUR-04 branch 2).  Physical % is
    # reported independently of remaining duration; Duration-% activities are
    # excluded from DUR-04 branch 2 because P6 derives their percent from
    # RD/OD, which would make the comparison self-referential.
    u1_pct = {1000: 100, 1010: 100, 1020: 100, 1030: 60, 1050: 30, 1070: 20,
              1080: 40, 1170: 30}
    build(os.path.join(HERE, "demo_update1.xer"), dd=datetime(2025, 4, 7, 8, 0),
          pct=u1_pct, float_shift=-2.0,
          af_before_as={1010},
          extra_rels=[(9999, 1140, "PR_FS", 0)])
    # Update 2 @ 2025-07-07: more progress, added + deleted activities, logic
    # churn, retroactive actual change on 1010, float erosion (negative float);
    # plus C-wave defects: 1070 held at the same 20% physical complete (no
    # further progress) but RD collapsed 192h -> 40h (DUR-04 branch 2; the
    # 152h consumed is well inside the ~500 working hours between the data
    # dates, so branch 1 correctly stays silent); a 0.5d stub wired
    # 1040->A1215->1060, added fresh, for the hollow-logic screen (LOG-10);
    # SCHEDOPTIONS retained-logic flip Y->N (SET-01); a new calendar-100
    # holiday, 2025-07-04 (CAL-04); 1130 re-parented from Mechanical (22) to
    # Civil (21) (STR-03); 1180 given an absurd 400-day float (FLT-03).
    u2_pct = {1000: 100, 1010: 100, 1020: 100, 1030: 100, 1040: 55, 1050: 70,
              1070: 20, 1080: 85, 1090: 10, 1170: 55}
    build(os.path.join(HERE, "demo_update2.xer"), dd=datetime(2025, 7, 7, 8, 0),
          pct=u2_pct, float_shift=-12.0,
          extra_acts=[(1210, "A1210", "Rework Foundations A1", "TT_Task", 12, CAL_5D, 21),
                      (1220, "MS-200", "Owner Milestone Added", "TT_FinMile", 0, CAL_5D, 24),
                      (1215, "A1215", "Reroute Stub", "TT_Task", 0.5, CAL_5D, 22)],
          removed=(1190,),
          extra_rels=[(1040, 1210, "PR_FS", 0), (1210, 1060, "PR_FS", 0),
                      (1150, 1220, "PR_FS", 0),
                      (1040, 1215, "PR_FS", 0), (1215, 1060, "PR_FS", 0)],
          removed_rels={(1050, 1070, "PR_FS")},  # lead rel — deletion now fires (bug found in wave-A audit)
          actual_overrides={1010: datetime(2025, 1, 20, 8, 0)},  # retro change vs U1
          finish_early={1020: 12},                # duration change 15d -> 12d
          rd_override={1070: 40},                 # DEFECT: RD compression, no progress
          retained_logic="N",                     # DEFECT: settings drift (SET-01)
          extra_holidays=[45842],                 # DEFECT: 2025-07-04 holiday added
          wbs_override={1130: 21},                # DEFECT: WBS re-parent 22 -> 21
          extreme_float={1180: 400 * 8})           # DEFECT: absurd float (FLT-03)
    # CPM validation-handshake fixtures (ADR-0007 / SET-02) — additive.
    build_cpm_fixtures()
    # Issue-impact fixture (ADR-0007 A2/A4/P5) — additive.
    build_impact_fixture()
    # MIP 3.4 half-step update pair (D9) — additive.
    build_halfstep_fixtures()
    print("fixtures written:", sorted(f for f in os.listdir(HERE) if f.endswith(".xer")))


if __name__ == "__main__":
    main()
