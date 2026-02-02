---
name: gemini-deep-research
description: Run a single Gemini deep research query from the CLI and store the report locally. Use when a user wants a one-off deep research result.
---

# Gemini Deep Research

Use `scripts/deep_research.py` to run one deep research query and save the report to local storage.

## Quick start

- Put `GOOGLE_API_KEY=...` in the project `.env`.
- Run: `python scripts/deep_research.py "your topic"`

## Storage

Reports are saved under `storage/` (relative to this skill directory). Each run gets:

- `report.md` (human-readable output)
- `run.json` (metadata)

## Expected wait time

Deep research typically takes a few minutes (often 2-10 minutes), longer for complex topics.
