# Arrchitect

Arrchitect reconciles eight media application configurations from Git. It manages root folders, download clients, indexers, libraries, request integration, subtitles, and transcode flows through application APIs. Runtime databases still hold users, libraries, histories, and other state that is not represented by these custom resources.

| Custom resource | Application |
|-----------------|-------------|
| SonarrConfig | Sonarr |
| RadarrConfig | Radarr |
| ProwlarrConfig | Prowlarr |
| QBittorrentConfig | qBittorrent |
| JellyfinConfig | Jellyfin |
| SeerrConfig | Seerr |
| BazarrConfig | Bazarr |
| TdarrConfig | Tdarr |

The `arrchitect` Application installs the `arrchitect` chart from `ghcr.io/kyleseneker/charts` at the version pinned in its `config.yml`. Its `values.yml` turns on only the eight applications above, so the chart installs only their CRDs and RBAC. The operator watches `media`, with metrics and a ServiceMonitor enabled. The API group is `arrchitect.dev/v1alpha1`, and `kubectl -n media get arrchitect` lists every resource with its `Ready` and `Synced` conditions. Custom resources live under `apps/media/media-config/` and deploy as the `media-config` Application. The `arrchitect` Application also holds the PrometheusRule (`ArrchitectConfigNotSynced`, `ArrchitectDriftNeverSettles`).

## Ownership and reconciliation

Each resource declares its service endpoint, credential Secret references, reconciliation interval, and `deletionPolicy: orphan`. Removing the CR leaves application settings intact. Prowlarr owns indexer sync to Sonarr/Radarr; Recyclarr owns quality profiles and custom-format scores. Avoid managing the same settings through multiple controllers or manual edits.

Application APIs must be reachable and credentials valid before reconciliation succeeds. Inspect CR status and operator logs for failed reconciliation, including HTTP 401s. `make media-keys-adopt` transfers generated keys into Vault at `homelab/apps/media`; ESO then reconciles `media-api-keys`. Jellyfin, qBittorrent, Seerr, Tdarr, and provider credentials have their own Secret references. qBittorrent clients authenticate even from the pod network.

All declared resources keep `deletionPolicy: orphan` and the default enforcement policy. Every application here supports observe mode. Prune and `deletionPolicy: delete` are supported for all of them except Jellyfin, which rejects both when the resource is applied.

## Cold-start gaps

The repository does not yet demonstrate a fully unattended rebuild. Generated API keys, initial account setup, and restored database state must agree with Vault. Run the adoption step after application initialization or restore, then verify all eight CRs become ready.

Seerr declares Sonarr's `WEB-1080p` and Radarr's `HD Bluray + WEB` profiles by name. The operator resolves each name against the application's quality-profile API before writing the connection. Run Recyclarr first so the profiles exist. Missing or ambiguous names and API failures leave the existing connection intact and report a reconciliation failure.

The name-based profile lookup passed a lab check against the restored Sonarr: stale ID `7` resolved to recreated ID `8`, name-only configuration selected `8`, and a nonexistent name produced no connection writes. That check used a temporary Seerr API fixture, so it does not establish full Seerr application recovery.

The Bazarr English profile ID also requires validation during a clean rebuild. Prowlarr indexers select the built-in `Standard` sync profile by name, so a rebuilt Prowlarr resolves its current ID; a missing or renamed profile blocks indexer writes and reports a reconciliation failure. Tdarr's large imported flow graph and IDs are operational configuration, not proof that every path is safe: validate library-specific flags and test a copied file before enabling a new flow or changing deletion/replacement behavior.

## Upgrades

Production and the restore lab pin the same chart version. The chart installs and upgrades the CRDs of the applications it runs, so Argo applies CRD changes with the chart. Check the release notes for field changes before bumping the version.

## Upstream

[Arrchitect](https://github.com/kyleseneker/arrchitect)
