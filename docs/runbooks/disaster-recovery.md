# Disaster Recovery

This runbook covers recovery procedures for the most severe failure scenarios, from a single node going down to a complete cluster rebuild.

## Complete Cluster Rebuild

Use this procedure when the entire Kubernetes cluster is lost and must be rebuilt from scratch.

### Prerequisites

Before a disaster occurs, ensure the following are available **outside the cluster**:

- Vault unseal key and root token (stored in password manager after `make vault-init`)
- Velero backups stored on MinIO (running on the NAS or otherwise accessible)
- This Git repository (the single source of truth for all cluster state)

!!! warning "Critical"
    If you do not have the Vault unseal key, Vault cannot be unsealed after a rebuild. Store the unseal key and root token in your password manager.

### Procedure

1. Rebuild the cluster infrastructure:

    ```bash
    make k8s-deploy
    ```

    This provisions VMs with Terraform, bootstraps Kubernetes with Ansible, and installs ArgoCD with the root application.

2. Retrieve the kubeconfig:

    ```bash
    make k8s-kubeconfig
    export KUBECONFIG=$(pwd)/kubeconfig
    ```

3. Wait for Vault to become available:

    ```bash
    kubectl -n vault wait --for=condition=ready pod/vault-0 --timeout=300s
    ```

4. Unseal Vault with the stored unseal key:

    ```bash
    make vault-unseal
    ```

5. Verify ESO is syncing secrets:

    ```bash
    kubectl get externalsecret --all-namespaces
    ```

6. Wait for ArgoCD to sync all applications. Monitor progress in the ArgoCD UI or with:

    ```bash
    kubectl get applications -n argocd
    ```

7. Once Velero and MinIO are running, restore the most recent backup:

    ```bash
    velero backup get
    velero restore create --from-backup <backup-name>
    ```

8. Verify the restore completed successfully:

    ```bash
    velero restore get
    kubectl get pods --all-namespaces
    ```

## Single Node Failure

If a single Kubernetes node fails (VM crash, disk corruption, etc.), re-provision it with Terraform and re-join it to the cluster with Ansible:

```bash
make k8s-infra && make k8s-configure
```

Terraform will recreate the failed VM and Ansible will configure it and join it back to the cluster. Pods that were scheduled on the failed node will be rescheduled automatically by Kubernetes.

## NAS Failure

All PersistentVolumeClaim data is stored on NFS shares hosted by the NAS. If the NAS becomes unavailable:

- Pods with NFS-backed volumes will hang on volume mount operations.
- New pods requiring NFS volumes will remain in `ContainerCreating` state.
- Running pods that already have volumes mounted may continue to work temporarily but will fail on any new I/O operations.

Recovery depends entirely on the NAS hardware and its RAID/backup configuration. Once the NAS is restored and NFS exports are available again, pods will recover automatically.

!!! tip
    If the NAS will be down for an extended period, you can delete the hanging pods to prevent them from consuming cluster resources. They will be recreated (and hang again) only if their controllers attempt rescheduling.

## Vault Unseal Key Loss

If the Vault unseal key is lost:

- You cannot unseal Vault; encrypted secrets in Vault may be unrecoverable without backups.
- You must re-initialize Vault and repopulate secrets from `.example` files, application UIs, and other authoritative sources.

### Recovery Procedure

1. Locate all `.example` files in the repository -- these contain the secret structure with placeholder values.
2. Re-initialize Vault and save the new credentials:

    ```bash
    make vault-init
    ```

    Save the unseal key and root token from the output to your password manager.

3. For each secret, write values to Vault:

    ```bash
    vault kv put homelab/<path> key1=value1 key2=value2
    ```

4. ESO syncs the new secrets from Vault automatically.

## What Is NOT Backed Up

!!! warning
    The following data is **not** included in Velero backups and will be lost in a disaster:

    - Volumes using `emptyDir` (ephemeral per-pod storage)
    - Node-local storage (hostPath volumes, local PVs)
    - Data written to container filesystems outside of mounted volumes
    - Kubernetes secrets that exist only in etcd and have no corresponding secret material in Vault or ExternalSecret manifests in Git
