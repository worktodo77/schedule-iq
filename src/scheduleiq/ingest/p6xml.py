"""Primavera P6 XML (PMXML) parser — pure Python (xml.etree), no dependencies.

PMXML is the schema P6 uses for its native XML export/import ("Export to XML").
The root element is ``<APIBusinessObjects>``; ``Project``, ``Calendar``, ``WBS``,
``Activity``, ``ActivityRelationship``, ``ScheduleOptions``, ``Resource`` and
``ResourceAssignment`` are DIRECT CHILDREN of the root (not nested inside
``Project``), cross-referenced by ``ObjectId`` / ``ProjectObjectId`` foreign
keys — the XML-schema analog of XER's flat tables.  Durations and floats are
plain decimal HOURS (unlike MSPDI's ``PT..H..M..S`` strings); dates are
``YYYY-MM-DDTHH:MM:SS``.

The default XML namespace changes with each P6 version
(``http://xmlns.oracle.com/Primavera/P6/V23.12/API/BusinessObjects``, V21.12,
V19.12, ...), so — unlike ``msp_xml.py``, which can hardcode the stable MSPDI
namespace — this parser matches elements by LOCAL NAME only and is therefore
version-agnostic.

Fidelity target: match xer.py field-for-field (see ADR-0002 addendum) for
activities, relationships, calendars (workweek + exceptions), ScheduleOptions,
constraints, WBS, and resource assignments.  Parse issues on individual rows
are recorded in ``parse_warnings`` and never abort the parse (mirrors xer.py /
msp_xml.py discipline).
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime

from .model import (Activity, ActivityStatus, ActivityType, Calendar,
                    ConstraintType, PercentCompleteType, Relationship, RelType,
                    ResourceAssignment, Schedule, ScheduleSettings, WbsNode,
                    WorkPattern, sha256_of)

ROOT_TAG = "APIBusinessObjects"

_ACT_TYPE = {
    "Task Dependent": ActivityType.TASK,
    "Resource Dependent": ActivityType.TASK,
    "Level of Effort": ActivityType.LOE,
    "WBS Summary": ActivityType.WBS_SUMMARY,
    "Start Milestone": ActivityType.START_MILESTONE,
    "Finish Milestone": ActivityType.FINISH_MILESTONE,
    "Hammock": ActivityType.HAMMOCK,
}
_STATUS = {
    "Not Started": ActivityStatus.NOT_STARTED,
    "In Progress": ActivityStatus.IN_PROGRESS,
    "Completed": ActivityStatus.COMPLETED,
    # defensive: some exporters drop the space
    "NotStarted": ActivityStatus.NOT_STARTED,
    "InProgress": ActivityStatus.IN_PROGRESS,
}
_REL = {
    "Finish to Start": RelType.FS,
    "Start to Start": RelType.SS,
    "Finish to Finish": RelType.FF,
    "Start to Finish": RelType.SF,
}
_CSTR = {
    "Start On": ConstraintType.START_ON,
    "Start On or Before": ConstraintType.START_ON_OR_BEFORE,
    "Start On or After": ConstraintType.START_ON_OR_AFTER,
    "Finish On": ConstraintType.FINISH_ON,
    "Finish On or Before": ConstraintType.FINISH_ON_OR_BEFORE,
    "Finish On or After": ConstraintType.FINISH_ON_OR_AFTER,
    "As Late As Possible": ConstraintType.AS_LATE_AS_POSSIBLE,
    "Mandatory Start": ConstraintType.MANDATORY_START,
    "Mandatory Finish": ConstraintType.MANDATORY_FINISH,
    "Expected Finish": ConstraintType.EXPECTED_FINISH,
}
_PCT_TYPE = {
    "Duration": PercentCompleteType.DURATION,
    "Physical": PercentCompleteType.PHYSICAL,
    "Units": PercentCompleteType.UNITS,
}
_RSRC_TYPE = {"Labor": "Labor", "Material": "Material", "Nonlabor": "Nonlabor"}
_DAY_ISO = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
            "Friday": 5, "Saturday": 6, "Sunday": 7}
_CRIT_DEF = {"Total Float": "TotalFloat", "Longest Path": "LongestPath"}


# --------------------------------------------------------------------------- helpers
def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _localname(c.tag) == name]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _localname(c.tag) == name:
            return c
    return None


def _text(el: ET.Element, name: str) -> str | None:
    c = _child(el, name)
    return c.text if c is not None and c.text is not None else None


def sniff(path_or_bytes) -> bool:
    """True if the file looks like PMXML (root element ``APIBusinessObjects``,
    any namespace/version)."""
    head = path_or_bytes
    if isinstance(head, str):
        with open(head, "rb") as fh:
            head = fh.read(4096)
    return b"APIBusinessObjects" in head


def _dt(s: str | None):
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _f(s: str | None, default: float | None = None) -> float | None:
    if s is None or s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _b(s: str | None) -> bool | None:
    if s is None or s == "":
        return None
    return s.strip().lower() in ("true", "1", "y", "yes")


# --------------------------------------------------------------------------- calendars
def _parse_calendar(cal_el: ET.Element, warnings: list[str]) -> Calendar:
    uid = _text(cal_el, "ObjectId") or ""
    cal = Calendar(
        uid=uid,
        name=_text(cal_el, "Name") or "",
        ctype=_text(cal_el, "Type") or "Global",
        hours_per_day=_f(_text(cal_el, "HoursPerDay"), 8.0) or 8.0,
        hours_per_week=_f(_text(cal_el, "HoursPerWeek"), 40.0) or 40.0,
    )
    try:
        sww = _child(cal_el, "StandardWorkWeek")
        if sww is not None:
            for swh in _children(sww, "StandardWorkHours"):
                day = _text(swh, "DayOfWeek") or ""
                iso = _DAY_ISO.get(day)
                if iso is None:
                    warnings.append(f"calendar {uid}: unrecognized DayOfWeek {day!r}")
                    continue
                spans = []
                for wt in _children(swh, "WorkTime"):
                    st, ft = _text(wt, "Start"), _text(wt, "Finish")
                    if st and ft:
                        spans.append((st[:5], ft[:5]))
                cal.work_patterns[iso] = WorkPattern(weekday=iso, spans=spans)
        hoe = _child(cal_el, "HolidayOrExceptions")
        if hoe is not None:
            for exc in _children(hoe, "HolidayOrException"):
                d_raw = _text(exc, "Date")
                dt = _dt(d_raw)
                if dt is None:
                    warnings.append(f"calendar {uid}: unparsable exception date {d_raw!r}")
                    continue
                d = dt.date()
                spans = []
                for wt in _children(exc, "WorkTime"):
                    st, ft = _text(wt, "Start"), _text(wt, "Finish")
                    if st and ft:
                        spans.append((st[:5], ft[:5]))
                if spans:
                    cal.exceptions_work[d] = WorkPattern(weekday=d.isoweekday(),
                                                         spans=spans).hours
                else:
                    cal.exceptions_nonwork.add(d)
    except Exception as e:                                 # never fail the parse
        warnings.append(f"calendar {uid} ({cal.name}): unparsed structure ({e})")
    return cal


# --------------------------------------------------------------------------- activities
def _parse_activity(act_el: ET.Element, warnings: list[str]) -> Activity:
    uid = _text(act_el, "ObjectId") or ""
    type_raw = _text(act_el, "Type") or ""
    atype = _ACT_TYPE.get(type_raw)
    if atype is None:
        atype = ActivityType.TASK
        if type_raw:
            warnings.append(f"activity {uid}: unrecognized Type {type_raw!r}, defaulted to Task")
    status_raw = _text(act_el, "Status") or ""
    status = _STATUS.get(status_raw)
    if status is None:
        status = ActivityStatus.NOT_STARTED
        if status_raw:
            warnings.append(f"activity {uid}: unrecognized Status {status_raw!r}, "
                            "defaulted to Not Started")

    def cstr(type_field, date_field):
        raw = _text(act_el, type_field)
        if not raw:
            return ConstraintType.NONE, None
        ct = _CSTR.get(raw)
        if ct is None:
            warnings.append(f"activity {uid}: unrecognized {type_field} {raw!r}")
            return ConstraintType.NONE, None
        return ct, _dt(_text(act_el, date_field))

    constraint, constraint_date = cstr("PrimaryConstraintType", "PrimaryConstraintDate")
    constraint2, constraint2_date = cstr("SecondaryConstraintType", "SecondaryConstraintDate")

    pct_type_raw = _text(act_el, "PercentCompleteType")
    pct_type = _PCT_TYPE.get(pct_type_raw, PercentCompleteType.DURATION)
    physical_pct = _f(_text(act_el, "PhysicalPercentComplete"), 0.0) or 0.0
    pct_complete = _f(_text(act_el, "PercentComplete"), 0.0) or 0.0

    driving_raw = _text(act_el, "DrivingPath")
    is_longest_path = _b(driving_raw)

    act = Activity(
        uid=uid,
        code=_text(act_el, "Id") or uid,
        name=_text(act_el, "Name") or "",
        atype=atype,
        status=status,
        wbs_uid=_text(act_el, "WBSObjectId") or None,
        calendar_uid=_text(act_el, "CalendarObjectId") or None,
        original_duration_hours=_f(_text(act_el, "PlannedDuration"), 0.0) or 0.0,
        remaining_duration_hours=_f(_text(act_el, "RemainingDuration"), 0.0) or 0.0,
        at_completion_duration_hours=_f(_text(act_el, "AtCompletionDuration")),
        early_start=_dt(_text(act_el, "EarlyStart")),
        early_finish=_dt(_text(act_el, "EarlyFinish")),
        late_start=_dt(_text(act_el, "LateStart")),
        late_finish=_dt(_text(act_el, "LateFinish")),
        actual_start=_dt(_text(act_el, "ActualStart")),
        actual_finish=_dt(_text(act_el, "ActualFinish")),
        planned_start=_dt(_text(act_el, "Start")),
        planned_finish=_dt(_text(act_el, "Finish")),
        expected_finish=_dt(_text(act_el, "ExpectedFinishDate")),
        total_float_hours=_f(_text(act_el, "TotalFloat")),
        free_float_hours=_f(_text(act_el, "FreeFloat")),
        constraint=constraint,
        constraint_date=constraint_date,
        constraint2=constraint2,
        constraint2_date=constraint2_date,
        pct_complete=pct_complete,
        physical_pct=physical_pct,
        pct_type=pct_type,
        is_longest_path=is_longest_path,
        create_date=_dt(_text(act_el, "CreateDate")),
        create_user=_text(act_el, "CreateUser") or None,
        update_date=_dt(_text(act_el, "LastUpdateDate")),
        update_user=_text(act_el, "LastUpdateUser") or None,
    )
    if act.expected_finish and act.constraint == ConstraintType.NONE:
        act.constraint = ConstraintType.EXPECTED_FINISH
        act.constraint_date = act.expected_finish
    if pct_type == PercentCompleteType.PHYSICAL:
        act.pct_complete = physical_pct
    elif act.completed and not pct_complete:
        act.pct_complete = 100.0
    return act


def parse_p6xml(path: str) -> list[Schedule]:
    """Parse a P6 XML (PMXML) export.  Returns one Schedule per ``Project``
    element (multi-project exports preserved, like xer.py)."""
    warnings: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"{path}: not well-formed XML ({e})") from e
    root = tree.getroot()
    if _localname(root.tag) != ROOT_TAG:
        raise ValueError(f"{path}: root element {_localname(root.tag)!r}, "
                         f"expected {ROOT_TAG!r} (PMXML)")

    projects = _children(root, "Project")
    if not projects:
        raise ValueError(f"{path}: no Project element — not a valid PMXML export")

    export_version = root.get("ExportVersion") or ""

    # Calendars are shared across projects in the export (mirrors xer.py).
    calendars: dict[str, Calendar] = {}
    for cal_el in _children(root, "Calendar"):
        cal = _parse_calendar(cal_el, warnings)
        calendars[cal.uid] = cal

    rsrc_names: dict[str, str] = {}
    rsrc_types: dict[str, str] = {}
    for r_el in _children(root, "Resource"):
        rid = _text(r_el, "ObjectId") or ""
        rsrc_names[rid] = _text(r_el, "Name") or ""
        rsrc_types[rid] = _RSRC_TYPE.get(_text(r_el, "ResourceType") or "", "Labor")

    assignments_by_proj: dict[str, list[tuple[str, ResourceAssignment]]] = {}
    for a_el in _children(root, "ResourceAssignment"):
        pid = _text(a_el, "ProjectObjectId") or ""
        ruid = _text(a_el, "ResourceObjectId") or ""
        asg = ResourceAssignment(
            activity_uid=_text(a_el, "ActivityObjectId") or "",
            resource_uid=ruid,
            resource_name=rsrc_names.get(ruid, ""),
            resource_type=rsrc_types.get(ruid, "Labor"),
            budget_units=_f(_text(a_el, "BudgetedUnits"), 0.0) or 0.0,
            actual_units=_f(_text(a_el, "ActualUnits"), 0.0) or 0.0,
            remaining_units=_f(_text(a_el, "RemainingUnits"), 0.0) or 0.0,
            budget_cost=_f(_text(a_el, "BudgetedCost"), 0.0) or 0.0,
            actual_cost=_f(_text(a_el, "ActualCost"), 0.0) or 0.0,
            remaining_cost=_f(_text(a_el, "RemainingCost"), 0.0) or 0.0,
        )
        assignments_by_proj.setdefault(pid, []).append((asg.activity_uid, asg))

    all_wbs = _children(root, "WBS")
    all_activities = _children(root, "Activity")
    all_rels = _children(root, "ActivityRelationship")
    all_schedopts = _children(root, "ScheduleOptions")

    out: list[Schedule] = []
    for proj_el in projects:
        pid = _text(proj_el, "ObjectId") or ""
        default_cal = _text(proj_el, "DefaultCalendarObjectId")
        if default_cal and default_cal in calendars:
            calendars[default_cal].is_default = True

        sched = Schedule(
            project_id=_text(proj_el, "Id") or pid,
            project_name=_text(proj_el, "Name") or "",
            data_date=_dt(_text(proj_el, "DataDate")),
            start_date=_dt(_text(proj_el, "PlannedStartDate")),
            finish_date=_dt(_text(proj_el, "ScheduledFinishDate")),
            must_finish_by=_dt(_text(proj_el, "MustFinishDate")),
            baseline_finish=_dt(_text(proj_el, "BaselineFinishDate")),
            source_file=os.path.basename(path),
            source_format="P6XML",
            source_sha256=sha256_of(path),
            source_tool=f"P6 (PMXML{' v' + export_version if export_version else ''})",
            export_user=_text(proj_el, "CreateUser") or "",
            export_date=_dt(_text(proj_el, "LastUpdateDate")),
            project_create_date=_dt(_text(proj_el, "CreateDate")),
            project_create_user=_text(proj_el, "CreateUser") or "",
            project_update_date=_dt(_text(proj_el, "LastUpdateDate")),
            project_update_user=_text(proj_el, "LastUpdateUser") or "",
        )
        sched.calendars = calendars

        so_el = next((s for s in all_schedopts if _text(s, "ProjectObjectId") == pid), None)
        if so_el is not None:
            sp = _text(so_el, "SchedulingProgressedActivities")
            retained_logic = progress_override = actual_dates = None
            if sp == "Retained Logic":
                retained_logic, progress_override = True, False
            elif sp == "Progress Override":
                retained_logic, progress_override = False, True
            elif sp == "Actual Dates":
                actual_dates = True
            elif sp:
                warnings.append(f"project {pid}: unrecognized SchedulingProgressedActivities "
                                f"{sp!r}")
            crit_def_raw = _text(so_el, "DefineCriticalActivities")
            sched.settings = ScheduleSettings(
                retained_logic=retained_logic,
                progress_override=progress_override,
                actual_dates=actual_dates,
                relationship_lag_calendar=_text(so_el, "RelationshipLagCalendar") or None,
                critical_float_threshold_hours=_f(_text(so_el, "CriticalFloatThreshold")),
                critical_definition=_CRIT_DEF.get(crit_def_raw, crit_def_raw),
                make_open_ends_critical=_b(_text(so_el, "MakeOpenEndedActivitiesCritical")),
                use_expected_finish=_b(_text(so_el, "UseExpectedFinishDates")),
                raw={_localname(c.tag): c.text for c in so_el
                     if c.text and _localname(c.tag) not in ("ObjectId", "ProjectObjectId")},
            )
        else:
            warnings.append(f"project {pid}: no ScheduleOptions element found")

        for wbs_el in all_wbs:
            if _text(wbs_el, "ProjectObjectId") != pid:
                continue
            wuid = _text(wbs_el, "ObjectId") or ""
            sched.wbs[wuid] = WbsNode(
                uid=wuid,
                parent_uid=_text(wbs_el, "ParentObjectId") or None,
                code=_text(wbs_el, "Code") or "",
                name=_text(wbs_el, "Name") or "",
            )

        proj_assignments: dict[str, list[ResourceAssignment]] = {}
        for act_uid, asg in assignments_by_proj.get(pid, []):
            proj_assignments.setdefault(act_uid, []).append(asg)

        for act_el in all_activities:
            if _text(act_el, "ProjectObjectId") != pid:
                continue
            act = _parse_activity(act_el, warnings)
            act.resources = proj_assignments.get(act.uid, [])
            act.budget_cost = sum(r.budget_cost for r in act.resources)
            act.actual_cost = sum(r.actual_cost for r in act.resources)
            act.remaining_cost = sum(r.remaining_cost for r in act.resources)
            sched.activities[act.uid] = act

        act_ids = set(sched.activities)
        for rel_el in all_rels:
            pred = _text(rel_el, "PredecessorActivityObjectId") or ""
            succ = _text(rel_el, "SuccessorActivityObjectId") or ""
            if succ not in act_ids and pred not in act_ids:
                continue                                   # other project in the export
            if succ in act_ids and pred not in act_ids:
                warnings.append(f"external predecessor {pred} -> {succ} "
                                "(cross-project or missing) kept")
            type_raw = _text(rel_el, "Type") or ""
            rtype = _REL.get(type_raw)
            if rtype is None:
                if type_raw:
                    warnings.append(f"relationship {pred}->{succ}: unrecognized Type "
                                    f"{type_raw!r}, defaulted to FS")
                rtype = RelType.FS
            sched.relationships.append(Relationship(
                pred_uid=pred, succ_uid=succ, rtype=rtype,
                lag_hours=_f(_text(rel_el, "Lag"), 0.0) or 0.0,
            ))

        sched.parse_warnings = list(warnings)
        out.append(sched)
    return out
