"""Tests for the weather & external-conditions overlay (backlog N1, §8.1).

The synthetic station fixture ``weather_station_sample.csv`` spans 2015-2025
(11 years) so a 10-year norm (2015-2024) exists for the 2025 project window.
Designed anomalies (see analytics/weather.py + tests/fixtures/gen notes):

  * April 10-year norm = exactly 10.0 rain-lost days.
  * demo_hs window [2025-04-07, 2025-05-05): actual 14 lost days, norm 8.0,
    exceedance = +6 (hand-computable).
  * every month of the 5-day-calendar span shows a calendar-realism shortfall
    (embedded downtime 0); April 2025 shortfall = 10.0.
  * a dry July window is better than norm -> negative exceedance (both ways).
"""
import csv
import os

import pytest

from scheduleiq.ingest import load
from scheduleiq.ingest.model import Activity, ActivityType, Schedule, WbsNode
from scheduleiq.analytics.weather import (
    DEFAULT_SENSITIVE_KEYWORDS, WeatherThresholds, analyze_weather,
    load_ghcn_csv, match_sensitive)
from datetime import datetime

HERE = os.path.dirname(__file__)
FIX = os.path.join(HERE, "fixtures")
CSV = os.path.join(FIX, "weather_station_sample.csv")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")

# custom sensitive tags: default keywords do not match the demo_hs names
HS_TAGS = ["foundation", "steel", "groundwork"]


# ---------------------------------------------------------------------------
# loader
# ---------------------------------------------------------------------------
def test_loader_parses_and_converts_units():
    rec = load_ghcn_csv(CSV)
    assert rec.station == "USW00099999"
    assert len(rec.by_date) > 4000
    # unit conversions exact (GHCN tenths -> standard units)
    from datetime import date
    jan1 = rec.by_date[date(2015, 1, 1)]
    assert jan1["PRCP"] == pytest.approx(4.0)     # 40 tenths mm -> 4.0 mm
    assert jan1["TMAX"] == pytest.approx(-2.0)    # -20 tenths C -> -2.0 C
    assert jan1["SNOW"] == pytest.approx(80.0)    # whole mm, unchanged
    assert jan1["TMIN"] == pytest.approx(-10.0)   # -100 tenths C -> -10.0 C
    # a rain day: 150 tenths mm -> 15.0 mm
    assert rec.by_date[date(2015, 4, 1)]["PRCP"] == pytest.approx(15.0)


def test_loader_ignores_unknown_elements_with_disclosure():
    rec = load_ghcn_csv(CSV)
    assert "AWND" in rec.unknown_elements
    assert "AWND" not in {k for v in rec.by_date.values() for k in v}
    assert any("unknown elements ignored" in d for d in rec.disclosures)


def test_lost_day_thresholds_union():
    rec = load_ghcn_csv(CSV)
    th = WeatherThresholds()
    from datetime import date
    assert rec.is_lost_day(date(2015, 4, 1), th)      # rain 15mm >= 10
    assert rec.is_lost_day(date(2015, 1, 1), th)      # freeze -2C <= 0 (and snow)
    assert not rec.is_lost_day(date(2015, 5, 15), th)  # dry May, warm


def test_coverage_guard_refuses_thin_window(tmp_path):
    """Truncating the record so the demo_hs window is mostly missing must make
    that window refuse rather than report on thin data."""
    trunc = tmp_path / "weather_trunc.csv"
    with open(CSV, newline="") as fin, open(trunc, "w", newline="") as fout:
        r = csv.reader(fin)
        w = csv.writer(fout)
        header = next(r)
        w.writerow(header)
        i_date = [c.upper() for c in header].index("DATE")
        for row in r:
            # keep everything up to 2025-04-10, drop the rest of the window
            if row[i_date] <= "2025-04-10":
                w.writerow(row)
    rec = load_ghcn_csv(str(trunc))
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    wa = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS)
    win = wa.windows[0]
    assert win.refused is True
    assert win.coverage < 0.60
    assert win.exceedance_days is None
    # the exhibit row reflects the refusal, not a fabricated number
    assert wa.exhibit_rows[0].actual_lost_days is None
    assert "REFUSED" in wa.exhibit_rows[0].note


# ---------------------------------------------------------------------------
# norm arithmetic
# ---------------------------------------------------------------------------
def test_april_norm_hand_computed():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    wa = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS)
    assert wa.norm_years == list(range(2015, 2025))          # exactly 10 years
    # each 2015-2024 April carries exactly 10 rain-lost days -> mean 10.0
    assert wa.monthly_norm[4] == pytest.approx(10.0)
    assert wa.monthly_norm[5] == pytest.approx(0.0)          # dry May by design


# ---------------------------------------------------------------------------
# abnormal weather per window (§8.1b)
# ---------------------------------------------------------------------------
def test_demo_hs_window_exceedance_exact():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    wa = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS)
    assert len(wa.windows) == 1
    win = wa.windows[0]
    assert win.refused is False
    assert win.coverage == pytest.approx(1.0)
    # norm = April 10 * 24/30 + May 0 * 4/31 = 8.0 ; actual = 14 ; exceedance +6
    assert win.norm_lost_days == pytest.approx(8.0)
    assert win.actual_lost_days == 14
    assert win.exceedance_days == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# calendar realism (§8.1a)
# ---------------------------------------------------------------------------
def test_calendar_realism_shortfall_month():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    wa = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS)
    by_label = {m.label: m for m in wa.calendar_realism}
    apr = by_label["2025-04"]
    # the 5-day calendar embeds zero weekday downtime; the norm implies 10 lost
    # days -> shortfall of exactly 10.0
    assert apr.embedded_downtime_days == 0
    assert apr.norm_lost_days == pytest.approx(10.0)
    assert apr.shortfall_days == pytest.approx(10.0)
    assert apr.flagged is True
    # dry May: norm 0 -> no shortfall
    assert by_label["2025-05"].flagged is False


# ---------------------------------------------------------------------------
# sensitive-set matching (§8.1b population)
# ---------------------------------------------------------------------------
def test_sensitive_default_keyword_hit():
    """A synthetic schedule whose activity names hit the documented default
    keyword set."""
    s = Schedule(data_date=datetime(2025, 4, 7))
    s.wbs["w1"] = WbsNode(uid="w1", parent_uid=None, code="EX", name="Sitework")
    s.activities["a1"] = Activity(uid="a1", code="E100",
                                  name="Site Excavation & Concrete Pour",
                                  atype=ActivityType.TASK, wbs_uid="w1")
    s.activities["a2"] = Activity(uid="a2", code="E200", name="Submittals",
                                  atype=ActivityType.TASK, wbs_uid="w1")
    hits = match_sensitive(s)          # default keywords
    assert "E100" in hits              # site / excavat / concrete
    assert "E200" in hits              # picks up "site" via WBS name "Sitework"
    # a keyword string appears in the reason
    assert any(k in hits["E100"] for k in DEFAULT_SENSITIVE_KEYWORDS)


def test_sensitive_custom_tags_match_demo_hs():
    hs2 = load(HS2)[0]
    assert match_sensitive(hs2) == {}                       # defaults miss demo_hs
    hits = match_sensitive(hs2, sensitive_tags=HS_TAGS)
    assert set(hits) == {"HA20", "HA30", "HA40"}
    # dict form with a wbs pattern is also accepted
    hits2 = match_sensitive(hs2, sensitive_tags={"keywords": ["steel"],
                                                 "wbs": ["half-step"]})
    assert "HA40" in hits2


# ---------------------------------------------------------------------------
# slippage overlay (hand-computed from the hs pair record dates)
# ---------------------------------------------------------------------------
def test_slippage_overlay_values():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    wa = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS)
    slip = {s.code: s for s in wa.windows[0].slippage}
    # HA30 Foundations: hs1 record finish 2025-04-11 (in prog) -> hs2 AF 2025-04-18
    assert slip["HA30"].finish_slip_days == 7
    assert slip["HA30"].near_critical is True              # float 6d <= 10d
    # HA40 Steel: hs1 EF 2025-04-25 -> hs2 EF 2025-05-08 = 13 calendar days
    assert slip["HA40"].finish_slip_days == 13
    assert slip["HA40"].near_critical is True
    # HA20 Groundworks finished before the window in both updates -> no slip, and
    # far off the critical path
    assert slip["HA20"].finish_slip_days == 0
    assert slip["HA20"].near_critical is False
    # only the two near-critical, slipped activities are "affected"
    affected = {s.code for s in wa.windows[0].affected}
    assert affected == {"HA30", "HA40"}


# ---------------------------------------------------------------------------
# both-ways presentation: a better-than-norm window has negative exceedance
# ---------------------------------------------------------------------------
def test_both_ways_negative_exceedance():
    rec = load_ghcn_csv(CSV)
    # a dry July window: [2025-07-07, 2025-07-28); actual 1 lost day, norm ~4.06
    early = Schedule(project_id="DRY", data_date=datetime(2025, 7, 7))
    late = Schedule(project_id="DRY", data_date=datetime(2025, 7, 28))
    wa = analyze_weather([early, late], rec)
    win = wa.windows[0]
    assert win.refused is False
    assert win.actual_lost_days == 1
    assert win.exceedance_days < 0                         # better than norm
    assert "better than norm" in win.note
    # the exhibit lists the better-than-norm window too (presented both ways)
    assert wa.exhibit_rows[0].exceedance_days < 0
    assert "both ways" in wa.preliminary.lower()


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------
def test_determinism():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    a = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS).to_dict()
    b = analyze_weather([hs1, hs2], rec, sensitive_tags=HS_TAGS).to_dict()
    import json
    assert json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# analyst-overridable thresholds
# ---------------------------------------------------------------------------
def test_thresholds_overridable():
    rec = load_ghcn_csv(CSV)
    hs1, hs2 = load(HS1)[0], load(HS2)[0]
    # raise the precipitation bar above the seeded 15mm rain days -> no rain-lost
    # days survive, so the April norm collapses to 0
    th = WeatherThresholds(prcp_lost_mm=20.0)
    wa = analyze_weather([hs1, hs2], rec, thresholds=th, sensitive_tags=HS_TAGS)
    assert wa.monthly_norm[4] == pytest.approx(0.0)
    assert wa.windows[0].actual_lost_days == 0


# ---------------------------------------------------------------------------
# ADR-0006: the module performs NO network I/O
# ---------------------------------------------------------------------------
def test_no_network_imports():
    import scheduleiq.analytics.weather as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for banned in ("import requests", "import urllib", "import http",
                   "import socket", "urlopen", "requests.get", "http.client"):
        assert banned not in src, f"weather.py must be offline (found {banned!r})"
