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
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
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
    print("fixtures written:", sorted(f for f in os.listdir(HERE) if f.endswith(".xer")))


if __name__ == "__main__":
    main()
