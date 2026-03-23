# Loki

Loki is a log aggregation system designed for efficiency, storing log streams with minimal indexing overhead. It runs in single-binary mode for simplicity in this homelab deployment.

## Details

| Field | Value |
|-------|-------|
| Chart | `loki` |
| Repository | <https://grafana.github.io/helm-charts> |
| Version | 6.55.0 |
| Namespace | `monitoring` (CreateNamespace=true) |
| Sync Wave | -1 |

## Key Configuration

- **Deployment mode**: `SingleBinary` with 1 replica
- **Authentication**: Disabled (`auth_enabled: false`)
- **Replication factor**: 1
- **Schema**: v13 with TSDB store, filesystem-based `object_store`, and a 24-hour index period
- **Retention**: 168 hours (7 days)
- **Storage**: 10Gi PVC using the `nfs-client` StorageClass
- **Caches**: Both `chunksCache` and `resultsCache` are disabled (not needed at homelab scale)
- **Gateway**: Disabled
- **Backend/read/write replicas**: 0 (all handled by the single binary)
- **Resources**:
    - Requests: 100m CPU, 256Mi memory
    - Limits: 512Mi memory

## Cluster Integration

Loki receives log streams from Alloy (deployed at sync wave 0), which runs as a DaemonSet and ships pod logs from every node.

Grafana (part of kube-prometheus-stack) has Loki pre-configured as a data source at:

```
http://loki.monitoring.svc.cluster.local:3100
```

Users query logs through Grafana Explore using LogQL.

Loki deploys at sync wave -1 alongside the rest of the monitoring stack. Alloy, which depends on Loki being available, deploys at wave 0.

## Upstream Documentation

<https://grafana.com/oss/loki>
