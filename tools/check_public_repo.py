"""Fail on tracked secrets, private state, or environment-specific public examples."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PUBLIC_FILES = (
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "NOTICE.md",
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/pull_request_template.md",
)

FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env$", re.IGNORECASE),
    re.compile(r"(^|/)data/", re.IGNORECASE),
    re.compile(r"(^|/)(?:\.venv|venv|\.pytest_cache)/", re.IGNORECASE),
    re.compile(r"\.(?:db|sqlite|sqlite3)$", re.IGNORECASE),
    re.compile(r"(^|/)(?:screenshot-token|tailscale-state|artifacts)(?:[./]|$)", re.IGNORECASE),
    re.compile(r"\.(?:pem|p12|pfx|key)$", re.IGNORECASE),
)

CONTENT_PATTERNS = (
    (
        "GitHub token",
        re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("Tailscale key", re.compile(r"\btskey-[A-Za-z0-9_-]{16,}\b")),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "environment-specific identifier",
        re.compile(
            r"BananaStandMoney|NegativeZone|DOMINO|watchtower|"
            r"192\.168\.(?:69|86)\.|"
            r"C:\\Users\\carlt|/home/carlt|"
            r"carltoncameron50@gmail\.com",
            re.IGNORECASE,
        ),
    ),
)
CONTENT_SCAN_EXCLUDES = {"tools/check_public_repo.py"}


@dataclass(frozen=True)
class Finding:
    location: str
    message: str


def tracked_files(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        root / value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    ]


def check_paths(paths: Iterable[Path], root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if any(pattern.search(relative) for pattern in FORBIDDEN_PATH_PATTERNS):
            findings.append(Finding(relative, "sensitive/local path must not be tracked"))
    return findings


def check_content(paths: Iterable[Path], root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            content = path.read_bytes()
        except OSError as exc:
            findings.append(Finding(path.relative_to(root).as_posix(), f"cannot read: {exc}"))
            continue
        if b"\0" in content:
            continue
        text = content.decode("utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        if relative in CONTENT_SCAN_EXCLUDES:
            continue
        for label, pattern in CONTENT_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(Finding(f"{relative}:{line}", label))
    return findings


def check_required_files(root: Path = ROOT) -> list[Finding]:
    return [
        Finding(relative, "required public repository file is missing")
        for relative in REQUIRED_PUBLIC_FILES
        if not (root / relative).is_file()
    ]


def run(root: Path = ROOT) -> list[Finding]:
    paths = tracked_files(root)
    return check_required_files(root) + check_paths(paths, root) + check_content(paths, root)


def main() -> None:
    findings = run()
    if findings:
        print("Public repository check failed:")
        for finding in findings:
            print(f"  - {finding.location}: {finding.message}")
        raise SystemExit(1)
    print("Public repository check passed.")


if __name__ == "__main__":
    main()
