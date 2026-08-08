# Repository Layout

Annotated directory tree showing the purpose of each section of the repository.

```
homelab/
├── Makefile                         # All operational commands
├── mkdocs.yml                       # Documentation site config
├── docs-requirements.txt            # MkDocs dependencies
├── renovate.json                    # Renovate dependency update config
├── docs/                            # Documentation source
├── scripts/
│   ├── vault-init.sh                # One-time Vault init + ESO K8s auth setup
│   ├── render-manifests.sh          # Render every ApplicationSet manifest; diff bootstrap
│   ├── check-alert-metrics.sh       # Verify alert selectors match live Prometheus series
│   └── gen-crd-schemas.sh           # Generate kubeconform schemas from media-operator charts
├── packer/
│   └── k8s-node/                    # K8s node VM template
│       ├── k8s-node.pkr.hcl         # Packer build config (proxmox-iso)
│       ├── variables.pkr.hcl        # Variable definitions
│       ├── k8s-node.auto.pkrvars.hcl.example  # Example variables
│       ├── playbook.yml             # Ansible provisioner playbook
│       └── http/                    # Ubuntu autoinstall config
│           ├── user-data
│           └── meta-data
├── terraform/
│   ├── modules/proxmox-vm/          # Reusable VM module
│   ├── hosts/<cluster>/             # Per-cluster VM provisioning
│   │   ├── terraform.tfvars.example # Example variables
│   │   ├── variables.tf             # Variable definitions
│   │   ├── main.tf                  # VM provisioning
│   │   ├── providers.tf             # Provider config
│   │   ├── versions.tf              # Version constraints
│   │   └── outputs.tf               # Terraform outputs
│   └── aws/                         # KMS key for Vault unseal, IAM user for offsite backup
├── ansible/
│   ├── ansible.cfg                  # Ansible configuration
│   ├── requirements.yml             # Galaxy collections
│   ├── playbooks/
│   │   ├── pve-host.yml             # Proxmox host setup
│   │   └── k8s-cluster.yml          # K8s cluster bootstrap
│   ├── inventory/
│   │   ├── <pve-host>/              # Proxmox host inventory + vaulted vars
│   │   └── <cluster>/               # K8s node inventory + NAS vars
│   ├── roles/
│   │   ├── base/                    # Common node setup
│   │   ├── igpu/                    # Intel iGPU driver setup
│   │   ├── nfs/                     # NFS client setup
│   │   ├── k8s_prereqs/             # Container runtime, kubeadm
│   │   ├── k8s_control_plane/       # kubeadm init + Cilium
│   │   ├── k8s_worker/              # kubeadm join
│   │   ├── pve_repos/               # Proxmox repo config
│   │   ├── pve_api_token/           # Proxmox API token
│   │   ├── pve_cloud_init/          # Cloud-init template
│   │   ├── pve_iommu/               # IOMMU/VFIO setup
│   │   ├── pve_pci_mapping/         # PCI device mapping
│   │   ├── pve_network/             # Bridges and VLAN subinterfaces
│   │   ├── pve_ups/                 # NUT server for the CyberPower UPS
│   │   ├── pve_disable_ksm/         # Disable KSM (ksmd oops wedges guests)
│   │   ├── pve_disable_wireless/    # Disable the unused AX211 radio
│   │   └── tfc_agent/               # Terraform Cloud agent
│   └── group_vars/all/
│       └── vars.yml                 # Global variables
├── k8s/
│   ├── bootstrap/                   # Applied with kubectl, NOT reconciled by ArgoCD
│   │   ├── argocd/                  # ArgoCD installation
│   │   │   ├── kustomization.yml    # Kustomize overlay
│   │   │   ├── namespace.yml        # argocd namespace
│   │   │   ├── ingress.yml          # ArgoCD HTTPRoute
│   │   │   └── custom-ca.yml        # Homelab CA trust for OIDC
│   │   └── applicationsets/         # ApplicationSet definitions
│   │       ├── kustomization.yml    # Kustomize wrapper
│   │       └── cluster-apps.yml     # Git File Generator ApplicationSet
│   ├── components/
│   │   ├── gateway-api/             # Gateway API CRDs
│   │   └── kyverno-policies/        # Shared ClusterPolicy manifests
│   └── clusters/<cluster>/
│       ├── infrastructure/          # Platform components
│       │   ├── vault/
│       │   │   ├── config.yml       # App metadata for ApplicationSet
│       │   │   ├── values.yml       # Helm values
│       │   │   ├── kustomization.yml # Supporting resources list
│       │   │   ├── pdb.yml          # Supporting resource
│       │   │   └── httproute.yml    # Supporting resource
│       │   ├── external-secrets/
│       │   ├── cert-manager/
│       │   ├── gateway/             # Gateway + L2 pool + HTTP redirect
│       │   ├── gateway-api/         # Gateway API CRD installation
│       │   ├── metrics-server/
│       │   ├── nfs-provisioner/
│       │   ├── local-path-provisioner/
│       │   ├── intel-gpu-operator/
│       │   ├── intel-gpu-plugin/
│       │   ├── kube-prometheus-stack/
│       │   ├── loki/
│       │   ├── alloy/
│       │   ├── nut-exporter/
│       │   ├── minio/
│       │   ├── velero/
│       │   ├── etcd-backup/
│       │   ├── authentik/
│       │   ├── reloader/
│       │   ├── descheduler/
│       │   ├── vpa/
│       │   ├── goldilocks/
│       │   ├── kyverno/
│       │   ├── kyverno-policies/
│       │   └── network-policies/
│       └── apps/                    # User-facing applications
│           ├── homepage/
│           ├── uptime-kuma/
│           ├── openclaw/
│           ├── media-operator/      # Servarr operator (Sonarr/Radarr/Prowlarr config)
│           ├── media-operator-downloads/  # Download-client operator
│           └── arr/
│               ├── prereqs/         # Shared namespace, PV, ConfigMap, API keys
│               ├── media-config/    # Servarr custom resources
│               ├── config-backup/   # Nightly SQLite dumps to NFS
│               ├── jellyfin/
│               ├── sonarr/
│               ├── radarr/
│               ├── prowlarr/
│               ├── bazarr/
│               ├── seerr/
│               ├── downloads/
│               ├── recyclarr/
│               ├── tdarr/
│               ├── unpackerr/
│               ├── flaresolverr/
│               └── exportarr/
├── .github/workflows/
│   ├── validate.yml                 # Lint, kubeconform, secret scan, manifest render
│   └── docs.yml                     # Build and publish the MkDocs site
├── .pre-commit-config.yaml          # Pre-commit hooks
├── .yamllint.yml                    # YAML lint rules
├── .ansible-lint                    # Ansible lint rules
├── .editorconfig                    # Editor settings
├── .gitignore                       # Git ignore rules
├── .trivyignore                     # Trivy false positive suppressions
├── CONTRIBUTING.md                  # Contribution guide
└── README.md                        # Project overview
```

## Design Decisions

**ApplicationSet with Git File Generator.** A single ApplicationSet discovers `config.yml` files via the glob `k8s/clusters/homelabk8s01/**/config.yml` and generates an Application per component. Each app has its own `config.yml` (metadata), `values.yml` (Helm values), and optionally a `kustomization.yml` (supporting resources). This gives full per-app control over chart versions, sync options, and namespace targeting while allowing independent syncs -- a broken app never blocks fixes to other apps.

The file extension is load-bearing: the generator matches `config.yml`, not `config.yaml`. A file named with the other extension is silently ignored.

**Three source types.** `config.yml` sets `sourceType` to one of:

| `sourceType` | Produces | Used by |
|--------------|----------|---------|
| `helm` | Multi-source Application: chart repo + `values.yml` from git + optional kustomize dir | Most components |
| `git` | Single-source Application pointing at `gitPath` | Plain manifests: gateway, network policies, etcd-backup, arr-prereqs |
| `kustomize` | Single-source Application over a kustomize directory | local-path-provisioner |

**Separation of infrastructure and apps.** Infrastructure components (Vault, External Secrets, cert-manager, Cilium Gateway, storage provisioners, monitoring) are the dependencies user-facing applications rest on. Nothing enforces the ordering -- see [Deployment Ordering](../infrastructure/index.md#deployment-ordering) -- but the split keeps the dependency direction legible.

**Namespace strategy.** Single-app namespaces use `CreateNamespace=true` on the Application, requiring no separate namespace manifest. The shared `arr` namespace is owned by a dedicated `arr/prereqs` Application that manages the namespace, shared PV, and shared ConfigMap.

**`k8s/bootstrap/` is outside GitOps.** It is applied with `kubectl apply -k` by `make k8s-bootstrap` and is not reconciled by ArgoCD, so it can drift from git undetected. `scripts/render-manifests.sh` runs `kubectl diff -k` over it and fails on drift. The ApplicationSet CRD requires `--server-side`; it exceeds the last-applied-configuration annotation limit.
