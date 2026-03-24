# Vault KMS Migration Runbook

This runbook covers two scenarios:

1. **One-time migration** — migrating the existing live Vault from Shamir to AWS KMS auto-unseal
2. **Disaster recovery bootstrap** — what to do after a full cluster rebuild when Vault needs to auto-unseal from day one

---

## Background

Vault is configured to auto-unseal using AWS KMS. On every pod restart, Vault contacts AWS KMS to decrypt the master key — no manual intervention required. The AWS credentials used for this are stored in a Kubernetes Secret (`vault-aws-kms` in the `vault` namespace) that is **never committed to Git**.

!!! warning "Bootstrap dependency"
    The `vault-aws-kms` Secret must exist in the `vault` namespace before the Vault pod starts. On a fresh cluster rebuild, create this Secret **before** running `make k8s-bootstrap`.

---

## Prerequisites

- `aws` CLI configured with an account that can create KMS keys and IAM users
- `terraform` CLI installed
- `vault` CLI installed
- `kubectl` configured with cluster access
- Vault's Shamir unseal key and root token in your password manager (needed for the one-time migration)

---

## Part 1: Provision AWS Resources

This is a one-time step. Skip if the KMS key and IAM user already exist.

```bash
cd terraform/aws

# Copy the example vars file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars if you want a different region or environment label

make aws-init
make aws-plan   # review what will be created
make aws-apply
```

After `apply` completes, capture the outputs:

```bash
terraform output kms_key_id           # e.g. 1234abcd-...
terraform output aws_access_key_id    # e.g. AKIA...
terraform output -raw aws_secret_access_key   # the secret — do not log this
```

---

## Part 2: Create the Bootstrap Kubernetes Secret

This Secret is **never stored in Git**. You must recreate it after any full cluster rebuild.

```bash
kubectl create secret generic vault-aws-kms \
  --namespace vault \
  --from-literal=AWS_ACCESS_KEY_ID="<aws_access_key_id>" \
  --from-literal=AWS_SECRET_ACCESS_KEY="<aws_secret_access_key>" \
  --from-literal=AWS_REGION="us-east-1" \
  --from-literal=VAULT_AWSKMS_SEAL_KEY_ID="<kms_key_id>"
```

Verify it was created:

```bash
kubectl get secret vault-aws-kms -n vault
```

---

## Part 3: One-Time Migration (Shamir → KMS)

This section applies only when migrating a live Vault that was previously initialized with Shamir keys. If you are setting up Vault for the first time with KMS already enabled, skip to [Part 4](#part-4-verify-auto-unseal).

### Step 1 — Apply Phase 1 config (seal stanza with `disabled = "true"`)

The `vault/application.yml` already contains the `seal "awskms"` stanza with `disabled = "true"`. Commit and push this to Git. ArgoCD will sync automatically and restart the Vault pod.

```bash
git add k8s/clusters/homelabk8s01/infrastructure/vault/application.yml
git commit -m "feat: add AWS KMS seal stanza (disabled) for migration"
git push
```

Wait for the pod to restart and be Running:

```bash
kubectl -n vault get pods -w
```

### Step 2 — Manually unseal Vault one last time

```bash
kubectl port-forward -n vault pod/vault-0 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200

vault status   # should show: Sealed: true, Seal Type: shamir
vault operator unseal <shamir-unseal-key>
vault login <root-token>
```

Confirm it's unsealed:

```bash
vault status   # Sealed: false
```

### Step 3 — Migrate the master key from Shamir to KMS

```bash
vault operator unseal -migrate <shamir-unseal-key>
```

Vault re-encrypts the master key under the AWS KMS key. After this command:

```bash
vault status   # Seal Type: awskms
```

### Step 4 — Remove `disabled = "true"` from the seal stanza

Edit [k8s/clusters/homelabk8s01/infrastructure/vault/application.yml](../../k8s/clusters/homelabk8s01/infrastructure/vault/application.yml) and remove the `disabled = "true"` line from the `seal "awskms"` block:

```hcl
seal "awskms" {
  region     = env("AWS_REGION")
  kms_key_id = env("VAULT_AWSKMS_SEAL_KEY_ID")
}
```

Commit and push:

```bash
git add k8s/clusters/homelabk8s01/infrastructure/vault/application.yml
git commit -m "feat: activate AWS KMS auto-unseal (remove disabled flag)"
git push
```

---

## Part 4: Verify Auto-Unseal

After ArgoCD syncs the Phase 2 config, test that Vault auto-unseals on pod restart:

```bash
kubectl -n vault delete pod vault-0
kubectl -n vault wait --for=condition=ready pod/vault-0 --timeout=120s

kubectl port-forward -n vault pod/vault-0 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200
vault status
```

Expected output:

```
Key                      Value
---                      -----
Recovery Seal Type       awskms
Initialized              true
Sealed                   false
...
```

Verify ESO is still syncing secrets:

```bash
kubectl get clustersecretstore vault-backend
kubectl get externalsecret --all-namespaces
```

All ExternalSecrets should show `SecretSynced`.

---

## Part 5: Disaster Recovery Bootstrap

Use this procedure any time you rebuild the cluster from scratch.

1. Ensure the AWS KMS key still exists (`make aws-plan` should show no changes needed)
2. **Before** running `make k8s-bootstrap`, create the `vault-aws-kms` Secret:

    ```bash
    kubectl create secret generic vault-aws-kms \
      --namespace vault \
      --from-literal=AWS_ACCESS_KEY_ID="<access_key_id>" \
      --from-literal=AWS_SECRET_ACCESS_KEY="<secret_access_key>" \
      --from-literal=AWS_REGION="us-east-1" \
      --from-literal=VAULT_AWSKMS_SEAL_KEY_ID="<kms_key_id>"
    ```

    If the `vault` namespace doesn't exist yet, create it first:

    ```bash
    kubectl create namespace vault
    kubectl create secret generic vault-aws-kms --namespace vault ...
    ```

3. Run `make k8s-bootstrap` — ArgoCD will deploy Vault, which will auto-unseal via KMS
4. If Vault's PVC data was restored from a Velero backup, Vault will be initialized and unsealed automatically. If the PVC was lost entirely, you'll need to run `make vault-init` to re-initialize.

!!! note "Keep the Shamir key"
    Even after migrating to KMS, keep the Shamir unseal key in your password manager. It may be needed if the KMS key becomes temporarily unavailable (e.g., AWS outage, accidental key deletion scheduling).

---

## Troubleshooting

**Vault pod fails to start (`CreateContainerConfigError`)**

The `vault-aws-kms` Secret is missing. Create it following Part 2 above.

**Vault starts but remains sealed**

Check KMS connectivity:

```bash
kubectl -n vault logs vault-0
```

Look for errors like `failed to unseal` or `AccessDeniedException`. Verify the IAM policy and that the access key in the Secret is correct.

**ESO shows `SecretSyncError` after migration**

Vault is unsealed but ESO's Kubernetes auth token may have expired. Force a resync:

```bash
kubectl annotate externalsecret <name> -n <namespace> \
  force-sync=$(date +%s) --overwrite
```
