# Alerting

Alertmanager routes alerts from Prometheus to a Slack `#alerts` channel. The kube-prometheus-stack ships ~100 default Kubernetes alerting rules, and custom homelab-specific rules supplement them for app health, backup health, and node-level monitoring.

## Architecture

```
Prometheus ──► Alertmanager ──► Slack #alerts
   ▲
   │
   ├── Default kube-prometheus rules (~100)
   ├── Custom homelab rules (homelab-rules.yml)
   └── Velero metrics (ServiceMonitor)
```

## Slack Integration

Alertmanager sends notifications to a single `#alerts` channel via an Incoming Webhook.

### Setup

1. Create a Slack App at <https://api.slack.com/apps>
2. Enable **Incoming Webhooks** and add one to your `#alerts` channel
3. Write the webhook URL to Vault:

```bash
vault kv put homelab/infrastructure/alertmanager-slack \
  url=https://hooks.slack.com/services/T.../B.../xxx
```

The ExternalSecret syncs `alertmanager-slack-webhook` from Vault into the `monitoring` namespace. Alertmanager mounts it via `alertmanagerSpec.secrets` and reads the URL from `/etc/alertmanager/secrets/alertmanager-slack-webhook/url`.

### Routing

| Behavior | Value |
|----------|-------|
| Group by | `alertname`, `namespace` |
| Group wait | 30s |
| Group interval | 5m |
| Repeat interval | 4h |
| Inhibition | Critical suppresses warning for same alert+namespace |

The `Watchdog` alert (a dead-man's-switch from the default rules) is routed to a null receiver to avoid noise.

## Custom Homelab Rules

Defined in `kube-prometheus-stack/homelab-rules.yml` as a standalone `PrometheusRule` resource. Prometheus discovers it because `ruleSelectorNilUsesHelmValues` is set to `false`.

### App Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `ArrAppDown` | critical | 5m | Any arr deployment has 0 available replicas |
| `GluetunVPNDown` | warning | 10m | Gluetun VPN sidecar container not ready |

### Infrastructure Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `AuthentikDown` | critical | 5m | Authentik server deployment has 0 replicas |
| `IngressNginxDown` | critical | 5m | No ingress-nginx DaemonSet pods available |
| `NFSStorageLow` | warning | 15m | Any PVC usage above 85% |
| `CertificateExpiringSoon` | warning | 1h | cert-manager certificate expires within 14 days |

### Backup Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `VeleroBackupFailed` | critical | -- | Backup failure in the last 24h |
| `VeleroBackupMissing` | warning | 1h | No successful backup for a schedule in 25h |
| `VeleroBackupPartialFailure` | warning | -- | Partial failure in the last 24h |

Requires Velero metrics to be enabled (`metrics.serviceMonitor.enabled: true` in the Velero Helm values).

### Node Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `HighNodeCPU` | warning | 15m | Sustained CPU above 85% |
| `HighNodeMemory` | warning | 15m | Memory usage above 90% |
| `NodeDiskPressure` | critical | 5m | Root filesystem above 90% full |

These supplement the default kube-prometheus-stack node alerts, which use predictive thresholds rather than static ones.

## Adding New Rules

Add new `PrometheusRule` resources in the `monitoring` namespace. With `ruleSelectorNilUsesHelmValues: false`, Prometheus picks up all rules regardless of labels.

Example rule:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: my-custom-rules
  namespace: monitoring
spec:
  groups:
    - name: my-group
      rules:
        - alert: MyAlert
          expr: some_metric > threshold
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Short description"
            description: "Detailed description with {{ $labels.instance }}."
```

## Silencing Alerts

To temporarily silence an alert, use the Alertmanager UI at `alertmanager.homelab.local`:

1. Navigate to **Silences** > **New Silence**
2. Add a matcher (e.g., `alertname = HighNodeCPU`)
3. Set duration and comment

Silences are ephemeral and not stored in Git.
