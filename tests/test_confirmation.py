"""Tests for the prompt-before-execute policy and its use by the gates.

confirmation_policy() is a pure function; the process_query tests below
check that the gates actually honour it (and the `safety` config key).
"""
import pytest
from test_process_query import FakeCompletedProcess, make_input

import nlsh


class TestConfirmationPolicy:
    """confirmation_policy(verdict, safety, ask_flag) -> (must_prompt, default_yes).

    verdict is the QA verdict for the selected command, or None when there
    is none (review disabled or failed).
    """

    @pytest.mark.parametrize("ask_flag", [False, True])
    def test_safety_on_pass_prompts_with_default_yes(self, ask_flag):
        assert nlsh.confirmation_policy("PASS", True, ask_flag) == (True, True)

    def test_safety_off_pass_runs_without_prompt(self):
        assert nlsh.confirmation_policy("PASS", False, False) == (False, True)

    def test_ask_flag_forces_prompt_for_pass_even_with_safety_off(self):
        assert nlsh.confirmation_policy("PASS", False, True) == (True, True)

    @pytest.mark.parametrize("verdict", ["WARN", "MISS", None])
    @pytest.mark.parametrize("safety", [True, False])
    @pytest.mark.parametrize("ask_flag", [False, True])
    def test_non_pass_always_prompts_with_default_no(self, verdict, safety, ask_flag):
        assert nlsh.confirmation_policy(verdict, safety, ask_flag) == (True, False)

    @pytest.mark.parametrize("safety", [True, False])
    def test_fail_never_defaults_to_yes(self, safety):
        # FAIL is blocked before the policy is consulted; if it ever reaches
        # it, it must not be weaker than WARN.
        assert nlsh.confirmation_policy("FAIL", safety, False) == (True, False)


class TestConfirmExecution:
    def test_enter_accepts_when_default_yes(self, monkeypatch):
        monkeypatch.setattr("builtins.input", make_input([""]))
        assert nlsh.confirm_execution(default_yes=True) is True

    def test_enter_declines_when_default_no(self, monkeypatch):
        monkeypatch.setattr("builtins.input", make_input([""]))
        assert nlsh.confirm_execution(default_yes=False) is False

    @pytest.mark.parametrize("answer", ["y", "Y", "yes", " YES "])
    def test_yes_accepts_when_default_no(self, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", make_input([answer]))
        assert nlsh.confirm_execution(default_yes=False) is True

    @pytest.mark.parametrize("answer", ["n", "no", "x"])
    def test_anything_else_declines_when_default_yes(self, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", make_input([answer]))
        assert nlsh.confirm_execution(default_yes=True) is False

    @pytest.mark.parametrize("default_yes", [True, False])
    def test_eof_means_no(self, monkeypatch, default_yes):
        monkeypatch.setattr("builtins.input", make_input([EOFError()]))
        assert nlsh.confirm_execution(default_yes=default_yes) is False

    def test_prompt_shows_the_default(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", make_input(["", ""]))
        nlsh.confirm_execution(default_yes=True)
        assert "[Y/n]" in capsys.readouterr().out
        nlsh.confirm_execution(default_yes=False)
        assert "[y/N]" in capsys.readouterr().out


@pytest.fixture
def config():
    cfg = nlsh.DEFAULT_CONFIG.copy()
    cfg["suggested_command_color"] = "blue"
    return cfg


def _setup(monkeypatch, qa_review, options=(("ls", "List"),)):
    options = list(options)
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(
        nlsh, "check_all_commands_availability", lambda *a, **k: [True] * len(options)
    )
    monkeypatch.setattr(nlsh, "qa_review", qa_review)
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    return run_calls


def _raise(*a, **k):
    raise RuntimeError("model unreachable")


def test_safety_on_pass_asks_before_executing_and_enter_runs(monkeypatch, config):
    run_calls = _setup(monkeypatch, lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["1", ""]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "ls"]]


def test_safety_on_pass_declined_does_not_execute(monkeypatch, config):
    run_calls = _setup(monkeypatch, lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["1", "n"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == []


def test_safety_off_pass_executes_without_prompt(monkeypatch, config):
    config["safety"] = False
    run_calls = _setup(monkeypatch, lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["1"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "ls"]]


def test_ask_flag_prompts_for_pass_even_with_safety_off(monkeypatch, config):
    config["safety"] = False
    run_calls = _setup(monkeypatch, lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["1", "n"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", True)

    assert run_calls == []


@pytest.mark.parametrize("safety", [True, False])
def test_warn_enter_defaults_to_no(monkeypatch, config, safety):
    config["safety"] = safety
    run_calls = _setup(monkeypatch, lambda *a, **k: [("WARN", "irreversible")])
    monkeypatch.setattr("builtins.input", make_input(["1", ""]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == []


@pytest.mark.parametrize("safety", [True, False])
def test_missing_verdict_prompts_with_default_no(monkeypatch, config, safety):
    """Command 2 got no verdict from the reviewer: it must not run on Enter."""
    config["safety"] = safety

    class FakeClient:
        def chat(self, **kwargs):
            return "1|PASS|"

    options = [("ls", "List"), ("rm -rf ~", "Wipe")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True, True])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd))
    monkeypatch.setattr("builtins.input", make_input(["2", ""]))

    nlsh.process_query(FakeClient(), config, "/bin/bash", "list", False)

    assert run_calls == []


@pytest.mark.parametrize("safety", [True, False])
def test_review_disabled_prompts_with_default_no(monkeypatch, config, safety):
    config["safety"] = safety
    config["qa_review"] = False
    run_calls = _setup(monkeypatch, lambda *a, **k: [])
    monkeypatch.setattr("builtins.input", make_input(["1", ""]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == []


@pytest.mark.parametrize("safety", [True, False])
def test_review_failure_prompts_with_default_no(monkeypatch, config, safety):
    config["safety"] = safety
    run_calls = _setup(monkeypatch, _raise)
    monkeypatch.setattr("builtins.input", make_input(["1", ""]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == []


def test_review_failure_runs_only_on_explicit_yes(monkeypatch, config):
    run_calls = _setup(monkeypatch, _raise)
    monkeypatch.setattr("builtins.input", make_input(["1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "ls"]]


def test_eof_at_confirmation_does_not_execute(monkeypatch, config):
    run_calls = _setup(monkeypatch, lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["1", EOFError()]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert result is True
    assert run_calls == []


def test_fail_is_still_blocked_with_safety_off(monkeypatch, capsys, config):
    config["safety"] = False
    run_calls = _setup(monkeypatch, lambda *a, **k: [("FAIL", "destroys data")])
    # decline the all-MISS/FAIL retry offer, then select the FAIL command
    monkeypatch.setattr("builtins.input", make_input(["n", "1"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == []
    assert "Command blocked by safety review" in capsys.readouterr().out
