# ADR-003: ArgoCD ApplicationSet with Git File Generator

## Status

Accepted

## Context

The cluster needs a GitOps controller to reconcile the desired state in Git with the live cluster state. The controller must handle Helm charts, plain YAML manifests, and independent deployment of components with diverse configurations.

## Decision

Use an ArgoCD ApplicationSet with a Git File Generator that discovers `config.yaml` files and generates independent Applications per component. Each app has:

- **`config.yaml`**: App metadata (name, namespace, chart info, sync options)
- **`values.yaml`**: Helm values
- **`kustomization.yaml`**: Lists supporting resources like PDBs, ExternalSecrets, and HTTPRoutes (only for apps that have them)

Helm apps use multi-source Applications: the chart source, a git ref for values, and optionally a kustomize source for supporting resources. Git-directory apps (network-policies, gateway, kyverno-policies) use a single git source.

A single ApplicationSet definition (`k8s/bootstrap/applicationsets/cluster-apps.yml`) uses `templatePatch` with Go template conditionals to handle both Helm and git source types.

## Alternatives Considered

- **App-of-apps with directory recursion**: A single root Application recursively discovers child Application manifests. Simpler setup, but all children sync as one operation -- one unhealthy app blocks all syncs.
- **Flux v2**: Comparable GitOps controller with HelmRelease and Kustomization CRDs. Uses a reconciliation-loop model rather than ArgoCD's sync model. No built-in UI.
- **Two separate ApplicationSets** (one for Helm, one for git): Avoids `templatePatch` conditionals but duplicates the template definition.

## Rationale

- **Independent syncs**: Each Application syncs in isolation. A broken app does not block fixes to other apps.
- **Per-app control**: Each `config.yaml` carries distinct sync options, namespace targeting, and chart versions.
- **Discoverability**: Adding a new app means creating a directory with `config.yaml` + `values.yaml`. The ApplicationSet generator picks it up automatically -- no generator template to update.
- **Multi-source**: Helm values live in git (`values.yaml`) rather than inline in the Application spec. Supporting resources (PDBs, ExternalSecrets, HTTPRoutes) are applied alongside the chart via a kustomize source, keeping everything in one Application.
- **Self-heal + prune**: Automated sync with `selfHeal: true` and `prune: true` ensures Git remains the single source of truth.
- **UI**: ArgoCD's web UI provides at-a-glance health status and sync state per app, which is valuable for quick visibility.

## Namespace Strategy

- **Single-app namespaces**: `CreateNamespace=true` on the Application. No separate namespace manifest.
- **Shared namespace (arr)**: A dedicated `arr/prereqs` Application owns the namespace, shared PV, and shared ConfigMap.

## Consequences

- `templatePatch` is required for conditional `sources` vs `source` rendering. If ArgoCD changes templatePatch behavior, the ApplicationSet definition may need updating.
- Supporting resources applied via kustomize must include CRD-defaulted fields explicitly (e.g., `conversionStrategy`, `decodingStrategy`, `weight` on HTTPRoute backendRefs) because server-side diff does not always account for these in multi-source apps.
- The ApplicationSet must be bootstrapped manually (`kubectl apply -k k8s/bootstrap/applicationsets/`) during initial cluster setup.
