# ADR-003: ArgoCD with App-of-Apps Pattern

## Status

Accepted

## Context

The cluster needs a GitOps controller to reconcile the desired state in Git with the live cluster state. The controller must handle Helm charts, plain YAML manifests, and ordered deployment of interdependent components.

## Decision

Use ArgoCD with a single root Application that discovers child Applications via recursive directory scanning. Each application is defined as its own `application.yml` with explicit sync wave annotations.

## Alternatives Considered

- **Flux v2**: Comparable GitOps controller with HelmRelease and Kustomization CRDs. Uses a reconciliation-loop model rather than ArgoCD's sync model. No built-in UI.
- **ArgoCD with ApplicationSets**: Templates multiple Applications from a single generator. Trades per-app granularity for reduced boilerplate.
- **Manual kubectl apply**: Not viable for a reproducible, self-healing cluster.

## Rationale

- **Per-app control**: Each application has its own `application.yml` with distinct Helm values, namespace, sync wave, and sync options. This granularity is important when applications have unique configuration (e.g., GPU node selectors, VPN sidecars, custom probes).
- **Sync waves**: `argocd.argoproj.io/sync-wave` annotations control deployment order (waves -3 through 2), ensuring Vault is ready before ESO, ESO before apps, etc. This eliminates race conditions during cluster bootstrap.
- **Directory recursion**: The root app recursively discovers all `*.yml` files under `k8s/clusters/homelabk8s01/`. Adding a new app is as simple as creating a directory with an `application.yml` -- no generator templates to update.
- **Self-heal + prune**: Automated sync with `selfHeal: true` and `prune: true` ensures Git remains the single source of truth. Manual `kubectl` changes are reverted.
- **UI**: ArgoCD's web UI provides at-a-glance health status and sync state, which is valuable for a homelab where you want quick visibility.

## Consequences

- ApplicationSets would reduce boilerplate for apps with identical patterns, but the homelab's apps are diverse enough that the boilerplate is justified.
- The root application must be bootstrapped manually (`kubectl apply -f k8s/bootstrap/root-app.yml`) during initial cluster setup.
