---
name: gemini-deep-research
description: Run Gemini deep research from the CLI with clarifying questions and persistent local storage. Use when a task is too complicated and requires rigorous results or extensive search. 
---

# Gemini Deep Research

Use `scripts/deep_research.py` to run deep research as an agent-like tool. It supports
interactive clarification, persistent storage, and run management.

## Quick start

- Ensure `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) is set.
- Run: `python scripts/deep_research.py "your topic"`

## Clarifications

By default the script asks a few clarification questions before starting. Use `--no-clarify`
to skip, or provide `--context-file` to add extra background.

## Storage layout

Runs are stored under `deep_research_runs/` (relative to this skill directory by default).
Each run has a folder with:

- `run.json` (metadata + status)
- `prompt.txt` (input prompt)
- `result.md` (human-readable output, when completed)

An index is kept in `deep_research_runs/index.md`.

## Run management

- List runs: `python scripts/deep_research.py --list`
- Show results: `python scripts/deep_research.py --show RUN_ID`
- Resume running: `python scripts/deep_research.py --resume RUN_ID`

## Configuration

- `--agent` to choose the Gemini agent.
- `--poll-interval` and `--max-wait` to control polling.
- `--store-dir` to override the storage location.
- `--no-wait` to start and exit without waiting.
