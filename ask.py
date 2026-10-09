#!/usr/bin/env python3
from __future__ import annotations

__version__ = "1.2"

import json
import os
import re
import unicodedata
import sys
import urllib.error
import urllib.request
from typing import Any

# Matches ANSI/VT escape sequences (CSI and single-char ESC) to prevent terminal injection
_ANSI_ESCAPE: re.Pattern[str] = re.compile(
    r'(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~])'
)

# Default Configuration
DEFAULT_CONFIG: dict[str, Any] = {
    "api": "ollama",
    "model": "gpt-oss:latest",
    "temperature": 0.3,
    "max_tokens": 2400,
    "python_venv": None,
    "ollama_endpoint": "http://localhost:11434",
    "llama_cpp_endpoint": "http://localhost:38080",
}


def get_config_path() -> str:
    """Get config file path, respecting XDG_CONFIG_HOME."""
    config_home: str = os.environ.get(
        'XDG_CONFIG_HOME',
        os.path.expanduser('~/.config')
    )
    return os.path.join(config_home, 'nlsh', 'config.json')


def get_python_venv_early() -> str | None:
    """Early lightweight config read to get python_venv setting before imports.
    
    This runs before venv activation, so it can't use the full config system.
    Falls back to default if config is missing or malformed.
    """
    config_path: str = get_config_path()
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config: dict[str, Any] = json.load(f)
            return config.get('python_venv')
    except Exception:
        pass  # Fall through to default
    
    return DEFAULT_CONFIG['python_venv']


def load_config() -> dict[str, Any]:
    """Load configuration from JSON file, merging with defaults.
    
    Returns:
        Configuration dictionary with user settings merged over defaults
    """
    config_path: str = get_config_path()
    
    # Start with defaults
    config: dict[str, Any] = DEFAULT_CONFIG.copy()
    
    # Try to load user config
    if not os.path.exists(config_path):
        return config
    
    try:
        with open(config_path, 'r') as f:
            user_config: dict[str, Any] = json.load(f)
        # Merge user config over defaults
        config.update(user_config)
    except Exception as e:
        print(f"Warning: Error loading config from {config_path}: {e}", file=sys.stderr)
        print("Continuing with default configuration.", file=sys.stderr)
    
    return config

SYSTEM_PROMPT = """\
You are a helpful, highly skilled expert. Provide clear, accurate, and concise answers. \
When appropriate, include examples or explanations. Use plain text output without \
markdown formatting.\
"""


def check_and_activate_venv() -> None:
    """Check and activate configured virtual environment if specified."""
    python_venv: str | None = get_python_venv_early()
    if not python_venv:
        return

    expected_python: str
    venv_display_name: str = python_venv

    if python_venv.startswith('pyenv:'):
        venv_name: str = python_venv[6:]
        home: str = os.path.expanduser("~")
        pyenv_versions: str = os.path.realpath(os.path.join(home, ".pyenv", "versions"))
        candidate: str = os.path.realpath(os.path.join(pyenv_versions, venv_name))
        if not candidate.startswith(pyenv_versions + os.sep):
            print(
                f"Warning: Invalid pyenv environment name '{venv_name}': path traversal detected",
                file=sys.stderr,
            )
            return
        venv_path: str = candidate
        expected_python = os.path.join(venv_path, "bin", "python")
        venv_display_name = venv_name
    elif python_venv.startswith('venv:'):
        venv_path = os.path.expanduser(python_venv[5:])
        expected_python = os.path.join(venv_path, "bin", "python")
    else:
        venv_path = os.path.expanduser(python_venv)
        expected_python = os.path.join(venv_path, "bin", "python")

    # Check if already running in the expected environment
    if venv_display_name in sys.prefix or expected_python == sys.executable:
        return

    if os.path.exists(expected_python):
        os.execv(expected_python, [expected_python] + sys.argv)
    else:
        print(
            f"Warning: Configured Python venv not found at {expected_python}",
            file=sys.stderr
        )
        print(
            f"Continuing with current Python: {sys.executable}",
            file=sys.stderr
        )


# Guarded by __main__ so that importing this module (e.g. from tests, or as
# a library) can never trigger an os.execv() re-exec as a side effect of import.
if __name__ == "__main__":
    check_and_activate_venv()

from ollama import ChatResponse, Client


def _llama_cpp_chat(host: str, model: str, messages: list[dict[str, str]], temperature: float | None = None, max_tokens: int | None = None) -> str:
    """Send a chat request to a local llama.cpp `llama-server` via its OpenAI-compatible API.

    llama-server doesn't implement Ollama's native `/api/chat` wire format, so
    this talks `/v1/chat/completions` instead, via stdlib urllib (no extra
    dependency).
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    request = urllib.request.Request(
        f"{host.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail: str = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llama.cpp server error (HTTP {e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach llama.cpp server at {host}. Is `llama-server` running? ({e.reason})"
        ) from e

    try:
        content: Any = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response from llama.cpp server: {body}") from e
    if not isinstance(content, str):
        raise RuntimeError(f"Unexpected response from llama.cpp server: {body}")
    return content


def main() -> None:
    # The module-level venv check only fires under `if __name__ ==
    # "__main__"`, so entry points that reach main() via import (e.g. the
    # pip/deb console-script wrapper) need it re-checked here. A no-op if
    # already in the configured environment.
    check_and_activate_venv()

    args: list[str] = sys.argv[1:]

    if args and args[0] in ('--version', '-V'):
        print(f"ask {__version__}")
        sys.exit(0)

    arg_question: str = " ".join(args).strip()
    has_args: bool = bool(arg_question)
    has_stdin: bool = not sys.stdin.isatty()

    if not has_args and not has_stdin:
        print("Usage: ask <question>", file=sys.stderr)
        print("       ask \"this is a question?\"", file=sys.stderr)
        print("       echo 'your question' | ask", file=sys.stderr)
        print("       cat file | ask \"what does this mean?\"", file=sys.stderr)
        sys.exit(1)

    MAX_STDIN_BYTES: int = 1 * 1024 * 1024  # 1 MB
    stdin_content: str = ""
    if has_stdin:
        raw: str = sys.stdin.read(MAX_STDIN_BYTES)
        if len(raw) == MAX_STDIN_BYTES:
            print("Warning: input truncated at 1 MB.", file=sys.stderr)
        stdin_content = raw.strip()

    if has_args and has_stdin:
        user_input = f"{arg_question}\n\n{stdin_content}" if stdin_content else arg_question
    elif has_args:
        user_input = arg_question
    else:
        user_input = stdin_content

    if not user_input:
        print("No input received.", file=sys.stderr)
        sys.exit(1)

    config: dict[str, Any] = load_config()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    try:
        if config.get("api") == "llama_cpp":
            content: str = _llama_cpp_chat(
                host=config.get("llama_cpp_endpoint", "http://localhost:38080"),
                model=config["model"],
                messages=messages,
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
            )
        else:
            client = Client(host=config.get("ollama_endpoint", "http://localhost:11434"))

            options: dict[str, Any] = {}
            if config.get('temperature') is not None:
                options['temperature'] = config['temperature']
            if config.get('max_tokens') is not None:
                options['num_predict'] = config['max_tokens']

            response: ChatResponse = client.chat(  # type: ignore[misc]
                model=config["model"],
                messages=messages,
                options=options,
                stream=False,
            )
            content = getattr(response.message, 'content', None) or ""
    except Exception as e:
        print(f"Error communicating with model: {e}", file=sys.stderr)
        sys.exit(1)
    if not content.strip():
        print("Error: empty response from model.", file=sys.stderr)
        sys.exit(1)

    print(''.join(ch for ch in _ANSI_ESCAPE.sub('', content) if ch in '\t\n' or unicodedata.category(ch) not in ('Cc', 'Cf')))


if __name__ == "__main__":
    main()
