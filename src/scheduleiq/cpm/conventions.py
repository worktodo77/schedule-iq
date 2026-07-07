"""
Ported from the LI MIP 3.9 tool (mip39.conventions) per ADR-0007 — port-and-validate.
INFRA-009: EF Convention Architecture for Phase 5.

Defines the EFConvention enum and the fs_forward_offset() helper used
by the forward pass, backward pass, free-float computation, and
longest-path tightness check.

Convention meanings
-------------------

INCLUSIVE_DAY (default / backward-compatible):
    P3-tradition / inclusive-day CPM convention.
    FS lag=k: successor ES_workday = predecessor EF_workday + k
    (same workday at lag=0 — predecessor's EF workday is available to
    the successor on that same calendar day).
    This is the convention used in Phases 1–4 of this tool.

P6_COMPATIBILITY:
    Analytical approximation of Primavera P6 single-calendar day-level
    scheduling behavior.
    FS lag=k: successor ES_workday = predecessor EF_workday + k + 1
    (successor starts the next workday — models P6's "work ends at
    end-of-day; successor begins beginning-of-next-workday" at day
    granularity).
    SS, FF, and SF relationships: identical scheduling results under
    both conventions.

Affected calculations
---------------------
The fs_forward_offset() value is applied in four places:
  1. Forward pass FS constraint:
         effective_lag = lag + fs_forward_offset(convention)
  2. Backward pass FS constraint:
         A.LF = apply_lag(B.LS, -k - fs_forward_offset(convention), ...)
  3. Free float for FS predecessor:
         FF = wt[B.ES] - wt[A.EF] - k - fs_forward_offset(convention)
  4. Longest-path FS tightness check:
         wt[A.EF] + k + fs_forward_offset(convention) == wt[B.ES]

SS, FF, SF: offset = 0 under both conventions (unchanged from Phase 4).

Governance (ADR-006)
--------------------
  - INCLUSIVE_DAY is the recommended default for forensic analysis.
    It is transparent, hand-calculation verifiable, and backward
    compatible with Phases 1–4.
  - P6_COMPATIBILITY is NOT exact P6 emulation. It is an analytical
    approximation at day granularity.
  - ACCEPTABLE:   "P6-compatible analytical convention",
                  "analytical approximation of P6 day-level scheduling".
  - NOT ACCEPTABLE: "exact P6 emulation", "identical to P6".
"""

from __future__ import annotations

from enum import Enum


class EFConvention(Enum):
    """
    Scheduling convention governing FS relationship offset behavior.

    Only FS relationships are affected. SS, FF, and SF produce identical
    results under both conventions.

    Members:
        INCLUSIVE_DAY:    P3-tradition. FS successor starts same workday
                          as predecessor EF (lag=0). Backward compatible
                          with Phases 1–4. Recommended for forensic analysis.
        P6_COMPATIBILITY: P6 analytical approximation. FS successor starts
                          next workday after predecessor EF (lag=0). Use
                          only with analyst confirmation.
    """
    INCLUSIVE_DAY = "inclusive_day"
    P6_COMPATIBILITY = "p6_compatibility"


def fs_forward_offset(convention: EFConvention) -> int:
    """
    Return the FS workday offset for the given convention.

    Returns:
        0 for INCLUSIVE_DAY  — no offset; successor ES = pred EF + lag.
        1 for P6_COMPATIBILITY — 1-workday offset; successor ES = pred EF + lag + 1.

    Apply this value consistently in the forward pass, backward pass,
    free-float formula, and longest-path tightness check for FS only.
    """
    return 0 if convention == EFConvention.INCLUSIVE_DAY else 1
