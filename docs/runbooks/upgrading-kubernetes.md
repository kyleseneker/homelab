# Upgrading Kubernetes

This runbook covers the procedure for upgrading the kubeadm-managed Kubernetes cluster. This is a manual process -- the Ansible roles handle initial cluster setup but do not automate version upgrades.

!!! warning
    Always upgrade one minor version at a time (e.g., 1.30 to 1.31, not 1.30 to 1.32). Skipping minor versions is not supported by kubeadm.

## Pre-Upgrade Checklist

Before starting the upgrade:

- [ ] Verify a recent Velero backup exists: `velero backup get`
- [ ] Check current cluster version: `kubectl version`
- [ ] Check the [Cilium compatibility matrix](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/) to confirm the target Kubernetes version is supported by the installed Cilium version
- [ ] Review the [Kubernetes changelog](https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/README.md) for the target version
- [ ] Ensure all nodes are in `Ready` state: `kubectl get nodes`
- [ ] Ensure all ArgoCD applications are synced and healthy

## Upgrade Procedure

### 1. Upgrade the Control Plane

On the control plane node, update the `kubeadm` package to the target version:

```bash
sudo apt-get update
sudo apt-get install -y kubeadm=<version>-*
```

Verify the upgrade plan:

```bash
sudo kubeadm upgrade plan
```

Apply the upgrade:

```bash
sudo kubeadm upgrade apply v<version>
```

Upgrade `kubelet` and `kubectl` on the control plane node:

```bash
sudo apt-get install -y kubelet=<version>-* kubectl=<version>-*
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```

### 2. Upgrade Worker Nodes

Upgrade each worker node one at a time to maintain availability.

**From your local machine**, drain the worker node:

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

**On the worker node**, update packages:

```bash
sudo apt-get update
sudo apt-get install -y kubeadm=<version>-*
sudo kubeadm upgrade node
sudo apt-get install -y kubelet=<version>-* kubectl=<version>-*
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```

**From your local machine**, uncordon the node:

```bash
kubectl uncordon <node-name>
```

Wait for the node to return to `Ready` state before proceeding to the next worker:

```bash
kubectl get nodes -w
```

Repeat for each remaining worker node.

### 3. Post-Upgrade Verification

1. Verify all nodes are running the new version:

    ```bash
    kubectl get nodes
    ```

2. Check that all system pods are healthy:

    ```bash
    kubectl get pods -n kube-system
    ```

3. Verify ArgoCD applications are still synced:

    ```bash
    kubectl get applications -n argocd
    ```

4. Confirm workloads are running:

    ```bash
    kubectl get pods --all-namespaces
    ```

## Troubleshooting

### Upgrade Plan Fails

If `kubeadm upgrade plan` reports errors, check that:

- The `kubeadm` package version matches the target version
- The cluster is healthy (`kubectl get cs` or `kubectl get pods -n kube-system`)
- etcd is running and responsive

### Node Fails to Rejoin

If a worker node does not return to `Ready` after upgrade:

1. Check kubelet logs on the node: `sudo journalctl -u kubelet -f`
2. Verify the kubelet version matches: `kubelet --version`
3. Restart kubelet: `sudo systemctl restart kubelet`

### Cilium Issues After Upgrade

If networking breaks after a Kubernetes upgrade, check Cilium pod status:

```bash
kubectl get pods -n kube-system -l k8s-app=cilium
kubectl logs -n kube-system -l k8s-app=cilium
```

A Cilium upgrade may be required. Check the [Cilium upgrade guide](https://docs.cilium.io/en/stable/operations/upgrade/) for instructions.
