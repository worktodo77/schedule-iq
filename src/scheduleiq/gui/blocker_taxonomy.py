"""Classify run-diagnostic messages into an analyst-facing blocker taxonomy.

The governed runner never sinks a run: when an engine-dependent exhibit cannot
be produced it appends a plain-language reason to ``RunResult.messages`` and
carries on.  Presented as one undifferentiated list, those reasons conflate
situations an analyst must treat very differently — a genuine schedule defect
that must be corrected in P6 looks the same as a legitimate schedule the
diagnostic engine simply cannot reproduce within tolerance.

This module groups the reasons into four categories, each with a severity tone
and standing guidance, so the Forensics page can say *why* an exhibit is missing
and *what, if anything, the analyst should do*:

* ``SCHEDULE_DEFECT``   — the source network is genuinely invalid; correct it.
* ``ENGINE_LIMITATION`` — the schedule is valid but the engine could not
  reproduce it; the imported P6 dates remain the schedule of record.
* ``CAPACITY_LIMIT``    — an exhibit was skipped for a size/scope limit; every
  other analytic is unaffected.
* ``OTHER_SKIP``        — anything else that was skipped.

Pure and deterministic: no Qt, no engine calls.  The one signal the message text
cannot carry reliably — whether a handshake refusal was caused by a *blocking
network-validation failure* (a real defect) versus a merely *low match rate* (an
engine limitation) — is supplied by the caller as ``network_validation_failed``,
read from the SET-02 check's ``network validation`` finding.  A 0.0% match rate
is NOT a reliable proxy: a valid-but-fully-divergent schedule also scores 0.0%.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlockerCategory:
    key: str
    title: str
    pill: str        # short StatusPill label
    tone: str        # StatusPill tone: danger | warning | info | muted
    guidance: str    # one standing paragraph of analyst guidance


SCHEDULE_DEFECT = BlockerCategory(
    key="schedule_defect",
    title="Schedule defect — correction required",
    pill="DEFECT",
    tone="danger",
    guidance=(
        "The diagnostic engine could not schedule this network because the "
        "source schedule contains a genuine logic defect — for example a true "
        "circular dependency, a duplicate activity ID, or an orphaned "
        "relationship. Engine-dependent exhibits and float are unavailable "
        "until the schedule is corrected in P6 and re-exported. Open Checks and "
        "select the SET-02 row for the exact blocking findings."),
)

ENGINE_LIMITATION = BlockerCategory(
    key="engine_limitation",
    title="Engine limitation — schedule of record stands",
    pill="ENGINE LIMIT",
    tone="warning",
    guidance=(
        "The schedule is valid, but the diagnostic engine could not reproduce "
        "it within the SET-02 tolerance, so engine-dependent exhibits were "
        "refused. This reflects a current limitation of the diagnostic engine, "
        "not a defect in your schedule. The imported P6 dates remain the "
        "schedule of record and every stored-field check is unaffected."),
)

CAPACITY_LIMIT = BlockerCategory(
    key="capacity_limit",
    title="Size or scope limit — exhibit skipped",
    pill="SCOPE LIMIT",
    tone="info",
    guidance=(
        "This exhibit was skipped because the schedule exceeds a size or scope "
        "limit built into the tool — for example the schedule-risk "
        "incomplete-activity cap, or a daily-ledger window span. All other "
        "analytics are unaffected."),
)

OTHER_SKIP = BlockerCategory(
    key="other_skip",
    title="Other skipped exhibit",
    pill="SKIPPED",
    tone="muted",
    guidance=(
        "This exhibit was skipped. Open Checks for the underlying detail."),
)

# Most-severe first — the presentation order.
CATEGORY_ORDER: tuple[BlockerCategory, ...] = (
    SCHEDULE_DEFECT, ENGINE_LIMITATION, CAPACITY_LIMIT, OTHER_SKIP,
)

# Synthesised lead when the engine failed network validation but no individual
# blocker message happened to spell out the cause (e.g. a single-file run where
# only the impact site refused with a bare match-rate string).
SYNTHETIC_DEFECT_MESSAGE = (
    "The diagnostic engine could not schedule this network — SET-02 network "
    "validation failed. Open Checks and select the SET-02 row for the blocking "
    "findings.")

# Phrase tables, checked in this precedence order.
_DEFECT_PHRASES = (
    "network validation failed", "net-006", "net-007", "net-009", "net-013",
    "circular dependency", "circular logic", "duplicate activity",
    "self-referential", "orphaned relationship",
)
# Specific, skip-context phrases only — never a bare "exceeds the", which a
# non-blocker variance message could carry.
_CAPACITY_PHRASES = (
    "activity cap", "window exceeds",
)
_HANDSHAKE_PHRASES = (
    "below threshold", "match rate", "handshake", "refused",
)
_CALENDAR_LIMIT_PHRASES = (
    "no workday found", "not in the workday table", "workday-table growth",
    "coverage error",
)
_OTHER_PHRASES = (
    "skipped", "unavailable", "not computable", "not generated",
)


def classify_message(message: str, *, defect_present: bool = False):
    """Return the ``BlockerCategory`` for one run message, or ``None`` if the
    message is not a blocker diagnostic (progress notes, disclosures, etc.).

    ``defect_present`` routes handshake/SET-02 refusals to ``SCHEDULE_DEFECT``
    rather than ``ENGINE_LIMITATION`` — because when the engine failed network
    validation, a "handshake refused" line is a *consequence of the defect*, not
    an independent tolerance miss.
    """
    low = str(message).strip().lower()
    if not low:
        return None
    if any(p in low for p in _DEFECT_PHRASES):
        return SCHEDULE_DEFECT
    if any(p in low for p in _CAPACITY_PHRASES):
        return CAPACITY_LIMIT
    if any(p in low for p in _HANDSHAKE_PHRASES):
        return SCHEDULE_DEFECT if defect_present else ENGINE_LIMITATION
    if any(p in low for p in _CALENDAR_LIMIT_PHRASES):
        return ENGINE_LIMITATION
    if any(p in low for p in _OTHER_PHRASES):
        return OTHER_SKIP
    return None


@dataclass(frozen=True)
class BlockerGroup:
    category: BlockerCategory
    messages: list[str]


def group_blockers(messages, *, network_validation_failed: bool = False):
    """Group run messages by category, most-severe first, dropping empties.

    Order within a category preserves first appearance; duplicate messages are
    collapsed.  When ``network_validation_failed`` is set but no message carried
    the cause, a synthetic lead is added so the defect is never silent.
    """
    buckets: dict[str, list[str]] = {c.key: [] for c in CATEGORY_ORDER}
    for raw in messages or ():
        text = str(raw).strip()
        if not text:
            continue
        category = classify_message(
            text, defect_present=network_validation_failed)
        if category is None:
            continue
        if text not in buckets[category.key]:
            buckets[category.key].append(text)

    if network_validation_failed and not buckets[SCHEDULE_DEFECT.key]:
        buckets[SCHEDULE_DEFECT.key].append(SYNTHETIC_DEFECT_MESSAGE)

    return [BlockerGroup(c, buckets[c.key])
            for c in CATEGORY_ORDER if buckets[c.key]]
