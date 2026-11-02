# cert-manager

cert-manager automates the issuance and renewal of TLS certificates within the cluster. It watches for Certificate resources and provisions certificates from the configured cluster issuers.

## Details

| Field | Value |
|-------|-------|
| Chart | `cert-manager` |
| Repository | <https://charts.jetstack.io> |
| Version | v1.21.3 |
| Namespace | `cert-manager` (CreateNamespace=true) |

## Key Configuration

- **CRDs**: Installed via the Helm chart (`crds.enabled: true`).
- **Cluster Issuer Chain**: A three-stage chain bootstraps a private CA for the cluster:
    1. **selfsigned-issuer** -- a `ClusterIssuer` of type `SelfSigned`, used only to sign the root CA certificate.
    2. **homelab-ca** -- a `Certificate` resource marked `isCA: true`, using ECDSA P-256. Signed by `selfsigned-issuer` and stored in the secret `homelab-ca-secret`.
    3. **homelab-ca-issuer** -- a `ClusterIssuer` of type `CA` that references `homelab-ca-secret`. It issues the `*.homelab.local` certificate.
- **Let's Encrypt issuers**: `letsencrypt-staging` and `letsencrypt-production` solve ACME DNS-01 through Route 53 for the `home.seneker.io` zone ([ADR-030](../decisions/030-public-domain-and-certificates.md)). They name the hosted zone ID and read `route53-dns01-credentials`, which External Secrets syncs from Vault at `infrastructure/cert-manager-route53`. That IAM user may only write the `_acme-challenge.home.seneker.io` TXT record.
- **DNS-01 self-check**: The UniFi gateway's DNS holds internal-only `home.seneker.io` records, so cert-manager checks challenge propagation against public resolvers (`--dns01-recursive-nameservers-only`, `1.1.1.1` and `9.9.9.9`).

## Cluster Integration

The Gateway's certificates are explicit `Certificate` resources in `infrastructure/gateway/certificates.yml`, not generated from Gateway annotations. cert-manager's Gateway integration applies one issuer per Gateway, and its update and reissue checks ignore changes to key usages. The Gateway's listeners use different issuers while services move to the new domain.

| Certificate | Names | Issuer | Listener |
|---|---|---|---|
| `homelab-gateway-tls` | `*.homelab.local` | `homelab-ca-issuer` | `https` |
| `home-gateway-tls` | `*.home.seneker.io`, `home.seneker.io` | `letsencrypt-production` | `https-home`, `https-home-root` |

HTTPRoutes inherit TLS termination at the listener for their hostname. Browsers must trust the `homelab-ca` root certificate for `*.homelab.local` names; `*.home.seneker.io` certificates are publicly trusted.

Both certificates request the `server auth` usage. That adds the serverAuth extended key usage, which Apple platforms require on every TLS server certificate, including ones from a private CA ([Apple requirements](https://support.apple.com/en-us/103769)). Without it, an iPhone or Mac that trusts the CA still rejects the connection.

Changing a Certificate's usages does not by itself trigger a reissue. Force one with `cmctl renew -n default <certificate>`, or without `cmctl` by adding an `Issuing=True` condition with reason `ManuallyTriggered` to the Certificate's status subresource. Then verify the certificate the Gateway actually serves:

```bash
echo | openssl s_client -connect 192.168.10.201:443 -servername home.homelab.local 2>/dev/null \
  | openssl x509 -noout -dates -text | grep -A1 'Extended Key Usage'
```

The issuers must exist before the Gateway's certificates are requested. Nothing enforces that order -- a Certificate created too early stays pending and ArgoCD retries until the ClusterIssuer is ready.

## Upstream Documentation

<https://cert-manager.io>
