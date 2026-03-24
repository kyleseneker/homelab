# Sonarr

Sonarr automates TV series management -- it monitors for new episodes, searches indexers, and sends downloads to a configured download client. Completed files are organized into the media library.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/sonarr:4.0.17` |
| Port | 8989 |
| Ingress | `sonarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-sonarr` |
| Sync wave | 1 |
| Internal URL | `http://arr-sonarr.arr.svc.cluster.local:8989` |

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

1. Open `https://sonarr.homelab.local` and set authentication to **Forms** (Settings > General > Authentication).
2. Add root folder: `/data/media/tv` (Settings > Media Management > Root Folders).
3. Add download clients (Settings > Download Clients):
    - **qBittorrent** -- host: `arr-vpn-downloads.arr.svc.cluster.local`, port: `8080`, category: `tv`
4. Note the API key from Settings > General -- it is required by Prowlarr, Recyclarr, Bazarr, Jellyseerr, and Homepage.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Prowlarr | Syncs indexers to Sonarr automatically |
| qBittorrent | Torrent download client |
| Recyclarr | Pushes quality profiles and custom formats |
| Bazarr | Fetches subtitles for downloaded episodes |
| Jellyseerr | Sends TV show requests to Sonarr |

## Upstream

- [https://sonarr.tv](https://sonarr.tv)
