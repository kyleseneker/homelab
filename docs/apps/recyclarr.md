# Recyclarr

Recyclarr syncs quality profiles and custom formats from the TRaSH Guides to Sonarr and Radarr. It runs as a long-lived server that syncs on its own schedule every 6 hours, exposes an HTTP API for its CLI and publishes Prometheus metrics.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `recyclarr` 9.0.0 (official, `oci://ghcr.io/recyclarr/charts/recyclarr`) |
| Image | `ghcr.io/recyclarr/recyclarr` (follows the chart version) |
| Controller type | Deployment (1 replica, `Recreate`) |
| Schedule | `0 */6 * * *` in `server.schedule.cron` |
| Ports | `7982` HTTP API, `7983` probes and `/metrics` |
| HTTPRoute | -- (in-cluster API only, no web UI) |
| Namespace | `media` |
| ArgoCD app | `recyclarr` |

### Storage

| Volume | Type | Mount Path | Notes |
|--------|------|------------|-------|
| `state` | PVC `recyclarr-state` (`nfs-client`, 256Mi) | `/state` | Sync state and job history; backed up by Velero |
| `data` | emptyDir | `/data` | Downloaded guides and caches; refetched at startup and excluded from backups |
| `tmp` | emptyDir | `/tmp` | Required with read-only root filesystem; excluded from backups |
| `configs` | ConfigMap (`recyclarr-config`) | `/config/configs/` | Quality profile and custom format definitions |
| `settings` | ConfigMap (`recyclarr-settings`, from values) | `/config/settings.yml` | Server schedule and logging |
| `secrets` | Secret (`recyclarr-secrets`, `secrets.yml` entry) | `/config/secrets.yml` | Sonarr and Radarr API keys |
| `api-key` | Secret (`recyclarr-secrets`, `api-key` entry) | `/secrets/api-key` | Server API key |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 256Mi |
| Limits | 1 | 512Mi |

The CPU limit is set high because the first guide download runs under a 5-minute startup probe.

## Key Configuration

- Environment variables from ConfigMap `media-env` (TZ, PUID, PGID).
- The pod runs as UID 977/GID 988, the NAS media identity that owns NFS-provisioned directories.
- Configuration is split across files:
    - `recyclarr.yml` (shared ConfigMap from `k8s/components/recyclarr-config`) defines which quality profiles and custom formats to sync. `SONARR_URL` and `RADARR_URL` can override the production defaults for isolated recovery.
    - `secrets.yml` (Secret) holds the Sonarr and Radarr API keys referenced by the config.
    - `settings.yml` (chart values) sets the schedule and turns off log files, since console output already goes to Loki.
- The server reloads `recyclarr.yml` edits within a minute. Changes to `settings.yml`, `media-env` or the mounted secrets need a restart, which Reloader does through the Deployment's `reloader.stakater.com/auto` annotation.
- A configuration error stops the server at startup, and it stays in CrashLoopBackOff until the error is fixed. An invalid edit made while it runs is logged, and the last valid configuration stays in use.
- Sync is self-healing: a configured custom format or profile that already exists in Sonarr or Radarr by name is adopted automatically.

### Quality Profiles

| Target | Profile |
|--------|---------|
| Sonarr | WEB-1080p |
| Radarr | HD Bluray + WEB |

### Custom Formats

The following custom formats are synced to both Sonarr and Radarr:

- Bad Dual Groups
- No-RlsGroup
- Obfuscated
- Retags

Radarr also receives:

- EVO (penalized release group)

## Post-Deploy Setup

1. Run `make media-keys-adopt` after Sonarr/Radarr initialization or restore. ESO reads `sonarr-api-key` and `radarr-api-key` from `homelab/apps/media` and templates `recyclarr-secrets`; do not create an unrelated Vault `apps/recyclarr` secret.

2. The server key lives at `homelab/apps/media` as `recyclarr-api-key` (at least 32 characters), and ESO renders it as the `api-key` entry of `recyclarr-secrets`. The server does not start without it. Create it once:

    ```bash
    VAL="$(openssl rand -hex 32)" make vault-put-secret SECRET_PATH=apps/media KEY=recyclarr-api-key
    ```

3. Run a sync and check the result. The CLI in the pod talks to the server in the same pod:

    ```bash
    kubectl -n media exec deploy/recyclarr -- recyclarr sync
    kubectl -n media exec deploy/recyclarr -- recyclarr sync --preview
    ```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Receives quality profiles and custom formats |
| Radarr | Receives quality profiles and custom formats |

## Upstream

- [https://recyclarr.dev](https://recyclarr.dev)
- [Kubernetes (Helm) guide](https://recyclarr.dev/guide/installation/kubernetes/)
