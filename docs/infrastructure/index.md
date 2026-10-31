# Infrastructure Components

This section documents the infrastructure layer of the homelab Kubernetes cluster. These components provide the foundational services that all applications depend on: certificate management, gateway routing, storage, monitoring, backups, and more.

## Component Overview

| Component | Namespace | Source | Chart / Type | Version |
|-----------|-----------|--------|--------------|---------|
| Vault | vault | helm | vault | 0.34.1 |
| External Secrets | external-secrets | helm | external-secrets | 2.14.0 |
| cert-manager | cert-manager | helm | cert-manager | v1.21.3 |
| trust-manager | cert-manager | helm | trust-manager | v0.26.0 |
| Gateway API CRDs | -- | git | (plain manifests) | -- |
| Gateway + Cilium L2 | default | git | (plain manifests) | -- |
| Metrics Server | kube-system | helm | metrics-server | 3.14.0 |
| NFS Provisioner | nfs-provisioner | helm | nfs-subdir-external-provisioner | 4.0.18 |
| Local-Path Provisioner | local-path-storage | kustomize | (plain manifests) | -- |
| Garage | backups | helm | app-template | 5.3.0 |
| MinIO (legacy, read-only) | backups | helm | minio | 5.4.0 |
| Velero | backups | helm | velero | 12.2.2 |
| etcd Backup | backups | git | (CronJob) | -- |
| Kyverno | kyverno | helm | kyverno | 3.9.2 |
| Kyverno Policies | -- | git | (plain manifests) | -- |
| Network Policies | (multiple) | git | (plain manifests) | -- |
| Intel GPU Operator | intel-gpu-operator | helm | intel-device-plugins-operator | 0.37.1 |
| Intel GPU Plugin | intel-gpu-operator | helm | intel-device-plugins-gpu | 0.37.1 |
| kube-prometheus-stack | monitoring | helm | kube-prometheus-stack | 83.7.0 |
| Loki | monitoring | helm | loki | 6.55.0 |
| Alloy | monitoring | helm | alloy | 1.15.0 |
| Blackbox Exporter | monitoring | helm | prometheus-blackbox-exporter | 11.20.2 |
| NUT Exporter | monitoring | helm | app-template | 5.3.0 |
| Authentik | auth | helm | authentik | 2026.2.1 |
| Reloader | kube-system | helm | reloader | 2.2.19 |
| Descheduler | kube-system | helm | descheduler | 0.36.0 |
| VPA | kube-system | helm | vertical-pod-autoscaler | 0.11.0 |
| Goldilocks | goldilocks | helm | goldilocks | 11.2.0 |

## Deployment Ordering

!!! warning "There is no ordering mechanism"
    The ApplicationSet controller creates Application objects directly, with no parent Application syncing them. `argocd.argoproj.io/sync-wave` is only honoured between resources *within* a sync, so a wave annotation on a generated Application is inert -- including the one still present in `local-path-provisioner/config.yml`.

    What actually converges the cluster is `retry: limit 10` with exponential backoff (10s to 3m) plus `selfHeal`. An Application whose dependency is missing fails, backs off, and succeeds on a later attempt.

The dependency graph the retry loop is resolving:

- **Bootstrap layer**: Vault, External Secrets, cert-manager, and the Gateway API CRDs. Almost everything else fails at least once until these exist.
- **Platform layer**: storage provisioners, Garage, legacy MinIO, Kyverno, metrics, and the GPU operator. These need CRDs and certificates from the layer above.
- **Service layer**: the monitoring stack, Velero, Authentik, and the GPU device plugin -- all of which consume storage, certificates, or load balancer IPs.
- **Consumers**: Alloy ships to Loki; Goldilocks needs the VPA CRDs. These settle last.

This converges reliably but not deterministically. A cold bootstrap shows a period of failed Applications before everything goes green, which is expected rather than a fault.

The [trust-manager](trust-manager.md) distributes internal CA trust, and [Blackbox Exporter](blackbox-exporter.md) owns Git-managed endpoint probes. ArgoCD notification credentials are reconciled by the `argocd-notifications` Application after ESO is available, separate from initial bootstrap.
