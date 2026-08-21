# Phase 8 -- Configuration as Code

**Status:** In progress -- 8.1, 8.2 and 8.4--8.6 largely landed; 8.3, 8.7 and 8.8 outstanding

**Goal:** Extend reproducibility past the pod boundary. Today the pipeline rebuilds every layer from bare metal up to running containers and then stops -- every setting *inside* an application is hand-entered in a web UI. Close that gap with a purpose-built Kubernetes operator.

**Addresses:** [C1--C9](assessment.md#configuration-layer), [K18--K27](assessment.md#kubernetes-software-layer), [M1, M3--M6](assessment.md#media-platform)

---

## 8.1 Fix the Blocking Defects

- [x] Replace `Makefile:126` with `kubectl apply -k k8s/bootstrap/applicationsets/` (K18)
- [x] Give the media share its own export root -- point `nfs-provisioner/values.yml` at a sibling directory and re-provision (K19)
- [x] Replace ArgoCD's literal CA PEM with a trust-manager Bundle (K20) -- the `custom-ca-certs` Bundle reads `homelab-ca-secret` and republishes it into `argocd`, so a CA rotation propagates without a commit. argocd-server's mount is `optional: true`, because on a cold rebuild trust-manager does not exist yet and a required mount would deadlock the bootstrap; the pod needs one restart after the CA first appears
- [x] Repair Recyclarr end to end: version bump, unique instance names, corrected `trash_id`s, required `qualities:` block (K25)
- [x] Add `- httproute.yml` to `apps/arr/seerr/kustomization.yml` and flip `route.main.enabled` (K26)
- [x] Set `UN_SONARR_0_PATHS_0` / `UN_RADARR_0_PATHS_0` to `/data/torrents`; change Unpackerr to UID 977 / GID 988 (K27). Its 401s are fixed by 8.2, not here
- [x] Add a `render` job to `validate.yml`: `kustomize build` per directory, `helm template` per `config.yml` (K22). It also checks every `config.yml` against the ApplicationSet's key contract, and `gen-crd-schemas.sh` keeps kubeconform aware of the operator's CRDs
- [x] Add a Renovate `customManager` matching the `chartRepo`/`chartName`/`chartVersion` keys in `config.yml` (K23)
- [ ] Reconcile `docs/architecture/auth.md` with reality, and decide whether to build Gateway API forward-auth (K21)

| | |
|---|---|
| **Why** | The rebuild path is broken today, so none of the work below can be tested from zero. Recyclarr may never have applied, which makes the Configarr comparison in 8.3 meaningless. And CI that never renders a manifest is how three of these shipped unnoticed in the first place. |

## 8.2 Invert the API-Key Flow

- [x] `make arr-keys-adopt`: copy each app's live key into `homelab/apps/arr` without printing it, making Vault the source
- [x] One `arr-api-keys` ExternalSecret in `apps/arr/prereqs/`, ESO-templated to emit both the `APPNAME__AUTH__APIKEY` env names and the plain keys existing consumers read
- [x] Add `envFrom.secretRef` alongside the existing `configMapRef: arr-env` in sonarr, radarr and prowlarr `values.yml`
- [x] Collapse the duplicate key copies in Vault -- `apps/exportarr` is gone and `apps/unpackerr` keeps only the qBittorrent password; every consumer reads `apps/arr`
- [ ] Destructive test: delete `arr-prowlarr-config`, let it rebuild, confirm the key is unchanged

| | |
|---|---|
| **Why** | The single biggest unblock in the repo, and roughly 30 lines of YAML. Today a cold rebuild deadlocks -- four humans-visiting-web-UIs stand between an empty PVC and eight consumers. After this, `kubectl delete pvc` on any *arr config volume is survivable. |
| **Verified** | The `APP__SECTION__KEY` env override landed in Sonarr v4.0.4.1699 (2024-05-24) and was cherry-picked to Radarr the same month. The cluster runs Sonarr 4.0.17, Radarr 6.0.4, Prowlarr 2.3.0. Seerr takes `API_KEY` directly. |
| **Do not** | Set `__AUTH__METHOD: External`. That disables the app's own login on the assumption a proxy authenticates first -- and per K21, nothing does. |

## 8.3 Adopt Configarr

- [ ] Swap the Recyclarr image; `configmap.yml` transplants nearly verbatim -- same YAML dialect, same `!secret` indirection
- [ ] Retarget the ExternalSecret at the new `arr-api-keys` source
- [ ] Extend coverage to root folders, download clients with remote path mappings, `media_naming_api`, delay profiles
- [ ] Resolve the transcode contradiction before touching profiles (M6, see 8.8)

| | |
|---|---|
| **Why** | Configarr is the maintained successor and covers meaningfully more surface for near-zero migration cost. |
| **Optional** | Independent of the operator. Taking it removes `RootFolder`, `DownloadClient` and `ArrSettings` from 8.4's scope; skipping it means the operator owns those too. Note the current `recyclarr/configmap.yml` sets only `quality_definition`, `quality_profiles` and `custom_formats`, so naming and Propers/Repacks are hand-clicked today even though Recyclarr already supports them. |

## 8.4 The media-operator

Built in its own repository ([kyleseneker/media-operator](https://github.com/kyleseneker/media-operator)), API group `media-operator.dev/v1alpha1`.

- [x] Scaffold with kubebuilder v4, against Kubernetes 1.31.4
- [x] One config CRD per app -- 15 kinds split across seven API groups, each group its own manager and chart, so an app that is not deployed costs nothing
- [x] Declare indexers **only** against the `prowlarr` instance -- Prowlarr's own sync fans them into Sonarr and Radarr, which removes the largest ordering hazard
- [x] Gate on app reachability: unreachable requeues without returning an error, so it does not enter exponential backoff
- [x] Adopt by name, and merge partial field arrays rather than discarding entries the CR omits
- [x] Finalizers with a per-CR `deletionPolicy` (`orphan`/`delete`) and a 10-minute give-up path, so a dead app cannot wedge `kubectl delete` or an ArgoCD prune
- [x] Prune only what is recorded in `.status.managedResources`, so anything created outside the operator is never deleted
- [x] Default `reconcile.interval` to 5m -- these are SQLite-backed apps
- [x] Emit `app_api_request_duration_seconds`, `app_api_errors_total`, `resources_pruned_total`, `managed_resources` and `config_synced`
- [ ] Validate against `GET /api/vN/<kind>/schema` before writing, failing fast with the valid field names in the message
- [ ] envtest coverage -- the controllers sit at 0% today
- [ ] Contract tests per app, asserting every spec field maps to a key the target API actually accepts. These apps answer 2xx for a payload they then ignore, so an unmapped field is inert while the CR reports `Synced=True` -- qBittorrent preferences, Jellyfin library paths and Tdarr's library settings have all been silently discarded this way. qBittorrent, SABnzbd and Tdarr have such a test; the remaining kinds do not
- [ ] A drift-corrected counter plus a `PrometheusRule` on repeated corrections
- [ ] `driftPolicy: Observe` to record drift without writing

| | |
|---|---|
| **Why** | This is the learning goal, against a problem with real ordering constraints (Sonarr key -> Prowlarr application -> indexer -> tag -> proxy) rather than toy CRUD. Informers, work queues, finalizers, status conditions, owner refs, SSA and CEL validation, on a system in daily use. |
| **Ordering** | Sync waves cannot help. The applicationset-controller creates Applications directly with no parent syncing them, so waves on a generated Application are inert (K24). Correctness comes from readiness gating in the controller. |
| **Lesson** | An app that accepts an unknown field and returns 2xx makes a wrong payload indistinguishable from a correct one. Three such bugs shipped before anything checked the payload against the receiving API rather than against the CRD. |

## 8.5 Package and Ship the Operator

- [x] Seven OCI Helm charts published to GHCR on tag, with CRDs synced into each chart and `make verify-crds` guarding the copy in CI
- [x] Managers and CRs as separate Applications: `media-operator`, `media-operator-downloads`, `media-operator-mediaservers`, plus `arr-media-config` for the CRs with `SkipDryRunOnMissingResource=true`
- [x] Generate CRD schemas and add a `-schema-location` for the new kinds -- `scripts/gen-crd-schemas.sh` derives them from the deployed chart versions, so they cannot drift from what is running
- [x] Label every manager pod `app.kubernetes.io/part-of: media-operator`, so one CiliumNetworkPolicy covers all of them and a new manager needs no policy change
- [ ] Coerce the OpenClaw webhook `headers` field to JSON -- the deployed payload is an array of `{key, value}` objects, not a string
- [ ] Make NAS directory creation (C9) a separate one-shot Job -- **not** a `RootFolder.ensureDirectory` field, which would require mounting the 10Ti `arr-data` PV into the manager and whose `chown` is a no-op or `EPERM` against a UID-squashing NAS
- [ ] Retire `apps/openclaw/boot-configmap.yml`'s notification reconciliation
- [ ] Deploy the remaining charts (`requests`, `automation`, `transcode`, `utilities`) as those apps are brought under config-as-code

| | |
|---|---|
| **Scope** | Fifteen kinds covers the apps in daily use. Everything with no usable write API stays in 8.6. |

## 8.6 The Long Tail

Bootstrap Jobs and seeded config files, not controller work.

- [x] **Jellyfin** (C5): no Job needed -- `JellyfinConfig` runs the startup wizard, creates the libraries and sets QSV encoding, with the admin credentials sourced from Vault
- [ ] **Authentik** (C7): blueprints in `/blueprints/custom/` for providers, applications, outposts, flows and groups, with client secrets from `!Env` so Vault becomes the source rather than the destination
- [x] **Seerr** (C6): `SeerrConfig` runs the setup, wires Jellyfin plus Sonarr and Radarr, and enables the discovered libraries; it authenticates with an API key adopted into Vault, because re-authenticating through Jellyfin fails once the admin user exists
- [x] **qBittorrent** (C6): share-limit policy and categories reconciled by `QBittorrentConfig`; the WebUI account is seeded into `qBittorrent.conf` on a fresh volume from a PBKDF2 hash held in Vault, so deleting the config PVC no longer deadlocks the stack
- [ ] **Bazarr** (C6): template `/config/config/config.yml` -- the API is too weak to drive
- [ ] **Tdarr** (C6): export the flow as JSON, commit it, POST via `/api/v2/cruddb`
- [ ] **Uptime Kuma** (C8): no REST write API exists -- replace the monitor list with `blackbox-exporter` and Git-committed `Probe` resources
- [ ] **NAS layout** (C9): move the volume UUID out of the PV manifest into documented configuration

## 8.7 Media Platform

- [ ] Install the Jellyfin plugins -- Intro Skipper, TMDB Box Sets, Playback Reporting, Trakt (M5). Resize `jellyfin/pvc.yml` past its current 5Gi first; trickplay plus fingerprints will not fit
- [x] Add a PrometheusRule on NFS free space with a `predict_linear` forecast (M3) -- `MediaLibrarySpaceLow`, `MediaLibraryFillingUp` and an `absent()` guard on `arr-data`
- [ ] Add a Usenet path: SABnzbd as a standalone controller (not inside the gluetun pod), a provider and an indexer (M1). `arr-egress` allows world egress on TCP/443 only -- 563 must be added
- [ ] Deploy Janitorr in dry-run for retention, and leave it there until the NAS mirror exists (M3)
- [x] Work around NFS inotify (M4) -- Sonarr and Radarr hold a `MediaBrowser` notification with `updateLibrary` on import, so Jellyfin refreshes on import rather than waiting for its 12h scan, which stays as the backstop

| | |
|---|---|
| **Why** | M1 and M3 are what decide whether the platform replaces streaming or gets abandoned: a request that fails sends a household back to Netflix, and a library with no ceiling eventually stops accepting writes. Off-LAN access (M2) is tracked in [Phase 3](phase-3-network.md). |

## 8.8 Decisions to Record

- [ ] **ADR-018 -- \*arr configuration as code.** The CRD taxonomy and reconcile semantics from 8.4, and why a purpose-built operator over Crossplane + provider-terraform (the fallback reaches fuller coverage without hand-written field mappings, but teaches composition rather than controllers, and Kyverno's `require-resource-limits` in Enforce mode rejects Crossplane's synthesised provider Deployments until `crossplane-system` is excluded)
- [ ] **ADR-019 -- transcode policy.** Resolve M6: whether the library targets x264 acquisition with in-house HEVC re-encoding, or native HEVC. Defensible either way; currently whichever Tdarr flow happens to be enabled decides it
- [ ] Amend ADR-010 or `docs/architecture/auth.md` to describe the auth mechanism that actually exists (K21)

---

## What Stays Click-Ops

After all of the above: Grafana ad-hoc explores, Alertmanager silences (correctly ephemeral), Jellyfin per-user watch state and playback positions, Tdarr's visual flow editor beyond import/export, and OpenClaw's Control-UI settings that live on the PVC by design. None of it is state worth mourning.
