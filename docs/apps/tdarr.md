# Tdarr

Tdarr is an automated media transcoding application. It scans media libraries and converts files to a target codec (H.265/HEVC), reducing storage usage while maintaining quality. It uses Intel QuickSync for hardware-accelerated transcoding.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/haveagitgat/tdarr:2.65.01` |
| Ports | 8265 (web UI), 8266 (server) |
| HTTPRoute | `tdarr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-tdarr` |
| Sync wave | 1 |
| Internal URL | `http://arr-tdarr.arr.svc.cluster.local:8265` |

### Storage

| Volume | Type | Size | Mount Path | Notes |
|--------|------|------|------------|-------|
| `config` | PVC (`nfs-client`) | 1Gi | `/app/server` | Tdarr server database and configuration |
| `temp` | emptyDir | 20Gi | `/temp` | Scratch space for active transcodes |
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

- Environment variables from ConfigMap `arr-env` (TZ, PUID, PGID) plus application-specific variables:

    | Variable | Value |
    |----------|-------|
    | `serverIP` | `0.0.0.0` |
    | `serverPort` | `8266` |
    | `webUIPort` | `8265` |
    | `internalNode` | `true` |
    | `inContainer` | `true` |
    | `ffmpegVersion` | `6` |

- Runs with an internal processing node (`internalNode=true`), so no external Tdarr node deployment is required.
- Ingress annotations set `proxy-read-timeout` and `proxy-send-timeout` to 3600 seconds to prevent nginx from timing out during long transcode operations.
- Liveness, readiness, and startup probes check the web UI on port 8265. The startup probe allows up to 30 failures at 10-second intervals (5 minutes).

## Post-Deploy Setup

1. Open `https://tdarr.homelab.local`.
2. Add media libraries (Libraries > Add Library):
    - **Movies** -- source: `/data/media/movies`
    - **TV Shows** -- source: `/data/media/tv`
3. Configure transcode settings:
    - Target codec: **H.265 (HEVC)** is recommended for storage savings.
    - The Intel GPU is already available at `/dev/dri` for hardware-accelerated encoding.
4. The internal node should appear automatically on the Nodes tab. Verify it shows as connected and assign libraries to it.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Shared media (`arr-data`) | Reads source files and writes transcoded output |
| Intel GPU node | Required for hardware-accelerated transcoding |

## Upstream

- [https://tdarr.io](https://tdarr.io)
