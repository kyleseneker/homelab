# Phase 8 -- Configuration as Code

**Status:** In progress -- 8.3 declined with reasons; 8.4--8.6 landed bar the items below; 8.7 and 8.8 outstanding

**Goal:** Extend reproducibility past the pod boundary. Today the pipeline rebuilds every layer from bare metal up to running containers and then stops -- every setting *inside* an application is hand-entered in a web UI. Close that gap with a purpose-built Kubernetes operator.

**Addresses:** [C1--C9](assessment.md#configuration-layer), [K18--K27](assessment.md#kubernetes-software-layer), [M1, M3--M6](assessment.md#media-platform)

---

## 8.3 Adopt Configarr

**Not adopting.** Configarr's advantage is breadth -- root folders, download clients with remote
path mappings, delay profiles. The operator already owns `rootFolders`, `downloadClients`,
`downloadClientConfig` and `notifications` on every PVR instance, so adopting Configarr for that
surface would put two controllers on the same resources, each reverting the other.
`media_operator_drift_corrected_total` would show it as a resource that never settles.

What remains once the overlap is removed -- delay profiles and `media_naming_api` -- does not
justify replacing a sync that runs cleanly every six hours. Recyclarr already covers quality
definitions, quality profiles, custom formats and media naming, and its last run reported every
section up to date.

| | |
|---|---|
| **Why** | Configarr is the maintained successor, but the surface it adds is surface the operator already reconciles. |

## 8.4 The media-operator

Built in its own repository ([kyleseneker/media-operator](https://github.com/kyleseneker/media-operator)), API group `media-operator.dev/v1alpha1`.

- [ ] Extend envtest coverage to the remaining kinds. Nine run create/reconcile/delete against a live apiserver today; Radarr, Lidarr and Readarr share Sonarr's reconciler shape, and Plex and FlareSolverr are not in the table

| | |
|---|---|
| **Why** | This is the learning goal, against a problem with real ordering constraints (Sonarr key -> Prowlarr application -> indexer -> tag -> proxy) rather than toy CRUD. Informers, work queues, finalizers, status conditions, owner refs, SSA and CEL validation, on a system in daily use. |
| **Ordering** | Sync waves cannot help. The applicationset-controller creates Applications directly with no parent syncing them, so waves on a generated Application are inert (K24). Correctness comes from readiness gating in the controller. |
| **Lesson** | An app that accepts an unknown field and returns 2xx makes a wrong payload indistinguishable from a correct one. Three such bugs shipped before anything checked the payload against the receiving API rather than against the CRD. |

## 8.5 Package and Ship the Operator

- [ ] Coerce the OpenClaw webhook `headers` field to JSON -- the deployed payload is an array of `{key, value}` objects, not a string
- [ ] Make NAS directory creation (C9) a separate one-shot Job -- **not** a `RootFolder.ensureDirectory` field, which would require mounting the 10Ti `arr-data` PV into the manager and whose `chown` is a no-op or `EPERM` against a UID-squashing NAS
- [ ] Retire `apps/openclaw/boot-configmap.yml`'s notification reconciliation
- [ ] Deploy the remaining charts (`requests`, `automation`, `transcode`, `utilities`) as those apps are brought under config-as-code

| | |
|---|---|
| **Scope** | Fifteen kinds covers the apps in daily use. Everything with no usable write API stays in 8.6. |

## 8.6 The Long Tail

Bootstrap Jobs and seeded config files, not controller work.

- [ ] **Bazarr** (C6): template `/config/config/config.yml` -- the API is too weak to drive
- [ ] **Uptime Kuma** (C8): no REST write API exists -- replace the monitor list with `blackbox-exporter` and Git-committed `Probe` resources
- [ ] **NAS layout** (C9): move the volume UUID out of the PV manifest into documented configuration

## 8.7 Media Platform

- [ ] Install the Jellyfin plugins -- Intro Skipper, TMDB Box Sets, Playback Reporting, Trakt (M5). Resize `jellyfin/pvc.yml` past its current 5Gi first; trickplay plus fingerprints will not fit
- [ ] Add a Usenet path: SABnzbd as a standalone controller (not inside the gluetun pod), a provider and an indexer (M1). `arr-egress` allows world egress on TCP/443 only -- 563 must be added
- [ ] Deploy Janitorr in dry-run for retention, and leave it there until the NAS mirror exists (M3)

| | |
|---|---|
| **Why** | M1 and M3 are what decide whether the platform replaces streaming or gets abandoned: a request that fails sends a household back to Netflix, and a library with no ceiling eventually stops accepting writes. Off-LAN access (M2) is tracked in [Phase 3](phase-3-network.md). |

## 8.8 Decisions to Record

---

## What Stays Click-Ops

After all of the above: Grafana ad-hoc explores, Alertmanager silences (correctly ephemeral), Jellyfin per-user watch state and playback positions, Tdarr's visual flow editor beyond import/export, and OpenClaw's Control-UI settings that live on the PVC by design. None of it is state worth mourning.
