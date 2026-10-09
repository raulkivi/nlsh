"""Tests for process_query's interactive selection/execution flow.

The LLM-calling layer (collect_unique_options, qa_review) and the
system-touching layer (subprocess.run, pyperclip, input()) are stubbed out
so these tests exercise process_query's own branching logic in isolation.
"""
import pytest

import nlsh


def make_input(responses):
    """Return a fake `input()` that yields each response in turn.

    A response that is an exception instance is raised instead of returned,
    so EOFError/KeyboardInterrupt can be simulated. Raises AssertionError if
    input() is called more times than the test scripted, converting an
    unexpected extra prompt into a clear failure instead of a hang.
    """
    it = iter(responses)

    def fake_input(*args, **kwargs):
        try:
            value = next(it)
        except StopIteration:
            raise AssertionError("input() called more times than the test expected")
        if isinstance(value, BaseException):
            raise value
        return value

    return fake_input


class FakeCompletedProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode


@pytest.fixture
def config():
    cfg = nlsh.DEFAULT_CONFIG.copy()
    cfg["suggested_command_color"] = "blue"
    return cfg


def test_executes_selected_command_on_success(monkeypatch, config):
    options = [("ls -la", "List files"), ("ls -a", "List all")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True, True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", ""), ("PASS", "")])
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    # safety is on by default: PASS still asks, and Enter means yes
    monkeypatch.setattr("builtins.input", make_input(["1", ""]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list files", False)

    assert result is True
    assert run_calls == [["/bin/bash", "-c", "ls -la"]]


def test_returns_false_when_no_options_generated(monkeypatch, config):
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: [])

    result = nlsh.process_query(object(), config, "/bin/bash", "do something", False)

    assert result is False


def test_blocks_execution_when_command_not_available(monkeypatch, capsys, config):
    options = [("fancytool --list", "List things")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [False])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda *a, **k: run_calls.append(a))
    monkeypatch.setattr("builtins.input", make_input(["1"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list things", False)

    assert result is True
    assert run_calls == []
    assert "not found in system" in capsys.readouterr().out


def test_blocks_execution_when_qa_verdict_is_fail(monkeypatch, capsys, config):
    options = [("rm -rf /", "Delete everything")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("FAIL", "destroys the filesystem")])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda *a, **k: run_calls.append(a))
    # A single FAIL verdict also trips the "all MISS/FAIL" retry offer first;
    # decline it ('n'), then make the actual selection ('1').
    monkeypatch.setattr("builtins.input", make_input(["n", "1"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "delete everything", False)

    assert result is True
    assert run_calls == []
    assert "Command blocked by safety review" in capsys.readouterr().out


def test_warn_verdict_declined_by_user(monkeypatch, config):
    options = [("mv a b", "Move file")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("WARN", "irreversible")])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda *a, **k: run_calls.append(a))
    monkeypatch.setattr("builtins.input", make_input(["1", "n"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "move file", False)

    assert result is True
    assert run_calls == []


def test_warn_verdict_confirmed_with_explicit_yes(monkeypatch, config):
    options = [("mv a b", "Move file")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("WARN", "irreversible")])
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    monkeypatch.setattr("builtins.input", make_input(["1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "move file", False)

    assert run_calls == [["/bin/bash", "-c", "mv a b"]]


def test_ask_flag_confirmation_declined(monkeypatch, config):
    options = [("touch f", "Create file")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda *a, **k: run_calls.append(a))
    monkeypatch.setattr("builtins.input", make_input(["1", "n"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "create file", ask_flag=True)

    assert result is True
    assert run_calls == []


def test_ask_flag_confirmation_accepted(monkeypatch, config):
    options = [("touch f", "Create file")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [])
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    monkeypatch.setattr("builtins.input", make_input(["1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "create file", ask_flag=True)

    assert run_calls == [["/bin/bash", "-c", "touch f"]]


def test_user_cancels_with_n(monkeypatch, config):
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])
    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda *a, **k: run_calls.append(a))
    monkeypatch.setattr("builtins.input", make_input(["n"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert result is True
    assert run_calls == []


def test_invalid_selection_takes_no_action(monkeypatch, capsys, config):
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr("builtins.input", make_input(["zzz"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert "No action taken." in capsys.readouterr().out


def test_copy_to_clipboard(monkeypatch, capsys, config):
    options = [("ls", "List"), ("pwd", "Dir")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True, True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", ""), ("PASS", "")])
    monkeypatch.setenv("DISPLAY", ":0")
    copied = []
    monkeypatch.setattr(nlsh.pyperclip, "copy", lambda text: copied.append(text))
    monkeypatch.setattr("builtins.input", make_input(["c", "2"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert copied == ["pwd"]
    assert "Copied command to clipboard." in capsys.readouterr().out


def test_copy_blocked_without_display(monkeypatch, capsys, config):
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr("builtins.input", make_input(["c"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert result is True
    assert "Clipboard not available without DISPLAY." in capsys.readouterr().out


def test_qa_review_skipped_when_disabled_in_config(monkeypatch, config):
    config["qa_review"] = False
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    qa_calls = []
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: qa_calls.append(1) or [])
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    # an unreviewed command needs an explicit yes
    monkeypatch.setattr("builtins.input", make_input(["1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert qa_calls == []
    assert run_calls == [["/bin/bash", "-c", "ls"]]


def test_qa_review_failure_is_caught_and_execution_needs_explicit_yes(monkeypatch, capsys, config):
    """qa_review failing is caught; the command runs only after an explicit yes."""
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])

    def raise_error(*a, **k):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(nlsh, "qa_review", raise_error)
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    monkeypatch.setattr("builtins.input", make_input(["1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "ls"]]
    assert "QA safety review failed" in capsys.readouterr().out


def test_all_miss_or_fail_offers_retry_and_falls_back_to_original_when_declined(monkeypatch, config):
    options = [("ls", "List")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("MISS", "doesn't answer the question")])
    run_calls = []
    monkeypatch.setattr(
        nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(0)
    )
    # 'n' declines the retry offer; '1' then selects from the ORIGINAL options;
    # a MISS verdict needs an explicit 'y' to run.
    monkeypatch.setattr("builtins.input", make_input(["n", "1", "y"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "ls"]]


def test_command_failure_offers_retry_and_user_quits(monkeypatch, capsys, config):
    options = [("false", "Always fails")]
    monkeypatch.setattr(nlsh, "collect_unique_options", lambda *a, **k: options)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])
    monkeypatch.setattr(nlsh.subprocess, "run", lambda cmd, **k: FakeCompletedProcess(1))
    monkeypatch.setattr("builtins.input", make_input(["1", "", "q"]))

    result = nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert result is True
    assert "exited with error" in capsys.readouterr().out


def test_command_failure_retry_regenerates_and_executes_new_selection(monkeypatch, config):
    first_options = [("false", "Always fails")]
    second_options = [("true", "Always succeeds")]
    call_count = {"n": 0}

    def fake_collect(*a, **k):
        call_count["n"] += 1
        return first_options if call_count["n"] == 1 else second_options

    monkeypatch.setattr(nlsh, "collect_unique_options", fake_collect)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", lambda *a, **k: [("PASS", "")])

    run_calls = []

    def fake_run(cmd, **k):
        run_calls.append(cmd)
        return FakeCompletedProcess(1 if cmd[-1] == "false" else 0)

    monkeypatch.setattr(nlsh.subprocess, "run", fake_run)
    # select 'false', confirm (fails) -> retry -> reuse prompt -> select 'true', confirm
    monkeypatch.setattr("builtins.input", make_input(["1", "", "r", "", "1", ""]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    assert run_calls == [["/bin/bash", "-c", "false"], ["/bin/bash", "-c", "true"]]
    assert call_count["n"] == 2


def test_command_failure_retry_still_blocks_a_fail_verdict_on_the_new_options(monkeypatch, config):
    """Regression test: the pre-refactor code path taken after a failed
    execution regenerated options but then executed the user's next pick
    directly, skipping the availability/FAIL/WARN gates. The refactored loop
    routes every execution through the same gates, retries included — this
    pins that fix down.
    """
    first_options = [("false", "Always fails")]
    second_options = [("rm -rf /", "Delete everything")]
    verdicts_by_call = [[("PASS", "")], [("FAIL", "destroys the filesystem")]]
    call_count = {"n": 0}

    def fake_collect(*a, **k):
        call_count["n"] += 1
        return first_options if call_count["n"] == 1 else second_options

    def fake_qa(*a, **k):
        return verdicts_by_call[call_count["n"] - 1]

    monkeypatch.setattr(nlsh, "collect_unique_options", fake_collect)
    monkeypatch.setattr(nlsh, "check_all_commands_availability", lambda *a, **k: [True])
    monkeypatch.setattr(nlsh, "qa_review", fake_qa)

    run_calls = []
    monkeypatch.setattr(nlsh.subprocess, "run", lambda cmd, **k: run_calls.append(cmd) or FakeCompletedProcess(1))
    # select 'false', confirm (fails) -> retry -> reuse prompt -> select the new (now FAIL-rated) option
    monkeypatch.setattr("builtins.input", make_input(["1", "", "r", "", "1"]))

    nlsh.process_query(object(), config, "/bin/bash", "list", False)

    # Only the first, non-FAIL execution should have actually run a command.
    assert run_calls == [["/bin/bash", "-c", "false"]]
