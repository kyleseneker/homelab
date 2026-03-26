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
| `temp` | PVC (`nfs-client`) | 100Gi | `/temp` | Scratch space for active transcodes |
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

### 1. Verify the Internal Node

1. Open `https://tdarr.homelab.local`.
2. Go to the **Tdarr** tab (main dashboard). The internal node "InternalNode" should appear automatically.
3. Click the node name, then **Options**. Set workers:
    - **Transcode CPU workers:** 1 (remuxing is I/O-bound; more workers on NFS won't help)
    - **Transcode GPU workers:** 0 (not needed for remux/copy operations)
    - **Health check CPU workers:** 1
    - **Health check GPU workers:** 0

### 2. Create the Remux Flow

Go to the **Flows** tab and click **Flow+** to create a new flow. Build this pipeline using the visual node editor:

1. **Input** (auto-created)
2. **Check File Medium** (category: `file`) -- ensures it's a video file
3. **Begin Command** (category: `ffmpegCommand`) -- starts building the ffmpeg command
4. **Set Container** (category: `ffmpegCommand`) -- set to `mkv`, enable **Force Conform** = true
5. **Remove Stream By Property** (category: `ffmpegCommand`) -- keep only English audio:
    - Property To Check: `tags.language`
    - Values: `eng,und`
    - Condition: remove streams that do **NOT** match (keeps English + undefined)
    - Stream type: `audio`
6. **Remove Subtitles** (category: `ffmpegCommand`) -- removes all embedded subs (Bazarr provides external subs)
7. **Remove Data Streams** (category: `ffmpegCommand`) -- removes cover art, fonts, attachments
8. **Custom Arguments** (category: `ffmpegCommand`) -- Output Arguments: `-c copy` (copy all streams, no re-encode)
9. **Execute** (category: `ffmpegCommand`) -- runs the assembled ffmpeg command
10. **Replace Original File** (category: `file`) -- moves the processed file from cache back to the source location

Wire Check File Medium's **first output** (video) to Begin Command. This flow remuxes files without re-encoding video or audio. It only strips unwanted streams.

### 3. Add Libraries

Go to the **Libraries** tab and click **Library+** for each:

**Movies:**
- Source: `/data/media/movies`
- Transcode cache: `/temp`
- Containers: `mkv,mp4,avi`
- Transcode options: select the remux flow created above
- Source options: enable **Scan on start**, enable **Folder watch**, set **Process Library** to ON
- Schedule: 24/7 (or limit to off-peak hours)

**TV Shows:**
- Source: `/data/media/tv`
- Same settings as Movies

### 4. Start Processing

1. Click **Scan (Fresh)** from the Library Options button to do a full scan.
2. Monitor the dashboard -- files will move through the queue.
3. Target status for completed files: "Transcode: Not required".

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Shared media (`arr-data`) | Reads source files and writes transcoded output |
| Intel GPU node | Required for hardware-accelerated transcoding |

## Upstream

- [https://tdarr.io](https://tdarr.io)
