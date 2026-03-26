# Repository Layout

Annotated directory tree showing the purpose of each section of the repository.

```
homelab/
├── Makefile                         # All operational commands
├── mkdocs.yml                       # Documentation site config
├── docs-requirements.txt            # MkDocs dependencies
├── docs/                            # Documentation source
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
│   └── hosts/<cluster>/             # Per-cluster Terraform config
│       ├── terraform.tfvars.example  # Example variables
│       ├── variables.tf              # Variable definitions
│       ├── main.tf                   # VM provisioning
│       └── outputs.tf                # Terraform outputs
├── ansible/
│   ├── ansible.cfg                   # Ansible configuration
│   ├── requirements.yml              # Galaxy collections
│   ├── playbooks/
│   │   ├── pve-host.yml              # Proxmox host setup
│   │   └── k8s-cluster.yml           # K8s cluster bootstrap
│   ├── inventory/
│   │   ├── <pve-host>/hosts.yml      # Proxmox host inventory
│   │   └── <cluster>/hosts.yml       # K8s node inventory
│   ├── roles/
│   │   ├── base/                     # Common node setup
│   │   ├── igpu/                     # Intel iGPU driver setup
│   │   ├── k8s_control_plane/        # kubeadm init + Cilium
│   │   ├── k8s_prereqs/              # Container runtime, kubeadm
│   │   ├── k8s_worker/               # kubeadm join
│   │   ├── nfs/                      # NFS client setup
│   │   ├── pve_api_token/            # Proxmox API token
│   │   ├── pve_cloud_init/           # Cloud-init template
│   │   ├── pve_iommu/                # IOMMU/VFIO setup
│   │   ├── pve_pci_mapping/          # PCI device mapping
│   │   └── pve_repos/                # Proxmox repo config
│   └── group_vars/all/
│       └── vars.yml                  # Global variables
├── k8s/
│   ├── bootstrap/
│   │   ├── argocd/                   # ArgoCD installation
│   │   │   ├── kustomization.yml     # Kustomize overlay
│   │   │   ├── namespace.yml         # argocd namespace
│   │   │   ├── ingress.yml           # ArgoCD HTTPRoute
│   │   │   └── custom-ca.yml         # Homelab CA trust for OIDC
│   │   └── root-app.yml              # Root app-of-apps
│   ├── components/
│   │   └── gateway-api/              # Gateway API CRDs
│   └── clusters/<cluster>/
│       ├── config/
│       │   └── env.yml               # Shared env ConfigMap
│       ├── infrastructure/           # Platform components
│       │   ├── vault/
│       │   ├── external-secrets/
│       │   ├── cert-manager/
│       │   ├── gateway/              # Gateway + L2 pool + redirect
│       │   ├── gateway-api/          # Gateway API CRD installation
│       │   ├── metrics-server/
│       │   ├── nfs-provisioner/
│       │   ├── intel-gpu-operator/
│       │   ├── intel-gpu-plugin/
│       │   ├── kube-prometheus-stack/
│       │   ├── loki/
│       │   ├── alloy/
│       │   ├── minio/
│       │   ├── velero/
│       │   ├── authentik/
│       │   ├── reloader/
│       │   ├── descheduler/
│       │   └── network-policies/
│       └── apps/                     # User-facing applications
│           ├── homepage/
│           ├── uptime-kuma/
│           ├── openclaw/
│           │   ├── ops-claw/
│           │   └── media-claw/
│           └── arr/
│               ├── namespace.yml
│               ├── shared-data-pv.yml
│               ├── jellyfin/
│               ├── sonarr/
│               ├── radarr/
│               ├── prowlarr/
│               ├── bazarr/
│               ├── jellyseerr/
│               ├── downloads/
│               ├── recyclarr/
│               ├── tdarr/
│               ├── unpackerr/
│               ├── flaresolverr/
│               └── exportarr/
├── .editorconfig                     # Editor settings
├── .gitignore                        # Git ignore rules
├── .trivyignore                      # Trivy false positive suppressions
├── renovate.json                     # Renovate dependency update config
└── README.md                         # Project overview
```

## Design Decisions

**Directory recursion over ApplicationSets.** The root ArgoCD Application uses directory recursion to discover child Applications rather than ApplicationSets. Each application is defined as its own `application.yml` with explicit sync wave annotations, giving full per-app control over Helm values, namespace targeting, and deployment ordering. ApplicationSets trade that granularity for templating convenience, which is unnecessary at homelab scale where each application has distinct configuration.

**Separation of infrastructure and apps.** Infrastructure components (Vault, External Secrets, cert-manager, Cilium Gateway, storage provisioners, monitoring) are deployed before user-facing applications. This separation ensures that shared platform dependencies -- TLS certificates, load balancer IPs, storage classes, and secret decryption -- are healthy before any workload that relies on them attempts to start.

**Sync wave ordering.** ArgoCD sync wave annotations control the deployment sequence within each layer. Infrastructure components are assigned ascending wave numbers so that foundational services (Vault, External Secrets, cert-manager) are ready before components that depend on them (monitoring, backups). Applications deploy at higher wave numbers, guaranteeing the full platform is in place first. This eliminates race conditions that would otherwise require manual intervention or retry loops.
