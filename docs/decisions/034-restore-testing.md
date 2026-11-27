# ADR-034: Automated Restore Testing

## Status

Accepted

## Context

Backups are taken, copied offsite and alerted on ([ADR-013](013-backup-strategy.md), [ADR-024](024-vault-integrated-storage.md), [ADR-025](025-garage-velero-local-backups.md)), but restores are proven only by hand. The [recovery coverage](../architecture/backups.md#recovery-coverage) lists most data as "application restore unverified", and the verified rows describe the drill that produced them, not today's backups. A dump that is empty, truncated, from a mismatched version or missing data the application needs would go unnoticed until the day it is restored. GitLab's 2017 outage is the best-known case. It had five backup and replication mechanisms, and nobody was responsible for testing any of them.

Published guidance sets floors and points beyond them. [CIS Control 11.5](https://cas.docs.cisecurity.org/en/latest/source/Controls11/) tests a sample of restores at least quarterly; [NIST SP 800-209](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-209.pdf) tests critical data at least monthly; [NIST CSF 2.0](https://www.nist.gov/document/csf-20-implementations-pdf) restores every type of data source at least annually. Google's [SRE book](https://sre.google/sre-book/data-integrity/) asks for recovery to be tested continuously, with an alert when the success heartbeat stops. AWS's [REL09-BP04](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_backing_up_data_periodic_recovery_testing_data.html) names restoring a backup without querying the data as an anti-pattern.

No Kubernetes backup tool verifies arbitrary applications after a restore. Velero's maintainers leave restore testing to an external harness ([velero#1688](https://github.com/velero-io/velero/issues/1688)), and its metrics record restore counts but no restore timestamp or duration.

Restoring into the production cluster carries hazards specific to it:

- The Velero server runs as `cluster-admin`, so whoever can create a Restore can write anything anywhere.
- Arrchitect writes to the media applications through their APIs. Its cache and its Roles are limited to `media`, so only that limit keeps it from acting on a restored copy.
- Argo CD, External Secrets and Kyverno act across namespaces through the API server, where network policy does not apply.
- A restored pod that mounts an NFS claim reaches that data whatever its network policy says.
- The `nfs-client` StorageClass keeps a deleted claim's directory (`reclaimPolicy: Retain`) and names it after the namespace and claim alone, so a second restore under the same names would reuse the first one's files.

## Decision

Velero stays the restore engine. A CronJob in `backups` runs a harness script, rendered by Argo CD from Git, that restores the latest backups into a throwaway `restore-sandbox` namespace, checks them in tiers, pushes per-target results to a Prometheus Pushgateway and deletes the sandbox.

**Targets.** The six SQLite dumps and the Tdarr archive on `config-backups`, the Uptime Kuma dump, the Authentik `pg_dump` archive, Home Assistant's native backups, the Vault Raft snapshot and the complete etcd set (snapshot, PKI and control-plane archives). Prometheus and Loki hold diagnostic data and are out of scope. Volumes backed up only as live files (qBittorrent, Grafana, Recyclarr state) join once they have a consistent export or holder.

**Schedule.** Every run tests every target.

| Cadence | Source | What runs |
|---|---|---|
| Nightly | `daily-stateful` on Garage; the etcd set on NFS | All targets except Vault |
| Weekly | `weekly-offsite` on S3; the etcd set on S3 | All targets except Vault |
| Monthly | S3 | The Vault snapshot into a scratch Vault |

The nightly run waits for that night's `daily-stateful` backup to complete; the weekly run follows `weekly-offsite` on Sunday. Both must finish before 06:15 UTC, when the UniFi devices' automatic firmware updates can drop NFS and DNS, and stay clear of kured (07:30 to 09:00 UTC) and the host patch window. The holder volumes total about 83 MB and the etcd snapshot about 250 MB (2026-11-27), so the weekly run downloads about 1.5 GB a month from S3, inside AWS's free 100 GB data-transfer allowance.

**Restore scope.** Each Restore names the schedule (`scheduleName`) so Velero picks its latest successful backup, maps the source namespaces into the sandbox, sets `includedResources: [pods, persistentvolumeclaims, persistentvolumes]`, `includeClusterResources: false` and `existingResourcePolicy: none`, and selects pods by the `app.kubernetes.io/component: backup-volume` label; Velero adds each pod's claims. A per-restore resource modifier strips scheduling constraints from the restored pods, clears each claim's binding to its production volume, which Velero keeps when volume objects are excluded, and moves the claims to `nfs-restore-test`, a StorageClass on the same provisioner with `reclaimPolicy: Delete`, `onDelete: delete` and no `pathPattern`, so each claim gets the provisioner's default directory, unique to its volume, and the directory is removed with it. Velero copies the production volume's `Retain` policy onto each new volume when it finishes a restore, so the harness sets the sandbox's volumes back to `Delete` straight after the restore and again before it deletes the sandbox. Velero restores pod volume data only when volumes are in the resource list, and with cluster resources excluded it never creates a volume object, so it cannot recreate one that points at production data. Deployments, application pods, network policies, routes, Services, ExternalSecrets, Arrchitect resources and `argoproj.io` kinds are never restored.

Home Assistant's `backups` volume gets its own holder Deployment on Home Assistant's node, because the claim is `ReadWriteOnce`, and the Home Assistant pod excludes that volume from file-system backup. Velero backs up a shared volume once, from the first pod it reaches, and the Home Assistant pod carries a Multus attachment to the IoT VLAN that Cilium policy does not govern.

**Isolation.**

- **Network**: The cluster-wide `baseline` policy denies all ingress and all egress except DNS for any new namespace, including traffic to the API server. The sandbox gets no allow policy; a checker container in the restored application's own pod queries it over localhost. The monthly Vault run is the one exception, with egress to AWS KMS and S3 only. The harness in `backups` gets a narrow path to the Pushgateway in `monitoring`.
- **Restores**: A Kyverno ValidatingPolicy admits a Restore from the harness ServiceAccount only if every namespace maps to `restore-sandbox`, it includes only pods, claims and volumes, it excludes cluster resources, its existing-resource policy is `none` and it carries the test resource modifier.
- **Arrchitect**: Its kinds are never restored, and a Kyverno ValidatingPolicy denies them in the sandbox. Every run fails unless Arrchitect still runs with `--watch-namespace=media`, no Arrchitect resource exists in the sandbox and a canary create of one, pointed at an unroutable address, is rejected.
- **Admission**: The sandbox takes the same Kyverno exceptions as the namespaces whose applications it tests and enforces Pod Security `baseline`, so tier 3 runs the production images with the security context production gives them.
- **Backups and GitOps**: `weekly-full-cluster` excludes the sandbox, so copies of production Secrets never enter a backup. Argo CD's annotation tracking ignores copies whose tracking annotation names another namespace, so restored objects neither change sync status nor get pruned.
- **Harness rights**: The harness ServiceAccount can create and delete namespaces and Restores; Kyverno limits both to the sandbox.
- **Data handling**: Checkers print counts and verdicts, never data, because Alloy ships every pod's logs to Loki and Loki is backed up. Decrypted Home Assistant archives and scratch PostgreSQL and Vault data live on `emptyDir`, never NFS. The Vault check uses a token whose policy reads only a canary path, because any token valid on the scratch Vault is valid on production.

**Checks.** Tiers run in order and fail closed; a tier that does not apply is recorded as such, never as a pass.

1. **Restored**: the Restore is `Completed` with no errors or warnings and a non-zero size.
2. **Intact**: SQLite `integrity_check` and `foreign_key_check`; `pg_restore --list` and a full read of the archive; `unzip -t` and an integrity check of Tdarr's inner database; decrypt and list Home Assistant's archive with its key from Vault; `vault operator raft snapshot inspect`; `etcdutl snapshot status` and the etcd job's own `recovery-<timestamp>.json` record.
3. **Usable**: the data loads into the product it belongs to. SQLite applications start on the restored database with the image the live Deployment runs. Authentik's archive restores into a scratch PostgreSQL of production's major version with `--exit-on-error`. The etcd snapshot restores into a single-member etcd on localhost. The Vault snapshot restores into a single-node Vault unsealed by the production KMS key.
4. **Answers**: an API or SQL query returns the expected objects.
5. **Fresh and plausible**: the backup is no older than its schedule allows, about 28 hours from Garage and 8 days from S3, the dump inside it was written no longer before the backup than its own schedule allows, and row counts do not fall from the previous runs beyond a tolerance. A faithful backup of a wiped database fails here, and so does a fresh backup of a dump job that stopped running.

Tiers 1, 2 and 5 apply to every target from the start and run before any application starts, because a newer image may migrate a database on startup. Tiers 3 and 4 are added per application, starting with Sonarr. An application that cannot start from its backup alone is recorded as a backup coverage gap.

**Evidence.** At the end of each run the harness pushes, per target and source, the attempt time, the last success, the duration, the data age, the tier results and the restored row counts to a Pushgateway with persistence. Alerts fire on per-target staleness beyond twice the run interval, on a failure (an attempt newer than the last success), on stale data, on falling counts, on any expected target missing (`absent()` guards generated from the target list), on a sandbox older than six hours and on orphaned `nfs-restore-test` volumes. Each alert is triggered on purpose once before it is relied on. The external Watchdog heartbeat covers Prometheus or Alertmanager being down.

The measured duration is a restore-test duration, not an RTO: it leaves out detection, the full namespace restore, the import into the live claim and the Argo CD sync. RTO evidence comes from drills.

**Failures.** A failed test is an incident. It is not retried automatically, and the runbook is corrected when a failure shows it is wrong. Known backup gaps live in an expected-failure register in Git (target, tier, reason, issue, expiry); a listed failure does not alert, an unlisted one does, and so does a listed one that starts passing or outlives its expiry. The harness and the [restore runbook](../runbooks/backup-and-restore.md) share the same import steps. The CronJob uses `concurrencyPolicy: Forbid`, `backoffLimit: 0` and an `activeDeadlineSeconds`, each Restore has a timeout, and a run that finds the sandbox still present or terminating fails instead of reusing it. A run started by hand can keep its sandbox for inspection.

**Drills.** Rebuild drills stay a separate, manual practice ([Phase 1.3](../roadmap/phase-1-foundations.md#13-verify-backup-and-power-alerts)). They should run on a cluster built from production's own definition, run these same checks against it and include one in-place restore of a single application by the runbook, which is the restore most likely to happen for real.

## Alternatives Considered

- **KubeStash `BackupVerifier`**: The only scheduled verification resource found. It replaces Velero rather than sitting beside it, its query checks target KubeDB databases and it needs an AppsCode licence.
- **Kasten K10 or CloudCasa**: Restore actions, transforms and hooks, but neither documents automated verification; CloudCasa's claim that it validates restores could not be confirmed in its technical documentation.
- **Small community harnesses (Kymaros, Kopiur drills)**: Useful reference designs, but young single-maintainer projects with no fencing for controllers that act through the API server.
- **Integrity checks only**: Kopia verify and SQLite checks on the staged dumps prove the bytes, not that an application can use them.
- **A weekly CronJob testing one application per run**: Each target would be tested about every nine weeks, below the monthly floor for critical data, and a single last-success value would hide a target that fails every time its turn comes. All holders together are small enough to test on every run.
- **A manifest written by each backup job**: Comparing restored data with values recorded at backup time proves fidelity, but needs a change to every backup job, cannot cover Home Assistant's own backups and adds little over Kopia's content hashing and the integrity checks. Trends between runs catch the failure that matters, a database that was wiped before it was backed up.
- **Job status from kube-state-metrics only**: No new component, and it catches a failing run, but it records no per-target duration, data age or counts.
- **A random older offsite point and a Kopia repository verify each month**: The 30-day offsite retention leaves only about three older points, and reading Velero's repository directly needs its password reviewed first. Revisit once the nightly and weekly runs are stable.
- **A permanent restore-test cluster**: Separate controllers and admission would remove most fencing, at the cost of a second always-on cluster on the one host; the lab VMs already push the host past 90% memory. Revisit with the second host and the [staging cluster](../roadmap/phase-6-platform-engineering.md#61-staging-cluster).

## Rationale

- **Velero already holds the backups**: No second backup system, and its restore primitives (schedule name, namespace mapping, resource and label selection, resource modifiers) express a narrow restore.
- **Tests prove use, not completion**: Each tier answers a way backups have failed in published incidents: empty or truncated dumps, version mismatches and data the application needed but the backup lacked.
- **Fence what can write**: The Restore guard, the Arrchitect checks and the default-deny baseline cover the paths network policy cannot, and the harness tests them on every run instead of trusting them.
- **Measurements age visibly**: A per-target last-verified time replaces statements in the docs that go stale silently.
- **Negligible cost**: Local runs read from the LAN; offsite runs stay far inside the free egress allowance.

## Consequences

- A Pushgateway joins the monitoring stack, with a network path from `backups`.
- The harness can create Restores, which act with Velero's `cluster-admin` rights; the Kyverno guard is what keeps that to the sandbox, so a change to the guard deserves the same review as a change to the harness.
- The sandbox carries the media namespaces' Kyverno exceptions while a run is active.
- For the length of a run, the sandbox holds copies of production credentials and personal data. It has no network access beyond its own pods, is excluded from backups and is deleted at the end; a sandbox that outlives six hours alerts.
- Each run creates and removes one directory per restored claim under the NFS provisioner's root.
- The Vault run needs egress to AWS KMS, a deliberate departure from HashiCorp's advice to test restores fully isolated; the default-deny baseline still keeps it away from the production Vault.
- Tests run the image production runs, so an application upgrade is tested against the backups the night after it deploys.
- The Jellyfin and Seerr dumps hold only their databases, so those targets may start in the expected-failure register until their backups capture what the applications need.
- Everything runs on one Proxmox host. Loss of the host is tested only when a drill restores onto other compute.
