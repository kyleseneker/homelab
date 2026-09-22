SHELL := /bin/bash
.DEFAULT_GOAL := help

CLUSTER  ?= homelabk8s01
PVE_HOST ?= homelabpve01

TF_DIR       := terraform/hosts/$(CLUSTER)
PACKER_DIR   := packer/k8s-node
ANSIBLE_DIR  := ansible
INVENTORY    := $(ANSIBLE_DIR)/inventory/$(CLUSTER)/hosts.yml
K8S_PLAYBOOK := $(ANSIBLE_DIR)/playbooks/k8s-cluster.yml

export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg
export KUBECONFIG ?= $(CURDIR)/kubeconfig

CP_IP      = $(shell cd $(TF_DIR) && terraform output -raw control_plane_ip 2>/dev/null || echo "unknown")
CILIUM_VER := $(shell grep k8s_control_plane_cilium_version $(ANSIBLE_DIR)/group_vars/all/vars.yml | awk -F'"' '{print $$2}')

.PHONY: help docs docs-serve

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

docs: ## Build documentation site
	pip install -q -r docs-requirements.txt && mkdocs build

docs-serve: ## Serve documentation site locally
	pip install -q -r docs-requirements.txt && mkdocs serve

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

VAULT_FILE    := $(ANSIBLE_DIR)/group_vars/all/vault.yml
VAULT_PW_FILE := .vault-password
VAULT_ARGS    := --vault-password-file ../$(VAULT_PW_FILE)

.PHONY: deps vault-create vault-edit vault-encrypt vault-decrypt

deps: ## Install Ansible Galaxy collections
	ansible-galaxy collection install -r $(ANSIBLE_DIR)/requirements.yml

vault-create: ## Create an empty vault.yml ready for editing and encryption
	@if [ ! -f $(VAULT_PW_FILE) ]; then \
		umask 077; echo "Enter a vault password:" && read -rs pw && printf '%s\n' "$$pw" > $(VAULT_PW_FILE); \
	fi
	@if [ ! -f $(VAULT_FILE) ]; then \
		echo "---" > $(VAULT_FILE); \
		echo "Created $(VAULT_FILE). Add secrets, then run: make vault-encrypt"; \
	else \
		echo "$(VAULT_FILE) already exists"; \
	fi

vault-edit: ## Edit vault.yml (decrypts in-place, re-encrypts on save)
	cd $(ANSIBLE_DIR) && ansible-vault edit $(VAULT_ARGS) group_vars/all/vault.yml

vault-encrypt: ## Encrypt vault.yml
	cd $(ANSIBLE_DIR) && ansible-vault encrypt $(VAULT_ARGS) group_vars/all/vault.yml

vault-decrypt: ## Decrypt vault.yml (for manual editing)
	cd $(ANSIBLE_DIR) && ansible-vault decrypt $(VAULT_ARGS) group_vars/all/vault.yml

# ---------------------------------------------------------------------------
# Packer  (VM template)
# ---------------------------------------------------------------------------

.PHONY: packer-init packer-validate packer-build

packer-init: ## Initialize Packer plugins
	cd $(PACKER_DIR) && packer init .

packer-validate: ## Validate Packer template
	cd $(PACKER_DIR) && packer validate .

packer-build: ## Build K8s node VM template on Proxmox
	cd $(PACKER_DIR) && packer build .

# ---------------------------------------------------------------------------
# Proxmox host  (override with PVE_HOST=<name>)
# ---------------------------------------------------------------------------

.PHONY: pve-configure pve-ssh

PLAYBOOK_VAULT_ARGS := $(if $(wildcard $(VAULT_PW_FILE)),$(VAULT_ARGS),)

pve-configure: ## Configure Proxmox host (repos, IOMMU, network, UPS, API token, TFC agent)
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(PVE_HOST)/hosts.yml playbooks/pve-host.yml

pve-ssh: ## SSH into Proxmox host
	ssh root@$$(cd $(ANSIBLE_DIR) && grep ansible_host inventory/$(PVE_HOST)/hosts.yml | head -1 | awk '{print $$2}')

# ---------------------------------------------------------------------------
# Kubernetes cluster  (override with CLUSTER=<name>)
# ---------------------------------------------------------------------------

SECRET_PATH ?=
KEY ?=
VAL ?=

.PHONY: k8s-init k8s-plan k8s-infra k8s-configure k8s-deploy k8s-destroy k8s-bootstrap cilium-upgrade k8s-backup k8s-backup-status k8s-restore k8s-kubeconfig k8s-ssh-cp k8s-render k8s-crd-schemas k8s-bootstrap-drift k8s-check-alerts vault-init vault-put-secret vault-status arr-keys-adopt aws-init aws-plan aws-apply

k8s-init: ## Initialize Terraform for K8s VMs
	terraform -chdir=$(TF_DIR) init

k8s-plan: ## Preview K8s VM changes
	terraform -chdir=$(TF_DIR) plan

k8s-infra: ## Provision K8s VMs on Proxmox
	terraform -chdir=$(TF_DIR) apply

k8s-configure: ## Bootstrap K8s cluster via Ansible
	@test "$(CLUSTER)" != "homelabrestore01" || { echo "Use the dedicated lab targets." >&2; exit 1; }
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(CLUSTER)/hosts.yml playbooks/k8s-cluster.yml

k8s-deploy: ## Full deploy: VMs + cluster + kubeconfig + ArgoCD
	$(MAKE) k8s-infra
	$(MAKE) k8s-configure
	$(MAKE) k8s-kubeconfig
	$(MAKE) k8s-bootstrap

k8s-destroy: ## Tear down all K8s VMs
	terraform -chdir=$(TF_DIR) destroy

k8s-bootstrap: ## Install or update ArgoCD and the ApplicationSet
	@test "$(CLUSTER)" != "homelabrestore01" || { echo "Use the dedicated lab targets." >&2; exit 1; }
	kubectl apply -k k8s/bootstrap/argocd/ --server-side --force-conflicts
	@echo "Waiting for ArgoCD to be ready..."
	kubectl -n argocd wait --for=condition=available deployment/argocd-server --timeout=300s
	kubectl apply -k k8s/bootstrap/applicationsets/ --server-side --force-conflicts

k8s-backup: ## Trigger an on-demand Velero backup of all namespaces
	velero backup create manual-$$(date +%Y%m%d-%H%M%S) \
		--default-volumes-to-fs-backup \
		--exclude-namespaces kube-system,kube-public
	@echo "Backup started. Run 'make k8s-backup-status' to check progress."

k8s-backup-status: ## Show Velero backup status
	velero backup get
	@echo ""
	velero schedule get

k8s-restore: ## List available Velero backups for restore
	@echo "Available backups:"
	@velero backup get
	@echo ""
	@echo "To restore, run: velero restore create --from-backup <backup-name>"

k8s-kubeconfig: ## Copy kubeconfig from control plane to local machine
	@test "$(CLUSTER)" != "homelabrestore01" || { echo "Use the dedicated lab targets." >&2; exit 1; }
	scp media@$(CP_IP):~/.kube/config "$(KUBECONFIG)"
	chmod 600 "$(KUBECONFIG)"
	@echo "Run: export KUBECONFIG=$$(pwd)/kubeconfig"

cilium-upgrade: ## Upgrade Cilium and enable Gateway API + L2 announcements on existing cluster
	@test "$(CLUSTER)" != "homelabrestore01" || { echo "Use the dedicated lab targets." >&2; exit 1; }
	cilium upgrade --version $(CILIUM_VER) --values ansible/roles/k8s_control_plane/files/cilium-values.yml --set k8sServiceHost=$(CP_IP) --set k8sServicePort=6443
	cilium status --wait

k8s-ssh-cp: ## SSH into control plane
	ssh media@$(CP_IP)

# ---------------------------------------------------------------------------
# HashiCorp Vault  (secrets backend for External Secrets Operator)
# ---------------------------------------------------------------------------

VAULT_NS ?= vault

k8s-render: ## Render every ApplicationSet manifest locally (same check CI runs)
	./scripts/render-manifests.sh

k8s-check-alerts: ## Audit current series referenced by local alert and recording rules
	./scripts/check-alert-metrics.sh

k8s-crd-schemas: ## Generate kubeconform schemas from the deployed media-operator charts
	./scripts/gen-crd-schemas.sh

vault-init: ## Initialize Vault and configure ESO integration (one-time)
	./scripts/vault-init.sh

export SECRET_PATH KEY VAL VAULT_NS

vault-put-secret: ## Patch one Vault key safely (set SECRET_PATH, KEY and exported VAL)
	@./scripts/with-vault.sh ./scripts/vault-put-secret.sh

arr-keys-adopt: ## Adopt live *arr keys into Vault without replacing sibling keys
	@./scripts/with-vault.sh ./scripts/arr-keys-adopt.sh

vault-status: ## Show Vault seal status
	@./scripts/with-vault.sh vault status

k8s-bootstrap-drift: ## Compare manually managed bootstrap resources with the cluster
	./scripts/check-bootstrap-drift.sh

# ---------------------------------------------------------------------------
# AWS  (KMS key + IAM user for Vault auto-unseal)
# ---------------------------------------------------------------------------

AWS_TF_DIR := terraform/aws

aws-init: ## Initialize Terraform for AWS resources
	terraform -chdir=$(AWS_TF_DIR) init

aws-plan: ## Preview AWS resource changes
	terraform -chdir=$(AWS_TF_DIR) plan

aws-apply: ## Provision AWS KMS key and IAM user for Vault auto-unseal
	terraform -chdir=$(AWS_TF_DIR) apply

# ---------------------------------------------------------------------------
# Isolated restore lab (never uses the production kubeconfig or ApplicationSet)
# ---------------------------------------------------------------------------

LAB_TF_DIR := terraform/hosts/homelabrestore01

.PHONY: lab-host lab-permissions lab-init lab-plan lab-infra lab-configure lab-tunnel lab-disconnect lab-kubeconfig lab-ssh lab-status lab-destroy

lab-host: ## Configure the isolated Proxmox bridge, firewall and lab API identity
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(PVE_HOST)/hosts.yml playbooks/restore-lab-host.yml

lab-permissions: ## Restore scoped lab ACLs after deleting a disposable VM
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(PVE_HOST)/hosts.yml playbooks/restore-lab-host.yml --tags lab_permissions

lab-init: ## Initialize the separate restore-lab Terraform workspace
	terraform -chdir=$(LAB_TF_DIR) init

lab-plan: ## Preview only the two disposable recovery VMs
	terraform -chdir=$(LAB_TF_DIR) plan

lab-infra: ## Provision the two disposable recovery VMs
	terraform -chdir=$(LAB_TF_DIR) apply

lab-configure: ## Bootstrap the lab without production storage or Applications
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/homelabrestore01/hosts.yml playbooks/restore-lab.yml

lab-tunnel: ## Open the lab API tunnel on localhost:16443
	./scripts/restore-lab-access.sh tunnel

lab-disconnect: ## Close the lab API tunnel
	./scripts/restore-lab-access.sh disconnect

lab-kubeconfig: ## Fetch lab credentials into .lab/kubeconfig
	./scripts/restore-lab-access.sh kubeconfig

lab-ssh: ## SSH to the disposable control plane through Proxmox
	./scripts/restore-lab-access.sh ssh

lab-status: ## Check nodes using only the lab kubeconfig
	kubectl --kubeconfig $(CURDIR)/.lab/kubeconfig get nodes -o wide

lab-destroy: ## Destroy only the recovery VMs; retain host network and credentials
	terraform -chdir=$(LAB_TF_DIR) destroy
