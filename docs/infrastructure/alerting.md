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

### Restore Tests

Rules in `backups/restore-test` read the [restore test](restore-test.md)'s results from the Pushgateway and kube-state-metrics.

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `RestoreTestFailed` | warning | 5m | A target's latest run did not pass |
| `RestoreTestStale` | warning | 10m | A target has not passed from the local backup in 54 hours, or from the AWS copy in 15 days |
| `RestoreTestMissing` | warning | 30h local, 8d offsite | No result exists for an expected target and source |
| `RestoreTestRowsDropped` | warning | 10m | A restored table has 20% fewer rows than its eight-day maximum |
| `RestoreSandboxLingering` | warning | -- | `restore-sandbox` has existed for six hours |
| `RestoreTestVolumesOrphaned` | warning | 1h | `nfs-restore-test` volumes exist without a sandbox |

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

### Patching

Thresholds follow [ADR-032](../decisions/032-os-patching.md). Host data comes from the `apt` and patch window textfiles on the hypervisor. Node data comes from the `apt.prom` textfile that `node_apt_metrics` writes on each node, read by the cluster's node-exporter, and from [kured](kured.md).

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `ProxmoxSecurityUpdatesPending` | warning | 3d | Debian security updates are pending on the host |
| `ProxmoxPackageListsStale` | warning | 1h | `apt-get update` has not succeeded for 2 days, or `apt.prom` is over an hour old or missing |
| `ProxmoxPatchWindowMissed` | warning | 1h | `pve-patch-window` has not succeeded for 35 days, or its timestamp is missing |
| `NodeRebootPending` | warning | 3d | A node has needed a reboot that kured has not done |
| `NodeSecurityUpdatesPending` | warning | 3d | Ubuntu security updates are pending on a node |
| `NodeUpdatesPending` | warning | 35d | Ubuntu updates are pending on a node; Kubernetes and Docker repository packages are excluded |
| `NodeUpdateDataStale` | warning | 1h | A node's package lists are 2 days old, or its `apt.prom` is over an hour old or missing |

### NAS Health

Defined in `snmp-exporter/prometheusrule.yml` from the UNAS Pro's SNMP agent ([SNMP Exporter](snmp-exporter.md)). The agent does not report drive or pool health.

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `NASMetricsAbsent` | warning | 15m | The `unas-snmp` target is down or missing |
| `NASFanStopped` | critical | 5m | `fan1` or `fan2` reports 0 RPM |
| `NASHot` | warning | 15m | Any NAS temperature sensor at or above 80°C |

The root filesystem holds container images, the journal and `local-path` volumes. `make k8s-node-disk` caps the journal at 1G and sets the kubelet to remove images unused for 7 days, and any unused image once the disk passes 75%, so images alone do not reach the 80% alert. kubeadm's default starts that cleanup only at 85%. The kubelet settings are `k8s_kubelet_config` in `ansible/group_vars/all/vars.yml`, used by `kubeadm init` and merged into the cluster's `kubelet-config` ConfigMap, which joins and upgrades copy to each node.

### UniFi

Defined in `unpoller/prometheusrule.yml` from the UniFi controller's metrics ([unpoller](unpoller.md)). The internet alerts use the gateway's own checks, so a gateway reboot of two or three minutes stays inside their windows.

| Alert | Severity | For | Condition |
|-------|----------|-----|-----------|
| `UnpollerAbsent` | warning | 10m | The `unpoller` target is down or missing: the pod, the API key or the pinned certificate |
| `InternetDown` | critical | 5m | No gateway internet check succeeds on any WAN; Slack delivers it once the link is back |
| `InternetDegraded` | warning | 10m | The gateway's best internet check target answers less than 90% of the time |
| `UniFiDeviceRestarted` | warning | -- | A UniFi device has been up for less than 15 minutes |
| `UniFiDevicesDisconnected` | warning | 5m | The controller reports a disconnected device in the LAN, WAN or WLAN subsystem |

`unpoller/loki-rules.yml` alerts on the controller's own events in Loki. Each fires within a few minutes of the event and resolves ten minutes later. Client roams and connections, admin activity, updates and firewall blocks stay in Loki without alerting.

| Alert | Severity | Condition |
|-------|----------|-----------|
| `UniFiSecurityDetection` | warning | Any security event other than a firewall block, such as an intrusion detection hit, labelled with the event and source client |
| `UniFiDeviceEvent` | warning | A UniFi device event of medium severity or higher, such as a lost mesh link, a rogue AP or a device going offline, labelled with the device. Re-mesh recoveries and channel changes are excluded. A controller update can log one rogue AP for the gateway's own BSSID |
| `UniFiUnclassifiedEvent` | warning | An event in a category the other rules do not cover yet, such as a new WAN or power event; classify it into an alert or an exclusion |

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
| `infrastructure/unpoller/loki-rules.yml` | `UniFiSecurityDetection`, `UniFiDeviceEvent`, `UniFiUnclassifiedEvent` ([UniFi](#unifi)) |

## Silencing Alerts

To temporarily silence an alert, use the Alertmanager UI at `alertmanager.home.seneker.io`:

1. Navigate to **Silences** > **New Silence**
2. Add a matcher (e.g., `alertname = HighNodeCPU`)
3. Set duration and comment

Silences are ephemeral and not stored in Git.
