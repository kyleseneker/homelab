# Repository Layout

Annotated directory tree showing the purpose of each section of the repository.

```
homelab/
├── Makefile                         # All operational commands
├── mkdocs.yml                       # Documentation site config
├── docs-requirements.txt            # MkDocs dependencies
├── docs/                            # Documentation source
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
│   │   ├── k8s-control-plane/        # kubeadm init + Cilium
│   │   ├── k8s-prereqs/              # Container runtime, kubeadm
│   │   ├── k8s-worker/               # kubeadm join
│   │   ├── nfs/                      # NFS client setup
│   │   ├── pve-api-token/            # Proxmox API token
│   │   ├── pve-cloud-init/           # Cloud-init template
│   │   ├── pve-iommu/                # IOMMU/VFIO setup
│   │   ├── pve-pci-mapping/          # PCI device mapping
│   │   └── pve-repos/                # Proxmox repo config
│   └── group_vars/all/
│       └── vars.yml                  # Global variables
├── k8s/
│   ├── bootstrap/
│   │   ├── argocd/                   # ArgoCD installation
│   │   │   ├── kustomization.yml     # Kustomize overlay
│   │   │   ├── namespace.yml         # argocd namespace
│   │   │   ├── ingress.yml           # ArgoCD ingress
│   │   │   └── custom-ca.yml         # Homelab CA trust for OIDC
│   │   └── root-app.yml              # Root app-of-apps
│   ├── components/
│   │   └── metallb-config/           # MetalLB IP pool + L2 ad
│   └── clusters/<cluster>/
│       ├── config/
│       │   └── env.yml               # Shared env ConfigMap
│       ├── infrastructure/           # Platform components
│       │   ├── sealed-secrets/
│       │   ├── cert-manager/
│       │   ├── metallb/
│       │   ├── metallb-config/
│       │   ├── metrics-server/
│       │   ├── nfs-provisioner/
│       │   ├── intel-gpu-operator/
│       │   ├── intel-gpu-plugin/
│       │   ├── ingress-nginx/
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
│               └── exportarr/
├── .editorconfig                     # Editor settings
├── .gitignore                        # Git ignore rules
└── README.md                         # Project overview
```

## Design Decisions

**Directory recursion over ApplicationSets.** The root ArgoCD Application uses directory recursion to discover child Applications rather than ApplicationSets. Each application is defined as its own `application.yml` with explicit sync wave annotations, giving full per-app control over Helm values, namespace targeting, and deployment ordering. ApplicationSets trade that granularity for templating convenience, which is unnecessary at homelab scale where each application has distinct configuration.

**Separation of infrastructure and apps.** Infrastructure components (Sealed Secrets, cert-manager, MetalLB, ingress-nginx, storage provisioners, monitoring) are deployed before user-facing applications. This separation ensures that shared platform dependencies -- TLS certificates, load balancer IPs, storage classes, and secret decryption -- are healthy before any workload that relies on them attempts to start.

**Sync wave ordering.** ArgoCD sync wave annotations control the deployment sequence within each layer. Infrastructure components are assigned ascending wave numbers so that foundational services (Sealed Secrets, cert-manager) are ready before components that depend on them (ingress-nginx, monitoring). Applications deploy at higher wave numbers, guaranteeing the full platform is in place first. This eliminates race conditions that would otherwise require manual intervention or retry loops.
