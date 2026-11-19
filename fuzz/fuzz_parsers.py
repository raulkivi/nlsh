"""Atheris harness for the parsers that handle untrusted LLM output.

Run locally: python fuzz/fuzz_parsers.py -max_total_time=60
Invariants mirror tests/test_fuzz_properties.py; a violated assert or any
uncaught exception is reported by Atheris as a crash.
"""
import os
import sys

import atheris

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with atheris.instrument_imports():
    import nlsh


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    num_commands = fdp.ConsumeIntInRange(0, 8)
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())

    for command, explanation in nlsh.parse_command_options(text):
        assert command and not nlsh.has_hidden_chars(command)
        assert not nlsh.has_hidden_chars(explanation)

    for key, (verdict, reason) in nlsh.parse_qa_verdicts(text, num_commands).items():
        assert 1 <= key <= num_commands
        assert verdict in nlsh._VERDICT_SEVERITY
        assert not nlsh.has_hidden_chars(reason)

    stripped = nlsh.strip_for_display(text)
    assert not nlsh.has_hidden_chars(stripped) and "\x1b" not in stripped
    assert nlsh.strip_for_display(stripped) == stripped

    sanitized = nlsh._sanitize_for_log(text)
    assert "\n" not in sanitized and "\r" not in sanitized

    assert not any(ch.isspace() for ch in nlsh.extract_base_command(text))


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
