import json
from pathlib import Path

import pytest

from bughound_agent import BugHoundAgent


SAMPLE = (
    Path(__file__).resolve().parents[1] / "sample_code" / "mixed_issues.py"
).read_text()
VALID_ISSUE = {
    "type": "Reliability",
    "severity": "High",
    "msg": "Bare except catches critical exceptions.",
}


class ReplayClient:
    """Replay a fixed analyzer response without spending API requests."""

    def __init__(self, response):
        self.response = response

    def complete(self, system_prompt, user_prompt):
        return self.response


@pytest.mark.parametrize(
    "response",
    [
        "[null]",
        "[42]",
        "[{}]",
        json.dumps([dict(VALID_ISSUE, severity="Critical")]),
        json.dumps([dict(VALID_ISSUE, severity="high")]),
        json.dumps([dict(VALID_ISSUE, msg=123)]),
        json.dumps([dict(VALID_ISSUE, type=" ")]),
        json.dumps([dict(VALID_ISSUE, msg="")]),
        json.dumps([{"type": "Reliability", "severity": "High"}]),
        json.dumps([VALID_ISSUE, None]),
        "not JSON",
    ],
)
def test_invalid_model_issues_trigger_complete_heuristic_fallback(response):
    agent = BugHoundAgent(client=ReplayClient(response))

    issues = agent.analyze(SAMPLE)

    assert issues == BugHoundAgent().analyze(SAMPLE)
    assert len(issues) == 3
    assert any("Falling back to heuristics" in log["message"] for log in agent.logs)


@pytest.mark.parametrize("issues", [[], [VALID_ISSUE]])
def test_valid_model_issues_are_accepted_without_fallback(issues):
    agent = BugHoundAgent(client=ReplayClient(json.dumps(issues)))

    assert agent.analyze(SAMPLE) == issues
    assert not any("Falling back" in log["message"] for log in agent.logs)
