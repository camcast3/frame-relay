# Public repository release checklist

Use this checklist immediately before changing repository visibility.

## Source and history

- [ ] `python tools/check_public_repo.py` passes.
- [ ] `git status --ignored --short` confirms local `.env`, `data/`, virtual environments,
      logs, screenshots, and tokens remain ignored.
- [ ] Review all branches, tags, commit metadata, and historical blobs for secrets and personal
      identifiers. Current-file scanning cannot remove information already present in history.
- [ ] Decide whether any non-noreply author email in existing commits must be rewritten before
      publication. A history rewrite requires coordinated force-pushes of every published ref.
- [ ] Remove obsolete private branches and tags that should not become visible.

## GitHub settings

- [ ] Keep the repository private while this checklist is incomplete.
- [ ] Enable private vulnerability reporting before publishing; SECURITY.md and the code of
      conduct use it as their confidential contact channel.
- [ ] Enable secret scanning, push protection, dependency graph, and Dependabot alerts where the
      account/repository supports them.
- [ ] Require the CI workflow on pull requests and protect `main` from direct pushes.
- [ ] Confirm Issues are enabled and the security issue link opens the private advisory form.
- [ ] Set a concise description, topics, and optional homepage.
- [ ] Review Actions permissions; default to read-only and approve write permissions per workflow.

## Documentation and operations

- [ ] README clearly states the project is experimental, self-hosted, and unauthenticated.
- [ ] LICENSE, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, SUPPORT, and NOTICE are present.
- [ ] Deployment examples use placeholders or documentation-safe values.
- [ ] Samples are synthetic/sanitized and tests still parse them.
- [ ] The LAN Compose warning makes clear that port 8080 must not be exposed publicly.
- [ ] Tailnet deployment remains fail-closed until a reviewed image satisfies dependency policy.

## Final verification

```powershell
.\.venv\Scripts\python.exe tools\check_public_repo.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\lock_requirements.py --check
docker build -t apollo-streaming-lab:public-check .
```

After the visibility change, verify the public landing page, issue forms, security policy,
license detection, CI status, and clone/setup instructions from a signed-out browser session.
