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
POLL_INTERVAL = 10


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (cleaned or "topic")[:max_len]


def find_env_file() -> Path | None:
    for base in [Path.cwd(), *Path(__file__).resolve().parents]:
        env_path = base / ".env"
        if env_path.is_file():
            return env_path
    return None


def load_env() -> Path | None:
    env_path = find_env_file()
    if not env_path:
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
    return env_path


def build_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY in .env or environment.")
    return genai.Client(api_key=api_key)


def storage_root() -> Path:
    return Path(__file__).resolve().parents[1] / "storage"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def poll_result(client: genai.Client, interaction_id: str) -> tuple[str, str]:
    while True:
        interaction = client.interactions.get(interaction_id)
        status = interaction.status
        if status == "completed":
            output_text = interaction.outputs[-1].text if interaction.outputs else ""
            return status, output_text
        if status == "failed":
            error = interaction.error if hasattr(interaction, "error") else "Unknown error"
            return status, f"Research failed: {error}"
        time.sleep(POLL_INTERVAL)


def save_report(run_dir: Path, metadata: dict, output_text: str) -> None:
    ensure_dir(run_dir)
    report_lines = [
        "# Deep Research Report",
        "",
        f"- Run ID: {metadata.get('run_id', '')}",
        f"- Topic: {metadata.get('topic', '')}",
        f"- Created: {metadata.get('created_at', '')}",
        f"- Completed: {metadata.get('completed_at', '')}",
        f"- Status: {metadata.get('status', '')}",
        f"- Agent: {metadata.get('agent', '')}",
        f"- Interaction ID: {metadata.get('interaction_id', '')}",
        "",
        "## Output",
        "",
        output_text.strip(),
        "",
    ]
    (run_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single Gemini deep research query.")
    parser.add_argument("topic", nargs="?", help="Deep research topic")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Agent name to use")
    return parser.parse_args()


def get_topic(args: argparse.Namespace) -> str:
    if args.topic:
        return args.topic.strip()
    if sys.stdin.isatty():
        return input("Deep research topic: ").strip()
    return sys.stdin.read().strip()


def main() -> None:
    load_env()
    args = parse_args()
    topic = get_topic(args)
    if not topic:
        raise ValueError("A research topic is required.")

    client = build_client()
    interaction = client.interactions.create(
        input=topic,
        agent=args.agent,
        background=True,
    )

    print(f"Research started: {interaction.id}")
    created_at = utc_now_iso()
    status, output_text = poll_result(client, interaction.id)
    completed_at = utc_now_iso()

    run_id = f"{created_at.replace(':', '').replace('Z', '')}-{slugify(topic)}"
    run_dir = storage_root() / run_id
    metadata = {
        "run_id": run_id,
        "created_at": created_at,
        "completed_at": completed_at,
        "topic": topic,
        "agent": args.agent,
        "interaction_id": interaction.id,
        "status": status,
    }
    save_report(run_dir, metadata, output_text)

    print(f"Stored report: {run_dir / 'report.md'}")
    print(output_text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
