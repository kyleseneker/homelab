# Bazarr

Bazarr automates subtitle downloading for media managed by Sonarr and Radarr. It monitors your libraries and fetches matching subtitles from configured providers.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/bazarr:1.5.6` |
| Port | 6767 |
| Ingress | `bazarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-bazarr` |
| Sync wave | 1 |
| Internal URL | `http://arr-bazarr.arr.svc.cluster.local:6767` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`nfs-client`) | 1Gi | `/config` |
| `data` | PVC (existing `arr-data`) | -- | `/data` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 128Mi |
| Limits | -- | 256Mi |

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- Liveness, readiness, and startup probes are enabled.
- The shared `arr-data` volume is mounted at `/data` so Bazarr can read media files and write subtitle files alongside them.

## Post-Deploy Setup

1. Open `https://bazarr.homelab.local`.
2. Connect to Sonarr (Settings > Sonarr):
    - Host: `arr-sonarr.arr.svc.cluster.local`
    - Port: `8989`
    - API Key: *(from Sonarr > Settings > General)*
3. Connect to Radarr (Settings > Radarr):
    - Host: `arr-radarr.arr.svc.cluster.local`
    - Port: `7878`
    - API Key: *(from Radarr > Settings > General)*
4. Add subtitle providers (Settings > Providers):
    - OpenSubtitles.com (account required)
    - Additional providers as desired

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Provides TV episode metadata and file paths |
| Radarr | Provides movie metadata and file paths |

## Upstream

- [https://www.bazarr.media](https://www.bazarr.media)
