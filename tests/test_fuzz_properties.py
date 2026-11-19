"""Property-based tests for the text parsers that handle untrusted LLM output."""
import unicodedata

from hypothesis import given, settings, strategies as st

import nlsh

FUZZ = settings(max_examples=200, deadline=None)

# Arbitrary Unicode text.
text = st.text(max_size=300)
# Text weighted towards the characters the parsers care about.
nasty = st.lists(
    st.sampled_from(
        list("ab |<>/=;\t\n\r")
        + ["\x1b", "\x1b[31m", "\x00", "\u202e", "\u200b", "\x7f", "\u00e9"]
    ),
    max_size=40,
).map("".join)
fragment_text = st.one_of(text, nasty)


@st.composite
def tagged_response(draw):
    """Responses built from <cN>/<eN> fragments, some unterminated."""
    parts = []
    for _ in range(draw(st.integers(0, 8))):
        n = draw(st.integers(0, 7))
        tag = draw(st.sampled_from("ce"))
        body = draw(fragment_text)
        closed = draw(st.booleans())
        parts.append(f"<{tag}{n}>{body}</{tag}{n}>" if closed else f"<{tag}{n}>{body}")
        parts.append(draw(st.sampled_from(["", "\n", " noise "])))
    return "".join(parts)


@st.composite
def verdict_response(draw):
    """Responses built from N|VERDICT|reason lines, some malformed."""
    lines = []
    for _ in range(draw(st.integers(0, 10))):
        num = draw(st.one_of(st.integers(-2, 12).map(str), st.just("x"), st.just("")))
        verdict = draw(st.sampled_from(["PASS", "warn", "FAIL", "MISS", "BOGUS", ""]))
        reason = draw(fragment_text)
        shape = draw(st.sampled_from([[num, verdict, reason], [num, verdict], [num]]))
        lines.append("|".join(shape))
    return "\n".join(lines)


@FUZZ
@given(st.one_of(text, tagged_response()))
def test_parse_command_options_invariants(response):
    options = nlsh.parse_command_options(response)
    assert len(options) <= 6
    for command, explanation in options:
        assert command and command == command.strip()
        assert command not in nlsh._PLACEHOLDER_COMMANDS
        assert not nlsh.has_hidden_chars(command)
        assert not nlsh.has_hidden_chars(explanation)


@FUZZ
@given(st.one_of(text, verdict_response()), st.integers(0, 8))
def test_parse_qa_verdicts_invariants(response, num_commands):
    verdicts = nlsh.parse_qa_verdicts(response, num_commands)
    for key, (verdict, reason) in verdicts.items():
        assert 1 <= key <= num_commands
        assert verdict in nlsh._VERDICT_SEVERITY
        assert not nlsh.has_hidden_chars(reason)
    assert len(nlsh.align_verdicts(verdicts, num_commands)) == num_commands


@FUZZ
@given(fragment_text)
def test_strip_for_display_removes_hidden_and_is_idempotent(value):
    out = nlsh.strip_for_display(value)
    assert not nlsh.has_hidden_chars(out)
    assert "\x1b" not in out
    assert nlsh.strip_for_display(out) == out


@FUZZ
@given(st.characters())
def test_is_hidden_matches_category_rule(ch):
    if ch in "\t\n":
        assert not nlsh._is_hidden(ch)
    else:
        assert nlsh._is_hidden(ch) == (unicodedata.category(ch) in ("Cc", "Cf"))


@FUZZ
@given(fragment_text)
def test_sanitize_for_log_removes_line_breaks(value):
    out = nlsh._sanitize_for_log(value)
    assert "\n" not in out and "\r" not in out
    assert len(out) == len(value)


@FUZZ
@given(fragment_text)
def test_extract_base_command_is_total_and_single_token(command):
    base = nlsh.extract_base_command(command)
    assert isinstance(base, str)
    assert not any(ch.isspace() for ch in base)
    if not command.split():
        assert base == ""


@FUZZ
@given(st.text(alphabet=st.characters(blacklist_characters="="), max_size=80))
def test_extract_base_command_stops_at_operators(command):
    base = nlsh.extract_base_command(command)
    assert not any(op in base for op in "|<>;")
