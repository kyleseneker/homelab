# Quick Start

A walkthrough from a configured Proxmox host to the Kubernetes platform managed by ArgoCD. The repository currently pins Kubernetes 1.31.4; complete the [staged upgrade plan](../runbooks/upgrading-kubernetes.md) before treating this as a supported fresh-install baseline.

## 1. Install Dependencies

```bash
make deps
```

This installs the required Ansible Galaxy collections. All other tools (Terraform, Ansible, kubectl, vault CLI, Velero CLI) must be installed manually -- see [Prerequisites](../getting-started/prerequisites.md).

## 2. Configure Proxmox Host Inventory

Edit the Proxmox inventory file with the IP address of your Proxmox host:

```
ansible/inventory/homelabpve01/hosts.yml
```

## 3. Configure the Proxmox Host

```bash
make pve-configure
```

This playbook configures repositories, IOMMU, networking, UPS shutdown, the HCP Terraform agent, and the Proxmox API token. It can reboot the host when IOMMU settings change. Distribution upgrades are a separate opt-in maintenance action (`pve_repos_upgrade_packages=true`), not a side effect of configuring the host. Store `vault_tfc_agent_token` and `vault_pve_ups_upsmon_password` in the inventory Ansible Vault before running it; the UPS password must be at least 16 letters, digits, underscores or hyphens.

Packer owns the default template ID `9000`. The legacy raw cloud-image role is disabled by default; explicit opt-in uses `9001` and requires `packer_template=false` when configuring its clones.

!!! warning
    The role stores a new API token in `/root/.terraform-api-token` on the Proxmox host; it does not print the secret. Put the token in the HCP Terraform workspace as a sensitive variable and in the ignored Packer variable file for template builds.

## 4. Build the K8s Node VM Template

Configure Packer variables:

```bash
cp packer/k8s-node/k8s-node.auto.pkrvars.hcl.example packer/k8s-node/k8s-node.auto.pkrvars.hcl
```

Edit `packer/k8s-node/k8s-node.auto.pkrvars.hcl` with your Proxmox API credentials, node name, ISO URL, and storage pools. See the [Configuration](configuration.md#packer) page for details.

Build the template:

```bash
make packer-init
make packer-build
```

This creates a K8s-ready VM template on Proxmox with Ubuntu 24.04, containerd, kubeadm, NFS client, and iGPU drivers pre-installed. Before conversion, Packer locks the build password, requires SSH keys, removes installer network configuration, and resets cloud-init, SSH host keys, and machine identity. Terraform will clone this template in the next step. Boot a disposable clone and verify its assigned IP, SSH public-key login, unique machine/host keys, and locked password before using a newly built template.

!!! note
    The template build takes roughly 10--15 minutes. The Packer build boots the ISO, runs Ubuntu autoinstall, then provisions the VM with Ansible roles before converting it to a template.

## 5. Configure Terraform

```bash
cp terraform/hosts/homelabk8s01/terraform.tfvars.example terraform/hosts/homelabk8s01/terraform.tfvars
```

Edit `terraform/hosts/homelabk8s01/terraform.tfvars` and fill in:

- The Proxmox endpoint and node name (store `proxmox_api_token` as a sensitive HCP Terraform workspace variable)
- VM IP addresses
- SSH public key contents
- Node definitions (roles, cores, memory, PCI devices)

See the [Configuration](configuration.md#terraform) page for a full reference.

## 6. Configure Ansible

Edit the following files:

| File | What to configure |
|------|-------------------|
| `ansible/inventory/homelabk8s01/hosts.yml` | K8s node IPs (must match the IPs in `terraform.tfvars`) |
| `ansible/inventory/homelabk8s01/group_vars/all.yml` | `nas_ip`, `nfs_nas_export_path`, `nfs_mount_path` |
| `ansible/group_vars/all/vars.yml` | `base_timezone`, `base_media_uid`, `base_media_gid` |

See the [Configuration](configuration.md#ansible) page for details.

Initialize both HCP Terraform workspaces with `terraform login`, `make k8s-init`, and `make aws-init`. The `homelab-homelabk8s01` workspace must use the configured agent pool to reach the private Proxmox endpoint; set workspace variables there when using remote execution.

## 7. Configure Kubernetes Manifests

Several K8s manifest files contain values specific to your environment (IP addresses, Git repo URL, timezone). See the [Configuration](configuration.md#kubernetes-manifests) page for the full list of files to edit.

Provision the AWS KMS key and offsite S3 bucket before deploying Vault (`make aws-plan`, then `make aws-apply`). Follow the [Vault bootstrap instructions](../infrastructure/vault.md) to supply `vault-aws-kms` in the `vault` namespace before expecting Vault to become Ready. KMS bootstrap credentials cannot come from an ExternalSecret backed by the Vault they must unseal.

## 8. Deploy Everything

```bash
make k8s-deploy
```

This single command will:

1. Provision VMs with Terraform
2. Bootstrap Kubernetes with kubeadm, the vendored Gateway API CRDs, and Cilium via Ansible
3. Retrieve the cluster kubeconfig
4. Install ArgoCD and the ApplicationSet

## 9. Get Kubeconfig and Initialize Vault

Retrieve the kubeconfig from the cluster:

```bash
make k8s-kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig
```

Wait for Vault and ESO to be deployed by ArgoCD, then initialize Vault:

```bash
# Wait for Vault pod to be running
kubectl -n vault wait --for=condition=ready pod/vault-0 --timeout=300s

# Initialize Vault (one-time setup: enable KV v2, configure K8s auth)
make vault-init
```

!!! warning "Save the Root Token"
    The init script writes the root token and recovery key to the private `vault-init-keys.json` file (mode 0600). Save them in separate safe locations, then remove that local file. Vault uses AWS KMS auto-unseal; recovery keys cannot replace a lost KMS key. After configuring normal administrative authentication, retire routine use of the root token.

## 10. Populate Secrets in Vault

Write each secret to Vault. Each `*-external-secret.yml` manifest documents the Vault path and required keys:

```bash
# Prompts for the value; do not put credentials in shell history or VAL=.
make vault-put-secret SECRET_PATH=apps/vpn KEY=OPENVPN_USER
make vault-put-secret SECRET_PATH=apps/vpn KEY=OPENVPN_PASSWORD
make vault-put-secret SECRET_PATH=infrastructure/minio KEY=rootUser
make vault-put-secret SECRET_PATH=infrastructure/minio KEY=rootPassword

# Repeat for all secrets using the paths and keys in the manifests.
```

ESO syncs secrets from Vault to Kubernetes automatically. Verify the sync status:

```bash
kubectl get externalsecret --all-namespaces
```

All ExternalSecrets should show `SecretSynced` status.

## 11. Access ArgoCD

Open [https://argocd.homelab.local](https://argocd.homelab.local) in your browser.

Retrieve the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

Log in with username `admin` and the password from the command above. From the ArgoCD dashboard you can monitor the sync status of all applications as they deploy.

!!! note
    If your browser shows a certificate warning, see [Trust the Homelab CA](trust-ca.md) to install the root certificate on your machine.

ArgoCD notification credentials are reconciled separately by the `argocd-notifications` Application. The initial `k8s/bootstrap/argocd` resources must not require ESO APIs: ESO is installed only after the ApplicationSet is created. This avoids a missing-CRD bootstrap cycle on a fresh cluster.
