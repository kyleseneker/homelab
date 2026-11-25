# Kured

Kured (Kubernetes Reboot Daemon) reboots nodes after their automatic updates need a restart, as part of the patching policy in [ADR-032](../decisions/032-os-patching.md). The Ubuntu nodes install security and regular updates daily with `unattended-upgrades`, which never reboots on its own; when an update needs a restart, Ubuntu creates `/var/run/reboot-required`. Kured sees the file, drains the node, reboots it and uncordons it when it returns, one node at a time.

## Details

| Field | Value |
|-------|-------|
| Chart | `kured` |
| Repository | <https://kubereboot.github.io/charts> |
| Version | 6.1.0 |
| Namespace | `kube-system` |

## Key Configuration

- **Window**: 01:30 to 03:00 America/Chicago, every day, checked every 10 minutes. It avoids the UniFi firmware updates around midnight, the evening backups and the Proxmox host's patch window at 03:30 on the first Sunday of each month. Nodes update around 06:30, so a node that needs a restart reboots the following night.
- **One at a time**: a lock on the DaemonSet allows one reboot at a time. The lock expires after 2 hours (`lockTtl`) if a node never comes back.
- **Blocked by alerts**: no reboot starts while Prometheus has a firing warning or critical alert. A node that is still recovering from the previous reboot blocks the next one. Kured ignores `Watchdog`, `InfoInhibitor`, `NodeRebootPending` (it only clears after the reboot it reports) and the info-severity alerts, which Alertmanager holds back unless a warning fires in the same namespace. Kured filters by alert name only, so `alertFilterRegexp` lists the info alerts by name; a chart update that adds one needs it added there.
- **Drain**: drains respect PodDisruptionBudgets and give up after 30 minutes. A failed drain does not reboot (`forceReboot: false`); kured tries again at the next check. A node waiting to reboot is tainted `weave.works/kured-node-reboot:PreferNoSchedule`, so pods drained from another node avoid it.
- **Least privilege**: kured reboots by sending systemd its reboot signal (`rebootMethod: signal`, a clean reboot through `reboot.target`). The container is not privileged: it adds only `KILL`, drops all other capabilities and reads the sentinel through a read-only `hostPath` mount of `/var/run`. It needs `hostPID` to signal the host's PID 1, and an `Unconfined` AppArmor profile because containerd's default profile only lets a container signal processes under the same profile; under it the signal fails with `permission denied` after the node has already drained. Kyverno's `restrict-security-profiles` excludes `kube-system`, so this needs no exception.
- **Control plane**: a toleration runs it on node-1 too. Rebooting node-1 makes the API unavailable for a few minutes; workloads keep running.

## Checking

```bash
kubectl -n kube-system logs ds/kured --all-containers --since=24h
kubectl get nodes -o custom-columns=NAME:.metadata.name,REBOOT_NEEDED:.metadata.annotations.weave\.works/kured-most-recent-reboot-needed
```

Prometheus scrapes `kured_reboot_required` from each node through the chart's ServiceMonitor.

## Upstream Documentation

<https://kured.dev/docs/>
