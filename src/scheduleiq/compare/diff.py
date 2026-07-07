"""Version-to-version schedule comparison (the change register).

Activities are matched on activity code (task_code / MSP ID) — the analyst-
facing identifier that survives export/import — with uid fallback.  Every
category of change a delay expert screens for at intake is captured, most
importantly retroactive changes to previously reported actual dates.
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


@dataclass
class RelChange:
    kind: str               # added | deleted | modified
    pred_code: str
    succ_code: str
    detail: str


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


def compare(earlier: Schedule, later: Schedule) -> ChangeSet:
    cs = ChangeSet(earlier=earlier, later=later)
    e_by_code = {a.code: a for a in earlier.activities.values()}
    l_by_code = {a.code: a for a in later.activities.values()}

    cs.added = [a for c, a in l_by_code.items() if c not in e_by_code]
    cs.deleted = [a for c, a in e_by_code.items() if c not in l_by_code]

    for code, ea in e_by_code.items():
        la = l_by_code.get(code)
        if la is None:
            continue
        if ea.name != la.name:
            cs.name_changes.append(FieldChange(code, la.name, "name", ea.name, la.name))
        if abs(ea.original_duration_hours - la.original_duration_hours) > 0.01:
            flag = "IN-PROGRESS" if la.in_progress else ("COMPLETED" if la.completed else "")
            cs.duration_changes.append(FieldChange(
                code, la.name, "original duration",
                f"{ea.original_duration_hours:.0f}h", f"{la.original_duration_hours:.0f}h",
                flag))
        # retroactive actual-date changes: both files report an actual, and it moved
        for fld in ("actual_start", "actual_finish"):
            ev, lv = getattr(ea, fld), getattr(la, fld)
            if ev and lv and ev != lv:
                cs.actual_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), _d(lv), "RETROACTIVE"))
            elif ev and not lv:
                cs.actual_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), "removed", "RETROACTIVE"))
        for fld in ("planned_start", "planned_finish"):
            ev, lv = getattr(ea, fld), getattr(la, fld)
            if not la.completed and ev and lv and ev != lv:
                cs.planned_date_changes.append(FieldChange(
                    code, la.name, fld.replace("_", " "), _d(ev), _d(lv)))
        if (ea.constraint, ea.constraint_date) != (la.constraint, la.constraint_date):
            cs.constraint_changes.append(FieldChange(
                code, la.name, "constraint",
                f"{ea.constraint.value} {_d(ea.constraint_date)}",
                f"{la.constraint.value} {_d(la.constraint_date)}"))
        ec = earlier.calendars.get(ea.calendar_uid)
        lc = later.calendars.get(la.calendar_uid)
        if (ec.name if ec else ea.calendar_uid) != (lc.name if lc else la.calendar_uid):
            cs.calendar_changes.append(FieldChange(
                code, la.name, "calendar",
                ec.name if ec else str(ea.calendar_uid),
                lc.name if lc else str(la.calendar_uid)))
        if ea.status != la.status:
            cs.status_changes.append(FieldChange(
                code, la.name, "status", ea.status.value, la.status.value))
        # WBS re-parenting: compare resolved node code/name, not raw uid
        ewbs = earlier.wbs.get(ea.wbs_uid)
        lwbs = later.wbs.get(la.wbs_uid)
        e_wbs_label = (ewbs.code or ewbs.name) if ewbs else (ea.wbs_uid or "")
        l_wbs_label = (lwbs.code or lwbs.name) if lwbs else (la.wbs_uid or "")
        if e_wbs_label != l_wbs_label:
            cs.wbs_changes.append(FieldChange(
                code, la.name, "wbs", e_wbs_label, l_wbs_label))
        if ea.total_float_hours is not None and la.total_float_hours is not None:
            hpd = 8.0
            cal = later.cal_for(la)
            if cal and cal.hours_per_day:
                hpd = cal.hours_per_day
            cs.float_deltas[code] = (la.total_float_hours - ea.total_float_hours) / hpd

    # relationships keyed by (pred code, succ code); track type/lag changes
    def rel_map(s: Schedule):
        by_uid = s.activities
        m: dict[tuple, list] = {}
        for r in s.relationships:
            p, q = by_uid.get(r.pred_uid), by_uid.get(r.succ_uid)
            if p and q:
                m.setdefault((p.code, q.code), []).append(r)
        return m

    em, lm = rel_map(earlier), rel_map(later)
    for key, rels in lm.items():
        if key not in em:
            for r in rels:
                cs.logic_changes.append(RelChange("added", key[0], key[1],
                                                  f"{r.rtype.value} lag {r.lag_hours:g}h"))
        else:
            e_sigs = sorted((r.rtype.value, r.lag_hours) for r in em[key])
            l_sigs = sorted((r.rtype.value, r.lag_hours) for r in rels)
            if e_sigs != l_sigs:
                cs.logic_changes.append(RelChange(
                    "modified", key[0], key[1],
                    f"{e_sigs} -> {l_sigs}"))
    for key, rels in em.items():
        if key not in lm:
            for r in rels:
                cs.logic_changes.append(RelChange("deleted", key[0], key[1],
                                                  f"{r.rtype.value} lag {r.lag_hours:g}h"))

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
