# Upgrading Kubernetes

The Ansible roles bootstrap nodes; changing their version variables does **not** perform a cluster upgrade. Use a maintenance window and upgrade the control plane, then each worker. Update the repository pins and rebuild the Packer template only after the running cluster passes verification.

The repository still records Kubernetes **1.31.4**, an unsupported release. This is a migration backlog item, not a recommendation for a new cluster. Select a supported destination using the [release history](https://kubernetes.io/releases/patch-releases/), then plan every intervening minor release. kubeadm does not support skipping minors. Follow the [upstream upgrade procedure](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/) for each step.

## Before each minor upgrade

- Confirm the live versions with `kubectl get nodes -o wide` and `kubectl version`; do not infer them from Git.
- Verify a recent off-host etcd snapshot, `/etc/kubernetes/pki` backup, and application data backup can be restored. A completed Velero backup alone does not establish this. Follow [Backup and Restore](backup-and-restore.md).
- Check the installed Cilium release's compatibility with both the current and next Kubernetes minor, plus Gateway API CRDs, containerd, Kyverno, and other admission webhooks. Use the [Cilium compatibility documentation](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/) for the actual installed release.
- Verify node readiness, ArgoCD health, storage mounts, and backup jobs. Review the target release's removed APIs and [version skew rules](https://kubernetes.io/releases/version-skew-policy/).
- Inspect `kubectl get pdb -A` and workloads on the node to be drained. Local-path volumes stay on their original node; the sole GPU worker cannot transfer GPU workloads to another node. Plan downtime and resolve any PDB that blocks maintenance before proceeding. Do not use `--disable-eviction` to bypass it.

## Configure the package repository on each node

Select an exact patch and Debian package version for the **next** minor. Run this on the control plane first and later on each worker. Replace the values below before using them:

```bash
TARGET_MINOR='1.32'
TARGET_VERSION='1.32.REPLACE_ME'
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
sudo kubeadm upgrade apply "v${TARGET_VERSION}"
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
