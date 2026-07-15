"""Regression tests for the CPM workday-table coverage backstop."""

import os
import sys
from datetime import date

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.models import Activity, Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402


def test_run_analysis_grows_table_when_project_start_is_outside_initial_window():
    calendar = Calendar(name="Standard")
    table = build_workday_table(calendar, date(2025, 1, 10), date(2025, 1, 31))
    result = run_analysis(
        activities=[Activity("A", original_duration=1)],
        relationships=[],
        project_start=date(2025, 1, 2),
        workday_table=table,
        calendar=calendar,
    )
    assert result.is_valid
    assert date(2025, 1, 2) in table
    assert min(table) < date(2025, 1, 2)
