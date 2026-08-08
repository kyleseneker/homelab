# etcd Backup

Velero backs up Kubernetes API resources, not etcd itself. This CronJob takes a nightly etcd snapshot plus a tarball of the control-plane PKI, writes both to NFS, and uploads them to S3.

## Details

| Field | Value |
|-------|-------|
| Type | CronJob (`sourceType: git`) |
| Namespace | `backups` |
| Schedule | `0 2 * * *` (2:00 AM daily) |
| Concurrency | `Forbid` |
| Local target | `etcd-snapshots` PVC (`nfs-client`, 1Gi) |
| Offsite target | `s3://velero-offsite-homelab/etcd-snapshots/` |
| Credentials | `etcd-backup-credentials` (ExternalSecret, `infrastructure/etcd-backup`) |

## How It Works

The job runs three containers in sequence, pinned to the control-plane node with a matching toleration:

1. **`snapshot`** -- `etcdctl snapshot save` against the local etcd endpoint using the kubeadm PKI mounted read-only from the host. Runs as root because the PKI is root-owned.
2. **`prepare`** -- timestamps the snapshot and tars `/etc/kubernetes/pki`. A snapshot without the matching CA material cannot rebuild a control plane, so the two are always produced together.
3. **`upload-offsite`** -- `aws s3 cp` of both artifacts to the S3 prefix.

!!! warning "The S3 prefix matters to Velero"
    These artifacts share a bucket with Velero's offsite backup storage location. Velero refuses a bucket containing unknown top-level directories, which is why the offsite BSL is configured with a `velero` prefix. Do not remove that prefix or move these snapshots to the bucket root.

## Failure Modes

The job is pinned to the control-plane node. If that node is unschedulable, the job does not run -- it does not fail, it simply never fires. `EtcdBackupStale` is the alert that covers this, and it is the only signal that the mechanism has stopped.

## Restore

See [Disaster Recovery &rarr; etcd Restore](../runbooks/disaster-recovery.md#etcd-restore-control-plane-corruption). Note that `etcdctl snapshot restore` was removed in etcd 3.6; restore uses `etcdutl`, which ships in the same image.

## Upstream Documentation

<https://etcd.io/docs/latest/op-guide/recovery/>
