# Homepage

Homepage is a dashboard that aggregates all homelab services into a single page with status widgets, quick links, and Kubernetes integration. It is deployed at sync wave 2 so that all other services are available before the dashboard starts querying them.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v3.6.0 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/gethomepage/homepage:v1.11.0` |
| Port | 3000 |
| Ingress | `home.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `homepage` |
| Sync wave | 2 |

### Storage

| Volume | Type | Mount Path | Notes |
|--------|------|------------|-------|
| `config` (ConfigMap `homepage-config`) | ConfigMap | `/app/config/` | Contains `services.yaml`, `settings.yaml`, `widgets.yaml`, `bookmarks.yaml` |

All configuration files are mounted read-only from the `homepage-config` ConfigMap.

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 25m | 64Mi |
| Limits | -- | 256Mi |

## Key Configuration

- `HOMEPAGE_ALLOWED_HOSTS`: `home.homelab.local` -- restricts which hostnames the server responds to.
- API keys for service widgets are injected as environment variables from the `homepage-secrets` Secret. These are referenced in the configuration files as `{{HOMEPAGE_VAR_*}}` placeholders.
- A `homepage` ServiceAccount is created for Kubernetes widget integration, allowing the dashboard to display cluster resource information.

### Dashboard Layout

| Group | Services |
|-------|----------|
| Media | Jellyfin, Jellyseerr |
| Downloads | qBittorrent, SABnzbd, Sonarr, Radarr |
| Management | Prowlarr, Bazarr, Tdarr, Recyclarr |
| Observability | Grafana, Prometheus, Alertmanager, Loki |
| Infrastructure | ArgoCD, Proxmox, Gluetun, Homepage |

### Configuration Files

| File | Purpose |
|------|---------|
| `services.yaml` | Defines service groups and widget configurations |
| `settings.yaml` | Global settings (title, theme, layout) |
| `widgets.yaml` | Top-level info widgets (Kubernetes, search, etc.) |
| `bookmarks.yaml` | External bookmark links |

## Post-Deploy Setup

1. Create the `homepage-secrets` Secret containing API keys for each service widget. The secret keys should be named with the `HOMEPAGE_VAR_` prefix:

    ```bash
    kubectl create secret generic homepage-secrets \
      --namespace arr \
      --from-literal=HOMEPAGE_VAR_JELLYFIN_KEY=<key> \
      --from-literal=HOMEPAGE_VAR_SONARR_KEY=<key> \
      --from-literal=HOMEPAGE_VAR_RADARR_KEY=<key> \
      --from-literal=HOMEPAGE_VAR_PROWLARR_KEY=<key> \
      --from-literal=HOMEPAGE_VAR_QBIT_PASSWORD=<password> \
      --from-literal=HOMEPAGE_VAR_SABNZBD_KEY=<key> \
      --dry-run=client -o yaml | kubeseal -o yaml > homepage-sealedsecret.yml
    ```

2. Open `https://home.homelab.local` and verify all service widgets display correctly.
3. If any widget shows an error, confirm the corresponding API key is correct and the target service is reachable from the `arr` namespace.

!!! note
    The `homepage-secrets` Secret is marked as `optional: true` in the deployment. Homepage will start without it, but service widgets that require API keys will not function until the secret is created.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| All *arr services | Widget status and statistics |
| Observability stack | Grafana, Prometheus, Alertmanager, Loki widgets |
| Infrastructure services | ArgoCD, Proxmox widgets |
| `homepage-secrets` | API keys for authenticated widget access |
| `homepage` ServiceAccount | Kubernetes cluster widget |

## Upstream

- [https://gethomepage.dev](https://gethomepage.dev)
