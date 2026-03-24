# Jellyseerr

Jellyseerr is a media request management application. Users browse and request movies or TV shows through its web UI, and those requests are automatically forwarded to Radarr or Sonarr for processing.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `fallenbagel/jellyseerr:2.7.3` |
| Port | 5055 |
| Ingress | `jellyseerr.homelab.local` |
| Namespace | `arr` |
| ArgoCD app | `arr-jellyseerr` |
| Sync wave | 1 |
| Internal URL | `http://arr-jellyseerr.arr.svc.cluster.local:5055` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `config` | PVC (`nfs-client`) | 1Gi | `/app/config` |

Jellyseerr does not require the shared `arr-data` volume because it interacts with media through the Sonarr/Radarr and Jellyfin APIs rather than the filesystem.

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 256Mi |
| Limits | -- | 512Mi |

## Key Configuration

- Environment variables injected from ConfigMap `arr-env` (TZ, PUID, PGID).
- Liveness, readiness, and startup probes are enabled.
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.

### Authentication

Jellyseerr uses **native OIDC** to Authentik rather than the forward-auth proxy used by other arr apps. This is because Jellyseerr has built-in OAuth2 support, so a direct OIDC integration is configured through its Settings UI. The ingress does not carry the `auth-url`/`auth-signin` annotations that other arr apps use.

## Post-Deploy Setup

1. Open `https://jellyseerr.homelab.local` and start the setup wizard.
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

- [https://github.com/Fallenbagel/jellyseerr](https://github.com/Fallenbagel/jellyseerr)
