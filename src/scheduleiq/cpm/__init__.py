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
forward_pass, calculation_registry, validation_framework, windows.

LIM-028 (date-constraint scheduling) and the Progress Override statusing mode
are implemented in ``constraints`` and wired into ``engine.run_analysis`` in
this port — see the constraints module and the engine docstring.
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
from .constraints import (
    ConstraintApplication,
    ConstraintType,
    SchedulingConstraint,
    StatusingMode,
    apply_backward_constraint,
    apply_forward_constraint,
    constraint_is_start_anchored,
    mnemonic,
)
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

# ADR-0007 §3 integration layer (E3/E4): ingest -> engine bridge and the
# validation handshake (SET-02).  Additive; imported after the core surface.
from .bridge import EngineInputs, build_engine_inputs, resolve_lag_strategy
from .handshake import (
    HandshakeRefusal,
    HandshakeResult,
    build_reference,
    clear_handshake_cache,
    require_valid_handshake,
    run_handshake,
)
