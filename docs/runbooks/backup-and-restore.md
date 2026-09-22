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

## Vault File-Backend Recovery

This section recovers retained pre-cutover archives. Production uses the native
Raft snapshot procedure below; its old NFS claim no longer receives writes.

Use the [quiesced backup helper](../infrastructure/vault.md#consistent-file-backend-copy)
for a consistent manual copy, then use the offsite transfer below. Scheduled
Velero backups still copy the live file backend; the verified manual archive does
not make those scheduled copies consistent.

1. Take the encrypted archive with Vault stopped, then verify production restarted,
   auto-unsealed, and resumed reconciliation. Preserve its SHA-256 digest privately
   alongside the archive.
2. Apply only the namespace, network policies and PVC from
   `k8s/clusters/homelabrestore01/infrastructure/vault` using `.lab/kubeconfig`.
   Keep the lab Deployment absent until import completes. Mount the fresh PVC in a
   temporary non-root import pod (UID 100, GID/fsGroup 1000), assert the directory
   is empty, and extract the trusted archive there. Compare every file digest with
   the archive before starting Vault, then remove the import pod.
3. Privately create `restore-vault-kms` in `restore-vault` with
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and
   `VAULT_AWSKMS_SEAL_KEY_ID`. Use the original KMS key; never initialize the
   restored storage. The committed policy permits DNS and KMS HTTPS to
   `kms.us-east-1.amazonaws.com`; the lab API is also allowed for authentication.
   Change the endpoint with the region if recovering a different deployment.
4. Apply the full lab Kustomization. Check `vault status -format=json` through
   `kubectl exec`: initialized, unsealed, `awskms`, file storage, and the original
   cluster identity. Restart the lab Deployment and repeat. Probe blocked public,
   production API and NAS destinations.
5. Continue with the Kubernetes auth/ESO procedure below. Unsealing does not prove
   client authentication. Use independently available administrative credentials;
   never expose a root token in logs or enable access back to production to bypass
   the replacement-cluster setup.

### Verified Storage and Auto-Unseal

| Check | Result |
|-------|--------|
| Source | Quiesced production archive `vault-file-20260922.tar.gz`; 44,304 bytes; subsequently downloaded from S3 into fresh lab storage |
| Archive SHA-256 | `ee7fcd3359383acb5b3cd35bff4c58f60b7f6590c8e889d29dcc5101aa57cfef` |
| Import | 109 encrypted files restored to empty lab-local storage; every SHA-256 digest matched |
| Runtime | Vault 1.21.2 initialized and auto-unsealed through the original AWS KMS key; original cluster identity matched |
| Restart | Lab auto-unseal passed again after restart |
| Isolation | Public HTTPS, production API and NAS TCP probes timed out; lab API access is restricted to authentication/reconciliation roles |
| Production | Vault restarted and auto-unsealed; maintenance pause and reader removed; ESO store Ready |

The local restore and the fresh S3 restore below both verified the encrypted file
backend, KMS auto-unseal and authenticated secret reads. The authentication check
also verifies bounded Kubernetes auth/ESO recovery. Scheduled consistent backups
remain unfinished; the manual copy does not establish a recurring recovery point.

### Offsite Vault Archive

After validating a quiesced archive, use the [HCP credential export](disaster-recovery.md#recover-aws-credentials-from-hcp-terraform)
and AWS CLI to upload it into the existing offsite bucket and verify a download:

```bash
python3 scripts/vault-offsite-copy.py \
  --archive '.lab/vault-restore/vault-file-<timestamp>.tar.gz' \
  --credentials-dir .lab/recovery-credentials \
  --expected-sha256 '<verified archive SHA-256>' \
  --download-output .lab/vault-restore/vault-file-offsite.tar.gz
```

The helper reads bucket/region from the protected export, ignores ambient AWS
credentials, checks the source digest, and uploads to
`vault-file-backups/<archive filename>` with S3 AES256 encryption and a SHA-256
metadata field. `If-None-Match: *` prevents overwriting an existing object. It
checks the downloaded bytes, metadata and version before publishing a private
local file; an existing local download is never overwritten. Reusing an uploaded
archive filename intentionally fails. If upload succeeds but download fails, use
`aws s3api get-object` with the exported credentials to retrieve that existing
object separately and verify its recorded digest; do not delete it to rerun the
upload.

This direct prefix is separate from Velero's `velero/` repositories and needs no
Kopia repository password. Recover into empty storage using the file-backend
procedure above. S3 bucket versioning is enabled, but neither it nor conditional
uploads make the archive immutable. Current objects have no automatic age-based
deletion; choose a retention policy before automating recurring uploads.

| Check | Verified result |
|-------|-----------------|
| Object | `s3://velero-offsite-homelab/vault-file-backups/vault-file-20260922.tar.gz` |
| Version | `_9pYzsIC99O4UqOJh3MtuYy6.ngKVJlM` |
| Integrity | Download SHA-256 matched the archive digest above; all 109 extracted encrypted file hashes matched |
| Fresh restore | Separate empty lab PVC; Vault initialized, auto-unsealed, and retained its original cluster identity |
| Authentication | Local administrative token authenticated; both Grafana fields matched the previously verified restore |
| Credentials | S3 and KMS credentials exported from HCP; no production Kubernetes access used for this restore |
| Overwrite protection | Repeated upload to the same object returned `PreconditionFailed` |
| Cleanup | Temporary offsite-test Deployment, PVC, KMS Secret and network policy removed; the original lab Vault/ESO remain |

The temporary server had no Service, service-account token, production mounts or
API access; its network policy allowed only DNS/KMS. This proves manual offsite
Vault recovery without the production cluster, MinIO or NAS, while still relying
on HCP access and independently held Vault administrative credentials.

### Kubernetes Auth and ESO Recovery

The lab Vault manifests include a projected, rotating Kubernetes service-account
token and the lab CA. Its dedicated ClusterRole permits only `create` on
`tokenreviews.authentication.k8s.io`. Vault can reach the lab API, DNS and the
regional KMS endpoint; ingress on 8200 is limited to the lab ESO controller.
Production API/NAS and unrelated public HTTPS remain blocked. No external route
is exposed.

1. Complete the storage restore and apply the lab Vault Kustomization. Obtain an
   administrative Vault token independently, either through `VAULT_TOKEN` or the
   local Vault CLI token file. Do not place it in manifests, command arguments,
   logs or the ESO runtime Secret.
2. Run `python3 scripts/restore-vault-auth.py`. It refuses a kubeconfig context
   other than `homelabrestore01`. It configures the restored Kubernetes auth mount
   to use the pod's lab CA and rotating reviewer token, then creates a dedicated
   `restore-external-secrets` role with audience `vault`, a ten-minute maximum
   token lifetime, and read access only to `homelab/data/infrastructure/grafana`.
   The restored production ESO role/policy remain separate.
3. Render/apply ESO chart 2.2.0 as `restore-external-secrets` in `restore-vault`,
   using `infrastructure/external-secrets/values.yml` under the lab cluster. Install
   its CRDs with server-side apply, then apply that directory's Kustomization.
   The controller uses namespace-scoped RBAC and a SecretStore; cluster stores,
   cluster reconciliation and push controllers are disabled. The lab uses only
   v1 resources, with conversion/webhook/certificate controllers disabled.
4. Wait for `SecretStore/restore-vault` and `ExternalSecret/restore-grafana` to
   report Ready. Privately compare both generated Grafana fields with the restored
   Vault data. Delete only `Secret/restore-grafana` and trigger a refresh; confirm
   ESO creates a new Secret UID with identical values.
5. Verify the correct service account/audience authenticates, while the wrong
   service account and audience fail. Confirm its Vault token cannot read another
   path or write the permitted path. Revoke the short-lived test token afterward.
   Restart Vault and ESO, then repeat the read/reconciliation checks.

This procedure passed using an existing administrative token from the local Vault
CLI file. Both restored Grafana fields matched production in a private comparison;
Kubernetes login, restricted reads, all four denial checks, and recreation after
Secret deletion passed before and after restarting Vault and ESO. No admin token
is required by either runtime controller. This demonstrates representative secret
recovery, not every application credential or a complete site-loss bootstrap.

Vault's [local reviewer-token behavior](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
and ESO's [Vault authentication configuration](https://external-secrets.io/latest/provider/hashicorp-vault/)
explain the rotating-token and audience settings used here.

### Raft Migration and Native Snapshot Rehearsal

Production and the lab now use separate local Raft PVCs, retaining their original
file PVCs as historical recovery material. The production
architecture is recorded in [ADR-024](../decisions/024-vault-integrated-storage.md).

To repeat the offline lab migration after a file-backend restore:

1. Verify Vault is initialized, unsealed and using file storage. Record its cluster
   ID and privately compare representative secret values. Keep the source archive.
2. Apply only `vault-raft/pvc.yml` to create an empty destination. Scale
   `Deployment/restore-vault` to zero and wait for its pods to disappear. The
   migration Job must never copy a live writer's data.
3. Apply `vault-raft/migration` and wait for `Job/restore-vault-raft-migrate` to
   complete. It mounts the original PVC read-only, copies it into scratch space,
   and runs `vault operator migrate` from that copy into the empty destination.
   It refuses a nonempty destination. Migration logs remain inside the temporary
   container because they contain internal storage paths.
4. Delete the completed migration Job, then apply the `vault-raft` overlay. Verify
   Raft storage, KMS auto-unseal, original cluster ID, authenticated reads, and ESO
   reconciliation. Do not initialize the migrated destination.
5. Before accepting new writes, applying the original `vault` base switches back
   to the retained file PVC. Verify auto-unseal, then reapply the Raft overlay to
   return to Raft. The old file backend does not receive subsequent Raft writes.

All lab commands use `.lab/kubeconfig` and namespace `restore-vault`. The lab's
Application config now points at the Raft overlay; the file base remains the
explicit file-archive restore stage. Production uses its own Raft claim and values.

Run `python3 scripts/restore-vault-auth.py --snapshots` after migration to configure
the lab snapshot-read role. `CronJob/restore-vault-snapshot` is suspended; create a
manual Job from it to test capture. It authenticates with a projected ten-minute
service-account token, saves and inspects a native snapshot, records its SHA-256,
and revokes its Vault token. It has no Kubernetes RBAC grants or AWS credentials.
Snapshots are staged on a separate lab PVC; this job does not upload them offsite.

For native restoration, start a separate Raft server with an **empty** PVC and the
same KMS key. Initialize only that empty test target, capture its temporary admin
credential privately, and run `vault operator raft snapshot restore` against the
snapshot. The rehearsal did not require `-force`. Wait for the original cluster
ID and unsealed state to converge: an immediate response can still show the
initial target's identity while restore completes. Authenticate with the original
restored administrative token and compare secret values before deleting the test
server and PVC.

| Check | Result |
|-------|--------|
| File-to-Raft migration | Offline copy migrated; original file PVC retained read-only during migration |
| Compatibility | KMS auto-unseal, original identity, authenticated values, Kubernetes auth denial checks and ESO Secret repair passed |
| Snapshot capture | Manual Job completed using only `read` on the snapshot endpoint; individual secret reads were denied |
| Snapshot | 49,752 bytes; SHA-256 `3ab68728b84bd9cc62e2ae71681afa35dbb5c6f9a9636a529e7cb5105ee84836` |
| Native restore | Fresh local PVC, same KMS key, no force flag; original identity and matching Grafana fields recovered |
| Rollback | Retained file backend auto-unsealed; return to Raft and ESO checks passed |

This verifies the migration and native backup mechanism. Production verification
is recorded in the next section.
See HashiCorp's [offline migration](https://developer.hashicorp.com/vault/docs/commands/operator/migrate)
and [Raft snapshot commands](https://developer.hashicorp.com/vault/docs/commands/operator/raft).

## Production Native Snapshots

`vault/vault-snapshot` runs daily at **01:30 UTC**. The job authenticates through
Kubernetes as `vault-snapshot`, saves and inspects an online Raft snapshot, and
uploads to `s3://velero-offsite-homelab/vault-raft-snapshots/`. Uploads refuse an
existing key. A successful job requires a downloaded copy with the same S3 version
and SHA-256. `scripts/vault-snapshot-auth.sh` configures its ten-minute,
snapshot-read-only role using an existing administrative Vault CLI session.

The S3 bucket denies insecure transport. Current objects under this prefix expire
after 30 days; noncurrent versions retain the existing 90-day rule. This is not
immutable storage. `VaultSnapshotStale` watches successful CronJob timestamps and
alerts after a 30-hour gap with a 30-minute pending period. The first run was a
manual job; the first scheduled run supplies the CronJob success timestamp.

### Restore a Native S3 Snapshot

1. Export recovery credentials from HCP using the disaster-recovery runbook. Keep
   the credential files and downloaded snapshot private. Select the desired
   `vault-raft-snapshots/` object, download it with the exported S3 identity, and
   compare SHA-256 with its `sha256` object metadata. This needs neither production
   Kubernetes nor Velero, MinIO or NAS.
2. Prepare a separate Vault 1.21.2 Raft target with a **new empty** local PVC and
   the original KMS key/credentials. Isolate it from production clients and
   Kubernetes authentication. Preserve any surviving data before replacing it.
3. Only for this empty snapshot target, run `vault operator init` and capture its
   temporary administrator credential privately. Copy the encrypted snapshot into
   private staging space in the target pod. Authenticate with that temporary
   credential and run `vault operator raft snapshot restore /tmp/offsite.snap`.
   The tested same-KMS-key procedure did not need `-force`.
4. Poll until the **original cluster ID** and unsealed state appear. Restore is
   asynchronous; an early status response can still describe the temporary
   cluster. Authenticate with the original restored administrative credential,
   compare representative KV values privately, and reconfigure Kubernetes auth
   for the destination cluster before enabling ESO and clients.
5. Verify ESO refreshes and secret values, then recreate the snapshot role if
   needed. Restore the backup job and credential reference only after auth works.
   Delete temporary test workloads, PVCs and network policies after validation.

| Check | Result |
|-------|--------|
| Production migration | Offline read-only copy from NFS to local Raft; old claim and a fresh encrypted archive retained |
| Production health | Original cluster identity, KMS auto-unseal, representative KV equality and forced ESO refresh passed; all 28 ExternalSecrets Ready |
| Backup permissions | Snapshot read allowed; secret read, wrong service account and wrong audience denied |
| Verified S3 object | `vault-raft-snapshots/vault-20260922T130941Z.snap`, 48,305 bytes |
| SHA-256 | `311af9f97be0060f00fc7ef59fe0d44c453d25918afe743d54abe20918541c02` |
| Restore | Independent HCP S3 credentials, new lab PVC, original KMS key; original identity and KV values recovered without force |
| Cleanup | Temporary restore Deployment, PVC and network policy removed |

The old `data-vault-0` NFS volume is stale after cutover. Returning to it would lose
new Raft writes. Keep it as historical recovery material until separately retired.
One Raft voter remains non-HA; loss of its node requires snapshot recovery.

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


## Verified Sonarr Offsite Restore

Sonarr 4.0.19 started successfully from an application-consistent SQLite dump retrieved directly from AWS S3 into the isolated restore lab. The database was copied into a fresh 1 GiB local-path PVC, owned by UID 977 / GID 988, and passed `PRAGMA integrity_check` before startup. The installed file matched the downloaded SHA-256.

| Evidence | Result |
|----------|--------|
| Velero backup | `velero-weekly-offsite-20260920050031` |
| PodVolumeBackup | `velero-weekly-offsite-20260920050031-mbzmn`, Completed |
| Kopia snapshot | `94b958bbbd73b55ab2269e6c0666c050`, subdirectory `sonarr` |
| S3 source | `velero-offsite-homelab`, repository prefix `velero/kopia/arr/` |
| Dump timestamp | 2026-09-20 01:35:01 UTC |
| Retrieval | 2026-09-21 13:22:01–13:22:05 UTC; approximately 4 seconds |
| Dump age at retrieval | 35 hours 47 minutes |
| Application verification | 2026-09-21 13:34:31 UTC; 12 minutes 30 seconds after retrieval began, with the lab already bootstrapped |
| Restored database | 4,046,848 bytes; integrity `ok` |
| SHA-256 | `a19f2fe0ce6ee12085462cb04f3c67d76760759de5d9e63d6a1ffaca2dc2f5ab` |
| Database/API comparison | 1 series, 116 episodes, 54 episode-file records, 7 quality profiles; all series identities and episode identities/titles match |
| Login | Fresh lab Forms user; anonymous protected-page redirect and authenticated HTTP 200 verified |

The staging pod could not connect to public HTTPS, the lab API, the production API or NAS NFS. No production media volume was mounted. The 54 episode-file records are metadata; this test did not recover or read the media files. The original database contained no local users, consistent with production's external authentication. The lab Forms login does not validate Authentik recovery.

The backup contained `sonarr.db`, not `config.xml`. Deployment/bootstrap settings and a fresh API key were supplied separately. In production, Git/Helm and Vault/ESO provide deployment settings and API credentials; media-operator owns the declared root folders, download clients, notifications and media-management settings; Prowlarr owns indexer sync; Recyclarr owns quality profiles and custom formats. These controllers should recreate their declared configuration after the database is restored. The subsequent [media-operator drill](restore-lab.md#media-operator-reconciliation) verified recreation of a lab root folder and repair of declared media-management/download-handling settings without changing restored series/episode identities. The [Recyclarr/Prowlarr drill](restore-lab.md#recyclarr-and-prowlarr-recovery) also verified profile recreation and local test-indexer synchronization. Production trackers, download clients/notifications, independent credential recovery and SSO remain unverified. Settings absent from these declarations still need explicit recovery coverage.

### Read-only S3 Retrieval

Use the selected Completed PodVolumeBackup's `snapshotID`, uploader and storage location to identify the repository. This drill used checksum-verified Kopia 0.23.1 to read the Velero Kopia repository directly. Follow Velero's [read-only Kopia connection guidance](https://velero.io/docs/v1.18/troubleshooting/) with `--readonly`, `--override-username=default` and `--override-hostname=default` so the recovery client does not take maintenance ownership.

Read the AWS credential reference from the offsite BackupStorageLocation and the repository password from `velero-repo-credentials`. Supply them through a private process environment, never command arguments or terminal output. Use an ephemeral configuration/cache directory under ignored `.lab/`, disable file logging and keychain access, and do not persist credentials. With that connection established:

```bash
# Use the same private --config-file and global options on each invocation.
kopia snapshot list --all --json
kopia snapshot restore <snapshot-id>/sonarr <new-private-directory> \
  --skip-owners --skip-permissions --no-overwrite-files
```

Record the dump's original timestamp before copying it. For an offline SQLite dump in WAL mode, open it with `mode=ro&immutable=1` for integrity checks; never use immutable mode against a live writer. Install only into a stopped application on a fresh volume, following the [lab procedure](restore-lab.md#sonarr-recovery).

This drill needed neither MinIO nor NAS data access, but the original services were not shut down. Backup credentials were obtained from the running production cluster. It therefore proves S3 database recovery across the lab's network boundary, not full site-loss recovery with externally escrowed credentials. Repeat with independently available credentials as part of the remaining recovery acceptance checks.

## Authentik PostgreSQL Recovery

`authentik-backup` runs at 01:45 UTC using PostgreSQL 17 tools, before the daily Velero schedule. PostgreSQL's [native `pg_dump`](https://www.postgresql.org/docs/17/app-pgdump.html) provides a consistent database snapshot while the application continues running. The job writes a custom-format archive to a temporary file, checks its archive listing, then atomically publishes `authentik.dump` on the `authentik-backups` PVC. The holder must remain Running for Velero to capture this volume. Do not overlap a manual dump with another dump job.

Keep the original `AUTHENTIK_SECRET_KEY` and bootstrap credentials available independently. The dump contains application data, not PostgreSQL cluster roles or a separately recoverable copy of Vault. A restore with `--no-owner --no-acl` assigns objects to the destination role; provision that role and its credentials before restoring.

### Restore into the Lab

1. Retrieve the `authentik-backup-holder` PodVolumeBackup from the chosen offsite backup using the read-only Kopia procedure above. Its repository prefix is `velero/kopia/auth/`; retain both `authentik.dump` and `completed-at` in a private directory.
2. Apply the lab `authentik-database/namespace.yml`, create `restore-authentik-db` in `restore-auth` with a fresh `password` key through private process input, then apply that directory's Kustomization. It creates only local storage and PostgreSQL, with no Service and namespace deny-all networking. Always select `.lab/kubeconfig` and confirm context `homelabrestore01` before writes.
3. Wait for the database Deployment to be Ready. Confirm the destination contains zero public tables. Never run the restore over an existing application's database.
4. Restore into the empty database:

    ```bash
    kubectl --kubeconfig .lab/kubeconfig -n restore-auth \
      exec -i deploy/restore-authentik-db -- \
      pg_restore --exit-on-error --single-transaction --no-owner --no-acl \
        -U authentik -d authentik_restore \
      < .lab/authentik-restore/source/authentik.dump
    ```

5. Compare table, user, application, provider, flow and migration counts with the recovery evidence. Confirm local PostgreSQL readiness and that public HTTPS, lab/production APIs and NAS access remain blocked. Database contents include sensitive identity material; keep the lab isolated and do not print rows or tokens.
6. Continue with the isolated application check below before reopening integrations.

### Verified Database Restore

| Evidence | Result |
|----------|--------|
| Offsite backup | `authentik-logical-20260921`, Completed |
| Kopia snapshot | `38ae9c0f39ab50ac03c58c4857cf88fe` in `velero/kopia/auth/` |
| Dump completed | 2026-09-21 14:42:17 UTC |
| S3 retrieval | 2026-09-21 14:48:50–14:48:55 UTC; dump age approximately 6 minutes 34 seconds |
| Restored archive | 15,770,027 bytes |
| SHA-256 | `2e1aefd9a2cffc9cd33a997a48d591df86178cb17fedcc3fb252d9d01d7e7753` |
| Destination | Fresh local-path PVC, PostgreSQL 17.9, database `authentik_restore` |
| Restore result | Exit 0 in a single transaction; verified at 2026-09-21 14:50:19 UTC |
| Counts matching production | 212 tables, 3 users, 13 applications, 13 providers, 14 flows, 692 migrations |
| Retrieval through database verification | Approximately 1 minute 28 seconds, with lab Kubernetes/PostgreSQL already ready |
| Isolation | Local database readiness passed; unrelated public HTTPS, both APIs and NAS TCP probes timed out |

The dump was retrieved from S3, without reading NAS data during restoration. Recovery credentials still came from the running production cluster. This database stage alone proves native database recovery. The application checks below extend that evidence; independent credential recovery remains unverified.

### Verified Application and OIDC Recovery

After restoring the database, create `restore-authentik-server` in `restore-auth` with the original `AUTHENTIK_SECRET_KEY` under `secret-key`, using private process input. Apply `k8s/clusters/homelabrestore01/apps/authentik-server` with the lab kubeconfig. This is a separate deployment step: it starts the matching Authentik 2026.2.1 server and permits only lab PostgreSQL and DNS egress. The database Service is internal; server access uses a localhost-only port-forward. No worker or embedded outpost runs, and no production blueprints are mounted.

The application recovery check passed against the S3-restored database:

- The server became Ready and loaded all 13 restored OIDC providers.
- `ak create_recovery_key 10 akadmin` issued a short-lived recovery link in the lab. Following it established a session; `/api/v3/core/users/me/` identified the restored administrator. Keep the link and cookies private.
- Only the restored ArgoCD provider's redirect URI was changed to `http://127.0.0.1:19001/callback`. Its original client credentials and signing key were retained. Never make this callback edit in production.
- An authorization-code request with random state and nonce passed the existing explicit-consent flow. Flow API submissions used the `X-authentik-CSRF` header and the server-issued consent challenge token.
- The code exchange returned an ID token whose RS256 signature verified against the restored provider's JWKS. Issuer, audience, nonce and expiry checks passed; userinfo matched the restored administrator. Reusing the code returned HTTP 400.
- The server could reach lab PostgreSQL; public HTTPS, lab/production APIs and NAS probes timed out.

This verifies emergency administrator login and the restored provider's OIDC protocol flow with a lab callback. It does not verify ordinary password/MFA login, a running ArgoCD/Grafana client, production TLS/routes, proxy outposts, worker tasks or independently escrowed recovery credentials. The original secret key and backup credentials were still obtained from production. Keep those remaining checks separate from this successful application restore, and delete private test links, cookies and client credentials after use.

## Tdarr Native Archive Recovery

Tdarr 2.86.01's bundled backup screen specifies an offline restore: stop the server and unpack the native archive into its data directory. The lab uses a fresh volume, so no existing database is overwritten. The archive contains `DB2` and `Plugins`; database dumps alone do not recover the plugin files.

1. Retrieve `tdarr/latest.zip` from the offsite media-holder snapshot using the read-only Kopia procedure. Keep the original archive private and verify its ZIP CRC and SHA-256 before extraction.
2. Apply only `namespace.yml`, `networkpolicy.yml` and `pvc.yml` from `k8s/clusters/homelabrestore01/apps/tdarr`, selecting `.lab/kubeconfig` explicitly. Leave the server stopped. Create `restore-tdarr-api-key` with a fresh `api-key` beginning with `tapi_` through private process input.
3. Mount the new PVC in a temporary non-root import pod in `restore-tdarr`. Reject absolute paths, parent-directory traversal and symlinks in the ZIP. Require an empty destination, then extract into the PVC's `Tdarr/` directory. Verify `Tdarr/DB2/SQL/database.db` with SQLite `integrity_check`. The archive's `SQL_backup_preop` directory is an old rollback copy, not the active database.
4. Remove the import pod, then apply the directory's Kustomization. It runs only the server binary at the production version, with `internalNode=false`, a read-only root filesystem and no media/GPU mounts. The namespace denies ingress and egress; no Service or route is created. Use `kubectl exec` or a localhost port-forward for checks.
5. Read `FlowsJSONDB`, `LibrarySettingsJSONDB`, `VariablesJSONDB` and `FileJSONDB` through `/api/v2/cruddb` in `getAll` mode using the fresh lab key. Compare complete records with the archive's corresponding SQLite tables, not merely their counts. Compare plugin file hashes and confirm `/api/v2/get-nodes` is empty. Do not confuse restored node configuration records with connected nodes.

### Verified Tdarr Restore

| Evidence | Result |
|----------|--------|
| Offsite backup | `recovery-verify-20260921` |
| Kopia snapshot | `823c7796b716c4351068b720750dd720` in `velero/kopia/arr/` |
| Native archive SHA-256 | `0aa77fb922435e0ebbad89fcd95912d81b15994651095571abace75b5df6ed38` |
| Archive contents | 501 entries; CRC checks passed |
| Active database SHA-256 before startup | `41712f7f2dcba881099bc178c2f5806b08bf82f6188fb013acad14d5225ca96e` |
| Destination | Fresh 2 GiB local-path PVC; Tdarr 2.86.01 |
| Database integrity | `ok` before application startup |
| Records loaded through the API | Exact matches for 5 flows, 2 libraries, 34 variables and 60 file-metadata records |
| Plugins | All 275 archived plugin files matched their original hashes |
| Authentication | Fresh lab API key accepted; unauthenticated collection request returned HTTP 401 |
| Restart | Exact record comparisons and API authentication passed again after server restart |
| Processing | Zero connected nodes; no media or GPU mounted |
| Isolation | Public HTTPS, lab/production APIs and NAS TCP probes timed out |

This verifies native configuration recovery and application readability. It does not recover the media files, prove flow execution or GPU transcoding, or verify normal UI/SSO login. Backup credentials still came from production. Test a copied media fixture and review library-specific replacement/deletion settings before enabling workers in a real recovery.

## qBittorrent Configuration and Resume Recovery

The `qbit-config` volume contains qBittorrent settings, category definitions and `BT_backup` torrent/resume records. It is captured as a live NFS filesystem backup. The download/media volume is excluded: restoring resume records does not restore their payload files or prove that a transfer can resume.

1. Retrieve the chosen `qbit-config` PodVolumeBackup through the read-only Kopia procedure. Preserve the original snapshot privately. Check that each `.torrent` has its corresponding `.fastresume`, both decode as bencode, and the torrent metadata's info-hash agrees with the resume record and filenames. Do not print torrent names, tracker URLs or credentials.
2. Prepare a separate lab copy while the client is stopped. Use a fresh WebUI username/password hash; require localhost authentication and disable subnet bypass. Disable external-command hooks, RSS auto-download and DHT/PeX/local discovery. Bind torrent networking to loopback. Set the copied resume records to stopped (`paused=1`, `auto_managed=0`), leaving their identities, paths and transfer history intact. Remove stale process locks. Never make these test changes in the original snapshot or production configuration.
3. Apply only `namespace.yml`, `networkpolicy.yml` and `pvc.yml` from `k8s/clusters/homelabrestore01/apps/qbittorrent`, with `.lab/kubeconfig`. Import the prepared copy into the empty PVC using a temporary non-root pod, then remove that pod before applying the Deployment.
4. The Deployment runs qBittorrent 5.2.3 directly, using `/config` for configuration and data. It starts no Gluetun/VPN sidecar and mounts no downloads. The namespace denies all ingress/egress; no Service or route is created. Access the WebUI through `kubectl exec` or a localhost-only port-forward.
5. Verify unauthenticated API rejection, login with the fresh lab credentials, and the restored torrent/category/path/history metadata. qBittorrent 5.2.3 returns HTTP 204 with a session cookie on successful login. Its Host header validation also checks the port: when forwarding local `18080` to `8080`, API clients must send matching `Host: 127.0.0.1:8080` and `Referer: http://127.0.0.1:8080` headers. Alternatively, forward local port `8080` when available. Keep host-header validation and CSRF protection enabled.
6. Confirm zero peers, blocked external/API/NAS access and persistent metadata after restarting the lab client. In a real recovery, restore and verify the payload at its expected paths and reestablish the VPN boundary before permitting transfers.

### Verified qBittorrent Restore

| Evidence | Result |
|----------|--------|
| Offsite backup | `recovery-verify-20260921` |
| Kopia snapshot | `a3aa2dbe8202b4ba7d09b12c87bfa50b` in `velero/kopia/arr/` |
| Snapshot contents | 36 files, including settings, categories and one torrent/resume pair |
| Pair integrity | Bencode readable; info-hash matched torrent metadata, resume record and filenames |
| Destination | Fresh 2 GiB local-path PVC; qBittorrent 5.2.3 |
| API comparisons | Torrent identity/name, category, save path, total size and download/upload history matched the source; category names/save paths matched |
| Authentication | Fresh login succeeded; unauthenticated torrent-list request returned HTTP 403; both authentication bypasses disabled |
| Runtime state | `missingFiles`, zero peers; download payload deliberately absent |
| Isolation | Public HTTPS, lab/production APIs and NAS TCP probes timed out |
| Restart | Authentication and metadata comparisons passed again |

This proves application-readable configuration and resume metadata for this snapshot. It does not establish atomic consistency for every future live filesystem backup, recover the payload, exercise VPN bootstrap or demonstrate downloading/seeding. Backup credentials still came from the running production cluster. The production media operator already handles this version's HTTP 204 login/session-cookie behavior and remained Ready/Synced.
