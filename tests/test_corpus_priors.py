"""Tests for the internal benchmark corpus (S9, ANALYTICS_PROPOSAL.md §6.9) and
the offline duration-uncertainty priors (S10, §6.10).

Fixtures are built by tests/fixtures/make_fixtures.py.  Two real reviewed
projects are harvested into a corpus (the legacy demo series and the handshake
pair); the percentile and prior arithmetic is otherwise checked against
hand-built rows so every placement / quantile / MLE parameter / KM step is
exactly reproducible.
"""
import math
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load, load_many                              # noqa: E402
from scheduleiq.trend.series import analyze_series                         # noqa: E402
from scheduleiq.analytics.corpus import (                                  # noqa: E402
    BenchmarkCorpus, CorpusRow, MIN_CONTEXT_N, CORPUS_SCHEMA_VERSION)
from scheduleiq.analytics import priors as P                               # noqa: E402
from scheduleiq.analytics.priors import (                                  # noqa: E402
    GOVERNANCE, fit_duration_priors, to_uncertainty_spec, prior_report,
    _kaplan_meier)
from scheduleiq.analytics.montecarlo import UncertaintySpec, run_simulation  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(BASELINE) and os.path.exists(HS2)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def demo_series():
    return analyze_series(load_many([BASELINE, U1, U2]))


@pytest.fixture(scope="session")
def hs_series():
    return analyze_series(load_many([HS1, HS2]))


# a designed, evenly-spaced ratio set: 0.50, 0.55, ... 2.45 (n=40).
RATIOS40 = [round(0.5 + 0.05 * i, 2) for i in range(40)]


def _type7(sorted_vals, p):
    n = len(sorted_vals)
    rank = (p / 100.0) * (n - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return float(sorted_vals[lo])
    frac = rank - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# ======================================================================== S9 corpus
def test_add_two_real_projects_and_anonymization_blocklist(tmp_path, demo_series,
                                                           hs_series):
    c = BenchmarkCorpus(str(tmp_path / "corpus.jsonl"))
    r1 = c.add_project(demo_series, sector="demo")
    r2 = c.add_project(hs_series, sector="industrial")
    assert len(c.rows) == 2
    assert {r1.sector, r2.sector} == {"demo", "industrial"}
    assert r1.schema_version == CORPUS_SCHEMA_VERSION
    # harvested outcomes are present
    assert r1.health_score is not None and r1.checks
    assert r1.ratio_meta.get("source") == "montecarlo.calibrate_from_series"
    assert "float_quantiles_days" in r1.series_stats
    assert r1.series_stats["update_cadence"]["n_updates"] == 3

    # ANONYMIZATION: the raw JSONL text carries no project names/ids, no source
    # file, and no activity names from either source project.
    text = (tmp_path / "corpus.jsonl").read_text()
    forbidden = set()
    for sa in (demo_series, hs_series):
        for s in sa.schedules:
            for tok in (s.project_name, s.project_id, s.source_file):
                if tok and len(str(tok)) >= 3:
                    forbidden.add(str(tok))
                    forbidden.add(os.path.basename(str(tok)))
            for a in s.activities.values():
                if a.name and len(a.name) >= 3:
                    forbidden.add(a.name)
    leaked = sorted(t for t in forbidden if t and t in text)
    assert leaked == [], f"anonymization leak: {leaked}"
    assert "DEMO-PLANT" not in text


def test_dedup_replaces_on_readd(tmp_path, demo_series):
    c = BenchmarkCorpus(str(tmp_path / "corpus.jsonl"))
    r1 = c.add_project(demo_series, sector="demo")
    n_lines_1 = len((tmp_path / "corpus.jsonl").read_text().splitlines())
    r2 = c.add_project(demo_series, sector="demo")     # same sources -> same id
    assert r1.corpus_id == r2.corpus_id
    assert len(c.rows) == 1                            # replaced, not appended
    n_lines_2 = len((tmp_path / "corpus.jsonl").read_text().splitlines())
    assert n_lines_2 == n_lines_1 == 1
    assert any("REPLACED" in d for d in c.load_disclosures)


def test_corruption_tolerant_load(tmp_path, demo_series, hs_series):
    path = tmp_path / "corpus.jsonl"
    c = BenchmarkCorpus(str(path))
    c.add_project(demo_series, sector="demo")
    c.add_project(hs_series, sector="industrial")
    # inject a corrupt line in the middle
    lines = path.read_text().splitlines()
    lines.insert(1, "{not valid json at all")
    path.write_text("\n".join(lines) + "\n")
    c2 = BenchmarkCorpus(str(path))
    assert len(c2.rows) == 2                            # the bad line is skipped
    assert any("skipped" in d for d in c2.load_disclosures)


def test_context_for_percentile_math_hand_computed(tmp_path):
    """Six-row corpus with known values -> exact p25/p50/p75 and placements."""
    c = BenchmarkCorpus(str(tmp_path / "ctx.jsonl"))
    m1 = [10, 20, 30, 40, 50, 60]
    m2 = [100, 200, 300, 400, 500, 600]
    health = [50, 60, 70, 80, 90, 100]
    for i in range(6):
        c.add_row(CorpusRow(
            corpus_id=f"r{i}", sector="proc",
            checks={"M1": {"value": m1[i], "status": "INFO"},
                    "M2": {"value": m2[i], "status": "INFO"}},
            health_score=health[i]))

    ctx = c.context_for({"M1": 35, "M2": 50, "health_score": 85}, sector="proc")
    assert not ctx.refused and ctx.n == 6

    a = ctx.metrics["M1"]
    assert (a.corpus_p25, a.corpus_p50, a.corpus_p75) == (22.5, 35.0, 47.5)
    assert a.placement_pct == 50.0                     # 3 of 6 at or below 35
    assert a.quartile_phrase() == "the second quartile (below the median)"

    # M2 = 50 is below every peer -> bottom quartile (the §6.9 headline line)
    b = ctx.metrics["M2"]
    assert b.placement_pct == 0.0
    assert b.quartile_phrase() == "the bottom quartile"
    line = ctx.line("M2", sector_label="process-plant")
    assert line == ("M2 = 50 — in the bottom quartile of process-plant "
                    "schedules LI has reviewed (n=6).")

    h = ctx.metrics["health_score"]
    assert (h.corpus_p25, h.corpus_p50, h.corpus_p75) == (62.5, 75.0, 87.5)
    assert h.placement_pct == round(100.0 * 4 / 6, 2)  # 66.67


def test_context_for_small_n_refusal(tmp_path):
    c = BenchmarkCorpus(str(tmp_path / "sn.jsonl"))
    for i in range(MIN_CONTEXT_N - 1):                 # 4 rows < 5
        c.add_row(CorpusRow(corpus_id=f"x{i}", sector="s",
                            checks={"M1": {"value": i, "status": "INFO"}}))
    ctx = c.context_for({"M1": 2}, sector="s")
    assert ctx.refused is True and ctx.n == MIN_CONTEXT_N - 1
    assert not ctx.metrics
    assert any("refused" in d for d in ctx.disclosures)


def test_sector_filter_isolation(tmp_path):
    c = BenchmarkCorpus(str(tmp_path / "sec.jsonl"))
    for i in range(6):
        c.add_row(CorpusRow(corpus_id=f"a{i}", sector="alpha",
                            checks={"M1": {"value": i, "status": "INFO"}}))
    # a different sector has no peers -> refused
    ctx = c.context_for({"M1": 2}, sector="beta")
    assert ctx.refused and ctx.n == 0


def test_to_dict_roundtrip_deterministic(tmp_path):
    row = CorpusRow(corpus_id="z", sector="s",
                    checks={"M1": {"value": 1.0, "status": "INFO"}},
                    ratio_sample=[1.0, 2.0], censored_sample=[1.5])
    assert CorpusRow.from_dict(row.to_dict()).to_dict() == row.to_dict()


# ======================================================================== S10 priors
def _priors_corpus(tmp_path):
    c = BenchmarkCorpus(str(tmp_path / "priors.jsonl"))
    c.add_row(CorpusRow(corpus_id="P", sector="p",
                        ratio_sample=RATIOS40, censored_sample=[1.2, 1.8]))
    c.add_row(CorpusRow(corpus_id="NC", sector="nc",
                        ratio_sample=RATIOS40, censored_sample=[]))
    c.add_row(CorpusRow(corpus_id="Q", sector="q",
                        ratio_sample=RATIOS40[:5], censored_sample=[]))
    return c


def test_empirical_quantiles_exact(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="p", min_n=30)
    assert pr.fitted and pr.n == 40
    e = pr.empirical
    assert e["mean"] == pytest.approx(1.475)
    assert e["p10"] == pytest.approx(_type7(RATIOS40, 10.0))
    assert e["p25"] == pytest.approx(_type7(RATIOS40, 25.0))
    assert e["p50"] == pytest.approx(1.475)            # midpoint of the spread
    assert e["p90"] == pytest.approx(_type7(RATIOS40, 90.0))
    assert (e["min"], e["max"]) == (0.5, 2.45)


def test_lognormal_mle_parameters_hand_computed(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="p", min_n=30)
    logs = [math.log(r) for r in RATIOS40]
    n = len(logs)
    mu = sum(logs) / n
    sigma = math.sqrt(sum((x - mu) ** 2 for x in logs) / n)   # MLE (population)
    assert pr.lognormal["method"] == "lognormal_mle"
    assert pr.lognormal["mu"] == pytest.approx(mu)
    assert pr.lognormal["sigma"] == pytest.approx(sigma)
    # KS statistic sanity-bounded
    ks = pr.lognormal["ks_stat"]
    assert 0.0 <= ks <= 1.0
    assert ks < 0.5                                     # a roughly-fitting sample


def test_min_n_refusal(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="q", min_n=30)
    assert pr.fitted is False and pr.n == 5
    assert "NOT FITTED" in pr.reason
    assert pr.lognormal is None and pr.survival is None
    with pytest.raises(ValueError):
        to_uncertainty_spec(pr)


def test_kaplan_meier_step_hand_computed():
    """events {1,2,3}, one censored at 2.5 -> hand-computed KM steps."""
    km = _kaplan_meier([1.0, 2.0, 3.0], [2.5])
    assert km["n_total"] == 4 and km["n_events"] == 3 and km["n_censored"] == 1
    steps = km["steps"]
    # t=1: at risk 4, S = 1*(1-1/4) = 0.75
    assert steps[0] == {"t": 1.0, "at_risk": 4, "events": 1, "survival": 0.75}
    # t=2: at risk 3 (2, 2.5, 3), S = 0.75*(1-1/3) = 0.5
    assert steps[1] == {"t": 2.0, "at_risk": 3, "events": 1, "survival": 0.5}
    # t=3: at risk 1, S = 0.5*(1-1/1) = 0.0
    assert steps[2] == {"t": 3.0, "at_risk": 1, "events": 1, "survival": 0.0}
    assert km["median_ratio"] == 2.0


def test_survival_present_with_censored_and_skipped_without(tmp_path):
    c = _priors_corpus(tmp_path)
    p_cen = fit_duration_priors(c, sector="p", min_n=30)
    assert p_cen.survival is not None
    assert p_cen.survival["n_censored"] == 2
    assert p_cen.provenance()["censoring"]["n_censored"] == 2
    assert any("Kaplan-Meier" in d for d in p_cen.disclosures)

    p_none = fit_duration_priors(c, sector="nc", min_n=30)
    assert p_none.survival is None
    assert any("no censored" in d for d in p_none.disclosures)


def test_governance_on_every_output(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="p", min_n=30)
    assert pr.to_dict()["governance"] == GOVERNANCE
    assert prior_report(pr)["governance"] == GOVERNANCE
    emp = to_uncertainty_spec(pr)
    assert GOVERNANCE in emp.disclosures
    # the provenance block threads corpus n / sectors / fit / KS / censoring
    prov = pr.to_dict()["provenance"]
    assert prov["corpus_n"] == 40 and prov["sectors"] == ["p"]
    assert prov["fit_method"] == "lognormal_mle"
    assert prov["ks_stat"] is not None
    assert prov["censoring"]["n_censored"] == 2


def test_determinism_fit_and_report(tmp_path):
    c = _priors_corpus(tmp_path)
    a = fit_duration_priors(c, sector="p", min_n=30)
    b = fit_duration_priors(c, sector="p", min_n=30)
    assert a.to_dict() == b.to_dict()
    assert prior_report(a) == prior_report(b)


def test_to_uncertainty_spec_runs_simulation_and_threads_provenance(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="p", min_n=30)
    emp = to_uncertainty_spec(pr, dist="empirical")
    hs2 = load(HS2)[0]
    res = run_simulation(hs2, spec=UncertaintySpec(empirical=emp),
                         iterations=100, seed=7)
    d = res.to_dict()
    assert d["iterations"] == 100
    # every varying activity resolved to the empirical (research-prior) tier
    tiers = {p["tier"] for p in d["input_provenance"]}
    assert tiers == {"empirical"}
    # the governance + provenance strings THREAD THROUGH into the simulation's
    # disclosures (montecarlo appends spec.empirical.disclosures verbatim)
    assert any("RESEARCH PRIOR" in x for x in d["disclosures"])
    assert any("RESEARCH-PRIOR PROVENANCE" in x for x in d["disclosures"])


def test_to_uncertainty_spec_lognormal_mode_runs(tmp_path):
    pr = fit_duration_priors(_priors_corpus(tmp_path), sector="p", min_n=30)
    emp = to_uncertainty_spec(pr, dist="lognormal")
    assert emp.method == "lognormal"
    hs2 = load(HS2)[0]
    res = run_simulation(hs2, spec=UncertaintySpec(empirical=emp),
                         iterations=50, seed=7)
    assert res.iterations == 50
    assert GOVERNANCE in "\n".join(res.to_dict()["disclosures"])
