"""
Range-aware workday-table contract for CalendarRegistry (ADR-029 r2, Codex P1b).

The old boolean ``tables_built()`` could not prove the *current* window's range
was covered; a narrow first build could be silently reused by a wider later
window. These tests pin the range-aware contract: ``ensure_workday_tables`` is
idempotent when covered, extends to a superset when not, ``tables_cover`` is the
real gate, and a failed (re)build leaves prior coverage intact (atomic).
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.models import Calendar  # noqa: E402
from scheduleiq.cpm.calendar_registry import CalendarEntry, CalendarRegistry  # noqa: E402

_JAN = (date(2026, 1, 1), date(2026, 1, 31))
_FEB_MAR = (date(2026, 2, 1), date(2026, 3, 31))


def _reg() -> CalendarRegistry:
    r = CalendarRegistry()
    r.register(CalendarEntry(clndr_id="1",
                             calendar=Calendar(name="MF", work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)))
    r.set_default("1")
    return r


def test_ensure_builds_when_empty():
    r = _reg()
    assert not r.tables_built() and not r.tables_cover(*_JAN)
    r.ensure_workday_tables(*_JAN)
    assert r.tables_built() and r.tables_cover(*_JAN)
    assert r.table_start == _JAN[0] and r.table_end == _JAN[1]
    assert r.get_workday_table("1")  # non-empty


def test_ensure_idempotent_when_covered():
    r = _reg()
    r.ensure_workday_tables(*_JAN)
    t1 = r.get_workday_table("1")
    r.ensure_workday_tables(date(2026, 1, 10), date(2026, 1, 20))   # sub-range of Jan
    assert r.table_start == _JAN[0] and r.table_end == _JAN[1]      # range unchanged
    assert r.get_workday_table("1") is t1                          # NOT rebuilt (same object)


def test_ensure_extends_to_superset():
    r = _reg()
    r.ensure_workday_tables(*_FEB_MAR)
    r.ensure_workday_tables(*_JAN)                                  # earlier, not covered
    assert r.table_start == _JAN[0] and r.table_end == _FEB_MAR[1]  # superset [Jan, Mar]
    assert r.tables_cover(date(2026, 1, 1), date(2026, 3, 31))


def test_tables_cover_false_out_of_range():
    r = _reg()
    r.ensure_workday_tables(*_JAN)
    assert r.tables_built() is True
    assert r.tables_cover(date(2025, 12, 1), date(2025, 12, 31)) is False  # built != covered


def test_rebuild_atomic_on_failure():
    # A pure-weekend range has no Mon-Fri workdays → build raises. Prior coverage
    # must be intact (Codex: a failed build cannot leave partial state).
    r = _reg()
    r.ensure_workday_tables(*_JAN)
    t1 = r.get_workday_table("1")
    with pytest.raises(ValueError):
        r.build_workday_tables(date(2026, 1, 10), date(2026, 1, 11))   # Sat + Sun
    assert r.table_start == _JAN[0] and r.table_end == _JAN[1]         # unchanged
    assert r.get_workday_table("1") is t1                            # not clobbered


def test_ensure_validates_range():
    r = _reg()
    with pytest.raises(ValueError):
        r.ensure_workday_tables(date(2026, 2, 1), date(2026, 1, 1))    # start > end
