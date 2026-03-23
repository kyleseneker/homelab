# Infrastructure Components

This section documents the infrastructure layer of the homelab Kubernetes cluster. These components provide the foundational services that all applications depend on: certificate management, ingress routing, storage, monitoring, backups, and more.

## Component Overview

| Component | Namespace | Sync Wave | Helm Chart | Version |
|-----------|-----------|-----------|------------|---------|
| Sealed Secrets | kube-system | -3 | sealed-secrets | 2.18.4 |
| cert-manager | cert-manager | -3 | cert-manager | v1.20.0 |
| MetalLB | metallb-system | -3 | metallb | 0.15.3 |
| MetalLB Config | metallb-system | -2 | (plain manifests) | - |
| Metrics Server | kube-system | -2 | metrics-server | 3.13.0 |
| NFS Provisioner | nfs-provisioner | -2 | nfs-subdir-external-provisioner | 4.0.18 |
| MinIO | backups | -2 | minio | 5.4.0 |
| Intel GPU Operator | intel-gpu-operator | -2 | intel-device-plugins-operator | 0.35.0 |
| ingress-nginx | ingress-nginx | -1 | ingress-nginx | 4.15.1 |
| kube-prometheus-stack | monitoring | -1 | kube-prometheus-stack | 82.13.6 |
| Loki | monitoring | -1 | loki | 6.55.0 |
| Velero | backups | -1 | velero | 12.0.0 |
| Intel GPU Plugin | intel-gpu-operator | -1 | intel-device-plugins-gpu | 0.35.0 |
| Reloader | kube-system | -1 | reloader | 2.2.9 |
| Descheduler | kube-system | -1 | descheduler | 0.35.1 |
| Alloy | monitoring | 0 | alloy | 1.6.2 |
| Authentik | auth | 0 | authentik | 2026.2.1 |
| Network Policies | (multiple) | -- | (plain manifests) | - |

## Sync Wave Ordering

ArgoCD sync waves control the order in which components are deployed. Components with lower (more negative) sync wave values are deployed first, ensuring that dependencies are fully available before the services that rely on them.

- **Wave -3**: Core primitives that almost everything else depends on -- secret management, certificate issuance, and bare-metal load balancing.
- **Wave -2**: Storage, metrics, GPU operators, and MetalLB configuration. These require the wave -3 foundations (e.g., MetalLB must be running before its address pool config is applied).
- **Wave -1**: Higher-level services that consume storage, certificates, and load balancers -- ingress routing, the full monitoring stack, backup infrastructure, and GPU device plugins.
- **Wave 0**: Components that depend on wave -1 services. For example, Alloy ships logs to Loki, so it must not start until Loki is ready.

This layered approach ensures a deterministic, repeatable bootstrap of the entire cluster from a single ArgoCD Application of Applications.
