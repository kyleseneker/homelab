# Prowlarr

Prowlarr is a centralized indexer manager for the *arr stack. Add torrent trackers once in Prowlarr and they automatically sync to Sonarr, Radarr, and any other connected application.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/prowlarr` |
| Port | 9696 |
| HTTPRoute | `prowlarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-prowlarr` |
| Internal URL | `http://arr-prowlarr.arr.svc.cluster.local:9696` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`local-path`) | 1Gi | `/config` |

Prowlarr does not require the shared `arr-data` volume because it does not interact with media files directly.

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 128Mi |
| Limits | -- | 256Mi |

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- Liveness, readiness, and startup probes are enabled.
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.

## Post-Deploy Verification

`ProwlarrConfig` owns indexers, Sonarr/Radarr app sync, and the FlareSolverr proxy. Initialize authentication as needed, run `make arr-keys-adopt`, then verify indexer tests and application sync. Make persistent setting changes in the CR. See [Media Operator](media-operator.md) for configuration ownership and cold-start prerequisites.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Receives synced indexers for TV searches |
| Radarr | Receives synced indexers for movie searches |
| FlareSolverr | Solves Cloudflare captchas for protected indexers |

## Upstream

- [https://prowlarr.com](https://prowlarr.com)
