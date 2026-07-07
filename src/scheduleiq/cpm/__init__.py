"""
Ported from the LI MIP 3.9 tool (mip39.__init__) per ADR-0007 — port-and-validate.

Public API surface for the ScheduleIQ CPM engine core (W1a port). This mirrors
the mip39 package `__init__.py`, restricted to the modules ported in this
wave: models, conventions, warnings, context, results, longest_path, engine,
calendar_registry, network, calendar_ops, lag_analysis, relationship_logic,
validation.

Not ported in this wave (see docs/adr/ADR-0007 and the engine.py module
docstring for the severed hooks): normalization, simulation, destatusing
(destatusing is ported separately, in parallel), xer, comparison,
forward_pass, constraints, calculation_registry, validation_framework,
windows.
"""

from .context import (
    AnalysisContext,
    CalculationMode,
    ENGINE_VERSION,
    ScheduleMetadata,
)
from .validation import (
    NetworkValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from .warnings import AnalysisWarning, WarningCategory, WarningLog
from .conventions import EFConvention, fs_forward_offset
from .models import Activity, Calendar, Relationship
from .network import ActivityNetwork, topological_sort
from .calendar_ops import build_workday_table
from .calendar_registry import (
    CalendarEntry,
    CalendarRegistry,
    LagCalendarStrategy,
)
from .lag_analysis import apply_lag, compute_lag_between, lag_variance
from .relationship_logic import compute_relationship_constraint
from .results import AnalysisResult, CriticalPathInfo, ScheduledActivity
from .longest_path import LongestPathResult, PathInfo, trace_longest_paths
from .engine import run_analysis
