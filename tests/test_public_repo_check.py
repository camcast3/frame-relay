"""Public repository hygiene checks."""
from __future__ import annotations

from pathlib import Path

from tools import check_public_repo


def test_check_paths_rejects_local_state(tmp_path):
    root = tmp_path
    paths = [
        root / ".env",
        root / "data" / "asl.db",
        root / "docs" / "guide.md",
    ]

    findings = check_public_repo.check_paths(paths, root)

    assert {finding.location for finding in findings} == {".env", "data/asl.db"}


def test_check_content_rejects_token_and_personal_marker(tmp_path):
    root = tmp_path
    token_file = root / "config.txt"
    fake_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
    personal_marker = "DOM" + "INO"
    token_file.write_text(
        f"token={fake_token}\nhost={personal_marker}\n",
        encoding="utf-8",
    )

    findings = check_public_repo.check_content([token_file], root)

    assert [finding.message for finding in findings] == [
        "GitHub token",
        "environment-specific identifier",
    ]


def test_check_content_skips_binary_files(tmp_path):
    root = tmp_path
    image = root / "image.png"
    image.write_bytes(b"\x89PNG\x00" + b"DOM" + b"INO")

    assert check_public_repo.check_content([image], root) == []


def test_repository_passes_public_hygiene_check():
    assert check_public_repo.run() == []
