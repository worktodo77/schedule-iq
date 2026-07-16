"""Unit coverage for the Forensics blocker taxonomy (pure, no Qt)."""
from __future__ import annotations

import os
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.gui.blocker_taxonomy import (  # noqa: E402
    CAPACITY_LIMIT, ENGINE_LIMITATION, OTHER_SKIP, SCHEDULE_DEFECT,
    SYNTHETIC_DEFECT_MESSAGE, classify_message, group_blockers,
)

# Verbatim shapes the governed runner / handshake actually emit.
SRA_CAP = ("schedule risk analysis skipped: 4430 incomplete activities exceeds "
           "the 2000-activity cap; other analytics unaffected.")
LEDGER_WINDOW = ("daily ledger skipped for Update 3 -> Update 4: window exceeds "
                 "400 days.")
IMPACT_REFUSAL = ("SET-02 handshake below threshold — engine impact analytics "
                  "refused (44.6%)")
LEDGER_REFUSAL = ("SET-02 handshake below threshold — daily ledger refused for "
                  "A -> B: match rate 32.9% is below the 99% threshold")
CALENDAR_BRIDGE = ("forensic delay diagnostics skipped: No workday found within "
                   "14 days backward from 2021-02-21 in calendar 'MV32 Topside'.")
NETWORK_DEFECT = ("SET-02 handshake below threshold — daily ledger refused for "
                  "A -> B: engine network validation failed (NET-006: circular "
                  "dependency among 3 activities)")
CLOSURE_DISCLOSURE = ("calendar 'MV32 Topside' (uid 7395) has a 21-day "
                      "non-working closure 2020-01-16 through 2020-02-05; "
                      "closure-aware engine snap bound is 21 days.")
PROGRESS_NOTE = "3 in-progress activity(ies) had a positive remaining duration."


def test_capacity_messages_classify_as_capacity():
    assert classify_message(SRA_CAP) is CAPACITY_LIMIT
    assert classify_message(LEDGER_WINDOW) is CAPACITY_LIMIT


def test_handshake_refusal_is_engine_limitation_when_engine_is_valid():
    assert classify_message(IMPACT_REFUSAL) is ENGINE_LIMITATION
    assert classify_message(LEDGER_REFUSAL) is ENGINE_LIMITATION


def test_handshake_refusal_becomes_defect_when_network_validation_failed():
    assert classify_message(
        IMPACT_REFUSAL, defect_present=True) is SCHEDULE_DEFECT


def test_explicit_network_validation_phrase_is_always_a_defect():
    # Even without the defect flag, an embedded validation-failure phrase wins.
    assert classify_message(NETWORK_DEFECT) is SCHEDULE_DEFECT


def test_calendar_bridge_refusal_is_engine_limitation():
    assert classify_message(CALENDAR_BRIDGE) is ENGINE_LIMITATION


def test_non_blocker_messages_are_not_classified():
    # A successfully-bridged closure disclosure and a progress note must not be
    # mistaken for blockers even though one contains the word "closure".
    assert classify_message(CLOSURE_DISCLOSURE) is None
    assert classify_message(PROGRESS_NOTE) is None
    assert classify_message("") is None


def test_generic_skip_is_other():
    assert classify_message("network cockpit skipped: boom") is OTHER_SKIP


def test_group_blockers_orders_by_severity_and_drops_empties():
    groups = group_blockers([PROGRESS_NOTE, SRA_CAP, IMPACT_REFUSAL,
                             "phase analyzer skipped: x"])
    assert [g.category for g in groups] == [
        ENGINE_LIMITATION, CAPACITY_LIMIT, OTHER_SKIP]
    # The progress note is not a blocker and never appears.
    flat = [m for g in groups for m in g.messages]
    assert PROGRESS_NOTE not in flat
    assert IMPACT_REFUSAL in flat and SRA_CAP in flat


def test_defect_flag_routes_refusals_and_leads_with_defect():
    groups = group_blockers([IMPACT_REFUSAL, SRA_CAP],
                            network_validation_failed=True)
    assert groups[0].category is SCHEDULE_DEFECT
    # The refusal moved into the defect group; capacity is untouched.
    assert IMPACT_REFUSAL in groups[0].messages
    assert any(g.category is CAPACITY_LIMIT and SRA_CAP in g.messages
               for g in groups)


def test_defect_synthesised_when_no_message_carries_the_cause():
    # A defect with zero classifiable blocker messages still surfaces.
    groups = group_blockers([PROGRESS_NOTE], network_validation_failed=True)
    assert groups and groups[0].category is SCHEDULE_DEFECT
    assert groups[0].messages == [SYNTHETIC_DEFECT_MESSAGE]


def test_duplicate_messages_collapse():
    groups = group_blockers([SRA_CAP, SRA_CAP])
    assert groups[0].messages == [SRA_CAP]


def test_categories_use_valid_statuspill_tones():
    valid = {"success", "warning", "danger", "info", "muted"}
    for cat in (SCHEDULE_DEFECT, ENGINE_LIMITATION, CAPACITY_LIMIT, OTHER_SKIP):
        assert cat.tone in valid
        assert cat.pill and cat.title and cat.guidance
