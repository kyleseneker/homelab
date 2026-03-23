# Secret Rotation

This runbook covers procedures for rotating application secrets and managing the Sealed Secrets controller key lifecycle.

## Standard Secret Rotation

Use this procedure to rotate any application secret (API keys, credentials, passwords).

1. Copy the original `.example` file:

    ```bash
    cp path/to/<name>-secret.example <name>-secret.yml
    ```

2. Edit `<name>-secret.yml` with the new values.

3. Seal the updated secret:

    ```bash
    make k8s-seal FILE=<name>-secret.yml
    ```

4. Move the sealed secret into the correct directory, overwriting the existing sealed secret:

    ```bash
    mv <name>-sealed-secret.yml path/to/<name>-sealed-secret.yml
    ```

5. Delete the plaintext file:

    ```bash
    rm <name>-secret.yml
    ```

6. Commit and push:

    ```bash
    git add path/to/<name>-sealed-secret.yml
    git commit -m "rotate <name> secret"
    git push
    ```

ArgoCD syncs the new SealedSecret, the Sealed Secrets controller decrypts it, and Kubernetes updates the Secret resource. Pods referencing the secret will pick up the new values on their next restart.

!!! tip
    Some applications cache secrets at startup and require a pod restart to pick up rotated values. Restart the affected deployment after the sealed secret syncs:

    ```bash
    kubectl rollout restart deployment -n <namespace> <deployment-name>
    ```

## Sealed Secrets Controller Key Rotation

The Sealed Secrets controller automatically generates a new signing key every 30 days. Old keys are retained so that existing SealedSecrets can still be decrypted.

### Forced Key Rotation

To force an immediate key rotation:

1. Back up the current key:

    ```bash
    make k8s-backup-sealed-key
    ```

2. Delete the current key secret (the controller regenerates a new one on restart):

    ```bash
    kubectl -n kube-system delete secret -l sealedsecrets.bitnami.com/sealed-secrets-key
    kubectl -n kube-system rollout restart deployment sealed-secrets
    ```

3. Back up the newly generated key:

    ```bash
    make k8s-backup-sealed-key
    ```

!!! warning "Re-sealing Required"
    After deleting the old key, all existing SealedSecrets must be re-sealed with the new key. SealedSecrets encrypted with the deleted key **cannot** be decrypted unless the old key is restored.

    To avoid re-sealing, keep the old key backup available and restore it alongside the new key if needed.

### Re-sealing All Secrets

If the old key was deleted and not retained, re-seal every secret from its `.example` file:

```bash
for example in $(find k8s/ -name '*-secret.example'); do
  name=$(basename "$example" .example)
  cp "$example" "${name}.yml"
  echo "Edit ${name}.yml with real values, then press Enter"
  read
  make k8s-seal FILE="${name}.yml"
  dir=$(dirname "$example")
  mv "${name%%-secret}-sealed-secret.yml" "$dir/"
  rm "${name}.yml"
done
```

## Secret Inventory

All secrets managed in this cluster, their namespaces, and the location of their example files:

| Secret | Namespace | Example File |
|--------|-----------|--------------|
| `vpn-credentials` | `arr` | `apps/arr/vpn-secret.example` |
| `recyclarr-secrets` | `arr` | `apps/arr/recyclarr-secret.example` |
| `homepage-secrets` | `arr` | `apps/homepage/homepage-secret.example` |
| `grafana-admin` | `monitoring` | `infrastructure/kube-prometheus-stack/grafana-secret.example` |
| `minio-credentials` | `backups` | `infrastructure/minio/minio-secret.example` |
| `velero-cloud-credentials` | `backups` | `infrastructure/velero/velero-secret.example` |

!!! note
    All paths in the table above are relative to `k8s/clusters/homelabk8s01/`.
