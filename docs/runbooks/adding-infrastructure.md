# Adding Infrastructure

This runbook covers three procedures for expanding the homelab infrastructure: adding a new Proxmox host, adding a worker node to an existing cluster, and creating an entirely new Kubernetes cluster.

## Adding a New Proxmox Host

Use this procedure when introducing a new physical machine running Proxmox VE.

1. Create the Ansible inventory directory for the new host:

    ```bash
    mkdir -p ansible/inventory/<pve-host>
    ```

2. Create `ansible/inventory/<pve-host>/hosts.yml` with the host IP:

    ```yaml
    all:
      hosts:
        <pve-host>:
          ansible_host: <ip-address>
          ansible_user: root
    ```

3. Run the Proxmox configuration playbook:

    ```bash
    make PVE_HOST=<pve-host> pve-configure
    ```

    This configures IOMMU and the host services selected in the inventory, creates a cloud-init VM template, and provisions the dedicated Terraform API identity.

The API token is not printed in Ansible output. The role saves it in `/root/.terraform-api-token` on the Proxmox host with mode `0600`. Retrieve it through the administrator SSH session and store it as the sensitive `proxmox_api_token` HCP Terraform workspace variable.

## Adding a New Worker Node

Use this procedure to add a worker node to an existing Kubernetes cluster.

### 1. Update Terraform Configuration

Add a new entry to the `nodes` map in `terraform/hosts/<cluster>/terraform.tfvars`:

```hcl
nodes = {
  # ... existing nodes ...
  <cluster>-node-<n> = {
    role   = "worker"
    ip     = "<ip-address>/24"
    vm_id  = <unique-vm-id>
    cores  = 4
    memory = 8192
  }
}
```

For a GPU node, also add `tags` and `pci_mappings`:

```hcl
  <cluster>-node-<n> = {
    role         = "worker"
    ip           = "<ip-address>/24"
    vm_id        = <unique-vm-id>
    cores        = 4
    memory       = 8192
    tags         = ["gpu"]
    pci_mappings = ["igpu"]
  }
```

### 2. Update Ansible Inventory

Add the new node to `ansible/inventory/<cluster>/hosts.yml` under the `workers` group. If the node has a GPU for hardware transcoding, also add it to the `gpu` group.

### 3. Provision and Configure

```bash
make k8s-infra && make k8s-configure
```

Terraform creates the new VM, and Ansible configures it and joins it to the cluster.

### 4. Verify

```bash
kubectl get nodes
```

The new node should appear in `Ready` state within a few minutes.

## Adding a New Cluster

Use this procedure to stand up an entirely new Kubernetes cluster alongside the existing one.

### 1. Create Terraform Configuration

```bash
mkdir -p terraform/hosts/<cluster>
# Export tracked files only: do not copy state, .terraform, or local credentials.
git archive HEAD terraform/hosts/homelabk8s01 | \
  tar -x -C terraform/hosts/<cluster> --strip-components=3
cp terraform/hosts/<cluster>/terraform.tfvars.example \
  terraform/hosts/<cluster>/terraform.tfvars
```

Review the tracked Terraform configuration before initialization. Give the new cluster its own backend workspace/state and credentials; copying configuration must never reuse the existing cluster's state. Then edit `terraform/hosts/<cluster>/terraform.tfvars`:

- Update the cluster name
- Set new VM IP addresses (must not overlap with existing clusters)
- Adjust node count, resources, and PCI passthrough as needed
- Set the correct Proxmox API token for the target host

### 2. Create Ansible Inventory

Create `ansible/inventory/<cluster>/hosts.yml` with the new node IPs. The structure mirrors the existing cluster inventory, with groups for `control_plane`, `workers`, and optionally `gpu`.

### 3. Create Kubernetes Manifests

Create the cluster's directory structure under `k8s/clusters/`:

```bash
mkdir -p k8s/clusters/<cluster>/{config,infrastructure,apps}
```

- `prereqs/` -- Shared resources (namespace, shared PV, shared ConfigMap) owned by a dedicated Application
- `infrastructure/` -- Infrastructure components (Cilium Gateway, cert-manager, Vault, etc.)
- `apps/` -- Application workloads

!!! tip
    Copy and adapt manifests from `k8s/clusters/homelabk8s01/` as a starting point. Update IP addresses, hostnames, and other cluster-specific values.

### 4. Configure ArgoCD ApplicationSet

The ApplicationSet tells ArgoCD where to find `config.yml` files for the cluster. You have two options:

- **For an ArgoCD instance in the new cluster**, give it a cluster-specific generator glob and bootstrap manifest. Do not replace the existing cluster's tracked generator to stand up a second cluster.
- **For a shared ArgoCD instance**, register the second destination cluster and create a second ApplicationSet with that destination and unique Application names. The current template uses the local cluster API endpoint.

### 5. Deploy

```bash
make CLUSTER=<cluster> k8s-deploy
```

The current Makefile selects Terraform and Ansible by `CLUSTER`, but its Kubernetes bootstrap paths are shared and still target the existing cluster layout. Adapt that bootstrap first and review the selected kubeconfig; this repository is not yet a turnkey multi-cluster installer. Run `make CLUSTER=<cluster> k8s-plan` and Ansible syntax checks before the mutating deploy command.

### 6. Post-Deployment

After the cluster is running:

1. Retrieve the kubeconfig: `make CLUSTER=<cluster> k8s-kubeconfig`
2. Initialize Vault for the new cluster: `make vault-init`
3. Populate secrets in Vault for the new cluster's workloads
4. Verify all applications sync in ArgoCD
