"""Lock generation enforces artifact-level release age, not just version age."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tools import lock_requirements


def _metadata(*files):
    return {
        "urls": [
            {
                "filename": filename,
                "digests": {"sha256": digest},
                "upload_time_iso_8601": uploaded,
            }
            for filename, digest, uploaded in files
        ]
    }


def test_filter_lock_removes_newly_uploaded_wheel_for_old_version(tmp_path, monkeypatch):
    old_hash = "a" * 64
    new_hash = "b" * 64
    lock = tmp_path / "requirements.txt"
    lock.write_text(
        "example==1.0 \\\n"
        f"    --hash=sha256:{old_hash} \\\n"
        f"    --hash=sha256:{new_hash}\n"
        "    # via test\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        lock_requirements,
        "fetch_release_metadata",
        lambda project, version: _metadata(
            ("example-1.0.tar.gz", old_hash, "2026-08-01T00:00:00Z"),
            ("example-1.0-py3-none-any.whl", new_hash, "2026-08-10T00:00:00Z"),
        ),
    )

    cutoff = datetime(2026, 8, 6, tzinfo=timezone.utc)
    lock_requirements.filter_lock_hashes_by_cutoff(lock, cutoff)
    content = lock.read_text(encoding="utf-8")
    assert old_hash in content
    assert new_hash not in content
    lock_requirements.verify_release_cutoff(
        lock_requirements.parse_locked_requirements(lock), cutoff
    )


def test_lock_parser_rejects_direct_urls_and_directives(tmp_path):
    direct_url = tmp_path / "url.txt"
    direct_url.write_text(
        "example @ https://example.invalid/example.whl \\\n"
        f"    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        lock_requirements.parse_locked_requirements(direct_url)

    directive = tmp_path / "directive.txt"
    directive.write_text(
        "--extra-index-url https://example.invalid/simple\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="directives"):
        lock_requirements.parse_locked_requirements(directive)


def test_lock_comparison_rejects_extra_hashed_package(tmp_path):
    expected = tmp_path / "expected.txt"
    committed = tmp_path / "committed.txt"
    expected.write_text(
        "example==1.0 \\\n"
        f"    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    committed.write_text(
        expected.read_text(encoding="utf-8")
        + "injected==9.9 \\\n"
        + f"    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="committed-only: injected==9.9"):
        lock_requirements.assert_lock_matches(expected, committed)
