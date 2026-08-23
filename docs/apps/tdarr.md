# Tdarr

Tdarr scans the media libraries, verifies files are playable, and normalises their streams. It
does not re-encode video -- see [ADR-019](../decisions/019-transcode-policy.md).

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/haveagitgat/tdarr` |
| Ports | 8265 (web UI), 8266 (server) |
| HTTPRoute | `tdarr.homelab.local`, proxied through the Authentik outpost |
| Namespace | `arr` |
| ArgoCD app | `arr-tdarr` |
| Internal URL | `http://arr-tdarr.arr.svc.cluster.local:8265` |
| Configuration | `TdarrConfig` CR, reconciled by the media-operator |

### Storage

| Volume | Type | Size | Mount Path | Notes |
|--------|------|------|------------|-------|
| `config` | PVC (`nfs-client`) | 1Gi | `/app/server` | Server database and configuration |
| `data` | PVC (existing `arr-data`) | -- | `/data` | Shared media library and transcode cache, mounted whole so the two share a filesystem |
| `dri` | hostPath | -- | `/dev/dri` | Intel GPU device |

### Resources

| | CPU | Memory | Ephemeral storage |
|---|-----|--------|-------------------|
| Requests | 500m | 1Gi | 1Gi |
| Limits | 3000m | 4Gi | 4Gi |

The ephemeral-storage limit bounds what Tdarr can write to the node's root disk. Without it an
oversized cache write takes the whole node into `DiskPressure`, which evicts every pod on it.

GPU limit: `gpu.intel.com/i915: 1`. `nodeSelector`: `gpu: intel`.

## Key Configuration

Environment from ConfigMap `arr-env` (TZ, PUID, PGID) plus:

| Variable | Value | Notes |
|----------|-------|-------|
| `serverIP` | `0.0.0.0` | |
| `serverPort` | `8266` | |
| `webUIPort` | `8265` | |
| `internalNode` | `true` | No separate node deployment is needed |
| `inContainer` | `true` | |
| `ffmpegVersion` | `7` | |
| `NODE_OPTIONS` | `--max-old-space-size=3072` | Node caps its own heap near 2 GB and exits below the container limit without this |

## Configuration as Code

Libraries, flows and worker counts come from the `TdarrConfig` CR in
`apps/arr/media-config/tdarr.yml`. Nothing here is set through the web UI.

The libraries run the community One Flow set with `disable_video: true`, so the flow performs
audio and container work and leaves the video stream untouched.

Settings that are load-bearing and easy to get wrong:

| Setting | Value | Why |
|---------|-------|-----|
| `folderWatching` | `false` | inotify does not work over NFS; the watcher leaks roughly 1.4 GiB/min until the pod is OOM-killed |
| `scheduledScanFindNew` | `true` | Replaces folder watching -- new files are found on an hourly scan |
| `containerFilter` | extension list | The scanner matches file extensions against this; an empty filter indexes nothing |
| `cache` | `/data/tdarr/cache` | The cache cleaner throws on every pass when this is unset. It must be on the NFS share: cache holds a full copy of the file being processed, and a UHD remux is larger than a node's root disk |
| `decisionMode` | `flows` | Without it Tdarr builds classic plugin-stack jobs, which produce an empty ffmpeg command |
| `healthCheckMode` | `thorough` | Quick health checks call HandBrake, which this image does not ship |

Health checks run on CPU workers. The GPU health-check worker assumes NVIDIA decode and fails
on this Intel GPU.

## Operating Notes

- The job queue is built at startup. A configuration change that affects queueing needs a pod
  restart before it takes effect.
- Job reports under `/app/server/Tdarr/DB2/JobReports/<footprintId>/` record the actual ffmpeg
  arguments and exit code, and are the fastest way to diagnose a failing job.
- `JobsJSONDB` records `workerGenus` per job, which distinguishes a flow job from a classic one.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Shared media (`arr-data`) | Reads and writes the library |
| Intel GPU node | Hardware decode for health checks and any future encode work |
| media-operator | Reconciles libraries, flows and worker counts |

## Upstream

- [https://tdarr.io](https://tdarr.io)
