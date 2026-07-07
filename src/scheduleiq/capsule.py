"""Reproducibility capsule & evidence sealing (ANALYTICS_PROPOSAL.md §8.5,
backlog N5).

``build_capsule`` is called once, at the very end of a completed run
(``runner.run()``), and writes ``<out_dir>/capsule/``:

- ``manifest.json`` — SHA-256 of every deterministic result artifact the run
  produced, the recorded input files (pulled from the audit log's last line,
  so this stays a single source of truth with ``audit.py``), the tool
  version, the Python version, the sha256 of ``metrics/matrix.yaml`` (the
  check inventory in force), the threshold-profile content (if any), and the
  exact run parameters needed to reconstruct the CLI invocation.
- ``rerun.py`` — a standalone script that re-executes that exact CLI
  invocation into a fresh directory and verifies the outputs hash identically
  to the sealed manifest, printing PASS/FAIL per file.
- ``README.txt`` — plain-language explanation for tribunal/opposing-expert use.

Never raises: the caller wraps this in a guarded try/except so a capsule
failure can never sink a run (matching analytics/paths.py's convention for
the path-analysis workbook in runner.py).

Design note on the audit trail: ``audit_log.jsonl`` legitimately differs on a
genuine re-run (it stamps a live timestamp/host/operator), even when every
finding is byte-identical.  It is therefore recorded in the manifest as
``audit_trail`` (informational, hashed for the record) rather than folded into
``outputs`` (the set ``rerun.py`` actually verifies bit-for-bit).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from . import __version__
from .metrics.engine import MATRIX_PATH
from .scorecard import SPEC_PATH as SCORECARD_SPEC_PATH

_AUDIT_DIRNAME = "audit"
_CAPSULE_DIRNAME = "capsule"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_outputs(out_dir: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Enumerate files under ``out_dir`` (relative, absolute), split into
    (result_files, audit_files); never descends into a pre-existing capsule
    directory from a prior run of the same out_dir."""
    result_files: list[tuple[str, str]] = []
    audit_files: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(out_dir):
        dirs[:] = [d for d in dirs if d != _CAPSULE_DIRNAME]
        for fn in files:
            ap = os.path.join(root, fn)
            rel = os.path.relpath(ap, out_dir).replace(os.sep, "/")
            top = rel.split("/", 1)[0]
            if top == _AUDIT_DIRNAME:
                audit_files.append((rel, ap))
            else:
                result_files.append((rel, ap))
    return sorted(result_files), sorted(audit_files)


def _last_audit_record(out_dir: str) -> dict:
    path = os.path.join(out_dir, _AUDIT_DIRNAME, "audit_log.jsonl")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    if not lines:
        return {}
    try:
        return json.loads(lines[-1])
    except (json.JSONDecodeError, ValueError):
        return {}


_RERUN_TEMPLATE = '''#!/usr/bin/env python3
"""Standalone reproducibility check for a ScheduleIQ evidence capsule.

Re-executes the EXACT CLI invocation recorded in manifest.json (same input
files, profile, paper size, PDF/benchmark flags) into a fresh output
directory, then verifies every deterministic result artifact (workbooks,
report) hashes identically to the sealed run.  See README.txt.

Usage:  python rerun.py   (from anywhere; paths are resolved from manifest.json
                            next to this script and the input paths it records)

Requires only the Python standard library plus an installed/importable
``scheduleiq`` package (the same version recorded in manifest.json for a
faithful re-run; a materially newer tool version may legitimately produce
different numbers if checks were added or corrected, which is why the tool
version and matrix.yaml hash are also sealed in the manifest).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(HERE, "manifest.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    rp = manifest["run_params"]

    with tempfile.TemporaryDirectory(prefix="scheduleiq_rerun_") as tmp:
        cmd = [sys.executable, "-m", "scheduleiq.cli", "analyze"]
        cmd += rp.get("paths", [])
        cmd += ["-o", tmp, "--paper", rp.get("paper", "letter")]
        if not rp.get("make_pdf", True):
            cmd.append("--no-pdf")
        if rp.get("profile"):
            cmd += ["--profile", rp["profile"]]
        if rp.get("benchmark"):
            cmd.append("--benchmark")

        print("Re-running:", " ".join(cmd))
        subprocess.run(cmd, check=True)

        ok = True
        for entry in manifest.get("outputs", []):
            rel, expected = entry["path"], entry["sha256"]
            path = os.path.join(tmp, rel)
            if not os.path.exists(path):
                print(f"MISSING  {rel}")
                ok = False
                continue
            actual = sha256_file(path)
            status = "PASS" if actual == expected else "FAIL"
            if status != "PASS":
                ok = False
            print(f"{status}  {rel}")

        print()
        if ok:
            print("ALL OUTPUTS MATCH \\u2014 bit-identical re-run.")
        else:
            print("MISMATCH DETECTED \\u2014 see FAIL/MISSING lines above.")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
'''

_README_TEMPLATE = """ScheduleIQ Reproducibility Capsule
==================================

What this is
------------
A sealed, self-verifying record of one ScheduleIQ analysis run, built for
tribunal and opposing-expert use.  It turns "trust our workings" into "run
our workings":

  manifest.json   SHA-256 of every input file, every deterministic result
                  artifact (workbooks, the Word/PDF report), the tool
                  version, the Python version, the SHA-256 of the check
                  matrix in force (metrics/matrix.yaml), the threshold
                  profile applied (if any), and the exact parameters needed
                  to reconstruct the CLI invocation.

  rerun.py        A standalone script that re-executes that exact invocation
                  into a fresh directory and prints PASS/FAIL for every
                  output file, comparing its freshly computed hash against
                  the one sealed in manifest.json.

  README.txt      This file.

How to use it
--------------
1.  Keep this whole "capsule" folder together with the run's output folder
    (or archive it alongside the matter's evidence — it is self-contained
    apart from needing the original input schedule files at the paths
    recorded in manifest.json, and a Python environment with the recorded
    ScheduleIQ version installed).
2.  To verify a delivered analysis is reproducible, run:

        python rerun.py

    A clean "ALL OUTPUTS MATCH" means every workbook and report figure in
    the delivered analysis can be regenerated byte-for-byte from the
    hash-identified input files and the recorded tool version — nothing in
    the analysis depends on an undocumented manual step.

Why the audit trail is listed separately
-----------------------------------------
manifest.json records the run's audit_log.jsonl entry under "audit_trail",
not under "outputs".  That file legitimately differs on every genuine
re-run: it stamps a live timestamp, operator, and hostname even when every
finding is identical.  Compare its "summary" field (health scores, fail
counts) logically, not by hash; the hash of "outputs" is the bit-for-bit
reproducibility guarantee.
"""


def build_capsule(out_dir: str, run_params: dict) -> str:
    """Build the reproducibility capsule for a completed run.  Returns the
    path to manifest.json.  Caller must guard this in try/except (it does
    not swallow its own errors) so a capsule failure never sinks a run."""
    out_dir = os.path.abspath(out_dir)
    capsule_dir = os.path.join(out_dir, _CAPSULE_DIRNAME)

    result_files, audit_files = _walk_outputs(out_dir)
    outputs_manifest = [{"path": rel, "sha256": _sha256_file(ap)}
                        for rel, ap in result_files]
    audit_manifest = [{"path": rel, "sha256": _sha256_file(ap)}
                      for rel, ap in audit_files]

    last_audit = _last_audit_record(out_dir)
    inputs = last_audit.get("inputs", [])

    profile_path = run_params.get("profile")
    profile_content = None
    if profile_path and os.path.exists(profile_path):
        with open(profile_path, encoding="utf-8") as f:
            profile_content = f.read()

    manifest = {
        "capsule_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "scheduleiq",
        "tool_version": __version__,
        "python_version": sys.version,
        "matrix_yaml_sha256": (_sha256_file(MATRIX_PATH)
                               if os.path.exists(MATRIX_PATH) else None),
        "scorecard_yaml_sha256": (_sha256_file(SCORECARD_SPEC_PATH)
                                 if os.path.exists(SCORECARD_SPEC_PATH) else None),
        "run_params": run_params,
        "threshold_profile_path": profile_path,
        "threshold_profile_content": profile_content,
        "inputs": inputs,
        "outputs": outputs_manifest,
        "audit_trail": audit_manifest,
        "note": ("`outputs` are the deterministic result artifacts verified "
                "bit-for-bit by rerun.py.  `audit_trail` (audit_log.jsonl) is "
                "recorded for context only: it carries a live run timestamp, "
                "operator, and host that will legitimately differ on a "
                "genuine re-run even when every finding is identical; "
                "compare its `summary` field logically, not by hash."),
    }

    os.makedirs(capsule_dir, exist_ok=True)
    manifest_path = os.path.join(capsule_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    with open(os.path.join(capsule_dir, "rerun.py"), "w", encoding="utf-8") as f:
        f.write(_RERUN_TEMPLATE)
    try:
        os.chmod(os.path.join(capsule_dir, "rerun.py"), 0o755)
    except OSError:                                    # pragma: no cover
        pass

    with open(os.path.join(capsule_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(_README_TEMPLATE)

    return manifest_path
