# Prowlarr

Prowlarr is a centralized indexer manager for the *arr stack. Add torrent trackers and Usenet indexers once in Prowlarr and they automatically sync to Sonarr, Radarr, and any other connected application.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/prowlarr:2.3.0` |
| Port | 9696 |
| Ingress | `prowlarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-prowlarr` |
| Sync wave | 1 |
| Internal URL | `http://arr-prowlarr.arr.svc.cluster.local:9696` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`nfs-client`) | 1Gi | `/config` |

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

## Post-Deploy Setup

1. Open `https://prowlarr.homelab.local` and set authentication (Settings > General).
2. Add indexers (Indexers > Add Indexer):
    - Add torrent trackers (public or private).
    - Add Usenet indexers (NZBgeek, etc.).
3. Connect to Sonarr and Radarr (Settings > Apps > Add Application):
    - **Prowlarr Server**: `http://arr-prowlarr.arr.svc.cluster.local:9696`
    - **Sonarr**: `http://arr-sonarr.arr.svc.cluster.local:8989` + Sonarr API key
    - **Radarr**: `http://arr-radarr.arr.svc.cluster.local:7878` + Radarr API key
4. Enable **Sync App Indexers** so that indexers added to Prowlarr are automatically pushed to connected apps.
5. Add FlareSolverr as an indexer proxy (Settings > Indexers > + > FlareSolverr):
    - **Host**: `http://arr-flaresolverr.arr.svc.cluster.local:8191`
    - **Tag**: `flaresolverr`
    - Assign the `flaresolverr` tag to any indexer that requires Cloudflare solving.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Receives synced indexers for TV searches |
| Radarr | Receives synced indexers for movie searches |
| FlareSolverr | Solves Cloudflare captchas for protected indexers |

## Upstream

- [https://prowlarr.com](https://prowlarr.com)
