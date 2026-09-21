# Isolated Restore Lab

The recovery lab uses two disposable VMs on the existing Proxmox host. It has passed a Sonarr database restore from offsite S3. The [recovery backlog](../roadmap/phase-1-foundations.md#12-verify-recovery) tracks the remaining controller, credential and platform recovery checks.

## Boundaries

| Resource | Lab allocation |
|----------|----------------|
| Terraform workspace | `kyleseneker/homelab-homelabrestore01` |
| Control plane | VM 300, `homelabrestore01-node-1`, 2 vCPU / 3 GiB / 32 GiB disk |
| Worker | VM 301, `homelabrestore01-node-2`, 2 vCPU / 4 GiB / 32 GiB disk |
| Node network | `vmbr1`, no physical ports; `172.26.0.0/24` |
| Node addresses | Control plane `172.26.0.10`, worker `172.26.0.11` |
| Pod / service ranges | `172.24.0.0/16` / `172.25.0.0/16` |
| Administrator | `labadmin`, separate key in `.lab/id_ed25519` |
| Kubernetes credentials | `.lab/kubeconfig`; context `homelabrestore01` |
| API access | SSH tunnel through Proxmox, `127.0.0.1:16443` |
| Storage | VM-local disks only; no production NFS mounts |

The nodes share the physical host's failure domain and are not a persistent staging or HA cluster. Worker 2 in production has 16 GiB to leave room for the lab. Check current host memory before starting it; the lab adds 7 GiB of guest allocation. Lab VMs do not start automatically with Proxmox.

The host's `restore-lab-network` service loads a dedicated nftables table before bringing up `vmbr1` and enabling IPv4 forwarding. Public internet access is masqueraded through `vmbr0`. Lab-initiated access to private networks, link-local addresses, the host and IPv6 forwarding is blocked. Return traffic for connections initiated by the host is allowed for administrative access. Forwarding between the existing Homelab and Management interfaces is also blocked. The playbook never flushes the host firewall or reloads the production bridge.

This network boundary still permits public internet access. Before starting a restored application, apply a deny-all egress policy in its namespace so recovered integrations cannot contact public production endpoints either. Keep the policy in place while inspecting the restored settings. Do not restore production ExternalSecrets, cluster credentials, ArgoCD Applications, webhooks or PV definitions indiscriminately.

## First-time Setup

1. Run `make lab-host` to install the bridge/firewall and the `restore-lab@pve` provisioning user.
2. Generate a dedicated SSH key, without overwriting an existing one:

    ```bash
    mkdir -p .lab
    chmod 700 .lab
    test -f .lab/id_ed25519 || ssh-keygen -t ed25519 -N '' -C homelabrestore01 -f .lab/id_ed25519
    ```

3. Create the separate HCP Terraform workspace shown above. Use the existing on-premises agent pool and Terraform version, and set its working directory to `terraform/hosts/homelabrestore01`. Do not connect it to automatic VCS applies.
4. Configure the cluster in `terraform/hosts/homelabrestore01/terraform.tfvars`, using the adjacent example as a guide. Set `ssh_public_key` from `.lab/id_ed25519.pub`. As with production, `main.tf` wires the VM module and `terraform.tfvars` owns the host, template, network and node allocations. Set the workspace's sensitive `proxmox_api_token` variable from `/root/.restore-lab-api-token` on Proxmox. Keep the token out of Git and command output. This identity has VM administration rights on IDs 300/301, clone rights on template 9010, allocation rights on `local-lvm`, node audit rights, and use of `vmbr1`. It has no rights on production VM IDs.
5. Run `make lab-init`, then `make lab-plan`. A first deployment must create only VMs 300 and 301. Run `make lab-infra` after reviewing that plan.
6. Run `make lab-configure`. Template 9010 is a lab-only copy of the older Ubuntu cloud image in template 9000, with its NIC on `vmbr1`. The lab token cannot use the production bridge. The guest agent is disabled in the lab VM configuration so Terraform can finish before the prerequisite packages are installed. This playbook explicitly runs the base and Kubernetes prerequisite roles. This does **not** complete the fresh Packer-image acceptance test.
7. Run `make lab-tunnel`, `make lab-kubeconfig`, and `make lab-status`.

Use the dedicated `lab-*` targets. The production ApplicationSet includes production storage, endpoints and credentials and must never be bootstrapped into this lab. The lab does not bootstrap ArgoCD or production applications automatically.

## Verified Bootstrap

Both nodes run Kubernetes 1.31.4 with Cilium 1.19.1, containerd 2.3.5 and kernel 6.8.0-139. They returned Ready after the package-required reboot, and a second bootstrap run completed with zero changes. All five production/lab machine IDs and SSH host keys are distinct. CoreDNS and public HTTPS work from a lab pod; the private endpoints below are blocked. The lab API token returns permission denied for production VMs 200–202 and template 9000. Production remains at three Ready nodes and 53 Synced/Healthy Applications.

The raw cloud-image bootstrap and isolated Sonarr database restore are verified. The fresh Packer build and ArgoCD/controller-driven application bootstrap remain separate acceptance checks.

## Acceptance Checks

Before transferring backup data:

- Both nodes are Ready at the intended version; Cilium and CoreDNS are healthy.
- Machine IDs and SSH host keys differ between the two clones and production nodes.
- The VM and pod address ranges match the table above and do not overlap production.
- Public HTTPS and DNS work from the lab; connections to production API `192.168.10.50:6443`, NAS `192.168.1.158:2049`, host SSH `172.26.0.1:22` and Management `192.168.99.2:22` are blocked.
- No NFS mounts or production credentials exist on the lab nodes.
- All production nodes and applications remain healthy.

## Sonarr Recovery

The lab manifests under `k8s/clusters/homelabrestore01/` provide the shared local-path provisioner and a Sonarr deployment using production's image and chart versions. Sonarr has a fresh local PVC, no media mount or ingress, and a namespace policy denying all ingress and egress. Administrative access uses port forwarding. The production ApplicationSet does not discover this cluster.

The [backup runbook](backup-and-restore.md#verified-sonarr-offsite-restore) records the source, checks and limits of the completed database restore. Non-database configuration is recreated from declared configuration and fresh lab credentials. Production recovery should use Helm/Git, Vault/ESO, media-operator, Prowlarr and Recyclarr according to their existing ownership; it should not accumulate a second manual configuration procedure. The standalone lab deployment intentionally does not reconcile production integrations.

For another drill:

1. Retrieve the selected Sonarr dump from S3 using the read-only procedure in the backup runbook. Preserve its timestamp, hash and integrity result.
2. Apply the lab local-path provisioner and Sonarr resource Kustomizations with `--kubeconfig .lab/kubeconfig`. Confirm the context is `homelabrestore01` and both nodes have the expected names before any write.
3. Mount the fresh `restore-sonarr-config` PVC in a temporary staging pod in `restore-sonarr`. Before copying data, verify the deny-all policy blocks public HTTPS, the lab API and production/NAS endpoints. Never reuse a volume containing an active database or stale WAL files.
4. Install `sonarr.db` as UID 977 / GID 988, mode 0600. Recreate `config.xml` with port 8989, Forms authentication and a newly generated lab API key. Keep credentials in ignored `.lab/` files with mode 0600. Verify the installed database hash matches the downloaded dump, then remove the staging pod.
5. Render `app-template` using the version in the lab Sonarr `config.yml` and its `values.yml`, release/namespace `restore-sonarr`; apply the render with the explicit lab kubeconfig. Wait for the Deployment to become Ready.
6. Forward the service locally and create a fresh Forms user through Sonarr's host configuration. Verify an anonymous protected page redirects to login and an authenticated browser session reaches it. Use the lab API key to compare series, episode and episode-file records against the source database.

```bash
kubectl --kubeconfig .lab/kubeconfig -n restore-sonarr \
  port-forward --address 127.0.0.1 svc/restore-sonarr 18989:8989
```

Keep restored integration credentials isolated. A full reconciliation drill requires lab-specific endpoints and Secrets before starting controllers; do not apply the production media-config resources unchanged.

## Access and Teardown

Every manual command must select the lab kubeconfig explicitly:

```bash
kubectl --kubeconfig .lab/kubeconfig get pods -A
make lab-ssh
```

`make lab-disconnect` closes the local API tunnel. `make lab-destroy` destroys only the VMs managed by the lab workspace; it retains the host bridge, firewall, API identity and local SSH key for the next drill. Deleting the lab VMs deletes their local restored data. Preserve any required evidence before teardown. After rebuilding a VM, verify its new host-key fingerprint through the Proxmox console before replacing its old known-hosts entry.
