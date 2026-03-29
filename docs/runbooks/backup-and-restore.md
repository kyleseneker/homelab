# Backup & Restore

This runbook covers backup schedules, manual backup procedures, and restore operations using Velero with MinIO (local) and AWS S3 (offsite) as storage backends.

## Automated Backup Schedules

Velero runs three automated backup schedules:

| Schedule | Scope | Retention | Time | Target |
|----------|-------|-----------|------|--------|
| `daily-stateful` | `arr`, `monitoring`, `auth` namespaces | 7 days | 3:00 AM daily | MinIO (local) |
| `weekly-full-cluster` | All namespaces (excluding `kube-system`, `kube-public`) | 30 days | 4:00 AM Sunday | MinIO (local) |
| `weekly-offsite` | All namespaces (excluding `kube-system`, `kube-public`) | 30 days | 5:00 AM Sunday | AWS S3 (offsite) |

Both local schedules back up Kubernetes resources and PVC data using file-system-level backup via Kopia. The offsite schedule mirrors the weekly full-cluster backup to AWS S3 Standard-IA in us-east-1 for disaster recovery.

!!! info "Offsite backup"
    The `weekly-offsite` schedule writes to an S3 bucket (`velero-offsite-homelab`) in AWS us-east-1. Objects are stored in S3 Standard and transitioned to Standard-IA after 30 days via lifecycle policy. Estimated cost is ~$1/month for a typical homelab backup set.

!!! note
    The `kube-system` and `kube-public` namespaces are excluded from backups because their resources are managed by kubeadm and ArgoCD. These are recreated during a cluster rebuild rather than restored from backup.

## etcd Snapshots

A separate CronJob backs up the etcd database directly. Velero cannot back up or restore etcd — it operates at the Kubernetes API layer and requires a running API server. etcd snapshots are the only way to recover a cluster whose control plane is corrupted or unrecoverable.

| Schedule | Retention | Local Storage | Offsite Storage |
|----------|-----------|---------------|-----------------|
| 2:00 AM daily | 7 snapshots | NFS PVC (`etcd-snapshots`) | S3 (`velero-offsite-homelab/etcd-snapshots/`) |

The CronJob runs on the control plane node with `hostNetwork: true` to reach the etcd endpoint at `127.0.0.1:2379`. An init container takes the snapshot using `etcdctl`, then the main container uploads it to S3.

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

!!! warning
    Restoring an etcd snapshot replaces the entire cluster state. All changes made after the snapshot was taken will be lost.

1. Copy the snapshot to the control plane node:

    ```bash
    # From local NFS
    kubectl cp backups/<etcd-backup-pod>:/snapshots/snapshot-YYYYMMDD-HHMMSS.db /tmp/snapshot.db

    # Or from S3
    aws s3 cp s3://velero-offsite-homelab/etcd-snapshots/snapshot-YYYYMMDD-HHMMSS.db /tmp/snapshot.db
    ```

2. Stop the API server and etcd (on the control plane node):

    ```bash
    sudo mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/
    sudo mv /etc/kubernetes/manifests/etcd.yaml /tmp/
    ```

3. Restore the snapshot:

    ```bash
    sudo ETCDCTL_API=3 etcdctl snapshot restore /tmp/snapshot.db \
      --data-dir=/var/lib/etcd-restore
    sudo rm -rf /var/lib/etcd
    sudo mv /var/lib/etcd-restore /var/lib/etcd
    ```

4. Restart the control plane:

    ```bash
    sudo mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/
    sudo mv /tmp/etcd.yaml /etc/kubernetes/manifests/
    ```

5. Verify the cluster is healthy:

    ```bash
    kubectl get nodes
    kubectl get pods -A
    ```

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
velero backup get
velero backup describe <backup-name> --details
velero schedule get
```

## Restoring from Backup

### Full Restore

1. List available backups:

    ```bash
    make k8s-restore
    ```

    Or:

    ```bash
    velero backup get
    ```

2. Create a restore from the desired backup:

    ```bash
    velero restore create --from-backup <backup-name>
    ```

3. Monitor the restore progress:

    ```bash
    velero restore get
    velero restore describe <restore-name> --details
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
velero restore create --from-backup <backup-name> --include-namespaces arr
```

Restore only specific resource types:

```bash
velero restore create --from-backup <backup-name> \
  --include-resources persistentvolumeclaims,persistentvolumes
```

Combine both filters:

```bash
velero restore create --from-backup <backup-name> \
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
velero backup describe <backup-name> --details
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
velero backup-location get
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

1. Verify the backup included volume data: `velero backup describe <backup-name> --details`
2. Check that the pod volumes are annotated for backup or that the `defaultVolumesToFsBackup` flag is set in the Velero schedule
3. Confirm that node-agent pods were running and healthy at the time of the backup
