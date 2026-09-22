# Disaster Recovery

Choose recovery based on what survived. An etcd restore recovers the old Kubernetes control-plane state, but does not recover application volume data. A fresh cluster with Velero restores is a separate path; do not run `kubeadm init` over an etcd recovery in progress.

## Complete Cluster Rebuild

### Prerequisites

Keep these outside Kubernetes and Vault itself:

- This repository, Ansible vault password, Terraform/PVE credentials, and access to replacement compute/storage.
- Vault root/recovery material, the original AWS KMS key ID, and working credentials permitted to decrypt with that key.
- AWS offsite credentials in a protected shared-credentials file, and the backup bucket/location/prefix details.
- A tested Vault data backup, application restore records, and recent etcd snapshot/PKI pairs.
- The NAS exports and retained PV directory mappings. MinIO runs **inside Kubernetes** on NFS; it is not a separate NAS service.

KMS auto-unseal decrypts existing Vault storage. It does not reconstruct lost Vault data or initialize a new empty Vault. A live file-system copy of the file storage backend is not evidence of a consistent Vault recovery point; use a quiesced backup. The [manual local restore](backup-and-restore.md#vault-file-backend-recovery) verified storage and KMS auto-unseal; consistent offsite recovery and replacement-cluster authentication remain unverified.

### Procedure

1. Recreate compute and Kubernetes first, leaving ArgoCD bootstrap until recovery dependencies are prepared:

    ```bash
    make k8s-infra
    make k8s-configure
    make k8s-kubeconfig
    export KUBECONFIG="$(pwd)/kubeconfig"
    ```

2. Restore NAS exports or provide replacement NFS storage. If the NAS survived, inventory retained PV paths and rebind the intended directories. Dynamic provisioning creates new directories; `Retain` alone does not reconnect a replacement PVC to its old data. For a local MinIO restore, recover its original data directory and credentials before expecting the bucket to appear.

3. Bootstrap only the storage/backup dependencies needed for recovery, using the pinned versions and values from Git. Keep ordinary workloads and ApplicationSet self-heal/prune paused until their data is restored. Do not wait for all applications to become healthy: Vault → ESO → backup credentials is a circular dependency on a blank cluster.

4. Seed the required bootstrap credentials directly from protected files held outside the cluster. The Vault env file must contain `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `VAULT_AWSKMS_SEAL_KEY_ID`. The Velero file uses AWS shared-credentials format:

    ```bash
    kubectl create namespace vault --dry-run=client -o yaml | kubectl apply -f -
    kubectl create secret generic vault-aws-kms -n vault \
      --from-env-file=/secure/vault-kms.env --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace backups --dry-run=client -o yaml | kubectl apply -f -
    kubectl create secret generic velero-offsite-credentials -n backups \
      --from-file=cloud=/secure/velero-offsite.credentials --dry-run=client -o yaml | kubectl apply -f -
    ```

    Velero's chart also references `velero-cloud-credentials`; provide its original MinIO credential file or a temporary recovery values override that uses only offsite. Recoveries from S3 do not require a healthy MinIO default location. Do not commit bootstrap credential files or capture the generated Secret YAML in logs.

5. Start Velero and its node agents, confirm the offsite location is `Available`, and let it synchronize backup metadata. Recover Vault storage before starting the Vault pod, or rebind its surviving NFS directory. Use the original KMS key, then verify `vault status` reports initialized and unsealed. **Do not run `make vault-init` on data intended for recovery.** If no usable Vault backup remains, explicitly take the full Vault data-loss path below.

6. Re-establish ESO's Kubernetes authentication and policy/binding for the new cluster before relying on Secret synchronization. A recovered Vault may retain old cluster authentication configuration. Confirm ExternalSecrets are ready without printing their contents.

7. Inspect available backup contents and choose a recovery point:

    ```bash
    velero --namespace backups backup get
    velero --namespace backups backup describe <backup-name> --details
    velero --namespace backups backup-location get
    ```

    Select an offsite backup by its storage location in the output. Restore application namespaces selectively into empty targets; review cluster-scoped resources and avoid restoring old PV node affinity or admission/networking resources indiscriminately. Use the local-path database procedure in [Backup & Restore](backup-and-restore.md#restoring-local-path-application-databases). A `Completed` Velero Restore does not copy database dumps into the applications' local PVCs automatically.

8. Validate data and authentication before resuming ArgoCD. Check Vault reads through ESO, application logins, library contents, downloads through VPN, and one representative playback. Re-adopt generated media API keys and validate Seerr profile IDs if application databases were reinitialized. Resume GitOps in stages and inspect drift before allowing prune.

This is a recovery sequence, not a fully automated or demonstrated cold-rebuild procedure. Record the exact recovery overrides and restore outcomes during a drill before considering the roadmap item complete.

## etcd Restore (Control Plane Corruption)

This procedure is for the current **single-member** kubeadm control plane with its original member name/address and PKI intact. If the node is lost, restore its original identity and static-pod configuration before following this path, or use a fresh cluster/Velero restore instead.

1. Obtain the snapshot from NAS or S3 without depending on a working Kubernetes API. On the control-plane host, put it at `/var/tmp/etcd-recovery/snapshot.db` with restrictive permissions. Retrieve the matching PKI tarball if certificates are lost; restore only that PKI after preserving any current files. Do not overwrite working certificates unnecessarily.

2. Record the `--name`, `--initial-advertise-peer-urls`, `--initial-cluster`, `--data-dir`, and image from `/etc/kubernetes/manifests/etcd.yaml`. The pinned kubeadm 1.31.4 default is `registry.k8s.io/etcd:3.5.15-0`; verify the actual manifest before selecting a restore utility. Prepare all artifacts before stopping the API.

3. On the control plane, move all control-plane manifests to a persistent directory **outside** the watched manifest directory. Keep kubelet running so it removes the static pods:

    ```bash
    RECOVERY_DIR="/var/tmp/etcd-recovery-$(date -u +%Y%m%dT%H%M%SZ)"
    sudo mkdir -m 0700 "$RECOVERY_DIR"
    for component in kube-apiserver kube-controller-manager kube-scheduler etcd; do
      sudo mv "/etc/kubernetes/manifests/${component}.yaml" "$RECOVERY_DIR/"
    done
    sudo crictl ps
    ```

    Wait until all four old containers have stopped before touching the data directory. Preserve the printed recovery-directory path for restart/rollback.

4. Verify the snapshot, then restore into a **new** data directory. Set the member variables to the exact values recorded from the original manifest; the values below are placeholders, not commands to paste unchanged:

    ```bash
    ETCD_IMAGE=registry.k8s.io/etcd:3.5.15-0
    ETCD_NAME='<original --name>'
    ETCD_PEER_URL='<original --initial-advertise-peer-urls>'
    ETCD_INITIAL_CLUSTER="${ETCD_NAME}=${ETCD_PEER_URL}"
    sudo test ! -e /var/lib/etcd-restore
    sudo ctr -n k8s.io run --rm \
      --mount type=bind,src=/var/tmp/etcd-recovery,dst=/recovery,options=rbind:ro \
      "$ETCD_IMAGE" etcd-snapshot-check \
      etcdutl snapshot status /recovery/snapshot.db --write-out=table
    sudo ctr -n k8s.io run --rm \
      --mount type=bind,src=/var/tmp/etcd-recovery,dst=/recovery,options=rbind:ro \
      --mount type=bind,src=/var/lib,dst=/var/lib,options=rbind:rw \
      "$ETCD_IMAGE" etcd-restore \
      etcdutl snapshot restore /recovery/snapshot.db \
        --data-dir=/var/lib/etcd-restore \
        --name="$ETCD_NAME" \
        --initial-advertise-peer-urls="$ETCD_PEER_URL" \
        --initial-cluster="$ETCD_INITIAL_CLUSTER" \
        --bump-revision=1000000000 --mark-compacted
    ```

    Stop on any failure; do not bypass hash validation. The revision bump and compaction invalidate stale Kubernetes watch caches. Increase the bump if snapshot age/write rate could exceed it. The [etcd 3.5 recovery guide](https://etcd.io/docs/v3.5/op-guide/recovery/) explains membership and revision handling.

5. Preserve the old data directory and switch only after restore succeeds:

    ```bash
    sudo mv /var/lib/etcd "/var/lib/etcd-before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
    sudo mv /var/lib/etcd-restore /var/lib/etcd
    sudo mv "$RECOVERY_DIR/etcd.yaml" /etc/kubernetes/manifests/
    ```

    Verify etcd starts healthy through `crictl` logs and an authenticated endpoint health check before returning the remaining manifests:

    ```bash
    for component in kube-apiserver kube-controller-manager kube-scheduler; do
      sudo mv "$RECOVERY_DIR/${component}.yaml" /etc/kubernetes/manifests/
    done
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf get nodes
    sudo kubectl --kubeconfig /etc/kubernetes/admin.conf get pods -A
    ```

6. Inspect reconciliation and Secret rotations since the snapshot. Keep the old data and manifests until recovery is validated. A rollback requires stopping the same static pods first, moving the failed restored directory aside, and putting the preserved directory back; never swap a live etcd data directory.

## Single Node Failure

Inspect the Terraform plan and the failed VM before replacement; restarting Terraform does not automatically identify every guest failure. Re-provision only the failed worker and rejoin using Ansible. Local-path PVCs remain tied to their original node/data directory; they do not migrate with rescheduled pods. Recover application data from dumps or surviving node disks before bringing those workloads online. A control-plane loss needs one of the recovery paths above.

## NAS Failure

NFS-backed workloads may hang on I/O or volume mounts. MinIO and Vault are also affected. Restore exports and permissions before restarting dependent pods; mass deletion just recreates the same mount failures. Offsite recovery still needs replacement writable storage. The large media/download share is excluded from Velero and requires an independent NAS backup or re-acquisition strategy.

## Vault KMS Credential Loss

If the KMS key exists, replace the IAM credentials in `vault-aws-kms` using the protected-file procedure above, then restart Vault and verify auto-unseal. Preserve the key ID. A Velero copy of encrypted Vault data is unusable without its original KMS key; recovery keys do not replace that key. Cancel a pending KMS deletion before its deadline. See [Vault auto-unseal recovery](https://developer.hashicorp.com/vault/docs/concepts/seal).

## Full Vault Data Loss

If no usable Vault data copy remains, provision an empty Vault with a working seal, run `make vault-init`, and store the new recovery material outside the cluster. Recreate each secret from protected sources using the repository's examples as the required structure; examples are not copies of real values. Reconfigure ESO, rotate dependent credentials as needed, and validate consumers individually.

## Coverage Limits

Velero captures Kubernetes Secret objects in included namespaces unless excluded; the earlier claim that etcd-only Secrets are universally omitted was incorrect. Backup access must be treated as credential access.

EmptyDir/container filesystems and the excluded media share are not protected. HostPath/local-path PVC data needs the separate SQLite/native-archive path. Prometheus local TSDB history has no such dump. SQLite dumps are not full application-directory backups: settings files, plugins, artwork, and other non-database data may need recreation. Live NFS database copies (including Vault and PostgreSQL) require a proven consistent recovery process. See the roadmap for the restore-drill and application-consistency work still outstanding.
