# Exportarr

Exportarr is a Prometheus exporter for *arr applications. It exposes metrics such as queue depth, library size, missing episodes, and download history, making them available for Grafana dashboards and alerting.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/onedr0p/exportarr:v2.3.0` |
| Namespace | `arr` |
| ArgoCD app | `arr-exportarr` |
| Sync wave | 1 |

### Exporters

| Controller | Target App | Port | Internal URL |
|------------|-----------|------|--------------|
| sonarr | Sonarr | 9707 | `http://arr-exportarr-sonarr.arr.svc.cluster.local:9707` |
| radarr | Radarr | 9708 | `http://arr-exportarr-radarr.arr.svc.cluster.local:9708` |
| prowlarr | Prowlarr | 9709 | `http://arr-exportarr-prowlarr.arr.svc.cluster.local:9709` |
| bazarr | Bazarr | 9710 | `http://arr-exportarr-bazarr.arr.svc.cluster.local:9710` |

Each exporter runs as a separate Deployment (one app-template controller per target app) with its own Service and ServiceMonitor.

### Resources (per exporter)

| | CPU | Memory |
|---|-----|--------|
| Requests | 10m | 32Mi |
| Limits | -- | 64Mi |

## Key Configuration

- Each exporter receives its target app's API key from the `exportarr-secrets` Secret.
- Health probes use the `/healthz` endpoint on each exporter's port.
- ServiceMonitors scrape the `/metrics` endpoint every 60 seconds.
- Prometheus discovers the ServiceMonitors across namespaces via `serviceMonitorSelectorNilUsesHelmValues: false` in kube-prometheus-stack.

## Post-Deploy Setup

1. Obtain API keys from each target app (Settings > General in each *arr app UI).
2. Write the API keys to Vault:

    ```bash
    vault kv put homelab/apps/exportarr \
      sonarr-api-key=your_key \
      radarr-api-key=your_key \
      prowlarr-api-key=your_key \
      bazarr-api-key=your_key
    ```

3. Verify targets appear in Prometheus: `https://prometheus.homelab.local/targets`

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr, Radarr, Prowlarr, Bazarr | Target apps whose APIs are scraped |
| `exportarr-secrets` | API keys for authenticated API access |
| kube-prometheus-stack | ServiceMonitor discovery and metrics storage |

## Upstream

- [https://github.com/onedr0p/exportarr](https://github.com/onedr0p/exportarr)
