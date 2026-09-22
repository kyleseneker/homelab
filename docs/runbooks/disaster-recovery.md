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

KMS auto-unseal decrypts existing Vault storage. It does not reconstruct lost Vault data or initialize a new empty Vault. Daily [native S3 snapshots](backup-and-restore.md#production-native-snapshots) provide the current recovery path. A production snapshot passed isolated restoration, KMS auto-unseal, original-identity and authenticated-read checks. Retained quiesced file archives are historical fallback material. The HCP credential path below is independent of Kubernetes and Vault.

### Recover AWS Credentials from HCP Terraform

The `homelab-aws` workspace in the `kyleseneker` HCP organization already holds the
KMS auto-unseal and Velero offsite IAM credentials as Terraform outputs. With a
working HCP account/CLI token, recover them without contacting Kubernetes or Vault:

```bash
make aws-init
mkdir -p .lab
python3 scripts/export-recovery-credentials.py --output-dir .lab/recovery-credentials
```

The output directory must be new. The helper creates it with mode 0700 and writes
`vault-kms.env`, `velero-offsite.credentials`, and non-secret `metadata.json` with
mode 0600. It captures Terraform output privately and never prints credentials.
The region comes from the original KMS key ARN. The env/credentials files can be
used directly by the bootstrap commands below. Do not commit or paste them into
logs; keep any long-term copy in protected recovery storage outside the homelab.

This path was tested without production Kubernetes access: the KMS credentials
successfully encrypted/decrypted a random nonce and matched the credentials used
by the restored Vault's auto-unseal; the S3 credentials successfully listed the
existing offsite backup prefix. The existing local Vault CLI token also
successfully administered the restored instance. This establishes a working
external credential source, not an offline recovery kit. Preserve HCP account/MFA
recovery, its CLI token or another authorized login, and Vault administrative or
recovery material separately. An HCP outage or loss of that account still requires
an independently protected copy. The local `.lab` export alone is not that copy.

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

5. Recover Vault from a [native S3 snapshot](backup-and-restore.md#production-native-snapshots) into a new local Raft target, or rebind surviving Raft storage. Native snapshot restoration initializes only a new empty target before importing; never initialize surviving or migrated data. The retained [file archive](backup-and-restore.md#offsite-vault-archive) is a historical fallback that needs the file-backend restore and Raft migration stages. Direct snapshots can be downloaded without Velero, MinIO or Kopia. Start Velero and its node agents for the remaining application backups, confirm the offsite location is `Available`, and let it synchronize backup metadata. Use the original KMS key, then verify `vault status` reports initialized and unsealed. **Do not run `make vault-init` on data intended for recovery.** If no usable Vault backup remains, explicitly take the full Vault data-loss path below.

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

2. Record the `--name`, `--initial-advertise-peer-urls`, `--initial-cluster`, `--data-dir`, and image from `/etc/kubernetes/manifests/etcd.yaml`. The pinned kubeadm 1.31.4 default is `registry.k8s.io/etcd:3.5.15-0`; verify the actual manifest before selecting a restore utility. This image ships `/usr/local/bin/etcdctl`, not `etcdutl`; its restore command supports the revision-bump and compaction flags below. Recheck the shipped binaries and flags when changing versions. Prepare all artifacts before stopping the API.

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
      /usr/local/bin/etcdctl snapshot status /recovery/snapshot.db --write-out=table
    sudo ctr -n k8s.io run --rm \
      --mount type=bind,src=/var/tmp/etcd-recovery,dst=/recovery,options=rbind:ro \
      --mount type=bind,src=/var/lib,dst=/var/lib,options=rbind:rw \
      "$ETCD_IMAGE" etcd-restore \
      /usr/local/bin/etcdctl snapshot restore /recovery/snapshot.db \
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

### Isolated etcd and API Verification

`scripts/verify-etcd-recovery.py` checks a production snapshot/PKI pair on
`homelabrestore01-node-1` without replacing the lab's control plane. It runs only
as root on that exact lab hostname, refuses an existing work directory, validates
archive paths, and creates a separate network namespace containing only loopback.
The original production API address exists only on that namespace's loopback;
there is no interface or route to either cluster or the internet. The default
check runs only etcd/API. `--controllers` also starts the recovered controller
manager and scheduler for a bounded bootstrap/scheduling test; neither mode
connects a kubelet or executes recovered workloads.

To repeat the drill:

1. Retrieve a matching `snapshot-<timestamp>.db` and `pki-<timestamp>.tar.gz` from
   `s3://velero-offsite-homelab/etcd-snapshots/` with independently recovered S3
   credentials. Record their versions and SHA-256 values. Both contain sensitive
   recovery material; use private directories and never print contents.
2. Prepare a root-owned **0700** input directory on the lab control plane with
   these files: `snapshot.db`, `pki.tar.gz`, `etcd-source.json`,
   `kube-apiserver-source.json`, and `audit-policy.yml`. Each source JSON document
   contains `image` and `command` from the corresponding original static-pod
   container. Capture these before an outage; the verified images are etcd
   `3.5.15-0` and kube-apiserver `v1.31.4`. Use the repository's
   `ansible/roles/k8s_control_plane/templates/audit-policy.yml.j2` for the audit
   policy. Transfer the verifier through the same administrative SSH path.
   For `--controllers`, also copy `scripts/recovery_controllers.py` beside it and
   provide `kube-controller-manager-source.json` and `kube-scheduler-source.json`
   with the same `image`/`command` structure from the original static pods.
3. Ensure the lab has headroom for the temporary processes. The verifier limits
   running etcd/API memory to 384/768 MiB and one CPU each. Controller mode adds
   256/128 MiB limits and refuses to start without another 512 MiB available after
   etcd/API are ready. On the lab host, run:

    ```bash
    sudo python3 /var/tmp/homelab-etcd-recovery-input/verify-etcd-recovery.py \
      --source /var/tmp/homelab-etcd-recovery-input \
      --work /var/tmp/homelab-etcd-recovery-check
    ```

   Add `--controllers` to test restored leader election, Deployment/ReplicaSet/Pod
   creation and scheduler binding. It regenerates one-day controller client
   certificates from the backed-up CA using their original identities and RBAC.
   A temporary bootstrap token requests a kubelet client certificate through the
   recovered API; built-in controllers must approve and sign it automatically.
   The issued identity registers a test Node, updates its status and is denied
   unrelated Secret listing. The test supplies Node status itself; this is a
   protocol fixture, not a running kubelet. A single pause Pod is scheduled to
   that record and must remain unexecuted. The token is then deleted.

4. Inspect the nonsensitive `verification.json` result. Commands and server logs
   stay in the private work directory. The verifier stops its own containers and
   removes its network namespace on normal completion, errors and handled
   termination. After an unhandled host/process failure, inspect named
   `etcd-recovery-*` containers and `homelab-etcd-recovery` networking before retrying;
   do not delete unrelated lab CRI containers or CNI namespaces.
5. Preserve only needed verification evidence, then remove the temporary input
   and work directories, downloaded working copies, and generated client keys.
   Confirm the original lab and production nodes remain Ready.

| Check | Verified result |
|-------|-----------------|
| Offsite pair | `snapshot-20260922-020005.db` and matching PKI archive, obtained with HCP-exported S3 credentials |
| Snapshot SHA-256 | `0f5945eef14a4f3b4340af6786c64fadc9f32ca0538e9a879639e6d06598b483` |
| Integrity and revision | Snapshot hash checked; revision `166199690` restored as `1166199690`; reads at the old revision rejected as compacted |
| PKI and API | Original TLS material accepted; authenticated `/readyz` succeeded; anonymous Secret access denied |
| Recovered objects | API and etcd counts matched: 19 namespaces, 3 node records, 64 deployments and 71 Secrets |
| Controllers | Original controller identities renewed both leader leases; Deployment produced a ReplicaSet and Pod; scheduler bound the Pod to the fixture Node |
| Bootstrap | Bootstrap token authenticated; CSR automatically approved/signed; issued node certificate registered its Node and was denied unrelated Secret listing |
| Isolation and cleanup | Loopback-only networking; no kubelet or workload execution; temporary containers, namespace, restored data and all copied/generated credentials removed |

This proves offsite datastore and API recovery using the backed-up PKI. Node
records in the restored API are historical objects, not recovered running nodes.
The bounded controller and bootstrap-protocol checks passed. Actual kubelet
reconnection, replacement-machine bootstrapping, runtime/CNI networking and
application volume recovery remain separate checks.

## Single Node Failure

Inspect the Terraform plan and the failed VM before replacement; restarting Terraform does not automatically identify every guest failure. Re-provision only the failed worker and rejoin using Ansible. Local-path PVCs remain tied to their original node/data directory; they do not migrate with rescheduled pods. Recover application data from dumps or surviving node disks before bringing those workloads online. A control-plane loss needs one of the recovery paths above.

## NAS Failure

NFS-backed workloads may hang on I/O or volume mounts. MinIO is also affected. Vault uses local Raft storage and direct S3 snapshots. Restore exports and permissions before restarting dependent pods; mass deletion just recreates the same mount failures. Offsite recovery still needs replacement writable storage. The large media/download share is excluded from Velero and requires an independent NAS backup or re-acquisition strategy.

## Vault KMS Credential Loss

If the KMS key exists, replace the IAM credentials in `vault-aws-kms` using the protected-file procedure above, then restart Vault and verify auto-unseal. Preserve the key ID. A Velero copy of encrypted Vault data is unusable without its original KMS key; recovery keys do not replace that key. Cancel a pending KMS deletion before its deadline. See [Vault auto-unseal recovery](https://developer.hashicorp.com/vault/docs/concepts/seal).

## Full Vault Data Loss

If no usable Vault data copy remains, provision an empty Vault with a working seal, run `make vault-init`, and store the new recovery material outside the cluster. Recreate each secret from protected sources using the repository's examples as the required structure; examples are not copies of real values. Reconfigure ESO, rotate dependent credentials as needed, and validate consumers individually.

## Coverage Limits

Velero captures Kubernetes Secret objects in included namespaces unless excluded; the earlier claim that etcd-only Secrets are universally omitted was incorrect. Backup access must be treated as credential access.

EmptyDir/container filesystems and the excluded media share are not protected. HostPath/local-path PVC data needs the separate SQLite/native-archive path. Prometheus local TSDB history has no such dump. SQLite dumps are not full application-directory backups: settings files, plugins, artwork, and other non-database data may need recreation. Live NFS database copies require a proven consistent recovery process. Vault uses native Raft snapshots; PostgreSQL recovery uses logical dumps. See the roadmap for the restore-drill and application-consistency work still outstanding.
