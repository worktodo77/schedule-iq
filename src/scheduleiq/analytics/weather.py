"""Weather & external-conditions overlay (backlog N1; ANALYTICS_PROPOSAL.md §8.1).

Excusable-delay screening from authoritative historical weather.  Given a set of
schedule updates and a downloaded station history, the module:

  (a) **Calendar realism** (§8.1a) — per calendar month spanned by the schedules,
      compare the downtime the schedule's own working calendar embeds
      (non-working weekdays + weekday exceptions) against the weather-implied
      downtime from the station's 10-year norm (days/month exceeding the
      thresholds below).  A *shortfall* is flagged wherever the weather norm
      exceeds what the calendar embeds — i.e. the calendar is more optimistic
      about the weather than the geography's own record.

  (b) **Abnormal weather per period** (§8.1b) — for each update-pair window
      (earlier.data_date -> later.data_date) compare the ACTUAL weather-lost days
      in the window against the 10-year norm for those same calendar months,
      pro-rated by the number of window days falling in each month (the usual
      contractual abnormal-weather test).  ``exceedance = actual - norm``.  The
      as-built finish slip of weather-sensitive activities over the window is
      overlaid (measured from tool-of-record dates only — no engine).

  (c) **Weather-delay exhibit** (§8.1c) — one auto-drafted table row per window:
      period, norm lost days, actual lost days, exceedance, and the affected
      weather-sensitive driving / near-critical activities.  Entitlement and
      causation are **expressly reserved to the expert** (CLAUDE.md §4): the
      exhibit is labelled PRELIMINARY, carries the tribunal-duty caption, and
      presents exceedance BOTH WAYS — windows *better* than the norm (negative
      exceedance) are listed alongside the abnormal ones.

Offline by construction (ADR-0006): the station history is read from a local
file and NOTHING in this module performs any network I/O.  The loader accepts
the GHCN-Daily "by-station" LONG CSV shape — columns ``STATION,DATE,ELEMENT,
VALUE`` (extra columns such as the M/Q/S flags are tolerated and ignored) — with
GHCN wire units: PRCP in tenths of a millimetre, TMAX/TMIN in tenths of a degree
Celsius, and SNOW in whole millimetres.  Unknown elements are ignored and
disclosed.  Missing days are tolerated: the norm is computed over the days
present with a coverage disclosure, and any requested window whose coverage
falls below ``min_coverage`` (default 60%) is refused rather than reported on
thin data.

Thresholds (analyst-overridable via :class:`WeatherThresholds`) and their
rationale:

  * ``prcp_lost_mm = 10.0`` — a day with >= 10 mm of precipitation is treated as
    a lost day for weather-sensitive outdoor work.  ~10 mm/day is a widely used
    contractual/industry trigger for a rained-out day: enough to suspend
    earthmoving, excavation dewatering, and open concrete placement.
  * ``freeze_tmax_c = 0.0`` — a day whose maximum temperature is <= 0 degC is a
    freeze day: concrete cannot be placed/cured without protection and earthworks
    are frozen.
  * ``snow_lost_mm = 25.0`` — > 25 mm of snowfall in a day halts site work.

A day meeting ANY threshold counts once (union) as a weather-lost day.
"""
from __future__ import annotations

import calendar as _calmod
import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Union

from ..ingest.model import Activity, Calendar, Schedule

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
KNOWN_ELEMENTS = ("PRCP", "TMAX", "TMIN", "SNOW")

# Default weather-sensitive keyword set (case-insensitive substring match on the
# activity name and its WBS code/name).  Documented and disclosed on every run.
DEFAULT_SENSITIVE_KEYWORDS = (
    "earthwork", "excavat", "concrete", "pav", "roof", "exterior", "site",
)

PRELIMINARY = (
    "PRELIMINARY — weather-delay screening exhibit.  Entitlement, causation, "
    "concurrency and quantum are reserved to the expert (CLAUDE.md §4).  This "
    "auto-drafted table presents exceedance BOTH WAYS: windows better than the "
    "10-year norm are listed alongside abnormal ones."
)


# ---------------------------------------------------------------------------
# thresholds
# ---------------------------------------------------------------------------
@dataclass
class WeatherThresholds:
    """Analyst-overridable thresholds and the norm/coverage knobs."""
    prcp_lost_mm: float = 10.0
    freeze_tmax_c: float = 0.0
    snow_lost_mm: float = 25.0
    near_critical_float_days: float = 10.0
    norm_years: int = 10
    min_coverage: float = 0.60

    def rationale(self) -> dict[str, str]:
        return {
            "prcp_lost_mm": (
                f">= {self.prcp_lost_mm:g} mm precipitation = a lost day for "
                "weather-sensitive outdoor work (rain-out of earthworks / "
                "excavation / open concrete placement)."),
            "freeze_tmax_c": (
                f"TMAX <= {self.freeze_tmax_c:g} degC = a freeze day (no "
                "unprotected concrete placement/cure; earthworks frozen)."),
            "snow_lost_mm": (
                f"> {self.snow_lost_mm:g} mm snowfall = a snow-lost day (site "
                "work halted)."),
            "combination": "a day meeting ANY threshold counts once (union).",
            "near_critical_float_days": (
                f"an activity is 'near-critical' when its tool-of-record total "
                f"float <= {self.near_critical_float_days:g} working days OR it "
                "carries the tool's critical flag."),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "prcp_lost_mm": self.prcp_lost_mm,
            "freeze_tmax_c": self.freeze_tmax_c,
            "snow_lost_mm": self.snow_lost_mm,
            "near_critical_float_days": self.near_critical_float_days,
            "norm_years": self.norm_years,
            "min_coverage": self.min_coverage,
        }


DEFAULT_THRESHOLDS = WeatherThresholds()


# ---------------------------------------------------------------------------
# weather record
# ---------------------------------------------------------------------------
@dataclass
class WeatherRecord:
    """A parsed station history in standard units.

    ``by_date`` maps a :class:`datetime.date` to ``{element: value}`` where
    PRCP/SNOW are in millimetres and TMAX/TMIN in degrees Celsius.
    """
    station: str = ""
    by_date: dict[date, dict[str, float]] = field(default_factory=dict)
    elements_seen: set[str] = field(default_factory=set)
    unknown_elements: set[str] = field(default_factory=set)
    start: Optional[date] = None
    end: Optional[date] = None
    source_file: str = ""
    disclosures: list[str] = field(default_factory=list)

    # -- lost-day classification ----------------------------------------
    def lost_reasons(self, d: date, th: WeatherThresholds) -> list[str]:
        vals = self.by_date.get(d)
        if not vals:
            return []
        reasons = []
        prcp = vals.get("PRCP")
        tmax = vals.get("TMAX")
        snow = vals.get("SNOW")
        if prcp is not None and prcp >= th.prcp_lost_mm:
            reasons.append(f"PRCP {prcp:g}mm >= {th.prcp_lost_mm:g}mm")
        if tmax is not None and tmax <= th.freeze_tmax_c:
            reasons.append(f"TMAX {tmax:g}C <= {th.freeze_tmax_c:g}C")
        if snow is not None and snow > th.snow_lost_mm:
            reasons.append(f"SNOW {snow:g}mm > {th.snow_lost_mm:g}mm")
        return reasons

    def is_lost_day(self, d: date, th: WeatherThresholds) -> bool:
        return bool(self.lost_reasons(d, th))

    def coverage(self, start: date, end: date) -> float:
        """Fraction of the half-open day range [start, end) present in the
        record (>= 1 observation).  Empty range -> 0.0."""
        total = (end - start).days
        if total <= 0:
            return 0.0
        present = sum(1 for i in range(total)
                      if (start + _days(i)) in self.by_date)
        return present / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "station": self.station,
            "days": len(self.by_date),
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "elements_seen": sorted(self.elements_seen),
            "unknown_elements_ignored": sorted(self.unknown_elements),
            "disclosures": list(self.disclosures),
        }


def _days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _norm_key(k: str) -> str:
    return (k or "").strip().lstrip("﻿").upper()


def load_ghcn_csv(path: str) -> WeatherRecord:
    """Load a GHCN-Daily by-station LONG CSV (``STATION,DATE,ELEMENT,VALUE``).

    Extra columns are tolerated and ignored.  Wire units are converted to
    standard units (PRCP/SNOW mm, TMAX/TMIN degC).  Unknown elements are ignored
    and recorded in ``unknown_elements``.  Raises ``ValueError`` if no usable
    observations are found.
    """
    rec = WeatherRecord(source_file=path)
    n_rows = 0
    n_used = 0
    stations: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path}: empty weather CSV")
        cols = {_norm_key(h): i for i, h in enumerate(header)}
        for req in ("DATE", "ELEMENT", "VALUE"):
            if req not in cols:
                raise ValueError(
                    f"{path}: GHCN by-station CSV must have STATION,DATE,ELEMENT,"
                    f"VALUE columns (missing {req})")
        i_station = cols.get("STATION")
        i_date, i_el, i_val = cols["DATE"], cols["ELEMENT"], cols["VALUE"]
        for row in reader:
            if not row or len(row) <= i_val:
                continue
            n_rows += 1
            if i_station is not None and i_station < len(row):
                st = row[i_station].strip()
                if st:
                    stations.add(st)
            d = _parse_date(row[i_date])
            el = _norm_key(row[i_el])
            raw = (row[i_val] or "").strip()
            if d is None or not el or raw == "":
                continue
            rec.elements_seen.add(el)
            try:
                v = float(raw)
            except ValueError:
                continue
            if el not in KNOWN_ELEMENTS:
                rec.unknown_elements.add(el)
                continue
            if el in ("PRCP",):
                v = v / 10.0            # tenths mm -> mm
            elif el in ("TMAX", "TMIN"):
                v = v / 10.0            # tenths degC -> degC
            # SNOW is already whole mm
            rec.by_date.setdefault(d, {})[el] = v
            n_used += 1

    if not rec.by_date:
        raise ValueError(f"{path}: no usable PRCP/TMAX/TMIN/SNOW observations")
    rec.station = sorted(stations)[0] if stations else ""
    rec.start = min(rec.by_date)
    rec.end = max(rec.by_date)
    rec.disclosures.append(
        f"parsed {n_used} observations across {len(rec.by_date)} days "
        f"({rec.start.isoformat()}..{rec.end.isoformat()}); GHCN units converted "
        "(PRCP/SNOW mm, TMAX/TMIN degC).")
    if rec.unknown_elements:
        rec.disclosures.append(
            "unknown elements ignored: " + ", ".join(sorted(rec.unknown_elements)))
    return rec


# ---------------------------------------------------------------------------
# sensitive-activity matching
# ---------------------------------------------------------------------------
def _normalize_tags(sensitive_tags: Optional[Union[dict, list]]
                    ) -> tuple[list[str], list[str]]:
    """Return (keywords, wbs_patterns) from the flexible ``sensitive_tags`` arg.

    ``None`` -> the default keyword set.  A list -> keyword list.  A dict ->
    ``{"keywords": [...], "wbs": [...]}`` (either key optional).
    """
    if sensitive_tags is None:
        return list(DEFAULT_SENSITIVE_KEYWORDS), []
    if isinstance(sensitive_tags, dict):
        kw = [str(k).lower() for k in sensitive_tags.get("keywords", []) if str(k).strip()]
        wbs = [str(w).lower() for w in sensitive_tags.get("wbs", []) if str(w).strip()]
        return kw, wbs
    return [str(k).lower() for k in sensitive_tags if str(k).strip()], []


def match_sensitive(schedule: Schedule,
                    sensitive_tags: Optional[Union[dict, list]] = None
                    ) -> dict[str, str]:
    """Return ``{activity_code: reason}`` for weather-sensitive activities.

    Matching is case-insensitive substring on the activity name and its WBS
    code/name (keywords), and on the WBS code/name (wbs patterns).  Deterministic.
    """
    keywords, wbs_patterns = _normalize_tags(sensitive_tags)
    out: dict[str, str] = {}
    for a in schedule.real_activities:
        wbs = schedule.wbs.get(a.wbs_uid)
        wbs_text = f"{wbs.code} {wbs.name}".lower() if wbs else ""
        name_hay = f"{a.name} {wbs_text}".lower()
        hits = [k for k in keywords if k in name_hay]
        wbs_hits = [w for w in wbs_patterns if w in wbs_text]
        reasons = []
        if hits:
            reasons.append("keyword: " + ", ".join(hits))
        if wbs_hits:
            reasons.append("wbs: " + ", ".join(wbs_hits))
        if reasons:
            out[a.code] = "; ".join(reasons)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class MonthRealism:
    year: int
    month: int
    total_weekdays: int
    embedded_downtime_days: int
    norm_lost_days: float
    shortfall_days: float
    flagged: bool

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.label,
            "total_weekdays": self.total_weekdays,
            "calendar_embedded_downtime_days": self.embedded_downtime_days,
            "weather_norm_lost_days": round(self.norm_lost_days, 3),
            "shortfall_days": round(self.shortfall_days, 3),
            "shortfall_flagged": self.flagged,
        }


@dataclass
class SlippageRow:
    code: str
    name: str
    reason: str
    earlier_finish: Optional[date]
    later_finish: Optional[date]
    finish_slip_days: Optional[int]
    total_float_days: Optional[float]
    near_critical: bool
    near_critical_basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "sensitivity": self.reason,
            "earlier_record_finish": self.earlier_finish.isoformat() if self.earlier_finish else None,
            "later_record_finish": self.later_finish.isoformat() if self.later_finish else None,
            "finish_slip_calendar_days": self.finish_slip_days,
            "total_float_days": (round(self.total_float_days, 2)
                                 if self.total_float_days is not None else None),
            "near_critical": self.near_critical,
            "near_critical_basis": self.near_critical_basis,
        }


@dataclass
class WindowWeather:
    label: str
    start: date
    end: date
    coverage: float
    refused: bool = False
    reason: str = ""
    norm_lost_days: Optional[float] = None
    actual_lost_days: Optional[int] = None
    exceedance_days: Optional[float] = None
    sensitive_population: list[str] = field(default_factory=list)
    slippage: list[SlippageRow] = field(default_factory=list)
    note: str = ""

    @property
    def affected(self) -> list[SlippageRow]:
        """Near-critical weather-sensitive activities that slipped in the window."""
        return [s for s in self.slippage
                if s.near_critical and (s.finish_slip_days or 0) > 0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.label,
            "window_start": self.start.isoformat(),
            "window_end_exclusive": self.end.isoformat(),
            "coverage_pct": round(100.0 * self.coverage, 1),
            "refused": self.refused,
            "reason": self.reason,
            "norm_lost_days": (round(self.norm_lost_days, 3)
                               if self.norm_lost_days is not None else None),
            "actual_lost_days": self.actual_lost_days,
            "exceedance_days": (round(self.exceedance_days, 3)
                                if self.exceedance_days is not None else None),
            "weather_sensitive_population": list(self.sensitive_population),
            "sensitive_slippage": [s.to_dict() for s in self.slippage],
            "affected_near_critical": [s.to_dict() for s in self.affected],
            "observational_note": self.note,
        }


@dataclass
class ExhibitRow:
    period: str
    norm_lost_days: Optional[float]
    actual_lost_days: Optional[int]
    exceedance_days: Optional[float]
    affected_activities: list[dict[str, Any]]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "norm_lost_days": (round(self.norm_lost_days, 3)
                               if self.norm_lost_days is not None else None),
            "actual_lost_days": self.actual_lost_days,
            "exceedance_days": (round(self.exceedance_days, 3)
                                if self.exceedance_days is not None else None),
            "affected_weather_sensitive_activities": self.affected_activities,
            "observational_note": self.note,
        }


@dataclass
class WeatherAnalysis:
    station: str = ""
    reference_year: Optional[int] = None
    norm_years: list[int] = field(default_factory=list)
    thresholds: WeatherThresholds = field(default_factory=WeatherThresholds)
    monthly_norm: dict[int, float] = field(default_factory=dict)
    calendar_realism: list[MonthRealism] = field(default_factory=list)
    windows: list[WindowWeather] = field(default_factory=list)
    exhibit_rows: list[ExhibitRow] = field(default_factory=list)
    sensitive_keywords: list[str] = field(default_factory=list)
    primary_calendar: str = ""
    disclosures: list[str] = field(default_factory=list)
    preliminary: str = PRELIMINARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "preliminary": self.preliminary,
            "tribunal_duty": (
                "Findings are evidence-based; abnormal-weather entitlement is "
                "reserved to the expert and presented both ways."),
            "station": self.station,
            "reference_year": self.reference_year,
            "norm_years": list(self.norm_years),
            "thresholds": self.thresholds.to_dict(),
            "threshold_rationale": self.thresholds.rationale(),
            "primary_calendar": self.primary_calendar,
            "weather_sensitive_keywords": list(self.sensitive_keywords),
            "monthly_norm_lost_days": {f"{m:02d}": round(self.monthly_norm[m], 3)
                                       for m in sorted(self.monthly_norm)},
            "calendar_realism": [m.to_dict() for m in self.calendar_realism],
            "windows": [w.to_dict() for w in self.windows],
            "weather_delay_exhibit": [r.to_dict() for r in self.exhibit_rows],
            "disclosures": list(self.disclosures),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _record_finish(a: Activity) -> Optional[datetime]:
    return a.actual_finish or a.early_finish or a.planned_finish


def _record_start(a: Activity) -> Optional[datetime]:
    return a.actual_start or a.early_start or a.planned_start


def _float_days(sched: Schedule, a: Activity) -> Optional[float]:
    cal = sched.cal_for(a)
    return a.total_float_days(cal)


def _is_near_critical(sched: Schedule, a: Activity, th: WeatherThresholds) -> bool:
    if a.is_critical_flag:
        return True
    fd = _float_days(sched, a)
    return fd is not None and fd <= th.near_critical_float_days


def _primary_calendar(sched: Schedule) -> Optional[Calendar]:
    for c in sched.calendars.values():
        if c.is_default:
            return c
    counts: dict[str, list] = {}
    for a in sched.real_activities:
        c = sched.cal_for(a)
        if c:
            counts.setdefault(c.uid, [c, 0])
            counts[c.uid][1] += 1
    if counts:
        return max(counts.values(), key=lambda t: t[1])[0]
    return next(iter(sched.calendars.values()), None)


def _monthly_norm(rec: WeatherRecord, norm_years: list[int], th: WeatherThresholds
                  ) -> tuple[dict[int, float], dict[int, float]]:
    """Return (norm_month, coverage_month).  ``norm_month[m]`` = mean over the
    norm years of the count of weather-lost days in calendar month ``m``;
    computed over the days present (coverage disclosed)."""
    per_year_counts: dict[int, list[int]] = {m: [] for m in range(1, 13)}
    per_year_cover: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for y in norm_years:
        for m in range(1, 13):
            ndays = _calmod.monthrange(y, m)[1]
            present = 0
            lost = 0
            for dom in range(1, ndays + 1):
                d = date(y, m, dom)
                if d in rec.by_date:
                    present += 1
                    if rec.is_lost_day(d, th):
                        lost += 1
            if present:
                per_year_counts[m].append(lost)
                per_year_cover[m].append(present / ndays)
    norm_month: dict[int, float] = {}
    cover_month: dict[int, float] = {}
    for m in range(1, 13):
        cs = per_year_counts[m]
        norm_month[m] = (sum(cs) / len(cs)) if cs else 0.0
        cv = per_year_cover[m]
        cover_month[m] = (sum(cv) / len(cv)) if cv else 0.0
    return norm_month, cover_month


def _window_norm(norm_month: dict[int, float], start: date, end: date) -> float:
    """Pro-rate the monthly norm by the number of window days [start, end) that
    fall in each calendar month."""
    counts: dict[tuple[int, int], int] = {}
    total = (end - start).days
    for i in range(total):
        d = start + _days(i)
        counts[(d.year, d.month)] = counts.get((d.year, d.month), 0) + 1
    norm = 0.0
    for (y, m), n in counts.items():
        dim = _calmod.monthrange(y, m)[1]
        norm += norm_month.get(m, 0.0) * n / dim
    return norm


def _spanned_months(schedules: list[Schedule]) -> list[tuple[int, int]]:
    lo = hi = None
    for s in schedules:
        for a in s.real_activities:
            rs, rf = _record_start(a), _record_finish(a)
            for dt_ in (rs, rf):
                if dt_ is None:
                    continue
                d = dt_.date()
                lo = d if lo is None or d < lo else lo
                hi = d if hi is None or d > hi else hi
        if s.data_date:
            d = s.data_date.date()
            lo = d if lo is None or d < lo else lo
            hi = d if hi is None or d > hi else hi
    if lo is None or hi is None:
        return []
    months: list[tuple[int, int]] = []
    y, m = lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _embedded_downtime(cal: Optional[Calendar], y: int, m: int) -> tuple[int, int]:
    """(embedded_downtime_days, total_weekdays) for calendar month (y, m).

    Embedded downtime = weekdays (Mon-Fri) the calendar marks non-working
    (its non-work weekday pattern + weekday holiday exceptions)."""
    ndays = _calmod.monthrange(y, m)[1]
    total_wd = 0
    down = 0
    for dom in range(1, ndays + 1):
        d = date(y, m, dom)
        if d.isoweekday() <= 5:
            total_wd += 1
            if cal is not None and not cal.is_workday(d):
                down += 1
    return down, total_wd


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def analyze_weather(schedules: list[Schedule], weather: WeatherRecord, *,
                    thresholds: WeatherThresholds = DEFAULT_THRESHOLDS,
                    sensitive_tags: Optional[Union[dict, list]] = None
                    ) -> WeatherAnalysis:
    """Run the weather overlay (§8.1a-c) over an ordered set of schedule updates."""
    th = thresholds
    out = WeatherAnalysis(station=weather.station, thresholds=th)
    keywords, wbs_patterns = _normalize_tags(sensitive_tags)
    out.sensitive_keywords = keywords + [f"wbs:{w}" for w in wbs_patterns]
    out.disclosures.extend(weather.disclosures)

    scheds = sorted([s for s in schedules if s.data_date is not None],
                    key=lambda s: s.data_date)
    if not scheds:
        out.disclosures.append("no schedules with data dates; nothing to analyze")
        return out

    ref_year = max(s.data_date.year for s in scheds)
    out.reference_year = ref_year
    wanted = list(range(ref_year - th.norm_years, ref_year))
    present_years = {d.year for d in weather.by_date}
    norm_years = [y for y in wanted if y in present_years]
    out.norm_years = norm_years
    if len(norm_years) < th.norm_years:
        out.disclosures.append(
            f"norm computed over {len(norm_years)} of {th.norm_years} requested "
            f"years ({wanted[0]}..{wanted[-1]}); available: "
            f"{norm_years[0] if norm_years else '—'}..{norm_years[-1] if norm_years else '—'}.")

    norm_month, cover_month = _monthly_norm(weather, norm_years, th)
    out.monthly_norm = norm_month
    thin = [f"{m:02d}={cover_month[m]:.0%}" for m in range(1, 13)
            if norm_years and cover_month[m] < th.min_coverage]
    if thin:
        out.disclosures.append("norm months below coverage floor: " + ", ".join(thin))

    # -- primary calendar (latest schedule) -----------------------------------
    latest = scheds[-1]
    cal = _primary_calendar(latest)
    out.primary_calendar = (cal.name or cal.uid) if cal else ""

    # -- (a) calendar realism -------------------------------------------------
    for (y, m) in _spanned_months(scheds):
        down, total_wd = _embedded_downtime(cal, y, m)
        norm = norm_month.get(m, 0.0)
        shortfall = norm - down
        out.calendar_realism.append(MonthRealism(
            year=y, month=m, total_weekdays=total_wd,
            embedded_downtime_days=down, norm_lost_days=norm,
            shortfall_days=max(0.0, shortfall), flagged=shortfall > 1e-9))

    # -- (b) abnormal weather per update-pair window --------------------------
    for earlier, later in zip(scheds, scheds[1:]):
        start = earlier.data_date.date()
        end = later.data_date.date()
        label = f"{start.isoformat()} → {end.isoformat()}"
        if end <= start:
            out.windows.append(WindowWeather(
                label=label, start=start, end=end, coverage=0.0, refused=True,
                reason="non-positive window (later data date not after earlier)"))
            continue
        cov = weather.coverage(start, end)
        w = WindowWeather(label=label, start=start, end=end, coverage=cov)
        if cov < th.min_coverage:
            w.refused = True
            w.reason = (f"window coverage {cov:.0%} < {th.min_coverage:.0%} floor; "
                        "refusing to report abnormal weather on thin data")
            out.windows.append(w)
            continue
        actual = sum(1 for i in range((end - start).days)
                     if weather.is_lost_day(start + _days(i), th))
        norm = _window_norm(norm_month, start, end)
        w.actual_lost_days = actual
        w.norm_lost_days = norm
        w.exceedance_days = actual - norm

        # slippage overlay of weather-sensitive activities present in both updates
        sens_e = match_sensitive(earlier, sensitive_tags)
        sens_l = match_sensitive(later, sensitive_tags)
        w.sensitive_population = sorted(set(sens_e) | set(sens_l))
        code_to_act_e = {a.code: a for a in earlier.real_activities}
        code_to_act_l = {a.code: a for a in later.real_activities}
        for code in sorted(set(sens_e) & set(sens_l)):
            ae, al = code_to_act_e.get(code), code_to_act_l.get(code)
            if ae is None or al is None:
                continue
            ef, lf = _record_finish(ae), _record_finish(al)
            slip = (lf.date() - ef.date()).days if (ef and lf) else None
            fd = _float_days(later, al)
            basis = ("critical flag" if al.is_critical_flag
                     else f"record float ≤ {th.near_critical_float_days:g}d")
            w.slippage.append(SlippageRow(
                code=code, name=al.name, reason=sens_l.get(code, sens_e.get(code, "")),
                earlier_finish=ef.date() if ef else None,
                later_finish=lf.date() if lf else None,
                finish_slip_days=slip, total_float_days=fd,
                near_critical=_is_near_critical(later, al, th),
                near_critical_basis=basis))

        direction = ("abnormal (actual exceeds norm)" if w.exceedance_days > 1e-9
                     else "better than norm" if w.exceedance_days < -1e-9
                     else "at norm")
        w.note = (f"{actual} actual weather-lost day(s) vs {norm:.2f} norm "
                  f"({direction}); {len(w.affected)} near-critical weather-sensitive "
                  "activit(y/ies) slipped in-window.  Entitlement reserved to the expert.")
        out.windows.append(w)

    # -- (c) weather-delay exhibit (both ways) --------------------------------
    for w in out.windows:
        if w.refused:
            out.exhibit_rows.append(ExhibitRow(
                period=w.label, norm_lost_days=None, actual_lost_days=None,
                exceedance_days=None, affected_activities=[],
                note=f"REFUSED — {w.reason}"))
            continue
        affected = [{
            "code": s.code, "name": s.name,
            "finish_slip_calendar_days": s.finish_slip_days,
            "total_float_days": (round(s.total_float_days, 2)
                                 if s.total_float_days is not None else None),
            "basis": s.near_critical_basis,
        } for s in w.affected]
        out.exhibit_rows.append(ExhibitRow(
            period=w.label, norm_lost_days=w.norm_lost_days,
            actual_lost_days=w.actual_lost_days, exceedance_days=w.exceedance_days,
            affected_activities=affected, note=w.note))

    return out
