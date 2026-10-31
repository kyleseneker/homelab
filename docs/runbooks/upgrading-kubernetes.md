# Upgrading Kubernetes

The bootstrap roles initialize nodes; changing their version variables does **not** perform a cluster upgrade. The separate `k8s-upgrade.yml` playbook performs an explicit, staged upgrade. Use a maintenance window and upgrade the control plane, then each worker. Update the repository pins and rebuild the Packer template only after the running cluster passes verification.

Production and the shared image defaults use Kubernetes **1.35.10**, which enters maintenance mode on 2026-12-28 and reaches end of life on 2027-02-28. The lab has completed intermediate steps through **1.36.5**, which is supported until 2027-06-28. This is a migration backlog item, not a recommendation for a new cluster. Select a supported destination using the [release history](https://kubernetes.io/releases/patch-releases/), then plan every intervening minor release. kubeadm does not support skipping minors. Follow the [upstream upgrade procedure](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/) for each step.

## Current platform and verified rehearsal

| Component | Production | Restore lab |
|---|---|---|
| Kubernetes API / kubeadm / kubelet / kubectl packages | 1.35.10 | 1.36.5 |
| containerd | 2.2.2 | 2.3.5 |
| Cilium | 1.20.4 | 1.20.4 |
| Gateway API CRDs | 1.6.3 | 1.4.0; Gateway controller disabled |
| etcd | 3.6.6 | 3.6.8 |
| Kyverno | 1.17.1, chart 3.7.1 | Not installed |

The lab passed the 1.31.4 → 1.32.13 → 1.33.13 control-plane-first upgrades through the shared playbook. Both nodes report the target version and Ready, kube-proxy remains absent, and all 14 ArgoCD Applications returned to Synced/Healthy. Cross-node Service traffic, Pod DNS, public HTTPS, private-network isolation, Sonarr records, Prowlarr integration, Authentik queries and Vault/ESO Secret recreation passed at both steps. On 1.33.13, qBittorrent also retained its torrent identities, categories and transfer history; authentication checks passed and transfers remained stopped with zero peers. Matching etcd 3.5.24 tools saved a snapshot, verified its integrity and restored it into an isolated data directory without starting a second server.

The 1.33.13 → 1.34.12 step moved etcd to 3.6. The [etcd 3.6 upgrade guide](https://etcd.io/docs/v3.6/upgrades/upgrade_3_6/) requires 3.5.32 or later first, so the lab etcd static Pod image was raised from 3.5.24-0 to 3.5.35-0 and verified healthy before the playbook ran. kubeadm then moved etcd to 3.6.5 and replaced `--experimental-initial-corrupt-check` with `--feature-gates=InitialCorruptCheck=true`. Once every member runs 3.6, binary rollback is no longer possible; recovery is a snapshot restore or the stopped-VM backups. At 1.34.12, both nodes report the target version and Ready, kube-proxy remains absent, Cilium reports OK and all 14 ArgoCD Applications returned to Synced/Healthy. Cross-node Service traffic in both directions, Pod DNS, public HTTPS and blocked access to the production API and NAS passed, and the lab Sonarr and Prowlarr configurations reconciled. The Sonarr record, Authentik, Vault/ESO Secret recreation and qBittorrent checks were not repeated at this step. etcd 3.6.5 tools saved a snapshot, verified its integrity and restored it into an isolated data directory without starting a second server.

In the 1.34.12 → 1.35.9 step, kubelet 1.35 no longer accepts `--pod-infra-container-image`, which kubeadm 1.31 had written to both nodes' `/var/lib/kubelet/kubeadm-flags.env`. `kubeadm upgrade apply` and `kubeadm upgrade node` rewrote that file without the flag before the new kubelet started, keeping the previous copy under `/etc/kubernetes/tmp/`. kubeadm 1.35 also rejects cgroup v1 during preflight; both lab nodes use cgroup v2. etcd moved from 3.6.5 to 3.6.6. At 1.35.9 the same platform, network, policy-enforcement and operator checks as the Cilium step passed, and etcd 3.6.6 tools completed the snapshot save, integrity check and isolated restore. The application-level record checks were not repeated.

In the 1.35.9 → 1.36.5 step, etcd moved from 3.6.6 to 3.6.8. The release's urgent notes rename the kube-controller-manager metric `volume_operation_total_errors` to `volume_operation_errors_total` and change the scheduler PreBind plugin API; no dashboards, alerts or custom schedulers here use either. At 1.36.5 the same platform, network, policy-enforcement, operator and etcd snapshot checks passed. The application-level record checks were not repeated.

The lab then upgraded Cilium 1.19.1 → 1.19.10 → 1.20.4 through [the Cilium procedure below](#upgrade-cilium). Pre-flight policy validation passed at each hop. On 1.20.4 both agents report OK and all 14 Applications remained Synced/Healthy. Cross-node Service and Pod traffic, Pod DNS, public HTTPS and the production API/NAS block passed. A pod under the `restore-sonarr` deny-all policy could not reach the internet or Sonarr, and the lab operators still reconciled Sonarr and Prowlarr through their allow rules. Gateway API is disabled in the lab, so the Gateway API CRD and TLSRoute changes were not exercised.

[Cilium 1.20's compatibility table](https://docs.cilium.io/en/v1.20/network/kubernetes/compatibility/) lists Kubernetes 1.33 through 1.36. Production moved from Cilium 1.19, whose [table](https://raw.githubusercontent.com/cilium/cilium/v1.19.1/Documentation/network/kubernetes/compatibility.rst) lists 1.31 through 1.34, to 1.20 before its 1.35 step. The [1.36 upgrade guide](https://v1-36.docs.kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/) covers the latest single-minor transition. Lab and production API deprecation metrics showed no requests to APIs with a scheduled removal release; this observation does not cover unexercised clients.

The lab currently omits production admission webhooks, Gateway routing, GPU and NFS workloads, and uses a different containerd patch line. Rehearse those integrations before production maintenance. A temporary clone of template `9011` installed 1.33.13 through the shared prerequisite role, joined through the worker role, rebooted Ready, and passed cross-node networking and isolation checks. Its short-lived join token was revoked; the test node was removed. No bootstrap tokens remain in the lab. The bootstrap roles now revoke initialization tokens and reject package-version changes on initialized nodes. Template `9011` still contains the 1.31.4 baseline; build and verify a destination-version image before completing the migration. The next minor to rehearse is 1.37. Cilium 1.20 lists Kubernetes 1.33 through 1.36, so that step first needs a Cilium release tested with 1.37.

CI renders the manifests with both production and lab Kubernetes capabilities and validates both schema targets, reading their versions from Ansible inventory. Production package, Packer, CLI and etcd-backup pins remain at the production baseline until its own tested cutover.

Production completed 1.31.4 → 1.32.13 through the same playbook after a fresh off-host recovery set and a verified stopped backup of the control-plane VM. Three single-replica PDBs with `minAvailable: 1` (authentik-server, the VPA recommender and the Prometheus operator) would have blocked every drain; they now use `maxUnavailable: 1` like the other repository PDBs. Draining node-2 moved the single-replica Kyverno, whose fail-closed webhook refused new pods in other namespaces until it was ready on node-3. After the control-plane step, the Cilium 1.19.1 agent on node-2 logged `BUG: Unexpected failure to delete backends` and kept a deleted CoreDNS backend for the cluster DNS Service, so about half of its DNS lookups failed and authentik-server never became ready. Restarting that agent rebuilt the correct backends, and the worker play then finished. At 1.32.13 all three nodes are Ready, etcd 3.5.24 is healthy, all 54 Applications are Synced/Healthy, the Gateway serves its 19 routes, the GPU node exposes its devices to Jellyfin and Tdarr, and all 13 NFS claims are bound. The drain also exposed that the pinned MinIO image can no longer be pulled from quay.io; MinIO runs only where the image is cached.

Production then upgraded Cilium 1.19.1 → 1.19.10 with the `cilium` CLI after a passing pre-flight (49 policies valid). All agents report OK, every agent's backends for the cluster DNS Service match the `kube-dns` endpoints, the Gateway serves its 19 routes and all Applications are Synced/Healthy. Its Helm history shows the original 1.16.5 install upgraded directly to 1.19.1 in March 2026, skipping two minors. The next Cilium step is 1.20.

Production then completed 1.32.13 → 1.33.13 after a fresh recovery set and a verified control-plane VM backup, running the control-plane and worker plays separately. After the control-plane step every Cilium agent's DNS backends matched the replaced CoreDNS endpoints and short-name lookups succeeded. The drains finished without eviction refusals or webhook-blocked Pod creation. etcd remains 3.5.24. All three nodes are Ready at 1.33.13, all 55 Applications are Synced/Healthy, and the Gateway, GPU, NFS, Kyverno, Garage and Velero checks match the pre-upgrade baseline.

Production then completed 1.33.13 → 1.34.12. After a fresh recovery set and control-plane VM backup, its etcd static Pod image was raised from 3.5.24-0 to 3.5.35-0; kubeadm then moved etcd to 3.6.5 and converted both experimental flags. The first worker drain stalled: one Kyverno admission replica could not be rescheduled because the remaining worker's CPU requests were at 99% and the control-plane taint blocked node-1. Allowing the admission controller on the control plane released the drain, and the rerun finished without eviction refusals. Garage was unavailable while its node drained, as ADR-025 expects; a Kopia maintenance run failed during that window and the next run succeeded. The etcd backup job now uses the 3.6.5 image and produced a verified recovery set, and the restore procedure uses `etcdutl`. All three nodes are Ready at 1.34.12, the admission replicas run one per node, and all 55 Applications are Synced/Healthy with the baseline checks intact.

Production then moved its Gateway API CRDs from 1.4.0 to 1.5.1, one minor at a time ahead of Cilium 1.20. Every version Cilium 1.19 requires at operator startup remains served; ReferenceGrant adds `v1` and keeps `v1beta1` as its storage version. A server-side dry run passed and ArgoCD synced the CRDs. A restarted 1.19.10 operator found the required resources and kept Gateway API enabled. The Gateway stayed Programmed, all 18 HTTPRoutes were Accepted with resolved references, every hostname answered over HTTPS and all 54 Applications are Synced/Healthy. At startup the operator logs one `no kind is registered for the type v1alpha2.TLSRouteList` error per Service, because its backend-Service handler lists TLSRoutes even when no TLSRoute CRD is installed. Loki shows the same burst on 2026-10-25 with the 1.4.0 CRDs.

Production then moved the CRDs to 1.6.3, which passed the same checks after another 1.19.10 operator restart, and added the TLSRoute and BackendTLSPolicy CRDs immediately before upgrading Cilium 1.19.10 → 1.20.4. ArgoCD briefly reported `gateway-api` Degraded from a health evaluation taken before the new CRDs were Established; its next reconcile cleared it. Pre-flight validated all 41 policies. The first `cilium upgrade` updated the agent, Envoy and operator workloads and their cluster RBAC, then failed on server-side apply conflicts in `cilium-config` and the `cilium-operator-ztunnel` Role, because the 2026-10-25 Helm attempt had left `helm` as a co-owner of fields on 14 Cilium objects. Removing those stale `helm` managedFields entries and rerunning the same command completed Helm revision 7. With Gateway API enabled, the 1.20 chart forces `bpf-lb-sock-hostns-only` and `bpf-lb-algorithm-annotation` to `true`, so socket load balancing now covers only the host namespace. The workloads carry no ConfigMap checksum, so the agents, Envoy and operator needed a rolling restart before `cilium_drift_checker_config_delta` reached 0. At 1.20.4 all agents report OK with 3/3 cluster health and kube-dns backends matching its endpoints. The operator found every required Gateway API resource without the 1.19 TLSRoute errors. The Gateway stayed Programmed with all 18 HTTPRoutes Accepted, every hostname answered over HTTPS, and all 13 in-cluster Blackbox probes through the Gateway succeeded throughout the upgrade. Prometheus reported all 59 targets up, a cross-node ClusterIP request succeeded, a request into a namespace its policies exclude timed out, and all 54 Applications are Synced/Healthy.

Production then completed 1.34.12 → 1.35.10 after a fresh recovery set and a verified stopped backup of the control-plane VM, running the control-plane and worker plays separately. Every node already used cgroup v2 and the `pause:3.10.1` sandbox image that kubeadm 1.35.10 expects. kubeadm rewrote each node's `kubeadm-flags.env` without `--pod-infra-container-image` before the new kubelet started, moved etcd from 3.6.5 to 3.6.6 and CoreDNS from 1.12.1 to 1.13.1. After the CoreDNS rollout every Cilium agent's DNS backends matched the ready `kube-dns` endpoints. Both worker drains finished without eviction refusals. The Kyverno admission controller's anti-affinity is only preferred, so the drains left two replicas on node-1 until a rolling restart restored one per node. ArgoCD briefly reported two Applications Unknown when server-side dry runs failed during the control-plane restart and while webhooks moved during drains; both cleared on their next reconcile. At 1.35.10 all three nodes are Ready, Cilium reports 3/3 cluster health, all 18 HTTPRoutes are Accepted, the GPU node exposes its devices to Jellyfin and Tdarr, all 27 PVCs including 14 NFS claims are bound, Vault is unsealed with all 28 ExternalSecrets Ready, all 59 Prometheus targets and 13 Blackbox probes are up, and all 54 Applications are Synced/Healthy. A post-upgrade recovery set completed with the 3.6.5 tooling, which the backup job then replaced with the 3.6.6 image.

Production template `9000` was then rebuilt by Packer at 1.35.10 from the checksum-verified 24.04.2 installer. It had still been the legacy raw cloud image, which the cluster playbook's default `packer_template` path cannot bootstrap; a verified stopped backup of that image is retained on Proxmox. Two temporary full clones booted with cloud-init DHCP addresses and the administrator key, then rebooted. kubeadm, kubelet and kubectl 1.35.10 were held; the containerd, swap, cgroup, kernel-module, NFS and iGPU prerequisites passed; APT updated without warnings. Machine IDs, system UUIDs and SSH host keys were unique and stable across reboot, the build key was rejected, password and root SSH login were disabled, and no kubeadm credentials, cluster PKI or etcd data were present. The unpinned `containerd.io` package installed 2.4.2, whose default sandbox image `pause:3.10.2` differs from kubeadm 1.35.10's `pause:3.10.1`; the running nodes keep 2.2.2. A fresh node join from the template has not been demonstrated.

## Upgrade Cilium

Cilium supports upgrades only between consecutive minor releases, and its [upgrade guide](https://docs.cilium.io/en/v1.20/operations/upgrade/) requires the latest patch of the current minor first. Before each hop:

1. Save the release values with `helm get values cilium -n kube-system -o yaml`. Do not use `--reuse-values` across minors. Releases installed by `cilium install` include values the CLI chose, such as `routingMode` and `cluster.name`.
2. Check the target's upgrade notes against the cluster. For 1.20: no `cilium.io/v2alpha1` CiliumNodeConfig objects, no Kafka or `l7` policy rules, Gateway API CRDs at v1.6.1 or later when `gatewayAPI.enabled` is true, and no dashboards or alerts using the removed operator IPAM metrics. Production's Gateway API CRDs come from the shared `k8s/components/gateway-api`. The 1.20 operator also requires TLSRoute and BackendTLSPolicy at `v1`, which that directory now vendors; without them it disables Gateway API. Cilium 1.19 detects TLSRoute by version name without checking whether the version is served, and the v1.6 TLSRoute CRD still lists an unserved `v1alpha2`, so a 1.19 operator restarted after that CRD is installed would set up watches for an API the server does not serve. Remove TLSRoute, with the `gateway-api` Application paused, before any rollback to 1.19.
3. Run the pre-flight check. Pass the API server address because kube-proxy is absent. Wait until its DaemonSet matches the agent count and its validator Deployment is ready, then delete it:

```bash
helm template cilium cilium --repo https://helm.cilium.io --version <target> \
  --namespace kube-system --set preflight.enabled=true --set agent=false \
  --set operator.enabled=false --set k8sServiceHost=<api-ip> --set k8sServicePort=6443 \
  > preflight.yaml
```

4. Upgrade with the saved values. Set `upgradeCompatibility` to the Cilium minor whose defaults the running configuration uses. That is normally the first installed version, but production was installed at 1.16.5 and upgraded to 1.19.1 without it, so its configuration already uses 1.19 defaults; use `1.19` for both clusters. Helm owns the lab release:

```bash
helm upgrade cilium cilium --repo https://helm.cilium.io --version <target> \
  --namespace kube-system -f values.yaml --set upgradeCompatibility=<initial-minor>
```

   Production's objects belong to the `cilium` field manager from `cilium install`, so Helm 4's server-side apply fails there with field conflicts. That 2026-10-25 attempt still left `helm` as a co-owner of fields on 14 objects, which blocked the CLI's 1.20.4 apply until the stale entries were removed. A conflicting apply can leave earlier objects updated, so compare workload images with the Helm history after any failed run. Upgrade production with the `cilium` CLI, as `make cilium-upgrade` does. Preview the result with `--dry-run-helm-values` first:

```bash
KUBECONFIG=kubeconfig cilium upgrade --version <target> \
  --values ansible/roles/k8s_control_plane/files/cilium-values.yml \
  --set k8sServiceHost=192.168.10.50 --set k8sServicePort=6443 \
  --set upgradeCompatibility=1.19
```

5. Wait for the `cilium`, `cilium-envoy` and `cilium-operator` rollouts. The workloads carry no ConfigMap checksum, so after a `cilium-config` change restart all three, as `make cilium-upgrade` does, and confirm `cilium_drift_checker_config_delta` in `cilium-dbg metrics list` is 0. Check `cilium-dbg status`, cross-node Service traffic, DNS and policy enforcement before the next hop. Roll back one minor at a time: `helm rollback cilium <revision> -n kube-system` in the lab, and `cilium upgrade --version <previous>` in production, where Helm's apply conflicts with the CLI's field ownership.

## Upgrade containerd

Every node holds `containerd.io` at `k8s_prereqs_containerd_version`, and the bootstrap role refuses to change an initialized node's runtime. Check the [containerd support table](https://github.com/containerd/containerd/blob/main/RELEASES.md) against both the current and next Kubernetes minor, then upgrade one minor at a time with the rolling playbook, control plane first:

```bash
cd ansible
ansible-playbook --vault-password-file ../.vault-password \
  -i inventory/homelabk8s01/hosts.yml playbooks/containerd-upgrade.yml \
  -e containerd_upgrade_version=<target>
```

It rejects skipped minors and downgrades, drains each node through the eviction API, installs and holds the target package while keeping the existing `config.toml`, restarts containerd and kubelet, and uncordons only after the node reports the target runtime and Ready. A failed node stays cordoned. Update the pin, rebuild the Packer template and record the version together.

## Before each minor upgrade

- Confirm the live versions with `kubectl get nodes -o wide` and `kubectl version`; do not infer them from Git.
- Verify a recent off-host etcd snapshot, `/etc/kubernetes/pki` backup, and application data backup can be restored. A completed Velero backup alone does not establish this. Follow [Backup and Restore](backup-and-restore.md).
- Check that each worker's PDB-protected Pods would fit elsewhere: draining one worker moves its Pods to the other worker and any workloads that tolerate the control plane. Compare CPU requests with allocatable capacity.
- Confirm no PodDisruptionBudget reports zero allowed disruptions, and note single-replica admission webhooks with `failurePolicy: Fail` on the nodes to be drained.
- After the control-plane step, confirm every Cilium agent's backends for the cluster DNS Service match the `kube-dns` endpoints (`cilium-dbg service list`). Restart an agent that kept a deleted backend.
- Before the 1.34 step, raise etcd to 3.5.32 or later; the [etcd 3.6 upgrade guide](https://etcd.io/docs/v3.6/upgrades/upgrade_3_6/) requires it before kubeadm 1.34 moves etcd to 3.6. Update the etcd backup tooling to 3.6 `etcdutl` with it.
- Before the 1.35 step, confirm every node uses cgroup v2: `stat -fc %T /sys/fs/cgroup` reports `cgroup2fs`. kubeadm 1.35 fails preflight on cgroup v1.
- Check the installed Cilium release's compatibility with both the current and next Kubernetes minor, plus Gateway API CRDs, containerd, Kyverno, and other admission webhooks. Use the [Cilium compatibility documentation](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/) for the actual installed release.
- Verify node readiness, ArgoCD health, storage mounts, and backup jobs. Review the target release's removed APIs and [version skew rules](https://kubernetes.io/releases/version-skew-policy/).
- Inspect `kubectl get pdb -A` and workloads on the node to be drained. Local-path volumes stay on their original node; the sole GPU worker cannot transfer GPU workloads to another node. Plan downtime and resolve any PDB that blocks maintenance before proceeding. Do not use `--disable-eviction` to bypass it.

## Run the shared upgrade playbook

After selecting an exact patch and verifying a recovery checkpoint, use the separate upgrade playbook. For example, the lab's verified 1.35.9 → 1.36.5 step used:

```bash
cd ansible
ansible-playbook --vault-password-file ../.vault-password \
  -i inventory/homelabrestore01/hosts.yml playbooks/k8s-upgrade.yml \
  -e k8s_upgrade_version=1.36.5 \
  -e '{"k8s_upgrade_backup_verified": true}'
```

The backup flag records a check performed by the operator; it does not create or verify backups. For the lab, use the [data checkpoint and controller pause](restore-lab.md#pausing-the-gitops-managed-lab), then verified stopped-VM backups of both nodes. Restart the nodes before running the playbook. Resume applications only after both nodes pass verification.

The role rejects skipped minors, downgrades and workers upgraded ahead of the API server. It upgrades the single control plane first, then workers serially, draining through the eviction API and leaving a failed node cordoned. It explicitly skips the kube-proxy addon because Cilium supplies that function. It never bypasses a PDB. The commands below describe the same procedure for diagnosis and manual recovery.

A lab-only upgrade changes the lab inventory's version overrides after verification. Keep production and shared Packer defaults at their actual deployed baseline until their own upgrade is verified. An unjoined clone can replace held image packages with the inventory-selected version before joining. An initialized node must use the upgrade playbook. Rebuild and boot-test the destination-version template before completing the migration.

## Configure the package repository on each node

Select an exact patch and Debian package version for the **next** minor. Run this on the control plane first and later on each worker. Replace the values below before using them:

```bash
TARGET_MINOR='1.36'
TARGET_VERSION='1.36.REPLACE_ME'
TARGET_PACKAGE="${TARGET_VERSION}-1.1"

sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/v${TARGET_MINOR}/deb/Release.key" \
  | sudo tee "/etc/apt/keyrings/kubernetes-v${TARGET_MINOR}.asc" >/dev/null
printf 'deb [signed-by=/etc/apt/keyrings/kubernetes-v%s.asc] https://pkgs.k8s.io/core:/stable:/v%s/deb/ /\n' \
  "$TARGET_MINOR" "$TARGET_MINOR" \
  | sudo tee /etc/apt/sources.list.d/kubernetes-upgrade.list
sudo apt-get update
apt-cache madison kubeadm
```

Verify `TARGET_PACKAGE` exists in the output. The previous minor's repository may remain during the transition; remove its obsolete entry after completing that minor upgrade. Update `TARGET_PACKAGE` if the published package suffix differs.

## Upgrade the control plane

On the control plane:

```bash
sudo apt-mark unhold kubeadm
sudo apt-get install -y "kubeadm=${TARGET_PACKAGE}"
sudo apt-mark hold kubeadm
sudo kubeadm upgrade plan
sudo kubeadm upgrade apply "v${TARGET_VERSION}" --skip-phases=addon/kube-proxy
```

From the administrator machine, drain the control plane before upgrading its kubelet. The cluster has one control plane, so API availability during maintenance is limited:

```bash
kubectl drain homelabk8s01-node-1 --ignore-daemonsets --delete-emptydir-data
```

On the control plane:

```bash
sudo apt-mark unhold kubelet kubectl
sudo apt-get install -y "kubelet=${TARGET_PACKAGE}" "kubectl=${TARGET_PACKAGE}"
sudo apt-mark hold kubelet kubectl
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```

From the administrator machine:

```bash
kubectl uncordon homelabk8s01-node-1
kubectl wait --for=condition=Ready node/homelabk8s01-node-1 --timeout=300s
kubectl get --raw='/readyz?verbose'
```

## Upgrade each worker

Complete all steps and verify workloads on one worker before starting the next. From the administrator machine:

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

On that worker, configure the same target package repository and variables as above, then run:

```bash
sudo apt-mark unhold kubeadm
sudo apt-get install -y "kubeadm=${TARGET_PACKAGE}"
sudo apt-mark hold kubeadm
sudo kubeadm upgrade node
sudo apt-mark unhold kubelet kubectl
sudo apt-get install -y "kubelet=${TARGET_PACKAGE}" "kubectl=${TARGET_PACKAGE}"
sudo apt-mark hold kubelet kubectl
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```

From the administrator machine:

```bash
kubectl uncordon <node-name>
kubectl wait --for=condition=Ready node/<node-name> --timeout=300s
```

## Verify and record the completed step

Check node versions, system pods, Cilium status, DNS, Gateway routes, a GPU transcode, NFS access, ArgoCD application health, and a new backup. Confirm the kubeadm-selected etcd image with `sudo kubeadm config images list --kubernetes-version v<version>` and update the etcd backup tooling to the corresponding etcd version. A Kubernetes minor upgrade can change etcd too.

Record the verified Kubernetes version consistently in:

- `ansible/group_vars/all/vars.yml` and the `k8s_prereqs` / `k8s_control_plane` role defaults
- Packer defaults and the Packer variable example (plus your ignored local variable file)
- CI schema validation versions and any rendered-manifest validation default
- The etcd backup image, documentation, and roadmap evidence

Rebuild and boot-test a clone of the updated Packer template before using it for replacement workers. Repeat the entire process for the next minor until reaching the supported destination.

## If an upgrade fails

Keep the affected node cordoned. Inspect `journalctl -u kubelet`, `kubectl get pods -n kube-system`, Cilium logs, and `/readyz?verbose`. Do not rerun the bootstrap playbook as an upgrade repair or blindly downgrade packages/etcd data. Use the target release's kubeadm recovery guidance and the verified backups. Escalate storage and PDB failures as maintenance issues rather than forcing deletion of stateful pods.
