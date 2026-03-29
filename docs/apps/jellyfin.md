# Jellyfin

Jellyfin is a self-hosted media server for streaming movies, TV shows, and music. It provides client apps and a web UI for playback, with support for hardware-accelerated transcoding via Intel QuickSync.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/jellyfin:10.11.6` |
| Port | 8096 |
| Service type | LoadBalancer |
| HTTPRoute | `jellyfin.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-jellyfin` |
| Sync wave | 1 |

### Storage

| Volume | Type | Size | Mount Path | Notes |
|--------|------|------|------------|-------|
| `config` | PVC (`nfs-client`) | 5Gi | `/config` | Jellyfin configuration and metadata |
| `media` | PVC (existing `arr-data`) | -- | `/data/media` | Shared media library (`subPath: media`) |
| `dri` | hostPath | -- | `/dev/dri` | Intel GPU device for hardware transcoding |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 200m | 512Mi |
| Limits | -- | 4Gi |

GPU limit: `gpu.intel.com/i915: 1`

### Scheduling

- `nodeSelector`: `gpu: intel`

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- The service is type `LoadBalancer`, giving Jellyfin a dedicated IP via Cilium L2 in addition to the Gateway API HTTPRoute.
- Startup probe allows up to 30 failures at 10-second intervals (5 minutes) to account for library scanning on first boot.

## Post-Deploy Setup

1. Open `https://jellyfin.homelab.local` and complete the setup wizard.
2. Create an admin user account.
3. Add media libraries:
    - **Movies** -- folder path `/data/media/movies`
    - **TV Shows** -- folder path `/data/media/tv`
    - **Music** -- folder path `/data/media/music`
4. Enable hardware transcoding:
    - Go to **Dashboard > Playback > Transcoding**.
    - Set hardware acceleration to **Intel QuickSync (QSV)**.
    - The `/dev/dri` device is already mounted and the GPU resource is allocated.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr / Radarr / Downloads | Provide media files to `/data/media` |
| Seerr | Connects to Jellyfin for user authentication and library status |
| Tdarr | Reads and transcodes files in `/data/media` |

## Upstream

- [https://jellyfin.org](https://jellyfin.org)
