#!/usr/bin/env python3
"""Build the RC6 public-spec publication package (docs/public_spec/).

Backlog RC6 (docs/REPORT_CARD_DESIGN.md §6): publish the LI Schedule Report
Card spec + a minimal reference scorer under Apache-2.0 while ScheduleIQ
itself stays proprietary.  Publication was approved 2026-07-07; this script
performs the mechanical build step docs/public_spec/README.md documents —
it does NOT itself push anything externally (see "still to do" in its
printed summary and in the rewritten README banner).

This script is RE-RUNNABLE: every file it writes is fully regenerated from
its inputs each run (no accumulation, no manual edits to preserve), so it is
safe — and expected — to run again after src/scheduleiq/scorecard.yaml
changes (e.g. once the parallel N16-N20 provocative-index wave lands).  Run
it LAST, after all other waves have merged, and re-run before every
publication cut.

What it does, in order
-----------------------
1. Copies src/scheduleiq/scorecard.yaml into docs/public_spec/scorecard.yaml
   VERBATIM, with ONE exception: the top-level ``internal_variant:`` block
   (N16-N20 provocative-index placeholders, §11 guardrails: privileged/
   internal surface, never scored) is stripped, together with its immediately
   preceding comment banner.  Nothing else in the file is touched — every
   other line, comment, and blank line is byte-identical to the source.
2. Computes the SHA-256 of the PUBLISHED (post-strip) scorecard.yaml and
   stamps it, with the spec_version, into LI-RC-spec.md's banner.
3. Writes LICENSE (Apache-2.0, copyright Long International, Inc. 2026).
4. Generates sample_results.csv (a tiny, real demo: the four
   ``duration_estimating`` category members, with their unit/threshold/
   direction/severity read live from metrics/matrix.yaml so the sample never
   drifts from the shipped matrix) and runs reference_scorer.py against it,
   verifying it exits cleanly and reproduces a category score; the captured
   stdout is written to sample_results_expected_output.txt as the package's
   "expected output" fixture.
5. Rewrites README.md's front-matter banner from NOT YET PUBLISHED to READY
   TO PUBLISH (approved 2026-07-07) — still instructing a human to
   actually stand up the public repository and push; ticks the checklist
   items this script itself completes; and documents the internal_variant
   exclusion.  LI-RC-spec.md's matching top banner is rewritten the same way.

Usage:
    python3 scripts/build_public_spec.py
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

SRC_SCORECARD = os.path.join(ROOT, "src", "scheduleiq", "scorecard.yaml")
PUBLIC_DIR = os.path.join(ROOT, "docs", "public_spec")
PUBLIC_SCORECARD = os.path.join(PUBLIC_DIR, "scorecard.yaml")
SPEC_MD = os.path.join(PUBLIC_DIR, "LI-RC-spec.md")
README_MD = os.path.join(PUBLIC_DIR, "README.md")
LICENSE_PATH = os.path.join(PUBLIC_DIR, "LICENSE")
SAMPLE_CSV = os.path.join(PUBLIC_DIR, "sample_results.csv")
EXPECTED_OUTPUT = os.path.join(PUBLIC_DIR, "sample_results_expected_output.txt")
REFERENCE_SCORER = os.path.join(PUBLIC_DIR, "reference_scorer.py")

APPROVAL_NOTE = "approved 2026-07-07"
SAMPLE_CATEGORY = "duration_estimating"
SAMPLE_MEMBER_VALUES = {
    # id -> (measured value, status) — everything else (unit/threshold/
    # direction/severity) is read live from matrix.yaml, never hardcoded.
    "DCMA-08": (3, "PASS"),
    "DUR-01": (2, "WARNING"),
    "DUR-02": (12, "INFO"),
    "DUR-03": (0, "PASS"),
}


# ---------------------------------------------------------------------------
# 1. Strip internal_variant from scorecard.yaml
# ---------------------------------------------------------------------------
def strip_internal_variant(yaml_text: str) -> tuple[str, bool]:
    """Remove the top-level ``internal_variant:`` block (and its immediately
    preceding comment banner) from a scorecard.yaml text.  Everything else is
    returned byte-identical.  Returns (stripped_text, stripped)."""
    lines = yaml_text.split("\n")
    idx = None
    for i, line in enumerate(lines):
        if line == "internal_variant:":
            idx = i
            break
    if idx is None:
        return yaml_text, False

    # internal_variant is the last top-level section (verified against the
    # live file at test time) -- walk backward over its immediately
    # preceding comment banner (and the blank line separating it from the
    # previous section) so the published file ends cleanly, not on a
    # dangling "# RC5 -- internal-variant scaffolding" comment.
    start = idx
    k = idx - 1
    while k >= 0 and (lines[k].startswith("#") or lines[k].strip() == ""):
        start = k
        k -= 1

    stripped_lines = lines[:start]
    while stripped_lines and stripped_lines[-1].strip() == "":
        stripped_lines.pop()
    return "\n".join(stripped_lines) + "\n", True


# ---------------------------------------------------------------------------
# 3. LICENSE
# ---------------------------------------------------------------------------
_APACHE_2_0_BODY = """\
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright {year} Long International, Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


def build_license(year: int) -> str:
    return _APACHE_2_0_BODY.format(year=year)


# ---------------------------------------------------------------------------
# 4. sample_results.csv + reference_scorer verification
# ---------------------------------------------------------------------------
def build_sample_csv() -> str:
    from scheduleiq.metrics.engine import load_matrix  # noqa: E402

    matrix = {c.id: c for c in load_matrix()}
    header = "id,value,status,threshold,direction,unit,severity"
    rows = [header]
    for check_id, (value, status) in SAMPLE_MEMBER_VALUES.items():
        c = matrix[check_id]
        threshold = "" if c.threshold is None else f"{c.threshold:g}"
        rows.append(f"{check_id},{value},{status},{threshold},{c.direction},"
                    f"{c.unit},{c.severity}")
    return "\n".join(rows) + "\n"


def run_reference_scorer(csv_path: str, spec_path: str) -> str:
    result = subprocess.run(
        [sys.executable, REFERENCE_SCORER, csv_path, spec_path, SAMPLE_CATEGORY],
        capture_output=True, text=True, cwd=PUBLIC_DIR)
    if result.returncode != 0:
        raise RuntimeError(
            "reference_scorer.py did not run cleanly against the sample CSV "
            f"(exit {result.returncode}):\n{result.stdout}\n{result.stderr}")
    if "score = " not in result.stdout and "no gradeable members" in result.stdout:
        raise RuntimeError(
            "reference_scorer.py produced no gradeable members from the "
            f"sample CSV -- sample is not exercising the scorer:\n{result.stdout}")
    return result.stdout


# ---------------------------------------------------------------------------
# 5. Banner rewrites (idempotent -- matches either the old NOT YET PUBLISHED
#    banner or an already-rewritten READY TO PUBLISH banner by consuming the
#    leading blockquote block line-by-line, so reruns update in place rather
#    than duplicating or requiring a fixed closing phrase to match on)
# ---------------------------------------------------------------------------


def _readme_banner(build_date: str, sha256: str, spec_version: str) -> str:
    return (
        f"> **READY TO PUBLISH ({APPROVAL_NOTE}).**  This directory is a "
        "publication-ready package for the LI Schedule Report Card spec "
        "(backlog RC6), built per docs/REPORT_CARD_DESIGN.md §6's "
        "recommendation to publish the spec and a minimal reference scorer "
        "under an open license (Apache-2.0) while ScheduleIQ itself remains "
        "proprietary.  `scripts/build_public_spec.py` last built this "
        f"package on {build_date} — spec_version `{spec_version}`, "
        f"published scorecard.yaml SHA-256 `{sha256}`.  The internal "
        "research variant (`internal_variant` — N16-N20 provocative "
        "indices, §11 guardrails) is NOT part of the public spec and has "
        "been stripped from the published scorecard.yaml.  **A human must "
        "still stand up the public repository/mirror and push these files "
        "— nothing in this repository publishes itself.**\n")


def _spec_banner(build_date: str, sha256: str, spec_version: str) -> str:
    return (
        f"> **READY TO PUBLISH ({APPROVAL_NOTE}).**  See `README.md` in "
        "this directory.  This document explains the methodology in prose; "
        "the normative, machine-readable spec is `scorecard.yaml` in this "
        "directory (copied verbatim from `src/scheduleiq/scorecard.yaml` at "
        "build time, EXCLUDING the internal `internal_variant` research "
        "block — see README.md).  Where this document and `scorecard.yaml` "
        f"disagree, `scorecard.yaml` governs.  Spec version `{spec_version}`, "
        f"SHA-256 `{sha256}` (built {build_date} by "
        "`scripts/build_public_spec.py`).  **A human must still stand up "
        "the public repository/mirror and push these files.**\n")


def rewrite_banner(path: str, new_banner: str) -> bool:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    start = None
    for i, line in enumerate(lines):
        if line.startswith("> **NOT YET PUBLISHED") or line.startswith("> **READY TO PUBLISH"):
            start = i
            break
    if start is None:
        raise RuntimeError(f"{path}: no NOT YET PUBLISHED / READY TO PUBLISH "
                           "banner found to rewrite")
    end = start
    while end < len(lines) and (lines[end].startswith(">") or lines[end].strip() == ""):
        if lines[end].strip() == "":
            break
        end += 1

    new_lines = lines[:start] + [new_banner] + lines[end:]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True


_CHECKLIST_RE = re.compile(r"## Publication checklist.*", re.DOTALL)


def rewrite_checklist(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new_checklist = (
        "## Publication checklist\n\n"
        "- [x] Confirm license (Apache-2.0 per the design doc's "
        "recommendation) — `LICENSE` written by the build step.\n"
        "- [x] Copy `src/scheduleiq/scorecard.yaml` into this directory "
        "verbatim (minus `internal_variant`) as part of the publish step — "
        "automated by `scripts/build_public_spec.py`, re-run before every "
        "publication cut.\n"
        "- [ ] Stand up the public repository (mirrors the internal "
        "mirroring arrangement already used for the engine port — see "
        "docs/BACKLOG.md L1).  **Not automated — a human action.**\n"
        "- [x] Remove the pre-approval notice from this file and from the "
        "top of `LI-RC-spec.md` — both banners replaced with a READY TO "
        f"PUBLISH banner ({APPROVAL_NOTE}).\n"
        "- [ ] Add a CHANGELOG.md for spec revisions per GOVERNANCE.md §1 "
        "(extended to cover the spec once published, per "
        "docs/REPORT_CARD_DESIGN.md §6).  **Not automated — a human "
        "action, once the public repository exists.**\n")
    if _CHECKLIST_RE.search(text):
        text = _CHECKLIST_RE.sub(new_checklist, text, count=1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    import yaml  # noqa: E402

    log: list[str] = []

    with open(SRC_SCORECARD, encoding="utf-8") as f:
        src_text = f.read()
    published_text, stripped = strip_internal_variant(src_text)
    if not stripped:
        raise RuntimeError("internal_variant block not found in "
                           f"{SRC_SCORECARD} -- refusing to publish an "
                           "un-stripped copy; check the source file's shape "
                           "has not changed.")

    # sanity: the strip removes ONLY internal_variant, nothing else.
    src_parsed = yaml.safe_load(src_text)
    pub_parsed = yaml.safe_load(published_text)
    src_minus = {k: v for k, v in src_parsed.items() if k != "internal_variant"}
    if pub_parsed != src_minus:
        raise RuntimeError("strip_internal_variant() changed something "
                           "other than internal_variant -- aborting build.")

    os.makedirs(PUBLIC_DIR, exist_ok=True)
    with open(PUBLIC_SCORECARD, "w", encoding="utf-8") as f:
        f.write(published_text)
    log.append(f"Stripped internal_variant block (N16-N20, privileged/"
              f"internal research surface, §11 guardrails) from the "
              f"published copy: {SRC_SCORECARD} -> {PUBLIC_SCORECARD} "
              f"({len(src_text.splitlines())} -> "
              f"{len(published_text.splitlines())} lines).")

    sha256 = hashlib.sha256(published_text.encode("utf-8")).hexdigest()
    spec_version = pub_parsed.get("spec_version", "?")
    log.append(f"Published scorecard.yaml: spec_version={spec_version!r}, "
              f"SHA-256={sha256}")

    with open(LICENSE_PATH, "w", encoding="utf-8") as f:
        f.write(build_license(date.today().year))
    log.append(f"Wrote {LICENSE_PATH} (Apache-2.0, "
              f"Copyright {date.today().year} Long International, Inc.)")

    sample_csv_text = build_sample_csv()
    with open(SAMPLE_CSV, "w", encoding="utf-8") as f:
        f.write(sample_csv_text)
    scorer_output = run_reference_scorer(SAMPLE_CSV, PUBLIC_SCORECARD)
    with open(EXPECTED_OUTPUT, "w", encoding="utf-8") as f:
        f.write(scorer_output)
    log.append(f"Wrote {SAMPLE_CSV} ({SAMPLE_CATEGORY} category, "
              f"{len(SAMPLE_MEMBER_VALUES)} members) and verified "
              "reference_scorer.py reproduces its category score; captured "
              f"stdout to {EXPECTED_OUTPUT}.")
    log.append("reference_scorer.py output:\n" +
              "\n".join("    " + ln for ln in scorer_output.splitlines()))

    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rewrite_banner(README_MD, _readme_banner(build_date, sha256, spec_version))
    rewrite_checklist(README_MD)
    log.append(f"Rewrote {README_MD} banner: NOT YET PUBLISHED -> READY TO "
              f"PUBLISH ({APPROVAL_NOTE}); checklist updated.")
    rewrite_banner(SPEC_MD, _spec_banner(build_date, sha256, spec_version))
    log.append(f"Rewrote {SPEC_MD} banner: NOT YET PUBLISHED -> READY TO "
              f"PUBLISH ({APPROVAL_NOTE}); stamped spec_version/SHA-256.")

    print("=== scripts/build_public_spec.py ===")
    for line in log:
        print(line)
    print("=== build complete;", PUBLIC_DIR, "is ready for a human to "
         "push to the public repository/mirror ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
