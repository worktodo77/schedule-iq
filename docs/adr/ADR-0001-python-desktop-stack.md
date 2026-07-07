# ADR-0001: Python + PySide6 desktop stack

**Status:** accepted · **Date:** 2026-07-06

## Context
The tool must run on analyst PCs (Windows), parse text/XML/binary schedule
formats, compute statistics, and emit Word/PDF/Excel.  The firm's existing
tooling (expert-assist) is Python; the analysts are not developers.

## Decision
Python 3.10+ core; PySide6 (Qt) desktop GUI; a CLI sharing the same runner.
Packaged with PyInstaller into a self-contained Windows folder + zip.

## Consequences
- One language across the firm's tooling; expert-assist utilities (LI DOCX
  template injection) are reused directly.
- PySide6 gives a professional native-feeling GUI with drag-and-drop and is
  LGPL (no license cost).  It is an optional extra for source installs so the
  core stays lightweight/scriptable.
- PyInstaller bundles are large (~300 MB with Qt + JRE) — accepted; analysts
  install one zip, no Python required.
