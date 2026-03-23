# cert-manager

cert-manager automates the issuance and renewal of TLS certificates within the cluster. It watches for Certificate resources and Ingress annotations, then provisions certificates from the configured cluster issuers.

## Details

| Field | Value |
|-------|-------|
| Chart | `cert-manager` |
| Repository | <https://charts.jetstack.io> |
| Version | v1.17.1 |
| Namespace | `cert-manager` (CreateNamespace=true) |
| Sync Wave | -3 |

## Key Configuration

- **CRDs**: Installed via the Helm chart (`installCRDs: true`).
- **Cluster Issuer Chain**: A three-stage chain bootstraps a private CA for the cluster:
    1. **selfsigned-issuer** -- a `ClusterIssuer` of type `SelfSigned`, used only to sign the root CA certificate.
    2. **homelab-ca** -- a `Certificate` resource marked `isCA: true`, using ECDSA P-256. Signed by `selfsigned-issuer` and stored in the secret `homelab-ca-secret`.
    3. **homelab-ca-issuer** -- a `ClusterIssuer` of type `CA` that references `homelab-ca-secret`. This is the issuer used by all application ingresses.

## Cluster Integration

Every Ingress resource in the cluster annotates with:

```yaml
cert-manager.io/cluster-issuer: homelab-ca-issuer
```

This triggers cert-manager to automatically provision a TLS certificate for the host defined in the Ingress. Because the CA is internal, browsers on the LAN must trust the `homelab-ca` root certificate to avoid warnings.

cert-manager deploys at sync wave -3 so that the issuer chain is ready before any ingress controller or application attempts to request a certificate.

## Upstream Documentation

<https://cert-manager.io>
