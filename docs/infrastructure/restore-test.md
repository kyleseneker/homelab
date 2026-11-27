# Restore Test

Every night a CronJob restores the backup volumes into a throwaway `restore-sandbox` namespace, checks the restored data in tiers and reports the result per target to the [Pushgateway](pushgateway.md) ([ADR-034](../decisions/034-restore-testing.md)). It covers every backup volume Velero holds; [Phase 1.4](../roadmap/phase-1-foundations.md#14-automate-restore-tests) tracks the application checks, Authentik's database restore and the offsite, etcd and Vault runs still to come.

## Details

| Field | Value |
|-------|-------|
| Type | CronJob (`sourceType: git`) |
| Namespace | `backups`; each run works in `restore-sandbox` |
| Schedule | `30 3 * * *` (03:30 UTC daily) |
| Source | Latest completed `velero-daily-stateful` backup on Garage |
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
| `usable` | The application starts on a writable copy of the restored database, with the image and security context its live Deployment runs |
| `answers` | The application's API returns as many objects as the database holds |

The app check runs in one pod: the application, plus a checker container that queries it over localhost with a throwaway API key. It needs no network policy and reaches nothing outside the pod.

## Targets

| Target | Volume | Dump | `intact` check | Dump age limit | App check |
|--------|--------|------|----------------|----------------|-----------|
| `sonarr` | `media/config-backups` | `sonarr/sonarr.db` | SQLite; `Series` has rows; no foreign-key violations | 26 h | `/api/v3/series` |
| `radarr` | `media/config-backups` | `radarr/radarr.db` | SQLite; `VersionInfo` has rows | 26 h | `/api/v3/movie` |
| `prowlarr` | `media/config-backups` | `prowlarr/prowlarr.db` | SQLite; `VersionInfo` has rows | 26 h | `/api/v1/indexer` |
| `bazarr` | `media/config-backups` | `bazarr/db/bazarr.db` | SQLite | 26 h | -- |
| `jellyfin` | `media/config-backups` | `jellyfin/data/data/jellyfin.db` | SQLite | 26 h | -- |
| `seerr` | `media/config-backups` | `seerr/db/db.sqlite3` | SQLite | 26 h | -- |
| `tdarr` | `media/config-backups` | `tdarr/latest.zip` | ZIP CRCs; `DB2/SQL/database.db` present and sound | 50 h | -- |
| `uptime-kuma` | `monitoring/uptime-kuma-backups` | `kuma.db` | SQLite | 26 h | -- |
| `authentik` | `auth/authentik-backups` | `authentik.dump` | `pg_restore --list`, then a full read, with the image that wrote it | 26 h, from `completed-at` | -- |
| `home-assistant` | `home-automation/home-assistant-backups` | newest `*.tar` | Every member reads; `backup.json` says the backup is encrypted; the payload archive is present | 40 h, from `backup.json` | -- |

A SQLite check passes when `integrity_check` is `ok`, the database holds rows and every required table has rows. Foreign-key violations are reported for every database but fail only Sonarr, whose schema is known to have none. A dump's age comes from its modification time, which Velero's restore keeps, unless the target names a timestamp. Checkers run as the user of the holder that mounts the volume.

## Safeguards

| Safeguard | What it stops |
|-----------|---------------|
| `restrict-restore-test` | The harness ServiceAccount touching any namespace but the sandbox or any volume but the sandbox's `nfs-restore-test` volumes, or creating a Restore that maps elsewhere, includes kinds beyond pods, claims and volumes, includes cluster resources, overwrites existing resources, skips the resource modifier or carries hooks. Velero acts with `cluster-admin`, so this policy is what limits a Restore |
| `deny-arrchitect-in-restore-sandbox` | Any Arrchitect resource in the sandbox, from anyone, Velero included |
| Kyverno exceptions | The sandbox shares `media`'s exemption from `require-run-as-nonroot` and `require-readonly-rootfs`, so applications run as they do in production |
| `weekly-full-cluster` exclusion | Copies of production Secrets entering a backup |

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

The duration is a restore-test duration, not an RTO: it leaves out detection, importing into the live claim and the Argo CD sync. See [Alerting](alerting.md#restore-tests) for the alerts.

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
