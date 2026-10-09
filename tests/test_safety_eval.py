"""Offline tests for the opt-in safety-eval harness (no real model calls)."""
from evals import run_safety_eval

CASE = {"shell": "/bin/bash", "question": "q", "command": "ls", "explanation": "List"}


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.last_response = None

    def chat(self, *args, **kwargs):
        self.last_response = self._response
        return self._response


def test_parsed_verdict_is_reported_as_actual():
    outcome = run_safety_eval.run_case(FakeClient("1|FAIL|bad"), {"model": "m"}, CASE)
    assert outcome["actual"] == "FAIL"


def test_unparseable_response_is_not_reported_as_a_real_verdict():
    # qa_review() fills a missing verdict with WARN for runtime safety; the
    # eval must still see that the model itself returned nothing usable.
    outcome = run_safety_eval.run_case(FakeClient("garbage"), {"model": "m"}, CASE)
    assert outcome["actual"] is None
