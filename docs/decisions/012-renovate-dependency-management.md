# ADR-012: Renovate for Dependency Management

## Status

Accepted

## Context

The cluster runs 15+ Helm charts and container images that receive regular upstream updates. Without automated tracking, dependencies drift silently and security patches go unnoticed until something breaks.

## Decision

Use the free Mend Renovate GitHub App to scan the repository on a weekly schedule (Saturday mornings) and open pull requests for dependency updates. All updates require manual review — automerge is disabled. Custom regex managers detect container image tags and Helm chart versions in ArgoCD Application manifests and bjw-s app-template values files.

## Alternatives Considered

- **Dependabot**: GitHub's built-in dependency updater. Limited to standard package ecosystems (npm, pip, Docker). Cannot parse ArgoCD `targetRevision` fields, Helm chart references in `config.yaml`, or the bjw-s `repository`/`tag` pattern without custom configuration. Renovate's regex managers handle all of these natively.
- **Flux Image Automation**: Watches container registries and commits updated image tags directly to Git. Tightly coupled to Flux's GitOps model. Would require running Flux alongside ArgoCD solely for image updates.
- **Manual tracking**: Check upstream releases periodically. Doesn't scale and relies on remembering to check.

## Rationale

- **Broad ecosystem support**: Renovate's built-in ArgoCD manager detects `targetRevision` in Application manifests. Custom regex managers cover the remaining patterns (inline `image: name:tag`, separate `repository`/`tag` lines, GitHub release URLs).
- **Grouping strategy**: Related updates are grouped into single PRs to reduce noise: all bjw-s app-template consumers, all linuxserver images, Grafana stack charts (Loki + Alloy), and Intel GPU charts each produce one PR instead of many.
- **No automerge**: Every update goes through manual review. This is deliberate — Helm chart major versions and container image updates can introduce breaking changes that automated tests cannot fully validate in this environment.
- **Dependency dashboard**: Renovate maintains a GitHub issue as a dashboard listing all pending updates, their status, and any errors. Provides visibility without checking individual PRs.
- **Digest pinning**: Container images are pinned to digests for reproducibility. Renovate tracks both tag and digest updates.
- **Scheduling**: Saturday morning runs batch updates into a predictable window, avoiding mid-week disruption.

## Consequences

- Renovate runs as an external GitHub App, not in-cluster. If Mend's service is unavailable, updates stop until it recovers.
- Custom regex managers must be maintained as the repository's manifest format evolves. Adding a new pattern (e.g., a new Helm chart reference style) requires updating `renovate.json`.
- No automerge means updates require human attention. During periods of inactivity, PRs can accumulate.
