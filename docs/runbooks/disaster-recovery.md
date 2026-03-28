# Disaster Recovery

This runbook covers recovery procedures for the most severe failure scenarios, from a single node going down to a complete cluster rebuild.

## Complete Cluster Rebuild

Use this procedure when the entire Kubernetes cluster is lost and must be rebuilt from scratch.

### Prerequisites

Before a disaster occurs, ensure the following are available **outside the cluster**:

- Vault root token (stored in password manager after `make vault-init`)
- AWS credentials and KMS key ID for Vault auto-unseal (the `vault-aws-kms` Secret must be recreated after a rebuild)
- Velero backups stored on MinIO (local, running on the NAS) or AWS S3 (offsite, `velero-offsite-homelab` bucket in us-east-1)
- AWS credentials for the `velero-offsite-homelab` IAM user (stored in password manager, also in Vault at `infrastructure/velero-offsite`)
- This Git repository (the single source of truth for all cluster state)

!!! warning "Critical"
    Vault uses AWS KMS for auto-unseal. The `vault-aws-kms` Kubernetes Secret must be recreated **before** the Vault pod starts (step 3 below). Store the AWS credentials and KMS key ID in your password manager.

### Procedure

1. Rebuild the cluster infrastructure:

    ```bash
    make k8s-deploy
    ```

    This provisions VMs with Terraform, bootstraps Kubernetes with Ansible, and installs ArgoCD with the ApplicationSet.

2. Retrieve the kubeconfig:

    ```bash
    make k8s-kubeconfig
    export KUBECONFIG=$(pwd)/kubeconfig
    ```

3. Before ArgoCD deploys Vault, create the `vault-aws-kms` Secret so Vault can auto-unseal:

    ```bash
    kubectl create namespace vault
    kubectl create secret generic vault-aws-kms \
      --namespace vault \
      --from-literal=AWS_ACCESS_KEY_ID="<access_key_id>" \
      --from-literal=AWS_SECRET_ACCESS_KEY="<secret_access_key>" \
      --from-literal=AWS_REGION="us-east-1" \
      --from-literal=VAULT_AWSKMS_SEAL_KEY_ID="<kms_key_id>"
    ```

4. Wait for Vault to become available (it will auto-unseal via KMS):

    ```bash
    kubectl -n vault wait --for=condition=ready pod/vault-0 --timeout=300s
    ```

5. Verify ESO is syncing secrets:

    ```bash
    kubectl get externalsecret --all-namespaces
    ```

6. Wait for ArgoCD to sync all applications. Monitor progress in the ArgoCD UI or with:

    ```bash
    kubectl get applications -n argocd
    ```

7. Once Velero is running, restore from the most recent backup. If the NAS is intact, use a local MinIO backup. If the NAS is lost, restore from offsite:

    **From local (MinIO):**

    ```bash
    velero backup get
    velero restore create --from-backup <backup-name>
    ```

    **From offsite (AWS S3) -- use when NAS is unavailable:**

    First, create the offsite credentials Secret (Vault is not yet available to sync via ESO):

    ```bash
    kubectl create secret generic velero-offsite-credentials \
      --namespace backups \
      --from-file=cloud=<(printf '[default]\naws_access_key_id=<key>\naws_secret_access_key=<secret>')
    ```

    Then restore from the offsite BSL:

    ```bash
    velero backup get --storage-location offsite
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

## Vault KMS Credential Loss

Vault uses AWS KMS auto-unseal. If the AWS credentials or KMS key ID (stored in the `vault-aws-kms` Secret) are lost, Vault cannot auto-unseal.

- If the KMS key still exists in AWS but credentials are lost: recreate the IAM user and generate new access keys, then recreate the `vault-aws-kms` Secret and restart the Vault pod.
- If the KMS key itself is deleted or scheduled for deletion: contact AWS support. A key scheduled for deletion has a minimum 7-day waiting period and can be cancelled during that window.
- If both the KMS key and a Velero backup of Vault data are lost: you must re-initialize Vault and repopulate all secrets.

### Recovery Procedure (credentials lost, KMS key intact)

1. Generate new AWS access keys for the Vault IAM user.
2. Recreate the `vault-aws-kms` Secret:

    ```bash
    kubectl delete secret vault-aws-kms -n vault
    kubectl create secret generic vault-aws-kms \
      --namespace vault \
      --from-literal=AWS_ACCESS_KEY_ID="<new_access_key_id>" \
      --from-literal=AWS_SECRET_ACCESS_KEY="<new_secret_access_key>" \
      --from-literal=AWS_REGION="us-east-1" \
      --from-literal=VAULT_AWSKMS_SEAL_KEY_ID="<kms_key_id>"
    ```

3. Restart the Vault pod: `kubectl -n vault delete pod vault-0`
4. Vault auto-unseals via KMS. Verify: `vault status`

### Recovery Procedure (full Vault data loss)

1. Locate all `.example` files in the repository -- these contain the secret structure with placeholder values.
2. Recreate the `vault-aws-kms` Secret (see above).
3. Re-initialize Vault:

    ```bash
    make vault-init
    ```

    Save the root token from the output to your password manager.

4. For each secret, write values to Vault:

    ```bash
    vault kv put homelab/<path> key1=value1 key2=value2
    ```

5. ESO syncs the new secrets from Vault automatically.

## What Is NOT Backed Up

!!! warning
    The following data is **not** included in Velero backups and will be lost in a disaster:

    - Volumes using `emptyDir` (ephemeral per-pod storage)
    - Node-local storage (hostPath volumes, local PVs)
    - Data written to container filesystems outside of mounted volumes
    - Kubernetes secrets that exist only in etcd and have no corresponding secret material in Vault or ExternalSecret manifests in Git
