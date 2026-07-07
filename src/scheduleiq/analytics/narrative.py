"""S4 — narrative reconciliation vs the XER record (ANALYTICS_PROPOSAL.md §6.8).

Cross-checks claims made in project narratives (monthly reports, letters,
minutes — already mined by expert-assist's contradiction-finder) against
what the update series actually recorded.  Each claim is matched to the
nearest update by data date; project-level claims (no activity) are checked
against the project forecast finish, activity-level claims against recorded
percent complete and forecast/actual finish.  Every claim is ALSO checked
against later updates for a retroactive rewrite: if the value the claim
matched at the time was subsequently changed on an actual date (the TRD-05
signal, from ``ChangeSet.actual_date_changes``), the row is classified
RECORD-REWRITTEN rather than CONSISTENT, because the record the claim relied
on no longer exists as reported.

Every discrepancy is exactly that — a discrepancy calling for explanation,
not a finding of impropriety (CLAUDE.md rule 2/4); the caption on every
output says so explicitly.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..intake._util import working_days_between

CAPTION = ("narrative reconciliation — each discrepancy is a matter for "
          "explanation, not, without more, evidence of impropriety.")

MAX_MATCH_DAYS = 45
PCT_GAP_THRESHOLD = 10.0
FINISH_WD_THRESHOLD = 5.0
PROJECT_FINISH_DAY_THRESHOLD = 5


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class NarrativeClaim:
    period_end: datetime
    source_doc: str = ""
    activity_code: Optional[str] = None
    claimed_pct: Optional[float] = None
    claimed_finish: Optional[datetime] = None
    claimed_status: str = ""
    quote: str = ""


@dataclass
class ReconciliationRow:
    claim: NarrativeClaim
    matched_update: str = ""
    recorded_value: str = ""
    delta: str = ""
    classification: str = "UNMATCHED"    # CONSISTENT | DISCREPANT | RECORD-REWRITTEN | UNMATCHED
    reason: str = ""


@dataclass
class ReconciliationResult:
    rows: list = field(default_factory=list)     # list[ReconciliationRow]
    summary: dict = field(default_factory=dict)
    caption: str = CAPTION
    reason: str = ""


# --------------------------------------------------------------------------
# loader
# --------------------------------------------------------------------------
def _parse_date(s: Optional[str]) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_float(s: Optional[str]) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_claims_csv(path: str) -> list:
    """Parse the narrative-claims CSV, tolerant of every optional column
    (activity_code, claimed_pct, claimed_finish, claimed_status, quote)
    being blank.  Rows with an unparseable period_end are skipped rather
    than raising."""
    claims: list = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            period_end = _parse_date(row.get("period_end"))
            if period_end is None:
                continue
            claims.append(NarrativeClaim(
                period_end=period_end,
                source_doc=(row.get("source_doc") or "").strip(),
                activity_code=(row.get("activity_code") or "").strip() or None,
                claimed_pct=_parse_float(row.get("claimed_pct")),
                claimed_finish=_parse_date(row.get("claimed_finish")),
                claimed_status=(row.get("claimed_status") or "").strip(),
                quote=(row.get("quote") or "").strip(),
            ))
    return claims


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def _nearest_update_idx(scheds, period_end: datetime,
                        max_days: int = MAX_MATCH_DAYS) -> Optional[int]:
    best_idx, best_diff = None, None
    for i, s in enumerate(scheds):
        if not s.data_date:
            continue
        diff = abs((s.data_date.date() - period_end.date()).days)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = i, diff
    if best_idx is None or best_diff > max_days:
        return None
    return best_idx


def _reconcile_one(scheds, changesets, claim: NarrativeClaim) -> ReconciliationRow:
    row = ReconciliationRow(claim=claim)
    idx = _nearest_update_idx(scheds, claim.period_end)
    if idx is None:
        row.classification = "UNMATCHED"
        row.reason = "no update within 45 days of the claim's period end"
        return row
    matched = scheds[idx]
    row.matched_update = matched.label()

    if not claim.activity_code:
        # -- project-level claim: claimed finish vs the update's forecast finish
        recorded = matched.finish_date
        row.recorded_value = recorded.date().isoformat() if recorded else "—"
        if claim.claimed_finish is None or recorded is None:
            row.classification = "CONSISTENT"
            row.reason = "no comparable claimed/recorded finish date"
            return row
        delta_days = (recorded.date() - claim.claimed_finish.date()).days
        row.delta = f"{delta_days:+d}d"
        if abs(delta_days) <= PROJECT_FINISH_DAY_THRESHOLD:
            row.classification = "CONSISTENT"
        else:
            row.classification = "DISCREPANT"
            row.reason = (f"claimed finish {claim.claimed_finish.date()} vs recorded "
                          f"project finish {recorded.date()} ({matched.label()})")
        return row

    # -- activity-level claim: percent complete and forecast/actual finish
    a = next((act for act in matched.activities.values()
             if act.code == claim.activity_code), None)
    if a is None:
        row.classification = "UNMATCHED"
        row.reason = f"activity {claim.activity_code} not present in {matched.label()}"
        return row

    discrepancies = []
    if claim.claimed_pct is not None:
        gap = claim.claimed_pct - a.pct_complete
        row.recorded_value = f"{a.pct_complete:.0f}% complete"
        row.delta = f"{gap:+.0f} pts"
        if abs(gap) > PCT_GAP_THRESHOLD:
            discrepancies.append(f"claimed {claim.claimed_pct:.0f}% vs recorded "
                                 f"{a.pct_complete:.0f}% complete ({gap:+.0f} pts)")

    recorded_finish = a.actual_finish or a.early_finish or a.planned_finish
    if claim.claimed_finish is not None and recorded_finish is not None:
        cal = matched.cal_for(a)
        delta_wd = working_days_between(cal, recorded_finish, claim.claimed_finish)
        if not row.recorded_value:
            row.recorded_value = recorded_finish.date().isoformat()
        if delta_wd is not None and abs(delta_wd) > FINISH_WD_THRESHOLD:
            discrepancies.append(f"claimed finish {claim.claimed_finish.date()} vs recorded "
                                 f"{recorded_finish.date()} ({delta_wd:+.1f} working days)")

    row.classification = "DISCREPANT" if discrepancies else "CONSISTENT"
    row.reason = "; ".join(discrepancies)

    # -- cross-check later updates: was the record rewritten out from under the claim?
    if claim.claimed_finish is not None:
        claimed_str = claim.claimed_finish.date().isoformat()
        for cs in changesets[idx:]:
            for ch in cs.actual_date_changes:
                if ch.code == claim.activity_code \
                        and ch.field in ("actual start", "actual finish") \
                        and ch.before == claimed_str:
                    row.classification = "RECORD-REWRITTEN"
                    row.reason = (f"claim matched the then-reported {ch.field} "
                                  f"({ch.before}); later rewritten to {ch.after} "
                                  f"in {cs.later.label()}")
                    return row
    return row


def _summarize(rows: list) -> dict:
    out = {"CONSISTENT": 0, "DISCREPANT": 0, "RECORD-REWRITTEN": 0, "UNMATCHED": 0}
    for r in rows:
        out[r.classification] = out.get(r.classification, 0) + 1
    out["total"] = len(rows)
    return out


def reconcile(sa, claims_csv: Optional[str]) -> ReconciliationResult:
    """Reconcile a narrative-claims CSV against a schedule series.  Never
    raises: a bad row, a missing activity, or a read failure is reported in
    the row/result ``reason`` instead."""
    result = ReconciliationResult()
    if not claims_csv:
        result.reason = "no narrative-claims CSV provided"
        return result
    scheds = getattr(sa, "schedules", [])
    if not scheds:
        result.reason = "no schedules to reconcile against"
        return result
    try:
        claims = load_claims_csv(claims_csv)
    except OSError as e:
        result.reason = f"could not read narrative-claims CSV: {e}"
        return result
    changesets = getattr(sa, "changesets", [])
    for claim in claims:
        try:
            result.rows.append(_reconcile_one(scheds, changesets, claim))
        except Exception as e:            # a broken claim must never sink the run
            result.rows.append(ReconciliationRow(
                claim=claim, classification="UNMATCHED",
                reason=f"reconciliation error: {e}"))
    result.summary = _summarize(result.rows)
    return result


def run_narrative(sa, claims_csv: Optional[str] = None) -> ReconciliationResult:
    """API wrapper matching the module's ``run_*`` convention.  Never
    raises."""
    try:
        return reconcile(sa, claims_csv)
    except Exception as e:                # pragma: no cover - defensive
        result = ReconciliationResult()
        result.reason = f"narrative reconciliation failed: {e}"
        return result
