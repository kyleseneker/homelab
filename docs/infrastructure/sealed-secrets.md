# Sealed Secrets

Sealed Secrets enables GitOps-compatible secret management by allowing encrypted secrets to be safely committed to version control.

## Details

| Field | Value |
|-------|-------|
| Chart | `sealed-secrets` |
| Repository | <https://bitnami-labs.github.io/sealed-secrets> |
| Version | 2.18.4 |
| Namespace | `kube-system` |
| Sync Wave | -3 |

## Key Configuration

- **Resources**:
    - Requests: 25m CPU, 32Mi memory
    - Limits: 128Mi memory

## How It Works

1. A developer creates a standard Kubernetes Secret manifest.
2. The `kubeseal` CLI encrypts the Secret against the controller's public key, producing a `SealedSecret` resource.
3. The `SealedSecret` is committed to Git (safe to store publicly).
4. The Sealed Secrets controller in the cluster decrypts each `SealedSecret` and creates the corresponding `Secret`.

Only the controller's private key can decrypt sealed secrets, so the encrypted form is safe to store in version control.

## Sealing Workflow

Encrypt a secret using the project Makefile:

```bash
make k8s-seal FILE=path/to/secret.yml
```

!!! warning "Key Backup"
    The controller's private key is essential for decrypting all sealed secrets. Back it up with:

    ```bash
    make k8s-backup-sealed-key
    ```

    Without this key, sealed secrets cannot be recovered after a cluster rebuild. This is a critical disaster recovery step.

## Cluster Integration

Sealed Secrets deploys at sync wave -3 because many other components reference `SealedSecret` resources for credentials (Grafana admin password, MinIO credentials, Velero cloud credentials, and others). The controller must be running before those resources are applied.

## Upstream Documentation

<https://github.com/bitnami-labs/sealed-secrets>
