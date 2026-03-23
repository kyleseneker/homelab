# Metrics Server

Metrics Server collects resource usage metrics (CPU and memory) from the kubelet on each node, making them available to the Kubernetes API for tools like `kubectl top` and the Horizontal Pod Autoscaler (HPA).

## Details

| Field | Value |
|-------|-------|
| Chart | `metrics-server` |
| Repository | <https://kubernetes-sigs.github.io/metrics-server> |
| Version | 3.13.0 |
| Namespace | `kube-system` |
| Sync Wave | -2 |

## Key Configuration

- **Extra args**: `--kubelet-insecure-tls`
- **Resources**:
    - Requests: 50m CPU, 64Mi memory
    - Limits: 128Mi memory

!!! note "Insecure TLS Flag"
    The `--kubelet-insecure-tls` flag is required because kubeadm-provisioned clusters use self-signed kubelet serving certificates that the Metrics Server cannot verify by default. This is standard practice for kubeadm-based homelab clusters.

## Cluster Integration

Metrics Server deploys at sync wave -2 as a foundational cluster service. Once running, it enables:

- **`kubectl top nodes`** -- view CPU and memory usage per node
- **`kubectl top pods`** -- view CPU and memory usage per pod
- **Horizontal Pod Autoscaler** -- scale workloads based on real-time CPU/memory utilization

Prometheus (via kube-prometheus-stack) provides long-term metrics storage and dashboarding, while Metrics Server handles the real-time metrics API that the Kubernetes control plane consumes directly.

## Upstream Documentation

<https://github.com/kubernetes-sigs/metrics-server>
