# Bazarr

Bazarr automates subtitle downloading for media managed by Sonarr and Radarr. It monitors your libraries and fetches matching subtitles from configured providers.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/bazarr` |
| Port | 6767 |
| HTTPRoute | `bazarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-bazarr` |
| Internal URL | `http://arr-bazarr.arr.svc.cluster.local:6767` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`local-path`) | 1Gi | `/config` |
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

## Post-Deploy Verification

`BazarrConfig` declares Sonarr/Radarr connections, English subtitles, and providers. Populate `opensubtitles-credentials` and the API-key Secret, then verify the CR is ready and download a representative subtitle. See [Media Operator](media-operator.md) for configuration ownership and cold-start prerequisites.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Provides TV episode metadata and file paths |
| Radarr | Provides movie metadata and file paths |

## Upstream

- [https://www.bazarr.media](https://www.bazarr.media)
