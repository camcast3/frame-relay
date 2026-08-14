"""Supply-chain policy must remain enforced by repository manifests."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools import lock_requirements

ROOT = Path(__file__).resolve().parent.parent


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_requirements_are_exact_and_hashed():
    runtime = lock_requirements.parse_locked_requirements(ROOT / "requirements.txt")
    dev = lock_requirements.parse_locked_requirements(ROOT / "requirements-dev.txt")
    assert runtime and dev
    assert all(requirement.hashes for requirement in runtime + dev)


def test_runtime_lock_excludes_dev_only_tools():
    runtime = _text("requirements.txt").lower()
    dev = _text("requirements-dev.txt").lower()
    for package in ("pytest==", "pip-audit==", "uv==", "httpx=="):
        assert package not in runtime
        assert package in dev


def test_container_references_are_immutable_and_fail_closed():
    dockerfile = _text("Dockerfile")
    compose_text = _text("docker-compose.yaml")
    compose = yaml.safe_load(compose_text)
    assert re.search(r"^FROM\s+python:3\.11\.\d+-[^@\s]+@sha256:[0-9a-f]{64}$",
                     dockerfile, re.MULTILINE)
    assert "pip install --no-cache-dir --require-hashes -r requirements.txt" in dockerfile
    assert compose["services"]["tailscale"]["image"] == (
        "tailscale/tailscale:security-review-required@sha256:"
        + ("0" * 64)
    )
