# Recyclarr

Recyclarr automatically syncs quality profiles and custom formats from TRaSH Guides to Sonarr and Radarr. It runs as a Kubernetes CronJob every 6 hours, ensuring your quality settings stay consistent and up to date.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/recyclarr/recyclarr:8.5.1` |
| Controller type | CronJob |
| Schedule | `0 */6 * * *` (every 6 hours) |
| HTTPRoute | -- (headless CronJob, no web UI) |
| Namespace | `arr` |
| ArgoCD app | `arr-recyclarr` |
| Sync wave | 1 |

### Storage

| Volume | Type | Mount Path | Notes |
|--------|------|------------|-------|
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
- Configuration is split into two files:
    - `recyclarr.yml` (ConfigMap) -- defines which quality profiles and custom formats to sync.
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

1. Store Sonarr and Radarr API keys in Vault:

    ```bash
    vault kv put homelab/apps/recyclarr \
      secrets.yml="sonarr_api_key: your_key\nradarr_api_key: your_key"
    # ESO syncs it to K8s automatically via recyclarr-external-secret.yml
    ```

    The `secrets.yml` file should follow the Recyclarr secrets format with keys for each instance.

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
