# Renovate

Renovate automatically tracks dependency versions across the homelab repo and opens pull requests when updates are available. It runs via the free [Mend Renovate GitHub App](https://github.com/apps/renovate) -- no self-hosted infrastructure required.

## What Gets Tracked

| Category | Manager | Count | Examples |
|----------|---------|-------|---------|
| Helm charts | `argocd` (built-in) | 15 | kube-prometheus-stack, app-template, loki, alloy |
| Container images | `regex` (custom) | 11 | linuxserver/sonarr, gethomepage/homepage, gluetun |
| ArgoCD install URL | `regex` (custom) | 1 | argoproj/argo-cd v3.3.4 in kustomization.yml |
| GitHub Actions | `github-actions` (built-in) | 4 | actions/checkout, actions/setup-python |

### How Each Manager Works

**ArgoCD manager**: Built into Renovate. Detects `targetRevision` in ArgoCD `Application` manifests and checks the Helm repo (`repoURL`) for newer chart versions. Configured via `fileMatch` to scan all `k8s/**/*.yml` files.

**Container image regex**: Two custom patterns handle the two image reference styles in the repo:

- `repository` + `tag` on separate lines (bjw-s app-template pattern)
- Inline `image: name:tag` (e.g., Velero init containers)

**ArgoCD install URL regex**: Matches the version in the raw GitHub URL used to install ArgoCD itself (`https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.4/manifests/install.yaml`).

## Schedule and Behavior

| Setting | Value |
|---------|-------|
| Schedule | Weekly, Saturday mornings |
| Automerge | Disabled (all updates require manual merge) |
| Dependency Dashboard | Enabled (GitHub issue tracking all pending updates) |
| Semantic commits | Enabled (e.g., `chore(deps): update ...`) |

## Grouping

Related dependencies are grouped into single PRs to reduce noise:

| Group | Packages |
|-------|----------|
| app-template chart | All 14 apps using the bjw-s app-template Helm chart |
| linuxserver images | All `lscr.io/linuxserver/*` container images |
| grafana stack | Loki + Alloy Helm charts |
| intel gpu | GPU device plugin + operator Helm charts |

Everything else gets individual PRs.

## Reviewing PRs

1. Renovate PRs include a changelog summary and compatibility notes
2. Check the ArgoCD diff after merging -- ArgoCD will show the pending sync
3. For Helm chart major version bumps, review the chart's migration guide before merging
4. For infrastructure charts (cert-manager, kube-prometheus-stack, loki), test in a maintenance window

## Adding New Dependencies

When adding a new ArgoCD Application with a Helm chart, Renovate picks it up automatically via the `argocd` manager (no config changes needed).

For new container images using the `repository` + `tag` pattern (bjw-s app-template), the existing regex handles them automatically.

For non-standard version patterns, add a new entry to `customManagers` in `renovate.json`.

## Configuration

The full configuration lives in `renovate.json` at the repo root.

## Upstream Documentation

<https://docs.renovatebot.com/>
