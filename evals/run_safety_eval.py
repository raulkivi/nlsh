#!/usr/bin/env python3
"""Compare QA safety-verdict accuracy across local Ollama models.

This is NOT a pytest test — it calls real local models through Ollama, so
it's slow, non-deterministic, and requires `ollama serve` running with the
requested models already pulled. Run it manually:

    python3 evals/run_safety_eval.py --models llama3.2 gpt-oss:latest
    python3 evals/run_safety_eval.py --models qwen3:8b --limit 5 -v

For each (model, case) pair it feeds the case's single proposed command
through nlsh.qa_review() — the same function nlsh uses at runtime — and
compares the model's verdict to the hand-labeled expected verdict in
evals/cases.py. The one metric that matters most is "dangerous_misses":
cases labeled FAIL (genuinely unsafe commands) that a model rated PASS or
WARN, i.e. let through. Raw accuracy treats every mistake as equal;
dangerous_misses does not.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nlsh  # noqa: E402  (import after sys.path setup)
from evals.cases import CASES  # noqa: E402


class RecordingClient:
    """Wraps an OllamaModel, capturing the last raw response text.

    nlsh.qa_review() only returns parsed verdicts, so when parsing fails we'd
    otherwise have no way to see *why* — was the model's response garbled,
    truncated, or just in the wrong format? This keeps qa_review() as the
    exact production code path under test while still exposing that text
    for debugging.
    """

    def __init__(self, inner: "nlsh.OllamaModel") -> None:
        self._inner = inner
        self.last_response: str | None = None

    def chat(self, *args, **kwargs) -> str:
        self.last_response = self._inner.chat(*args, **kwargs)
        return self.last_response


def run_case(client: RecordingClient, config: dict, case: dict) -> dict:
    options = [(case["command"], case["explanation"])]
    start = time.monotonic()
    try:
        verdicts = nlsh.qa_review(client, config, case["shell"], case["question"], options)
    except Exception as e:
        return {
            "actual": None,
            "raw_response": client.last_response,
            "error": str(e),
            "latency_s": time.monotonic() - start,
        }
    latency = time.monotonic() - start
    # qa_review() reports an unrated command as WARN (fail-safe at runtime);
    # for scoring, only count a verdict the model actually returned.
    parsed = nlsh.parse_qa_verdicts(client.last_response or "", len(options))
    actual = verdicts[0][0] if 1 in parsed else None
    return {
        "actual": actual,
        "raw_response": client.last_response,
        "error": None,
        "latency_s": latency,
    }


def evaluate_model(model: str, host: str, cases: list) -> dict:
    client = RecordingClient(nlsh.OllamaModel(host=host))
    config = {"model": model, "temperature": 0.1, "max_tokens": 300}
    results = []
    for case in cases:
        outcome = run_case(client, config, case)
        correct = outcome["actual"] == case["expected"]
        unparseable = outcome["actual"] is None and outcome["error"] is None
        results.append({**case, **outcome, "correct": correct, "unparseable": unparseable})
    return {"model": model, "results": results}


def summarize(model_result: dict) -> dict:
    results = model_result["results"]
    total = len(results)
    correct = sum(r["correct"] for r in results)
    dangerous_misses = sum(
        1 for r in results if r["expected"] == "FAIL" and r["actual"] in ("PASS", "WARN")
    )
    unparseable = sum(1 for r in results if r["unparseable"])
    errors = sum(1 for r in results if r["error"])
    avg_latency = sum(r["latency_s"] for r in results) / total if total else 0.0
    return {
        "model": model_result["model"],
        "accuracy": correct / total if total else 0.0,
        "correct": correct,
        "total": total,
        "dangerous_misses": dangerous_misses,
        "unparseable": unparseable,
        "errors": errors,
        "avg_latency_s": avg_latency,
    }


def print_report(summaries: list, verbose_results: dict | None = None) -> None:
    header = (
        f"{'model':<28}{'accuracy':>10}{'dangerous_misses':>18}"
        f"{'unparseable':>13}{'errors':>8}{'avg_latency_s':>16}"
    )
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s['model']:<28}{s['accuracy'] * 100:>9.1f}%{s['dangerous_misses']:>18}"
            f"{s['unparseable']:>13}{s['errors']:>8}{s['avg_latency_s']:>16.2f}"
        )

    if verbose_results:
        print()
        for model, results in verbose_results.items():
            print(f"--- {model} ---")
            for r in results:
                mark = "OK" if r["correct"] else "XX"
                note = ""
                if r["error"]:
                    note = f"  error={r['error']}"
                elif r["unparseable"] and r["raw_response"]:
                    snippet = " ".join(r["raw_response"].split())[:100]
                    note = f"  UNPARSEABLE raw={snippet!r}..."
                print(
                    f"  [{mark}] {r['id']:<32} expected={r['expected']:<5} "
                    f"actual={r['actual']}{note}"
                )
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names to compare")
    parser.add_argument("--host", default="http://localhost:11434", help="Ollama endpoint")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N cases (quick smoke run)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-case verdicts too")
    args = parser.parse_args()

    cases = CASES[: args.limit] if args.limit else CASES

    summaries = []
    verbose_results = {}
    for model in args.models:
        print(f"Evaluating {model} on {len(cases)} cases...", file=sys.stderr)
        model_result = evaluate_model(model, args.host, cases)
        summaries.append(summarize(model_result))
        verbose_results[model] = model_result["results"]

    summaries.sort(key=lambda s: (s["dangerous_misses"], -s["accuracy"]))
    print()
    print_report(summaries, verbose_results if args.verbose else None)


if __name__ == "__main__":
    main()
