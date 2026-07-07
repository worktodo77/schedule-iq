"""Structured audit log — one JSON line per run (LI audit discipline).

Records timestamp, operator, host, tool version, parameters, input files with
SHA-256 hashes, outputs, and result counts, so any Report figure can be traced
to the exact inputs and check versions that produced it.
"""
from __future__ import annotations

import getpass
import json
import os
import socket
from datetime import datetime, timezone

from . import __version__
from .ingest.model import sha256_of


def append_audit(audit_dir: str, action: str, params: dict,
                 inputs: list[str], outputs: list[str],
                 summary: dict) -> str:
    os.makedirs(audit_dir, exist_ok=True)
    path = os.path.join(audit_dir, "audit_log.jsonl")
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "scheduleiq",
        "version": __version__,
        "action": action,
        "operator": getpass.getuser(),
        "host": socket.gethostname(),
        "params": params,
        "inputs": [{"path": os.path.abspath(p), "sha256": sha256_of(p)}
                   for p in inputs if os.path.exists(p)],
        "outputs": [os.path.abspath(p) for p in outputs],
        "summary": summary,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path
