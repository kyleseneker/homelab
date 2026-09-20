# Phase 8 — Configuration as Code

**Status:** Substantially implemented; fresh-install completion and user outcomes remain open.

**Goal:** Rebuild the useful media platform, including internal application settings and valuable household state. See [ADR-018](../decisions/018-arr-configuration-as-code.md).

## 8.1 Implemented ownership

| Owner | Declared surface |
|---|---|
| Media operator — seven pinned charts | PVR, downloads, indexers, media servers, requests, subtitles and transcode controllers |
| Eight media Config resources | Sonarr, Radarr, Prowlarr, qBittorrent, Jellyfin, Seerr, Bazarr and Tdarr |
| Recyclarr | Quality definitions, profiles, custom formats and naming |
| Authentik blueprints | OIDC/proxy providers, applications and outpost bindings |
| Blackbox Probe resources | Reproducible HTTP/HTTPS reachability monitoring |
| Vault + External Secrets | Shared application keys and credentials, with bootstrap exceptions |

Configarr is not being adopted alongside this ownership model. Its overlapping capabilities would require a deliberate migration, not another reconciler writing the same settings. Separate-repository operator tests/releases belong to the media-operator backlog; homelab tracks the pinned contract it consumes.

## 8.2 Prove empty-database bootstrap

- [ ] Produce a credential dependency map, including keys needed to start apps versus keys the apps create themselves.
- [ ] Verify first boot for Bazarr, Seerr and qBittorrent, not only a reconcile against existing databases.
- [ ] Resolve Sonarr/Radarr/Seerr quality-profile references on a fresh database; do not rely on current numeric IDs.
- [ ] Create required media directories in a separate storage-preparation step with NAS-compatible identity. Do not mount the entire media tree into every operator manager.
- [ ] Verify Authentik administrator bootstrap, secret injection, outpost creation and both OIDC clients against an empty database.
- [ ] Verify operator reconcile errors and repeated drift reach an external notification destination.
- [ ] Test application API payloads against the pinned applications. Schema-valid YAML and HTTP 2xx alone do not establish that a setting took effect.

## 8.3 Remove conflicting and obsolete ownership

- [ ] Confirm notification wiring has exactly one owner and retire any legacy OpenClaw boot-time reconciler once the operator owns the same entries.
- [ ] Keep desired settings in Git and secrets in Vault; document intentional UI-only exceptions.
- [ ] Keep the supported CRD schemas and chart versions aligned in validation and Renovate.

## 8.4 Household media outcomes

- [ ] Verify Gluetun blocks download traffic before tunnel readiness and after tunnel loss; confirm forwarded-port updates reach qBittorrent.
- [ ] Run a request-to-playback acceptance test: Seerr request, acquisition, import, Jellyfin refresh, subtitles, hardware-assisted playback and resume.
- [ ] Verify new requests use the intended quality profile; existing library profile migration is a separately reviewed operation.
- [ ] Add a reliable import notification/refresh path with periodic scans as fallback for NFS.
- [ ] Measure Jellyfin metadata/trickplay and media growth before changing local-path claims or adding plugins; requested PVC size is not enforcement.
- [ ] Evaluate Usenet only when acquisition failures justify another paid dependency and its secrets/network policy are defined.
- [ ] Evaluate retention in dry-run with explicit protected-content rules. Do not enable deletion until the household policy is reviewed.
- [ ] Add desired household UX features such as invites, watch analytics, collections and playback plugins after the core acceptance test passes.
- [ ] Keep public access in [Phase 3](phase-3-network.md) and verify video-preserving Tdarr behavior from [ADR-019](../decisions/019-transcode-policy.md).

## 8.5 Preserve valuable runtime state

Watch history, playback positions, users, requests, download resume information and tracker credentials cannot all be reconstructed from declarative settings. Back up the state worth keeping. Grafana explores and temporary Alertmanager silences can remain ephemeral; household state should not be dismissed as disposable click-ops.

## Definition of Done

A tested empty-database deployment plus a tested state restore yield working requests, import, playback and resume. Each setting has one owner, and any manual bootstrap exception is explicit and reproducible.
