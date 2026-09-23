# etcd Backup

Velero backs up Kubernetes API resources, not etcd itself. This CronJob takes a nightly etcd snapshot, matching PKI and control-plane host configuration. It writes a checksummed recovery set to NFS and publishes it to S3 only after downloading and verifying every artifact.

## Details

| Field | Value |
|-------|-------|
| Type | CronJob (`sourceType: git`) |
| Namespace | `backups` |
| Schedule | `0 2 * * *` (02:00 UTC daily) |
| Concurrency | `Forbid` |
| Local target | `etcd-snapshots` PVC (`nfs-client`, 1Gi) |
| Offsite target | `s3://velero-offsite-homelab/etcd-snapshots/` |
| Retention | Seven completed sets; legacy snapshot/PKI pairs retained until seven full sets exist |
| Deadline | 15 minutes per Job |
| Credentials | `etcd-backup-credentials` (ExternalSecret, `infrastructure/etcd-backup`) |

## How It Works

The job runs three containers in sequence, pinned to the control-plane node with a matching toleration:

1. **`snapshot`** -- `etcdctl snapshot save` against the host IP on port 2379 using
   the kubeadm PKI mounted read-only. It writes into a per-Pod working volume,
   keeping concurrent manual Jobs and retries separate.
2. **`prepare`** -- creates three artifacts with one timestamp: `snapshot-*.db`,
   `pki-*.tar.gz` and `control-plane-*.tar.gz`. The configuration archive contains
   the four static-pod manifests, controller-manager and scheduler kubeconfigs,
   kubeadm configuration, audit policy, kubelet configuration/flags, containerd
   configuration, hostname and OS release. Host inputs are mounted read-only.
   The archive includes controller client credentials; protect it like the PKI.
   A `recovery-*.json` manifest records each artifact's size and SHA-256.
3. **`upload-offsite`** -- reads only this Pod's prepared set, checks local hashes,
   uploads each artifact without replacing an existing key, and downloads it to
   verify its bytes. A retry may reuse an existing object only if it matches.
   The completion manifest is uploaded and verified last. A failed read-back never
   publishes that marker or starts offsite pruning.

Snapshot and archive files are mode 0640 in group 1000 so the non-root uploader
can read them. Snapshot tooling is pinned to kubeadm 1.31.4's etcd 3.5.15-0;
the prepare/upload helper uses Python already present in the pinned AWS CLI image.
The helper is delivered by a generated ConfigMap, so its hash is part of the next
Job's Pod specification.

Retention follows completion manifests, keeping seven full sets. Older artifacts,
including legacy snapshot/PKI pairs, become eligible only once seven completed
sets exist. Unfinished newer uploads do not displace successful recovery points.
These are current-object deletions in a versioned bucket; noncurrent-version
retention is controlled separately by the bucket lifecycle.

!!! warning "The S3 prefix matters to Velero"
    These artifacts share a bucket with Velero's offsite backup storage location. Velero refuses a bucket containing unknown top-level directories, which is why the offsite BSL is configured with a `velero` prefix. Do not remove that prefix or move these snapshots to the bucket root.

## Failure Modes

The job is pinned to the control-plane node. If that node is unavailable, the Pod cannot run and the Job eventually reaches its 15-minute deadline. `EtcdBackupStale` detects the absence of a recent successful Job, including when the control plane cannot create scheduled Jobs. A failed upload or read-back leaves the previous completed recovery sets eligible for restore.

## Restore

See [Disaster Recovery &rarr; etcd Restore](../runbooks/disaster-recovery.md#etcd-restore-control-plane-corruption). The pinned `registry.k8s.io/etcd:3.5.15-0` image ships `/usr/local/bin/etcdctl`, not `etcdutl`. Its restore command supports revision bump and compaction; revalidate the image and tooling together during upgrades.

For machine-loss recovery, download the completion manifest and all three named
artifacts into a private directory using independently recovered S3 credentials.
Prepare inputs locally with Python and PyYAML:

```bash
python3 scripts/prepare-etcd-recovery.py \
  --manifest /secure/etcd-backup/recovery-YYYYMMDD-HHMMSS.json \
  --output /secure/etcd-recovery-input
```

The helper rejects mismatched hashes, unsafe archive paths and existing output
folders. It derives component images/arguments and the audit policy from the
backed-up files, without querying a surviving control plane. The original host
configuration remains under the private output's `control-plane/` directory for
review; the helper does not install it or start services. Legacy two-file backups
remain usable for the older drill when their original configuration is available.

The [isolated etcd/API drill](../runbooks/disaster-recovery.md#isolated-etcd-and-api-verification)
restored an offsite snapshot and matching PKI, verified revision bump/compaction,
and read matching object counts through the recovered API. Its optional controller
check passed leader election, scheduling and automatic node-certificate issuance
and registration. A real isolated kubelet/runtime check and a fresh lab worker
rebuild also passed. A [fresh-machine static control-plane boot and reboot](../runbooks/restore-lab.md#native-control-plane-recovery-drill)
also passed from the complete offsite bundle. That drill uses standalone kubelet
for containment. The subsequent [two-node recovery drill](../runbooks/restore-lab.md#node-and-cilium-recovery-drill)
quarantined executable records in the recovered copy, registered fresh nodes, and
verified the production Cilium configuration, DNS, cross-node Services, policy
enforcement and a lab L2 Gateway through node reboots. The [combined drill](../runbooks/restore-lab.md#combined-machine-and-application-recovery-drill)
also restored an offsite qBittorrent volume onto those fresh machines and verified
application state after both node reboots. Other application coverage remains open.

## Upstream Documentation

<https://etcd.io/docs/latest/op-guide/recovery/>
