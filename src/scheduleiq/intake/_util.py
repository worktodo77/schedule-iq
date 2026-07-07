"""Shared helpers for the intake-accelerator pack (backlog D1-D8).

Kept private to ``scheduleiq.intake`` — not part of the public analytics
surface.  Everything here is pure and defensive: no function raises on
missing dates or calendars, matching the "never sink a run" discipline of
``analytics.paths``.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..ingest.model import Calendar

# (typical interval in days, label) — used to describe the dominant update
# cadence in plain English for the scorecard and the report.
_CADENCE_BUCKETS = [
    (7.0, "weekly"),
    (14.0, "biweekly"),
    (30.44, "monthly"),
    (60.9, "bimonthly (~2 months)"),
    (91.3, "quarterly (~3 months)"),
    (182.6, "semi-annual (~6 months)"),
    (365.25, "annual (~12 months)"),
]


def cadence_label(days: Optional[float]) -> str:
    """Plain-English label for a dominant update interval in calendar days."""
    if not days or days <= 0:
        return "irregular / insufficient data"
    best_days, best_name = min(_CADENCE_BUCKETS, key=lambda b: abs(b[0] - days))
    if abs(best_days - days) <= max(5.0, 0.2 * days):
        return f"~{days:.0f} days ({best_name})"
    return f"~{days:.0f} days (irregular)"


def working_days_between(cal: Optional[Calendar], start: Optional[datetime],
                         finish: Optional[datetime]) -> Optional[float]:
    """Signed count of working days on ``cal`` between two datetimes (positive
    when ``finish`` is later than ``start``).  Falls back to a Mon-Fri
    assumption when no calendar is available, mirroring
    ``trend.series._working_hours_between``.  Defensively capped at 10 years
    of iteration so a bad date pair can never hang a run."""
    if start is None or finish is None:
        return None
    sign = 1.0
    a, b = start, finish
    if a > b:
        a, b = b, a
        sign = -1.0
    d, end_d = a.date(), b.date()
    cap = d + timedelta(days=10 * 365)
    total = 0.0
    while d < end_d and d < cap:
        if cal is not None:
            if cal.is_workday(d):
                total += 1.0
        elif d.isoweekday() <= 5:
            total += 1.0
        d += timedelta(days=1)
    return sign * total


def band_label(days: Optional[float]) -> str:
    """Float band used to aggregate the float ledger (D3)."""
    if days is None:
        return "unknown"
    if days <= 0:
        return "critical (<=0d)"
    if days <= 5:
        return "0-5d"
    if days <= 10:
        return "5-10d"
    if days <= 20:
        return "10-20d"
    return ">20d"


MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]


def months_between(a: datetime, b: datetime) -> list[str]:
    """Calendar year-month strings ("YYYY-MM") strictly between ``a`` and
    ``b`` (exclusive of both endpoints' months)."""
    out: list[str] = []
    y, m = a.year, a.month
    m += 1
    if m > 12:
        m, y = 1, y + 1
    while (y, m) < (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def format_month_range(months: list[str]) -> str:
    """Render a "YYYY-MM" list as "May-June 2025" (or the single-month form)."""
    if not months:
        return ""
    if len(months) == 1:
        y, m = months[0].split("-")
        return f"{MONTH_NAMES[int(m)]} {y}"
    y0, m0 = months[0].split("-")
    y1, m1 = months[-1].split("-")
    if y0 == y1:
        return f"{MONTH_NAMES[int(m0)]}-{MONTH_NAMES[int(m1)]} {y0}"
    return f"{MONTH_NAMES[int(m0)]} {y0} - {MONTH_NAMES[int(m1)]} {y1}"
