# Recyclarr

Recyclarr automatically syncs quality profiles and custom formats from TRaSH Guides to Sonarr and Radarr. It runs as a Kubernetes CronJob every 6 hours, ensuring your quality settings stay consistent and up to date.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/recyclarr/recyclarr` |
| Controller type | CronJob |
| Schedule | `0 */6 * * *` (every 6 hours) |
| HTTPRoute | -- (headless CronJob, no web UI) |
| Namespace | `arr` |
| ArgoCD app | `arr-recyclarr` |

### Storage

| Volume | Type | Mount Path | Notes |
|--------|------|------------|-------|
| `state` | PVC (`nfs-client`, 256Mi) | `/config` | Writable state and downloaded resources; holder keeps it mounted for Velero |
| `tmp` | emptyDir | `/tmp` | Required with read-only root filesystem |
| `config` | ConfigMap (`recyclarr-config`) | `/config/recyclarr.yml` | Quality profile and custom format definitions |
| `secrets` | Secret (`recyclarr-secrets`) | `/config/secrets.yml` | Sonarr and Radarr API keys |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 64Mi |
| Limits | -- | 128Mi |

### Job History

| | Retained |
|---|----------|
| Successful jobs | 1 |
| Failed jobs | 3 |

## Key Configuration

- Container args: `sync` -- runs a one-shot sync of all configured profiles.
- Environment variables from ConfigMap `arr-env` (TZ, PUID, PGID).
- The Job and state holder run as UID 977/GID 988, matching the NAS media identity. Recyclarr's process identity is set by the pod security context; `PUID`/`PGID` alone do not change it. Matching ownership lets Git use the NFS cache without disabling its ownership check.
- Configuration is split into two files:
    - `recyclarr.yml` (shared ConfigMap from `k8s/components/recyclarr-config`) -- defines which quality profiles and custom formats to sync. `SONARR_URL` and `RADARR_URL` can override the production defaults for isolated recovery.
    - `secrets.yml` (Secret) -- contains Sonarr and Radarr API keys referenced by the config.

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

1. Run `make arr-keys-adopt` after Sonarr/Radarr initialization or restore. ESO reads `sonarr-api-key` and `radarr-api-key` from `homelab/apps/arr` and templates `recyclarr-secrets`; do not create an unrelated Vault `apps/recyclarr` secret.

2. Trigger a manual sync to verify the configuration:

    ```bash
    kubectl create job --from=cronjob/arr-recyclarr -n arr recyclarr-manual
    ```

3. Check the job logs to confirm profiles and custom formats were applied:

    ```bash
    kubectl logs -n arr job/recyclarr-manual
    ```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Receives quality profiles and custom formats |
| Radarr | Receives quality profiles and custom formats |

## Upstream

- [https://recyclarr.dev](https://recyclarr.dev)

The writable volumes follow [Recyclarr's read-only container requirements](https://recyclarr.dev/guide/installation/docker/). CronJobs use `Forbid` concurrency so scheduled runs cannot race over the state volume. Avoid launching a manual sync while a scheduled one is active. The `arr-recyclarr-state-holder` must stay running for file-system backups between jobs.
