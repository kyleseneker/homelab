# Uptime Kuma

Uptime Kuma is a self-hosted monitoring tool that provides synthetic HTTP/TCP/DNS checks against services and a status page. It monitors services from inside the cluster, complementing Prometheus-based metrics with "can I reach this endpoint?" checks.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `louislam/uptime-kuma` |
| Port | 3001 |
| HTTPRoute | `status.homelab.local` |
| Namespace | `monitoring` |
| ArgoCD app | `uptime-kuma` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `data` | PVC (`local-path`) | 1Gi | `/app/data` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 25m | 128Mi |
| Limits | -- | 256Mi |

## Key Configuration

- **Database**: SQLite (`UPTIME_KUMA_DB_TYPE: sqlite`), stored on the local-path PVC; the SQLite backup job stages a consistent dump onto NFS.
- The HTTPRoute goes directly to Uptime Kuma; protect its administration with native authentication.
- Startup probe allows up to 30 failures at 5-second intervals to account for initial database setup.

## Post-Deploy Setup

1. Add `status.homelab.local` to DNS (if not using a wildcard record).
2. Confirm the direct route and intended visibility of the public status page.
3. Open `https://status.homelab.local` and create an admin account.
4. Add HTTP monitors for each service:

    | Monitor | URL |
    |---------|-----|
    | Jellyfin | `https://jellyfin.homelab.local` |
    | Sonarr | `https://sonarr.homelab.local` |
    | Radarr | `https://radarr.homelab.local` |
    | Prowlarr | `https://prowlarr.homelab.local` |
    | Bazarr | `https://bazarr.homelab.local` |
    | Seerr | `https://seerr.homelab.local` |
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
    | Homepage | `https://home.homelab.local` |

!!! note
    Uptime Kuma monitors from within the cluster. Install the homelab CA before relying on HTTPS validation; do not treat checks that ignore certificate errors as TLS coverage. The CA-backed Blackbox probes provide separate route/TLS checks. Internal HTTP checks can diagnose service reachability but do not test the gateway.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Cilium Gateway | HTTPRoute routing |
| cert-manager | TLS certificate |
| Authentik | Forward-auth SSO |

## Upstream

- [https://github.com/louislam/uptime-kuma](https://github.com/louislam/uptime-kuma)
