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
| P1 | **No UPS** | Power event corrupts NVMe mid-write, kills NAS mid-IO, or causes unclean Proxmox/etcd shutdown. | Critical |
| P2 | **Single NAS drive** | One drive failure loses all NFS-backed data: media, app configs, Prometheus, Loki, Vault, Velero backups. | Critical |
| P3 | **Running at GbE when 10G is available** | MS-01 has 2x 10G SFP+ unused. NFS throughput and future live migration bottlenecked at 1 Gbps. USW-16-PoE has 1G SFP only. | Low |
| P4 | **Single compute host** | All VMs on one machine. Hardware failure means total cluster loss. | High |
| P5 | **Unused PCIe x16 slot** | Half-height PCIe 4.0 x16 available for a dedicated GPU, HBA, or NIC. | Informational |
| P6 | **No IPMI/remote management** | MS-01 supports Intel vPro AMT but it is not configured. Hung host requires physical access. | Medium |

### Network Layer

| # | Gap | Risk | Severity |
|---|-----|------|----------|
| N1 | **No dedicated management VLAN** | Proxmox, switch, PDU, and NAS management share VLANs with production or household traffic. | Medium |
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
| K6 | **Authentik Redis unauthenticated** | `auth.enabled: false`. Network policies mitigate but any pod in the auth namespace has access. | Low |
| K7 | **Prometheus TSDB on NFS** | Heavy random I/O on NFS degrades query performance and risks TSDB corruption. | Medium |
| K8 | **No HPA** | Nothing scales horizontally under load. | Low |
| K9 | **No pod topology spread constraints** | Scheduler may co-locate critical services on one node. | Medium |
| K10 | **No distributed tracing** | Debugging cross-service request flows requires manual log correlation. | Low |
| K11 | **No image registry allowlist** | Any registry allowed. No protection against pulls from untrusted sources. | Low |
| K12 | **No chaos testing** | DR runbooks exist but are never automatically validated. | Low |
| K13 | **No supply chain verification** | No cosign signature verification or SBOM generation. | Low |
| K14 | **Grafana dashboards are click-ops** | Dashboards not stored in Git. DR event could lose custom dashboards. | Medium |
| K15 | **No cert-manager health alerting** | cert-manager pod failures or renewal errors are not monitored. | Low |
| K16 | **No etcd snapshot schedule** | Single control plane with no dedicated etcd backup. Velero backs up API resources but an etcd corruption or quorum loss requires a snapshot to restore. | Resolved |
| K17 | **No Loki retention policy** | Logs grow unbounded on NFS. No compaction or retention limits configured. | Medium |

## Gap-to-Phase Mapping

| Gap | Addressed In |
|-----|-------------|
| P1, P2, K5, K16 | [Phase 1 -- Foundations](phase-1-foundations.md) |
| K3, K6, K7, K9, K11, K15, K17, N6 | [Phase 2 -- Kubernetes Hardening](phase-2-kubernetes-hardening.md) |
| P3, N1, N3, N4, N5 | [Phase 3 -- Network](phase-3-network.md) |
| P4, K1, K4 | [Phase 4 -- Compute & Storage](phase-4-compute-and-storage.md) |
| K10, K14, K8 | [Phase 5 -- Observability](phase-5-observability.md) |
| P6, K12, K13 | [Phase 6 -- Platform Engineering](phase-6-platform-engineering.md) |
| P5, N2 | [Phase 7 -- Long-Term Vision](phase-7-long-term-vision.md) |
