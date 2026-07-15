"""End-to-end regression for NET-006 parallel-edge false positives."""

import os
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.cpm.bridge import build_engine_inputs  # noqa: E402
from scheduleiq.cpm.handshake import run_handshake  # noqa: E402
from scheduleiq.cpm.network import ActivityNetwork, topological_sort  # noqa: E402
from scheduleiq.cpm.validation import NetworkValidator  # noqa: E402
from scheduleiq.ingest import parse_xer  # noqa: E402


FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "net006_parallel_pair.xer"
)


def test_micro_xer_parallel_pair_survives_parse_bridge_validate_handshake():
    """A typed parallel pair remains two scheduling constraints, not a cycle."""
    schedule = parse_xer(FIXTURE)[0]
    inputs = build_engine_inputs(schedule)

    validation = NetworkValidator(inputs.activities, inputs.relationships)
    assert validation.check_circular_logic() == []
    assert {issue.issue_code for issue in validation.validate_all().issues} == set()

    order = topological_sort(ActivityNetwork(inputs.activities, inputs.relationships))
    assert order == ["A", "B"]

    handshake = run_handshake(schedule)
    assert handshake.engine_is_valid is True
    assert handshake.blocking_issues == []
