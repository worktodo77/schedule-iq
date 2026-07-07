"""
The shared window/run calendar-resource helper (ADR-029 r2 Slice A, stage 2).

`build_calendar_resources` is the single normal path for building a window's
default workday table + (when present) ensuring the multi-calendar registry's
per-calendar tables cover the run range. Stage 2 is purely additive: with the
default still single-calendar (registry None) the helper is a verified no-op,
byte-identical to today's build_workday_table; the registry path is additive and
only activates as consumers migrate (Stage 4) + the default flips (Stage 5).
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import types
from datetime import date

import pytest

from scheduleiq.cpm.models import Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.calendar_registry import CalendarEntry, CalendarRegistry  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_calendar_resources   # canonical home (re-exported by engine_runner)  # noqa: E402

_LO, _HI = date(2026, 1, 1), date(2026, 3, 31)
_MF = Calendar(name="MF", work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)


def test_registry_none_is_identical_to_build_workday_table():
    # The no-op proof: a source with no registry returns exactly today's table.
    src = types.SimpleNamespace(calendar=_MF)            # no calendar_registry attr at all
    table, reg = build_calendar_resources(src, _LO, _HI)
    assert reg is None
    assert table == build_workday_table(_MF, _LO, _HI)


def test_registry_none_when_attr_is_none():
    src = types.SimpleNamespace(calendar=_MF, calendar_registry=None)
    table, reg = build_calendar_resources(src, _LO, _HI)
    assert reg is None and table == build_workday_table(_MF, _LO, _HI)


def test_bare_calendar_form():
    # Sites that hold only a Calendar pass source=None + calendar=...
    table, reg = build_calendar_resources(None, _LO, _HI, calendar=_MF)
    assert reg is None and table == build_workday_table(_MF, _LO, _HI)


def test_requires_source_or_calendar():
    with pytest.raises(ValueError):
        build_calendar_resources(None, _LO, _HI)


def test_registry_present_ensures_coverage():
    reg = CalendarRegistry()
    reg.register(CalendarEntry(clndr_id="1", calendar=_MF))
    reg.set_default("1")
    src = types.SimpleNamespace(calendar=_MF, calendar_registry=reg)
    assert not reg.tables_cover(_LO, _HI)                # not built yet
    table, out_reg = build_calendar_resources(src, _LO, _HI)
    assert out_reg is reg
    assert reg.tables_cover(_LO, _HI)                    # helper ensured per-calendar tables
    assert reg.get_workday_table("1")                    # the per-calendar table exists
    assert table == build_workday_table(_MF, _LO, _HI)   # default table unchanged


def test_registry_extends_for_wider_window():
    reg = CalendarRegistry()
    reg.register(CalendarEntry(clndr_id="1", calendar=_MF))
    src = types.SimpleNamespace(calendar=_MF, calendar_registry=reg)
    build_calendar_resources(src, date(2026, 2, 1), date(2026, 2, 28))   # narrow first
    build_calendar_resources(src, _LO, _HI)                              # wider later
    assert reg.tables_cover(_LO, _HI)
    assert reg.table_start == _LO and reg.table_end == _HI               # superset, not too-narrow reuse
