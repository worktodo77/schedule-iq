"""Version-to-version schedule comparison (the change register).

Activities and relationship endpoints are matched UID-first. Code/name remain
analyst-facing display labels; an unambiguous code fallback is used only for a
legacy export row with no UID. Every category of change a delay expert screens
for at intake is captured, most importantly retroactive changes to previously
reported actual dates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..ingest.model import Activity, Schedule


@dataclass
class FieldChange:
    code: str
    name: str
    field: str
    before: str
    after: str
    flag: str = ""          # extra severity annotation (e.g. RETROACTIVE)
    uid: Optional[str] = None  # stable activity identity; code remains display-only


@dataclass
class RelChange:
    kind: str               # added | deleted | modified
    pred_code: str
    succ_code: str
    detail: str
    pred_uid: Optional[str] = None
    succ_uid: Optional[str] = None


@dataclass
class ChangeSet:
    earlier: Schedule
    later: Schedule
    added: list[Activity] = field(default_factory=list)
    deleted: list[Activity] = field(default_factory=list)
    duration_changes: list[FieldChange] = field(default_factory=list)
    actual_date_changes: list[FieldChange] = field(default_factory=list)     # retroactive
    planned_date_changes: list[FieldChange] = field(default_factory=list)
    constraint_changes: list[FieldChange] = field(default_factory=list)
    calendar_changes: list[FieldChange] = field(default_factory=list)
    status_changes: list[FieldChange] = field(default_factory=list)
    name_changes: list[FieldChange] = field(default_factory=list)
    logic_changes: list[RelChange] = field(default_factory=list)
    float_deltas: dict[str, float] = field(default_factory=dict)             # code -> d days
    critical_before: set[str] = field(default_factory=set)
    critical_after: set[str] = field(default_factory=set)
    calendar_def_changes: list[FieldChange] = field(default_factory=list)    # CAL-04
    wbs_changes: list[FieldChange] = field(default_factory=list)             # STR-03

    @property
    def critical_path_jaccard(self) -> Optional[float]:
        u = self.critical_before | self.critical_after
        if not u:
            return None
        return len(self.critical_before & self.critical_after) / len(u)

    @property
    def logic_churn_pct(self) -> float:
        n_earlier = len(self.earlier.relationships)
        churn = sum(1 for c in self.logic_changes if c.kind in ("added", "deleted"))
        return 100.0 * churn / n_earlier if n_earlier else 0.0

    def summary_counts(self) -> dict[str, int]:
        return {
            "activities added": len(self.added),
            "activities deleted": len(self.deleted),
            "relationships added": sum(1 for c in self.logic_changes if c.kind == "added"),
            "relationships deleted": sum(1 for c in self.logic_changes if c.kind == "deleted"),
            "relationships modified": sum(1 for c in self.logic_changes if c.kind == "modified"),
            "duration changes": len(self.duration_changes),
            "retroactive actual-date changes": len(self.actual_date_changes),
            "planned-date changes": len(self.planned_date_changes),
            "constraint changes": len(self.constraint_changes),
            "calendar changes": len(self.calendar_changes),
            "status changes": len(self.status_changes),
        }


def _d(x: Optional[datetime]) -> str:
    return x.strftime("%Y-%m-%d") if x else "—"


def _activity_identity(act: Activity) -> Optional[str]:
    """Return the persistent identity, or None for a legacy UID-less row."""
    return act.uid or None


def match_activity(schedule: Schedule, source: Activity) -> Optional[Activity]:
    """Resolve source activity in schedule using UID-first identity.

    Code fallback is allowed only when the source row or the candidate legacy
    row has no UID. If both rows carry different UIDs, they are a replacement,
    not a rename.
    """
    if source.uid:
        exact = schedule.activities.get(source.uid)
        if exact is not None:
            return exact
    candidates = [a for a in schedule.activities.values() if a.code == source.code]
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if source.uid and candidate.uid:
        return None
    return candidate


def _match_activity_pairs(earlier: Schedule, later: Schedule):
    """Pair activities UID-first, with an intentionally narrow legacy fallback.

    A pair with two present-but-different UIDs is never matched by code: that
    is the ruled true-replacement case. Code fallback is permitted only when
    at least one side has no UID and the code is unambiguous.
    """
    e_values, l_values = list(earlier.activities.values()), list(later.activities.values())
    e_by_uid: dict[str, Activity] = {}
    l_by_uid: dict[str, Activity] = {}
    e_dupes: set[str] = set()
    l_dupes: set[str] = set()
    for act in e_values:
        uid = _activity_identity(act)
        if uid is None:
            continue
        if uid in e_by_uid:
            e_dupes.add(uid)
        else:
            e_by_uid[uid] = act
    for act in l_values:
        uid = _activity_identity(act)
        if uid is None:
            continue
        if uid in l_by_uid:
            l_dupes.add(uid)
        else:
            l_by_uid[uid] = act
    for uid in e_dupes:
        e_by_uid.pop(uid, None)
    for uid in l_dupes:
        l_by_uid.pop(uid, None)

    pairs: list[tuple[Activity, Activity]] = []
    e_used: set[int] = set()
    l_used: set[int] = set()
    for uid in e_by_uid.keys() & l_by_uid.keys():
        ea, la = e_by_uid[uid], l_by_uid[uid]
        pairs.append((ea, la))
        e_used.add(id(ea))
        l_used.add(id(la))

    e_remaining = [a for a in e_values if id(a) not in e_used]
    l_remaining = [a for a in l_values if id(a) not in l_used]
    e_by_code: dict[str, list[Activity]] = {}
    l_by_code: dict[str, list[Activity]] = {}
    for act in e_remaining:
        e_by_code.setdefault(act.code, []).append(act)
    for act in l_remaining:
        l_by_code.setdefault(act.code, []).append(act)
    for code in e_by_code.keys() & l_by_code.keys():
        ea_list, la_list = e_by_code[code], l_by_code[code]
        if len(ea_list) != 1 or len(la_list) != 1:
            continue
        ea, la = ea_list[0], la_list[0]
        if ea.uid and la.uid:
            continue
        pairs.append((ea, la))
        e_used.add(id(ea))
        l_used.add(id(la))

    return (pairs,
            [a for a in e_values if id(a) not in e_used],
            [a for a in l_values if id(a) not in l_used])


def compare(earlier: Schedule, later: Schedule) -> ChangeSet:
    cs = ChangeSet(earlier=earlier, later=later)
    pairs, deleted, added = _match_activity_pairs(earlier, later)
    cs.deleted = deleted
    cs.added = added

    for ea, la in pairs:
        code = la.code
        uid = _activity_identity(la) or _activity_identity(ea)
        if ea.name != la.name:
            cs.name_changes.append(FieldChange(code, la.name, "name", ea.name, la.name,
                                               uid=uid))
        if abs(ea.original_duration_hours - la.original_duration_hours) > 0.01:
            flag = "IN-PROGRESS" if la.in_progress else ("COMPLETED" if la.completed else "")
            cs.duration_changes.append(FieldChange(
                code, la.name, "original duration",
                f"{ea.original_duration_hours:.0f}h", f"{la.original_duration_hours:.0f}h",
                flag, uid))
        # retroactive actual-date changes: both files report an actual, and it moved
        for fld in ("actual_start", "actual_finish"):
            ev, lv = getattr(ea, fld), getattr(la, fld)
            if ev and lv and ev != lv:
                cs.actual_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), _d(lv), "RETROACTIVE",
                    uid))
            elif ev and not lv:
                cs.actual_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), "removed", "RETROACTIVE",
                    uid))
        for fld in ("planned_start", "planned_finish"):
            ev, lv = getattr(ea, fld), getattr(la, fld)
            if not la.completed and ev and lv and ev != lv:
                cs.planned_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), _d(lv), uid=uid))
        if (ea.constraint, ea.constraint_date) != (la.constraint, la.constraint_date):
            cs.constraint_changes.append(FieldChange(
                code, la.name, "constraint",
                f"{ea.constraint.value} {_d(ea.constraint_date)}",
                f"{la.constraint.value} {_d(la.constraint_date)}", uid=uid))
        ec = earlier.calendars.get(ea.calendar_uid)
        lc = later.calendars.get(la.calendar_uid)
        if (ec.name if ec else ea.calendar_uid) != (lc.name if lc else la.calendar_uid):
            cs.calendar_changes.append(FieldChange(
                code, la.name, "calendar",
                ec.name if ec else str(ea.calendar_uid),
                lc.name if lc else str(la.calendar_uid), uid=uid))
        if ea.status != la.status:
            cs.status_changes.append(FieldChange(
                code, la.name, "status", ea.status.value, la.status.value, uid=uid))
        # WBS re-parenting: compare resolved node code/name, not raw uid
        ewbs = earlier.wbs.get(ea.wbs_uid)
        lwbs = later.wbs.get(la.wbs_uid)
        e_wbs_label = (ewbs.code or ewbs.name) if ewbs else (ea.wbs_uid or "")
        l_wbs_label = (lwbs.code or lwbs.name) if lwbs else (la.wbs_uid or "")
        if e_wbs_label != l_wbs_label:
            cs.wbs_changes.append(FieldChange(
                code, la.name, "wbs", e_wbs_label, l_wbs_label, uid=uid))
        if ea.total_float_hours is not None and la.total_float_hours is not None:
            hpd = 8.0
            cal = later.cal_for(la)
            if cal and cal.hours_per_day:
                hpd = cal.hours_per_day
            cs.float_deltas[code] = (la.total_float_hours - ea.total_float_hours) / hpd

    # Relationships are keyed by persistent endpoint UIDs; codes are retained
    # on RelChange solely as the human-readable display labels.
    def rel_map(s: Schedule):
        m: dict[tuple, list[tuple]] = {}
        for r in s.relationships:
            p, q = s.activities.get(r.pred_uid), s.activities.get(r.succ_uid)
            if p and q:
                pkey = _activity_identity(p) or p.code
                qkey = _activity_identity(q) or q.code
                m.setdefault((pkey, qkey), []).append((r, p, q))
        return m

    em, lm = rel_map(earlier), rel_map(later)
    for key, items in lm.items():
        display_p, display_q = items[0][1].code, items[0][2].code
        if key not in em:
            for r, p, q in items:
                cs.logic_changes.append(RelChange(
                    "added", p.code, q.code,
                    f"{r.rtype.value} lag {r.lag_hours:g}h",
                    _activity_identity(p) or p.code, _activity_identity(q) or q.code))
        else:
            e_sigs = sorted((r.rtype.value, r.lag_hours) for r, _, _ in em[key])
            l_sigs = sorted((r.rtype.value, r.lag_hours) for r, _, _ in items)
            if e_sigs != l_sigs:
                cs.logic_changes.append(RelChange(
                    "modified", display_p, display_q,
                    f"{e_sigs} -> {l_sigs}", key[0], key[1]))
    for key, items in em.items():
        if key not in lm:
            for r, p, q in items:
                cs.logic_changes.append(RelChange(
                    "deleted", p.code, q.code,
                    f"{r.rtype.value} lag {r.lag_hours:g}h",
                    _activity_identity(p) or p.code, _activity_identity(q) or q.code))

    # calendar *definition* changes (CAL-04): calendars present in both,
    # matched by uid first, falling back to name for calendars whose uid
    # was reassigned on re-export.
    e_cals, l_cals = earlier.calendars, later.calendars
    pairs: list[tuple] = []
    matched_e_uids: set[str] = set()
    for uid in set(e_cals) & set(l_cals):
        pairs.append((e_cals[uid], l_cals[uid]))
        matched_e_uids.add(uid)
    e_by_name = {c.name: c for c in e_cals.values() if c.name}
    l_by_name = {c.name: c for c in l_cals.values() if c.name}
    for name in set(e_by_name) & set(l_by_name):
        ec, lc = e_by_name[name], l_by_name[name]
        if ec.uid in matched_e_uids:
            continue
        pairs.append((ec, lc))

    for ec, lc in pairs:
        label = lc.name or lc.uid
        if ec.hours_per_day != lc.hours_per_day:
            cs.calendar_def_changes.append(FieldChange(
                label, label, "hours per day",
                f"{ec.hours_per_day:g}", f"{lc.hours_per_day:g}"))
        if ec.workdays_per_week != lc.workdays_per_week:
            cs.calendar_def_changes.append(FieldChange(
                label, label, "workdays per week",
                str(ec.workdays_per_week), str(lc.workdays_per_week)))
        e_spans = {wd: tuple(p.spans) for wd, p in ec.work_patterns.items()}
        l_spans = {wd: tuple(p.spans) for wd, p in lc.work_patterns.items()}
        if e_spans != l_spans:
            cs.calendar_def_changes.append(FieldChange(
                label, label, "work pattern spans", str(e_spans), str(l_spans)))
        added_hol = lc.exceptions_nonwork - ec.exceptions_nonwork
        removed_hol = ec.exceptions_nonwork - lc.exceptions_nonwork
        if added_hol:
            cs.calendar_def_changes.append(FieldChange(
                label, label, "holidays added", "",
                ", ".join(sorted(d.isoformat() for d in added_hol))))
        if removed_hol:
            cs.calendar_def_changes.append(FieldChange(
                label, label, "holidays removed",
                ", ".join(sorted(d.isoformat() for d in removed_hol)), ""))

    def crit(s: Schedule) -> set[str]:
        return {a.code for a in s.activities.values()
                if not a.is_loe_or_summary and not a.completed
                and a.total_float_hours is not None and a.total_float_hours <= 0}
    cs.critical_before, cs.critical_after = crit(earlier), crit(later)
    return cs
