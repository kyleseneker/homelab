# Radarr

Radarr automates movie management -- it monitors for releases, searches indexers, and sends downloads to a configured download client. Completed files are organized into the media library.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/radarr` |
| Port | 7878 |
| HTTPRoute | `radarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-radarr` |
| Internal URL | `http://arr-radarr.arr.svc.cluster.local:7878` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`local-path`) | 5Gi | `/config` |
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

## Post-Deploy Verification

`RadarrConfig` owns `/data/media/movies`, qBittorrent, and Jellyfin notifications. Recyclarr owns quality profiles. Initialize application authentication as needed, run `make arr-keys-adopt`, and verify the CR and a test import. See [Media Operator](media-operator.md) for configuration ownership and cold-start prerequisites.

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
