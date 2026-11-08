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

Loki ruler ──► Alertmanager
   ▲
   └── LogQL rules (ConfigMaps labelled loki_rule in monitoring)
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

The `Watchdog` alert is sent every minute to the heartbeat URL from Vault. The external heartbeat service must be configured to notify on missing pings and tested by interrupting delivery. `InfoInhibitor` goes to the null receiver.

## Custom Homelab Rules

Defined in `kube-prometheus-stack/homelab-rules.yml` as a standalone `PrometheusRule` resource. Prometheus discovers it because `ruleSelectorNilUsesHelmValues` is set to `false`.

### App Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `MediaAppDown` | critical | 5m | Any media deployment has 0 available replicas |
| `GluetunVPNDown` | warning | 10m | Gluetun VPN sidecar container not ready |

### Infrastructure Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `AuthentikDown` | critical | 5m | Authentik server deployment has 0 replicas |
| `LokiDown` | critical | 5m | Loki scrape target is unreachable |
| `NFSStorageLow` | warning | 15m | Any PVC usage above 85% |
| `CertificateExpiringSoon` | warning | 1h | cert-manager certificate expires within 14 days |
| `CertificateNotReady` | warning | 15m | Certificate Ready condition is false, including failed initial issuance |

### Backup Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `VeleroBackupFailed` | critical | -- | Backup failure in the last 24h |
| `VeleroBackupMissing` | warning | 1h | Daily schedule has no successful backup in 25h (weekly/offsite schedules use 8 days) |
| `VeleroBackupPartialFailure` | warning | -- | Partial failure in the last 24h |

Requires Velero metrics to be enabled (`metrics.serviceMonitor.enabled: true` in the Velero Helm values).

### Node Health

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `HighNodeCPU` | warning | 15m | Sustained CPU above 85% |
| `HighNodeMemory` | warning | 15m | Memory usage above 90% |
| `NodeRootDiskFillingUp` | warning | 30m | Root filesystem above 80% full |
| `NodeDiskPressure` | critical | 5m | Root filesystem above 90% full |

These supplement the default kube-prometheus-stack node alerts, which use predictive thresholds rather than static ones. They select no job, so they also cover the Proxmox host (`instance="homelabpve01"`); the default alerts cover only the Kubernetes nodes.

### Proxmox Host Health

Metrics come from node-exporter on the hypervisor ([Proxmox Host Metrics](proxmox-host-metrics.md)).

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `ProxmoxHostMetricsAbsent` | warning | 15m | The `proxmox-host` target is down or missing |
| `ProxmoxNVMeHealthStale` | warning | 15m | `nvme.prom` is over an hour old, or missing while the host is up |
| `ProxmoxNVMeCriticalWarning` | critical | 5m | The NVMe critical warning field is non-zero |
| `ProxmoxNVMeMediaErrors` | warning | 5m | The NVMe has logged any media and data integrity errors |
| `ProxmoxNVMeWearing` | warning | 1h | More than 80% of rated write endurance used |
| `ProxmoxCPUHot` | warning | 30m | CPU package at or above 95°C |

The root filesystem holds container images, the journal and `local-path` volumes. `make k8s-node-disk` caps the journal at 1G and sets the kubelet to remove images unused for 7 days, and any unused image once the disk passes 75%, so images alone do not reach the 80% alert. kubeadm's default starts that cleanup only at 85%. The kubelet settings are `k8s_kubelet_config` in `ansible/group_vars/all/vars.yml`, used by `kubeadm init` and merged into the cluster's `kubelet-config` ConfigMap, which joins and upgrades copy to each node.

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

## Log Alerts

The Loki ruler evaluates LogQL rules and sends their alerts to the same Alertmanager, so routing and silences apply unchanged. Add a ConfigMap in `monitoring` labelled `loki_rule: "true"` whose data keys are rule files in the Prometheus format with LogQL expressions. Set a `namespace` label on each rule, since log alerts carry only the labels the expression keeps.

| File | Alerts |
|------|--------|
| `infrastructure/loki/home-assistant-rules.yml` | `HomeAssistantLoginFailures`, `HomeAssistantIPBanned` ([Home Assistant](../apps/home-assistant.md#monitoring)) |

## Silencing Alerts

To temporarily silence an alert, use the Alertmanager UI at `alertmanager.home.seneker.io`:

1. Navigate to **Silences** > **New Silence**
2. Add a matcher (e.g., `alertname = HighNodeCPU`)
3. Set duration and comment

Silences are ephemeral and not stored in Git.
