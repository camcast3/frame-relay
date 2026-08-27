# Contributing

Thanks for helping improve Frame Relay.

## Before starting

- Use an issue for bugs, feature proposals, or behavior changes large enough to need discussion.
- Do not include real credentials, private logs, personal screenshots, database files, SSIDs,
  public IPs, or other identifying environment data.
- Keep changes focused. Update the directly related user and maintainer documentation.

## Development setup

Python 3.11 is the project baseline. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

See [docs/maintainer/development.md](./docs/maintainer/development.md) for targeted tests, Docker
smoke checks, and import-time configuration details.

## Project rules

- Preserve the router → `service.py` → `db.py` layering.
- Treat `hub/models.py` as the shared API contract.
- Keep `collectors/frame_relay_collector/` standard-library only.
- Keep parser logic testable from sanitized captured samples.
- Use only the fixed network-path values documented by the project.
- Never weaken screenshot-token checks or expose additional artifact surfaces silently.
- Do not hand-edit dependency lock versions or hashes. Use `tools/lock_requirements.py`.
- Keep runtime images version-and-digest pinned.

The complete mandatory rules live in
[.github/copilot-instructions.md](./.github/copilot-instructions.md), with rationale in
[docs/maintainer/README.md](./docs/maintainer/README.md).

## Pull requests

1. Create a focused branch.
2. Add or update tests for behavioral changes.
3. Run the smallest relevant tests, then the full suite when the change is cross-cutting.
4. Run `python tools/check_public_repo.py`.
5. Update documentation and samples.
6. Explain user-visible behavior, security implications, and validation in the PR description.

By contributing, you agree that your contribution is licensed under the repository's
[MIT License](./LICENSE).
