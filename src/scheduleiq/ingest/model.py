"""Canonical, format-neutral schedule model.

Every ingest path (.xer, MSPDI .xml, .mpp via MPXJ) normalizes into these
dataclasses so the metrics engine, trend engine, and comparison engine never
touch format-specific structures.  Durations and floats are carried in HOURS
(the P6 native unit) with day conversions performed through each activity's
calendar (never a global 8-hour assumption — see check CAL-02).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class ActivityType(str, Enum):
    TASK = "Task"
    START_MILESTONE = "Start Milestone"
    FINISH_MILESTONE = "Finish Milestone"
    LOE = "Level of Effort"
    WBS_SUMMARY = "WBS Summary"
    HAMMOCK = "Hammock"
    SUMMARY = "Summary"          # MSP summary rows (excluded from most checks)


class ActivityStatus(str, Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class RelType(str, Enum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


class ConstraintType(str, Enum):
    NONE = "None"
    START_ON = "Start On"                      # CS_MSO / MSO
    START_ON_OR_BEFORE = "Start On or Before"  # CS_MSOB / SNLT
    START_ON_OR_AFTER = "Start On or After"    # CS_MSOA / SNET
    FINISH_ON = "Finish On"                    # CS_MEO / MFO
    FINISH_ON_OR_BEFORE = "Finish On or Before"  # CS_MEOB / FNLT
    FINISH_ON_OR_AFTER = "Finish On or After"    # CS_MEOA / FNET
    AS_LATE_AS_POSSIBLE = "As Late as Possible"  # CS_ALAP
    MANDATORY_START = "Mandatory Start"        # CS_MANDSTART
    MANDATORY_FINISH = "Mandatory Finish"      # CS_MANDFIN
    EXPECTED_FINISH = "Expected Finish"        # P6 expect_end_date

    @property
    def is_hard(self) -> bool:
        """Hard (two-way) constraints override network logic in both directions."""
        return self in (
            ConstraintType.MANDATORY_START,
            ConstraintType.MANDATORY_FINISH,
            ConstraintType.START_ON,
            ConstraintType.FINISH_ON,
        )

    @property
    def is_late_type(self) -> bool:
        """Constraints that prevent rightward movement (DCMA 'hard' set):
        can create negative float and mask true criticality."""
        return self in (
            ConstraintType.START_ON_OR_BEFORE,
            ConstraintType.FINISH_ON_OR_BEFORE,
            ConstraintType.START_ON,
            ConstraintType.FINISH_ON,
            ConstraintType.MANDATORY_START,
            ConstraintType.MANDATORY_FINISH,
        )


class PercentCompleteType(str, Enum):
    DURATION = "Duration"
    PHYSICAL = "Physical"
    UNITS = "Units"


@dataclass
class WorkPattern:
    """One weekday's working spans, e.g. [("08:00","12:00"),("13:00","17:00")]."""
    weekday: int                      # ISO: 1=Monday .. 7=Sunday
    spans: list[tuple[str, str]] = field(default_factory=list)

    @property
    def hours(self) -> float:
        total = 0.0
        for s, f in self.spans:
            sh, sm = int(s[:2]), int(s[3:5])
            fh, fm = int(f[:2]), int(f[3:5])
            span = (fh + fm / 60) - (sh + sm / 60)
            if span <= 0:             # spans like 00:00-00:00 mean a full day in P6
                span += 24
            total += span
        return total


@dataclass
class Calendar:
    uid: str
    name: str = ""
    ctype: str = "Global"             # Global | Project | Resource
    hours_per_day: float = 8.0
    hours_per_week: float = 40.0
    is_default: bool = False
    work_patterns: dict[int, WorkPattern] = field(default_factory=dict)
    exceptions_nonwork: set[date] = field(default_factory=set)
    exceptions_work: dict[date, float] = field(default_factory=dict)  # date -> hours

    @property
    def workdays_per_week(self) -> int:
        if not self.work_patterns:
            return 5
        return sum(1 for p in self.work_patterns.values() if p.spans)

    def is_workday(self, d: date) -> bool:
        if d in self.exceptions_nonwork:
            return False
        if d in self.exceptions_work:
            return self.exceptions_work[d] > 0
        p = self.work_patterns.get(d.isoweekday())
        if p is None:
            return d.isoweekday() <= 5 if not self.work_patterns else False
        return bool(p.spans)


@dataclass
class Relationship:
    pred_uid: str
    succ_uid: str
    rtype: RelType = RelType.FS
    lag_hours: float = 0.0

    def key(self) -> tuple:
        return (self.pred_uid, self.succ_uid, self.rtype.value)


@dataclass
class ResourceAssignment:
    activity_uid: str
    resource_uid: str
    resource_name: str = ""
    resource_type: str = "Labor"      # Labor | Material | Equipment/Nonlabor
    budget_units: float = 0.0
    actual_units: float = 0.0
    remaining_units: float = 0.0
    budget_cost: float = 0.0
    actual_cost: float = 0.0
    remaining_cost: float = 0.0


@dataclass
class Activity:
    uid: str                          # stable internal id (task_id / UID)
    code: str                         # analyst-facing id (task_code / MSP ID)
    name: str = ""
    atype: ActivityType = ActivityType.TASK
    status: ActivityStatus = ActivityStatus.NOT_STARTED
    wbs_uid: Optional[str] = None
    calendar_uid: Optional[str] = None

    original_duration_hours: float = 0.0
    remaining_duration_hours: float = 0.0
    at_completion_duration_hours: Optional[float] = None

    early_start: Optional[datetime] = None
    early_finish: Optional[datetime] = None
    late_start: Optional[datetime] = None
    late_finish: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_finish: Optional[datetime] = None
    planned_start: Optional[datetime] = None   # target/baseline-in-file dates
    planned_finish: Optional[datetime] = None
    baseline_start: Optional[datetime] = None  # from linked baseline, if any
    baseline_finish: Optional[datetime] = None
    suspend_date: Optional[datetime] = None
    resume_date: Optional[datetime] = None
    expected_finish: Optional[datetime] = None

    total_float_hours: Optional[float] = None
    free_float_hours: Optional[float] = None

    constraint: ConstraintType = ConstraintType.NONE
    constraint_date: Optional[datetime] = None
    constraint2: ConstraintType = ConstraintType.NONE
    constraint2_date: Optional[datetime] = None

    pct_complete: float = 0.0                     # 0-100, per pct_type
    physical_pct: float = 0.0
    pct_type: PercentCompleteType = PercentCompleteType.DURATION

    is_critical_flag: Optional[bool] = None       # as stored by the tool
    is_longest_path: Optional[bool] = None
    resources: list[ResourceAssignment] = field(default_factory=list)
    budget_cost: float = 0.0
    actual_cost: float = 0.0
    remaining_cost: float = 0.0
    notes: dict[str, str] = field(default_factory=dict)

    # -- derived helpers -------------------------------------------------
    @property
    def is_milestone(self) -> bool:
        return self.atype in (ActivityType.START_MILESTONE, ActivityType.FINISH_MILESTONE)

    @property
    def is_loe_or_summary(self) -> bool:
        return self.atype in (ActivityType.LOE, ActivityType.WBS_SUMMARY,
                              ActivityType.HAMMOCK, ActivityType.SUMMARY)

    @property
    def completed(self) -> bool:
        return self.status == ActivityStatus.COMPLETED

    @property
    def in_progress(self) -> bool:
        return self.status == ActivityStatus.IN_PROGRESS

    @property
    def not_started(self) -> bool:
        return self.status == ActivityStatus.NOT_STARTED

    @property
    def start(self) -> Optional[datetime]:
        return self.actual_start or self.early_start or self.planned_start

    @property
    def finish(self) -> Optional[datetime]:
        return self.actual_finish or self.early_finish or self.planned_finish

    def duration_days(self, cal: Optional[Calendar]) -> float:
        hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
        return self.original_duration_hours / hpd

    def remaining_days(self, cal: Optional[Calendar]) -> float:
        hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
        return self.remaining_duration_hours / hpd

    def total_float_days(self, cal: Optional[Calendar]) -> Optional[float]:
        if self.total_float_hours is None:
            return None
        hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
        return self.total_float_hours / hpd


@dataclass
class WbsNode:
    uid: str
    parent_uid: Optional[str]
    code: str = ""
    name: str = ""


@dataclass
class ScheduleSettings:
    """Scheduling options captured from the source tool (P6 SCHEDOPTIONS etc.)."""
    retained_logic: Optional[bool] = None         # vs progress override
    progress_override: Optional[bool] = None
    actual_dates: Optional[bool] = None
    relationship_lag_calendar: Optional[str] = None
    critical_float_threshold_hours: Optional[float] = None
    critical_definition: Optional[str] = None     # TotalFloat | LongestPath
    make_open_ends_critical: Optional[bool] = None
    use_expected_finish: Optional[bool] = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class Schedule:
    """One parsed schedule file (one project)."""
    project_id: str = ""
    project_name: str = ""
    data_date: Optional[datetime] = None
    start_date: Optional[datetime] = None          # plan start
    finish_date: Optional[datetime] = None         # current scheduled finish
    must_finish_by: Optional[datetime] = None
    baseline_finish: Optional[datetime] = None     # target/baseline project finish

    activities: dict[str, Activity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    calendars: dict[str, Calendar] = field(default_factory=dict)
    wbs: dict[str, WbsNode] = field(default_factory=dict)
    settings: ScheduleSettings = field(default_factory=ScheduleSettings)

    source_file: str = ""
    source_format: str = ""                        # XER | MSPDI | MPP
    source_sha256: str = ""
    source_tool: str = ""                          # e.g. "P6 Professional 20.12"
    export_user: str = ""
    export_date: Optional[datetime] = None
    parse_warnings: list[str] = field(default_factory=list)

    # -- convenience views -----------------------------------------------
    def cal_for(self, act: Activity) -> Optional[Calendar]:
        if act.calendar_uid and act.calendar_uid in self.calendars:
            return self.calendars[act.calendar_uid]
        for c in self.calendars.values():
            if c.is_default:
                return c
        return None

    @property
    def real_activities(self) -> list[Activity]:
        """Activities that count for quality metrics: tasks + milestones,
        excluding LOE / WBS-summary / hammock / MSP summary rows."""
        return [a for a in self.activities.values() if not a.is_loe_or_summary]

    @property
    def incomplete_activities(self) -> list[Activity]:
        return [a for a in self.real_activities if not a.completed]

    def predecessors_of(self, uid: str) -> list[Relationship]:
        return [r for r in self.relationships if r.succ_uid == uid]

    def successors_of(self, uid: str) -> list[Relationship]:
        return [r for r in self.relationships if r.pred_uid == uid]

    def label(self) -> str:
        dd = self.data_date.strftime("%Y-%m-%d") if self.data_date else "no DD"
        return f"{self.project_id or self.project_name} ({dd})"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
