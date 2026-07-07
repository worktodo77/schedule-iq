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
