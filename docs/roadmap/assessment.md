# Assessment

Analysis of the homelab's current strengths and gaps, used to prioritize the [roadmap phases](index.md).

## Strengths

**Full IaC pipeline.** Every layer from Proxmox host configuration through application deployment is codified and reproducible. `make k8s-deploy` rebuilds from zero. This matches how production infrastructure teams operate and is rare in homelabs.

**GitOps discipline.** ApplicationSet with Git File Generator for automatic app discovery, automated sync with prune and self-heal, Renovate with digest pinning on a weekly schedule. No manual `kubectl apply` for day-2 operations.

**Externalized secrets.** Vault with AWS KMS auto-unseal and ESO using Kubernetes auth is the industry-standard pattern. No secrets in Git, no static credentials.

**Layered security.** Cilium network policies (default-deny per namespace), Kyverno admission policies, non-root security contexts with dropped capabilities, gitleaks + Trivy in CI, Authentik SSO on every service. Multiple independent controls at different layers.

**Complete observability.** Metrics, logs, alerting, audit logging, capacity planning (VPA/Goldilocks), and synthetic monitoring (Uptime Kuma). Custom PrometheusRules for app health, infrastructure, backups, and node resources.

**Exceptional documentation.** 15 ADRs, architecture docs for every subsystem, runbooks for DR/upgrades/troubleshooting/SSO bypass, auto-published MkDocs site.

**Clean operational interface.** Makefile targets for every operational task. Reloader for config-driven restarts. Descheduler for pod rebalancing. Low operator toil.

## Gaps

### Physical Layer

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| P1 | **No UPS** | Power event corrupts NVMe mid-write, kills NAS mid-IO, or causes unclean Proxmox/etcd shutdown. | Resolved |
| P2 | **Single NAS drive** | One drive failure loses all NFS-backed data: media, app configs, Prometheus, Loki, Vault, Velero backups. | Critical |
| P3 | **Running at GbE when 10G is available** | MS-01 has 2x 10G SFP+ unused. NFS throughput and future live migration bottlenecked at 1 Gbps. USW-16-PoE has 1G SFP only. | Low |
| P4 | **Single compute host** | All VMs on one machine. Hardware failure means total cluster loss. | High |
| P5 | **Unused PCIe x16 slot** | Half-height PCIe 4.0 x16 available for a dedicated GPU, HBA, or NIC. | Informational |
| P6 | **No IPMI/remote management** | MS-01 supports Intel vPro AMT but it is not configured. Hung host requires physical access. | Resolved |

### Network Layer

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| N1 | **No dedicated management VLAN** | Proxmox, switch, PDU, and NAS management share VLANs with production or household traffic. | Resolved |
| N2 | **No IoT VLAN** | Smart home devices (if any) share the default VLAN with household devices and the NAS. | Low |
| N3 | **DNS is manual static entries** | Adding a service requires a manual UniFi console edit. | Medium |
| N4 | **WireGuard VPN not configured** | No way to reach the homelab off-site. | Medium |
| N5 | **No external access path** | No reverse proxy, Cloudflare Tunnel, or Tailscale Funnel for sharing services externally. | Low |
| N6 | **Unrestricted internet egress from Homelab VLAN** | A compromised pod can reach any external destination. | Low |

### Kubernetes / Software Layer

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| K1 | **Single control plane** | API server, etcd, and scheduler are a single point of failure. | High |
| K2 | **Kyverno audit-mode policies not enforced** | `require-resource-limits`, `require-run-as-nonroot`, `require-readonly-rootfs` only report. | Resolved |
| K3 | **No ResourceQuotas or LimitRanges** | A runaway pod can OOM an entire node and cascade-kill neighbors. | Medium |
| K4 | **Vault standalone, no HA** | Single Vault pod on NFS. Pod failure loses secret access cluster-wide. | Medium |
| K5 | **No offsite backup copy** | Velero backs up to MinIO on the same NAS as production data. | Resolved |
| K6 | **Authentik Redis unauthenticated** | `auth.enabled: false`. Network policies mitigate but any pod in the auth namespace has access. | Resolved |
| K7 | **Prometheus TSDB on NFS** | Heavy random I/O on NFS degrades query performance and risks TSDB corruption. | Resolved |
| K8 | **No HPA** | Nothing scales horizontally under load. | Low |
| K9 | **No pod topology spread constraints** | Scheduler may co-locate critical services on one node. | Medium |
| K10 | **No distributed tracing** | Debugging cross-service request flows requires manual log correlation. | Low |
| K11 | **No image registry allowlist** | Any registry allowed. No protection against pulls from untrusted sources. | Low |
| K12 | **No chaos testing** | DR runbooks exist but are never automatically validated. | Low |
| K13 | **No supply chain verification** | No cosign signature verification or SBOM generation. | Low |
| K14 | **Grafana dashboards are click-ops** | Dashboards not stored in Git. DR event could lose custom dashboards. | Medium |
| K15 | **No cert-manager health alerting** | cert-manager pod failures or renewal errors are not monitored. | Low |
| K16 | **No etcd snapshot schedule** | Single control plane with no dedicated etcd backup. Velero backs up API resources but an etcd corruption or quorum loss requires a snapshot to restore. | Resolved |
| K17 | **No Loki retention policy** | Logs grow unbounded on NFS. No compaction or retention limits configured. | Resolved |
| K18 | **`make k8s-bootstrap` applies a deleted file** | `Makefile:126` runs `kubectl apply -f k8s/bootstrap/root-app.yml`, removed in `7742cb0`. Nothing applies `k8s/bootstrap/applicationsets/`. The documented rebuild path -- step 1 of the DR runbook -- fails on its first command. | Critical |
| K19 | **Media share and cluster storage share were the same NFS export** | Every *arr container mounted the export root, so qBittorrent could read and write Vault's storage, the MinIO bucket holding Velero backups, Loki, Prometheus and Authentik's database. Fixed by moving the media tree into a `library/` subdirectory and repointing the `arr-data` PV at it; container paths are unchanged, and the dynamic PVC directories are now outside the mount. The provisioner root is deliberately left at `.data` so existing PVs keep their immutable paths. | Resolved |
| K20 | **ArgoCD's pinned CA certificate expired** | `k8s/bootstrap/argocd/custom-ca.yml` embeds a literal PEM (`CN=homelab-ca`, 90-day validity, issued 2026-03-23, expired 2026-06-21) mounted into `argocd-server`. cert-manager rotates the real CA; this copy does not follow. No x509 errors appear in current `argocd-server` logs, so the impact is latent -- it surfaces the next time ArgoCD must validate a `*.homelab.local` certificate. | Medium |
| K21 | **The *arr apps are not behind SSO, and the docs say they are** | `docs/architecture/auth.md` describes nginx-ingress `auth_request` forward-auth protecting Sonarr, Radarr, Prowlarr and qBittorrent. The cluster runs `gatewayClassName: cilium` and contains no `nginx.ingress.kubernetes.io/*` annotation. Every *arr UI is open on the LAN. | High |
| K22 | **CI never renders manifests** | `validate.yml` runs kubeconform over individual files but ignores `config.yml` and `values.yml` -- the only two file types the ApplicationSet consumes -- and never runs `kustomize build`, `helm template`, or the Kyverno CLI. K18, K23 and K26 would all have been caught by a render job. | High |
| K23 | **Renovate proposes no Helm chart bumps** | Renovate's `argocd` manager only reads YAML whose `kind` is `Application`/`ApplicationSet`. Since the ApplicationSet migration, chart versions live in schema-less `config.yml` files no manager matches. ~30 chart versions are silently hand-maintained. | High |
| K24 | **No dependency ordering between Applications** | The applicationset-controller creates Application objects directly with no parent Application syncing them, so `argocd.argoproj.io/sync-wave` on a generated Application is inert -- including the one in `local-path-provisioner/config.yml`. Ordering is `retry: limit 10` plus luck. | Medium |
| K25 | **Recyclarr had never synced** | Both the Sonarr and Radarr instance were named `main`; Recyclarr v8 requires instance names unique *across* services and silently discards the whole file, exiting 0. Compounding it: 33 fabricated `trash_id`s (valid-looking, wrong suffixes; several cross-wired to the wrong streaming service), a missing `qualities:` block that v8 requires when creating a profile, and a stale API key. Sonarr and Radarr now hold 31 and 43 custom formats and both quality profiles exist. | Resolved |
| K28 | **The control-plane node could not create new pods** | systemd on `homelabk8s01-node-1` had lost its D-Bus name registration, so every pod sandbox failed with `Failed to activate service 'org.freedesktop.systemd1': timed out` and `sshd` was dead. `systemctl` and `SIGTERM` to PID 1 both failed to recover it; the node had been up 122 days and a cluster of core units had restarted on 2026-05-29. Resolved by a hard power-cycle via Proxmox after taking an etcd snapshot; etcd came back clean and the cluster settled in 50s. | Resolved |
| K29 | **etcd backups stopped for 61 days and nothing surfaced it** | The CronJob is pinned to the control plane and could not schedule (K28). `EtcdBackupStale` fired correctly throughout, but Alertmanager could deliver nothing (K30), so no human saw it. Backups resumed 2026-08-02. The lesson stands: K16 was marked Resolved while the mechanism was silently dead for two months. | Resolved |
| K30 | **Alertmanager delivery was silently broken** | Every notification failed with `connect: operation not permitted` to the `openclaw` webhook receiver. Not a policy denial: Cilium's socket-LB returns `EPERM` when a ClusterIP has zero ready backends, and OpenClaw was CrashLoopBackOff (its image needed a writable `/home/node/.npm`). Because that receiver sits in the shared route tree, its retry exhaustion suppressed delivery for every alert. Both integrations were failing at ~99.8% for 121 days. Now fixed, with an external healthchecks.io heartbeat receiving the Watchdog alert every minute, so a future delivery outage surfaces from outside the cluster. Critical alerts also repeat hourly instead of 4-hourly. | Resolved |
| K26 | **Seerr's HTTPRoute is dead code** | `apps/arr/seerr/httproute.yml` is in Git and passes CI but is listed in no `kustomization.yml`, and `values.yml` sets `route.main.enabled: false`. Nothing creates the route. | Medium |
| K27 | **Unpackerr is a silent no-op** | It has been returning `401` from both Sonarr and Radarr continuously for 16+ weeks -- the API keys in `unpackerr-secrets` no longer match the ones the apps generated, which is C1 manifesting in production. Separately, `UN_SONARR_0_PATHS` / `UN_RADARR_0_PATHS` are unset and default to `/downloads`, a path the pod does not mount, and it runs as UID 1000 against a share that squashes to 977:988. All three must be fixed for it to do anything. | High |

### Configuration Layer

Runtime state that lives inside an application's own database rather than in Git. Recorded only as prose in `docs/apps/*.md` "Post-Deploy Setup" sections -- roughly 120 individual settings across 18 categories.

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| C1 | **\*arr API keys are self-generated and hand-copied into Vault** | Sonarr, Radarr, Prowlarr and Bazarr each generate a key into `/config/config.xml` on first boot. Eight consumers depend on those keys, so a cold rebuild deadlocks until a human visits four web UIs. Blocks every other item in this table. | Critical |
| C2 | **Prowlarr indexer definitions and private-tracker passkeys exist only in SQLite** | The least reproducible state in the homelab. Some passkeys cannot be re-obtained without contacting a tracker. | Critical |
| C3 | **Prowlarr's app-sync to Sonarr/Radarr is manual** | Without it, indexers added to Prowlarr never reach Sonarr or Radarr and the centralised-indexer benefit evaporates. | High |
| C4 | **Sonarr/Radarr root folders and download-client wiring are click-ops** | Neither app will accept a series or movie without a root folder, and nothing creates the directories they point at. | High |
| C5 | **Jellyfin's setup wizard, admin account, libraries and hardware transcoding are manual** | The entire GPU path is codified -- Proxmox PCI mapping, node selector, device plugin -- except the one setting that makes Jellyfin use it. | High |
| C6 | **Bazarr, Seerr, qBittorrent and Tdarr configuration is entirely UI state** | Subtitle providers, language profiles, service registrations, download categories, and a 10-node transcode flow graph. | High |
| C7 | **Authentik providers, applications, outposts and OAuth2 client secrets are 12 UI steps** | The longest post-deploy procedure in the repo. Client secrets are generated in the UI and hand-copied into Vault, inverting the intended direction. | High |
| C8 | **Uptime Kuma's admin account, 18 monitors and status page are hand-created** | Its API is socket.io-only with no supported REST write path, making the monitoring-of-last-resort the least reproducible app in the repo. | Medium |
| C9 | **NAS export layout and the media directory tree are undocumented manual setup** | `shared-data-pv.yml` hardcodes a volume UUID that will differ on any replacement NAS, and nothing creates `/data/media/{movies,tv,music}`. | Medium |

### Media Platform

Gaps measured against the goal of replacing streaming subscriptions rather than against infrastructure correctness.

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| M1 | **Acquisition is torrent-only** | A single gluetun + qBittorrent pod dependent on swarm health and on PIA continuing to forward a port. For back catalogue and non-English content this is where a request fails -- and a failed request is what sends a household back to streaming. | High |
| M2 | **Nothing works off-LAN** | Jellyfin is a LoadBalancer behind a self-signed CA at `jellyfin.homelab.local`. Family cannot watch anywhere, and TV clients will not accept a private CA. | High |
| M3 | **No retention policy against a hard capacity ceiling** | `shared-data-pv.yml` declares `capacity: 10Ti` against one 8 TB drive; NFS PVs enforce no quota, so nothing warns before writes fail. Nothing deletes anything, and media is deliberately excluded from backup. | High |
| M4 | **No library-freshness mechanism** | Media lives on NFS and inotify does not work across NFS, so Jellyfin's real-time monitor is unreliable -- imports appear only on scheduled scans. | Medium |
| M5 | **No household UX layer** | No watch analytics, no invites, no collections, no resume continuity, and none of the free Jellyfin plugins (Intro Skipper, TMDB Box Sets, Playback Reporting, Trakt) installed. | Medium |
| M6 | **Transcode policy is contradictory and unstated** | `recyclarr/configmap.yml` scores `x265 (HD)` as unwanted on both profiles while Tdarr is deployed to transcode. If Tdarr targets HEVC it manufactures exactly the files Recyclarr rejects, plus a generation of quality loss. | Medium |

## Gap-to-Phase Mapping

| Gap | Addressed In |
|-----|-------------|
| P2 | [Phase 1 -- Foundations](phase-1-foundations.md) |
| K3, K9, K11, K15, N6 | [Phase 2 -- Kubernetes Hardening](phase-2-kubernetes-hardening.md) |
| P3, N3, N4, N5, M2 | [Phase 3 -- Network](phase-3-network.md) |
| P4, K1, K4 | [Phase 4 -- Compute & Storage](phase-4-compute-and-storage.md) |
| K10, K14, K8 | [Phase 5 -- Observability](phase-5-observability.md) |
| K12, K13 | [Phase 6 -- Platform Engineering](phase-6-platform-engineering.md) |
| P5, N2 | [Phase 7 -- Long-Term Vision](phase-7-long-term-vision.md) |
| C1--C9, K18--K27, K30, M1, M3--M6 | [Phase 8 -- Configuration as Code](phase-8-configuration-as-code.md) |
