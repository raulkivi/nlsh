# Contributing to nlsh

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
5. Update `README.md` if you change user-visible behaviour or configuration.
6. Open a PR and fill in the template.

CI runs the test suite on Linux and macOS across supported Python versions, plus CodeQL and a hidden-Unicode scan. All must pass.

## Dependencies
`requirements-dev.txt` is generated with `uv pip compile --generate-hashes` (see its header); do not edit it by hand. Dependabot proposes updates.

## Conduct
By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
