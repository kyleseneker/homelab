# Uptime Kuma

Uptime Kuma is a self-hosted monitoring tool that provides synthetic HTTP/TCP/DNS checks against services and a status page. It monitors services from inside the cluster, complementing Prometheus-based metrics with "can I reach this endpoint?" checks.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `louislam/uptime-kuma:2.2.1` |
| Port | 3001 |
| HTTPRoute | `status.homelab.local` |
| Namespace | `monitoring` |
| ArgoCD app | `uptime-kuma` |
| Sync wave | 2 |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `data` | PVC (`nfs-client`) | 1Gi | `/app/data` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 25m | 128Mi |
| Limits | -- | 256Mi |

## Key Configuration

- **Database**: SQLite (`UPTIME_KUMA_DB_TYPE: sqlite`), stored on the NFS-backed PVC.
- Authentik forward-auth protects the web UI (same pattern as other arr apps).
- Startup probe allows up to 30 failures at 5-second intervals to account for initial database setup.

## Post-Deploy Setup

1. Add `status.homelab.local` to DNS (if not using a wildcard record).
2. Create an Authentik application and proxy provider for `status.homelab.local`.
3. Open `https://status.homelab.local` and create an admin account.
4. Add HTTP monitors for each service:

    | Monitor | URL |
    |---------|-----|
    | Jellyfin | `https://jellyfin.homelab.local` |
    | Sonarr | `https://sonarr.homelab.local` |
    | Radarr | `https://radarr.homelab.local` |
    | Prowlarr | `https://prowlarr.homelab.local` |
    | Bazarr | `https://bazarr.homelab.local` |
    | Jellyseerr | `https://jellyseerr.homelab.local` |
    | qBittorrent | `https://qbit.homelab.local` |
    | Tdarr | `http://tdarr.homelab.local` |
    | OpenClaw | `https://openclaw.homelab.local` |
    | Grafana | `https://grafana.homelab.local` |
    | Prometheus | `https://prometheus.homelab.local` |
    | Alertmanager | `https://alertmanager.homelab.local` |
    | Uptime Kuma | `https://status.homelab.local` |
    | Goldilocks | `https://goldilocks.homelab.local` |
    | ArgoCD | `https://argocd.homelab.local` |
    | Vault | `https://vault.homelab.local` |
    | Authentik | `https://auth.homelab.local` |
    | Proxmox | `https://proxmox.homelab.local:8006` |
    | Homepage | `https://home.homelab.local` |

!!! note
    Uptime Kuma monitors from within the cluster. For TLS checks to work against `*.homelab.local` endpoints using the internal CA, the monitors should be configured to accept self-signed certificates (or use HTTP checks against the internal service URLs instead).

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Cilium Gateway | HTTPRoute routing |
| cert-manager | TLS certificate |
| Authentik | Forward-auth SSO |

## Upstream

- [https://github.com/louislam/uptime-kuma](https://github.com/louislam/uptime-kuma)
