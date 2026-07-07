"""Tests for the interactive HTML network cockpit (backlog S8,
ANALYTICS_PROPOSAL.md §6.7 first bullet) — report/cockpit.py.

Exercised against the legacy demo series (demo_baseline/demo_update1/
demo_update2 — 3 updates, known seeded findings, see
tests/fixtures/make_fixtures.py) and the demo_hs pair (demo_hs1/demo_hs2 —
single consecutive-pair series).  A synthetic in-memory schedule with >400
near-critical activities exercises the node cap / truncation-disclosure path
without needing an oversized fixture on disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load, load_many                       # noqa: E402
from scheduleiq.ingest.model import (Activity, ActivityStatus,      # noqa: E402
                                     ActivityType, Schedule)
from scheduleiq.analytics.paths import driving_path                 # noqa: E402
from scheduleiq.metrics.engine import evaluate                      # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis, analyze_series  # noqa: E402
from scheduleiq.report.cockpit import (DEFAULT_NODE_CAP, FOOTER_TEXT,  # noqa: E402
                                       write_cockpit)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    need = [p for p in (BASELINE, U1, U2, HS1, HS2) if not os.path.exists(p)]
    if need:
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def legacy_series():
    return analyze_series(load_many([BASELINE, U1, U2]))


@pytest.fixture(scope="session")
def hs_series():
    return analyze_series(load_many([HS1, HS2]))


def _extract_blob(html_text: str) -> dict:
    marker = '<script type="application/json" id="cockpit-data">'
    start = html_text.index(marker) + len(marker)
    end = html_text.index("</script>", start)
    return json.loads(html_text[start:end])


def _no_external_urls(html_text: str) -> list[str]:
    """Return any http(s):// occurrence not attributable to an xmlns
    namespace URI and not inside an HTML comment."""
    offenders = []
    comment_spans = [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", html_text, re.S)]

    def in_comment(pos: int) -> bool:
        return any(a <= pos < b for a, b in comment_spans)

    for m in re.finditer(r"https?://[^\s\"'<>]*", html_text):
        if in_comment(m.start()):
            continue
        line_start = html_text.rfind("\n", 0, m.start()) + 1
        line_end = html_text.find("\n", m.end())
        line_end = line_end if line_end != -1 else len(html_text)
        line = html_text[line_start:line_end]
        if "xmlns" in line:
            continue
        offenders.append(line.strip())
    return offenders


# --------------------------------------------------------------------------
# basic file properties
# --------------------------------------------------------------------------
def test_writes_valid_utf8_html(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    assert os.path.exists(out)
    with open(out, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")           # raises on invalid UTF-8
    assert text.lstrip().startswith("<title>") or "<title>" in text[:200]
    assert "<html" not in text[:50]      # we emit a body-content fragment, not a full doc


def test_footer_text_present(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    text = open(out, encoding="utf-8").read()
    assert FOOTER_TEXT in text


def test_no_external_urls(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    text = open(out, encoding="utf-8").read()
    offenders = _no_external_urls(text)
    assert offenders == [], f"external URL(s) outside comments/xmlns: {offenders}"


def test_inline_script_and_style_only(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    text = open(out, encoding="utf-8").read()
    # every <script ...> and <link ...> tag must not reference an external
    # resource (no src= on <script>, no <link rel=stylesheet>)
    for m in re.finditer(r"<script\b[^>]*>", text):
        assert "src=" not in m.group(), m.group()
    assert "<link" not in text
    assert text.count("<style>") >= 1
    assert text.count("<script>") >= 1 or "<script type=\"application/json\"" in text


# --------------------------------------------------------------------------
# JSON blob content
# --------------------------------------------------------------------------
def test_json_blob_top_level_keys(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    assert set(blob.keys()) == {"version", "footer", "near_days", "node_cap",
                                "is_series", "updates", "churn"}
    assert blob["footer"] == FOOTER_TEXT
    assert blob["is_series"] is True
    assert len(blob["updates"]) == 3
    assert len(blob["churn"]) == 2


def test_per_update_node_sets_non_empty(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    for upd in blob["updates"]:
        assert len(upd["nodes"]) > 0, upd["label"]
        assert len(upd["edges"]) > 0, upd["label"]


def test_driving_path_codes_cross_check_analytics_paths(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    for sched, upd in zip(legacy_series.schedules, blob["updates"]):
        dp = driving_path(sched)
        assert upd["target_code"] == (dp.target.code if dp.target else None)
        node_codes = {n["code"] for n in upd["nodes"]}
        driving_codes_in_blob = {n["code"] for n in upd["nodes"] if n["band"] == "driving"}
        assert driving_codes_in_blob == set(dp.codes)
        # spot-check a couple of driving-path codes directly against paths.py
        for code in dp.codes[:3]:
            assert code in node_codes


def test_findings_reference_check_ids_from_engine(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    first_upd = blob["updates"][0]
    assert first_upd["findings"], "expected seeded findings on the baseline file"
    ids_in_blob = {f["check_id"] for f in first_upd["findings"]}
    ids_in_assessment = {r.check.id for r in legacy_series.assessments[0].results if r.findings}
    assert ids_in_blob == ids_in_assessment
    for f in first_upd["findings"]:
        assert f["severity"] in ("critical", "warning", "info")
        assert f["object_ids"]


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------
def test_deterministic_bytes_across_two_runs(legacy_series, tmp_path):
    p1 = write_cockpit(legacy_series, str(tmp_path / "a.html"))
    p2 = write_cockpit(legacy_series, str(tmp_path / "b.html"))
    h1 = hashlib.sha256(open(p1, "rb").read()).hexdigest()
    h2 = hashlib.sha256(open(p2, "rb").read()).hexdigest()
    assert h1 == h2


# --------------------------------------------------------------------------
# degradation
# --------------------------------------------------------------------------
def test_single_file_series_hides_slider_and_marks_not_series(tmp_path):
    sa = analyze_series(load(BASELINE))
    assert sa.is_series is False
    out = write_cockpit(sa, str(tmp_path / "single.html"))
    text = open(out, encoding="utf-8").read()
    blob = _extract_blob(text)
    assert blob["is_series"] is False
    assert len(blob["updates"]) == 1
    assert blob["churn"] == []
    # the JS hides the slider wrapper for non-series output
    assert 'document.getElementById("slider-wrap").style.display = "none"' in text


def test_empty_paths_degrade_without_crash(tmp_path):
    empty = Schedule(project_id="EMPTY")
    sa = SeriesAnalysis(schedules=[empty], assessments=[evaluate(empty)])
    out = write_cockpit(sa, str(tmp_path / "empty.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    upd = blob["updates"][0]
    assert upd["nodes"] == []
    assert upd["edges"] == []
    assert upd["target_code"] is None
    assert upd["target_reason"]


def test_hs_pair_series_renders(hs_series, tmp_path):
    out = write_cockpit(hs_series, str(tmp_path / "hs.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    assert blob["is_series"] is True
    assert len(blob["updates"]) == 2
    assert len(blob["churn"]) == 1
    for upd in blob["updates"]:
        assert len(upd["nodes"]) > 0


# --------------------------------------------------------------------------
# node cap / truncation disclosure (synthetic, in-memory, no fixture needed)
# --------------------------------------------------------------------------
def _big_schedule(n: int) -> Schedule:
    sched = Schedule(project_id="BIG", data_date=datetime(2025, 1, 1))
    d0 = datetime(2025, 1, 1, 8, 0)
    for i in range(n):
        code = f"BIG{i:04d}"
        a = Activity(uid=str(i), code=code, name=f"Synthetic activity {i}",
                    atype=ActivityType.TASK, status=ActivityStatus.NOT_STARTED,
                    total_float_hours=40.0,           # 5 working days at 8h/day
                    early_start=d0 + timedelta(days=i),
                    early_finish=d0 + timedelta(days=i + 2))
        sched.activities[a.uid] = a
    return sched


def test_truncation_disclosure_on_large_synthetic_series(tmp_path):
    sched = _big_schedule(450)
    sa = SeriesAnalysis(schedules=[sched], assessments=[evaluate(sched)])
    out = write_cockpit(sa, str(tmp_path / "big.html"))
    text = open(out, encoding="utf-8").read()
    blob = _extract_blob(text)
    upd = blob["updates"][0]
    assert upd["candidate_count"] == 450
    assert upd["included_count"] == DEFAULT_NODE_CAP == 400
    assert upd["truncated"] is True
    assert len(upd["nodes"]) == 400
    # disclosure must be reachable in the rendered page, not silently dropped
    assert "truncNote.textContent" in text
    assert str(DEFAULT_NODE_CAP) in text


def test_below_cap_synthetic_series_not_truncated(tmp_path):
    sched = _big_schedule(50)
    sa = SeriesAnalysis(schedules=[sched], assessments=[evaluate(sched)])
    out = write_cockpit(sa, str(tmp_path / "small.html"))
    blob = _extract_blob(open(out, encoding="utf-8").read())
    upd = blob["updates"][0]
    assert upd["candidate_count"] == 50
    assert upd["included_count"] == 50
    assert upd["truncated"] is False


# --------------------------------------------------------------------------
# size discipline
# --------------------------------------------------------------------------
def test_demo_series_under_size_budget(legacy_series, tmp_path):
    out = write_cockpit(legacy_series, str(tmp_path / "cockpit.html"))
    size = os.path.getsize(out)
    assert size < 2 * 1024 * 1024, f"cockpit file is {size} bytes, over the 2MB budget"
