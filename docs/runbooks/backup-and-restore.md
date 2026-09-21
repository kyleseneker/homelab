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
