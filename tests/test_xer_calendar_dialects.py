"""Regression for P6 finish-first overnight calendar spans."""

import os
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest.model import Calendar  # noqa: E402
from scheduleiq.ingest.xer import parse_calendar_data  # noqa: E402


def test_finish_first_overnight_span_is_not_silently_dropped():
    calendar = Calendar(uid="6205", name="7x24", hours_per_day=22.0)
    blob = (
        "(0||CalendarData()((0||DaysOfWeek()((0||1()((0||0("
        "f|12:00|s|01:00)())(0||1(f|00:00|s|13:00)()))))"
        "(0||Exceptions()())))"
    )
    parse_calendar_data(blob, calendar)
    assert calendar.work_patterns[7].spans == [
        ("01:00", "12:00"),
        ("13:00", "00:00"),
    ]
    assert calendar.work_patterns[7].hours == 22.0
