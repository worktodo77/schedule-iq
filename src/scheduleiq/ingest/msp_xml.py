"""Microsoft Project MSPDI (.xml) parser — pure Python (xml.etree).

MSPDI stores durations as ISO-8601-ish strings (``PT16H0M0S``), slack in
tenths of minutes... except when it doesn't: TotalSlack/StartSlack/FinishSlack
are integers in tenths of minutes in most exports.  Both encodings are handled.
PredecessorLink Type: 0=FF, 1=FS, 2=SF, 3=SS.  ConstraintType: 0=ASAP, 1=ALAP,
2=Must Start On, 3=Must Finish On, 4=SNET, 5=SNLT, 6=FNET, 7=FNLT.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from .model import (Activity, ActivityStatus, ActivityType, Calendar,
                    ConstraintType, PercentCompleteType, Relationship, RelType,
                    ResourceAssignment, Schedule, WbsNode, WorkPattern,
                    sha256_of)

_NS = "http://schemas.microsoft.com/project"
_REL = {0: RelType.FF, 1: RelType.FS, 2: RelType.SF, 3: RelType.SS}
_CSTR = {0: ConstraintType.NONE, 1: ConstraintType.AS_LATE_AS_POSSIBLE,
         2: ConstraintType.MANDATORY_START, 3: ConstraintType.MANDATORY_FINISH,
         4: ConstraintType.START_ON_OR_AFTER, 5: ConstraintType.START_ON_OR_BEFORE,
         6: ConstraintType.FINISH_ON_OR_AFTER, 7: ConstraintType.FINISH_ON_OR_BEFORE}

_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


def _tag(el, name):
    v = el.find(f"{{{_NS}}}{name}")
    return v.text if v is not None and v.text is not None else None


def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        return None


def _dur_hours(s) -> float:
    if not s:
        return 0.0
    m = _DUR_RE.match(s)
    if not m:
        return 0.0
    h = float(m.group(1) or 0)
    mi = float(m.group(2) or 0)
    sec = float(m.group(3) or 0)
    return h + mi / 60 + sec / 3600


def _slack_hours(s) -> float | None:
    """Slack fields: integer tenths of minutes, or a PT..H..M..S duration."""
    if s is None or s == "":
        return None
    if s.startswith("PT") or s.startswith("-PT"):
        sign = -1 if s.startswith("-") else 1
        return sign * _dur_hours(s.lstrip("-"))
    try:
        return float(s) / 600.0        # tenths of minutes -> hours
    except ValueError:
        return None


def parse_mspdi(path: str) -> list[Schedule]:
    tree = ET.parse(path)
    root = tree.getroot()
    sched = Schedule(
        project_id=_tag(root, "Name") or os.path.splitext(os.path.basename(path))[0],
        project_name=_tag(root, "Title") or _tag(root, "Name") or "",
        data_date=_dt(_tag(root, "StatusDate")) or _dt(_tag(root, "CurrentDate")),
        start_date=_dt(_tag(root, "StartDate")),
        finish_date=_dt(_tag(root, "FinishDate")),
        source_file=os.path.basename(path),
        source_format="MSPDI",
        source_sha256=sha256_of(path),
        source_tool=f"Microsoft Project (SaveVersion {_tag(root, 'SaveVersion') or '?'})",
        export_date=_dt(_tag(root, "LastSaved")),
    )
    default_hpd = (float(_tag(root, "MinutesPerDay") or 480)) / 60.0

    for cal_el in root.iter(f"{{{_NS}}}Calendar"):
        cal = Calendar(uid=_tag(cal_el, "UID") or "",
                       name=_tag(cal_el, "Name") or "",
                       hours_per_day=default_hpd,
                       hours_per_week=(float(_tag(root, "MinutesPerWeek") or 2400)) / 60.0)
        for wd in cal_el.iter(f"{{{_NS}}}WeekDay"):
            day_type = _tag(wd, "DayType")
            working = _tag(wd, "DayWorking") == "1"
            spans = []
            for wt in wd.iter(f"{{{_NS}}}WorkingTime"):
                ft, tt = _tag(wt, "FromTime"), _tag(wt, "ToTime")
                if ft and tt:
                    spans.append((ft[:5], tt[:5]))
            if day_type and day_type.isdigit():
                d = int(day_type)
                if 1 <= d <= 7:                        # 1=Sunday .. 7=Saturday
                    iso = 7 if d == 1 else d - 1
                    cal.work_patterns[iso] = WorkPattern(weekday=iso,
                                                         spans=spans if working else [])
                elif d == 0:                           # exception day
                    tp = wd.find(f"{{{_NS}}}TimePeriod")
                    if tp is not None:
                        f_ = _dt(_tag(tp, "FromDate"))
                        t_ = _dt(_tag(tp, "ToDate"))
                        if f_ and t_:
                            cur = f_.date()
                            while cur <= t_.date():
                                if working and spans:
                                    cal.exceptions_work[cur] = WorkPattern(
                                        weekday=cur.isoweekday(), spans=spans).hours
                                else:
                                    cal.exceptions_nonwork.add(cur)
                                cur += timedelta(days=1)
        sched.calendars[cal.uid] = cal
    if sched.calendars and _tag(root, "CalendarUID"):
        base = _tag(root, "CalendarUID")
        if base in sched.calendars:
            sched.calendars[base].is_default = True

    rsrc_names, rsrc_types = {}, {}
    resources_el = root.find(f"{{{_NS}}}Resources")
    if resources_el is not None:
        for r in resources_el.iter(f"{{{_NS}}}Resource"):
            uid = _tag(r, "UID")
            rsrc_names[uid] = _tag(r, "Name") or ""
            rsrc_types[uid] = {"0": "Material", "1": "Labor", "2": "Cost"}.get(
                _tag(r, "Type") or "1", "Labor")

    tasks_el = root.find(f"{{{_NS}}}Tasks")
    if tasks_el is None:
        raise ValueError(f"{path}: no Tasks element — not a valid MSPDI file")
    for t in tasks_el.iter(f"{{{_NS}}}Task"):
        uid = _tag(t, "UID")
        if uid is None or _tag(t, "IsNull") == "1":
            continue
        if uid == "0":                                 # project summary row
            continue
        is_summary = _tag(t, "Summary") == "1"
        is_milestone = _tag(t, "Milestone") == "1"
        pct = float(_tag(t, "PercentComplete") or 0)
        act_start, act_finish = _dt(_tag(t, "ActualStart")), _dt(_tag(t, "ActualFinish"))
        if act_finish or pct >= 100:
            status = ActivityStatus.COMPLETED
        elif act_start or pct > 0:
            status = ActivityStatus.IN_PROGRESS
        else:
            status = ActivityStatus.NOT_STARTED
        dur_h = _dur_hours(_tag(t, "Duration"))
        rem_h = _dur_hours(_tag(t, "RemainingDuration"))
        atype = (ActivityType.SUMMARY if is_summary else
                 (ActivityType.FINISH_MILESTONE if is_milestone else ActivityType.TASK))
        act = Activity(
            uid=uid,
            code=_tag(t, "ID") or uid,
            name=_tag(t, "Name") or "",
            atype=atype,
            status=status,
            calendar_uid=_tag(t, "CalendarUID"),
            wbs_uid=_tag(t, "WBS"),
            original_duration_hours=dur_h,
            remaining_duration_hours=rem_h if (act_start or rem_h) else dur_h,
            early_start=_dt(_tag(t, "EarlyStart") or _tag(t, "Start")),
            early_finish=_dt(_tag(t, "EarlyFinish") or _tag(t, "Finish")),
            late_start=_dt(_tag(t, "LateStart")),
            late_finish=_dt(_tag(t, "LateFinish")),
            actual_start=act_start,
            actual_finish=act_finish,
            planned_start=_dt(_tag(t, "Start")),
            planned_finish=_dt(_tag(t, "Finish")),
            baseline_start=None,
            baseline_finish=None,
            total_float_hours=_slack_hours(_tag(t, "TotalSlack")),
            free_float_hours=_slack_hours(_tag(t, "FreeSlack")),
            constraint=_CSTR.get(int(_tag(t, "ConstraintType") or 0), ConstraintType.NONE),
            constraint_date=_dt(_tag(t, "ConstraintDate")),
            pct_complete=pct,
            physical_pct=float(_tag(t, "PhysicalPercentComplete") or 0),
            pct_type=(PercentCompleteType.PHYSICAL
                      if _tag(t, "PhysicalPercentComplete") not in (None, "0")
                      else PercentCompleteType.DURATION),
            is_critical_flag=_tag(t, "Critical") == "1",
        )
        for bl in t.iter(f"{{{_NS}}}Baseline"):
            if _tag(bl, "Number") == "0":
                act.baseline_start = _dt(_tag(bl, "Start"))
                act.baseline_finish = _dt(_tag(bl, "Finish"))
        if act.calendar_uid == "-1":
            act.calendar_uid = _tag(root, "CalendarUID")
        sched.activities[uid] = act
        if act.wbs_uid and act.wbs_uid not in sched.wbs:
            sched.wbs[act.wbs_uid] = WbsNode(uid=act.wbs_uid, parent_uid=None,
                                             code=act.wbs_uid, name="")
        for pl in t.findall(f"{{{_NS}}}PredecessorLink"):
            pred = _tag(pl, "PredecessorUID")
            lag_raw = _tag(pl, "LinkLag")           # tenths of minutes
            lag_h = (float(lag_raw) / 600.0) if lag_raw else 0.0
            sched.relationships.append(Relationship(
                pred_uid=pred, succ_uid=uid,
                rtype=_REL.get(int(_tag(pl, "Type") or 1), RelType.FS),
                lag_hours=lag_h))

    asg_el = root.find(f"{{{_NS}}}Assignments")
    if asg_el is not None:
        for a in asg_el.iter(f"{{{_NS}}}Assignment"):
            tuid, ruid = _tag(a, "TaskUID"), _tag(a, "ResourceUID")
            if tuid in sched.activities and ruid not in (None, "-65535"):
                asg = ResourceAssignment(
                    activity_uid=tuid, resource_uid=ruid or "",
                    resource_name=rsrc_names.get(ruid, ""),
                    resource_type=rsrc_types.get(ruid, "Labor"),
                    budget_units=_dur_hours(_tag(a, "Work")),
                    actual_units=_dur_hours(_tag(a, "ActualWork")),
                    remaining_units=_dur_hours(_tag(a, "RemainingWork")),
                    budget_cost=float(_tag(a, "Cost") or 0),
                    actual_cost=float(_tag(a, "ActualCost") or 0),
                    remaining_cost=float(_tag(a, "RemainingCost") or 0),
                )
                act = sched.activities[tuid]
                act.resources.append(asg)
                act.budget_cost += asg.budget_cost
                act.actual_cost += asg.actual_cost
                act.remaining_cost += asg.remaining_cost

    return [sched]
