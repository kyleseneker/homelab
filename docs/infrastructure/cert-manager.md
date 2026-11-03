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
- **Let's Encrypt issuers**: `letsencrypt-staging` and `letsencrypt-production` solve ACME DNS-01 through Route 53 for the `home.seneker.io` zone ([ADR-030](../decisions/030-public-domain-and-certificates.md)). They name the hosted zone ID and read `route53-dns01-credentials`, which External Secrets syncs from Vault at `infrastructure/cert-manager-route53`. That IAM user may only write the `_acme-challenge.home.seneker.io` TXT record.
- **DNS-01 self-check**: The UniFi gateway's DNS holds internal-only `home.seneker.io` records, so cert-manager checks challenge propagation against public resolvers (`--dns01-recursive-nameservers-only`, `1.1.1.1` and `9.9.9.9`).

## Cluster Integration

The Gateway's certificate is an explicit `Certificate` resource in `infrastructure/gateway/certificates.yml`, not generated from Gateway annotations. cert-manager's Gateway integration applies one issuer per Gateway, and its update and reissue checks ignore changes to key usages.

| Certificate | Names | Issuer | Listener |
|---|---|---|---|
| `home-gateway-tls` | `*.home.seneker.io`, `home.seneker.io` | `letsencrypt-production` | `https-home`, `https-home-root` |

HTTPRoutes inherit TLS termination at the listener for their hostname. The certificate is publicly trusted, so clients need no extra trust configuration.

The certificate requests the `server auth` usage. That adds the serverAuth extended key usage, which Apple platforms require on every TLS server certificate ([Apple requirements](https://support.apple.com/en-us/103769)).

Changing a Certificate's usages does not by itself trigger a reissue. Force one with `cmctl renew -n default <certificate>`, or without `cmctl` by adding an `Issuing=True` condition with reason `ManuallyTriggered` to the Certificate's status subresource. Then verify the certificate the Gateway actually serves:

```bash
echo | openssl s_client -connect 192.168.10.201:443 -servername home.seneker.io 2>/dev/null \
  | openssl x509 -noout -dates -text | grep -A1 'Extended Key Usage'
```

The issuers must exist before the Gateway's certificate is requested. Nothing enforces that order -- a Certificate created too early stays pending and ArgoCD retries until the ClusterIssuer is ready.

## Upstream Documentation

<https://cert-manager.io>
