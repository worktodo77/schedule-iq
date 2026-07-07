"""Interactive HTML network cockpit (backlog S8, ANALYTICS_PROPOSAL.md §6.7
first bullet).

``write_cockpit(sa, out_path)`` renders ONE self-contained HTML file — no
install, no network, no build step — that lets counsel or the analyst
explore the driving/near-critical network of a :class:`SeriesAnalysis`
without opening ScheduleIQ itself: a zoomable time-scaled network, a slider
across updates, and click-through from any check finding to its activities
and back.

Scope note: this is the diagnostic explorer only.  The companion bullet in
§6.7 (the firm's graphics-generator demonstratives — windows bars,
float-erosion ribbons, path-evolution storyboards) is expert-assist-side
tooling and is OUT of scope here.

Self-contained (ADR-0006 — no network calls; counsel opens this from a file
share): every byte of CSS/JS is inlined below, vanilla JS + inline SVG, zero
external requests, zero CDN references.  The only ``http(s)://`` string that
may appear in the emitted file is the standard SVG XML namespace URI, which
is not a network request.

Data source: this module reads only the plain dataclasses already produced
by ``analytics.paths`` (driving path + record floats — the schedule-of-record
statement, per ADR-0004) and ``trend.series``/``metrics.engine`` (per-file
check findings).  It does not run its own CPM pass and does not import the
matplotlib figure modules.

Determinism: node/edge/finding lists are explicitly sorted before
serialization, the JSON blob is dumped with ``sort_keys=True`` and no
timestamps are embedded anywhere in the output, so two calls on the same
``SeriesAnalysis`` produce byte-identical files.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..analytics.paths import DEFAULT_TOL_HOURS, driving_path
from ..ingest.model import Activity, ConstraintType, Schedule
from ..trend.series import SeriesAnalysis

# ---------------------------------------------------------------------------
# LI house style (reused from report/impact_figures.py)
# ---------------------------------------------------------------------------
TEAL = "#1F6F7B"
AMBER = "#FFC000"
GRAY = "#7F7F7F"
LIGHT_GRAY = "#BFBFBF"
CRITICAL_RED = "#B00020"

FOOTER_TEXT = ("PRELIMINARY — diagnostic explorer; tool-of-record dates; "
               "expert review required.")

DEFAULT_NEAR_DAYS = 10.0     # analyst default near-critical float band, days
DEFAULT_NODE_CAP = 400       # per-update node cap, with disclosure


# ---------------------------------------------------------------------------
# activity -> plain-dict helpers
# ---------------------------------------------------------------------------
def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _constraint_label(a: Activity) -> str:
    if a.constraint and a.constraint != ConstraintType.NONE:
        return a.constraint.value
    if a.constraint2 and a.constraint2 != ConstraintType.NONE:
        return a.constraint2.value
    return ""


def _wbs_label(schedule: Schedule, a: Activity) -> tuple[str, str]:
    node = schedule.wbs.get(a.wbs_uid) if a.wbs_uid else None
    if node is None:
        return "", ""
    return node.code or "", node.name or ""


def _calendar_label(schedule: Schedule, a: Activity):
    cal = schedule.cal_for(a)
    return cal, (cal.name or cal.uid) if cal else (a.calendar_uid or "")


# ---------------------------------------------------------------------------
# per-update node/edge extraction
# ---------------------------------------------------------------------------
def _build_update(schedule: Schedule, near_days: float, node_cap: int,
                  tolerance_hours: float = DEFAULT_TOL_HOURS) -> tuple[dict, set]:
    """Driving path + near-critical band (record float <= ``near_days``) for
    one schedule, capped at ``node_cap`` nodes with disclosure.  Returns the
    update dict (without ``findings``, attached by the caller) and the set of
    included activity codes (used for the between-update churn annotation)."""
    dp = driving_path(schedule, tolerance_hours=tolerance_hours)
    driving_codes = set(dp.codes)
    driving_pairs = {(dp.steps[i].code, dp.steps[i + 1].code)
                     for i in range(len(dp.steps) - 1)}

    uid_to_code = {a.uid: a.code for a in schedule.activities.values()}

    candidates: dict[str, Activity] = {}
    for a in schedule.real_activities:
        cal = schedule.cal_for(a)
        fl = a.total_float_days(cal)
        if a.code in driving_codes or (fl is not None and fl <= near_days):
            candidates[a.code] = a

    candidate_count = len(candidates)

    # deterministic selection under the cap: the driving path is always kept
    # (it is the spine of the whole view); near-critical alternates fill the
    # remainder ranked by ascending float (tightest first), code tie-break.
    driving_list = sorted(c for c in candidates if c in driving_codes)

    def fl_key(code: str):
        a = candidates[code]
        fl = a.total_float_days(schedule.cal_for(a))
        return (fl if fl is not None else 1e9, code)

    other_sorted = sorted((c for c in candidates if c not in driving_codes),
                          key=fl_key)
    included = list(driving_list)
    remaining_cap = max(node_cap - len(included), 0)
    included += other_sorted[:remaining_cap]
    included_set = set(included)
    truncated = candidate_count > len(included_set)

    nodes = []
    for code in sorted(included_set):
        a = candidates[code]
        cal, cal_label = _calendar_label(schedule, a)
        wbs_code, wbs_name = _wbs_label(schedule, a)
        nodes.append({
            "code": a.code,
            "name": a.name or "",
            "start": _iso(a.start),
            "finish": _iso(a.finish),
            "float_days": a.total_float_days(cal),
            "calendar": cal_label,
            "constraint": _constraint_label(a),
            "wbs_code": wbs_code,
            "wbs_name": wbs_name,
            "band": "driving" if code in driving_codes else "near_critical",
            "completed": bool(a.completed),
            "pct_complete": a.pct_complete,
        })

    edge_keys = set()
    edges = []
    for r in schedule.relationships:
        pc = uid_to_code.get(r.pred_uid)
        sc = uid_to_code.get(r.succ_uid)
        if pc is None or sc is None or pc not in included_set or sc not in included_set:
            continue
        key = (pc, sc, r.rtype.value, r.lag_hours)
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append({
            "pred": pc, "succ": sc, "rel_type": r.rtype.value,
            "lag_hours": r.lag_hours,
            "driving": (pc, sc) in driving_pairs,
        })
    edges.sort(key=lambda e: (e["pred"], e["succ"], e["rel_type"], e["lag_hours"]))

    update = {
        "label": schedule.label(),
        "data_date": _iso(schedule.data_date),
        "target_code": dp.target.code if dp.target else None,
        "target_reason": dp.reason or "",
        "near_days": near_days,
        "nodes": nodes,
        "edges": edges,
        "candidate_count": candidate_count,
        "included_count": len(included_set),
        "truncated": truncated,
    }
    return update, included_set


def _build_findings(assessment) -> list[dict]:
    """Per-file check findings: check id/name/severity + the object ids they
    name, so the JS can highlight matching network nodes on click."""
    out = []
    if assessment is None:
        return out
    for r in assessment.results:
        if not r.findings:
            continue
        obj_ids = sorted({f.object_id for f in r.findings if f.object_id})
        detail_by_id: dict[str, str] = {}
        for f in r.findings:
            if f.object_id and f.object_id not in detail_by_id:
                detail_by_id[f.object_id] = f.detail
        out.append({
            "check_id": r.check.id,
            "check_name": r.check.name,
            "severity": r.check.severity,
            "status": r.status,
            "object_ids": obj_ids,
            "details": [{"object_id": oid, "detail": detail_by_id.get(oid, "")}
                       for oid in obj_ids],
        })
    out.sort(key=lambda f: (f["check_id"],))
    return out


def _churn(prev_codes: set, cur_codes: set, prev_label: str, cur_label: str) -> dict:
    return {
        "from_label": prev_label,
        "to_label": cur_label,
        "entered": sorted(cur_codes - prev_codes),
        "left": sorted(prev_codes - cur_codes),
    }


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def write_cockpit(sa: SeriesAnalysis, out_path: str,
                  near_days: float = DEFAULT_NEAR_DAYS,
                  node_cap: int = DEFAULT_NODE_CAP,
                  tolerance_hours: float = DEFAULT_TOL_HOURS) -> str:
    """Render the interactive network cockpit for ``sa`` to ``out_path``.

    Degrades gracefully: a single-file "series" still renders (the update
    slider is simply hidden by the JS when there is only one update), and an
    update with no recoverable driving/near-critical path renders a message
    in place of the network view rather than raising.  Never raises on
    well-formed input.
    """
    updates: list[dict] = []
    code_sets: list[set] = []
    for i, schedule in enumerate(sa.schedules):
        upd, included_set = _build_update(schedule, near_days, node_cap, tolerance_hours)
        assessment = sa.assessments[i] if i < len(sa.assessments) else None
        upd["findings"] = _build_findings(assessment)
        updates.append(upd)
        code_sets.append(included_set)

    churn = [
        _churn(code_sets[i], code_sets[i + 1], updates[i]["label"], updates[i + 1]["label"])
        for i in range(len(updates) - 1)
    ]

    blob: dict[str, Any] = {
        "version": 1,
        "footer": FOOTER_TEXT,
        "near_days": near_days,
        "node_cap": node_cap,
        "is_series": len(updates) > 1,
        "updates": updates,
        "churn": churn,
    }
    json_text = json.dumps(blob, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    html = _HTML_HEAD + json_text + _HTML_TAIL

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return out_path


# ---------------------------------------------------------------------------
# static HTML/CSS/JS (inline, self-contained; no external requests)
# ---------------------------------------------------------------------------
_HTML_HEAD = """<title>ScheduleIQ Network Cockpit</title>
<meta charset="utf-8">
<style>
  :root {
    --teal: #1F6F7B;
    --amber: #FFC000;
    --gray: #7F7F7F;
    --light-gray: #BFBFBF;
    --crit-red: #B00020;
    --ink: #1B1B1B;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    color: var(--ink); background: #FFFFFF;
  }
  #app { display: flex; flex-direction: column; height: 100vh; }
  header {
    background: var(--teal); color: #FFFFFF; padding: 10px 16px;
    display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; letter-spacing: .01em; }
  header .sub { font-size: 11px; opacity: .85; }
  #controls {
    display: flex; align-items: center; gap: 14px; padding: 8px 16px;
    border-bottom: 1px solid #DDD; flex-wrap: wrap; font-size: 12px;
  }
  #controls label { display: flex; align-items: center; gap: 6px; }
  #slider-wrap { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 240px; }
  #slider-wrap input[type=range] { flex: 1; }
  button.viewbtn {
    border: 1px solid var(--teal); background: #FFFFFF; color: var(--teal);
    padding: 4px 10px; border-radius: 3px; font-size: 12px; cursor: pointer;
  }
  button.viewbtn.active { background: var(--teal); color: #FFFFFF; }
  #main { flex: 1; display: flex; min-height: 0; }
  #network-pane { flex: 1; position: relative; overflow: hidden; border-right: 1px solid #DDD; }
  #findings-pane {
    width: 340px; min-width: 280px; overflow-y: auto; padding: 10px 12px;
    font-size: 12px; background: #FAFAFA;
  }
  #findings-pane h2 { font-size: 13px; margin: 4px 0 8px; color: var(--teal); }
  .check-group { margin-bottom: 10px; border: 1px solid #E3E3E3; border-radius: 4px; overflow: hidden; }
  .check-head {
    padding: 6px 8px; cursor: pointer; font-weight: 600; display: flex;
    justify-content: space-between; align-items: center;
  }
  .check-head.critical { background: #FBE4E7; color: var(--crit-red); }
  .check-head.warning { background: #FFF3CD; color: #7A5B00; }
  .check-head.info { background: #E7EEF0; color: var(--teal); }
  .finding-row {
    padding: 4px 8px; border-top: 1px solid #EEE; cursor: pointer;
  }
  .finding-row:hover { background: #EFEFEF; }
  .finding-row .oid { font-weight: 600; }
  .finding-row .detail { color: #555; display: block; font-size: 11px; }
  #node-detail {
    border-top: 2px solid var(--teal); margin-top: 10px; padding-top: 8px;
  }
  #node-detail h3 { font-size: 12px; margin: 0 0 4px; }
  #truncation-note {
    background: #FFF3CD; color: #7A5B00; font-size: 11px; padding: 4px 16px;
    display: none;
  }
  #churn-note { font-size: 11px; color: #444; padding: 4px 16px; background: #F0F5F5; display: none; }
  #empty-note { padding: 24px; color: #666; font-size: 13px; }
  svg#net { width: 100%; height: 100%; display: block; cursor: grab; background: #FFFFFF; }
  svg#net.grabbing { cursor: grabbing; }
  .bar-driving { fill: var(--teal); }
  .bar-near { fill: var(--amber); }
  .bar-selected { stroke: var(--crit-red); stroke-width: 2px; }
  .edge-driving { stroke: var(--teal); stroke-width: 1.6px; }
  .edge-normal { stroke: var(--light-gray); stroke-width: 1px; }
  .lane-label { font-size: 10px; fill: #555; }
  .axis-label { font-size: 9px; fill: #666; }
  .node-label { font-size: 9px; fill: #222; pointer-events: none; }
  #tooltip {
    position: absolute; pointer-events: none; background: #222; color: #fff;
    font-size: 11px; padding: 6px 8px; border-radius: 3px; max-width: 320px;
    display: none; z-index: 5; line-height: 1.4;
  }
  footer {
    padding: 6px 16px; font-size: 10.5px; color: #555; border-top: 1px solid #DDD;
    background: #FAFAFA;
  }
</style>
<div id="app">
  <header>
    <h1>ScheduleIQ Network Cockpit</h1>
    <span class="sub" id="hdr-sub"></span>
  </header>
  <div id="controls">
    <div id="slider-wrap">
      <label for="update-slider">Update:</label>
      <input type="range" id="update-slider" min="0" max="0" step="1" value="0">
      <span id="update-label"></span>
    </div>
    <label>Swimlanes:
      <button class="viewbtn active" id="lane-float" type="button">Float band</button>
      <button class="viewbtn" id="lane-wbs" type="button">WBS</button>
    </label>
    <button class="viewbtn" id="zoom-reset" type="button">Reset zoom</button>
  </div>
  <div id="truncation-note"></div>
  <div id="churn-note"></div>
  <div id="main">
    <div id="network-pane">
      <svg id="net" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600"></svg>
      <div id="empty-note" style="display:none;"></div>
      <div id="tooltip"></div>
    </div>
    <div id="findings-pane">
      <h2>Findings</h2>
      <div id="findings-list"></div>
      <div id="node-detail" style="display:none;"></div>
    </div>
  </div>
  <footer id="footer">PRELIMINARY — diagnostic explorer; tool-of-record dates; expert review required.</footer>
</div>
<script type="application/json" id="cockpit-data">"""

_HTML_TAIL = """</script>
<script>
(function () {
  "use strict";
  var raw = document.getElementById("cockpit-data").textContent;
  var DATA = JSON.parse(raw);

  document.getElementById("footer").textContent = DATA.footer;
  document.getElementById("hdr-sub").textContent =
    "near-critical band \\u2264 " + DATA.near_days + " working days of float";

  var state = {
    updateIndex: 0,
    laneMode: "float",
    selectedCodes: new Set(),
    vbox: { x: 0, y: 0, w: 1000, h: 600 }
  };

  var svg = document.getElementById("net");
  var tooltip = document.getElementById("tooltip");
  var emptyNote = document.getElementById("empty-note");
  var slider = document.getElementById("update-slider");
  var updateLabel = document.getElementById("update-label");
  var truncNote = document.getElementById("truncation-note");
  var churnNote = document.getElementById("churn-note");
  var findingsList = document.getElementById("findings-list");
  var nodeDetail = document.getElementById("node-detail");

  var NS = "http://www.w3.org/2000/svg"; // xmlns namespace URI for inline SVG creation (not a network request)
  function el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) { e.setAttribute(k, attrs[k]); }
    return e;
  }

  // ---- update slider setup -------------------------------------------
  var nUpdates = DATA.updates.length;
  slider.max = String(Math.max(nUpdates - 1, 0));
  if (!DATA.is_series) {
    document.getElementById("slider-wrap").style.display = "none";
  }

  slider.addEventListener("input", function () {
    state.updateIndex = parseInt(slider.value, 10);
    state.selectedCodes = new Set();
    render();
  });

  document.getElementById("lane-float").addEventListener("click", function () {
    setLaneMode("float");
  });
  document.getElementById("lane-wbs").addEventListener("click", function () {
    setLaneMode("wbs");
  });
  function setLaneMode(mode) {
    state.laneMode = mode;
    document.getElementById("lane-float").classList.toggle("active", mode === "float");
    document.getElementById("lane-wbs").classList.toggle("active", mode === "wbs");
    render();
  }

  document.getElementById("zoom-reset").addEventListener("click", function () {
    resetZoom();
  });

  // ---- helpers ----------------------------------------------------------
  function currentUpdate() { return DATA.updates[state.updateIndex]; }

  function laneKey(node) {
    if (state.laneMode === "wbs") {
      return node.wbs_code ? (node.wbs_code + " " + (node.wbs_name || "")) : "(no WBS)";
    }
    if (node.band === "driving") { return "0 \\u2014 Driving path"; }
    var fl = node.float_days;
    if (fl === null || fl === undefined) { return "9 \\u2014 Float unknown"; }
    var bucket = Math.min(4, Math.max(0, Math.floor(fl / 2)));
    var lo = bucket * 2, hi = lo + 2;
    return (1 + bucket) + " \\u2014 " + lo + "\\u2013" + hi + "d float";
  }

  function fmtDate(iso) {
    if (!iso) { return "\\u2014"; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return iso; }
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return d.getUTCDate() + " " + months[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  // ---- rendering ----------------------------------------------------------
  function render() {
    var upd = currentUpdate();
    updateLabel.textContent = upd ? (upd.label + (upd.data_date ? " (DD " + fmtDate(upd.data_date) + ")" : "")) : "";

    // truncation disclosure
    if (upd && upd.truncated) {
      truncNote.style.display = "block";
      truncNote.textContent = "Showing " + upd.included_count + " of " + upd.candidate_count +
        " driving/near-critical activities (capped at " + DATA.node_cap + " nodes per update).";
    } else {
      truncNote.style.display = "none";
    }

    // churn annotation vs previous update
    if (state.updateIndex > 0 && DATA.churn.length >= state.updateIndex) {
      var c = DATA.churn[state.updateIndex - 1];
      var bits = [];
      if (c.entered.length) { bits.push(c.entered.length + " entered band: " + c.entered.slice(0, 12).join(", ") + (c.entered.length > 12 ? ", \\u2026" : "")); }
      if (c.left.length) { bits.push(c.left.length + " left band: " + c.left.slice(0, 12).join(", ") + (c.left.length > 12 ? ", \\u2026" : "")); }
      if (bits.length) {
        churnNote.style.display = "block";
        churnNote.textContent = c.from_label + " \\u2192 " + c.to_label + ": " + bits.join("; ") + ".";
      } else {
        churnNote.style.display = "block";
        churnNote.textContent = c.from_label + " \\u2192 " + c.to_label + ": band unchanged.";
      }
    } else {
      churnNote.style.display = "none";
    }

    while (svg.firstChild) { svg.removeChild(svg.firstChild); }

    if (!upd || upd.nodes.length === 0) {
      emptyNote.style.display = "block";
      var reason = (upd && upd.target_reason) ? upd.target_reason : "no driving/near-critical path could be recovered for this update.";
      emptyNote.textContent = "No network to display: " + reason;
      renderFindings();
      return;
    }
    emptyNote.style.display = "none";

    var nodes = upd.nodes;
    var byCode = {};
    nodes.forEach(function (n) { byCode[n.code] = n; });

    var timed = nodes.filter(function (n) { return n.start && n.finish; });
    var untimedCount = nodes.length - timed.length;

    var minT = null, maxT = null;
    timed.forEach(function (n) {
      var s = new Date(n.start).getTime(), f = new Date(n.finish).getTime();
      if (minT === null || s < minT) { minT = s; }
      if (maxT === null || f > maxT) { maxT = f; }
    });
    if (minT === null) {
      emptyNote.style.display = "block";
      emptyNote.textContent = "No activity in this update carries a usable record start/finish date.";
      renderFindings();
      return;
    }
    if (maxT === minT) { maxT = minT + 24 * 3600 * 1000; }

    var margin = { left: 150, right: 30, top: 30, bottom: 30 };
    var plotW = 1400;
    var rowH = 20, rowGap = 4, laneGap = 14, laneLabelH = 14;

    // group into lanes, then pack rows within each lane (interval packing)
    var lanes = {};
    timed.forEach(function (n) {
      var k = laneKey(n);
      (lanes[k] = lanes[k] || []).push(n);
    });
    var laneKeys = Object.keys(lanes).sort();

    function xOf(iso) {
      var t = new Date(iso).getTime();
      return margin.left + (t - minT) / (maxT - minT) * plotW;
    }

    var y = margin.top;
    var placed = [];   // {node, x1, x2, y, lane}
    laneKeys.forEach(function (lk) {
      var members = lanes[lk].slice().sort(function (a, b) {
        return new Date(a.start) - new Date(b.start);
      });
      var rowEnds = [];   // end-x of the last bar placed in each row
      var laneTop = y + laneLabelH;
      var maxRow = 0;
      members.forEach(function (n) {
        var x1 = xOf(n.start), x2 = Math.max(xOf(n.finish), x1 + 3);
        var row = 0;
        while (row < rowEnds.length && rowEnds[row] > x1 - 2) { row++; }
        rowEnds[row] = x2;
        if (row > maxRow) { maxRow = row; }
        placed.push({ node: n, x1: x1, x2: x2, y: laneTop + row * (rowH + rowGap), lane: lk });
      });
      var laneRows = rowEnds.length || 1;
      var laneHeight = laneLabelH + laneRows * (rowH + rowGap);
      placed.push({ laneLabelAt: y, laneKey: lk });
      y += laneHeight + laneGap;
    });
    var totalH = y + margin.bottom;
    var totalW = margin.left + plotW + margin.right;

    state.vbox = { x: 0, y: 0, w: totalW, h: totalH };
    applyViewBox();

    // time axis (top)
    var nTicks = 8;
    for (var i = 0; i <= nTicks; i++) {
      var t = minT + (maxT - minT) * (i / nTicks);
      var xx = margin.left + plotW * (i / nTicks);
      var line = el("line", { x1: xx, x2: xx, y1: margin.top - 6, y2: totalH - margin.bottom, stroke: "#EEEEEE" });
      svg.appendChild(line);
      var lbl = el("text", { x: xx, y: margin.top - 10, class: "axis-label", "text-anchor": "middle" });
      lbl.textContent = fmtDate(new Date(t).toISOString());
      svg.appendChild(lbl);
    }

    // lane labels
    placed.filter(function (p) { return p.laneKey; }).forEach(function (p) {
      var lbl = el("text", { x: 4, y: p.laneLabelAt + laneLabelH - 2, class: "lane-label" });
      lbl.textContent = p.laneKey;
      svg.appendChild(lbl);
    });

    // edges (drawn before bars so bars sit on top)
    var barByCode = {};
    placed.filter(function (p) { return p.node; }).forEach(function (p) {
      barByCode[p.node.code] = p;
    });
    upd.edges.forEach(function (e) {
      var a = barByCode[e.pred], b = barByCode[e.succ];
      if (!a || !b) { return; }
      var x1 = a.x2, y1 = a.y + rowH / 2, x2 = b.x1, y2 = b.y + rowH / 2;
      var path = el("path", {
        d: "M" + x1 + "," + y1 + " C" + (x1 + 20) + "," + y1 + " " + (x2 - 20) + "," + y2 + " " + x2 + "," + y2,
        fill: "none",
        class: e.driving ? "edge-driving" : "edge-normal"
      });
      svg.appendChild(path);
    });

    // bars
    placed.filter(function (p) { return p.node; }).forEach(function (p) {
      var n = p.node;
      var g = el("g", { "data-code": n.code });
      var rect = el("rect", {
        x: p.x1, y: p.y, width: Math.max(p.x2 - p.x1, 3), height: rowH,
        rx: 2, ry: 2,
        class: (n.band === "driving" ? "bar-driving" : "bar-near") +
               (state.selectedCodes.has(n.code) ? " bar-selected" : "")
      });
      g.appendChild(rect);
      if (p.x2 - p.x1 > 26) {
        var lbl = el("text", { x: p.x1 + 3, y: p.y + rowH - 6, class: "node-label" });
        lbl.textContent = n.code;
        g.appendChild(lbl);
      }
      g.addEventListener("mouseenter", function (ev) { showTooltip(ev, n); });
      g.addEventListener("mousemove", function (ev) { positionTooltip(ev); });
      g.addEventListener("mouseleave", hideTooltip);
      g.addEventListener("click", function () { selectNode(n.code); });
      svg.appendChild(g);
    });

    if (untimedCount > 0) {
      var note = el("text", { x: margin.left, y: totalH - 6, class: "axis-label" });
      note.textContent = untimedCount + " activity(ies) with no record start/finish are omitted from the timeline (still listed in Findings).";
      svg.appendChild(note);
    }

    renderFindings();
  }

  function showTooltip(ev, n) {
    tooltip.style.display = "block";
    tooltip.innerHTML =
      "<b>" + n.code + "</b> " + (n.name || "") + "<br>" +
      "Start: " + fmtDate(n.start) + " &nbsp; Finish: " + fmtDate(n.finish) + "<br>" +
      "Float: " + (n.float_days === null || n.float_days === undefined ? "\\u2014" : n.float_days.toFixed(1) + "d") +
      " &nbsp; Calendar: " + (n.calendar || "\\u2014") + "<br>" +
      (n.constraint ? ("Constraint: " + n.constraint + "<br>") : "") +
      (n.wbs_code ? ("WBS: " + n.wbs_code + " " + (n.wbs_name || "") + "<br>") : "") +
      "Band: " + (n.band === "driving" ? "Driving path" : "Near-critical") +
      " &nbsp; " + n.pct_complete.toFixed(0) + "% complete";
    positionTooltip(ev);
  }
  function positionTooltip(ev) {
    var rect = document.getElementById("network-pane").getBoundingClientRect();
    tooltip.style.left = (ev.clientX - rect.left + 12) + "px";
    tooltip.style.top = (ev.clientY - rect.top + 12) + "px";
  }
  function hideTooltip() { tooltip.style.display = "none"; }

  // ---- findings panel -----------------------------------------------------
  function renderFindings() {
    var upd = currentUpdate();
    findingsList.innerHTML = "";
    nodeDetail.style.display = "none";
    if (!upd || !upd.findings.length) {
      findingsList.textContent = "No check findings recorded for this update.";
      return;
    }
    upd.findings.forEach(function (grp) {
      var box = document.createElement("div");
      box.className = "check-group";
      var head = document.createElement("div");
      head.className = "check-head " + grp.severity;
      head.textContent = grp.check_id + " \\u2014 " + grp.check_name + " (" + grp.status + ")";
      box.appendChild(head);
      grp.details.forEach(function (d) {
        var row = document.createElement("div");
        row.className = "finding-row";
        var oid = document.createElement("span");
        oid.className = "oid";
        oid.textContent = d.object_id;
        row.appendChild(oid);
        if (d.detail) {
          var det = document.createElement("span");
          det.className = "detail";
          det.textContent = d.detail;
          row.appendChild(det);
        }
        row.addEventListener("click", function () {
          highlightFinding(grp.object_ids);
        });
        box.appendChild(row);
      });
      findingsList.appendChild(box);
    });
  }

  function highlightFinding(objectIds) {
    var upd = currentUpdate();
    var present = objectIds.filter(function (c) {
      return upd.nodes.some(function (n) { return n.code === c; });
    });
    state.selectedCodes = new Set(present);
    render_bars_only();
    if (present.length) { panToCode(present[0]); }
  }

  function selectNode(code) {
    state.selectedCodes = new Set([code]);
    render_bars_only();
    var upd = currentUpdate();
    var hits = upd.findings.filter(function (grp) { return grp.object_ids.indexOf(code) !== -1; });
    nodeDetail.style.display = "block";
    if (!hits.length) {
      nodeDetail.innerHTML = "<h3>" + code + "</h3>No findings reference this activity.";
      return;
    }
    var html = "<h3>" + code + " \\u2014 findings</h3>";
    hits.forEach(function (grp) {
      html += "<div><b>" + grp.check_id + "</b> " + grp.check_name + " (" + grp.status + ")</div>";
    });
    nodeDetail.innerHTML = html;
  }

  function render_bars_only() {
    // cheap re-render: recompute selection styling without a full relayout
    render();
  }

  function panToCode(code) {
    var upd = currentUpdate();
    var n = upd.nodes.filter(function (x) { return x.code === code; })[0];
    if (!n || !n.start) { return; }
    // re-run layout to find the bar's x by scanning the rendered SVG
    var g = svg.querySelector('g[data-code="' + cssEscape(code) + '"]');
    if (!g) { return; }
    var rect = g.querySelector("rect");
    var bx = parseFloat(rect.getAttribute("x"));
    var by = parseFloat(rect.getAttribute("y"));
    state.vbox.x = Math.max(0, bx - state.vbox.w / 2);
    state.vbox.y = Math.max(0, by - state.vbox.h / 2);
    applyViewBox();
  }

  function cssEscape(s) {
    return s.replace(/["\\\\]/g, "\\\\$&");
  }

  // ---- zoom / pan -----------------------------------------------------
  function applyViewBox() {
    var v = state.vbox;
    svg.setAttribute("viewBox", v.x + " " + v.y + " " + v.w + " " + v.h);
  }
  function resetZoom() { render(); }

  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var factor = ev.deltaY > 0 ? 1.1 : 0.9;
    var rect = svg.getBoundingClientRect();
    var mx = (ev.clientX - rect.left) / rect.width;
    var my = (ev.clientY - rect.top) / rect.height;
    var v = state.vbox;
    var cx = v.x + mx * v.w, cy = v.y + my * v.h;
    var nw = v.w * factor, nh = v.h * factor;
    v.x = cx - mx * nw;
    v.y = cy - my * nh;
    v.w = nw;
    v.h = nh;
    applyViewBox();
  }, { passive: false });

  var dragging = false, lastX = 0, lastY = 0;
  svg.addEventListener("mousedown", function (ev) {
    dragging = true; lastX = ev.clientX; lastY = ev.clientY;
    svg.classList.add("grabbing");
  });
  window.addEventListener("mousemove", function (ev) {
    if (!dragging) { return; }
    var rect = svg.getBoundingClientRect();
    var v = state.vbox;
    var dx = (ev.clientX - lastX) / rect.width * v.w;
    var dy = (ev.clientY - lastY) / rect.height * v.h;
    v.x -= dx; v.y -= dy;
    lastX = ev.clientX; lastY = ev.clientY;
    applyViewBox();
  });
  window.addEventListener("mouseup", function () {
    dragging = false;
    svg.classList.remove("grabbing");
  });

  render();
})();
</script>
"""
