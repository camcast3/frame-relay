# Security policy

## Supported versions

Apollo Streaming Lab is an early-stage self-hosted project. Security fixes are made on the
current `main` branch; older commits and deployments are not supported release lines.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting:

<https://github.com/camcast3/apollo-streaming-lab/security/advisories/new>

Include:

- affected commit or deployment mode
- reproduction steps or a proof of concept
- expected impact
- any suggested mitigation

Please avoid accessing data that is not yours and give maintainers reasonable time to investigate
before public disclosure.

## Important trust boundary

The hub currently has no general application authentication. Anyone who can reach its HTTP port
can view and modify sessions and access persisted artifacts. Deploy it only on a trusted LAN,
behind WireGuard/Tailscale, or behind another authenticated reverse proxy. Never expose the LAN
Compose port directly to the public internet.

Screenshot-request endpoints use a shared token, but completed screenshots become normal
artifacts. Logs and screenshots may contain device names, network identifiers, desktop content,
or notifications. Review data before sharing a database or artifact directory.

Operational details are documented in
[docs/maintainer/security-and-operations.md](./docs/maintainer/security-and-operations.md).

## Dependency and container reports

Dependency changes must preserve the repository's hash locks, seven-day release holdback, pinned
container digests, and critical/high vulnerability gates. See
[docs/maintainer/dependency-security.md](./docs/maintainer/dependency-security.md).
