# Personal Package Archive

**URL:** https://ppa.launchpadcontent.net/raulkivi/nlsh

## Display name

NLSH — AI-powered command assistant

## Description

nlsh is an AI-powered command-line assistant that translates natural language into executable Linux/shell commands using local LLMs via Ollama.

Describe what you want in plain English and get 3 ranked command alternatives with detailed, line-by-line explanations — no cloud required, no man-page diving.

Key features:
- 3 command alternatives per query (shell variants plus one-liners in awk, perl, python3, etc.), each fully explained
- Interactive shell mode (REPL) with a `?<question>` shortcut for direct LLM Q&A
- Advisory QA review: a second LLM call flags dangerous or incorrect commands (PASS / WARN / MISS / FAIL); read the command before you confirm it
- Checks command availability before suggesting tools not installed on your system
- Detects available scripting languages (bash, awk, python, perl, ruby, node, …)
- Copy commands to clipboard or execute directly
- Companion `ask` tool for general-purpose Q&A (e.g. `cat error.log | ask "What went wrong?"`)
- XDG-compliant paths, daily logging, per-invocation model override
- Supports thinking models (deepseek-r1, etc.) and optional Ollama cloud models