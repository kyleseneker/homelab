# Seerr

Seerr is a media request management application (the unified successor to Jellyseerr and Overseerr). Users browse and request movies or TV shows through its web UI, and those requests are automatically forwarded to Radarr or Sonarr for processing.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `seerr-chart` v3.3.0 ([seerr-team](https://github.com/seerr-team/seerr)) |
| Image | `ghcr.io/seerr-team/seerr:v3.1.0` |
| Port | 80 |
| HTTPRoute | `seerr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-seerr` |
| Internal URL | `http://arr-seerr.arr.svc.cluster.local:80` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`nfs-client`) | 1Gi | `/app/config` |

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

Seerr authenticates through **Jellyfin** directly. Native OIDC support is not yet available ([seerr-team/seerr#2715](https://github.com/seerr-team/seerr/pull/2715)).

## Post-Deploy Setup

1. Open `https://seerr.homelab.local` and start the setup wizard.
2. Sign in with Jellyfin:
    - Jellyfin server URL: `http://arr-jellyfin.arr.svc.cluster.local:8096`
    - Use a Jellyfin admin account to authenticate.
3. Add Sonarr (Settings > Sonarr):
    - URL: `http://arr-sonarr.arr.svc.cluster.local:8989`
    - API Key: *(from Sonarr > Settings > General)*
    - Select quality profile and root folder (`/data/media/tv`).
4. Add Radarr (Settings > Radarr):
    - URL: `http://arr-radarr.arr.svc.cluster.local:7878`
    - API Key: *(from Radarr > Settings > General)*
    - Select quality profile and root folder (`/data/media/movies`).

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Jellyfin | User authentication and library status |
| Sonarr | Receives TV show requests |
| Radarr | Receives movie requests |

## Upstream

- [https://github.com/seerr-team/seerr](https://github.com/seerr-team/seerr)
