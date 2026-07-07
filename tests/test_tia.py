"""Tests for the push-button TIA workbench (backlog S6; ANALYTICS_PROPOSAL.md
§6.5) — scheduleiq.analytics.tia.

The engine-consistent half-step update pair demo_hs1.xer / demo_hs2.xer (both
handshake at 100%) doubles as the TIA fixture.  Every asserted number was
extracted from a manual engine run on the pair and is restated inline:

  Additive fragnet impact on demo_hs2 (statused baseline; target MS-HS EF
  2025-07-07 record and engine):
    * EV-ENV  fragnet(6 wd) ahead of HA50 "Envelope" (controlling chain) ->
      target +6 wd (2025-07-15).
    * EV-FIT  fragnet(4 wd) ahead of HA60 "Fit-Out" (controlling chain), in
      series after HA50 -> cumulative +10 wd (2025-07-21); marginal +4.
    * EV-LND  fragnet(3 wd) ahead of HC10 "Landscaping" (high-float chain R,
      off path) -> isolated 0, marginal 0.
    cumulative total +10 wd == Σ marginals (6 + 4 + 0).

  Subtractive collapse on demo_hs2 (pure-CPM planning network; unstatused finish
  2025-08-15):
    * OWNER GLOBAL: remove HA50(6) + HA60(4) -> compensable 10 wd (2025-08-01).
    * OWNER STEPPED (latest-first): HA60 marginal 4 (cum 4) then HA50 marginal 6
      (cum 10); compensable 10.
"""
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load                                          # noqa: E402
from scheduleiq.intake.events import EventMapResult, EventMapping, EventMatch  # noqa: E402
from scheduleiq.analytics.tia import TiaResult, run_tia                     # noqa: E402
from scheduleiq.cpm.collapse import (CollapseInput, Delay, ExtractionMode,  # noqa: E402
                                     run_collapse)
from scheduleiq.cpm.models import Activity as CA, Relationship as CR        # noqa: E402
from scheduleiq.cpm.handshake import HandshakeRefusal, clear_handshake_cache  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")
EVENTS_CSV = os.path.join(FIX, "tia_events_sample.csv")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(HS1) and os.path.exists(HS2)
            and os.path.exists(EVENTS_CSV)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def hs1():
    return load(HS1)[0]


@pytest.fixture(scope="session")
def hs2():
    return load(HS2)[0]


def _mapping(hs2):
    """A hand-built EventMapResult mapping three events onto demo_hs2 by activity
    code, so fragnet insertion and impact are fully deterministic (independent of
    the date-overlap/keyword matcher)."""
    label = hs2.label()

    def ev(eid, title, code, name, start, finish, resp):
        return EventMapping(
            event_id=eid, title=title, start=start, finish=finish,
            keywords=[], responsibility=resp, schedule_label=label,
            matches=[EventMatch(code, name, ["explicit test mapping"])])

    return EventMapResult(events=[
        ev("EV-ENV", "Envelope Redesign", "HA50", "Envelope",
           datetime(2025, 4, 14), datetime(2025, 4, 21), "Owner"),      # 6 wd
        ev("EV-FIT", "Fit-Out Access", "HA60", "Fit-Out",
           datetime(2025, 4, 22), datetime(2025, 4, 25), "Owner"),      # 4 wd
        ev("EV-LND", "Landscaping Weather", "HC10", "Landscaping",
           datetime(2025, 4, 28), datetime(2025, 4, 30), "Neutral"),    # 3 wd
    ])


@pytest.fixture(scope="session")
def tia(hs1, hs2):
    return run_tia([hs1, hs2], _mapping(hs2))


# ----------------------------------------------------------------- basic shape
def test_target_and_handshakes(tia, hs2):
    assert tia.target_code == "MS-HS"
    assert tia.as_built_schedule_label == hs2.label()
    # both updates handshook at 100%
    assert all(h["match_rate_pct"] == 100.0 for h in tia.handshakes.values())
    assert len(tia.handshakes) == 2
    assert isinstance(tia, TiaResult)


# ---------------------------------------------------- fragnet auto-build (3.6/3.7)
def test_fragnet_built_at_right_insertion(tia, hs2):
    # EV-ENV -> HA50: fragnet duration 6 wd (2025-04-14..04-21 on the 5-day cal),
    # tied from HA50's predecessors and INTO HA50 (FS).
    frag = next(f for f in tia.fragnets if f.event_id == "EV-ENV")
    assert frag.mapped_activity_code == "HA50"
    assert frag.duration_workdays == 6
    assert frag.rel_type == "FS"
    assert frag.successor_tie == frag.mapped_activity_uid == "4050"
    # HA50 has two predecessors in hs2 (chain P HA40 + rerouted chain Q HB20).
    assert set(frag.predecessor_ties) == {"4040", "4110"}
    assert frag.responsibility == "OWNER"
    # off-path event's fragnet duration is 3 wd on HC10.
    lnd = next(f for f in tia.fragnets if f.event_id == "EV-LND")
    assert lnd.mapped_activity_code == "HC10" and lnd.duration_workdays == 3


# ------------------------------------------------- single-event isolated impact
def test_single_event_impacts_hand_derived(tia):
    u = tia.updates[0]  # only demo_hs2 carries events
    rows = {r.event_id: r for r in u.rows}
    # HA50 on the controlling chain -> +6 wd isolated; HA60 -> +4; HC10 off -> 0.
    assert rows["EV-ENV"].isolated_delta_workdays == 6
    assert rows["EV-FIT"].isolated_delta_workdays == 4
    assert rows["EV-LND"].isolated_delta_workdays == 0
    assert u.baseline_engine_target_finish.isoformat() == "2025-07-07"
    assert u.record_target_finish.isoformat() == "2025-07-07"


# ---------------------------------------------- cumulative stepped-insertion table
def test_cumulative_marginals_sum_to_total(tia):
    u = tia.updates[0]
    rows = {r.event_id: r for r in u.rows}
    # event-date order: ENV (+6), FIT (cum +10, marginal +4), LND (marginal 0).
    assert rows["EV-ENV"].cumulative_delta_workdays == 6
    assert rows["EV-FIT"].cumulative_delta_workdays == 10
    assert rows["EV-FIT"].marginal_delta_workdays == 4
    assert rows["EV-LND"].marginal_delta_workdays == 0
    assert u.cumulative_total_workdays == 10
    assert rows["EV-FIT"].engine_target_finish.isoformat() == "2025-07-21"
    # identity: Σ marginal == cumulative total (exact by construction)
    assert u.identity_holds is True
    assert sum(r.marginal_delta_workdays for r in u.rows) == 10


# ------------------------------------------------ collapse global (MIP 3.8/3.9)
def test_collapse_global_earlier_finish(tia):
    owner = tia.collapse["OWNER"]["global"]
    # unstatused as-built finish 2025-08-15; removing HA50(6)+HA60(4) -> 2025-08-01.
    assert owner["is_blocked"] is False
    assert owner["calibration_ok"] is True
    assert owner["compensable_days"] == 10
    assert owner["original_finish"] == "2025-08-15"
    assert owner["collapsed_finish"] == "2025-08-01"
    assert owner["delay_quantity"] == "ECD"      # OWNER extraction


def test_collapse_stepped_latest_first(tia):
    stepped = tia.collapse["OWNER"]["stepped"]
    marg = [(m["activity_id"], m["marginal_days"], m["cumulative_days"])
            for m in stepped["per_delay_marginal"]]
    # latest-first: HA60 (4060) removed first, then HA50 (4050).
    assert marg == [("4060", 4, 4), ("4050", 6, 10)]
    assert stepped["compensable_days"] == 10
    # the Neutral event lands under its own party bucket, not OWNER.
    assert set(tia.collapse) == {"OWNER", "NEUTRAL"}


# ------------------------------------- collapse OOS block guard (unit-level)
def test_collapse_block_guard_surfaces_and_no_auto_ack():
    # The engine inputs from a statused file carry pins, not raw actuals, so the
    # collapse there is OOS-clean.  Construct the OOS case directly to prove the
    # block path is faithfully carried: is_blocked, no auto-acknowledge.
    from datetime import date
    from scheduleiq.cpm.calendar_ops import build_workday_table
    from scheduleiq.cpm.models import Calendar
    acts = [
        CA("P", original_duration=5, actual_start=date(2023, 1, 2),
           actual_finish=date(2023, 1, 9)),
        CA("S", original_duration=5, actual_start=date(2023, 1, 2)),
    ]
    cal = Calendar(name="c", work_days={1, 2, 3, 4, 5, 6, 7})
    tbl = build_workday_table(cal, date(2023, 1, 1), date(2023, 3, 1))
    inp = CollapseInput(activities=acts, relationships=[CR("P", "S", "FS", 0)],
                        project_start=date(2023, 1, 2), workday_table=tbl,
                        calendar=cal, delays=[Delay("S", "OWNER", 2)], party="OWNER")
    res = run_collapse(inp)
    assert res.is_blocked is True                 # blocked, reported blocked
    assert res.oos_clean is False
    assert res.collapsed_finish is None           # no but-for auto-computed
    assert res.compensable_days == 0


# ------------------------------------------------------------- handshake gating
def test_handshake_refusal_propagates():
    with pytest.raises(HandshakeRefusal):
        run_tia([load(CPM_DIV)[0]], EventMapResult(events=[]))


def test_handshake_skip_runs_with_disclosure(hs1, hs2):
    res = run_tia([hs1, hs2], _mapping(hs2), handshake="skip")
    assert any("skip" in d.lower() and "bypass" in d.lower() for d in res.disclosures)
    # skip still computes the same additive impact on the valid pair
    assert res.updates[0].cumulative_total_workdays == 10


def test_bad_handshake_mode_raises(hs1, hs2):
    with pytest.raises(ValueError):
        run_tia([hs1, hs2], _mapping(hs2), handshake="maybe")


# ------------------------------------------------------------------- CSV path
def test_events_csv_path_runs(hs1, hs2):
    res = run_tia([hs1, hs2], EVENTS_CSV)
    assert res.target_code == "MS-HS"
    assert res.fragnets                             # at least one fragnet built
    assert res.to_dict()["preliminary"].startswith("PRELIMINARY")


# ---------------------------------------------------------------- determinism
def test_deterministic_to_dict(hs1, hs2):
    clear_handshake_cache()
    a = run_tia([hs1, hs2], _mapping(hs2)).to_dict()
    clear_handshake_cache()
    b = run_tia([hs1, hs2], _mapping(hs2)).to_dict()
    assert a == b


# ---------------------------------------------------------- serialization shape
def test_to_dict_shape_and_framing(tia):
    d = tia.to_dict()
    assert set(d) >= {"method", "mode", "presentation_rule", "target",
                      "handshakes", "fragnets", "updates", "collapse",
                      "disclosures", "preliminary", "framing"}
    assert "6.5" in d["framing"] or "§6.5" in d["framing"]
    assert d["mode"] == "prospective"
