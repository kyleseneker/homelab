# Renovate

Renovate scans through the installed GitHub App and proposes reviewed dependency updates on Saturday mornings. Configuration lives in `renovate.json`; it does not deploy bootstrap resources or upgrade an existing Kubernetes node.

## Discovery

| Dependency | Mechanism |
|---|---|
| HTTP Helm charts | Custom regex reads `chartRepo`, `chartName`, `chartVersion` in ApplicationSet `config.yml` |
| OCI media-operator charts | Custom regex maps the registry/chart to the Docker datasource with semantic chart versions |
| Application images | Custom regex reads `repository`/`tag` and inline `image` references |
| ArgoCD installation | Custom regex reads the pinned raw GitHub manifest URL |
| GitHub Actions and Terraform | Built-in ecosystem managers |

The built-in ArgoCD manager cannot discover arbitrary metadata files merely because they live under `k8s/`. The custom chart managers close that gap. A regression test checks every current Helm config is extracted once with the correct unquoted chart version.

Related packages are grouped, including app-template consumers, monitoring components, backup components and all media-operator charts. The operator group must keep CRDs and managers on one release. Container digest pinning is configured; audit actual references before claiming every image is pinned.

The etcd backup image is excluded from independent updates because it follows kubeadm's etcd version. Update it deliberately with the [Kubernetes upgrade procedure](../runbooks/upgrading-kubernetes.md).

## Review and verification

Run `make k8s-render` and the relevant regression checks before merging. Review upstream migration/compatibility notes for platform changes. After a Renovate configuration change, verify the next extraction/dependency dashboard and generated PRs; local regex tests do not exercise the hosted service.

ArgoCD bootstrap updates require an explicit `make k8s-bootstrap` and subsequent drift check. Application changes require a post-deployment health check; a successful version PR does not prove application API behavior, backup compatibility or recovery.

See [ADR-012](../decisions/012-renovate-dependency-management.md) and [Renovate custom regex managers](https://docs.renovatebot.com/modules/manager/regex/).
