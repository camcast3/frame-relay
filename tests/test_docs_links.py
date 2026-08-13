"""Repository-local Markdown links must survive documentation moves."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    files = [ROOT / "README.md", ROOT / ".github" / "copilot-instructions.md"]
    files.extend((ROOT / "docs").rglob("*.md"))
    return [path for path in files if path.exists()]


def _target_path(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = unquote(target.split("#", 1)[0])
    if not target:
        return None
    return (source.parent / target).resolve()


def test_repository_markdown_links_exist():
    broken: list[str] = []
    for source in _markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = _target_path(source, match.group(1))
            if target is not None and not target.exists():
                broken.append(
                    f"{source.relative_to(ROOT)} -> {match.group(1)}"
                )
    assert broken == [], "Broken Markdown links:\n" + "\n".join(broken)
