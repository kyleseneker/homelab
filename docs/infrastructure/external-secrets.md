# External Secrets Operator

External Secrets Operator (ESO) syncs secrets from HashiCorp Vault into Kubernetes `Secret` objects, enabling secret rotation without Git commits.

## Details

| Field | Value |
|-------|-------|
| Chart | `external-secrets` |
| Repository | <https://charts.external-secrets.io> |
| Version | 2.2.0 |
| Namespace | `external-secrets` |
| Sync Wave | -3 |

## Key Configuration

- **CRDs**: Installed via Helm
- **Resources** (controller):
    - Requests: 25m CPU, 32Mi memory
    - Limits: 128Mi memory
- **Webhook resources**:
    - Requests: 10m CPU, 16Mi memory
    - Limits: 64Mi memory
- **Cert controller resources**:
    - Requests: 10m CPU, 16Mi memory
    - Limits: 64Mi memory

## Architecture

ESO uses three custom resources:

| Resource | Scope | Purpose |
|----------|-------|---------|
| `ClusterSecretStore` | Cluster | Defines the connection to Vault (auth method, server URL, KV path) |
| `ExternalSecret` | Namespace | Declares which Vault keys to sync into a K8s Secret |
| `Secret` | Namespace | Standard K8s Secret, created and managed by ESO |

A single `ClusterSecretStore` named `vault-backend` is configured to connect to Vault at `http://vault.vault.svc.cluster.local:8200` using Kubernetes authentication.

## How It Works

1. ESO authenticates to Vault using its service account token (Kubernetes auth method)
2. Each `ExternalSecret` specifies a Vault path and the keys to extract
3. ESO fetches the values and creates or updates the target K8s `Secret`
4. Secrets are refreshed on a configurable interval (default: 1 hour)
5. If Vault is temporarily unavailable, existing K8s Secrets remain intact

## Adding a New Secret

1. Store the value in Vault:

    ```bash
    vault kv put homelab/apps/my-app API_KEY=secret_value
    ```

2. Create an `ExternalSecret` manifest:

    ```yaml
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: my-app-secrets
      namespace: my-namespace
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: ClusterSecretStore
        name: vault-backend
      target:
        name: my-app-secrets
      data:
        - secretKey: API_KEY
          remoteRef:
            key: apps/my-app
            property: API_KEY
    ```

3. Commit and push -- ArgoCD syncs the `ExternalSecret`, and ESO creates the K8s Secret.

## Cluster Integration

ESO is deployed by the ApplicationSet as an independent Application. The `ClusterSecretStore` is a supporting resource applied via the kustomize source alongside the Helm chart. `ExternalSecret` resources in other apps are similarly applied as supporting resources in their respective kustomize sources. They may fail initially if Vault is not yet initialized, but the retry backoff on each Application handles this gracefully.

## Upstream Documentation

<https://external-secrets.io>
