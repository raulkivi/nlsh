import io
import json

import nlsh


class TestCheckAndActivateVenvNoConfig:
    def test_noop_when_no_venv_configured(self, tmp_path, monkeypatch):
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda *a, **k: execv_calls.append(a))
        nlsh.check_and_activate_venv(str(tmp_path / "missing.json"))
        assert execv_calls == []


class TestCheckAndActivateVenvPathTraversal:
    def test_pyenv_traversal_attempt_is_blocked(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"python_venv": "pyenv:../../etc/passwd"}))
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda *a, **k: execv_calls.append(a))

        nlsh.check_and_activate_venv(str(config_path))

        assert execv_calls == []
        assert "path traversal detected" in capsys.readouterr().err

    def test_pyenv_absolute_path_escape_is_blocked(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"python_venv": "pyenv:/etc/passwd"}))
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda *a, **k: execv_calls.append(a))

        nlsh.check_and_activate_venv(str(config_path))

        assert execv_calls == []
        assert "path traversal detected" in capsys.readouterr().err


class TestCheckAndActivateVenvMissingInterpreter:
    def test_warns_and_continues_when_venv_python_missing(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        missing_venv = tmp_path / "nonexistent-venv"
        config_path.write_text(json.dumps({"python_venv": f"venv:{missing_venv}"}))
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda *a, **k: execv_calls.append(a))

        nlsh.check_and_activate_venv(str(config_path))

        assert execv_calls == []
        assert "not found" in capsys.readouterr().err


class TestCheckAndActivateVenvAlreadyActive:
    def test_noop_when_display_name_already_in_sys_prefix(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"python_venv": "pyenv:myenv"}))
        monkeypatch.setattr(nlsh.sys, "prefix", "/home/user/.pyenv/versions/myenv")
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda *a, **k: execv_calls.append(a))

        nlsh.check_and_activate_venv(str(config_path))

        assert execv_calls == []


class TestCheckAndActivateVenvActivation:
    def test_execs_into_venv_python_when_it_exists(self, tmp_path, monkeypatch):
        venv_dir = tmp_path / "myvenv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        python_path = bin_dir / "python"
        python_path.write_text("#!/bin/sh\n")

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"python_venv": f"venv:{venv_dir}"}))

        monkeypatch.setattr(nlsh.sys, "prefix", "/unrelated/prefix")
        execv_calls = []
        monkeypatch.setattr(nlsh.os, "execv", lambda path, argv: execv_calls.append((path, argv)))

        nlsh.check_and_activate_venv(str(config_path))

        assert len(execv_calls) == 1
        called_path, called_argv = execv_calls[0]
        assert called_path == str(python_path)
        assert called_argv[0] == str(python_path)


class TestGetSafeShell:
    def test_returns_configured_shell_when_listed_in_etc_shells(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        monkeypatch.setattr(
            nlsh, "open", lambda *a, **k: io.StringIO("/bin/bash\n/bin/zsh\n"), raising=False
        )
        assert nlsh.get_safe_shell() == "/bin/zsh"

    def test_falls_back_to_bin_sh_when_shell_not_listed(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/opt/weird/shell")
        monkeypatch.setattr(
            nlsh, "open", lambda *a, **k: io.StringIO("/bin/bash\n/bin/zsh\n"), raising=False
        )
        assert nlsh.get_safe_shell() == "/bin/sh"

    def test_falls_back_to_hardcoded_allowlist_when_etc_shells_missing(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/fish")

        def raise_not_found(*a, **k):
            raise FileNotFoundError()

        monkeypatch.setattr(nlsh, "open", raise_not_found, raising=False)
        assert nlsh.get_safe_shell() == "/bin/fish"

    def test_falls_back_to_bin_sh_when_etc_shells_missing_and_shell_unrecognized(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/opt/custom/shell")

        def raise_not_found(*a, **k):
            raise FileNotFoundError()

        monkeypatch.setattr(nlsh, "open", raise_not_found, raising=False)
        assert nlsh.get_safe_shell() == "/bin/sh"


class TestMissingPosixDisplay:
    def test_true_when_display_unset(self, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        assert nlsh.missing_posix_display() is True

    def test_true_when_display_empty(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", "")
        assert nlsh.missing_posix_display() is True

    def test_false_when_display_set(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":0")
        assert nlsh.missing_posix_display() is False


class TestHiddenCharacterHandling:
    """LLM output reaches the terminal and a shell; hidden characters must not
    make the displayed command differ from the executed one."""

    def test_strip_for_display_removes_ansi_control_and_bidi(self):
        raw = "ok\x1b[31m red\x1b[0m\x07‮​ end"
        assert nlsh.strip_for_display(raw) == "ok red end"

    def test_strip_for_display_keeps_newline_and_tab(self):
        assert nlsh.strip_for_display("a\nb\tc") == "a\nb\tc"

    def test_command_with_bidi_override_is_rejected(self):
        response = "<c1>ls ‮txt.sh</c1><e1>list</e1><c2>ls -l</c2><e2>long</e2>"
        assert nlsh.parse_command_options(response) == [("ls -l", "long")]

    def test_command_with_escape_or_carriage_return_is_rejected(self):
        response = "<c1>echo hi\rrm -rf x</c1><e1>a</e1><c2>echo \x1b[2Jhi</c2><e2>b</e2>"
        assert nlsh.parse_command_options(response) == []

    def test_command_with_zero_width_is_rejected(self):
        assert nlsh.parse_command_options("<c1>ls​ -l</c1><e1>x</e1>") == []

    def test_explanation_is_sanitised(self):
        response = "<c1>ls</c1><e1>list ‮files\x1b[31m</e1>"
        assert nlsh.parse_command_options(response) == [("ls", "list files")]

    def test_qa_reason_is_sanitised(self):
        assert nlsh.parse_qa_verdicts("1|WARN|bad ‮thing\x1b[31m", 1) == {1: ("WARN", "bad thing")}
