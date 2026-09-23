# Isolated Restore Lab

The recovery lab uses two disposable VMs on the existing Proxmox host. It runs from a verified Packer template and has passed clean ArgoCD bootstrap, application-data preservation and offsite restore drills. The [recovery backlog](../roadmap/phase-1-foundations.md#12-verify-recovery) tracks the remaining controller, credential and platform recovery checks.

## Boundaries

| Resource | Lab allocation |
|----------|----------------|
| Terraform workspace | `kyleseneker/homelab-homelabrestore01` |
| Control plane | VM 300, `homelabrestore01-node-1`, 2 vCPU / 4 GiB / 32 GiB disk |
| Worker | VM 301, `homelabrestore01-node-2`, 2 vCPU / 4 GiB / 32 GiB disk |
| Node network | `vmbr1`, no physical ports; `172.26.0.0/24` |
| Node addresses | Control plane `172.26.0.10`, worker `172.26.0.11` |
| Pod / service ranges | `172.24.0.0/16` / `172.25.0.0/16` |
| Administrator | `labadmin`, separate key in `.lab/id_ed25519` |
| Kubernetes credentials | `.lab/kubeconfig`; context `homelabrestore01` |
| API access | SSH tunnel through Proxmox, `127.0.0.1:16443` |
| Storage | VM-local disks only; no production NFS mounts |

The nodes share the physical host's failure domain and are not a persistent staging or HA cluster. Worker 2 in production has 16 GiB to leave room for the lab. Check current host memory before starting it; the lab adds 8 GiB of guest allocation. Lab VMs do not start automatically with Proxmox.

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
4. Configure the cluster in `terraform/hosts/homelabrestore01/terraform.tfvars`, using the adjacent example as a guide. Set `ssh_public_key` from `.lab/id_ed25519.pub`. As with production, `main.tf` wires the VM module and `terraform.tfvars` owns the host, template, network and node allocations. Set the workspace's sensitive `proxmox_api_token` variable from `/root/.restore-lab-api-token` on Proxmox. Keep the token out of Git and command output. This identity has VM administration rights on IDs 300/301, clone rights on template 9011, allocation rights on `local-lvm`, node audit rights, and use of `vmbr1`. It has no rights on production VM IDs.
5. Build and verify Packer template `9011` if it is not already available; see [template acceptance](#packer-template-acceptance). Its ID must match Terraform's `clone_template_id` and Ansible's `pve_restore_lab_template_id`. Run `make lab-permissions` after building the template.
6. Run `make lab-init`, then `make lab-plan`. A first deployment must create only VMs 300 and 301. Run `make lab-infra` after reviewing that plan.
7. Run `make lab-configure` to initialize Kubernetes and join the worker using the shared roles. The Packer image already includes the guest agent and prerequisites; Ansible checks convergence.
8. Run `make lab-tunnel`, `make lab-kubeconfig`, and `make lab-status`.

Use the dedicated `lab-*` targets. The production ApplicationSet includes production storage, endpoints and credentials and must never be bootstrapped into this lab. `make lab-argocd` installs the shared ArgoCD base without production SSO, ingress or notification settings. `make lab-apps` applies the lab isolation policies before creating its restricted ApplicationSet. Both commands verify the lab kubeconfig endpoint and exact node identities.

## Verified Bootstrap

Both nodes run Kubernetes 1.31.4 with Cilium 1.19.1, containerd 2.3.5 and kernel 6.8.0-142, cloned from Packer template `9011`. A new cluster was initialized without existing ArgoCD, ESO or media-operator CRDs, application Secrets or restore namespaces. ArgoCD installed its CRDs and all 14 lab Applications converged to Synced/Healthy. Its controllers run on the control-plane node to leave worker memory for the restored applications.

Nine preserved local volumes were imported onto the fresh worker; all 5,597 regular files matched their archive hashes before application startup. Seven externally held bootstrap Secrets were imported explicitly. Generated ESO output was excluded: restored Vault auto-unsealed through KMS, accepted the new cluster's Kubernetes identities, and ESO recreated its Secret. This is a planned rebuild with preserved inputs, not a claim that credentials can be recovered without those inputs.

Sonarr records and 54 episode-file entries, the Prowlarr fixture connection, Authentik database users, qBittorrent login/category/history data, and media-operator Ready/Synced conditions passed. Both nodes and all 14 Applications recovered after node reboots. ESO initially reported provider errors while networking and Vault restarted; a fresh reconciliation verified SecretStore recovery and Secret recreation. Cross-node Service traffic, DNS, public HTTPS and the private-network boundary passed. Production remains at three Ready nodes and 53 Synced/Healthy Applications.

### Repeat a Clean Rebuild

1. Record current health and confirm the lab kubeconfig. Preserve application inputs with `python3 scripts/restore-lab-data.py export --work-dir .lab/rebuild`. Use a new private directory. The helper pauses lab ArgoCD reconciliation and its application controller, stops application deployments and refuses to copy while writers remain. It excludes generated ESO Secrets. If cancelling the rebuild, use its `resume` action to restore saved application/controller replicas and reconciliation annotations.
2. Take full stopped-VM `vzdump` archives for IDs 300/301 on Proxmox and verify both with `zstd -t` and `vma verify`. Keep them until the new cluster passes acceptance; a Terraform replacement removes VM disks and their snapshots.
3. Review and apply a lab-only destroy plan, run `make lab-permissions` to replace deleted VM ACLs, then review and apply the create plan. Require exactly IDs 300/301, template `9011`, and `vmbr1`. Verify the new SSH host keys through Proxmox before updating local trust.
4. Run `make lab-configure lab-tunnel lab-kubeconfig lab-status`. Confirm fresh machine identities and absence of application CRDs/Secrets before `make lab-argocd`.
5. Import with `python3 scripts/restore-lab-data.py import --work-dir .lab/rebuild`. It requires an empty worker storage directory, verifies every file hash, then restores local PV/PVC bindings and bootstrap Secrets. If extraction completed but verification was interrupted, `--resume` verifies the existing files without overwriting them.
6. Run `make lab-apps`; wait for all 14 Applications to become Synced/Healthy. Verify application records, Vault/ESO authentication, network isolation and node reboots. Confirm Terraform has no further changes and production remains healthy before removing temporary migration and rollback copies.

The shared ArgoCD installation lives in `k8s/components/argocd`; production and lab bootstrap overlays add their own settings. The lab ApplicationSet reuses the shared generator/template with only its source path and project changed. Bootstrap credentials and application data remain explicit recovery inputs; they are never committed to Git.

## Packer Template Acceptance

Template `9011` (`restore-lab-packer-template`) was built from the checksum-verified Ubuntu 24.04.2 installer using the shared Packer configuration and Ansible roles. It uses `vmbr1`; template `9000`, cloud-image template `9010`, and the existing recovery nodes were preserved.

Use `packer/k8s-node/restore-lab.pkrvars.hcl.example` for the isolated network and bastion settings, together with the [Packer configuration](../getting-started/configuration.md#packer). Keep the actual variable file and a dedicated build key under `.lab/`. Select an unused template ID and verify the ISO checksum before using a pre-uploaded `iso_file`. Build credentials require VM administration on that ID, node audit, bridge use, disk allocation, and ISO upload/removal permissions. Revoke temporary build credentials after acceptance.

The installer receives its configuration on a temporary seed ISO. The build uses key-only SSH, establishes the shared media UID/GID before first login, waits for cloud-init, and provisions the existing base, Kubernetes, NFS and iGPU roles. Cleanup removes installer settings, the build key, machine identity and SSH host keys. The generated seed ISO is removed when Packer finishes.

Two temporary full clones were booted with independent cloud-init addresses and the lab administrator key, then rebooted:

| Check | Verified result |
|---|---|
| Prerequisites | Kubernetes 1.31.4, containerd 2.3.5, kernel 6.8.0-142; guest agent active, swap disabled, systemd cgroups enabled, required kernel modules load |
| Identity | Distinct machine IDs, system UUIDs and SSH host keys; machine IDs also differ from all five existing production/lab nodes; identities remain stable across reboot |
| Access and cleanup | Assigned cloud-init addresses work; installer network override and disabled marker absent; build key rejected; media UID/GID 977/988; password and root SSH login disabled |
| Cluster state | No inherited kubeadm credentials, cluster PKI or etcd member data |
| Isolation | Public HTTPS works; TCP access to production API, NAS, host SSH and Management endpoints is blocked |
| Existing systems | Three production and two original lab nodes Ready; all 53 production Applications Synced/Healthy |

The acceptance clones and temporary build credentials were removed; stopped template `9011` is retained. Both current lab nodes now select `9011`; their clean Kubernetes and ArgoCD bootstrap is covered above.

## Acceptance Checks

Before transferring backup data:

- Both nodes are Ready at the intended version; Cilium and CoreDNS are healthy.
- Machine IDs and SSH host keys differ between the two clones and production nodes.
- The VM and pod address ranges match the table above and do not overlap production.
- Public HTTPS and DNS work from the lab; connections to production API `192.168.10.50:6443`, NAS `192.168.1.158:2049`, host SSH `172.26.0.1:22` and Management `192.168.99.2:22` are blocked.
- No NFS mounts or production credentials exist on the lab nodes.
- All production nodes and applications remain healthy.

## Pausing the GitOps-managed Lab

Before any drill below scales or replaces application workloads, pause ArgoCD's application controller as well as reconciliation. An annotation alone can race with a reconciliation already in progress. `scripts/restore-lab-data.py export --work-dir .lab/<new-drill-directory>` saves replicas and annotations, stops the lab controller, then stops application writers and creates a private data checkpoint. Its `resume` action restores that saved state. Keep the controller stopped until restored data and isolation policies are ready; otherwise self-healing can restart workloads during recovery. The controller pause applies only to the lab.

## Worker Replacement Drill

A worker-only rebuild uses the existing Terraform VM module and Ansible worker
role. The worker role generates a 15-minute bootstrap token on the surviving
control plane only when `kubelet.conf` is absent, then revokes that token after
its join attempt. It does not require the control-plane play to run first.

1. Confirm the explicit lab kubeconfig selects only the two lab nodes. Inventory
   PV paths, node affinity, application replica counts and suspended CronJobs.
   Save these records privately. Every current lab local-path PV resides on VM 301;
   replacing that disk without a data restore would lose those volumes.
2. Scale the `restore-*` Deployments to zero and wait for their Pods to terminate.
   Keep the control plane and network controllers running. Archive
   `/opt/local-path-provisioner` with numeric ownership, permissions, ACLs and
   extended attributes preserved. Verify the archive and record file hashes before
   proceeding. These are sensitive recovery files; use directories mode 0700 and
   files mode 0600.
3. Take a full VM 301 backup with Proxmox `vzdump --mode stop` into a private local
   directory. Wait for completion and verify both compressed-stream and VMA
   integrity. A VM snapshot alone is insufficient rollback protection because
   Terraform replacement deletes the old VM disks and their snapshots.
4. Use two reviewed Terraform plans in the lab workspace. First save a destroy
   plan with `-destroy -target='module.vm["homelabrestore01-node-2"]'` and confirm
   it deletes only VM 301. Apply that exact plan after both recovery copies are
   verified. Proxmox removes `/vms/301` ACLs when deleting the VM, so run
   `make lab-permissions` next to restore the existing narrow permissions.
   Then save a normal plan, require exactly one create for VM 301, and apply it.
   A single `-replace` apply cannot recreate this VM with its deleted ACL. Do not
   broaden the provisioning token to bypass this boundary. Keep applications
   scaled to zero throughout.
5. Remove the old lab worker's Node record. Verify the replacement's SSH host key
   through the administrative Proxmox path and update only that lab host's trust
   entry. Run the existing playbook with the worker limit:

    ```bash
    cd ansible
    ansible-playbook --vault-password-file ../.vault-password \
      -i inventory/homelabrestore01/hosts.yml playbooks/restore-lab.yml \
      --limit homelabrestore01-node-2
    ```

6. Confirm a new machine ID, system UUID and Node UID, plus healthy Cilium and
   kubelet registration. Restore the quiesced volume archive into `/opt` on the
   fresh worker before restarting applications. Require every recorded file's
   hash, owner and permissions to match, and confirm PV paths and node affinity
   still refer to the intended worker. Do not import old kubelet credentials,
   containerd state or Cilium state from the VM backup.
7. Restore saved replica counts. Verify application readiness, Vault auto-unseal,
   database access, Pod DNS and cross-node service traffic. Retest the lab's
   production/NAS/management blocks and application egress policies. Run the
   worker playbook again to check convergence, then require a no-change Terraform
   plan and healthy production nodes/Applications.
8. Retain the VM backup until the checks pass. On failure, stop the replacement
   VM and restore the verified VM 301 backup on `local-lvm`; reconcile Terraform
   and node registration before restoring application replica counts. Remove only
   the temporary drill backups and copied credentials after successful acceptance.

The worker replacement passed on VM 301 using a fresh clone of template 9010:

| Check | Verified result |
|-------|-----------------|
| Machine and bootstrap | New SSH host key, machine ID, system UUID and Node UID; Kubernetes 1.31.4 Ready through the worker-only play; bootstrap token revoked |
| Local data | All 5,702 checkpointed files matched SHA-256, size, UID/GID and mode before application startup; all 12 PV definitions preserved |
| Cilium networking | Worker Pod reached a service backed by a control-plane Pod; Pod DNS and public HTTPS passed; production API, NAS, host SSH and management SSH blocked |
| Policy enforcement | A selected worker Pod lost service/public egress under a deny-egress policy; temporary probe namespace removed |
| Convergence and cleanup | Worker Ansible rerun completed with zero changes; Terraform reported no changes; temporary VM and volume recovery archives removed after acceptance |
| Applications | Original Deployment replica counts restored; Sonarr identities and 54 episode files preserved; Prowlarr connection test and application egress blocks passed; Vault Raft auto-unsealed through KMS; Authentik retained two users |

This drill distinguishes rebuilding a worker from restoring its application data.
A local quiesced volume checkpoint does not prove recovery after loss of the
Proxmox host, nor does it replace the application's verified offsite restore path.

## Native Control-plane Recovery Drill

Use a fresh VM 300 to verify that the offsite bundle can boot the original static
control-plane pods with the host's kubelet and containerd. The
`scripts/verify-native-control-plane.py` helper runs only on the lab control-plane
hostname. It uses standalone kubelet with no API kubeconfig and disables the
kubelet API, so restored Deployments, DaemonSets and other API workloads cannot
execute. This is a deliberate containment overlay on the archived kubelet
settings; normal node registration and production Cilium convergence are separate
acceptance checks.

1. Record lab node identities, PVs and application replica counts privately. Scale
   restored applications to zero and wait for writers to exit. Shut down VM 301
   and leave its disks untouched throughout the drill.
2. Create a full VM 300 `vzdump --mode stop` backup in a private Proxmox directory.
   Verify both Zstandard and VMA integrity with pipeline failure propagation.
   VM snapshots alone do not survive Terraform deletion.
3. Review and apply a saved Terraform destroy plan targeting only
   `module.vm["homelabrestore01-node-1"]`, then run `make lab-permissions`.
   Review a separate create plan with the same target: an unrestricted plan would
   also restart the intentionally stopped worker. Apply only the reviewed plan.
4. Verify the new SSH host key through Proxmox, update only the lab host's trust
   entry, and run `playbooks/restore-lab-prepare.yml` with the lab inventory and
   `--limit homelabrestore01-node-1`. This shared prerequisite play installs base
   packages and Kubernetes tooling without running `kubeadm init`. Verify the
   fresh machine identity and absence of old etcd and Kubernetes credentials.
5. Before transferring recovery credentials, cache the four pinned control-plane
   images and the pause image selected by the archived containerd configuration.
   Install Python/PyYAML and nftables. Add a temporary Proxmox forwarding rule
   dropping all traffic arriving from `vmbr1`, including established outbound
   connections. Keep the worker stopped. Administrative SSH from Proxmox remains
   available through the existing host input rules.
6. Download a completed bundle using independent S3 credentials and run the
   [offline preparation helper](../infrastructure/etcd-backup.md#restore).
   Transfer its private output and both Python helpers into a root-owned 0700
   directory on the fresh VM. Run the native helper's `install --source <input>`.
   It installs a persistent guest firewall allowing only loopback and host SSH,
   places the original API address on loopback, restores etcd with revision bump
   and compaction, and boots the four static pods with the recovered PKI and
   controller kubeconfigs. It refuses an initialized machine.
7. Inspect the private `verification.json`: authenticated API readiness, recovered
   object counts, exactly four running control-plane containers, the bumped etcd
   revision and renewed controller/scheduler leases must pass. Record the machine
   and boot IDs. Reboot the VM, run the helper's `verify` operation, and require
   the same checks on a new boot ID. Check outbound blocks explicitly.
8. Preserve only nonsensitive evidence. Stop the fresh VM and restore the verified
   VM 300 rollback archive on its existing ID/storage. Restore the original SSH
   trust after checking the restored key through Proxmox. Remove only the drill's
   host firewall table, start VM 300 and then VM 301, and restore saved replica
   counts. Verify lab networking/application health, production health, and a full
   no-change Terraform plan before deleting the temporary rollback archive and
   downloaded recovery credentials.

The fresh-machine static control-plane drill passed using the completed offsite
bundle `recovery-20260922-202350.json`:

| Check | Verified result |
|-------|-----------------|
| Fresh machine | Terraform replaced VM 300 from template 9010; SSH host key, machine ID and system UUID differed from the original lab nodes; no `kubeadm init` or old guest state was used |
| Native boot | Host kubelet/containerd ran exactly the four original static control-plane pods with recovered PKI and controller kubeconfigs; authenticated API ready and both controller leases renewed |
| Datastore | Snapshot SHA-256 matched the offline drill; revision bump retained; 19 namespaces, 3 historical Node records, 64 Deployments and 72 Secrets matched |
| Reboot | New boot ID, same recovered datastore/object counts, all four static containers running and both controller leases renewed |
| Isolation | Persistent guest firewall and host forwarding block; public HTTPS, production worker kubelet, NAS NFS and host SSH egress probes timed out before and after reboot |
| Lab rollback | Original VM 300 identity and both Ready nodes restored; saved replica counts, Sonarr/Prowlarr checks, Vault auto-unseal, Authentik access and cross-node networking passed; full Terraform plan had no changes; temporary recovery copies removed |

The native kubelet intentionally had no API kubeconfig, and the historical Node
records do not demonstrate fresh node registration. The following drill verifies
normal kubelet integration and production Cilium separately.

## Node and Cilium Recovery Drill

Extend the [native control-plane drill](#native-control-plane-recovery-drill) to
normal kubelet registration and the production Cilium configuration on two fresh
VMs. This tests a disposable copy of the offsite datastore. It deliberately
removes executable workload records before connecting kubelets; it does not
restore production applications or their volumes.

1. Quiesce lab applications and save both original VM 300/301 archives, node
   identities, PV inventory and replica counts. Verify both archives before
   replacing either VM. Review Terraform plans for exactly those two replacements,
   restore their scoped permissions with `make lab-permissions`, and prepare both
   fresh nodes with the shared prerequisite play. Confirm new machine IDs and no
   existing Kubernetes credentials or datastore.
2. Before enabling the host egress block, cache the archived control-plane images,
   configured pause image, production Cilium/Envoy/operator images, CoreDNS and the
   synthetic fixture image on both nodes. Use `crictl pull` and verify the image
   references with `crictl inspecti`: raw `ctr` tag-plus-digest imports can miss
   kubelet's canonical digest lookup and cause blocked download attempts.
3. Keep the worker stopped while running the native static control-plane restore
   and verification. Retain the Proxmox `vmbr1` forwarding block throughout this
   drill. Copy `quarantine-recovered-workloads.py` and
   `bootstrap-recovered-control-plane.py` beside the native helper on VM 300.
4. Run the quarantine helper as root. It requires verified standalone kubelet,
   pauses the two static controllers, removes executable Kubernetes workloads,
   admission webhooks and stale node/Cilium identities from the **recovered copy**,
   verifies their absence and records the source snapshot hash. Secrets,
   configuration, RBAC, volume records and Helm history remain. If it fails, inspect
   the failure with the controllers stopped; do not enable normal kubelet.
5. Run `bootstrap-recovered-control-plane.py --source <input> --cilium-values
   <shared-values>`, using `ansible/roles/k8s_control_plane/files/cilium-values.yml`.
   It rechecks the empty workload set, retains the original CA and archived kubelet
   settings, and generates only the kubelet kubeconfig through a dedicated kubeadm
   phase. It does not initialize a new cluster. The temporary administrator
   certificate comes from the native drill and lasts one day. Label/taint the
   registered control plane as usual.
6. The guest firewall now permits the two lab nodes, the configured production Pod
   range, and Proxmox-initiated administration. Its narrow HTTP reply exception to
   `172.26.0.1` permits Cilium Gateway proxy replies that bypass the ordinary
   conntrack state match. Host forwarding still blocks external access. On the
   worker, persist `192.168.10.50/32 via 172.26.0.10` before kubelet startup: that
   address belongs to the recovered API on control-plane loopback. Start the
   worker and join through the existing `k8s_worker` role with the lab inventory;
   its short-lived token is revoked after the attempt.
7. Forward local port 16444 through Proxmox to `172.26.0.10:6443`, using a separate
   private kubeconfig with the recovered CA, temporary administrator certificate
   and TLS server name `192.168.10.50`. Keep the original lab kubeconfig for
   rollback. Upgrade the retained Cilium release using the production path:

   ```bash
   cilium upgrade --kubeconfig .lab/network-recovery/kubeconfig \
     --version 1.19.1 \
     --values ansible/roles/k8s_control_plane/files/cilium-values.yml \
     --set k8sServiceHost=192.168.10.50 --set k8sServicePort=6443
   ```

   Recreate CoreDNS through `kubeadm init phase addon coredns --config
   <recovered-kubeadm-config>`. Require both nodes Ready and all Cilium/Envoy,
   operator and DNS Pods healthy. Check the actual Cilium ConfigMap: cluster name
   `kubernetes`, ID `0`, pool `10.0.0.0/8`, kube-proxy replacement, Gateway API and
   L2 announcements remain the production settings. This drill does not migrate
   the overlapping production Pod/Service ranges.
8. Apply `tests/recovery/network-fixture.yml` only to this quarantined cluster. It
   places server/client Pods on opposite nodes and creates a private Gateway VIP
   `172.26.0.241` with hostname `recovery.invalid`. Verify internal DNS, cross-node
   Service HTTP, Gateway/HTTPRoute conditions and an HTTP request from Proxmox to
   the VIP. Apply a temporary deny-egress NetworkPolicy selecting only the client;
   require its previously working direct Service request to fail, then remove the
   policy and require traffic to return. Check public HTTPS, production worker,
   NAS, host SSH and management SSH are inaccessible from the client.
9. Reboot each node separately. Require a new boot ID with its existing fresh node
   identity, healthy static/API components, both nodes Ready, and repeat the
   networking/isolation checks. Inventory running Pods: only the explicitly
   installed infrastructure and synthetic fixture may run.
10. Stop both disposable VMs and restore **both** verified original VM archives.
    Verify original SSH keys and machine IDs before restoring trust. Confirm the
    recovered datastore and copied credentials are absent, close the temporary
    tunnel, remove only the drill host firewall table and reopen original lab
    access. Restore saved replica counts and verify original application data,
    networking, production health and a full no-change Terraform plan. Only then
    remove temporary archives, downloaded inputs and generated credentials.

The two-node drill passed from the same completed offsite bundle:

| Check | Verified result |
|-------|-----------------|
| Fresh nodes | Both VMs replaced from template 9010; new machine IDs/system UUIDs and real kubelet registration using the recovered CA |
| Containment | Executable records removed only from the recovered copy before normal kubelet startup; only explicitly installed infrastructure and fixture Pods ran |
| Cilium | Production 1.19.1 chart and shared values; original cluster identity and IPAM retained; two agents and Envoys plus operator healthy |
| Traffic | Internal DNS and cross-node Service HTTP passed; temporary deny-egress policy blocked the direct Service request; traffic returned after removal |
| Gateway | Lab VIP `172.26.0.241` allocated and announced; Gateway/HTTPRoute accepted; Proxmox HTTP request returned the synthetic response |
| Reboots | Both nodes returned Ready after separate reboots; their identities persisted and DNS, Service/Gateway traffic and isolation passed again |
| Convergence | Shared worker join role completed with zero changes after recovery |
| Lab rollback | Both original node identities and PV specifications restored; saved replicas and Sonarr/Prowlarr, Vault, Authentik and network checks passed; full Terraform plan had no changes; production remained healthy |

The [combined drill below](#combined-machine-and-application-recovery-drill) adds
offsite application-volume recovery to these fresh machines.
The Gateway check covers the isolated bridge; it does not establish physical
network failover, multi-control-plane availability or application recovery.

## Combined Machine and Application Recovery Drill

Run the node/Cilium recovery and independent offsite-volume restore in the same
fresh two-node environment. This closes the gap between testing replacement
machines and testing an application on an already running lab. The bounded
application fixture is qBittorrent configuration/resume state; its media payload
and VPN remain separate recovery requirements.

1. Follow the [two-node recovery procedure](#node-and-cilium-recovery-drill),
   including verified rollback archives for both original VMs. Before blocking
   routed egress, also cache the committed local-path provisioner/helper and
   qBittorrent images on both fresh nodes through CRI.
2. Recover the complete offsite etcd bundle, quarantine executable records, join
   both fresh nodes and converge production Cilium/CoreDNS. Verify the network
   fixture before installing application storage. Keep the Proxmox egress block
   in place throughout application import and testing.
3. Read only `backups/velero-repo-credentials` from this recovered API into a
   protected process buffer. Use `export_kopia_password` from the existing
   `verify-etcd-recovery.py` helper to validate its identity and write the private
   password file. Use it with the HCP S3 export and
   [read-only Kopia helper](backup-and-restore.md#independent-repository-credential-recovery).
   Neither the repository password nor application files come from the original
   lab VM archives or the live production cluster.
4. Apply the shared lab local-path provisioner to the recovered cluster. Derive a
   separate namespace and PVC from the committed qBittorrent lab manifests, pin
   the test to the fresh worker and keep the namespace's deny-all policy. Do not
   reuse historical PV records or their paths. Verify the new PVC/PV identity,
   worker affinity and empty directory before importing.
5. Prepare the downloaded volume using the existing no-transfer qBittorrent
   procedure: fresh authentication, stopped resume records, disabled hooks and
   discovery, loopback torrent interface, and no media/VPN mount. Import into the
   new PVC; compare every prepared file hash before starting the application.
6. Verify source torrent/category/path/history metadata, fresh login,
   unauthenticated rejection and zero peers. Repeat after application restart,
   then reboot each fresh VM separately. Require the same fresh node identities
   and PVC binding, a new boot ID, working DNS/Service/Gateway traffic and the same
   application checks after each reboot. Public, API and NAS probes from the
   application must stay blocked.
7. Save only nonsensitive evidence. Restore both original VM archives using the
   node recovery rollback procedure; verify original node/PV identities,
   applications, networking, Terraform convergence and production health before
   removing temporary rollback archives, source copies and generated credentials.

The combined drill passed using etcd set `recovery-20260922-202350.json` and
qBittorrent Kopia snapshot `a3aa2dbe8202b4ba7d09b12c87bfa50b`:

| Check | Verified result |
|-------|-----------------|
| Machines | Both original VMs replaced from template 9010; new machine IDs, system UUIDs and node registrations |
| Control plane/network | Offsite static-pod recovery, workload quarantine, normal node join and production Cilium configuration; DNS, cross-node Service and lab Gateway passed |
| Credentials/data | S3 credentials from HCP; Kopia password from this recovered API; application volume downloaded read-only from S3 without production/MinIO/NAS reads |
| New storage | Shared provisioner created a new worker-local PVC/PV; target was empty; all 34 prepared-file hashes matched before startup |
| Application | qBittorrent 5.2.3 retained source torrent/category/path/history metadata; fresh login passed and anonymous access was rejected; zero peers |
| Restart/reboots | Checks passed after application restart and each node reboot; fresh node identities and the new PVC binding persisted; Cilium/Envoy healthy |
| Isolation | Only expected infrastructure and fixtures ran; public, recovered API, production worker and NAS probes from the application timed out |
| Lab rollback | Original node/PV identities and application data checks passed; original networking restored; Terraform reported no changes and production remained healthy; temporary drill copies removed |

The measured interval from the start of the VM destruction apply to first
successful restored-application API verification was **10 minutes 2 seconds**.
It excludes rollback archive creation, the initial etcd download, later reboot
acceptance and restoring the original lab. It is a measured drill phase, not an
agreed production recovery-time target. No download payload, VPN bootstrap,
physical-host rebuild or other application recovery is established by this fixture.

## Sonarr Recovery

The lab manifests under `k8s/clusters/homelabrestore01/` provide the shared local-path provisioner and a Sonarr deployment using production's image and chart versions. Sonarr has a fresh local PVC, no production media mount or HTTPRoute, and restricted egress. Namespace traffic is denied by default; narrow policies allow the lab controllers and Recyclarr to reach Sonarr, and Sonarr to reach lab Prowlarr and DNS. Administrative access uses port forwarding. The production ApplicationSet does not discover this cluster.

The [backup runbook](backup-and-restore.md#verified-sonarr-offsite-restore) records the source, checks and limits of the completed database restore. Non-database configuration is recreated from declared configuration and fresh lab credentials. Production recovery should use Helm/Git, Vault/ESO, media-operator, Prowlarr and Recyclarr according to their existing ownership; it should not accumulate a second manual configuration procedure. The lab operator reconciles a bounded Sonarr configuration; production download clients, notifications and indexers remain isolated.

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

## Media-operator Reconciliation

The lab runs the same `media-operator-pvr` 0.34.3 chart as production, watching only `restore-sonarr`. Its Secret access is scoped to that namespace. Metrics are disabled because the lab has no monitoring stack. The lab `SonarrConfig` uses a fresh API-key Secret, a local `/config/restore-media/tv` directory and the same declared media-management/download-handling settings as production. It does not declare production integrations or take ownership of Recyclarr's profiles.

To repeat after the database restore:

1. Create `restore-sonarr-api-key` in `restore-sonarr` with key `api-key` matching the lab Sonarr API key. Supply its value through a private file or process input, not shell arguments or terminal output.
2. Create `/config/restore-media/tv` inside Sonarr's local PVC, owned by 977:988. This empty directory substitutes for a media root; it contains no recovered media.
3. Apply the lab `media-operator` resource Kustomization, then render/apply its pinned Helm chart with CRDs included. Use release `restore-media-operator`, namespace `restore-sonarr`, and the committed lab values. Every Kubernetes command must specify `.lab/kubeconfig`.
4. Wait for the SonarrConfig CRD to become Established and the operator Deployment to become Ready, then apply the lab `media-config` Kustomization.
5. Inspect both Ready and Synced conditions, their observed generation, and the actual Sonarr API settings. A successful Deployment alone does not demonstrate reconciliation.
6. Change a managed setting through the lab API and remove only the lab root-folder API entry. Within the one-minute reconciliation interval, verify the setting and entry are restored. Compare series/episode identities with the source dump and confirm Sonarr still cannot reach public HTTPS, either Kubernetes API, or NAS NFS.

Network access is limited by pod identity: the operator can reach the lab API, CoreDNS and Sonarr. The subsequent Prowlarr drill adds only DNS and lab Prowlarr access for Sonarr. Retain the namespace default-deny policy. Keep restored integration credentials isolated; do not apply production media-config resources unchanged.

The drill passed initial reconciliation and a second repair: the operator corrected all three changed settings, created the missing lab root-folder entry, and recreated it after deletion (API ID 2 became 3). Ready and Synced conditions matched the current generation. All series and episode identities still matched the source dump, all 54 episode-file records remained, and all four Sonarr egress probes timed out as expected. Verification completed at 2026-09-21 14:07:38 UTC.

This verifies Sonarr's bounded media-operator reconciliation. The following drills cover Recyclarr and Prowlarr's synchronization path. Production tracker recovery, download clients, notifications, Vault/ESO credential bootstrap and Authentik remain separate recovery checks.

## Recyclarr and Prowlarr Recovery

The lab uses production's Recyclarr 8.7.1, Prowlarr 2.5.2 and indexer-operator 0.34.0 pins. Both clusters consume the same Recyclarr profile ConfigMap from `k8s/components/recyclarr-config`; URL environment overrides select the lab, while the default URLs preserve production behavior. The suspended lab CronJob runs only `sync sonarr`, stores its cache on local-path storage and uses a separate lab Secret. Run jobs sequentially against that cache.

Recyclarr repaired a deliberately disabled upgrade setting, adopted all 31 existing custom formats, and recreated the deleted `WEB-1080p` profile. Its new ID was **8**, replacing **7**. The lab series was temporarily assigned another profile to permit deletion, then reassociated with the recreated profile by name. A third sync reported no changes to profiles, formats, quality sizes or naming. This proves the configured profile can be recreated; consumers such as Seerr must resolve and verify the resulting ID rather than reuse production's numeric ID.

Prowlarr starts with a fresh local database and lab API key. The indexer operator recreates its Sonarr application connection and a Torznab indexer named `Recovery Fixture` from the lab `ProwlarrConfig`. A local Python fixture advertises TV categories and returns one synthetic release because Prowlarr rejects an empty feed during validation. Its download URL returns 404, and it serves no media. It does not use real tracker credentials or public tracker endpoints.

The operator reports Ready and Synced for the declared application and indexer. Prowlarr synchronizes `Recovery Fixture (Prowlarr)` into Sonarr using the lab endpoint and credentials. Sonarr's indexer connection test passes. After deleting only the test entry from Sonarr, `ApplicationIndexerSync` completed and recreated it (ID 7 became 8). All series/episode identities and 54 episode-file records remained intact; both applications timed out against the four blocked network probes. Verification completed at 2026-09-21 14:30:31 UTC. This validates the Prowlarr-to-Sonarr synchronization path, not recovery of the five production tracker definitions or their credentials. The four original indexer rows in the restored Sonarr database remain isolated; a new Prowlarr database does not automatically adopt or remove those old connections.

### Repeat the Drill

1. Complete the Sonarr restore first. Create `restore-recyclarr-secrets` with a `secrets.yml` entry named `sonarr_api_key` containing the lab Sonarr key. Use private process input or a protected file. Use `radarr_api_key: unused-lab-only` for the shared configuration's unused Radarr reference; `sync sonarr` excludes that instance.
2. Apply the lab Recyclarr resource Kustomization and render/apply its pinned Helm chart with release `restore-recyclarr` and the committed values. Run `kubectl --kubeconfig .lab/kubeconfig -n restore-sonarr create job --from=cronjob/restore-recyclarr <unique-job-name>`. Verify completion, logs, profile settings and custom-format counts; repeat to confirm no further changes. Leave the CronJob suspended.
3. Create `restore-prowlarr-api-key` with a new `api-key` value. Apply the `indexer-fixture` and `prowlarr` resource Kustomizations, then render/apply Prowlarr's chart as `restore-prowlarr` with the committed values.
4. Apply the `media-operator-indexers` resource Kustomization and render/apply its pinned chart as `restore-media-operator-indexers`, including CRDs. The 0.34.3 chart includes FlareSolverr RBAC; no separate workaround is required.
5. Confirm Prowlarr's `/api/v1/appprofile` maps ID 1 to `Standard` before applying its CR. The CR currently requires a numeric app-profile ID. Apply `media-config`, then check Ready/Synced conditions at the current generation and verify actual application/indexer state through both APIs.
6. Test the synchronized indexer through Sonarr. To verify repair, delete only `Recovery Fixture (Prowlarr)` from Sonarr and run Prowlarr's `ApplicationIndexerSync` command; confirm the indexer returns and the command completes. Never delete the restored production indexers as part of this test.
7. Compare restored series/episode identities and the 54 episode-file records against the source dump. Retest blocked connections to the production API, NAS, lab API and unrelated public HTTPS from both applications.

Prowlarr needs the official `indexers.prowlarr.com` catalog even when using the built-in Torznab schema. Its Cilium policy allows that hostname on HTTPS, the local fixture, Sonarr and DNS. Recyclarr alone can fetch public HTTPS guide resources; it has only fresh lab credentials. Sonarr can reach only lab Prowlarr and DNS. Neither application can reach production/NAS endpoints or arbitrary public HTTPS. These are deliberately different permissions for different recovery roles, not a namespace-wide internet allowance.

## Dependent Profile Resolution

The released `media-operator-requests` 0.34.1 controller was tested temporarily in `restore-sonarr` against the real restored Sonarr and an isolated Seerr API fixture. It resolved stale profile ID `7` to `WEB-1080p` ID `8`, then reconciled successfully with the numeric ID omitted. Selecting a nonexistent profile made `Synced` false and left the fixture's connection and write count unchanged. The temporary controller, fixture, Secret, custom resource and network allowances were removed after verification; the existing PVR/indexer controllers remain on 0.34.1.

This tests the released controller's profile dependency, not Seerr login or restored application data. Production declares profiles by name and still needs reachable Sonarr/Radarr APIs, valid API keys and profiles created by Recyclarr.

## Authentik Database Recovery

The `authentik-database` lab manifests provide a separate `restore-auth` namespace, a fresh local PVC and PostgreSQL 17.9. The database-only step starts no Authentik server/worker or Service. Its namespace denies all network traffic; administration uses `kubectl exec` and the local PostgreSQL socket.

The [S3 logical-dump restore](backup-and-restore.md#authentik-postgresql-recovery) passed a transactional restore and source/restored count comparison. The separate `authentik-server` manifests then enable the [verified emergency-login/OIDC check](backup-and-restore.md#verified-application-and-oidc-recovery), allowing only server-to-database traffic and DNS. They require the original Authentik application secret key in a lab Secret. No worker or embedded outpost is enabled. Ordinary password/MFA login, client applications and independently available recovery credentials remain unverified.

## Tdarr Recovery

The `tdarr` manifests run Tdarr 2.86.01 in `restore-tdarr`, using fresh local storage and namespace deny-all networking. Restore the native archive while the server is stopped, following the [Tdarr recovery procedure](backup-and-restore.md#tdarr-native-archive-recovery), before applying the Deployment. Supply a fresh lab API-key Secret; no production credentials, media volumes, GPUs or worker nodes are configured.

The server loads the archived flows, libraries, variables and file metadata exactly; all archived plugin file hashes match. API authentication and isolation checks passed. Transcoding, media recovery and normal UI/SSO login remain outside this verification.

## qBittorrent Recovery

The `qbittorrent` manifests provide an isolated client in `restore-qbittorrent` with fresh local storage and deny-all networking. Prepare and import the stopped lab copy before applying the Deployment, following the [configuration/resume recovery procedure](backup-and-restore.md#qbittorrent-configuration-and-resume-recovery). The client has no VPN sidecar, download volume, Service or route.

Fresh login, torrent/category/path/history comparisons, network isolation and persistence across restart passed. The restored torrent reports `missingFiles`, which is expected because payload data was not restored. VPN bootstrap and real transfer recovery remain separate checks.

## Vault Recovery

The `infrastructure/vault` base restores Vault 1.21.2 in `restore-vault` on a
fresh local PVC, with a cluster-internal Service and no external route. Import the
quiesced encrypted archive before starting the Deployment and supply the original
KMS credentials privately. DNS, the regional KMS HTTPS endpoint and the lab API
are allowed; production storage/API remain unreachable. Vault uses an explicitly
projected rotating token with only TokenReview permission.

The [file-backend recovery procedure](backup-and-restore.md#vault-file-backend-recovery)
verified all 109 restored file digests, the original Vault identity, and KMS
auto-unseal across restart. The [Kubernetes auth/ESO check](backup-and-restore.md#kubernetes-auth-and-eso-recovery)
then verified restricted login, matching Grafana credentials, rejection of invalid
identities/permissions, and Secret recreation across controller restarts. ESO is
scoped to this namespace. The admin credential came from the local Vault CLI file;
KMS/S3 credential retrieval from HCP was independently verified. A subsequent
fresh-PVC restore of the direct S3 archive passed auto-unseal and authenticated
reads without production access; its temporary resources were removed. A protected credential copy independent of HCP remains open.

The lab now runs the `infrastructure/vault-raft` overlay after the verified
[file-to-Raft migration and native snapshot restore](backup-and-restore.md#raft-migration-and-native-snapshot-rehearsal).
Its original file PVC remains for rollback; Raft and snapshot staging each have a
separate local PVC. The lab snapshot CronJob stays suspended. Production now uses
local Raft and a daily direct S3 snapshot job. Its first uploaded native snapshot
also passed a fresh-PVC lab restore; temporary verification resources were removed.

## etcd and API Recovery

The [isolated verifier](disaster-recovery.md#isolated-etcd-and-api-verification)
restored a production S3 etcd snapshot and its matching PKI on the lab control-plane
host using separate container storage and loopback-only networking. Snapshot
integrity, revision bump/compaction, TLS and recovered API object counts passed.
The optional controller check also passed leader election, Deployment/Pod creation,
scheduler binding and automatic node-certificate approval/registration. Runtime
mode then connected a real kubelet with that certificate, verified Node readiness
and lease renewal, and ran one inert pause container in a separate CRI and dedicated
cgroup inside the disconnected namespace. The control-plane VM now has 4 GiB RAM
for this drill, managed through its existing Terraform node variables.
Temporary containers, services, cgroups, networking, restored data and copied/generated
credentials were removed afterward; both original lab nodes remain Ready.
The [native control-plane](#native-control-plane-recovery-drill) and
[node/Cilium recovery](#node-and-cilium-recovery-drill) drills extend these checks
to replacement VMs. The [combined drill](#combined-machine-and-application-recovery-drill)
then restored an offsite qBittorrent volume on those fresh machines; other
application/integration coverage remains in the backlog. The separate
[worker replacement drill](#worker-replacement-drill) verifies a fresh lab worker
and restoration of its locally checkpointed volumes.

## Access and Teardown

Every manual command must select the lab kubeconfig explicitly:

```bash
kubectl --kubeconfig .lab/kubeconfig get pods -A
make lab-ssh
```

`make lab-disconnect` closes the local API tunnel. `make lab-destroy` destroys only the VMs managed by the lab workspace; it retains the host bridge, firewall, API identity and local SSH key for the next drill. Deleting the lab VMs deletes their local restored data. Preserve any required evidence before teardown. After rebuilding a VM, verify its new host-key fingerprint through the Proxmox console before replacing its old known-hosts entry.
