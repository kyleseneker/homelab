# Radarr

Radarr automates movie management -- it monitors for releases, searches indexers, and sends downloads to a configured download client. Completed files are organized into the media library.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/radarr:6.0.4` |
| Port | 7878 |
| HTTPRoute | `radarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-radarr` |
| Sync wave | 1 |
| Internal URL | `http://arr-radarr.arr.svc.cluster.local:7878` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`nfs-client`) | 1Gi | `/config` |
| `data` | PVC (existing `arr-data`) | -- | `/data` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 250m | 512Mi |
| Limits | -- | 1Gi |

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- Liveness, readiness, and startup probes are enabled.
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.

## Post-Deploy Setup

1. Open `https://radarr.homelab.local` and set authentication to **Forms** (Settings > General > Authentication).
2. Add root folder: `/data/media/movies` (Settings > Media Management > Root Folders).
3. Add download clients (Settings > Download Clients):
    - **qBittorrent** -- host: `arr-vpn-downloads.arr.svc.cluster.local`, port: `8080`, category: `movies`
4. Note the API key from Settings > General -- it is required by Prowlarr, Recyclarr, Bazarr, Seerr, and Homepage.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Prowlarr | Syncs indexers to Radarr automatically |
| qBittorrent | Torrent download client |
| Recyclarr | Pushes quality profiles and custom formats |
| Bazarr | Fetches subtitles for downloaded movies |
| Seerr | Sends movie requests to Radarr |

## Upstream

- [https://radarr.video](https://radarr.video)
