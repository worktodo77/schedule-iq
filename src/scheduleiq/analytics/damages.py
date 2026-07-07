"""Damages / exposure overlay (backlog S7; ANALYTICS_PROPOSAL.md §6.6).

Translates any P-date or diagnostic delta already computed elsewhere in the
engine into money, using two independent, analyst-supplied rates:

* ``time_cost_per_day`` — an extended time-related-cost rate that applies to
  ANY schedule delta (a waterfall bar, a half-step progress/revision split, a
  daily-ledger cumulative, a robustness-certificate range, an SRA percentile
  offset).  Priced by :func:`exposure_for_delta`.  Always computable once a
  rate is entered; the sign of the delta is preserved (a delta that moves the
  target EARLIER prices as a negative — an avoided-cost read, not a finding).
* ``ld_rate_per_day`` — a liquidated-damages rate that only prices the portion
  of a completion DATE beyond ``contractual_completion``.  Priced by
  :func:`exposure_for_date`.  Disabled (returns a non-computable
  :class:`ExposureLine`) until BOTH a rate and a contractual completion date
  are configured.  LD is priced on a CALENDAR-day convention regardless of
  ``daily_basis`` — LD clauses are almost always calendar days by their own
  drafting, so that convention is fixed rather than left to the config
  (documented here, not hidden).

STANDING LABEL (``STANDING_LABEL`` — every consuming report/figure carries it
verbatim, once per sheet/figure, per CLAUDE.md §4 / §6.6):
    "EXPOSURE ARITHMETIC ONLY — quantum, causation, and entitlement are
    reserved to the expert; rates are analyst inputs, not findings."

This module performs literal arithmetic ONLY.  It never infers a rate, never
guesses a contractual date, and never silently converts between calendar and
workday bases on the caller's behalf: ``daily_basis`` documents what basis the
analyst's own rate is denominated in; ``exposure_for_delta``'s ``basis_note``
documents what basis the delta being priced actually is (the caller — a
report module — knows this; a waterfall's ``delta_workdays`` is workdays, its
``delta_calendar_days`` is calendar days).  A mismatch between the two is
flagged in ``ExposureLine.basis``, never reconciled: the formula shown is
always exactly ``delta_days x rate``, nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional, Union

import yaml

STANDING_LABEL = ("EXPOSURE ARITHMETIC ONLY — quantum, causation, and "
                  "entitlement are reserved to the expert; rates are analyst "
                  "inputs, not findings.")

_VALID_BASES = ("calendar", "workday")

_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "CAD": "$", "AUD": "$"}

_BASIS_ABBR = {"calendar": "cd", "workday": "wd"}


def _parse_date(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v).split("T")[0]).date()


def _fmt_money(amount: float, currency: str) -> str:
    sign = "-" if amount < 0 else ""
    sym = _SYMBOLS.get(currency)
    if sym:
        return f"{sign}{sym}{abs(amount):,.0f}"
    return f"{sign}{currency} {abs(amount):,.0f}"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class DamagesConfig:
    """Analyst-supplied exposure inputs.  Every field is an ANALYST INPUT, not
    a finding — nothing here is derived from the schedule.

    ld_rate_per_day        liquidated-damages rate, currency/day beyond
                            ``contractual_completion``.  None disables LD math.
    contractual_completion date (or ISO string) the contract measures lateness
                            against.  None disables LD math (default: None).
    time_cost_per_day      extended time-related-cost rate, currency/day,
                            applies to any delay/advance delta.  None disables
                            time-cost math.
    currency                ISO-ish currency code, default "USD".
    daily_basis             "calendar" | "workday", default "calendar" — LD
                            clauses are almost always calendar days; this
                            documents the basis the analyst's OWN rates are
                            denominated in (used to pick which delta field a
                            report sheet feeds to exposure_for_delta; LD
                            itself always prices in calendar days regardless
                            of this setting — see module docstring).
    """
    ld_rate_per_day: Optional[float] = None
    contractual_completion: Optional[date] = None
    time_cost_per_day: Optional[float] = None
    currency: str = "USD"
    daily_basis: str = "calendar"

    def __post_init__(self) -> None:
        if self.daily_basis not in _VALID_BASES:
            raise ValueError(
                f"daily_basis must be one of {_VALID_BASES}, got {self.daily_basis!r}")
        if self.contractual_completion is not None:
            self.contractual_completion = _parse_date(self.contractual_completion)
        if self.ld_rate_per_day is not None:
            self.ld_rate_per_day = float(self.ld_rate_per_day)
        if self.time_cost_per_day is not None:
            self.time_cost_per_day = float(self.time_cost_per_day)

    @property
    def ld_enabled(self) -> bool:
        return self.ld_rate_per_day is not None and self.contractual_completion is not None

    @property
    def basis_abbr(self) -> str:
        return _BASIS_ABBR[self.daily_basis]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ld_rate_per_day": self.ld_rate_per_day,
            "contractual_completion": (self.contractual_completion.isoformat()
                                       if self.contractual_completion else None),
            "time_cost_per_day": self.time_cost_per_day,
            "currency": self.currency,
            "daily_basis": self.daily_basis,
            "ld_enabled": self.ld_enabled,
            "label": STANDING_LABEL,
        }


_KNOWN_KEYS = {"ld_rate_per_day", "contractual_completion", "time_cost_per_day",
              "currency", "daily_basis"}


def load_damages_config(source: Union[str, dict, "DamagesConfig", None]
                        ) -> Optional[DamagesConfig]:
    """Build a :class:`DamagesConfig` from a dict, a YAML file path, or an
    existing config (returned unchanged).  A falsy ``source`` (``None``, ``""``)
    returns ``None`` — no damages overlay this run, which every consuming
    surface treats as "changes nothing"."""
    if not source:
        return None
    if isinstance(source, DamagesConfig):
        return source
    if isinstance(source, dict):
        data = dict(source)
    elif isinstance(source, str):
        with open(source, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        raise TypeError(
            f"load_damages_config expects a dict, YAML path, or DamagesConfig; got {type(source)!r}")
    extra = set(data) - _KNOWN_KEYS
    if extra:
        raise ValueError(f"unknown damages config key(s): {sorted(extra)}")
    return DamagesConfig(**data)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
@dataclass
class ExposureLine:
    """One priced exposure line.  ``amount`` is ``None`` when not computable
    (rate/date missing) — never fabricated, never defaulted to zero.  The
    formula is ALWAYS shown in ``formula_text`` (e.g.
    ``"14 cd × $25,000/cd = $350,000"``) so the arithmetic is visible without
    cross-referencing the config.  ``label`` carries the standing disclaimer
    on every line so it survives being lifted out of context (a single cell
    copy-pasted into a settlement deck, for instance)."""
    amount: Optional[float]
    formula_text: str
    basis: str
    label: str = STANDING_LABEL

    def to_dict(self) -> dict[str, Any]:
        return {"amount": self.amount, "formula_text": self.formula_text,
                "basis": self.basis, "label": self.label}


def _basis_abbr_for_note(basis_note: Optional[str], config: DamagesConfig) -> str:
    note = (basis_note or "").lower()
    if "work" in note:
        return "wd"
    if "cal" in note:
        return "cd"
    return config.basis_abbr


# ---------------------------------------------------------------------------
# Pricing functions
# ---------------------------------------------------------------------------
def exposure_for_delta(delta_days: Optional[float], config: Optional[DamagesConfig],
                       basis_note: Optional[str] = None) -> ExposureLine:
    """Price a schedule DELTA (a waterfall bar, a half-step progress/revision
    effect, a daily-ledger cumulative, a robustness-certificate range, an SRA
    percentile-vs-deterministic offset) against ``config.time_cost_per_day``.

    ``delta_days`` is taken LITERALLY — this function performs no unit
    conversion.  ``basis_note`` documents what basis ``delta_days`` is
    actually expressed in (e.g. ``"workdays (target calendar)"`` or
    ``"calendar days"``); it is echoed into ``ExposureLine.basis`` and, when it
    disagrees with ``config.daily_basis``, that disagreement is flagged in the
    same string rather than silently reconciled.

    Sign is preserved: a delta that moves the target EARLIER (negative) prices
    as a negative amount — an avoided-cost read, not a finding.
    """
    if config is None or config.time_cost_per_day is None:
        return ExposureLine(
            amount=None,
            formula_text="not computable — no time_cost_per_day rate configured",
            basis=basis_note or (config.daily_basis if config else "—"))
    if delta_days is None:
        return ExposureLine(
            amount=None, formula_text="not computable — no delta to price",
            basis=basis_note or config.daily_basis)

    abbr = _basis_abbr_for_note(basis_note, config)
    rate = config.time_cost_per_day
    amount = float(delta_days) * rate
    formula = (f"{delta_days:g} {abbr} × {_fmt_money(rate, config.currency)}/{abbr} "
              f"= {_fmt_money(amount, config.currency)}")
    basis_txt = basis_note or f"{config.daily_basis} days (config default)"
    if abbr != config.basis_abbr:
        basis_txt += (f"; NOTE: delta basis ({abbr}) differs from the "
                      f"configured daily_basis ({config.daily_basis}) — rate "
                      f"applied literally to the {abbr} figure, no conversion "
                      f"performed")
    return ExposureLine(amount=amount, formula_text=formula, basis=basis_txt)


def exposure_for_date(target_date: Any, config: Optional[DamagesConfig]) -> ExposureLine:
    """Price a completion DATE (a P-date, an engine/record finish) as
    liquidated damages: calendar days beyond ``config.contractual_completion``
    (LD clauses are almost always calendar days, regardless of
    ``daily_basis``), times ``config.ld_rate_per_day``.  Clamped at zero — LD
    prices lateness, never an early-finish credit.  Disabled (a non-computable
    line) unless BOTH a rate and a contractual completion date are configured
    (``config.ld_enabled``)."""
    if config is None or not config.ld_enabled:
        if config is None or config.ld_rate_per_day is None:
            reason = "no ld_rate_per_day configured"
        else:
            reason = "no contractual_completion date configured"
        return ExposureLine(amount=None, formula_text=f"not computable — {reason}",
                            basis="calendar days beyond contractual completion (LD)")

    d = _parse_date(target_date)
    if d is None:
        return ExposureLine(amount=None, formula_text="not computable — no date to price",
                            basis="calendar days beyond contractual completion (LD)")

    days_late = (d - config.contractual_completion).days
    priced_days = max(days_late, 0)
    rate = config.ld_rate_per_day
    amount = priced_days * rate
    formula = (f"{priced_days} cd × {_fmt_money(rate, config.currency)}/cd "
              f"= {_fmt_money(amount, config.currency)}")
    if days_late < 0:
        formula += (f"  (date is {abs(days_late)} cd AHEAD of contractual "
                    f"completion {config.contractual_completion.isoformat()} — no LD)")
    basis = (f"calendar days beyond contractual completion "
            f"{config.contractual_completion.isoformat()} (LD clause convention, "
            f"fixed regardless of daily_basis)")
    return ExposureLine(amount=amount, formula_text=formula, basis=basis)
