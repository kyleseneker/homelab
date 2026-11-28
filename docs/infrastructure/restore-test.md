# Restore Test

Every night a CronJob restores the backup volumes into a throwaway `restore-sandbox` namespace, checks the restored data in tiers and reports the result per target to the [Pushgateway](pushgateway.md) ([ADR-034](../decisions/034-restore-testing.md)). It covers every backup volume Velero holds; [Phase 1.4](../roadmap/phase-1-foundations.md#14-automate-restore-tests) tracks the application checks, Authentik's database restore and the offsite, etcd and Vault runs still to come.

## Details

| Field | Value |
|-------|-------|
| Type | CronJob (`sourceType: git`) |
| Namespace | `backups`; each run works in `restore-sandbox` |
| Schedule | `restore-test` at `30 3 * * *` (03:30 UTC daily); `restore-test-offsite` at `30 5 * * 0` (05:30 UTC Sundays); `restore-test-etcd` at `30 2 * * *` |
| Source | Latest completed `velero-daily-stateful` backup on Garage nightly; latest completed `velero-weekly-offsite` backup on S3 weekly, which may be 8 days old |
| Deadline | 2 hours per Job; one Job at a time |
| Image | `python:3.15-alpine` for the harness and most checkers; the image that wrote a dump for its check (Authentik's `pg_dump`); the application's own image for app checks |
| Results | Pushgateway, job `restore_test`, grouped by `target` and `source` |

## How a Run Works

1. The run fails at once if `restore-sandbox` exists, so it never reuses a sandbox a person kept for inspection. It waits for the newest `velero-daily-stateful` backup to finish.
2. It creates `restore-sandbox` with Pod Security `baseline`. The cluster-wide `baseline` network policy leaves pods there only DNS.
3. It checks the fences: Arrchitect still runs with `--watch-namespace=media`, and a dry-run Sonarr resource in the sandbox is refused by `deny-arrchitect-in-restore-sandbox`.
4. It creates a Velero Restore from the schedule's latest completed backup. The Restore brings back only pods and claims labelled `app.kubernetes.io/component: backup-volume`. It lists volumes too, because Velero restores pod volume data only then, but excludes cluster resources, so Velero never creates a volume object. It maps their namespaces to the sandbox, leaves existing resources alone and applies the `restore-test-modifiers` ConfigMap, which strips scheduling constraints from the pods, clears each claim's binding to its production volume and moves the claims to the `nfs-restore-test` StorageClass. Velero keeps that binding when, as here, volume objects are not part of the restore.
5. It checks each target in tiers. A later tier runs only when the ones it depends on passed.
6. It pushes each target's results, deletes the sandbox and the Restore and exits non-zero if any target failed. Deleting the sandbox deletes its volumes and their NAS directories. Velero copies production's `Retain` reclaim policy onto the restored volumes, so the run sets them back to `Delete` after the restore and again before cleanup, which also reclaims volumes an interrupted run left behind.

| Tier | Passes when |
|------|-------------|
| `restored` | The Restore completed with no errors and the target's volume restored a non-zero size |
| `intact` | The dump passes its format's own check (below) |
| `fresh` | The backup started no more than 28 hours before the run, and the dump inside it was written no longer before the backup than its schedule allows |
| `usable` | The application starts on a writable copy of its restored dump directory, or of its unpacked archive, with the image and security context its live Deployment runs |
| `answers` | The application's API returns as many objects as the restored database holds |

Authentik's database check runs a throwaway Postgres server from the image of the production `authentik-postgresql` StatefulSet, with trust authentication that only its own pod can reach, and restores the dump into it with `pg_restore --exit-on-error --single-transaction`, so any failed statement fails the tier.

The app check runs in one pod: the application, plus a checker container that queries it over localhost with a throwaway API key. It needs no network policy and reaches nothing outside the pod. The application runs with its live pod and container security context and keeps its production CPU, memory and ephemeral-storage limits but requests only 50m CPU and 256 MiB and no GPU, and each check pod is deleted once its result is read, so a run never stacks applications. The cluster's CPU requests sit close to what it can promise with one node down, and production-sized requests held through a slow check tripped `KubeCPUOvercommit`.

## Targets

| Target | Volume | Dump | `intact` check | Dump age limit | App check |
|--------|--------|------|----------------|----------------|-----------|
| `sonarr` | `media/config-backups` | `sonarr/sonarr.db` | SQLite; `Series` has rows; no foreign-key violations | 26 h | `/api/v3/series` |
| `radarr` | `media/config-backups` | `radarr/radarr.db` | SQLite; `VersionInfo` has rows | 26 h | `/api/v3/movie` |
| `prowlarr` | `media/config-backups` | `prowlarr/prowlarr.db` | SQLite; `VersionInfo` has rows | 26 h | `/api/v1/applications` |
| `bazarr` | `media/config-backups` | `bazarr/db/bazarr.db` | SQLite | 26 h | `/api/series` counts `table_shows`, with a throwaway key seeded into `config.yaml` |
| `jellyfin` | `media/config-backups` | `jellyfin/data/data/jellyfin.db` | SQLite | 26 h | `/System/Info/Public` reports the setup wizard completed |
| `seerr` | `media/config-backups` | `seerr/db/db.sqlite3` | SQLite | 26 h | Starts on `/api/v1/settings/public`, which then reports `initialized` |
| `tdarr` | `media/config-backups` | `tdarr/latest.zip` | ZIP CRCs; `DB2/SQL/database.db` present and sound | 50 h | `/api/v2/cruddb` lists as many libraries as `librarysettingsjsondb` holds |
| `uptime-kuma` | `monitoring/uptime-kuma-backups` | `kuma.db` | SQLite | 26 h | Starts and serves `/api/entry-page`; no data probe |
| `authentik` | `auth/authentik-backups` | `authentik.dump` | `pg_restore --list`, then a full read, with the image that wrote it | 26 h, from `completed-at` | Restore into a scratch Postgres running production's image; users, groups, applications and flows have rows |
| `home-assistant` | `home-automation/home-assistant-backups` | newest `*.tar` | Every member reads; `backup.json` says the backup is encrypted; every payload decrypts with the backup key from Vault, and Home Assistant's holds `.storage/core.config_entries` | 40 h, from `backup.json` | -- |

A SQLite check passes when `integrity_check` is `ok`, the database holds rows and every required table has rows. Foreign-key violations are reported for every database but fail only Sonarr, whose schema is known to have none. A dump's age comes from its modification time, which Velero's restore keeps, unless the target names a timestamp. Checkers run as the user of the holder that mounts the volume.

Home Assistant's check runs in the image its live Deployment runs, whose `securetar` decrypts the archive the way a restore does. The payload is decrypted and listed in memory and never written to disk. The key reaches the sandbox through the `restore-test-home-assistant` ClusterExternalSecret, which selects only `restore-sandbox`, so External Secrets syncs it from Vault `apps/home-assistant` when a run creates the sandbox, and it goes when the sandbox does. The harness reads no Secrets; it waits up to three minutes for the ExternalSecret to report `Ready` and fails the target with External Secrets' message if it does not.

Uptime Kuma shows its monitors only to signed-in users or through status pages, and the production database holds neither monitors nor status pages, so its check ends at `usable`. Seerr's `/api/v1/status` and Bazarr's startup both call GitHub, which the sandbox cannot reach: Seerr's check uses its local public-settings endpoint instead, and Bazarr gets 15 minutes to start.

Tdarr's archive is unpacked into the server's `Tdarr/` directory, as its offline restore specifies. The server runs with `internalNode=false`, so no worker starts and nothing touches media, and with scheduled plugin updates off. The intact check also records the archived library, flow, variable and file counts.

Prowlarr's check counts its configured applications, not its indexers. Prowlarr builds the indexer list from definitions it downloads at startup and keeps outside its database, so a sandbox with no internet access cannot list indexers, and a real restore needs Prowlarr to reach its definitions server before indexers work.

## etcd

Velero does not hold the etcd recovery set, so `restore-test-etcd` checks it where the [etcd backup](etcd-backup.md) writes it. It runs at 02:30 UTC on the control-plane node, where the backup job runs, and mounts the `etcd-snapshots` volume read-only. The etcd image the backup job snapshots with is mounted as an image volume, so the check runs that image's own `etcdutl` and `etcd`.

| Tier | Passes when |
|------|-------------|
| `restored` | A `recovery-*.json` record exists; the newest by its timestamp is checked |
| `intact` | The snapshot, PKI and control-plane archives are all listed, match the record's sizes and SHA-256 sums, and the archives read |
| `fresh` | The set is at most 26 hours old |
| `usable` | `etcdutl snapshot restore` accepts the snapshot, including its integrity hash, and a single-member etcd starts on it on localhost |
| `answers` | Keys exist under `/registry/`, including the `kube-system`, `media` and `backups` namespaces |

The key count goes to `restore_test_rows{table="keys"}`, so a shrinking cluster state alerts like a shrinking database.

`restore-test-etcd-offsite` runs the same checks every Sunday at 02:45 UTC on the copy in S3. It downloads the newest set from `etcd-snapshots/` with the backup job's AWS CLI image and the read-only `restore-test` IAM user, whose key ExternalSecrets syncs from Vault `infrastructure/restore-test`, and reports as `source="offsite"`.

## Safeguards

| Safeguard | What it stops |
|-----------|---------------|
| `restrict-restore-test` | The harness ServiceAccount touching any namespace but the sandbox or any volume but the sandbox's `nfs-restore-test` volumes, or creating a Restore that maps elsewhere, includes kinds beyond pods, claims and volumes, includes cluster resources, overwrites existing resources, skips the resource modifier or carries hooks. Velero acts with `cluster-admin`, so this policy is what limits a Restore |
| `deny-arrchitect-in-restore-sandbox` | Any Arrchitect resource in the sandbox, from anyone, Velero included |
| Kyverno exceptions | The sandbox shares `media`'s exemption from `require-run-as-nonroot` and `require-readonly-rootfs`, so applications run as they do in production |
| `weekly-full-cluster` exclusion | Copies of production Secrets, including Home Assistant's backup key, entering a backup |

Both policies are generated as native ValidatingAdmissionPolicies. `tests/kyverno/restore-test` covers them.

## Metrics

| Metric | Meaning |
|--------|---------|
| `restore_test_last_attempt_timestamp_seconds` | When the latest run for the target finished |
| `restore_test_last_success_timestamp_seconds` | When the target last passed; kept across failed runs |
| `restore_test_duration_seconds` | From creating the Restore to the end of the target's checks |
| `restore_test_data_age_seconds` | How old the restored backup was |
| `restore_test_restored_bytes` | Size of the target's restored volume |
| `restore_test_tier_passed{tier}` | 1 or 0 per tier that ran |
| `restore_test_fence_passed{fence}` | 1 or 0 per fence |
| `restore_test_dump_age_seconds` | How long before the backup the dump was written |
| `restore_test_rows{table}` | Row counts of the target's named tables |
| `restore_test_total_rows` | Rows across every table of a restored SQLite database |
| `restore_test_foreign_key_violations` | SQLite `foreign_key_check` findings |
| `restore_test_expected_failure{tier}` | 1 for a listed tier that still fails |
| `restore_test_expected_failure_resolved{tier}` | 1 for a listed tier that now passes |

The duration is a restore-test duration, not an RTO: it leaves out detection, importing into the live claim and the Argo CD sync. See [Alerting](alerting.md#restore-tests) for the alerts.

## Expected Failures

`expected_failures.json` lists tiers that fail because the backup itself is incomplete, each with a reason and an expiry date. A listed tier that fails does not fail its target, pushes `restore_test_expected_failure{tier}` and leaves `last_success` advancing. A listed tier that passes pushes `restore_test_expected_failure_resolved{tier}` and raises `RestoreTestExpectedFailureResolved`, so the entry gets removed. An entry past its expiry stops counting, and the failure alerts again.

The register is empty.

## Offsite

`restore-test-offsite` runs the same harness against the AWS copy each Sunday, half an hour after `velero-weekly-offsite` starts. Velero reads the offsite location with its own credentials, so the harness needs none, and the holder volumes amount to well under 1 GB a month of AWS egress. It reports as `source="offsite"`. Velero can mark a backup `Completed` even when it skipped volumes it could not read. The offsite backup of 2026-11-22 held none of the dumps, and only this test's first tier would have caught it.

## Running by Hand

```bash
kubectl -n backups create job --from=cronjob/restore-test restore-test-manual
kubectl -n backups logs -f job/restore-test-manual
```

To keep the sandbox for inspection, set `KEEP_SANDBOX`:

```bash
kubectl -n backups create job --from=cronjob/restore-test restore-test-keep --dry-run=client -o json \
  | jq '.spec.template.spec.containers[0].env += [{"name": "KEEP_SANDBOX", "value": "true"}]' \
  | kubectl apply -f -
```

Delete the sandbox and the Restore afterwards; the next run fails while the sandbox exists.

```bash
kubectl delete namespace restore-sandbox
kubectl -n backups delete restore -l app.kubernetes.io/name=restore-test
```

## Drilling the Alerts

Each alert can be made to fire without breaking a real target. Watch `alertmanager_notifications_total{integration="slack"}` and `alertmanager_notifications_failed_total` on Alertmanager to confirm delivery; every alert should send one firing and one resolved notification.

| Alert | How to trigger it |
|-------|-------------------|
| `RestoreTestStale` | Push a `drill` target whose last attempt and last success are both 55 hours old, so `RestoreTestFailed` stays quiet; fires after 10 minutes |
| `RestoreTestRowsDropped` | Push `restore_test_rows{table="drill"} 100` for that target, wait for a scrape, then push 10; fires after 10 minutes |
| `RestoreTestVolumesOrphaned` | Create an unbound PersistentVolume with `storageClassName: nfs-restore-test` and an NFS source at `192.0.2.1`; fires after an hour |
| `RestoreTestMissing`, `RestoreSandboxLingering` | Their windows are 30 and 6 hours, so send the alert to Alertmanager with `amtool alert add` and its real labels and annotations instead |

```bash
printf 'restore_test_last_attempt_timestamp_seconds %s\nrestore_test_last_success_timestamp_seconds %s\n' "$OLD" "$OLD" \
  | curl -X PUT --data-binary @- localhost:9091/metrics/job/restore_test/target/drill/source/local
curl -X DELETE localhost:9091/metrics/job/restore_test/target/drill/source/local
```

Delete the Pushgateway group and the volume afterwards. The harness leaves the volume alone, since it has no claim in the sandbox, so `RestoreTestVolumesOrphaned` keeps firing until it is gone.
