# cert-manager

cert-manager automates the issuance and renewal of TLS certificates within the cluster. It watches for Certificate resources and Ingress annotations, then provisions certificates from the configured cluster issuers.

## Details

| Field | Value |
|-------|-------|
| Chart | `cert-manager` |
| Repository | <https://charts.jetstack.io> |
| Version | v1.20.0 |
| Namespace | `cert-manager` (CreateNamespace=true) |

## Key Configuration

- **CRDs**: Installed via the Helm chart (`crds.enabled: true`).
- **Cluster Issuer Chain**: A three-stage chain bootstraps a private CA for the cluster:
    1. **selfsigned-issuer** -- a `ClusterIssuer` of type `SelfSigned`, used only to sign the root CA certificate.
    2. **homelab-ca** -- a `Certificate` resource marked `isCA: true`, using ECDSA P-256. Signed by `selfsigned-issuer` and stored in the secret `homelab-ca-secret`.
    3. **homelab-ca-issuer** -- a `ClusterIssuer` of type `CA` that references `homelab-ca-secret`. This is the issuer used by all application ingresses.

## Cluster Integration

The shared Gateway carries the issuer annotation:

```yaml
cert-manager.io/cluster-issuer: homelab-ca-issuer
```

With Gateway API support enabled, this provisions the wildcard TLS certificate referenced by the Gateway HTTPS listener. HTTPRoutes inherit TLS termination at that listener. Because the CA is internal, browsers on the LAN must trust the `homelab-ca` root certificate to avoid warnings.

The issuer chain must exist before the Gateway or any application requests a certificate. Nothing enforces that order -- a Certificate created too early stays pending and ArgoCD retries until the ClusterIssuer is ready.

## Upstream Documentation

<https://cert-manager.io>
