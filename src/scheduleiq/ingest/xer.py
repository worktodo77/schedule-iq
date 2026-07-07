"""Primavera P6 .xer parser (pure Python, no dependencies).

The XER format is a tab-delimited text export: an ERMHDR header line, then for
each table a ``%T <table>`` line, a ``%F <field...>`` line, and ``%R <value...>``
rows.  Encoding is normally cp1252; P6 writes dates as ``YYYY-MM-DD HH:MM``.
Durations and floats are stored in hours (``*_hr_cnt`` fields).

Every schedule figure downstream must be reproducible from these tables, so the
parser keeps the raw tables available on the result (``Schedule`` is built from
them, and parse warnings are recorded rather than silently dropped).
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

from .model import (Activity, ActivityStatus, ActivityType, Calendar,
                    ConstraintType, PercentCompleteType, Relationship, RelType,
                    ResourceAssignment, Schedule, ScheduleSettings, WbsNode,
                    WorkPattern, sha256_of)

_TASK_TYPE = {
    "TT_Task": ActivityType.TASK,
    "TT_Rsrc": ActivityType.TASK,               # resource-dependent task
    "TT_Mile": ActivityType.START_MILESTONE,
    "TT_FinMile": ActivityType.FINISH_MILESTONE,
    "TT_LOE": ActivityType.LOE,
    "TT_WBS": ActivityType.WBS_SUMMARY,
    "TT_Hammock": ActivityType.HAMMOCK,
}
_STATUS = {
    "TK_NotStart": ActivityStatus.NOT_STARTED,
    "TK_Active": ActivityStatus.IN_PROGRESS,
    "TK_Complete": ActivityStatus.COMPLETED,
}
_REL = {"PR_FS": RelType.FS, "PR_SS": RelType.SS,
        "PR_FF": RelType.FF, "PR_SF": RelType.SF,
        "PR_FS1": RelType.FS}
_CSTR = {
    "": ConstraintType.NONE,
    "CS_ALAP": ConstraintType.AS_LATE_AS_POSSIBLE,
    "CS_MEO": ConstraintType.FINISH_ON,
    "CS_MEOA": ConstraintType.FINISH_ON_OR_AFTER,
    "CS_MEOB": ConstraintType.FINISH_ON_OR_BEFORE,
    "CS_MANDFIN": ConstraintType.MANDATORY_FINISH,
    "CS_MANDSTART": ConstraintType.MANDATORY_START,
    "CS_MSO": ConstraintType.START_ON,
    "CS_MSOA": ConstraintType.START_ON_OR_AFTER,
    "CS_MSOB": ConstraintType.START_ON_OR_BEFORE,
}
_PCT = {"CP_Drtn": PercentCompleteType.DURATION,
        "CP_Phys": PercentCompleteType.PHYSICAL,
        "CP_Units": PercentCompleteType.UNITS}

_EPOCH_1899 = date(1899, 12, 30)   # P6 calendar-exception day numbers


def _dt(s: str | None):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _f(s: str | None, default: float | None = None):
    if s is None or s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def read_tables(path: str, encoding: str = "cp1252") -> tuple[dict, list[str]]:
    """Return ({table_name: [row_dict, ...]}, header_fields)."""
    tables: dict[str, list[dict]] = {}
    header: list[str] = []
    cur: str | None = None
    fields: list[str] = []
    with open(path, "r", encoding=encoding, errors="replace", newline="") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("ERMHDR"):
                header = line.split("\t")
                continue
            tag, _, rest = line.partition("\t")
            if tag == "%T":
                cur = rest.strip()
                tables.setdefault(cur, [])
                fields = []
            elif tag == "%F":
                fields = [f.strip() for f in rest.split("\t")]
            elif tag == "%R" and cur is not None:
                vals = rest.split("\t")
                row = {fields[i]: (vals[i] if i < len(vals) else "")
                       for i in range(len(fields))}
                tables[cur].append(row)
            # %E = end of export
    return tables, header


# --------------------------------------------------------------------------
# Calendar-data blob:  (0||CalendarData()( (0||DaysOfWeek()(...)) (0||Exceptions()(...)) ))
# Weekday keys are P6 numbering 1=Sunday..7=Saturday; work spans are
# s|08:00 ... f|17:00 pairs; exceptions are d|<days since 1899-12-30>.
# --------------------------------------------------------------------------
def parse_calendar_data(blob: str, cal: Calendar) -> None:
    if not blob:
        return
    dow = re.search(r"DaysOfWeek\(\)(.*?)(?:\(0\|\|(?:VIEW|Exceptions))", blob, re.S)
    dow_text = dow.group(1) if dow else blob
    for m in re.finditer(r"\(0\|\|([1-7])\(\)([^)]*(?:\([^)]*\)[^)]*)*)\)", dow_text):
        p6_day = int(m.group(1))
        body = m.group(2)
        spans = re.findall(r"s\|(\d{2}:\d{2})\|f\|(\d{2}:\d{2})", body)
        iso = 7 if p6_day == 1 else p6_day - 1        # P6 1=Sun -> ISO 7
        cal.work_patterns[iso] = WorkPattern(weekday=iso,
                                             spans=[(s, f) for s, f in spans])
    exc = re.search(r"Exceptions\(\)(.*)$", blob, re.S)
    if exc:
        for m in re.finditer(r"d\|(\d+)\)\(([^)]*)\)", exc.group(1)):
            day = _EPOCH_1899 + timedelta(days=int(m.group(1)))
            spans = re.findall(r"s\|(\d{2}:\d{2})\|f\|(\d{2}:\d{2})", m.group(2))
            if spans:
                cal.exceptions_work[day] = WorkPattern(weekday=day.isoweekday(),
                                                       spans=spans).hours
            else:
                cal.exceptions_nonwork.add(day)
        # exceptions written as d|NNNN) with no span group at all
        for m in re.finditer(r"d\|(\d+)\)(?!\()", exc.group(1)):
            cal.exceptions_nonwork.add(_EPOCH_1899 + timedelta(days=int(m.group(1))))


def parse_xer(path: str, project_id: str | None = None) -> list[Schedule]:
    """Parse an .xer file.  Returns one Schedule per exported project
    (multi-project exports are preserved; cross-project relationships are
    attached to the successor's project with a warning)."""
    tables, header = read_tables(path)
    warnings: list[str] = []

    projects = tables.get("PROJECT", [])
    if not projects:
        raise ValueError(f"{path}: no PROJECT table — not a valid XER export")
    if project_id:
        projects = [p for p in projects if p.get("proj_short_name") == project_id
                    or p.get("proj_id") == project_id]

    # calendars are shared across projects in the export
    calendars: dict[str, Calendar] = {}
    for row in tables.get("CALENDAR", []):
        cal = Calendar(
            uid=row.get("clndr_id", ""),
            name=row.get("clndr_name", ""),
            ctype={"CA_Base": "Global", "CA_Project": "Project",
                   "CA_Rsrc": "Resource"}.get(row.get("clndr_type", ""), "Global"),
            hours_per_day=_f(row.get("day_hr_cnt"), 8.0) or 8.0,
            hours_per_week=_f(row.get("week_hr_cnt"), 40.0) or 40.0,
            is_default=row.get("default_flag", "") == "Y",
        )
        try:
            parse_calendar_data(row.get("clndr_data", ""), cal)
        except Exception as e:                        # never fail the parse on a blob
            warnings.append(f"calendar {cal.uid} ({cal.name}): unparsed data blob ({e})")
        calendars[cal.uid] = cal

    rsrc_names = {r.get("rsrc_id"): (r.get("rsrc_name") or r.get("rsrc_short_name") or "")
                  for r in tables.get("RSRC", [])}
    rsrc_types = {r.get("rsrc_id"): {"RT_Labor": "Labor", "RT_Mat": "Material",
                                     "RT_Equip": "Nonlabor"}.get(r.get("rsrc_type", ""), "Labor")
                  for r in tables.get("RSRC", [])}

    assignments: dict[str, list[ResourceAssignment]] = {}
    for row in tables.get("TASKRSRC", []):
        a = ResourceAssignment(
            activity_uid=row.get("task_id", ""),
            resource_uid=row.get("rsrc_id", ""),
            resource_name=rsrc_names.get(row.get("rsrc_id"), ""),
            resource_type=rsrc_types.get(row.get("rsrc_id"), "Labor"),
            budget_units=_f(row.get("target_qty"), 0.0) or 0.0,
            actual_units=(_f(row.get("act_reg_qty"), 0.0) or 0.0)
                          + (_f(row.get("act_ot_qty"), 0.0) or 0.0),
            remaining_units=_f(row.get("remain_qty"), 0.0) or 0.0,
            budget_cost=_f(row.get("target_cost"), 0.0) or 0.0,
            actual_cost=(_f(row.get("act_reg_cost"), 0.0) or 0.0)
                         + (_f(row.get("act_ot_cost"), 0.0) or 0.0),
            remaining_cost=_f(row.get("remain_cost"), 0.0) or 0.0,
        )
        assignments.setdefault(a.activity_uid, []).append(a)

    schedopts = {row.get("proj_id"): row for row in tables.get("SCHEDOPTIONS", [])}

    out: list[Schedule] = []
    for proj in projects:
        pid = proj.get("proj_id", "")
        sched = Schedule(
            project_id=proj.get("proj_short_name", "") or pid,
            project_name=proj.get("proj_short_name", ""),
            data_date=_dt(proj.get("last_recalc_date")),
            start_date=_dt(proj.get("plan_start_date")),
            finish_date=_dt(proj.get("scd_end_date")),
            must_finish_by=_dt(proj.get("plan_end_date")),
            source_file=os.path.basename(path),
            source_format="XER",
            source_sha256=sha256_of(path),
            source_tool=f"P6 (XER {header[1] if len(header) > 1 else '?'})",
            export_user=header[4] if len(header) > 4 else "",
            export_date=_dt(header[2]) if len(header) > 2 else None,
            project_create_date=_dt(proj.get("create_date")),
            project_create_user=proj.get("create_user") or "",
            project_update_date=_dt(proj.get("update_date")),
            project_update_user=proj.get("update_user") or "",
        )
        so = schedopts.get(pid, {})
        logic_mode = so.get("sched_retained_logic")
        prog_override = so.get("sched_progress_override")
        sched.settings = ScheduleSettings(
            retained_logic=(logic_mode == "Y") if logic_mode in ("Y", "N") else None,
            progress_override=(prog_override == "Y") if prog_override in ("Y", "N") else None,
            relationship_lag_calendar=so.get("sched_calendar_on_relationship_lag") or None,
            critical_float_threshold_hours=_f(so.get("sched_critical_float_hr_cnt")),
            make_open_ends_critical=(so.get("sched_open_critical_flag") == "Y")
                                     if so.get("sched_open_critical_flag") else None,
            use_expected_finish=(so.get("sched_use_expect_end_flag") == "Y")
                                 if so.get("sched_use_expect_end_flag") else None,
            raw={k: v for k, v in so.items() if v},
        )
        sched.calendars = calendars

        for row in tables.get("PROJWBS", []):
            if row.get("proj_id") != pid:
                continue
            sched.wbs[row.get("wbs_id", "")] = WbsNode(
                uid=row.get("wbs_id", ""),
                parent_uid=row.get("parent_wbs_id") or None,
                code=row.get("wbs_short_name", ""),
                name=row.get("wbs_name", ""),
            )

        for row in tables.get("TASK", []):
            if row.get("proj_id") != pid:
                continue
            uid = row.get("task_id", "")
            act = Activity(
                uid=uid,
                code=row.get("task_code", ""),
                name=row.get("task_name", ""),
                atype=_TASK_TYPE.get(row.get("task_type", ""), ActivityType.TASK),
                status=_STATUS.get(row.get("status_code", ""), ActivityStatus.NOT_STARTED),
                wbs_uid=row.get("wbs_id") or None,
                calendar_uid=row.get("clndr_id") or None,
                original_duration_hours=_f(row.get("target_drtn_hr_cnt"), 0.0) or 0.0,
                remaining_duration_hours=_f(row.get("remain_drtn_hr_cnt"), 0.0) or 0.0,
                early_start=_dt(row.get("early_start_date")),
                early_finish=_dt(row.get("early_end_date")),
                late_start=_dt(row.get("late_start_date")),
                late_finish=_dt(row.get("late_end_date")),
                actual_start=_dt(row.get("act_start_date")),
                actual_finish=_dt(row.get("act_end_date")),
                planned_start=_dt(row.get("target_start_date")),
                planned_finish=_dt(row.get("target_end_date")),
                suspend_date=_dt(row.get("suspend_date")),
                resume_date=_dt(row.get("resume_date")),
                expected_finish=_dt(row.get("expect_end_date")),
                total_float_hours=_f(row.get("total_float_hr_cnt")),
                free_float_hours=_f(row.get("free_float_hr_cnt")),
                constraint=_CSTR.get(row.get("cstr_type", ""), ConstraintType.NONE),
                constraint_date=_dt(row.get("cstr_date")),
                constraint2=_CSTR.get(row.get("cstr_type2", ""), ConstraintType.NONE),
                constraint2_date=_dt(row.get("cstr_date2")),
                physical_pct=_f(row.get("phys_complete_pct"), 0.0) or 0.0,
                pct_type=_PCT.get(row.get("complete_pct_type", ""),
                                  PercentCompleteType.DURATION),
                is_longest_path=(row.get("driving_path_flag") == "Y")
                                 if row.get("driving_path_flag") else None,
                create_date=_dt(row.get("create_date")),
                create_user=row.get("create_user") or None,
                update_date=_dt(row.get("update_date")),
                update_user=row.get("update_user") or None,
            )
            if act.expected_finish and act.constraint == ConstraintType.NONE:
                act.constraint = ConstraintType.EXPECTED_FINISH
                act.constraint_date = act.expected_finish
            # percent complete per its type
            if act.pct_type == PercentCompleteType.PHYSICAL:
                act.pct_complete = act.physical_pct
            elif act.completed:
                act.pct_complete = 100.0
            elif act.original_duration_hours > 0 and act.status == ActivityStatus.IN_PROGRESS:
                od, rd = act.original_duration_hours, act.remaining_duration_hours
                act.pct_complete = max(0.0, min(100.0, 100.0 * (1 - rd / od))) if od else 0.0
            act.resources = assignments.get(uid, [])
            act.budget_cost = sum(r.budget_cost for r in act.resources)
            act.actual_cost = sum(r.actual_cost for r in act.resources)
            act.remaining_cost = sum(r.remaining_cost for r in act.resources)
            sched.activities[uid] = act

        act_ids = set(sched.activities)
        for row in tables.get("TASKPRED", []):
            succ, pred = row.get("task_id", ""), row.get("pred_task_id", "")
            if succ not in act_ids and pred not in act_ids:
                continue                              # other project in the export
            if succ in act_ids and pred not in act_ids:
                warnings.append(f"external predecessor {pred} -> {succ} "
                                "(cross-project or missing) kept")
            sched.relationships.append(Relationship(
                pred_uid=pred, succ_uid=succ,
                rtype=_REL.get(row.get("pred_type", ""), RelType.FS),
                lag_hours=_f(row.get("lag_hr_cnt"), 0.0) or 0.0,
            ))

        sched.parse_warnings = list(warnings)
        out.append(sched)
    return out
