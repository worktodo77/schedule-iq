"""Native .mpp ingestion via MPXJ (optional dependency).

.mpp is a closed binary format; the only credible open reader is MPXJ
(https://www.mpxj.org), a Java library with a Python bridge (``pip install
mpxj``, requires a JVM).  The Windows installer bundles a JRE so analysts get
native .mpp reading with zero setup; source installs degrade gracefully with
an actionable message (export to MSPDI .xml as the fallback workflow).

Rather than re-mapping every MPXJ field, we ask MPXJ to write an MSPDI file
and reuse the battle-tested MSPDI parser — one canonical mapping to maintain.
"""
from __future__ import annotations

import os
import tempfile

from .model import Schedule, sha256_of


class MppSupportMissing(RuntimeError):
    pass


def mpxj_available() -> bool:
    try:
        import mpxj  # noqa: F401
        return True
    except Exception:
        return False


def parse_mpp(path: str) -> list[Schedule]:
    try:
        import jpype
        import mpxj  # noqa: F401  (starts the JVM / sets classpath)
    except Exception as e:
        raise MppSupportMissing(
            "Native .mpp reading requires the MPXJ bridge (pip install mpxj, "
            "plus a Java runtime).  The packaged Windows installer includes it.  "
            "Workaround: open the file in Microsoft Project and save as XML "
            "(MSPDI), then ingest the .xml.  "
            f"[{type(e).__name__}: {e}]"
        ) from e
    if not jpype.isJVMStarted():
        jpype.startJVM()
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
    for s in schedules:
        s.source_file = os.path.basename(path)
        s.source_format = "MPP"
        s.source_sha256 = sha256_of(path)
        s.source_tool = "Microsoft Project (.mpp via MPXJ)"
    return schedules
