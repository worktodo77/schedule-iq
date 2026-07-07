"""Ribbon Analyzer — group-by-field/WBS metric rollup (Fuse parity backlog F1;
docs/FUSE_PARITY.md "Ribbon Analyzer (group-by field/WBS)").

Fuse purpose
------------
The Ribbon view answers "which part of the job carries the quality
problems?" by regrouping the existing per-activity offender lists a
``ScheduleAssessment`` already carries (``metrics.engine.Finding.object_id``)
against the WBS tree (or an analyst-supplied custom grouping), instead of
recomputing anything.  Per docs/FUSE_PARITY.md's note, "the engine keeps
offender lists with WBS ids, so per-WBS ribbons are a straightforward
aggregation" — this module is exactly that aggregation, nothing more.

Grouping
--------
``group_by="wbs"`` (default): each activity is assigned to the WBS node at
``level`` in its ancestor chain, counted from the WBS root(s) — level 1 is
the root of the chain (``WbsNode`` with ``parent_uid`` absent from
``sched.wbs``), level 2 its child, and so on (``ingest.model.WbsNode``,
walked via ``parent_uid``).  When an activity's chain is shorter than
``level`` (its leaf sits above that depth) it is grouped at the deepest node
actually available and the row count is disclosed in ``clamped_activities``
— it is never silently dropped.  Activities with no ``wbs_uid``, or whose
``wbs_uid`` is absent from ``sched.wbs``, fall into the synthetic
``"(unassigned)"`` group (also disclosed, never hidden).

``groups=<dict>``: a custom activity-code -> group-label map, e.g. for a
non-WBS field (area, contractor, phase code carried in ``Activity.notes``,
...).  When supplied it overrides ``group_by``/``level`` entirely; activity
codes absent from the map fall into ``"(unassigned)"`` exactly as above.

Finding resolution (which checks can be ribboned)
--------------------------------------------------
A ``Finding.object_id`` resolves to a group only when it equals a real
activity's ``code`` in this schedule — the convention every single-activity
check in ``metrics.checks.core`` already follows (``Finding(a.code, ...)``,
see ``core._fx``).  Relationship checks (DCMA-02/-03/-04, LOG-03/-04/-07/-
08/-09, REL-01) key their findings on a composite ``"pred -> succ"`` string
and calendar/file-level checks (CAL-*, CP-01, STR-01/-02, DAT-04, DCMA-13)
key on calendar names, counts, or nothing at all — none of those match an
activity code, so they never localize to one WBS branch.  A check is
excluded from the ribbon (and named in ``excluded_checks`` with a reason)
when it has at least one finding globally but NONE of them resolve to an
activity code; a check with zero findings anywhere is harmlessly carried at
0 offenders in every group.  Series-level checks (``applies_to == "series"``)
are excluded outright — there is nothing to regroup before a series exists.

Health score (per group)
-------------------------
Reuses ``ScheduleAssessment.health_score``'s weighting philosophy (critical
checks weigh 2x warnings) but adapted to a group's small population: instead
of the whole-schedule PASS/WARNING/FAIL tri-state (calibrated against a
global threshold, noisy at WBS-branch scale), each *eligible* check —
ribbon-mappable AND carrying >= 1 finding somewhere in the assessment, i.e.
"live" — contributes ``weight * (1 - offender_share)`` to the numerator and
``weight`` to the denominator, where ``offender_share`` is this group's
offender count for that check divided by this group's real-activity count
(clipped to 1.0).  ``score = 100 * num / den`` (100.0 when no check is
eligible).  This is a triage aid, not an opinion on any WBS branch's
adequacy — the same caveat ``health_score`` itself carries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..ingest.model import Schedule, WbsNode
from ..metrics.engine import ScheduleAssessment

UNASSIGNED = "(unassigned)"
TOP_N_WORST_CHECKS = 5

LABEL = ("PRELIMINARY — Ribbon Analyzer regroups the assessment's existing "
        "offender findings by WBS branch (or a custom grouping); a group's "
        "score is a triage aid pointing at where quality problems "
        "concentrate, not an opinion on that branch's adequacy.")

SCORE_FORMULA = (
    "group score = 100 * sum(weight_c * (1 - min(1, offenders_c / activities))) "
    "/ sum(weight_c), over checks c that are ribbon-mappable and have >= 1 "
    "finding anywhere in the assessment; weight_c = 2.0 if check.severity == "
    "'critical' else 1.0 (mirrors ScheduleAssessment.health_score)."
)


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class RibbonRow:
    group: str
    group_name: str
    activity_count: int
    check_offenders: dict[str, int] = field(default_factory=dict)
    category_density: dict[str, float] = field(default_factory=dict)
    worst_checks: list[tuple[str, int]] = field(default_factory=list)
    score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "group_name": self.group_name,
            "activity_count": self.activity_count,
            "check_offenders": dict(sorted(self.check_offenders.items())),
            "category_density": {k: round(v, 4)
                                 for k, v in sorted(self.category_density.items())},
            "worst_checks": [[cid, n] for cid, n in self.worst_checks],
            "score": self.score,
        }


@dataclass
class RibbonAnalysis:
    group_by: str = "wbs"
    level: int = 1
    rows: list[RibbonRow] = field(default_factory=list)
    excluded_checks: list[str] = field(default_factory=list)
    excluded_reason: dict[str, str] = field(default_factory=dict)
    unassigned_activities: int = 0
    clamped_activities: int = 0
    formula: str = SCORE_FORMULA
    reason: str = ""
    label: str = LABEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_by": self.group_by,
            "level": self.level,
            "rows": [r.to_dict() for r in self.rows],
            "excluded_checks": list(self.excluded_checks),
            "excluded_reason": dict(sorted(self.excluded_reason.items())),
            "unassigned_activities": self.unassigned_activities,
            "clamped_activities": self.clamped_activities,
            "formula": self.formula,
            "reason": self.reason,
            "label": self.label,
        }


# --------------------------------------------------------------------------
# WBS ancestor-chain grouping
# --------------------------------------------------------------------------
def _ancestor_chain(node_uid: str, wbs: dict[str, WbsNode]) -> list[WbsNode]:
    """Root -> ... -> leaf chain for ``node_uid``; defensively cycle-guarded."""
    chain: list[WbsNode] = []
    seen: set[str] = set()
    cur = wbs.get(node_uid)
    while cur is not None and cur.uid not in seen:
        chain.append(cur)
        seen.add(cur.uid)
        cur = wbs.get(cur.parent_uid) if cur.parent_uid else None
    chain.reverse()
    return chain


def _wbs_group(sched: Schedule, level: int, chains: dict[str, list[WbsNode]],
              a) -> tuple[Optional[str], Optional[str], bool]:
    if not a.wbs_uid or a.wbs_uid not in sched.wbs:
        return None, None, False
    chain = chains.setdefault(a.wbs_uid, _ancestor_chain(a.wbs_uid, sched.wbs))
    if not chain:
        return None, None, False
    idx = level - 1
    clamped = idx >= len(chain)
    node = chain[-1] if clamped else chain[idx]
    return (node.code or node.uid), (node.name or node.code or node.uid), clamped


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def ribbon_analysis(sched: Schedule, assessment: ScheduleAssessment, *,
                    group_by: str = "wbs", level: int = 1,
                    groups: Optional[dict[str, str]] = None) -> RibbonAnalysis:
    ra = RibbonAnalysis(group_by=("custom" if groups is not None else group_by),
                        level=level)
    pop = sched.real_activities
    if not pop:
        ra.reason = "no real activities to group"
        return ra
    if groups is None and group_by != "wbs":
        ra.reason = f"unsupported group_by {group_by!r}; use 'wbs' or pass groups="
        return ra

    code_to_act = {a.code: a for a in sched.activities.values()}

    # -- assign every real activity to a group -----------------------------
    chains: dict[str, list[WbsNode]] = {}
    activity_group: dict[str, str] = {}          # code -> group key
    group_names: dict[str, str] = {}
    group_activities: dict[str, set[str]] = {}
    unassigned = clamped_n = 0

    def _bucket(key: str, name: str, code: str) -> None:
        group_names.setdefault(key, name)
        group_activities.setdefault(key, set()).add(code)

    for a in pop:
        if groups is not None:
            key = groups.get(a.code)
            if key is None:
                unassigned += 1
                _bucket(UNASSIGNED, UNASSIGNED, a.code)
                activity_group[a.code] = UNASSIGNED
            else:
                _bucket(key, key, a.code)
                activity_group[a.code] = key
        else:
            key, name, clamped = _wbs_group(sched, level, chains, a)
            if key is None:
                unassigned += 1
                _bucket(UNASSIGNED, UNASSIGNED, a.code)
                activity_group[a.code] = UNASSIGNED
            else:
                if clamped:
                    clamped_n += 1
                _bucket(key, name, a.code)
                activity_group[a.code] = key

    ra.unassigned_activities = unassigned
    ra.clamped_activities = clamped_n

    # -- regroup findings ----------------------------------------------------
    check_defs = {}
    # group -> check_id -> set(activity codes)
    offenders: dict[str, dict[str, set[str]]] = {g: {} for g in group_activities}
    global_resolved: dict[str, set[str]] = {}      # check_id -> activity codes resolved anywhere
    any_finding: dict[str, bool] = {}              # check_id -> had >=1 finding at all

    for mr in assessment.results:
        cd = mr.check
        if cd.applies_to == "series":
            continue
        check_defs[cd.id] = cd
        if mr.findings:
            any_finding[cd.id] = True
        for f in mr.findings:
            if f.object_id not in code_to_act:
                continue
            code = f.object_id
            if code not in activity_group:
                continue          # e.g. an LOE/summary activity finding — not groupable
            g = activity_group[code]
            offenders[g].setdefault(cd.id, set()).add(code)
            global_resolved.setdefault(cd.id, set()).add(code)

    included_checks = {cid: cd for cid, cd in check_defs.items()
                       if cid in global_resolved or cid not in any_finding}
    for cid, cd in check_defs.items():
        if cid not in included_checks:
            ra.excluded_checks.append(cid)
            ra.excluded_reason[cid] = ("findings do not resolve to individual "
                                       "activity codes (file-level or "
                                       "relationship-keyed check)")
    ra.excluded_checks.sort()

    eligible = sorted(cid for cid in included_checks if cid in global_resolved)

    # -- build rows ------------------------------------------------------
    rows = []
    for g, codes in group_activities.items():
        activity_count = len(codes)
        check_offenders: dict[str, int] = {}
        category_totals: dict[str, int] = {}
        for cid, cd in included_checks.items():
            n = len(offenders[g].get(cid, ()))
            check_offenders[cid] = n
            category_totals[cd.category] = category_totals.get(cd.category, 0) + n
        category_density = {cat: (n / activity_count if activity_count else 0.0)
                            for cat, n in category_totals.items()}
        worst = sorted(((cid, n) for cid, n in check_offenders.items() if n > 0),
                       key=lambda t: (-t[1], t[0]))[:TOP_N_WORST_CHECKS]

        num = den = 0.0
        for cid in eligible:
            cd = included_checks[cid]
            w = 2.0 if cd.severity == "critical" else 1.0
            den += w
            share = (check_offenders.get(cid, 0) / activity_count) if activity_count else 0.0
            num += w * (1.0 - min(1.0, share))
        score = round(100.0 * num / den, 1) if den else 100.0

        rows.append(RibbonRow(
            group=g, group_name=group_names[g], activity_count=activity_count,
            check_offenders=check_offenders, category_density=category_density,
            worst_checks=worst, score=score))

    rows.sort(key=lambda r: (r.score, r.group))
    ra.rows = rows
    return ra
