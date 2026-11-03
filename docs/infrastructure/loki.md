# Loki

Loki is a log aggregation system designed for efficiency, storing log streams with minimal indexing overhead. It runs in single-binary mode for simplicity in this homelab deployment.

## Details

| Field | Value |
|-------|-------|
| Chart | `loki` |
| Repository | <https://grafana-community.github.io/helm-charts> |
| Version | 20.2.1 |
| Namespace | `monitoring` (CreateNamespace=true) |

## Key Configuration

- **Deployment mode**: `Monolithic` (the single binary; formerly `SingleBinary`) with 1 replica
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
    - Limits: 500m CPU, 512Mi memory (the chart derives `GOMEMLIMIT` from the memory limit)
- **Ruler**: Evaluates LogQL alerting rules every minute and sends to Alertmanager at `kube-prometheus-stack-alertmanager.monitoring.svc:9093`. The rules sidecar copies ConfigMaps labelled `loki_rule` in `monitoring` into `/rules/fake`, the directory of the single tenant Loki uses without `auth_enabled`. Its Role covers this namespace only, and it reads ConfigMaps, never Secrets.
- **Memberlist**: The memberlist Service publishes not-ready addresses. The single replica is its own only peer, and Loki exits if its startup join fails 10 times; without this, the join waits until the Pod is ready.

## Cluster Integration

Loki receives log streams from Alloy, which runs as a DaemonSet and ships pod logs from every node.

Grafana (part of kube-prometheus-stack) has Loki pre-configured as a data source at:

```
http://loki.monitoring.svc.cluster.local:3100
```

Users query logs through Grafana Explore using LogQL.

Alloy depends on Loki being available to accept writes. Nothing sequences the two -- Alloy buffers and retries until Loki is ready.

Loki's metrics carry `app_instance="loki"` from the ServiceMonitor; chart 18 replaced the earlier `cluster` label.

## Upgrades

The chart moved from the Loki repository to the grafana-community repository after 6.55.0; the 7.x and later charts left at `grafana.github.io` serve Grafana Enterprise Logs only ([ADR-027](../decisions/027-loki-community-chart.md)). Take chart majors one at a time and read each section of the chart README's [Upgrading](https://github.com/grafana-community/helm-charts/blob/main/charts/loki/README.md#upgrading) notes.

- The values schema rejects unknown top-level keys from chart 20, so a leftover or misspelled key fails rendering.
- StatefulSet volume claim fields (storage class, size, access modes) and the selector are immutable. A change to them fails the Argo CD sync instead of applying.
- From chart 19.3 the Pod template no longer carries the chart label, so a chart bump restarts Loki only when the Pod spec changes.
- Chart 18 changed the claim retention policy to `Retain`: deleting or scaling down the StatefulSet keeps `storage-loki-0`.

## Upstream Documentation

<https://grafana.com/oss/loki>
