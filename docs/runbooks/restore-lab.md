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

The lab runs the same `media-operator-pvr` 0.34.1 chart as production, watching only `restore-sonarr`. Its Secret access is scoped to that namespace. Metrics are disabled because the lab has no monitoring stack. The lab `SonarrConfig` uses a fresh API-key Secret, a local `/config/restore-media/tv` directory and the same declared media-management/download-handling settings as production. It does not declare production integrations or take ownership of Recyclarr's profiles.

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
4. Apply the `media-operator-indexers` resource Kustomization and render/apply its pinned chart as `restore-media-operator-indexers`, including CRDs. The 0.34.0 chart needs the same missing FlareSolverr RBAC workaround as production; the lab grants it only in `restore-sonarr`.
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
scheduler binding and automatic node-certificate approval/registration. The Node
was a protocol fixture; no kubelet or workload execution was tested.
The lab's own control plane and workloads were unchanged. Temporary containers,
networking, restored data and copied/generated credentials were removed afterward.
Real kubelet/runtime and replacement-machine recovery remain in the backlog.

## Access and Teardown

Every manual command must select the lab kubeconfig explicitly:

```bash
kubectl --kubeconfig .lab/kubeconfig get pods -A
make lab-ssh
```

`make lab-disconnect` closes the local API tunnel. `make lab-destroy` destroys only the VMs managed by the lab workspace; it retains the host bridge, firewall, API identity and local SSH key for the next drill. Deleting the lab VMs deletes their local restored data. Preserve any required evidence before teardown. After rebuilding a VM, verify its new host-key fingerprint through the Proxmox console before replacing its old known-hosts entry.
