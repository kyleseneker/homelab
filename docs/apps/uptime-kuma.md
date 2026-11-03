# Uptime Kuma

Uptime Kuma is a self-hosted monitoring tool that provides synthetic HTTP/TCP/DNS checks against services and a status page. It monitors services from inside the cluster, complementing Prometheus-based metrics with "can I reach this endpoint?" checks.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v5.3.0 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `louislam/uptime-kuma` |
| Port | 3001 |
| HTTPRoute | `status.home.seneker.io` |
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

1. Add a UniFi DNS record for `status.home.seneker.io`.
2. Confirm the direct route and intended visibility of the public status page.
3. Open `https://status.home.seneker.io` and create an admin account.
4. Add HTTP monitors for each service:

    | Monitor | URL |
    |---------|-----|
    | Jellyfin | `https://jellyfin.home.seneker.io` |
    | Sonarr | `https://sonarr.home.seneker.io` |
    | Radarr | `https://radarr.home.seneker.io` |
    | Prowlarr | `https://prowlarr.home.seneker.io` |
    | Bazarr | `https://bazarr.home.seneker.io` |
    | Seerr | `https://seerr.home.seneker.io` |
    | qBittorrent | `https://qbit.home.seneker.io` |
    | Tdarr | `https://tdarr.home.seneker.io` |
    | Grafana | `https://grafana.home.seneker.io` |
    | Prometheus | `https://prometheus.home.seneker.io` |
    | Alertmanager | `https://alertmanager.home.seneker.io` |
    | Uptime Kuma | `https://status.home.seneker.io` |
    | Goldilocks | `https://goldilocks.home.seneker.io` |
    | ArgoCD | `https://argocd.home.seneker.io` |
    | Vault | `https://vault.home.seneker.io` |
    | Authentik | `https://auth.home.seneker.io` |
    | Homepage | `https://home.seneker.io` |

!!! note
    Uptime Kuma monitors from within the cluster. The gateway's certificate is publicly trusted, so HTTPS checks can validate it; do not treat checks that ignore certificate errors as TLS coverage. The Blackbox probes provide separate route/TLS checks. Internal HTTP checks can diagnose service reachability but do not test the gateway.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Cilium Gateway | HTTPRoute routing |
| cert-manager | TLS certificate |
| Authentik | Forward-auth SSO |

## Upstream

- [https://github.com/louislam/uptime-kuma](https://github.com/louislam/uptime-kuma)
