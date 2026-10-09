"""Tests for install.sh's legacy-osh cleanup.

install.sh is sourced (not executed) in a temporary HOME so only its
functions are defined; nothing outside tmp_path is touched and no network
or package installation happens.
"""
import os
import pty
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def run_cleanup(home: Path, answer: str | None = None) -> subprocess.CompletedProcess:
    """Source install.sh and run remove_legacy_osh_installs in a fake HOME.

    answer=None runs non-interactively (stdin is /dev/null); otherwise stdin
    is a pseudo-terminal pre-loaded with `answer`.
    """
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    cmd = ["bash", "-c", 'source "$1" && remove_legacy_osh_installs', "_", str(INSTALL_SH)]
    if answer is None:
        return subprocess.run(cmd, env=env, cwd=home, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=30, check=False)
    master, slave = pty.openpty()
    try:
        os.write(master, answer.encode())
        return subprocess.run(cmd, env=env, cwd=home, stdin=slave,
                              capture_output=True, text=True, timeout=30, check=False)
    finally:
        os.close(slave)
        os.close(master)


def make_legacy_install(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "osh.py").write_text("# old osh\n")
    (path / "ask.py").write_text("# old ask\n")


@pytest.mark.parametrize("rel", ["osh", ".local/osh"])
def test_unrelated_directory_named_osh_survives(tmp_path, rel):
    unrelated = tmp_path / rel
    unrelated.mkdir(parents=True)
    (unrelated / "notes.txt").write_text("precious\n")

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (unrelated / "notes.txt").read_text() == "precious\n"


def test_sourcing_does_not_run_the_installer(tmp_path):
    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Installing NLSH" not in result.stdout
    assert not (tmp_path / ".local" / "nlsh").exists()


@pytest.mark.parametrize("rel", ["osh", ".local/osh"])
def test_legacy_install_is_kept_in_non_interactive_run(tmp_path, rel):
    legacy = tmp_path / rel
    make_legacy_install(legacy)

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (legacy / "osh.py").exists()
    assert str(legacy) in result.stdout


@pytest.mark.parametrize("rel", ["osh", ".local/osh"])
def test_legacy_install_removed_after_explicit_yes(tmp_path, rel):
    legacy = tmp_path / rel
    make_legacy_install(legacy)

    result = run_cleanup(tmp_path, answer="y\n")

    assert result.returncode == 0, result.stderr
    assert not legacy.exists()


@pytest.mark.parametrize("answer", ["\n", "n\n"])
def test_legacy_install_kept_when_user_does_not_say_yes(tmp_path, answer):
    legacy = tmp_path / "osh"
    make_legacy_install(legacy)

    result = run_cleanup(tmp_path, answer=answer)

    assert result.returncode == 0, result.stderr
    assert (legacy / "osh.py").exists()


def test_unrelated_osh_binary_in_bin_dir_survives(tmp_path):
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    other = bin_dir / "osh"
    other.write_text("#!/bin/sh\n# some other osh\n")

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert other.exists()


def test_legacy_osh_launcher_symlink_is_removed(tmp_path):
    make_legacy_install(tmp_path / ".local" / "osh")
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    link = bin_dir / "osh"
    link.symlink_to(tmp_path / ".local" / "osh" / "osh.py")

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not link.is_symlink()
