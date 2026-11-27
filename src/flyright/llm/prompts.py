"""Discover and load versioned FlyRight prompts."""

import re
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"
VERSION_PATTERN = re.compile(r"^([a-z][a-z0-9_]*)_v(\d+)\.md$")


def list_versions(task: str, prompts_dir: Path | None = None) -> list[str]:
    """Return available prompt versions in numeric order."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", task):
        raise ValueError(f"Invalid prompt task: {task}")

    directory = Path(prompts_dir) if prompts_dir is not None else PROMPT_DIR
    versions = []

    for path in directory.glob(f"{task}_v*.md"):
        match = VERSION_PATTERN.match(path.name)
        if match and match.group(1) == task:
            versions.append((int(match.group(2)), f"v{match.group(2)}"))

    return [version for _, version in sorted(versions)]


def find_prompt_versions(task: str, prompts_dir: Path | None = None) -> list[str]:
    """Compatibility alias for listing prompt versions."""
    return list_versions(task, prompts_dir)


def load_prompt(
    task: str,
    version: str | int | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Load a specified version, or the latest available version."""
    available = list_versions(task, prompts_dir)

    if not available:
        raise FileNotFoundError(f"No prompts found for task: {task}")

    if version is None:
        selected = available[-1]
    else:
        selected = str(version)
        if selected.isdigit():
            selected = f"v{selected}"
        if selected not in available:
            raise FileNotFoundError(
                f"Prompt {task}_{selected}.md not found. Available: {available}"
            )

    directory = Path(prompts_dir) if prompts_dir is not None else PROMPT_DIR
    return (directory / f"{task}_{selected}.md").read_text(encoding="utf-8")


def latest_version(task: str, prompts_dir: Path | None = None) -> str:
    """Return the newest available version."""
    available = list_versions(task, prompts_dir)
    if not available:
        raise FileNotFoundError(f"No prompts found for task: {task}")
    return available[-1]
