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

    This configures IOMMU, creates a cloud-init VM template, and generates a Proxmox API token for Terraform.

!!! warning
    Save the API token printed at the end of the playbook run. It is required for Terraform to provision VMs on this host.

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
cp -r terraform/hosts/homelabk8s01 terraform/hosts/<cluster>
```

Edit `terraform/hosts/<cluster>/terraform.tfvars`:

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

- `config/` -- Shared resources (namespaces, ConfigMaps) deployed at early sync waves
- `infrastructure/` -- Infrastructure components (Cilium Gateway, cert-manager, Vault, etc.)
- `apps/` -- Application workloads

!!! tip
    Copy and adapt manifests from `k8s/clusters/homelabk8s01/` as a starting point. Update IP addresses, hostnames, and other cluster-specific values.

### 4. Configure ArgoCD ApplicationSet

The ApplicationSet tells ArgoCD where to find `config.yaml` files for the cluster. You have two options:

- **Modify `k8s/bootstrap/applicationsets/cluster-apps.yml`** to update the glob path for the new cluster.
- **Create a second ApplicationSet** to manage both clusters from the same ArgoCD instance.

### 5. Deploy

```bash
make CLUSTER=<cluster> k8s-deploy
```

This runs the full provisioning pipeline: Terraform VM creation, Ansible cluster bootstrap, and ArgoCD installation.

### 6. Post-Deployment

After the cluster is running:

1. Retrieve the kubeconfig: `make CLUSTER=<cluster> k8s-kubeconfig`
2. Initialize Vault for the new cluster: `make vault-init`
3. Populate secrets in Vault for the new cluster's workloads
4. Verify all applications sync in ArgoCD
