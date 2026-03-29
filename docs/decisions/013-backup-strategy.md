# ADR-013: Backup Strategy

## Status

Accepted

## Context

The cluster needs a backup strategy that protects against accidental deletion, data corruption, and site-level disaster. Backups must cover three distinct layers: Kubernetes resource manifests, persistent volume data, and the etcd database. The 3-2-1 rule requires at least three copies on two media types with one offsite.

These layers require two separate backup mechanisms. Velero operates at the Kubernetes API layer — it can back up manifests and PVC data but requires a running API server and cannot snapshot etcd. An etcd snapshot can bootstrap a cluster from nothing but knows nothing about application data. Every major Kubernetes distribution (OpenShift, Rancher, RKE2, Gardener) maintains separate pipelines for these two concerns. On a single control-plane kubeadm cluster, etcd corruption without a snapshot means a full cluster rebuild.

## Decision

Two backup pipelines, both storing data locally on the NAS for fast recovery and offsite in AWS S3 for disaster recovery:

**Velero** handles application-layer backups. It uses the AWS plugin for S3-compatible storage, Kopia for file-system PVC backup, and two storage targets: standalone MinIO on an NFS-backed PVC for local backups, and an S3 bucket (`velero-offsite-homelab`) in us-east-1 for offsite copies. Three schedules run nightly: daily stateful namespaces (7-day retention), weekly full-cluster (30-day retention), and weekly offsite (30-day retention).

**A CronJob** handles etcd snapshots. It runs `etcdctl snapshot save` daily at 2:00 AM on the control plane node, stores snapshots on an NFS-backed PVC with 7-snapshot retention, and uploads each snapshot to the same S3 bucket under an `etcd-snapshots/` prefix.

## Alternatives Considered

- **NFS snapshots only**: Covers data but not Kubernetes resource state (Secrets, ConfigMaps, RBAC). Restoration requires manual re-creation of all cluster resources.
- **Restic/Kopia standalone**: Can back up PVC data but doesn't handle Kubernetes resource backup or integrate with `kubectl`-style restore workflows.
- **Backblaze B2**: Cheaper storage ($0.006/GB/month) but adds another vendor dependency. AWS was chosen because the account and IAM infrastructure already exist for Vault KMS auto-unseal.
- **Longhorn/Rook volume snapshots**: Require distributed storage (see ADR-006). Not applicable with NFS.
- **Kasten K10**: Can orchestrate both Velero-style and etcd backups via Kanister blueprints. Heavyweight and commercial — overkill for a homelab.
- **Velero for etcd**: Not possible. Velero requires a running API server and cannot snapshot or restore etcd. Confirmed by upstream maintainers.
- **adfinis/kubernetes-etcd-backup Helm chart**: Handles snapshot scheduling and local retention but does not support offsite upload. A custom CronJob provides the same functionality with S3 upload included.

## Rationale

- **Two pipelines by design**: etcd snapshots solve "the cluster is dead" scenarios; Velero solves "I deleted a namespace" scenarios. These are fundamentally different recovery paths that cannot be unified without fragility.
- **Every layer local + offsite**: Both Velero and etcd snapshots land on the NAS (fast restore) and S3 (disaster recovery). Consistent storage strategy across both pipelines.
- **In-cluster S3 via MinIO**: Provides S3-compatible storage without cloud dependency. Velero's AWS plugin works unmodified against MinIO. NFS-backed PVC with Retain policy ensures backup data survives cluster rebuilds.
- **Resource + volume data**: Velero backs up both Kubernetes manifests and PVC data via Kopia file-system backup, providing a complete application-layer snapshot.
- **Three Velero schedules**: Daily backups for stateful namespaces catch frequent changes. Weekly full-cluster and offsite backups provide broader coverage with longer retention.
- **AWS S3 Standard-IA lifecycle**: Objects transition from S3 Standard to Standard-IA after 30 days. Noncurrent versions expire after 90 days. Cost is ~$1/month.
- **Selective restore**: Velero supports namespace-scoped and resource-scoped restores, allowing targeted recovery without affecting the rest of the cluster.
- **Reuse existing AWS account**: The account, IAM patterns, and Terraform module already exist for Vault KMS auto-unseal. Adding an S3 bucket and IAM user follows the same pattern.

## Consequences

- Two backup mechanisms to operate and monitor. PrometheusRules alert on both Velero schedule failures and etcd snapshot staleness.
- Offsite backups add a runtime dependency on AWS S3 availability and internet egress. Cilium network policy allows HTTPS egress (0.0.0.0/0:443) from the backups namespace.
- AWS credentials are stored in Vault and synced via ExternalSecret. During a DR rebuild where Vault is not yet available, credentials must be manually created from a password manager.
- Velero restore may conflict with ArgoCD's desired state. ArgoCD sync should be verified after any restore.
- The `vault-aws-kms` Secret is not backed up by Velero and must be manually created before Vault can start during disaster recovery.
- The etcd-backup CronJob requires `hostNetwork: true` and `hostPath` access to `/etc/kubernetes/pki/`. This bypasses Cilium network policies.
- The CronJob backs up the full control plane PKI alongside each etcd snapshot. Both are required for disaster recovery on a replacement node.
