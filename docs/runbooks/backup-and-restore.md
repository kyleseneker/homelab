# Backup & Restore

This runbook covers backup schedules, manual backup procedures, and restore operations using Velero with MinIO (local) and AWS S3 (offsite) as storage backends.

## Automated Backup Schedules

Velero runs three automated backup schedules:

| Schedule | Scope | Retention | Time | Target |
|----------|-------|-----------|------|--------|
| `daily-stateful` | `arr`, `monitoring`, `auth`, `openclaw` namespaces | 7 days | 3:00 AM daily | MinIO (local) |
| `weekly-full-cluster` | All except `kube-system`, `kube-public`, `nfs-provisioner`, `backups` | 30 days | 4:00 AM Sunday | MinIO (local) |
| `weekly-offsite` | `arr`, `monitoring`, `auth`, `openclaw`, `argocd`, `vault`, `external-secrets` | 30 days | 5:00 AM Sunday | AWS S3 (offsite) |

Times are UTC. The schedules capture Kubernetes objects and eligible mounted volume data through Kopia. Offsite is a selected recovery set, not a copy of the local schedule; it excludes the MinIO backup store to avoid copying local archives again. Local-path data requires the separate dump/restore procedure below.

!!! info "Offsite backup"
    The `weekly-offsite` schedule writes to an S3 bucket (`velero-offsite-homelab`) in AWS us-east-1. Objects are stored in S3 Standard and transitioned to Standard-IA after 30 days via lifecycle policy. Storage, request, and restore charges depend on actual retained data and must be measured.

!!! note
    The `kube-system` and `kube-public` namespaces are excluded from backups because their resources are managed by kubeadm and ArgoCD. These are recreated during a cluster rebuild rather than restored from backup.

## etcd Snapshots

A separate CronJob backs up the etcd database directly. Velero cannot back up or restore etcd — it operates at the Kubernetes API layer and requires a running API server. etcd snapshots are the only way to recover a cluster whose control plane is corrupted or unrecoverable.

| Schedule | Retention | Local Storage | Offsite Storage |
|----------|-----------|---------------|-----------------|
| 2:00 AM daily | 7 snapshots | NFS PVC (`etcd-snapshots`) | S3 (`velero-offsite-homelab/etcd-snapshots/`) |

The CronJob runs on the control plane using pod networking and the node IP (`status.hostIP`) on TCP 2379. It uses the matching kubeadm etcd tool version, then pairs the snapshot with a PKI archive. Root-owned artifacts have group-read permission for the non-root uploader, which sends both to S3. The CronJob explicitly uses UTC.

### Checking etcd Backup Status

```bash
kubectl get cronjob -n backups etcd-backup
kubectl get jobs -n backups -l app.kubernetes.io/name=etcd-backup --sort-by=.status.startTime
```

### Manual etcd Snapshot

To trigger an immediate backup:

```bash
kubectl create job -n backups etcd-backup-manual --from=cronjob/etcd-backup
```

### Restoring from etcd Snapshot

Follow the single authoritative [etcd restore procedure](disaster-recovery.md#etcd-restore-control-plane-corruption). It preserves the old data directory, uses the original member name/peer URL, and restores with a revision bump and compaction. A failed API server cannot provide `kubectl cp`; retrieve artifacts directly from NAS or S3.

## Manual Backup

### Creating a Backup

```bash
make k8s-backup
```

### Checking Backup Status

```bash
make k8s-backup-status
```

Or use the Velero CLI directly for more detail:

```bash
velero --namespace backups backup get
velero --namespace backups backup describe <backup-name> --details
velero --namespace backups schedule get
```

## Restoring from Backup

### Full Restore

1. List available backups:

    ```bash
    make k8s-restore
    ```

    Or:

    ```bash
    velero --namespace backups backup get
    ```

2. Create a restore from the desired backup:

    ```bash
    velero --namespace backups restore create --from-backup <backup-name>
    ```

3. Monitor the restore progress:

    ```bash
    velero --namespace backups restore get
    velero --namespace backups restore describe <restore-name> --details
    ```

4. Verify pods are running after the restore completes:

    ```bash
    kubectl get pods -n arr
    kubectl get pods -n monitoring
    ```

!!! warning
    A restore does not delete existing resources. If restoring into a cluster that already has running workloads, existing resources that conflict with the backup will be skipped. For a clean restore, use a freshly rebuilt cluster.

### Partial Restore

Restore only specific namespaces:

```bash
velero --namespace backups restore create --from-backup <backup-name> --include-namespaces arr
```

Restore only specific resource types:

```bash
velero --namespace backups restore create --from-backup <backup-name> \
  --include-resources persistentvolumeclaims,persistentvolumes
```

Combine both filters:

```bash
velero --namespace backups restore create --from-backup <backup-name> \
  --include-namespaces arr \
  --include-resources deployments,services,persistentvolumeclaims
```

## Troubleshooting Backups

### Backup Stuck in InProgress

A backup that remains in `InProgress` for longer than expected may indicate an issue with the Velero server or node agent.

```bash
# Check Velero server logs
kubectl logs -n backups -l app.kubernetes.io/name=velero

# Check for errors in the backup description
velero --namespace backups backup describe <backup-name> --details
```

### Node Agent Issues

The node-agent DaemonSet handles file-system-level PVC backups. If PVC data is not being backed up:

```bash
# Verify node-agent pods are running on all nodes
kubectl get pods -n backups -l name=node-agent -o wide

# Check node-agent logs
kubectl logs -n backups -l name=node-agent
```

### S3/MinIO Connectivity

If backups fail with storage-related errors, verify MinIO is running and accessible:

```bash
# Check MinIO pod
kubectl get pods -n backups -l app=minio

# Check MinIO logs
kubectl logs -n backups -l app=minio

# Verify all BackupStorageLocations are available
velero --namespace backups backup-location get
```

A `BackupStorageLocation` in `Unavailable` status indicates that Velero cannot reach the storage endpoint. Check the service, credentials, and network connectivity.

### Offsite (AWS S3) Connectivity

If the `offsite` BackupStorageLocation shows `Unavailable`:

1. Verify the `velero-offsite-credentials` Secret exists and is synced:

    ```bash
    kubectl get externalsecret -n backups velero-offsite-credentials
    ```

2. Verify the Cilium network policy allows egress to S3:

    ```bash
    kubectl get ciliumnetworkpolicy -n backups backups-egress -o yaml
    ```

3. Test S3 connectivity from the Velero pod:

    ```bash
    kubectl exec -n backups -it deploy/velero -- \
      wget -qO- --spider https://s3.us-east-1.amazonaws.com
    ```

### Backup Contains No PVC Data

If a restore completes but PVC data is missing:

1. Verify the backup included volume data: `velero --namespace backups backup describe <backup-name> --details`
2. Check that the pod volumes are annotated for backup or that the `defaultVolumesToFsBackup` flag is set in the Velero schedule
3. Confirm that node-agent pods were running and healthy at the time of the backup

## Restoring Local-Path Application Databases

The `arr-config-backups` and `uptime-kuma-backups` PVCs hold staged database dumps. Velero restores those NFS volumes; it does not automatically install dumps into the applications' local-path PVCs.

1. Pause GitOps reconciliation for the target workload and stop its writer. For a drill, use an isolated namespace, fresh PVCs, and disabled ingress/notifications; do not map a test pod to the production NFS path or local PV.
2. Restore the backup-holder volume into the isolated target, confirm the relevant PodVolumeRestore completed, and inspect the dump timestamp/size. A successful Backup object alone is insufficient.
3. Run `PRAGMA integrity_check` on SQLite dumps. Preserve the destination database and its `-wal`/`-shm` files together, then install the dump with the application's expected UID/GID. Never leave old WAL/SHM files next to a restored database; move them into the rollback directory while the app is stopped.
4. Restore non-database configuration from a known backup or recreate it from Git/Vault. SQLite dumps do not include the entire application directory. For Tdarr, use its native archive restore workflow; the copy job rejects corrupt archives and archives older than 48 hours.
5. Start the app and verify login, representative records, and integration/API credentials before resuming GitOps. Retain the rollback copy until validated.

Record the source backup, dump age, target volume mapping, integrity result, and an actual application-level read. A monthly isolated restore drill is still required; schedules and holder pods alone do not demonstrate recoverability.
