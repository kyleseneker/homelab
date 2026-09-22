# Media Operator

Seven operators reconcile eight media application configurations from Git. They manage root folders, download clients, indexers, libraries, request integration, subtitles, and transcode flows through application APIs. Runtime databases still hold users, libraries, histories, and other state that is not represented by these custom resources.

| ArgoCD app | Chart | Custom resources |
|------------|-------|------------------|
| `media-operator` | `media-operator-pvr` | SonarrConfig, RadarrConfig |
| `media-operator-indexers` | `media-operator-indexers` | ProwlarrConfig |
| `media-operator-downloads` | `media-operator-downloads` | QBittorrentConfig |
| `media-operator-mediaservers` | `media-operator-mediaservers` | JellyfinConfig |
| `media-operator-requests` | `media-operator-requests` | SeerrConfig |
| `media-operator-subtitles` | `media-operator-subtitles` | BazarrConfig |
| `media-operator-transcode` | `media-operator-transcode` | TdarrConfig |

Charts come from `ghcr.io/kyleseneker/media-operator`; each `config.yml` pins its version. All watch `arr`, with metrics and ServiceMonitors enabled. The API group is `media-operator.dev/v1alpha1`. Custom resources live under `apps/arr/media-config/` and deploy as the `arr-media-config` Application.

## Ownership and reconciliation

Each resource declares its service endpoint, credential Secret references, reconciliation interval, and `deletionPolicy: orphan`. Removing the CR leaves application settings intact. Prowlarr owns indexer sync to Sonarr/Radarr; Recyclarr owns quality profiles and custom-format scores. Avoid managing the same settings through multiple controllers or manual edits.

Application APIs must be reachable and credentials valid before reconciliation succeeds. Inspect CR status and operator logs for failed reconciliation, including HTTP 401s. `make arr-keys-adopt` transfers generated keys into Vault at `homelab/apps/arr`; ESO then reconciles `arr-api-keys`. Jellyfin, qBittorrent, Seerr, Tdarr, and provider credentials have their own Secret references. qBittorrent clients authenticate even from the pod network.

## Cold-start gaps

The repository does not yet demonstrate a fully unattended rebuild. Generated API keys, initial account setup, and restored database state must agree with Vault. Run the adoption step after application initialization or restore, then verify all eight CRs become ready.

Seerr declares Sonarr's `WEB-1080p` and Radarr's `HD Bluray + WEB` profiles by name. The pinned [v0.34.3 release](https://github.com/kyleseneker/media-operator/releases/tag/v0.34.3) resolves each name against the application's quality-profile API before writing the connection. Run Recyclarr first so the profiles exist. Missing or ambiguous names and API failures leave the existing connection intact and report a reconciliation failure; ID-only configurations remain supported upstream.

The v0.34.1 controller passed a lab check against the restored Sonarr: stale ID `7` resolved to recreated ID `8`, name-only configuration selected `8`, and a nonexistent name produced no connection writes. That check used a temporary Seerr API fixture, so it does not establish full Seerr application recovery. Production Sonarr and Radarr connections also reconciled successfully with the new controller.

The Bazarr English profile ID and Prowlarr application profile IDs also require validation during a clean rebuild. Tdarr's large imported flow graph and IDs are operational configuration, not proof that every path is safe: validate library-specific flags and test a copied file before enabling a new flow or changing deletion/replacement behavior.

The operators are pinned to 0.34.3 in production and restore-lab configurations.
This includes safe pruning and ownership retention, namespace-correct Secret
RBAC, and FlareSolverr permissions in the indexers chart. The separate
FlareSolverr RBAC workaround has been removed. Status-only CR updates no longer
trigger another reconciliation.

All declared resources retain `deletionPolicy: orphan` and the default enforcement
policy. Upstream now supports tracked-resource deletion for Servarr and
FlareSolverr; other integrations reject that policy. Observe mode is supported for
Servarr, FlareSolverr, qBittorrent and Jellyfin, and explicitly rejected elsewhere.
Do not enable pruning on an upgraded installation without reviewing existing
`status.managedResources` records: older versions could claim pre-existing items.


## Upstream

[Media Operator](https://github.com/kyleseneker/media-operator)
