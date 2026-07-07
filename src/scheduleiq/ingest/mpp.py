"""Native .mpp / Asta .pp / Phoenix .ppx ingestion via MPXJ (optional dependency).

.mpp is a closed binary format; the only credible open reader is MPXJ
(https://www.mpxj.org), a Java library with a Python bridge (``pip install
mpxj``, requires a JVM).  The Windows installer bundles a JRE so analysts get
native .mpp reading with zero setup; source installs degrade gracefully with
an actionable message (export to MSPDI .xml as the fallback workflow).

Rather than re-mapping every MPXJ field, we ask MPXJ to write an MSPDI file
and reuse the battle-tested MSPDI parser — one canonical mapping to maintain.

F5 (backlog): the same MPXJ bridge also reads Asta Powerproject (``.pp``,
both the legacy text and the newer zip-based container — MPXJ's
``UniversalProjectReader`` auto-detects the variant) and Phoenix Project
Manager (``.ppx``) exports, since MPXJ ships dedicated readers for both
(``AstaReader`` family, ``PhoenixReader``) behind the same
``UniversalProjectReader`` entry point used for .mpp.  Everything downstream
(MSPDI conversion, source-format tagging) is identical; only the label and
the source extension differ.
"""
from __future__ import annotations

import os
import tempfile

from .model import Schedule, sha256_of

_SOURCE_LABEL = {
    ".mpp": ("MPP", "Microsoft Project (.mpp via MPXJ)"),
    ".pp": ("ASTA_PP", "Asta Powerproject (.pp via MPXJ)"),
    ".ppx": ("PHOENIX", "Phoenix Project Manager (.ppx via MPXJ)"),
}


class MppSupportMissing(RuntimeError):
    pass


def mpxj_available() -> bool:
    try:
        import mpxj  # noqa: F401
        return True
    except Exception:
        return False


def _require_mpxj():
    try:
        import jpype
        import mpxj  # noqa: F401  (starts the JVM / sets classpath)
    except Exception as e:
        raise MppSupportMissing(
            "Native reading of this format requires the MPXJ bridge (pip install "
            "mpxj, plus a Java runtime).  The packaged Windows installer includes "
            "it.  Workaround: export the file from its authoring tool (P6/MS "
            "Project/Asta/Phoenix) to MSPDI .xml, then ingest the .xml.  "
            f"[{type(e).__name__}: {e}]"
        ) from e
    if not jpype.isJVMStarted():
        jpype.startJVM()
    return jpype


def parse_via_mpxj(path: str) -> list[Schedule]:
    """Read any MPXJ-supported binary/proprietary format (.mpp, .pp, .ppx, ...)
    through MPXJ's ``UniversalProjectReader``, converting to MSPDI and reusing
    the MSPDI parser — the same bridge for every non-native format (F5)."""
    jpype = _require_mpxj()
    from net.sf.mpxj.reader import UniversalProjectReader          # type: ignore
    from net.sf.mpxj.mspdi import MSPDIWriter                      # type: ignore

    project = UniversalProjectReader().read(path)
    if project is None:
        raise ValueError(f"{path}: MPXJ could not read this file")
    tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
    tmp.close()
    try:
        MSPDIWriter().write(project, tmp.name)
        from .msp_xml import parse_mspdi
        schedules = parse_mspdi(tmp.name)
    finally:
        os.unlink(tmp.name)
    ext = os.path.splitext(path)[1].lower()
    fmt, tool = _SOURCE_LABEL.get(ext, ("MPP", "MPXJ"))
    for s in schedules:
        s.source_file = os.path.basename(path)
        s.source_format = fmt
        s.source_sha256 = sha256_of(path)
        s.source_tool = tool
    return schedules


def parse_mpp(path: str) -> list[Schedule]:
    return parse_via_mpxj(path)
