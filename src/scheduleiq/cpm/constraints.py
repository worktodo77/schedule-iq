"""
Date-constraint scheduling and statusing-mode taxonomy for the ScheduleIQ CPM
engine (closes LIM-028; adds the Progress Override statusing mode).

Two capabilities live here:

  1. Date constraints (LIM-028, closed in this port).
     ``SchedulingConstraint`` records one P6-style date constraint on an
     activity. ``ConstraintType`` enumerates the P6 constraint vocabulary with
     the standard P6 mnemonics (SNET/SNLT/FNET/FNLT/SO/FO/MS/MF/ALAP/XF). The
     engine applies these during the forward and backward passes at DAY
     granularity, and emits a ``ConstraintApplication`` disclosure record per
     constraint describing exactly what it did (including any non-workday snap
     and any violation of predecessor logic).

  2. ``StatusingMode`` — RETAINED_LOGIC (default) vs PROGRESS_OVERRIDE. The
     engine's pinning mechanism already implements Retained Logic (ADR-002);
     PROGRESS_OVERRIDE is net-new here.

P6 fidelity (ADR-006 house rule): this is a *P6-compatible analytical
convention* at day granularity, NOT exact P6 emulation. Real P6 schedules at
hour granularity and its constraint interactions (especially ALAP float
consumption and hard-constraint negative float) are approximated here. Every
approximation is disclosed in the ``ConstraintApplication.effect`` text and in
the engine's constraint log / warnings.

The helper functions ``apply_forward_constraint`` and
``apply_backward_constraint`` are the single source of truth for the day-level
constraint arithmetic; the engine calls them from inside its passes so that
constraint math stays folded into the existing ES/EF and LS/LF mechanisms.

Sources:
  P6 scheduling reference behavior (documented approximation).
  CPW-P6 Manual pp. 8-12 (constraint detection as a normalization check).
  AACE 49R-06 §2 (constraints as a cause of float distortion / CP misID).
  ADR-002 (Retained Logic); ADR-006 (P6-compatible analytical convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Optional

from .calendar_ops import nearest_workday_index as _wd_index
from .lag_analysis import apply_lag
from .models import Calendar


# ---------------------------------------------------------------------------
# Constraint taxonomy
# ---------------------------------------------------------------------------

class ConstraintType(Enum):
    """
    P6 date-constraint vocabulary (with the standard P6 mnemonic in comments).

    Early-side (forward-pass) semantics push dates LATER (a floor); late-side
    (backward-pass) semantics pull dates EARLIER (a ceiling). Hard constraints
    (MANDATORY_*) pin both passes and can create negative float.
    """
    START_ON_OR_AFTER = "start_on_or_after"     # SNET — Start No Earlier Than
    START_ON_OR_BEFORE = "start_on_or_before"   # SNLT — Start No Later Than
    FINISH_ON_OR_AFTER = "finish_on_or_after"   # FNET — Finish No Earlier Than
    FINISH_ON_OR_BEFORE = "finish_on_or_before"  # FNLT — Finish No Later Than
    START_ON = "start_on"                       # SO   — Start On (SNET + SNLT)
    FINISH_ON = "finish_on"                     # FO   — Finish On (FNET + FNLT)
    MANDATORY_START = "mandatory_start"         # MS   — hard; pins both passes
    MANDATORY_FINISH = "mandatory_finish"       # MF   — hard; pins both passes
    AS_LATE_AS_POSSIBLE = "as_late_as_possible"  # ALAP — consumes free float
    EXPECTED_FINISH = "expected_finish"         # XF   — recalc remaining duration


# P6 mnemonic labels for disclosure text.
_MNEMONIC: dict[ConstraintType, str] = {
    ConstraintType.START_ON_OR_AFTER: "SNET",
    ConstraintType.START_ON_OR_BEFORE: "SNLT",
    ConstraintType.FINISH_ON_OR_AFTER: "FNET",
    ConstraintType.FINISH_ON_OR_BEFORE: "FNLT",
    ConstraintType.START_ON: "SO",
    ConstraintType.FINISH_ON: "FO",
    ConstraintType.MANDATORY_START: "MS",
    ConstraintType.MANDATORY_FINISH: "MF",
    ConstraintType.AS_LATE_AS_POSSIBLE: "ALAP",
    ConstraintType.EXPECTED_FINISH: "XF",
}

# Constraint types that anchor on a START date (snap non-workday cdate FORWARD).
_START_ANCHORED: frozenset = frozenset({
    ConstraintType.START_ON_OR_AFTER,
    ConstraintType.START_ON_OR_BEFORE,
    ConstraintType.START_ON,
    ConstraintType.MANDATORY_START,
})

# Constraint types that anchor on a FINISH date (snap non-workday cdate BACK).
_FINISH_ANCHORED: frozenset = frozenset({
    ConstraintType.FINISH_ON_OR_AFTER,
    ConstraintType.FINISH_ON_OR_BEFORE,
    ConstraintType.FINISH_ON,
    ConstraintType.MANDATORY_FINISH,
    ConstraintType.EXPECTED_FINISH,
})


def mnemonic(ct: ConstraintType) -> str:
    """Return the P6 mnemonic (e.g. 'SNET') for a constraint type."""
    return _MNEMONIC[ct]


def constraint_is_start_anchored(ct: ConstraintType) -> bool:
    """
    Return True if a non-workday constraint date should snap FORWARD (to the
    next workday, start-type) or False if it should snap BACKWARD (to the
    previous workday, finish-type). ALAP has no date and returns True (unused).
    """
    return ct not in _FINISH_ANCHORED


# ---------------------------------------------------------------------------
# Statusing mode
# ---------------------------------------------------------------------------

class StatusingMode(Enum):
    """
    CPM statusing mode governing how out-of-sequence (OOS) progress is handled.

    RETAINED_LOGIC (default):
        An unstarted successor of an incomplete predecessor waits for the
        predecessor's remaining work (logic retained). This is the engine's
        existing pinning behavior (ADR-002); the default path is unchanged.

    PROGRESS_OVERRIDE:
        When a predecessor has STARTED but is INCOMPLETE (in-progress: it has an
        actual start / ``pinned_early_start`` but no actual finish), its
        retained-logic tie to the successor's remaining work is DROPPED — the
        successor may proceed at the data date as if the incomplete predecessor
        did not restrain it. Relationships from unstarted or completed
        predecessors behave normally.

    P6 scheduling reference behavior (documented approximation): this is a
    P6-compatible analytical convention at day granularity, not exact P6
    emulation.
    """
    RETAINED_LOGIC = "retained_logic"
    PROGRESS_OVERRIDE = "progress_override"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class SchedulingConstraint:
    """
    One P6-style date constraint on an activity.

    Fields:
        act_id: Activity the constraint applies to.
        ctype:  ConstraintType.
        cdate:  The constraint date. May be None only for AS_LATE_AS_POSSIBLE
                (ALAP has no associated date).
    """
    act_id: str
    ctype: ConstraintType
    cdate: Optional[date] = None

    def __post_init__(self) -> None:
        if self.cdate is None and self.ctype is not ConstraintType.AS_LATE_AS_POSSIBLE:
            raise ValueError(
                f"SchedulingConstraint for {self.act_id!r}: cdate=None is only "
                f"permitted for AS_LATE_AS_POSSIBLE (ALAP); got {self.ctype.name}."
            )


@dataclass
class ConstraintApplication:
    """
    Disclosure record describing what one constraint did during scheduling.

    Fields:
        act_id:         Activity ID.
        ctype:          ConstraintType applied.
        cdate:          The (workday-snapped) constraint date used, or None (ALAP).
        effect:         Human-readable description of the forward/backward effect,
                        including any non-workday snap and negative-float note.
        violated:       True when the constraint conflicts with predecessor logic
                        (MANDATORY_* logic date later than cdate, or XF cdate
                        earlier than the computed ES).
        violation_days: Workday magnitude of the violation, or None.
    """
    act_id: str
    ctype: ConstraintType
    cdate: Optional[date]
    effect: str
    violated: bool = False
    violation_days: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for audit output."""
        return {
            "act_id": self.act_id,
            "ctype": self.ctype.value,
            "mnemonic": _MNEMONIC[self.ctype],
            "cdate": self.cdate.isoformat() if self.cdate is not None else None,
            "effect": self.effect,
            "violated": self.violated,
            "violation_days": self.violation_days,
        }


# ---------------------------------------------------------------------------
# Forward-pass constraint arithmetic
# ---------------------------------------------------------------------------

def apply_forward_constraint(
    con: SchedulingConstraint,
    es: date,
    ef: date,
    logic_es: date,
    logic_ef: date,
    span: int,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> Optional[tuple[date, date, str, bool, Optional[int]]]:
    """
    Apply ONE constraint's forward-pass (early-date) effect.

    ``es``/``ef`` are the current (possibly already constraint-adjusted) early
    dates; ``logic_es``/``logic_ef`` are the unconstrained predecessor-driven
    dates (used to measure violations). ``span = max(0, OD - 1)``.

    Returns ``(new_es, new_ef, effect, violated, violation_days)`` when the
    constraint has a forward-pass effect, or ``None`` for constraint types that
    only act on the backward pass (SNLT, FNLT) or post-pass (ALAP).

    P6 semantics at day granularity (documented approximation):
      * SNET / START_ON early side: ES = max(logic ES, cdate).
      * FNET / FINISH_ON early side: EF = max(logic EF, cdate); ES retreats by
        span (folded into the ef-constraint mechanism).
      * MANDATORY_START: ES := cdate unconditionally; EF = ES + span. Violated
        when logic ES is later than cdate.
      * MANDATORY_FINISH: EF := cdate unconditionally; ES = EF - span. Violated
        when logic EF is later than cdate.
      * EXPECTED_FINISH: EF := cdate when cdate >= ES (remaining duration
        recalculated); when cdate < ES, violated and EF := ES (zero remaining).
    """
    ct = con.ctype
    cdate = con.cdate
    label = _MNEMONIC[ct]

    if ct in (ConstraintType.START_ON_OR_AFTER, ConstraintType.START_ON):
        # SNET (and early side of SO): ES = max(logic ES, cdate).
        new_es = max(es, cdate)  # dates compare chronologically == workday order
        if new_es != es:
            new_ef = apply_lag(new_es, span, workday_table, calendar, anchor_is_start=True)
            eff = f"{label}: ES {es.isoformat()} -> {new_es.isoformat()} (start no earlier than {cdate.isoformat()})"
            return new_es, new_ef, eff, False, None
        eff = f"{label}: no forward effect (logic ES {es.isoformat()} already >= {cdate.isoformat()})"
        return es, ef, eff, False, None

    if ct in (ConstraintType.FINISH_ON_OR_AFTER, ConstraintType.FINISH_ON):
        # FNET (and early side of FO): EF = max(logic EF, cdate); ES retreats.
        target_ef = max(ef, cdate)
        if target_ef != ef:
            es_from_ef = apply_lag(target_ef, -span, workday_table, calendar, anchor_is_start=False)
            new_es = max(es, es_from_ef)
            new_ef = apply_lag(new_es, span, workday_table, calendar, anchor_is_start=True)
            eff = f"{label}: EF {ef.isoformat()} -> {new_ef.isoformat()} (finish no earlier than {cdate.isoformat()}); ES {es.isoformat()} -> {new_es.isoformat()}"
            return new_es, new_ef, eff, False, None
        eff = f"{label}: no forward effect (logic EF {ef.isoformat()} already >= {cdate.isoformat()})"
        return es, ef, eff, False, None

    if ct is ConstraintType.MANDATORY_START:
        # Hard: ES := cdate unconditionally (overrides logic in both directions).
        new_es = cdate
        new_ef = apply_lag(new_es, span, workday_table, calendar, anchor_is_start=True)
        violated = _wd_index(workday_table, logic_es) > _wd_index(workday_table, cdate)
        vdays = (
            _wd_index(workday_table, logic_es) - _wd_index(workday_table, cdate)
            if violated else None
        )
        eff = f"{label}: ES := {cdate.isoformat()} (hard, overrides logic); EF := {new_ef.isoformat()}"
        if violated:
            eff += f"; VIOLATION: logic ES {logic_es.isoformat()} is {vdays} workday(s) later (may create negative float)"
        return new_es, new_ef, eff, violated, vdays

    if ct is ConstraintType.MANDATORY_FINISH:
        # Hard: EF := cdate unconditionally; ES = EF - span.
        new_ef = cdate
        new_es = apply_lag(new_ef, -span, workday_table, calendar, anchor_is_start=False)
        violated = _wd_index(workday_table, logic_ef) > _wd_index(workday_table, cdate)
        vdays = (
            _wd_index(workday_table, logic_ef) - _wd_index(workday_table, cdate)
            if violated else None
        )
        eff = f"{label}: EF := {cdate.isoformat()} (hard, overrides logic); ES := {new_es.isoformat()}"
        if violated:
            eff += f"; VIOLATION: logic EF {logic_ef.isoformat()} is {vdays} workday(s) later (may create negative float)"
        return new_es, new_ef, eff, violated, vdays

    if ct is ConstraintType.EXPECTED_FINISH:
        # XF: P6 recalcs remaining duration so the activity finishes on cdate.
        cd_wd = _wd_index(workday_table, cdate)
        es_wd = _wd_index(workday_table, es)
        if cd_wd >= es_wd:
            new_ef = cdate
            eff = (
                f"{label}: EF := {cdate.isoformat()} (remaining duration recalculated; "
                f"effective span {cd_wd - es_wd} workday(s))"
            )
            return es, new_ef, eff, False, None
        vdays = es_wd - cd_wd
        eff = (
            f"{label}: cdate {cdate.isoformat()} precedes ES {es.isoformat()}; "
            f"VIOLATION: EF held at ES (zero remaining), {vdays} workday(s) short"
        )
        return es, es, eff, True, vdays

    # SNLT, FNLT: no forward-pass effect. ALAP: handled post-backward-pass.
    return None


# ---------------------------------------------------------------------------
# Backward-pass constraint arithmetic
# ---------------------------------------------------------------------------

def apply_backward_constraint(
    con: SchedulingConstraint,
    ls: date,
    lf: date,
    span: int,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> Optional[tuple[date, date, str]]:
    """
    Apply ONE constraint's backward-pass (late-date) effect.

    ``ls``/``lf`` are the current (logic-driven) late dates. Returns
    ``(new_ls, new_lf, effect)`` when the constraint has a backward-pass effect,
    or ``None`` for constraint types that only act on the forward pass
    (SNET, FNET, XF) or post-pass (ALAP).

    P6 semantics at day granularity (documented approximation):
      * SNLT / START_ON late side: LS = min(logic LS, cdate); LF follows.
      * FNLT / FINISH_ON late side: LF = min(logic LF, cdate); LS follows.
      * MANDATORY_START: LS := cdate; LF = LS + span (hard, pins both passes).
      * MANDATORY_FINISH: LF := cdate; LS = LF - span (hard, pins both passes).
    """
    ct = con.ctype
    cdate = con.cdate
    label = _MNEMONIC[ct]

    if ct in (ConstraintType.START_ON_OR_BEFORE, ConstraintType.START_ON):
        # SNLT (and late side of SO): LS = min(logic LS, cdate).
        new_ls = min(ls, cdate)
        if new_ls != ls:
            new_lf = apply_lag(new_ls, span, workday_table, calendar, anchor_is_start=True)
            eff = f"{label} (late): LS {ls.isoformat()} -> {new_ls.isoformat()} (start no later than {cdate.isoformat()})"
            return new_ls, new_lf, eff
        eff = f"{label} (late): no late effect (logic LS {ls.isoformat()} already <= {cdate.isoformat()})"
        return ls, lf, eff

    if ct in (ConstraintType.FINISH_ON_OR_BEFORE, ConstraintType.FINISH_ON):
        # FNLT (and late side of FO): LF = min(logic LF, cdate).
        new_lf = min(lf, cdate)
        if new_lf != lf:
            new_ls = apply_lag(new_lf, -span, workday_table, calendar, anchor_is_start=False)
            eff = f"{label} (late): LF {lf.isoformat()} -> {new_lf.isoformat()} (finish no later than {cdate.isoformat()})"
            return new_ls, new_lf, eff
        eff = f"{label} (late): no late effect (logic LF {lf.isoformat()} already <= {cdate.isoformat()})"
        return ls, lf, eff

    if ct is ConstraintType.MANDATORY_START:
        new_ls = cdate
        new_lf = apply_lag(new_ls, span, workday_table, calendar, anchor_is_start=True)
        eff = f"{label} (late): LS := {cdate.isoformat()} (hard, pins backward pass); LF := {new_lf.isoformat()}"
        return new_ls, new_lf, eff

    if ct is ConstraintType.MANDATORY_FINISH:
        new_lf = cdate
        new_ls = apply_lag(new_lf, -span, workday_table, calendar, anchor_is_start=False)
        eff = f"{label} (late): LF := {cdate.isoformat()} (hard, pins backward pass); LS := {new_ls.isoformat()}"
        return new_ls, new_lf, eff

    # SNET, FNET, XF: no backward-pass effect. ALAP: handled post-backward-pass.
    return None
