# ADR-0002: Schedule format support — native XER/MSPDI, MPXJ for .mpp

**Status:** accepted · **Date:** 2026-07-06

## Context
.xer is a documented tab-delimited text format; MSPDI .xml is a documented
schema; .mpp is a closed binary format with no credible pure-Python reader.

## Decision
- Write our own XER and MSPDI parsers (pure Python, zero dependencies) — full
  control over the fields forensic checks need (SCHEDOPTIONS, calendar data
  blobs, suspend/resume, expected finish) and no third-party mapping errors.
- Read .mpp through MPXJ (the industry-standard Java library, also used by
  commercial tools) via its Python bridge, converting MPXJ's model to MSPDI
  and reusing our MSPDI parser so there is exactly one canonical mapping.
- Bundle a JRE + MPXJ in the Windows installer; source installs get a clear
  degradation message with the MSPDI-export workaround.
- P6 XML (.xml) ingestion is backlog: same canonical model, new reader; the
  loader already reserves the dispatch slot.

## Consequences
- XER fidelity is ours to test (fixtures + real-file validation before
  first matter use).  MPXJ adds ~200 MB to the installer only.

## Addendum (2026-07-07): F3 (P6 XML) and F5 (Asta/Phoenix via MPXJ) delivered

- **F3 — native P6 XML (PMXML) parser** (`src/scheduleiq/ingest/p6xml.py`):
  pure Python, `xml.etree` only, zero new dependencies — same fidelity bar as
  xer.py (activities, relationships, calendars with workweek + exceptions,
  WBS, ScheduleOptions, both constraint slots, resource assignments,
  multi-project exports, non-fatal `parse_warnings`).  Unlike msp_xml.py, the
  parser matches elements by LOCAL NAME rather than a hardcoded namespace URI,
  because the PMXML default namespace embeds the P6 version
  (`.../P6/V23.12/API/BusinessObjects`, V21.12, ...) and changes on every P6
  release; this makes the parser version-agnostic by construction.
  `ingest/__init__.py`'s `.xml` dispatch now sniffs the root element
  (`Project` in the MSPDI namespace vs. `APIBusinessObjects`) so both formats
  share the `.xml` extension without collision; MSPDI behavior is unchanged
  (checked first, byte-identical).
- **F5 — Asta Powerproject (.pp) and Phoenix Project Manager (.ppx)**: routed
  through the same MPXJ bridge as .mpp (`ingest/mpp.py`, now
  `parse_via_mpxj`), behind the same optional-dependency guard
  (`MppSupportMissing` / `mpxj_available()`); `.pp` and `.ppx` added to
  `ingest.SUPPORTED`.  MPXJ's `UniversalProjectReader` auto-detects the Asta
  variant (legacy text vs. newer zip container) and the Phoenix schedule XML,
  so no format-specific code is needed beyond the extension routing and the
  source-format label.
- **Known PMXML gaps** (documented, not silently dropped — see the parser's
  module docstring and the addendum notes below):
  - No standard field carries "who exported this file and when" the way the
    XER header row does; `export_user`/`export_date` fall back to the
    Project row's `CreateUser`/`LastUpdateDate`, and `source_tool` records the
    `ExportVersion` root attribute only when the exporter sets it.
  - Calendar `IsDefault` has no per-calendar flag in PMXML; the default
    calendar is inferred from `Project/DefaultCalendarObjectId`, and — like
    xer.py — calendars are shared instances across a multi-project export, so
    `is_default` is not distinguishable per-project if two projects in the
    same file point at different default calendars.
  - `ScheduleOptions`' retained-logic/progress-override tri-state
    (`SchedulingProgressedActivities`) and the relationship-lag-calendar
    setting are both exposed and mapped; PMXML does not appear to expose a
    separate "ignore relationships across projects" flag equivalent to some
    of SCHEDOPTIONS' XER columns — unmapped fields land in `settings.raw` for
    audit visibility rather than being silently discarded.
- Fixture: `tests/fixtures/demo_p6.xml` — synthetic, hand-written (not
  exported from a live P6 database); compact single-project PMXML exercising
  every mapped field.  Tests: `tests/test_p6xml.py`.
