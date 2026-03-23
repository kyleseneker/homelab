SHELL := /bin/bash
.DEFAULT_GOAL := help

CLUSTER  ?= homelabk8s01
PVE_HOST ?= homelabpve01

TF_DIR       := terraform/hosts/$(CLUSTER)
ANSIBLE_DIR  := ansible
INVENTORY    := $(ANSIBLE_DIR)/inventory/$(CLUSTER)/hosts.yml
K8S_PLAYBOOK := $(ANSIBLE_DIR)/playbooks/k8s-cluster.yml

export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg

CP_IP := $(shell cd $(TF_DIR) && terraform output -raw control_plane_ip 2>/dev/null || echo "unknown")

.PHONY: help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

VAULT_FILE    := $(ANSIBLE_DIR)/group_vars/all/vault.yml
VAULT_PW_FILE := .vault-password
VAULT_ARGS    := --vault-password-file ../$(VAULT_PW_FILE)

.PHONY: deps vault-create vault-edit vault-encrypt vault-decrypt

deps: ## Install Ansible Galaxy collections
	ansible-galaxy collection install -r $(ANSIBLE_DIR)/requirements.yml

vault-create: ## Create an empty vault.yml and encrypt it
	@if [ ! -f $(VAULT_PW_FILE) ]; then \
		echo "Enter a vault password:" && read -s pw && echo "$$pw" > $(VAULT_PW_FILE); \
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
# Proxmox host  (override with PVE_HOST=<name>)
# ---------------------------------------------------------------------------

.PHONY: pve-configure pve-ssh

PLAYBOOK_VAULT_ARGS := $(if $(wildcard $(VAULT_PW_FILE)),$(VAULT_ARGS),)

pve-configure: ## Configure Proxmox host (repos, IOMMU, cloud-init, API token)
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(PVE_HOST)/hosts.yml playbooks/pve-host.yml

pve-ssh: ## SSH into Proxmox host
	ssh root@$$(cd $(ANSIBLE_DIR) && grep ansible_host inventory/$(PVE_HOST)/hosts.yml | head -1 | awk '{print $$2}')

# ---------------------------------------------------------------------------
# Kubernetes cluster  (override with CLUSTER=<name>)
# ---------------------------------------------------------------------------

.PHONY: k8s-init k8s-plan k8s-infra k8s-configure k8s-deploy k8s-destroy k8s-bootstrap k8s-secrets k8s-kubeconfig k8s-ssh-cp

k8s-init: ## Initialize Terraform for K8s VMs
	cd $(TF_DIR) && terraform init

k8s-plan: ## Preview K8s VM changes
	cd $(TF_DIR) && terraform plan

k8s-infra: ## Provision K8s VMs on Proxmox
	cd $(TF_DIR) && terraform apply -auto-approve

k8s-configure: ## Bootstrap K8s cluster via Ansible
	cd $(ANSIBLE_DIR) && ansible-playbook $(PLAYBOOK_VAULT_ARGS) -i inventory/$(CLUSTER)/hosts.yml playbooks/k8s-cluster.yml

k8s-deploy: k8s-infra k8s-configure k8s-bootstrap ## Full deploy: VMs + cluster + ArgoCD

k8s-destroy: ## Tear down all K8s VMs
	cd $(TF_DIR) && terraform destroy

k8s-bootstrap: ## Install ArgoCD and root app-of-apps (one-time)
	kubectl apply -k k8s/bootstrap/argocd/
	@echo "Waiting for ArgoCD to be ready..."
	kubectl -n argocd wait --for=condition=available deployment/argocd-server --timeout=300s
	kubectl apply -f k8s/bootstrap/root-app.yml

k8s-secrets: ## Apply VPN, Recyclarr, and Homepage secrets to the cluster
	kubectl apply -f k8s/clusters/homelabk8s01/apps/arr/vpn-secret.yml
	kubectl apply -f recyclarr-secret.yml
	kubectl apply -f homepage-secret.yml

k8s-kubeconfig: ## Copy kubeconfig from control plane to local machine
	scp media@$(CP_IP):~/.kube/config ./kubeconfig
	@echo "Run: export KUBECONFIG=$$(pwd)/kubeconfig"

k8s-ssh-cp: ## SSH into control plane
	ssh media@$(CP_IP)
