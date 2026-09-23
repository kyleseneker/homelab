# Upgrading Kubernetes

The bootstrap roles initialize nodes; changing their version variables does **not** perform a cluster upgrade. The separate `k8s-upgrade.yml` playbook performs an explicit, staged upgrade. Use a maintenance window and upgrade the control plane, then each worker. Update the repository pins and rebuild the Packer template only after the running cluster passes verification.

Production and the shared image defaults still use Kubernetes **1.31.4**, an unsupported release. The lab has completed intermediate steps through **1.33.13**, which is also end-of-life and is not the destination. This is a migration backlog item, not a recommendation for a new cluster. Select a supported destination using the [release history](https://kubernetes.io/releases/patch-releases/), then plan every intervening minor release. kubeadm does not support skipping minors. Follow the [upstream upgrade procedure](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/) for each step.

## Current platform and verified rehearsal

| Component | Production | Restore lab |
|---|---|---|
| Kubernetes API / kubeadm / kubelet / kubectl packages | 1.31.4 | 1.33.13 |
| containerd | 2.2.2 | 2.3.5 |
| Cilium | 1.19.1 | 1.19.1 |
| Gateway API CRDs | 1.4.0 | 1.4.0; Gateway controller disabled |
| etcd | 3.5.15 | 3.5.24 |
| Kyverno | 1.17.1, chart 3.7.1 | Not installed |

The lab passed the 1.31.4 → 1.32.13 → 1.33.13 control-plane-first upgrades through the shared playbook. Both nodes report the target version and Ready, kube-proxy remains absent, and all 14 ArgoCD Applications returned to Synced/Healthy. Cross-node Service traffic, Pod DNS, public HTTPS, private-network isolation, Sonarr records, Prowlarr integration, Authentik queries and Vault/ESO Secret recreation passed at both steps. On 1.33.13, qBittorrent also retained its torrent identities, categories and transfer history; authentication checks passed and transfers remained stopped with zero peers. Matching etcd 3.5.24 tools saved a snapshot, verified its integrity and restored it into an isolated data directory without starting a second server.

[Cilium's pinned 1.19.1 compatibility table](https://raw.githubusercontent.com/cilium/cilium/v1.19.1/Documentation/network/kubernetes/compatibility.rst) includes Kubernetes 1.32 and 1.33. The [1.33 upgrade guide](https://v1-33.docs.kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/) covers the latest single-minor transition. Lab and production API deprecation metrics showed no requests to APIs marked for removal in 1.33; this observation does not cover unexercised clients.

The lab currently omits production admission webhooks, Gateway routing, GPU and NFS workloads, and uses a different containerd patch line. Rehearse those integrations before production maintenance. A temporary clone of template `9011` installed 1.33.13 through the shared prerequisite role, joined through the worker role, rebooted Ready, and passed cross-node networking and isolation checks. Its short-lived join token was revoked; the test node was removed. No bootstrap tokens remain in the lab. The bootstrap roles now revoke initialization tokens and reject package-version changes on initialized nodes. Template `9011` still contains the 1.31.4 baseline; build and verify a destination-version image before completing the migration. The next minor to rehearse is 1.34; choose the supported destination against the complete controller compatibility matrix.

CI renders the manifests with both production and lab Kubernetes capabilities and validates both schema targets, reading their versions from Ansible inventory. Production package, Packer, CLI and etcd-backup pins remain at the production baseline until its own tested cutover.

## Before each minor upgrade

- Confirm the live versions with `kubectl get nodes -o wide` and `kubectl version`; do not infer them from Git.
- Verify a recent off-host etcd snapshot, `/etc/kubernetes/pki` backup, and application data backup can be restored. A completed Velero backup alone does not establish this. Follow [Backup and Restore](backup-and-restore.md).
- Check the installed Cilium release's compatibility with both the current and next Kubernetes minor, plus Gateway API CRDs, containerd, Kyverno, and other admission webhooks. Use the [Cilium compatibility documentation](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/) for the actual installed release.
- Verify node readiness, ArgoCD health, storage mounts, and backup jobs. Review the target release's removed APIs and [version skew rules](https://kubernetes.io/releases/version-skew-policy/).
- Inspect `kubectl get pdb -A` and workloads on the node to be drained. Local-path volumes stay on their original node; the sole GPU worker cannot transfer GPU workloads to another node. Plan downtime and resolve any PDB that blocks maintenance before proceeding. Do not use `--disable-eviction` to bypass it.

## Run the shared upgrade playbook

After selecting an exact patch and verifying a recovery checkpoint, use the separate upgrade playbook. For example, the lab's verified 1.32.13 → 1.33.13 step used:

```bash
cd ansible
ansible-playbook --vault-password-file ../.vault-password \
  -i inventory/homelabrestore01/hosts.yml playbooks/k8s-upgrade.yml \
  -e k8s_upgrade_version=1.33.13 \
  -e '{"k8s_upgrade_backup_verified": true}'
```

The backup flag records a check performed by the operator; it does not create or verify backups. For the lab, use the [data checkpoint and controller pause](restore-lab.md#pausing-the-gitops-managed-lab), then verified stopped-VM backups of both nodes. Restart the nodes before running the playbook. Resume applications only after both nodes pass verification.

The role rejects skipped minors, downgrades and workers upgraded ahead of the API server. It upgrades the single control plane first, then workers serially, draining through the eviction API and leaving a failed node cordoned. It explicitly skips the kube-proxy addon because Cilium supplies that function. It never bypasses a PDB. The commands below describe the same procedure for diagnosis and manual recovery.

A lab-only upgrade changes the lab inventory's version overrides after verification. Keep production and shared Packer defaults at their actual deployed baseline until their own upgrade is verified. An unjoined clone can replace held image packages with the inventory-selected version before joining. An initialized node must use the upgrade playbook. Rebuild and boot-test the destination-version template before completing the migration.

## Configure the package repository on each node

Select an exact patch and Debian package version for the **next** minor. Run this on the control plane first and later on each worker. Replace the values below before using them:

```bash
TARGET_MINOR='1.33'
TARGET_VERSION='1.33.REPLACE_ME'
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
