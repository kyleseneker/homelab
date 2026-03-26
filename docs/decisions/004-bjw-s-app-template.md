# ADR-004: bjw-s app-template for Application Deployments

## Status

Accepted

## Context

Each application needs Kubernetes manifests for Deployment/StatefulSet, Service, HTTPRoute, PVC, and security contexts. Writing raw manifests for 15+ applications creates significant boilerplate and makes it easy to miss security settings or probe configurations.

## Decision

Use the [bjw-s app-template](https://bjw-s-labs.github.io/helm-charts) Helm chart for all application deployments. Application-specific configuration is provided via inline `valuesObject` in each ArgoCD Application manifest.

## Alternatives Considered

- **Raw Kubernetes manifests**: Full control but massive boilerplate. A single application requires 3-5 separate YAML files (Deployment, Service, HTTPRoute, PVC, PDB).
- **Kustomize overlays**: Good for patching base manifests but doesn't eliminate the need to maintain base templates. Overlay composition can become hard to reason about.
- **Per-app Helm charts**: Each upstream project's Helm chart has different value schemas, naming conventions, and defaults. Maintaining familiarity with 15 different chart APIs is impractical.

## Rationale

- **Consistent interface**: Every application uses the same value schema for containers, services, routes, persistence, and security contexts. Learning one chart covers all apps.
- **Security by default**: The template makes it natural to set `securityContext`, `resources`, `probes`, and `persistence` in a uniform structure, reducing the chance of omission.
- **Inline values**: ArgoCD's `valuesObject` embeds Helm values directly in the Application manifest. Each app is fully defined in a single file -- no separate `values.yaml` to track.
- **Community-maintained**: The chart is actively developed with regular releases tracked by Renovate.

## Consequences

- Tied to the bjw-s chart's value schema. Breaking changes in major versions require updating all application manifests.
- Some advanced Kubernetes features may require workarounds if the chart doesn't expose them directly.
- The chart version should be kept consistent across applications to avoid behavioral differences.
