"""Ingestion dispatch: one call, any supported format."""
from __future__ import annotations

import os

from .model import Schedule  # noqa: F401
from .xer import parse_xer
from .msp_xml import parse_mspdi

SUPPORTED = (".xer", ".xml", ".mpp")


def load(path: str) -> list[Schedule]:
    """Parse any supported schedule file into canonical Schedule objects."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xer":
        return parse_xer(path)
    if ext == ".xml":
        head = open(path, "rb").read(4096)
        if b"schemas.microsoft.com/project" in head:
            return parse_mspdi(path)
        raise ValueError(f"{path}: unrecognized XML (expected MSPDI; "
                         "P6 XML support tracked in ADR-0002)")
    if ext == ".mpp":
        from .mpp import parse_mpp
        return parse_mpp(path)
    raise ValueError(f"{path}: unsupported extension {ext} (supported: {SUPPORTED})")


def load_many(paths: list[str]) -> list[Schedule]:
    out: list[Schedule] = []
    for p in paths:
        out.extend(load(p))
    return out
