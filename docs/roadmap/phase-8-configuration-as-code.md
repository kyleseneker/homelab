# Phase 8 -- Configuration as Code

**Status:** Not started

**Goal:** Extend reproducibility past the pod boundary. Today the pipeline rebuilds every layer from bare metal up to running containers and then stops -- every setting *inside* an application is hand-entered in a web UI. Close that gap with a purpose-built Kubernetes operator.

**Addresses:** [C1--C9](assessment.md#configuration-layer), [K18--K27](assessment.md#kubernetes-software-layer), [M1, M3--M6](assessment.md#media-platform)

---

## 8.1 Fix the Blocking Defects

- [x] Replace `Makefile:126` with `kubectl apply -k k8s/bootstrap/applicationsets/` (K18)
- [ ] Give the media share its own export root -- point `nfs-provisioner/values.yml` at a sibling directory and re-provision (K19)
- [ ] Replace ArgoCD's literal CA PEM with a trust-manager Bundle or a cert-manager `additionalOutputFormat` (K20)
- [x] Repair Recyclarr end to end: version bump, unique instance names, corrected `trash_id`s, required `qualities:` block (K25)
- [x] Add `- httproute.yml` to `apps/arr/seerr/kustomization.yml` and flip `route.main.enabled` (K26)
- [x] Set `UN_SONARR_0_PATHS_0` / `UN_RADARR_0_PATHS_0` to `/data/torrents`; change Unpackerr to UID 977 / GID 988 (K27). Its 401s are fixed by 8.2, not here
- [ ] Add a `render` job to `validate.yml`: `kustomize build` per directory, `helm template` per `config.yml` (K22)
- [x] Add a Renovate `customManager` matching the `chartRepo`/`chartName`/`chartVersion` keys in `config.yml` (K23)
- [ ] Reconcile `docs/architecture/auth.md` with reality, and decide whether to build Gateway API forward-auth (K21)

| | |
|---|---|
| **Why** | The rebuild path is broken today, so none of the work below can be tested from zero. Recyclarr may never have applied, which makes the Configarr comparison in 8.3 meaningless. And CI that never renders a manifest is how three of these shipped unnoticed in the first place. |

## 8.2 Invert the API-Key Flow

- [ ] `make arr-keys` target: `vault kv put homelab/apps/arr <app>-api-key=$(openssl rand -hex 16)` for all four apps
- [ ] One `arr-api-keys` ExternalSecret in `apps/arr/prereqs/`, ESO-templated to emit both the `APPNAME__AUTH__APIKEY` env names and the plain keys existing consumers read
- [ ] Add `envFrom.secretRef` alongside the existing `configMapRef: arr-env` in sonarr, radarr and prowlarr `values.yml`
- [ ] Collapse the duplicate key copies in Vault (`apps/exportarr` and `apps/unpackerr` hold the same Sonarr/Radarr keys)
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

## 8.4 Build the \*arr Operator

New top-level `operators/arr-operator/`, API group `arr.homelab.local/v1alpha1`, wrapping the `devopsarr` Go SDKs.

- [ ] Scaffold with kubebuilder v4; **pin controller-runtime to the v0.19.x line**, `controller-gen` v0.16.x, `ENVTEST_K8S_VERSION=1.31.0` -- the cluster is on Kubernetes 1.31.4 and controller-runtime tracks one minor per release
- [ ] Define the CRD taxonomy: `ArrInstance` (root, one per app, owns base URL + `apiKeySecretRef` + liveness), fine-grained kinds for identity-bearing objects (`Indexer`, `ProwlarrApplication`, `Notification`, `DownloadClient`, `RootFolder`, `ImportList`), and `ArrSettings` as a singleton for the PUT-only config structs that have no identity
- [ ] Declare indexers **only** against the `prowlarr` instance -- Prowlarr's own sync fans them into Sonarr and Radarr, which removes the largest ordering hazard
- [ ] Write one generic reconciler parameterised by an `Adapter[S]` interface (`List`/`Get`/`Create`/`Update`/`Delete`/`Render`/`SchemaFor`), ~80 lines per kind on top
- [ ] Gate children on instance readiness: not-Ready requeues 30s and **returns no error**, so it does not enter exponential backoff
- [ ] Validate against `GET /api/vN/<kind>/schema` before writing, failing fast with the valid field names in the message
- [ ] **Adopt by name first**, `.status.externalID` second -- the ApplicationSet sets `prune: true` unconditionally and a Velero restore renumbers IDs, both of which break ID-first lookup
- [ ] Exclude secret-valued fields from read-back diffing (the APIs return `********`); track them via `.status.appliedHash` instead, with an explicit per-CR `driftCheckFields` allowlist
- [ ] Finalizers with per-kind deletion policy: `Delete` for indexers, clients, notifications and import lists; `Orphan` for `RootFolder`; adoption overrides to `Orphan` unless set explicitly
- [ ] Give the finalizer a 10-minute give-up path so a dead Sonarr can never wedge `kubectl delete` or an ArgoCD prune
- [ ] Field index on `.spec.instanceRef.name` plus `.Watches(&ArrInstance{}, ...)` so children requeue the instant an instance goes Ready
- [ ] Default `reconcileInterval` to 5m, not 1m -- these are SQLite-backed apps
- [ ] Emit `clapperboard_drift_corrected_total` and a Kubernetes Event on every correction; add a `PrometheusRule` on `increase(...[6h]) > 3`
- [ ] Provide `driftPolicy: Observe` to record drift without writing
- [ ] envtest plus an in-memory \*arr fake with recorded `/schema` fixtures

| | |
|---|---|
| **Why** | This is the learning goal, against a problem with real ordering constraints (Sonarr key → Prowlarr application → indexer → tag → proxy) rather than toy CRUD. Informers, work queues, finalizers, status conditions, owner refs, SSA, CEL validation and envtest, on a system in daily use. |
| **Ordering** | Sync waves cannot help. The applicationset-controller creates Applications directly with no parent syncing them, so waves on a generated Application are inert (K24). Correctness comes from readiness gating in the controller; waves only reduce event noise *within* the `arr-config` Application. |
| **Effort** | **30--45 focused days.** First Go module in the repo, 8 CRDs, a generics-parameterised adapter, an envtest harness, a hand-built API fake, a secret resolver with a redaction type, and adoption-by-name. Plan for 6--10 weekends. |

## 8.5 Package and Ship the Operator

- [ ] Two Applications, not one: `arr-operator` (`gitPath k8s/components/arr-operator`, CRDs + manager) and `arr-config` (CRs, `SkipDryRunOnMissingResource=true`)
- [ ] Add a `kustomization.yml` to `k8s/components/arr-operator/` -- the existing `kyverno-policies/` is flat and has none, and `templatePatch` cannot set `source.directory.recurse`
- [ ] Generate CRD schemas and add a `-schema-location` for the new kinds, or the first PR fails kubeconform
- [ ] Make directory creation (C9) a separate one-shot Job -- **not** a `RootFolder.ensureDirectory` field, which would require mounting the 10Ti `arr-data` PV into the manager and whose `chown` is a no-op or `EPERM` against a UID-squashing NAS
- [ ] Coerce the OpenClaw webhook `headers` field to JSON -- the deployed payload is an array of `{key, value}` objects, not a string
- [ ] Add an `instanceRefs` list to fan-out kinds so `Notification` does not need paired CRs that always change together
- [ ] Keep the app→endpoint table (`sonarr → {8989, v3}`, `radarr → {7878, v3}`, `prowlarr → {9696, v1}`) as one reviewable Go var or ConfigMap, not dispatch logic in a factory
- [ ] New CI surface: GHCR auth, a tag→deploy flow, and `disallow-latest-tag` (Enforce) applying to the manager's own manifest
- [ ] Retire `apps/openclaw/boot-configmap.yml`'s notification reconciliation

| | |
|---|---|
| **Scope** | The devopsarr provider exposes 81 Sonarr resources. Eight kinds is ~15% of the settings surface and that is the right answer -- it closes roughly 60% of the configuration inventory. Everything else is 8.6. |

## 8.6 The Long Tail

Bootstrap Jobs and seeded config files, not controller work.

- [ ] **Jellyfin** (C5): one Job hitting `/Startup/Configuration`, `/Startup/User`, `/Library/VirtualFolders`, then `/System/Configuration/encoding` to enable QSV
- [ ] **Authentik** (C7): blueprints in `/blueprints/custom/` for providers, applications, outposts, flows and groups, with client secrets from `!Env` so Vault becomes the source rather than the destination
- [ ] **Seerr** (C6): `/api/v1/settings/{jellyfin,radarr,sonarr}` + `initialize`
- [ ] **qBittorrent** (C6): seed `qBittorrent.conf` from a ConfigMap + initContainer with a PBKDF2 hash derived from the Vault password; ship `categories.json`
- [ ] **Bazarr** (C6): template `/config/config/config.yaml` -- the API is too weak to drive
- [ ] **Tdarr** (C6): export the flow as JSON, commit it, POST via `/api/v2/cruddb`
- [ ] **Uptime Kuma** (C8): no REST write API exists -- replace the monitor list with `blackbox-exporter` and Git-committed `Probe` resources
- [ ] **NAS layout** (C9): move the volume UUID out of the PV manifest into documented configuration

## 8.7 Media Platform

- [ ] Install the Jellyfin plugins -- Intro Skipper, TMDB Box Sets, Playback Reporting, Trakt (M5). Resize `jellyfin/pvc.yml` past its current 5Gi first; trickplay plus fingerprints will not fit
- [ ] Add a PrometheusRule on NFS free space with a `predict_linear` forecast (M3)
- [ ] Add a Usenet path: SABnzbd as a standalone controller (not inside the gluetun pod), a provider and an indexer (M1). `arr-egress` allows world egress on TCP/443 only -- 563 must be added
- [ ] Deploy Janitorr in dry-run for retention, and leave it there until the NAS mirror exists (M3)
- [ ] Add a scheduled library refresh to work around NFS inotify (M4)

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
