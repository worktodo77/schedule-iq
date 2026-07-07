"""Tests for S5 — editing-session forensics (ANALYTICS_PROPOSAL.md §6.1).

Driven by the demo_edit.xer / demo_edit_u1.xer fixture pair.  Also covers the
S5 ingest prerequisite (the create/update audit columns) and the byte-identity
gate on the pre-existing fixtures.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load, load_many                          # noqa: E402
from scheduleiq.analytics.editsessions import (                        # noqa: E402
    mine_edit_sessions, EditSessionAnalysis, LABEL, SENTENCE_CAP,
    BULK_MIN_ACTIVITIES)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EDIT0 = os.path.join(FIX, "demo_edit.xer")
EDIT1 = os.path.join(FIX, "demo_edit_u1.xer")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")

CLAIM_EVENTS = [{"title": "Claim submission", "date": datetime(2025, 6, 30)}]


@pytest.fixture(scope="session", autouse=True)
def _fixtures():
    if not os.path.exists(EDIT1):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def analysis():
    return mine_edit_sessions(load_many([EDIT0, EDIT1]), CLAIM_EVENTS)


def _u1(analysis):
    return [s for s in analysis.sessions if s.update_index == 1]


# ---------------------------------------------------------------- ingest (S5 prereq)
def test_ingest_parses_audit_columns_when_present():
    s1 = load(EDIT1)[0]
    x = next(a for a in s1.real_activities if a.code == "EDIT-X1")
    assert x.update_user == "s_logic"
    assert x.update_date == datetime(2025, 6, 25, 9, 0)
    assert x.create_user == "planner"
    assert x.create_date == datetime(2025, 1, 2, 8, 0)
    # schedule-level PROJECT audit columns captured too
    assert s1.project_update_user == "s_bulk"


def test_ingest_absent_columns_are_none():
    """Legacy fixtures carry no audit columns -> every field parses to None."""
    sb = load(BASELINE)[0]
    for a in sb.real_activities:
        assert a.create_date is None and a.create_user is None
        assert a.update_date is None and a.update_user is None
    assert sb.project_update_user == ""


def test_preexisting_fixtures_byte_identical():
    """Regenerating the fixtures must not perturb a single pre-existing byte
    (the additive-only gate)."""
    names = ["demo_baseline.xer", "demo_update1.xer", "demo_update2.xer",
             "demo_cpm.xer", "demo_cpm_divergent.xer", "demo_impact.xer",
             "demo_hs1.xer", "demo_hs2.xer"]
    before = {n: hashlib.sha256(open(os.path.join(FIX, n), "rb").read()).hexdigest()
              for n in names}
    subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                   check=True, capture_output=True)
    after = {n: hashlib.sha256(open(os.path.join(FIX, n), "rb").read()).hexdigest()
             for n in names}
    assert before == after


# ------------------------------------------------------------- session clustering
def test_update1_session_composition(analysis):
    got = sorted((s.user, s.activity_count) for s in _u1(analysis))
    # s_bulk(30), s_mech(6), s_civ split into two sessions (D1 alone; W1-3),
    # s_logic(1, X1), temp_contractor(2)
    assert got == sorted([("s_bulk", 30), ("s_mech", 6), ("s_civ", 1),
                          ("s_civ", 3), ("s_logic", 1), ("temp_contractor", 2)])
    # every real activity is accounted for exactly once
    assert sum(s.activity_count for s in _u1(analysis)) == 43


def test_bulk_session_flagged_before_claim(analysis):
    bulk = next(s for s in _u1(analysis) if s.user == "s_bulk")
    assert bulk.activity_count == 30 >= BULK_MIN_ACTIVITIES
    codes = {f.code for f in bulk.flags}
    assert "bulk_session" in codes
    assert "bulk_before_claim" in codes
    detail = next(f.detail for f in bulk.flags if f.code == "bulk_before_claim")
    assert "10 day" in detail                            # 2025-06-20 -> 2025-06-30
    # exactly one bulk-before-claim session in the whole series
    assert analysis.summary["bulk_before_claim"] == 1


def test_unusual_user_flag(analysis):
    assert analysis.users_single_update == ["temp_contractor"]
    sess = next(s for s in _u1(analysis) if s.user == "temp_contractor")
    assert sess.activity_count == 2
    assert "unusual_user" in {f.code for f in sess.flags}
    assert analysis.summary["unusual_user"] == 1


def test_logic_with_actuals_same_session(analysis):
    sess = next(s for s in _u1(analysis) if s.user == "s_logic")
    assert sess.activity_codes == ["EDIT-X1"]
    flag = next((f for f in sess.flags if f.code == "logic_with_actuals"), None)
    assert flag is not None
    assert "EDIT-X1" in flag.detail
    assert analysis.summary["logic_with_actuals"] == 1


def test_driving_path_share(analysis):
    # 8 driving-path-flagged activities (6 MECH + X1 + D1) of 43 edited per file
    assert analysis.driving_path_overall_share == pytest.approx(8 / 43, abs=1e-6)
    mech = next(s for s in _u1(analysis) if s.user == "s_mech")
    assert mech.driving_path_share == 1.0
    logic = next(s for s in _u1(analysis) if s.user == "s_logic")
    assert logic.driving_path_share == 1.0


def test_timeline_ordered(analysis):
    keys = [(s.update_index, s.start_time) for s in analysis.timeline]
    assert keys == sorted(keys, key=lambda k: (k[0], k[1] or ""))


# ------------------------------------------------------------------ weak proxy
def test_weak_proxy_when_no_events():
    r = mine_edit_sessions(load_many([EDIT0, EDIT1]))
    # 2025-06-20 bulk session is 11 days before the file's 2025-07-01 export
    assert r.summary["bulk_before_claim"] == 1
    bulk = next(s for s in r.sessions
                if s.update_index == 1 and s.user == "s_bulk")
    detail = next(f.detail for f in bulk.flags if f.code == "bulk_before_claim")
    assert "weak proxy" in detail or "export date" in detail
    assert any("weak proxy" in d.lower() for d in r.disclosures)


# ----------------------------------------------------------------- degradation
def test_missing_metadata_degrades_cleanly():
    """Sanitized XERs with no audit columns degrade with a naming disclosure."""
    r = mine_edit_sessions(load_many([BASELINE, U1, U2]))
    assert r.sessions == []
    assert r.reason
    named = " ".join(r.disclosures)
    for col in ("create_date", "create_user", "update_date", "update_user"):
        assert col in named


def test_empty_list_degrades():
    r = mine_edit_sessions([])
    assert isinstance(r, EditSessionAnalysis)
    assert r.reason
    assert r.to_dict()["sessions"] == []


# --------------------------------------------------------- guardrails / language
def test_preliminary_and_language_cap(analysis):
    assert analysis.label == LABEL and "PRELIMINARY" in analysis.label
    text = repr(analysis.to_dict()).lower()
    assert SENTENCE_CAP in text                          # 'warrants explanation'
    assert "manipulation" not in text
    assert "intent" not in text                          # covers 'intentional'
    assert analysis.innocent_explanations
    for ie in analysis.innocent_explanations:
        assert ("verify" in ie or "confirm" in ie or "inquiry" in ie
                or "warrants explanation" in ie)


def test_time_mode_disclosed(analysis):
    assert any("30-minute window" in d for d in analysis.disclosures)


def test_determinism_and_json(analysis):
    d2 = mine_edit_sessions(load_many([EDIT0, EDIT1]), CLAIM_EVENTS).to_dict()
    assert analysis.to_dict() == d2
    json.dumps(d2)
