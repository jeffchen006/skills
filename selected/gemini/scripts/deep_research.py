#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google import genai

DEFAULT_AGENT = "deep-research-pro-preview-12-2025"
DEFAULT_POLL_INTERVAL = 10
DEFAULT_MAX_WAIT_SECONDS = 3600
CLARIFICATION_QUESTIONS = [
    ("goal", "What is the exact goal or deliverable?"),
    ("scope", "Any scope boundaries to include/exclude?"),
    ("timeframe", "Any timeframe or recency requirements?"),
    ("sources", "Any preferred or disallowed sources?"),
    ("format", "Preferred output format or length?"),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    if not cleaned:
        cleaned = "topic"
    return cleaned[:max_len]


def build_run_id(topic: str) -> str:
    return f"{utc_now_iso().replace(':', '').replace('Z', '')}-{slugify(topic)}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def resolve_base_dir(store_dir: str | None) -> Path:
    if store_dir:
        return Path(store_dir).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "deep_research_runs"


def ensure_base_dir(base_dir: Path) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)


def build_prompt(topic: str, clarifications: dict, extra_context: str | None) -> str:
    parts = [f"Deep research topic: {topic}"]
    if clarifications:
        parts.append("Clarifications:")
        for key, value in clarifications.items():
            if value:
                parts.append(f"- {key}: {value}")
    if extra_context:
        parts.append("Additional context:")
        parts.append(extra_context)
    parts.append("Please conduct deep research and provide a structured report.")
    return "\n".join(parts).strip()


def prompt_clarifications() -> dict:
    answers: dict[str, str] = {}
    print("Before I start, a few quick clarifying questions.")
    for key, question in CLARIFICATION_QUESTIONS:
        response = input(f"{question}\n> ").strip()
        if response:
            answers[key] = response
    return answers


def confirm_run(topic: str, clarifications: dict, extra_context: str | None) -> bool:
    print("\nI will run deep research with:")
    print(f"- Topic: {topic}")
    if clarifications:
        for key, value in clarifications.items():
            print(f"- {key}: {value}")
    if extra_context:
        print("- Additional context: provided")
    confirm = input("Proceed? [Y/n] ").strip().lower()
    return confirm in ("", "y", "yes")


def build_client(args: argparse.Namespace) -> genai.Client:
    if args.vertexai or args.project or args.location:
        if not args.project or not args.location:
            raise ValueError("Vertex AI requires --project and --location.")
        return genai.Client(vertexai=True, project=args.project, location=args.location)
    api_key = args.api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "Missing API key. Set GOOGLE_API_KEY or GEMINI_API_KEY, or pass --api-key."
        )
    return genai.Client(api_key=api_key)


def refresh_index_md(base_dir: Path) -> None:
    rows = []
    for run_dir in sorted(base_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue
        data = read_json(run_json)
        topic = (data.get("topic") or "").replace("|", "\\|")
        rows.append(
            (
                data.get("run_id", run_dir.name),
                data.get("created_at", ""),
                data.get("status", ""),
                topic,
            )
        )

    lines = ["# Deep Research Runs", "", "| Run ID | Created (UTC) | Status | Topic |", "| --- | --- | --- | --- |"]
    for run_id, created_at, status, topic in rows:
        lines.append(f"| {run_id} | {created_at} | {status} | {topic} |")
    lines.append("")
    write_text(base_dir / "index.md", "\n".join(lines))


def resolve_run_dir(base_dir: Path, run_id: str) -> Path:
    exact = base_dir / run_id
    if exact.exists():
        return exact
    matches = [p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith(run_id)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No run found matching '{run_id}'.")
    raise ValueError(f"Run id '{run_id}' is ambiguous. Matches: {', '.join(p.name for p in matches)}")


def list_runs(base_dir: Path) -> None:
    refresh_index_md(base_dir)
    print(read_text(base_dir / "index.md"))


def show_run(base_dir: Path, run_id: str) -> None:
    run_dir = resolve_run_dir(base_dir, run_id)
    result_path = run_dir / "result.md"
    if result_path.exists():
        print(read_text(result_path))
        return
    run_json = run_dir / "run.json"
    if run_json.exists():
        data = read_json(run_json)
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    print(f"No data found for run '{run_id}'.")


def save_result(run_dir: Path, metadata: dict, output_text: str | None) -> None:
    if output_text:
        lines = [
            "# Deep Research Result",
            "",
            f"- Run ID: {metadata.get('run_id', '')}",
            f"- Topic: {metadata.get('topic', '')}",
            f"- Created: {metadata.get('created_at', '')}",
            f"- Completed: {metadata.get('completed_at', '')}",
            f"- Agent: {metadata.get('agent', '')}",
            f"- Interaction ID: {metadata.get('interaction_id', '')}",
            "",
        ]
        clarifications = metadata.get("clarifications") or {}
        if clarifications:
            lines.append("## Clarifications")
            for key, value in clarifications.items():
                lines.append(f"- {key}: {value}")
            lines.append("")
        lines.append("## Output")
        lines.append("")
        lines.append(output_text.strip())
        lines.append("")
        write_text(run_dir / "result.md", "\n".join(lines))
    write_json(run_dir / "run.json", metadata)


def poll_interaction(
    client: genai.Client,
    interaction_id: str,
    poll_interval: int,
    max_wait_seconds: int | None,
) -> tuple[str, str | None]:
    start_time = time.time()
    while True:
        interaction = client.interactions.get(interaction_id)
        status = interaction.status
        if status == "completed":
            output_text = interaction.outputs[-1].text if interaction.outputs else ""
            return status, output_text
        if status == "failed":
            error = interaction.error if hasattr(interaction, "error") else "Unknown error"
            return status, f"Research failed: {error}"
        if max_wait_seconds and (time.time() - start_time) > max_wait_seconds:
            return "timeout", None
        time.sleep(poll_interval)


def run_new_research(args: argparse.Namespace) -> None:
    base_dir = resolve_base_dir(args.store_dir)
    ensure_base_dir(base_dir)

    topic = args.topic or args.topic_input
    if not topic and sys.stdin.isatty():
        topic = input("Deep research topic: ").strip()
    if not topic:
        raise ValueError("A research topic is required.")

    clarifications: dict[str, str] = {}
    if args.clarify and sys.stdin.isatty():
        clarifications = prompt_clarifications()

    extra_context = None
    if args.context_file:
        extra_context = read_text(Path(args.context_file).expanduser())

    if args.clarify and sys.stdin.isatty():
        if not confirm_run(topic, clarifications, extra_context):
            print("Cancelled.")
            return

    prompt = build_prompt(topic, clarifications, extra_context)
    if args.dry_run:
        print(prompt)
        return

    run_id = build_run_id(topic)
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = run_dir / "prompt.txt"
    write_text(prompt_path, prompt)

    client = build_client(args)
    interaction = client.interactions.create(
        input=prompt,
        agent=args.agent,
        background=True,
    )

    metadata = {
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "topic": topic,
        "clarifications": clarifications,
        "agent": args.agent,
        "interaction_id": interaction.id,
        "status": "running",
        "prompt_path": str(prompt_path),
    }
    save_result(run_dir, metadata, None)
    refresh_index_md(base_dir)

    print(f"Research started: {interaction.id}")
    print(f"Run stored at: {run_dir}")

    if args.no_wait:
        return

    status, output_text = poll_interaction(
        client,
        interaction.id,
        args.poll_interval,
        args.max_wait,
    )
    metadata["status"] = status
    metadata["completed_at"] = utc_now_iso() if status == "completed" else None
    save_result(run_dir, metadata, output_text)
    refresh_index_md(base_dir)

    if status == "completed":
        print(read_text(run_dir / "result.md"))
    elif status == "timeout":
        print("Timed out waiting for completion. Use --resume to continue later.")
    else:
        print(output_text or "Research failed.")


def resume_research(args: argparse.Namespace) -> None:
    base_dir = resolve_base_dir(args.store_dir)
    ensure_base_dir(base_dir)

    run_dir = resolve_run_dir(base_dir, args.resume)
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise FileNotFoundError(f"No run metadata found in {run_dir}.")
    metadata = read_json(run_json)

    if metadata.get("status") == "completed":
        print(read_text(run_dir / "result.md"))
        return

    interaction_id = metadata.get("interaction_id")
    if not interaction_id:
        raise ValueError("Missing interaction_id in run metadata.")

    client = build_client(args)
    status, output_text = poll_interaction(
        client,
        interaction_id,
        args.poll_interval,
        args.max_wait,
    )
    metadata["status"] = status
    metadata["completed_at"] = utc_now_iso() if status == "completed" else None
    save_result(run_dir, metadata, output_text)
    refresh_index_md(base_dir)

    if status == "completed":
        print(read_text(run_dir / "result.md"))
    elif status == "timeout":
        print("Timed out waiting for completion. Try --resume again later.")
    else:
        print(output_text or "Research failed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemini deep research with persistence.")
    parser.add_argument("topic_input", nargs="?", help="Deep research topic")
    parser.add_argument("--topic", dest="topic", help="Deep research topic (overrides positional)")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Agent name to use")
    parser.add_argument("--api-key", help="Google AI API key (otherwise uses env vars)")
    parser.add_argument("--vertexai", action="store_true", help="Use Vertex AI instead of Google AI API")
    parser.add_argument("--project", help="Vertex AI project id")
    parser.add_argument("--location", help="Vertex AI location (e.g., us-central1)")
    parser.add_argument("--clarify", action="store_true", default=True, help="Ask clarifying questions")
    parser.add_argument("--no-clarify", dest="clarify", action="store_false", help="Skip clarifying questions")
    parser.add_argument("--context-file", help="Path to additional context to include in the prompt")
    parser.add_argument("--store-dir", help="Directory to store run data")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL, help="Polling interval seconds")
    parser.add_argument("--max-wait", type=int, default=DEFAULT_MAX_WAIT_SECONDS, help="Max wait seconds (0 for none)")
    parser.add_argument("--no-wait", action="store_true", help="Start research and exit without waiting")
    parser.add_argument("--dry-run", action="store_true", help="Print the prompt and exit")
    parser.add_argument("--list", action="store_true", help="List stored runs")
    parser.add_argument("--show", help="Show a stored run by id (prefix allowed)")
    parser.add_argument("--resume", help="Resume a running run by id (prefix allowed)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_wait == 0:
        args.max_wait = None

    base_dir = resolve_base_dir(args.store_dir)
    ensure_base_dir(base_dir)

    if args.list:
        list_runs(base_dir)
        return
    if args.show:
        show_run(base_dir, args.show)
        return
    if args.resume:
        resume_research(args)
        return

    run_new_research(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}")
        sys.exit(1)

