# Assessment

The homelab supports a household media platform and a practical infrastructure learning environment. This assessment tracks the current capabilities, constraints and remaining work behind the [roadmap](index.md).

Provisioning is encoded in Packer, Ansible and Terraform; ArgoCD reconciles application and infrastructure resources; Vault supplies secrets; and metrics, logs, backups and media configuration are managed in Git. The next step is to prove that these pieces rebuild and restore together, then use that environment to upgrade the platform.

**Status convention:** Implemented means the configuration exists in the repository. A restore, upgrade or application outcome is complete only after its acceptance check succeeds. Operational checks remain open where evidence is still needed.

All three production nodes are Ready and all 53 ArgoCD Applications are Synced/Healthy. The [isolated restore lab](../runbooks/restore-lab.md) has two Ready nodes, a tested reboot and repeatable bootstrap, distinct node identities and verified network isolation. Offsite application recovery remains unverified: completed Velero backups contain warnings, and a successful backup does not prove the data can be restored.

## Physical Layer

The additional drives, 10G equipment and compute hosts are planned purchases. They remain valuable projects but do not block the immediate software work.

| IDs | Current assessment | Next step |
|---|---|---|
| P1, P7 | UPS/NUT configuration and monitoring are implemented. | Verify USB stability, alert delivery and orderly shutdown in [Phase 1](phase-1-foundations.md) |
| P2 | The NAS has one documented data drive. Active NFS data, local backup copies and media share that failure domain. | Planned hardware: add the [two-drive mirror](phase-1-foundations.md#11-add-nas-drive-redundancy) and prove an independent restore |
| P3 | The MS-01's 10G SFP+ ports are available; its current GbE path limits storage and inter-host transfers. | [Phase 3](phase-3-network.md): 10G switch and DAC links |
| P4 | All three Kubernetes VMs share one Proxmox host. | [Phase 4](phase-4-compute-and-storage.md): second MS-01 and workload distribution |
| P5 | The MS-01's PCIe slot is available for expansion. | [Phase 7](phase-7-long-term-vision.md): dedicated GPU, subject to fit, power and cooling |
| P6 | Intel AMT is provisioned in firmware; the management-port connection remains a task. | Complete the connection and test access with the host OS unavailable in [Phase 3](phase-3-network.md#35-complete-intel-amt-connectivity) |

## Network Layer

| IDs | Current assessment | Next step |
|---|---|---|
| N1, N7 | VLAN 99 and management access are configured. Management-service isolation still needs an endpoint-by-endpoint check. | Test Proxmox, NAS and AMT reachability from management clients and ordinary workloads; close unintended paths |
| N2 | A dedicated IoT VLAN is planned for smart home devices. | [Phase 7](phase-7-long-term-vision.md), when those devices are added |
| N3 | Internal DNS records and Gateway address allocations are manual. | Record recoverable allocations and select a supported DNS automation path in [Phase 3](phase-3-network.md#33-automate-internal-dns) |
| N4 | WireGuard and Teleport are implemented with Homelab and Management access. | Record an off-LAN DNS, TLS, login and management-access check |
| N5, M2 | VPN provides private remote access. Public Jellyfin access remains planned for clients that cannot use a VPN. | Choose and test the intended client experience in [Phase 3](phase-3-network.md#34-plan-external-access-for-jellyfin) |
| N6 | Cilium egress policies cover selected namespaces and destinations. | Inventory coverage and required traffic before tightening policies |
| N8 | The configured Cilium pool, `10.0.0.0/8`, contains the Kubernetes service range, `10.96.0.0/12`. | Inventory production and routed/VPN ranges, then rehearse the production migration using the lab's verified non-overlapping ranges |

## Kubernetes / Software Layer

| IDs | Current assessment | Next step |
|---|---|---|
| K1, K4 | One control plane and standalone Vault are single-instance dependencies. | [Phase 4](phase-4-compute-and-storage.md): three members and tested failover; a 2+1 placement across two hosts cannot survive loss of either host |
| K2, K34 | Kyverno policies enforce regular/init-container requirements, with explicit infrastructure exceptions. | Verify rendered-workload coverage, real admission outcomes and necessary exceptions in [Phase 2](phase-2-kubernetes-hardening.md) |
| K3, K9 | Namespace budgets are not measured; singleton PDBs and node-local state constrain maintenance. | Size quotas from observed demand, document singleton drain procedures and spread eligible multi-replica services |
| K5, K16, K29, K31, K36 | Etcd snapshots and local/offsite Velero schedules are implemented, including distinct S3 prefixes and control-plane node-agent coverage. | Inspect backup warnings and excluded volumes, prove recovery from S3 without the original NAS, and test backup-age/failure alerts in [Phase 1](phase-1-foundations.md) |
| K6, K21, K26 | Authentik uses PostgreSQL; proxy/OIDC configuration and application routes are represented in Git. | Verify empty-database login and the documented emergency-access procedure |
| K7, K17, K37 | Prometheus uses local-path with time/size retention; Loki has explicit retention. Prometheus history is disposable. | Measure disk headroom including Prometheus WAL/head data outside the block-retention ceiling |
| K8, K10, K12, K13 | HPA, tracing, chaos tooling and admission-time signature verification remain planned. | [Phases 5](phase-5-observability.md), [6](phase-6-platform-engineering.md) and [7](phase-7-long-term-vision.md) |
| K11 | Images are drawn from multiple registries without an admission allowlist. | Inventory dependencies and introduce a tested registry policy in [Phase 2](phase-2-kubernetes-hardening.md) |
| K14 | Capacity, namespace and Exportarr dashboards are in Git; chart dashboards are provisioned. | Export useful remaining UI-created dashboards and verify an empty Grafana database |
| K15, K32, K35, K43 | Certificate readiness/expiry, missing metrics, external heartbeat, OOM and slow-restart alerts are implemented. | Test failure and missing-series cases through external delivery in [Phase 5](phase-5-observability.md) |
| K18 | Shared provisioning variables, template sanitization, Cilium prerequisites and ordered bootstrap are encoded. Packer owns the default Kubernetes template. | Build a fresh clone and isolated cluster; prove host identity, node join and bootstrap without preexisting resources |
| K19 | The media PV mounts a library subdirectory outside the dynamic-storage directories. | Verify NAS export permissions and directory ownership independently |
| K20 | A long-lived CA and trust-manager distribute public CA trust to in-cluster consumers. | Rehearse CA restoration/rotation and verify client reload behavior |
| K22 | CI validates ApplicationSet contracts, rendered manifests, pinned CRD schemas, admission fixtures and operational scripts. | Use the same checks for the isolated rebuild; runtime behavior remains an acceptance check |
| K23 | Renovate extracts HTTP and OCI chart versions from ApplicationSet configuration files. | Confirm scheduled discovery and resulting update PRs |
| K24, K39 | ArgoCD Applications reconcile independently. Bootstrap ArgoCD/ApplicationSet resources are manually applied; generated Application sync waves do not order their workloads. | Use the explicit bootstrap/drift commands and prove convergence from an empty cluster |
| K25, K27 | Recyclarr and Unpackerr use shared API-key references; their configuration includes writable state, download paths and NAS-compatible identity. | Verify successful configuration sync and processing against fresh and restored application state |
| K30 | Slack/webhook delivery and an external heartbeat are configured. | Exercise receiver downtime and confirm independent detection of a failed delivery path |
| K33, K41 | SQLite/native dumps bridge local-path application data into mounted NFS volumes for Velero. Recovery procedures include etcd tool compatibility and Vault/NFS bootstrap dependencies. | Inventory every application's data, test database/native archive consistency and restore retained state; set explicit recovery-point and recovery-time targets |
| K38 | Retained NFS PV directories can be reused by claim name. | Map each directory to all current PV references before reclaiming storage; a Released PV alone does not establish unused data |
| K40 | Gateway TLS depends on Cilium's propagation of the referenced certificate Secret. | Test certificate replacement and confirm the certificate actually served to clients |
| K42 | Local-path PVC sizes do not enforce quotas or expose the same capacity series as CSI/NFS volumes. | Add per-directory usage visibility and node-disk headroom alerts |
| K44 | Memory limits need peak-demand, OOM and node-headroom evidence. | Tune from representative workloads; avoid blanket increases based on percentage-of-limit alone |
| K45 | The cluster and provisioning configuration use Kubernetes 1.31.4, an unsupported release line. | After the rebuild/restore lab, rehearse sequential minor upgrades and a fresh node join using [Phase 2](phase-2-kubernetes-hardening.md#21-upgrade-the-unsupported-platform) |
| K46 | Sensitive API audit events are metadata-only; Alloy has pod-log permissions and node-scoped discovery. | Verify new logs omit credential bodies, records are collected once, and retained logs have appropriate access controls |
| K47 | OpenClaw has read access without Secrets/exec and named Deployment-scale permissions for autonomous remediation. | Finish the node-write denial check in [Phase 2](phase-2-kubernetes-hardening.md), then test Slack pairing and rejection of unauthenticated hooks in [Phase 6](phase-6-platform-engineering.md#65-scoped-autonomous-operations) |
| K48 | Vault helpers use CAS-protected secret creation and own their port-forward processes; regression tests cover failures and literal values. | Exercise the helpers during isolated credential bootstrap and rotation |
| K49 | Provisioning and backup credentials, TLS trust and floating tool/runtime versions need a complete inventory. S3 versioning and Terraform deletion guards do not make backups immutable. | Reduce broad credentials, establish trusted provisioning endpoints and choose backup retention/deletion controls |

## Configuration Layer

Seven media-operator chart configurations and eight media Config resources are present, alongside Recyclarr and Authentik blueprints. Remaining work is to prove initial configuration, secret dependencies and restoration of valuable runtime state.

| IDs | Current assessment | Next step |
|---|---|---|
| C1 | Sonarr/Radarr/Prowlarr API-key injection and shared Vault references are implemented. Bazarr and other first-boot credentials need a tested adoption/bootstrap path. | Rebuild without preexisting application databases |
| C2, C3 | Prowlarr indexers, application sync and secret references are declared. | Escrow tracker secrets and prove reconciliation after restore |
| C4 | Sonarr/Radarr root folders and download wiring are declared. | Prepare NAS directories and resolve quality-profile identity on a fresh database |
| C5 | Jellyfin admin bootstrap, libraries and QSV encoding are declared. | Verify initial setup, permissions and actual hardware-assisted playback |
| C6 | Bazarr, Seerr, qBittorrent and Tdarr Config resources are implemented. | Test generated payloads and secret dependencies against the pinned applications |
| C7 | Authentik providers, applications and outpost associations are blueprinted. | Bootstrap the administrator and secrets, then test OIDC/proxy login on an empty database |
| C8 | Blackbox Probe resources provide a Git-managed monitor inventory. Uptime Kuma retains separate UI/status state. | Verify synthetic checks and back up retained status-page configuration |
| C9 | NAS paths and volume identity are site-specific inputs; host and application NFS mounts serve different purposes. | Rehearse directory preparation and path migration on replacement storage |

See [Phase 8](phase-8-configuration-as-code.md) for the bootstrap and media acceptance tasks.

## Media Platform

| ID | Current assessment | Next step |
|---|---|---|
| M1 | Acquisition is torrent-only, with Gluetun providing a native-sidecar startup gate. | Verify tunnel-loss and forwarded-port behavior; evaluate Usenet as an additional acquisition path |
| M2 | VPN access exists; public Jellyfin access is planned. | Test the intended remote-client experience before choosing ingress |
| M3 | There is no automatic retention policy; declared NFS PV capacity is not a quota. | Measure capacity and alert headroom; develop retention rules in dry-run |
| M4 | NFS-backed libraries need a reliable import-to-library refresh path. | Add supported notifications/API refresh and retain periodic scans as fallback |
| M5 | Household enhancements include invites, watch analytics, collections and playback plugins. Watch/resume/request state is valuable data. | Prove request-to-playback and state recovery, then add the desired UX improvements |
| M6 | [ADR-019](../decisions/019-transcode-policy.md) preserves video while allowing audio/container processing. | Verify Tdarr flows and quality-profile assignments against that policy |
