from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_INPUT = ROOT / "requirements.in"
DEV_INPUT = ROOT / "requirements-dev.in"
RUNTIME_LOCK = ROOT / "requirements.txt"
DEV_LOCK = ROOT / "requirements-dev.txt"
DEFAULT_PYTHON_VERSION = "3.11"
DEFAULT_INDEX_URL = "https://pypi.org/simple"
DEFAULT_AUDIT_SERVICE = "osv"
BUFFER_DAYS = 7

HASH_PATTERN = re.compile(r"--hash=sha256:[0-9a-f]{64}")
HASH_DIGEST_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})")
LOCK_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<extras>\[[^]]+\])?==(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)$"
)
INPUT_NAME_PATTERN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<extras>\[[^]]+\])?")
LOCK_CUTOFF_PATTERN = re.compile(r"--exclude-newer\s+(\S+)")


@dataclass(frozen=True)
class LockedRequirement:
    raw_name: str
    project_name: str
    version: str
    marker: str | None
    hashes: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compile hash-locked runtime and development requirements with uv, "
            "verify PyPI upload cutoffs, and audit the results."
        )
    )
    parser.add_argument(
        "--cutoff",
        help=(
            "RFC 3339 cutoff timestamp. Defaults to current UTC time minus "
            f"{BUFFER_DAYS} days."
        ),
    )
    parser.add_argument(
        "--python-version",
        default=DEFAULT_PYTHON_VERSION,
        help=f"Python version to resolve for (default: {DEFAULT_PYTHON_VERSION}).",
    )
    parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help=f"Package index to resolve against (default: {DEFAULT_INDEX_URL}).",
    )
    parser.add_argument(
        "--audit-service",
        default=DEFAULT_AUDIT_SERVICE,
        choices=("osv", "pypi"),
        help=f"Vulnerability service for pip-audit (default: {DEFAULT_AUDIT_SERVICE}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Regenerate into temporary files and fail if committed locks do not exactly "
            "match the dependency graphs resolved from the .in manifests."
        ),
    )
    return parser.parse_args()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def default_cutoff(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0) - timedelta(days=BUFFER_DAYS)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lock_cutoff(lock_file: Path) -> datetime:
    header = "\n".join(lock_file.read_text(encoding="utf-8").splitlines()[:5])
    match = LOCK_CUTOFF_PATTERN.search(header)
    if not match:
        raise ValueError(f"Lock file does not record --exclude-newer cutoff: {lock_file}")
    return parse_timestamp(match.group(1))


def resolve_cutoff(raw_cutoff: str | None, *, check: bool = False) -> datetime:
    if raw_cutoff:
        return parse_timestamp(raw_cutoff)
    if check:
        return lock_cutoff(RUNTIME_LOCK)
    return default_cutoff()


def ensure_tooling() -> None:
    missing: list[str] = []
    for module_name, package_name in (("uv", "uv"), ("pip_audit", "pip-audit")):
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            "Missing lock tooling: "
            f"{joined}. Install the development environment from requirements-dev.txt first."
        )


def run(command: list[str]) -> None:
    printable = subprocess.list2cmdline(command)
    print(f"+ {printable}")
    subprocess.run(command, cwd=ROOT, check=True)


def compile_lock(
    *,
    input_file: Path,
    output_file: Path,
    cutoff: datetime,
    python_version: str,
    index_url: str,
) -> None:
    command = [
        sys.executable,
        "-m",
        "uv",
        "pip",
        "compile",
        str(input_file.name),
        "--output-file",
        str(output_file.name if output_file.parent == ROOT else output_file),
        "--python-version",
        python_version,
        "--universal",
        "--generate-hashes",
        "--exclude-newer",
        format_timestamp(cutoff),
        "--index-url",
        index_url,
        "--upgrade",
    ]
    run(command)
    filter_lock_hashes_by_cutoff(output_file, cutoff)


def audit_lock(lock_file: Path, audit_service: str) -> None:
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--requirement",
        str(lock_file.name),
        "--vulnerability-service",
        audit_service,
        "--disable-pip",
        "--no-deps",
        "--progress-spinner",
        "off",
    ]
    run(command)


def iter_logical_lines(path: Path) -> Iterator[str]:
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        piece = raw_line.rstrip()
        if pending:
            piece = piece.lstrip()
        if piece.endswith("\\"):
            pending += piece[:-1].rstrip() + " "
            continue
        logical = (pending + piece).strip()
        pending = ""
        if logical and not logical.startswith("#"):
            yield logical
    if pending:
        raise ValueError(f"Unterminated continuation in {path}")


def parse_locked_requirements(lock_file: Path) -> list[LockedRequirement]:
    requirements: list[LockedRequirement] = []
    for logical_line in iter_logical_lines(lock_file):
        if logical_line.startswith("-"):
            raise ValueError(f"Lock directives are not allowed: {logical_line}")
        hashes = tuple(HASH_PATTERN.findall(logical_line))
        if not hashes:
            raise ValueError(f"Locked requirement is missing hashes: {logical_line}")
        base = HASH_PATTERN.sub("", logical_line).strip()
        marker: str | None = None
        if ";" in base:
            base, marker = [part.strip() for part in base.split(";", 1)]
        match = LOCK_PATTERN.fullmatch(base)
        if not match:
            raise ValueError(f"Unable to parse locked requirement line: {logical_line}")
        raw_name = match.group("name")
        requirements.append(
            LockedRequirement(
                raw_name=raw_name,
                project_name=normalize_name(raw_name),
                version=match.group("version"),
                marker=marker,
                hashes=hashes,
            )
        )
    return requirements


def parse_direct_projects(input_file: Path) -> list[str]:
    direct_projects: list[str] = []
    for logical_line in iter_logical_lines(input_file):
        if logical_line.startswith("-"):
            continue
        requirement_text = logical_line.split(";", 1)[0].strip()
        match = INPUT_NAME_PATTERN.match(requirement_text)
        if not match:
            raise ValueError(f"Unable to parse input requirement line: {logical_line}")
        direct_projects.append(normalize_name(match.group("name")))
    return direct_projects


@lru_cache(maxsize=None)
def fetch_release_metadata(project_name: str, version: str) -> dict[str, object]:
    url = f"https://pypi.org/pypi/{project_name}/{version}/json"
    request = Request(url, headers={"User-Agent": "apollo-streaming-lab-locker/1"})
    try:
        with urlopen(request) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"PyPI metadata lookup failed for {project_name}=={version}: HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"PyPI metadata lookup failed for {project_name}=={version}: {error.reason}") from error


def verify_release_cutoff(requirements: Iterable[LockedRequirement], cutoff: datetime) -> None:
    failures: list[str] = []
    for requirement in requirements:
        metadata = fetch_release_metadata(requirement.project_name, requirement.version)
        files_by_hash = _release_files_by_hash(metadata)
        for locked_hash in requirement.hashes:
            digest_match = HASH_DIGEST_PATTERN.fullmatch(locked_hash)
            if not digest_match:
                failures.append(
                    f"{requirement.raw_name}=={requirement.version}: invalid hash {locked_hash}"
                )
                continue
            digest = digest_match.group(1)
            file_info = files_by_hash.get(digest)
            if file_info is None:
                failures.append(
                    f"{requirement.raw_name}=={requirement.version}: locked hash {digest} "
                    "does not match a PyPI release file"
                )
                continue
            filename, upload_time = file_info
            if upload_time > cutoff:
                failures.append(
                    f"{requirement.raw_name}=={requirement.version}: {filename} upload "
                    f"{format_timestamp(upload_time)} is newer than cutoff "
                    f"{format_timestamp(cutoff)}"
                )
    if failures:
        joined = "\n".join(f"  - {failure}" for failure in failures)
        raise SystemExit(f"Cutoff verification failed:\n{joined}")


def _release_files_by_hash(
    metadata: dict[str, object],
) -> dict[str, tuple[str, datetime]]:
    files_by_hash: dict[str, tuple[str, datetime]] = {}
    for raw_file in metadata.get("urls", []):
        if not isinstance(raw_file, dict):
            continue
        digests = raw_file.get("digests")
        upload_time = raw_file.get("upload_time_iso_8601")
        filename = raw_file.get("filename")
        if not isinstance(digests, dict) or not upload_time or not filename:
            continue
        digest = digests.get("sha256")
        if digest:
            files_by_hash[str(digest)] = (
                str(filename),
                parse_timestamp(str(upload_time)),
            )
    return files_by_hash


def filter_lock_hashes_by_cutoff(lock_file: Path, cutoff: datetime) -> None:
    """Remove hashes for distribution files uploaded after the holdback cutoff."""
    lines = lock_file.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        is_requirement = (
            stripped
            and not line[0].isspace()
            and not stripped.startswith(("#", "-"))
            and "==" in stripped
        )
        if not is_requirement:
            output.append(line)
            index += 1
            continue

        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            candidate_stripped = candidate.strip()
            if (
                candidate_stripped
                and not candidate[0].isspace()
                and not candidate_stripped.startswith(("#", "-"))
                and "==" in candidate_stripped
            ):
                break
            end += 1
        block = lines[index:end]

        header = stripped.rstrip("\\").strip()
        if ";" in header:
            header = header.split(";", 1)[0].strip()
        match = LOCK_PATTERN.fullmatch(header)
        if not match:
            raise ValueError(f"Unable to parse lock header: {line}")
        project = normalize_name(match.group("name"))
        version = match.group("version")
        metadata = fetch_release_metadata(project, version)
        files_by_hash = _release_files_by_hash(metadata)

        retained_hashes: list[str] = []
        comments: list[str] = []
        for block_line in block[1:]:
            hash_match = HASH_DIGEST_PATTERN.search(block_line)
            if hash_match:
                digest = hash_match.group(1)
                file_info = files_by_hash.get(digest)
                if file_info is None:
                    raise ValueError(
                        f"{project}=={version}: generated hash {digest} is not a PyPI file"
                    )
                if file_info[1] <= cutoff:
                    retained_hashes.append(digest)
            else:
                comments.append(block_line)
        if not retained_hashes:
            raise SystemExit(
                f"{project}=={version}: no distribution files are old enough for cutoff "
                f"{format_timestamp(cutoff)}"
            )

        output.append(line.rstrip().rstrip("\\").rstrip() + " \\")
        for hash_index, digest in enumerate(retained_hashes):
            continuation = " \\" if hash_index < len(retained_hashes) - 1 else ""
            output.append(f"    --hash=sha256:{digest}{continuation}")
        output.extend(comments)
        index = end

    lock_file.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")


def collect_direct_versions(
    direct_projects: Iterable[str],
    requirements: Iterable[LockedRequirement],
) -> list[str]:
    by_project: dict[str, LockedRequirement] = {
        requirement.project_name: requirement for requirement in requirements
    }
    selected: list[str] = []
    for project_name in direct_projects:
        requirement = by_project.get(project_name)
        if requirement is None:
            raise SystemExit(f"Direct dependency {project_name} was not present in the compiled lock file.")
        selected.append(f"{requirement.raw_name}=={requirement.version}")
    return selected


def collect_marker_summary(requirements: Iterable[LockedRequirement]) -> list[str]:
    marker_entries = [
        f"{requirement.raw_name}=={requirement.version}; {requirement.marker}"
        for requirement in requirements
        if requirement.marker
    ]
    return sorted(marker_entries, key=str.casefold)


def lock_signature(lock_file: Path) -> tuple[LockedRequirement, ...]:
    return tuple(parse_locked_requirements(lock_file))


def assert_lock_matches(generated: Path, committed: Path) -> None:
    generated_signature = lock_signature(generated)
    committed_signature = lock_signature(committed)
    if generated_signature != committed_signature:
        generated_set = set(generated_signature)
        committed_set = set(committed_signature)
        extra = committed_set - generated_set
        missing = generated_set - committed_set
        details: list[str] = []
        if extra:
            details.append(
                "committed-only: "
                + ", ".join(
                    f"{item.raw_name}=={item.version}" for item in sorted(
                        extra, key=lambda item: (item.project_name, item.version)
                    )
                )
            )
        if missing:
            details.append(
                "generated-only: "
                + ", ".join(
                    f"{item.raw_name}=={item.version}" for item in sorted(
                        missing, key=lambda item: (item.project_name, item.version)
                    )
                )
            )
        if not details:
            details.append("versions, markers, or allowed artifact hashes differ")
        raise SystemExit(
            f"{committed.name} does not match {generated.name}: " + "; ".join(details)
        )


def print_summary(
    *,
    cutoff: datetime,
    runtime_direct_versions: list[str],
    dev_direct_versions: list[str],
    runtime_markers: list[str],
    dev_markers: list[str],
) -> None:
    print(f"Resolved with cutoff: {format_timestamp(cutoff)}")
    print("Runtime direct selections:")
    for version in runtime_direct_versions:
        print(f"  - {version}")
    print("Dev direct selections:")
    for version in dev_direct_versions:
        print(f"  - {version}")
    print("Runtime marker entries:")
    for marker_entry in runtime_markers or ["  (none)"]:
        print(marker_entry if marker_entry.startswith("  ") else f"  - {marker_entry}")
    print("Dev-only/additional marker entries:")
    dev_only_markers = [entry for entry in dev_markers if entry not in runtime_markers]
    for marker_entry in dev_only_markers or ["  (none)"]:
        print(marker_entry if marker_entry.startswith("  ") else f"  - {marker_entry}")


def main() -> None:
    args = parse_args()
    cutoff = resolve_cutoff(args.cutoff, check=args.check)
    ensure_tooling()

    if args.check:
        with tempfile.TemporaryDirectory(prefix="asl-lock-check-") as temp_dir:
            runtime_generated = Path(temp_dir) / "requirements.txt"
            dev_generated = Path(temp_dir) / "requirements-dev.txt"
            compile_lock(
                input_file=RUNTIME_INPUT,
                output_file=runtime_generated,
                cutoff=cutoff,
                python_version=args.python_version,
                index_url=args.index_url,
            )
            assert_lock_matches(runtime_generated, RUNTIME_LOCK)
            compile_lock(
                input_file=DEV_INPUT,
                output_file=dev_generated,
                cutoff=cutoff,
                python_version=args.python_version,
                index_url=args.index_url,
            )
            assert_lock_matches(dev_generated, DEV_LOCK)
    else:
        compile_lock(
            input_file=RUNTIME_INPUT,
            output_file=RUNTIME_LOCK,
            cutoff=cutoff,
            python_version=args.python_version,
            index_url=args.index_url,
        )
        compile_lock(
            input_file=DEV_INPUT,
            output_file=DEV_LOCK,
            cutoff=cutoff,
            python_version=args.python_version,
            index_url=args.index_url,
        )

    runtime_requirements = parse_locked_requirements(RUNTIME_LOCK)
    dev_requirements = parse_locked_requirements(DEV_LOCK)
    verify_release_cutoff(runtime_requirements, cutoff)
    verify_release_cutoff(dev_requirements, cutoff)

    audit_lock(RUNTIME_LOCK, args.audit_service)
    audit_lock(DEV_LOCK, args.audit_service)

    print_summary(
        cutoff=cutoff,
        runtime_direct_versions=collect_direct_versions(parse_direct_projects(RUNTIME_INPUT), runtime_requirements),
        dev_direct_versions=collect_direct_versions(parse_direct_projects(DEV_INPUT), dev_requirements),
        runtime_markers=collect_marker_summary(runtime_requirements),
        dev_markers=collect_marker_summary(dev_requirements),
    )


if __name__ == "__main__":
    main()
