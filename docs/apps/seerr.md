# Seerr

Seerr is a media request management application (the unified successor to Jellyseerr and Overseerr). Users browse and request movies or TV shows through its web UI, and those requests are automatically forwarded to Radarr or Sonarr for processing.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `seerr-chart` v3.3.0 ([seerr-team](https://github.com/seerr-team/seerr)) |
| Image | `ghcr.io/seerr-team/seerr` |
| Port | 80 |
| HTTPRoute | `seerr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-seerr` |
| Internal URL | `http://arr-seerr.arr.svc.cluster.local:80` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`local-path`) | 5Gi | `/app/config` |

Seerr does not require the shared `arr-data` volume because it interacts with media through the Sonarr/Radarr and Jellyfin APIs rather than the filesystem.

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 256Mi |
| Limits | -- | 512Mi |

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.
- Uses the official Seerr Helm chart (OCI: `ghcr.io/seerr-team/seerr/seerr-chart`).

### Authentication

Seerr authenticates through **Jellyfin** directly. The deployed configuration enables Jellyfin and local login; it does not configure OIDC.

## Post-Deploy Verification

`SeerrConfig` declares Jellyfin authentication and Sonarr/Radarr integrations. Verify the credentials and initial setup, then confirm the configured quality profile IDs match the profiles Recyclarr created before testing a request. See [Media Operator](media-operator.md) for configuration ownership and cold-start prerequisites.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Jellyfin | User authentication and library status |
| Sonarr | Receives TV show requests |
| Radarr | Receives movie requests |

## Upstream

- [https://github.com/seerr-team/seerr](https://github.com/seerr-team/seerr)
