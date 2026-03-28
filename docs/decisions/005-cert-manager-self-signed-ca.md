# ADR-005: cert-manager with Self-Signed CA

## Status

Accepted

## Context

All internal services run behind HTTPS on `*.homelab.local` subdomains. The cluster needs automated TLS certificate provisioning for Gateway API listeners and internal service communication.

## Decision

Use cert-manager with a three-stage self-signed CA chain: a `SelfSigned` ClusterIssuer creates a root CA certificate (`homelab-ca`, ECDSA P-256), which backs a `CA` ClusterIssuer (`homelab-ca-issuer`) that issues all per-service certificates. Clients (browsers, OS) import the root CA to trust the internal PKI.

cert-manager deploys at sync wave -3 to ensure issuers and certificates are available before any Gateway or application that needs TLS.

## Alternatives Considered

- **Let's Encrypt (ACME)**: Free, publicly trusted certificates. Requires DNS-01 or HTTP-01 challenges, which need either a public DNS provider API or internet-reachable endpoints. Neither is available on a private `homelab.local` domain with no public DNS.
- **Step-ca (Smallstep)**: Full-featured private CA with ACME support. More capable than cert-manager's built-in CA issuer, but adds another stateful service to operate. The additional features (short-lived certs, SSH certs) aren't needed here.
- **Manual certificates**: Generate certs with openssl and mount as Secrets. No automation, no rotation, doesn't scale with 15+ services.
- **mkcert**: Developer-focused tool for local CAs. No Kubernetes integration or automated renewal.

## Rationale

- **Private domain**: `homelab.local` is not publicly resolvable, ruling out ACME-based issuers without additional infrastructure (external DNS provider, split-horizon DNS).
- **Automation**: cert-manager watches Certificate resources and Gateway annotations, automatically provisioning and renewing TLS certificates without manual intervention.
- **Gateway API integration**: cert-manager's Gateway API support (`gateway.networking.k8s.io/v1`) provisions certs directly from Gateway listener definitions.
- **Simplicity**: The built-in `SelfSigned` and `CA` issuer types require no external dependencies. The entire CA chain is defined in a single YAML file.
- **ECDSA P-256**: Smaller key size and faster TLS handshakes compared to RSA, with equivalent security.

## Consequences

- Every client device must import the `homelab-ca` root certificate to avoid browser warnings. The trust procedure is documented in the "Trust the CA" getting-started guide.
- If the CA certificate expires or is lost, all issued certificates become invalid. The CA cert should be included in the cluster backup strategy.
- Certificates are only trusted internally. Any service exposed externally in the future would need a separate ACME-based issuer.
