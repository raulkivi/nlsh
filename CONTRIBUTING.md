# Contributing to nlsh

**Last changed:** 2026-11-20 · **Source:** https://github.com/raulkivi/nlsh

Thanks for helping out. This is a personal project maintained on a best-effort basis, so replies may take a few days.

## Before you start
- Bugs and small fixes: open a PR directly, or an issue if you want to discuss first.
- New features or larger changes: open an issue first so we can agree on scope.
- Security problems: do **not** open an issue; follow [SECURITY.md](SECURITY.md).

## Development setup
Requires Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m pytest -q
```

Tests do not need a running Ollama or llama.cpp server; the LLM layer is mocked.

## Making a change
1. Fork and create a branch from `main`.
2. Write a failing test first, then the code that makes it pass.
3. Keep changes focused; one concern per PR.
4. Run `python -m pytest -q` and make sure it passes.
5. Update `README.md` if you change user-visible behavior or configuration.
6. Open a PR and fill in the template.

CI runs the test suite on Linux and macOS across supported Python versions, plus CodeQL, a hidden-Unicode scan and a spelling check. All must pass.

## Spelling
Use US English. The Spelling workflow runs [codespell](https://github.com/codespell-project/codespell) (settings in `.codespellrc`) on commit messages and added lines; existing text is not checked. For a proper name it flags, add `codespell:ignore <word>` on that line.

## Dependencies
`requirements-dev.txt` is generated with `uv pip compile --generate-hashes` (see its header); do not edit it by hand. Dependabot proposes updates. A grouped Dependabot bump can leave a transitive pin behind (for example `pydantic-core` after a `pydantic` bump), which fails `--require-hashes` installs in CI. Rerun the command from the file's header with `--upgrade-package <name>` for the stale package.

## Fuzzing
- `tests/test_fuzz_properties.py` holds Hypothesis property tests for the parsers that handle LLM output. They run with the normal suite in CI.
- `fuzz/fuzz_parsers.py` is an Atheris harness over the same parsers. The Fuzz workflow runs it for 120 seconds on every PR and weekly.
- Atheris is pinned in `.github/fuzz-requirements.txt` (Python 3.12, Linux). To run the harness locally:

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip install --no-deps --require-hashes -r .github/fuzz-requirements.txt
python fuzz/fuzz_parsers.py -max_total_time=60
```

A crash is saved as a `crash-*` file; replay it with `python fuzz/fuzz_parsers.py crash-<hash>`.

## Conduct
By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
