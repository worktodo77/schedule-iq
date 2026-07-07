"""S5 — editing-session forensics (ANALYTICS_PROPOSAL.md §6.1).

P6 TASK rows carry ``create_date``, ``create_user``, ``update_date``, and
``update_user`` audit columns.  This module reconstructs editing SESSIONS per
update file (activities clustered by editing user and timestamp), then raises
named, citable observations: bulk sessions dated just before a claim, edits by
unusual users, sessions where an activity's logic changed in the same session
its actuals were entered, and the driving-path share of the edits.

Discipline (CLAUDE.md §§2, 4): every flag is decomposed to the record that
raised it and paired with an innocent explanation ("a bulk edit may reflect a
scheduled data-maintenance pass").  No conclusion is drawn — the language cap
is "warrants explanation"; the words "manipulation" and "intent" do not
appear.  Missing audit metadata is common in sanitized XERs and degrades
cleanly with a disclosure naming the absent columns; the module never crashes.

Session semantics
-----------------
Activities of the same ``update_user`` are grouped into a session when their
``update_date`` values fall within a 30-minute window of one another IF the
timestamps carry a time of day; when every timestamp is midnight (a date-only
export) the fallback groups by the same calendar day.  Which path was taken is
disclosed per file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ..compare.diff import compare
from ..ingest.model import Activity, Schedule

LABEL = ("PRELIMINARY — editing-session forensics; observational only, every "
         "flag warrants explanation and is reserved to the expert")
CAPTION = ("editing-session flags — preliminary screening from the files' P6 "
           "audit columns; each warrants explanation, none is a conclusion.")
SENTENCE_CAP = "warrants explanation"

# A session is "bulk" once it touches at least this many activities, or at least
# this share of the file's real activities — whichever the analyst prefers.
BULK_MIN_ACTIVITIES = 25
BULK_FILE_SHARE = 0.20
# A bulk session dated within this many days before a claim/submission date is
# the observation of interest.
CLAIM_LOOKBACK_DAYS = 14
# Same-user edits within this many minutes cluster into one session (time-mode).
SESSION_WINDOW_MINUTES = 30

INNOCENT_EXPLANATIONS = [
    "a bulk edit session may reflect a routine scheduled data-maintenance pass "
    "(a global calendar or code re-assignment); confirm against the update "
    "narrative before drawing any inference.",
    "a user appearing in a single update may be a temporary or seconded planner "
    "covering one cycle; verify against the project's staffing record.",
    "logic and actuals entered together may simply be one planner statusing a "
    "newly started activity and wiring its successor in the same sitting; "
    "inquiry into the update workflow warrants explanation.",
]


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class SessionFlag:
    code: str                        # bulk_before_claim | bulk_session | ...
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


@dataclass
class EditSession:
    update_index: int                # position of the file in the series
    schedule_label: str
    user: str
    start_time: Optional[str]        # isoformat of earliest update_date
    end_time: Optional[str]
    activity_count: int
    activity_codes: list[str]
    wbs_spread: int                  # distinct top-level WBS nodes touched
    driving_path_count: int
    driving_path_share: Optional[float]
    flags: list[SessionFlag] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "update_index": self.update_index,
            "schedule_label": self.schedule_label,
            "user": self.user,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "activity_count": self.activity_count,
            "activity_codes": list(self.activity_codes),
            "wbs_spread": self.wbs_spread,
            "driving_path_count": self.driving_path_count,
            "driving_path_share": self.driving_path_share,
            "flags": [f.to_dict() for f in self.flags],
        }


@dataclass
class EditSessionAnalysis:
    label: str
    caption: str
    sessions: list[EditSession]
    timeline: list[EditSession]                 # every session ordered by time
    users_single_update: list[str]
    driving_path_overall_share: Optional[float]
    summary: dict[str, int]
    disclosures: list[str]
    innocent_explanations: list[str]
    thresholds: dict[str, float]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "caption": self.caption,
            "sessions": [s.to_dict() for s in self.sessions],
            "timeline": [s.to_dict() for s in self.timeline],
            "users_single_update": list(self.users_single_update),
            "driving_path_overall_share": self.driving_path_overall_share,
            "summary": dict(self.summary),
            "disclosures": list(self.disclosures),
            "innocent_explanations": list(self.innocent_explanations),
            "thresholds": dict(self.thresholds),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _has_metadata(sched: Schedule) -> bool:
    return any(a.update_user or a.update_date for a in sched.real_activities)


def _on_driving_path(a: Activity) -> bool:
    return bool(a.is_longest_path) or bool(a.is_critical_flag)


def _top_wbs_uid(sched: Schedule, wbs_uid: Optional[str]) -> str:
    """Highest ancestor below the project root (for WBS-spread counting)."""
    if not wbs_uid or wbs_uid not in sched.wbs:
        return wbs_uid or "(none)"
    chain, seen = [], set()
    node = sched.wbs.get(wbs_uid)
    while node is not None and node.uid not in seen:
        seen.add(node.uid)
        chain.append(node.uid)
        node = sched.wbs.get(node.parent_uid) if node.parent_uid else None
    return chain[-2] if len(chain) >= 2 else chain[-1]


def _claim_dates(events: Optional[list]) -> list[datetime]:
    """Pull candidate claim/submission dates from an events list (dicts as
    produced by intake.events.load_events_csv, or any dict carrying a date)."""
    out: list[datetime] = []
    if not events:
        return out
    for ev in events:
        if not isinstance(ev, dict):
            continue
        for key in ("date", "claim_date", "submission_date", "finish", "start"):
            v = ev.get(key)
            if isinstance(v, datetime):
                out.append(v)
                break
    return out


def _cluster(acts: list[Activity], time_mode: bool) -> list[list[Activity]]:
    """Group one user's activities into sessions by update_date proximity."""
    dated = sorted((a for a in acts if a.update_date is not None),
                   key=lambda a: a.update_date)
    undated = [a for a in acts if a.update_date is None]
    clusters: list[list[Activity]] = []
    cur: list[Activity] = []
    anchor: Optional[datetime] = None
    for a in dated:
        if not cur:
            cur, anchor = [a], a.update_date
            continue
        if time_mode:
            close = (a.update_date - anchor) <= timedelta(minutes=SESSION_WINDOW_MINUTES)
        else:
            close = a.update_date.date() == anchor.date()
        if close:
            cur.append(a)
        else:
            clusters.append(cur)
            cur, anchor = [a], a.update_date
    if cur:
        clusters.append(cur)
    if undated:
        clusters.append(undated)
    return clusters


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def mine_edit_sessions(schedules: list[Schedule],
                       events: Optional[list] = None) -> EditSessionAnalysis:
    """Reconstruct and flag editing sessions across a schedule series.  ``events``
    is an optional list of event dicts (as from ``intake.events.load_events_csv``)
    whose dates supply the claim/submission reference for the bulk-timing flag;
    without it the file's own export date is used as a disclosed weak proxy.
    Never raises."""
    thresholds = {
        "bulk_min_activities": float(BULK_MIN_ACTIVITIES),
        "bulk_file_share": BULK_FILE_SHARE,
        "claim_lookback_days": float(CLAIM_LOOKBACK_DAYS),
        "session_window_minutes": float(SESSION_WINDOW_MINUTES),
    }
    ordered = sorted(schedules, key=lambda s: (s.data_date or s.export_date
                                               or datetime.max))
    disclosures: list[str] = []

    if not ordered:
        return EditSessionAnalysis(
            LABEL, CAPTION, [], [], [], None,
            {"schedules": 0, "sessions": 0}, ["no schedules supplied"],
            list(INNOCENT_EXPLANATIONS), thresholds,
            reason="no schedules supplied")

    if not any(_has_metadata(s) for s in ordered):
        disclosures.append(
            "no editing-session forensics possible: the TASK audit columns "
            "create_date, create_user, update_date, update_user are absent "
            "from every file (common in sanitized XERs).")
        return EditSessionAnalysis(
            LABEL, CAPTION, [], [], [], None,
            {"schedules": len(ordered), "sessions": 0}, disclosures,
            list(INNOCENT_EXPLANATIONS), thresholds,
            reason="no create/update audit metadata on any file")

    claim_dates = _claim_dates(events)
    if not claim_dates:
        disclosures.append(
            "no event/claim dates supplied: bulk-session timing is tested "
            "against each file's own export date as a disclosed WEAK PROXY.")

    # users present in each update -> single-update ("unusual") users
    users_per_update: list[set[str]] = []
    for s in ordered:
        users_per_update.append({a.update_user for a in s.real_activities
                                 if a.update_user})
    user_update_count: dict[str, int] = {}
    for us in users_per_update:
        for u in us:
            user_update_count[u] = user_update_count.get(u, 0) + 1
    single_update_users = sorted(u for u, n in user_update_count.items() if n == 1)

    all_sessions: list[EditSession] = []
    dp_total = dp_hits = 0

    for idx, sched in enumerate(ordered):
        reals = sched.real_activities
        file_real = len(reals)
        # per-file clustering mode: time-of-day if any timestamp carries a time
        time_mode = any(a.update_date is not None
                        and (a.update_date.hour or a.update_date.minute)
                        for a in reals)
        disclosures.append(
            f"{sched.label()}: sessions clustered by "
            + ("update_user within a 30-minute window (timestamps carry time)."
               if time_mode else
               "update_user and calendar day (timestamps are date-only)."))

        # prior-update change register for the logic-with-actuals correlation
        prior = ordered[idx - 1] if idx > 0 else None
        cs = compare(prior, sched) if prior is not None else None
        logic_codes: set[str] = set()
        if cs is not None:
            for lc in cs.logic_changes:
                logic_codes.add(lc.pred_code)
                logic_codes.add(lc.succ_code)
        prior_by_code = ({a.code: a for a in prior.real_activities}
                         if prior is not None else {})

        by_user: dict[str, list[Activity]] = {}
        for a in reals:
            if a.update_user or a.update_date:
                by_user.setdefault(a.update_user or "(unknown user)", []).append(a)

        for user in sorted(by_user):
            for cluster in _cluster(by_user[user], time_mode):
                if not cluster:
                    continue
                times = [a.update_date for a in cluster if a.update_date]
                codes = sorted(a.code for a in cluster)
                wbs_spread = len({_top_wbs_uid(sched, a.wbs_uid) for a in cluster})
                dp_count = sum(1 for a in cluster if _on_driving_path(a))
                dp_total += len(cluster)
                dp_hits += dp_count
                session = EditSession(
                    update_index=idx,
                    schedule_label=sched.label(),
                    user=user,
                    start_time=min(times).isoformat() if times else None,
                    end_time=max(times).isoformat() if times else None,
                    activity_count=len(cluster),
                    activity_codes=codes,
                    wbs_spread=wbs_spread,
                    driving_path_count=dp_count,
                    driving_path_share=(dp_count / len(cluster) if cluster else None),
                )
                _flag_session(session, cluster, times, file_real, claim_dates,
                              sched, logic_codes, prior_by_code, single_update_users)
                all_sessions.append(session)

    timeline = sorted(all_sessions,
                      key=lambda s: (s.update_index, s.start_time or "",
                                     s.user))
    flagged = [s for s in all_sessions if s.flags]
    summary = {
        "schedules": len(ordered),
        "sessions": len(all_sessions),
        "flagged_sessions": len(flagged),
        "bulk_before_claim": sum(1 for s in all_sessions
                                 for f in s.flags if f.code == "bulk_before_claim"),
        "unusual_user": sum(1 for s in all_sessions
                            for f in s.flags if f.code == "unusual_user"),
        "logic_with_actuals": sum(1 for s in all_sessions
                                  for f in s.flags if f.code == "logic_with_actuals"),
        "single_update_users": len(single_update_users),
    }
    overall_share = (dp_hits / dp_total) if dp_total else None
    disclosures.append(
        f"driving-path share of edited activities is computed from the record's "
        f"own driving-path/critical flags: {dp_hits} of {dp_total} edited "
        f"activities ({overall_share:.0%})." if dp_total else
        "no driving-path/critical flags on the edited activities.")

    return EditSessionAnalysis(
        LABEL, CAPTION, all_sessions, timeline, single_update_users,
        overall_share, summary, disclosures, list(INNOCENT_EXPLANATIONS),
        thresholds)


def _flag_session(session: EditSession, cluster: list[Activity],
                  times: list[datetime], file_real: int,
                  claim_dates: list[datetime], sched: Schedule,
                  logic_codes: set[str], prior_by_code: dict[str, Activity],
                  single_update_users: list[str]) -> None:
    n = len(cluster)
    is_bulk = n >= BULK_MIN_ACTIVITIES or (file_real and n >= BULK_FILE_SHARE * file_real)
    if is_bulk:
        session.flags.append(SessionFlag(
            "bulk_session",
            f"{n} activities edited in one session "
            f"({n / file_real:.0%} of the file's {file_real} real activities)"
            if file_real else f"{n} activities edited in one session"))
        ref = min(times) if times else None
        near, basis = _near_claim(ref, claim_dates, sched)
        if near is not None:
            session.flags.append(SessionFlag(
                "bulk_before_claim",
                f"bulk session dated {ref.date()} — {near} day(s) before "
                f"{basis}; warrants explanation."))

    if session.user in single_update_users:
        session.flags.append(SessionFlag(
            "unusual_user",
            f"user {session.user!r} appears in only one update of the series; "
            "warrants explanation."))

    # logic changed in the same session an activity's actuals first appear
    hits = []
    for a in cluster:
        if a.code not in logic_codes:
            continue
        prior = prior_by_code.get(a.code)
        if prior is None:
            continue
        first_start = a.actual_start is not None and prior.actual_start is None
        first_finish = a.actual_finish is not None and prior.actual_finish is None
        if first_start or first_finish:
            hits.append(a.code)
    if hits:
        session.flags.append(SessionFlag(
            "logic_with_actuals",
            "logic edited in the same session the actuals were entered for "
            f"{', '.join(sorted(hits))}; warrants explanation."))


def _near_claim(ref: Optional[datetime], claim_dates: list[datetime],
                sched: Schedule) -> tuple[Optional[int], str]:
    """Days between a session and the nearest claim/submission date it precedes
    (within the lookback), and the basis string.  Falls back to the file's
    export date as a disclosed weak proxy when no claim dates are supplied."""
    if ref is None:
        return None, ""
    if claim_dates:
        best = None
        for cd in claim_dates:
            delta = (cd.date() - ref.date()).days
            if 0 <= delta <= CLAIM_LOOKBACK_DAYS and (best is None or delta < best):
                best = delta
        if best is not None:
            return best, "a claim/submission date"
        return None, ""
    # weak proxy: the file's own export date
    exp = sched.export_date
    if exp is not None:
        delta = (exp.date() - ref.date()).days
        if 0 <= delta <= CLAIM_LOOKBACK_DAYS:
            return delta, "this file's export date (weak proxy — no claim dates supplied)"
    return None, ""
