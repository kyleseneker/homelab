# Jellyfin

Jellyfin is a self-hosted media server for streaming movies, TV shows, and music. It provides client apps and a web UI for playback, with support for hardware-accelerated transcoding via Intel QuickSync.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v5.3.0 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `lscr.io/linuxserver/jellyfin` |
| Port | 8096 |
| Service type | ClusterIP |
| HTTPRoute | `jellyfin.home.seneker.io` |
| Namespace | `media` |
| ArgoCD app | `jellyfin` |

### Storage

| Volume | Type | Size | Mount Path | Notes |
|--------|------|------|------------|-------|
| `config` | PVC (`local-path`) | 5Gi | `/config` | Jellyfin configuration and metadata |
| `media` | PVC (existing `media-data`) | -- | `/data/media` | Shared media library (`subPath: media`) |
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

- Environment variables injected from ConfigMap `media-env` (TZ, PUID, PGID).
- The service is `ClusterIP`. Clients reach Jellyfin only through the Gateway at `jellyfin.home.seneker.io`, which has a publicly trusted certificate.
- Startup probe allows up to 30 failures at 10-second intervals (5 minutes) to account for library scanning on first boot.

## Authentication

People sign in with their Authentik account. Every client keeps Jellyfin's own username and password screen; the LDAP Authentication plugin checks the credentials against the [Authentik LDAP outpost](../infrastructure/authentik.md#ldap-outpost) and creates the Jellyfin user on first sign-in. Membership of `Jellyfin Users` grants access, and members of `authentik Admins` among them become administrators. To add a person, add their Authentik account to `Jellyfin Users`.

The local administrator in `jellyfin-credentials` does not use LDAP. Arrchitect signs in with it, and it is the emergency login while Authentik is down. Its username must not match any Authentik username.

Arrchitect does not manage plugins, so install and configure the plugin by hand from **Dashboard → Plugins → Catalog → LDAP Authentication**, then restart Jellyfin. The catalog picks the release built for the running Jellyfin version. The configuration lives on the `config` PVC.

| Setting | Value |
|---------|-------|
| LDAP Server / Port | `authentik-ldap.auth.svc.cluster.local` / `389` |
| Secure LDAP, StartTLS | Off |
| LDAP Bind User | `cn=jellyfin-ldap-bind,ou=users,dc=home,dc=seneker,dc=io` |
| LDAP Bind User Password | Vault `infrastructure/authentik-ldap` `jellyfin-bind-password` |
| LDAP Base DN for searches | `dc=home,dc=seneker,dc=io` |
| LDAP Search Filter | `(&(objectClass=user)(memberOf=cn=Jellyfin Users,ou=groups,dc=home,dc=seneker,dc=io))` |
| LDAP Search Attributes | `uid, cn, mail, displayName` |
| LDAP Uid Attribute / Username Attribute | `uid` / `cn` |
| LDAP Admin Base DN | `dc=home,dc=seneker,dc=io` |
| LDAP Admin Filter | `(&(memberOf=cn=Jellyfin Users,ou=groups,dc=home,dc=seneker,dc=io)(memberOf=cn=authentik Admins,ou=groups,dc=home,dc=seneker,dc=io))` |
| Enable User Creation | On |
| Allow Password Change | Off |
| Library Access | Enable access to all libraries |

Use the plugin's server and filter test buttons before saving. Rotating the bind password means updating both Vault and this page.

## Post-Deploy Verification

`JellyfinConfig` declares the administrator credentials, Movies/TV libraries, and QSV settings. Populate `jellyfin-credentials`, verify reconciliation and the administrator login, then test a hardware-transcoded playback. Music is not currently a declared library. See [Arrchitect](arrchitect.md) for configuration ownership and cold-start prerequisites.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Authentik LDAP outpost | Checks sign-ins for Authentik accounts |
| Sonarr / Radarr / Downloads | Provide media files to `/data/media` |
| Seerr | Connects to Jellyfin for user authentication and library status |
| Tdarr | Reads and transcodes files in `/data/media` |

## Upstream

- [https://jellyfin.org](https://jellyfin.org)

## Library Refresh

Jellyfin's own folder watching does not work over NFS, because inotify events do not cross the
mount. Sonarr and Radarr each hold a `MediaBrowser` notification with `updateLibrary` enabled, so
an import tells Jellyfin to refresh rather than waiting for a scheduled scan. Both notifications
are reconciled by Arrchitect.
