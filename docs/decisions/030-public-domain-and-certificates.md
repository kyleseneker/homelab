# ADR-030: Public Domain and Certificates for Homelab Services

## Status

Accepted. Amended 2026-11-08: a single `*.home.seneker.io` record in the UniFi gateway replaced the per-service records, so a new route needs no DNS change.

## Context

Homelab services are named `*.homelab.local` and use certificates from the internal CA ([ADR-005](005-cert-manager-self-signed-ca.md)), with trust distributed inside the cluster by trust-manager ([ADR-020](020-ca-trust-distribution.md)). Every client device has to install and trust that root CA. Household members' phones and TVs will not have a private CA installed, so the services cannot become household services as they stand.

Two further constraints apply:
- **Apple's certificate rules**: Apple platforms reject a TLS server certificate without the serverAuth extended key usage, even from a trusted private CA ([Apple requirements](https://support.apple.com/en-us/103769)).
- **The `.local` domain**: `.local` is reserved for Multicast DNS ([RFC 6762](https://www.rfc-editor.org/rfc/rfc6762)), so resolving it through ordinary unicast DNS depends on each client's resolver behavior.

ADR-005 rejected publicly trusted certificates only because `homelab.local` has no public DNS. A registered domain whose DNS has an API removes that obstacle. The homelab has no inbound path from the internet, so the challenge must be DNS-01. HTTP-01 needs the ACME server to reach port 80 ([challenge types](https://letsencrypt.org/docs/challenge-types/)).

## Decision

Serve homelab services under `home.seneker.io`, a subdomain of the household domain `seneker.io`, with publicly trusted Let's Encrypt certificates.

### Domain and DNS

- **Registration**: `seneker.io` is registered through Route 53. `terraform/aws` manages the registration (auto-renew, transfer lock, contact privacy) and the hosted zone.
- **Names**: Household services are named `<app>.home.seneker.io`, and `home.seneker.io` itself serves the Homepage dashboard that links to the rest. Names directly under `seneker.io`, such as a blog or resume, are reserved for deliberately public sites.
- **Split-horizon DNS**: `home.seneker.io` records exist only in the UniFi gateway's local DNS. A wildcard record, `*.home.seneker.io`, points every service name at the Cilium Gateway's L2 address. The bare `home.seneker.io`, which a wildcard does not match, and `proxmox.home.seneker.io`, which points at the Proxmox host, keep their own records. A name without a route resolves to the Gateway, which answers 404. The public zone holds no homelab records. It carries the homelab's ACME challenge record and the public sites' records, and Terraform manages its contents.

### Certificates

- **Issuers**: cert-manager ClusterIssuers for Let's Encrypt staging and production, solving ACME DNS-01 through Route 53 ([cert-manager Route 53](https://cert-manager.io/docs/configuration/acme/dns01/route53/)). The issuers name the hosted zone ID, so cert-manager needs no zone-lookup permission.
- **One certificate**: `*.home.seneker.io` plus the bare `home.seneker.io`, which a wildcard does not match, serves the Gateway's HTTPS listeners for the domain, requested with the `server auth` usage. Gateway certificates are explicit `Certificate` resources, because cert-manager's Gateway integration applies a single issuer per Gateway. Individual service names never appear in Certificate Transparency logs, and the certificate cannot impersonate a public site under `seneker.io`.
- **Credentials**: A dedicated IAM user whose policy allows changes only to TXT records named `_acme-challenge.home.seneker.io` in that zone. The policy uses Route 53's record-name and record-type condition keys ([Route 53 IAM conditions](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/specifying-rrset-conditions.html)), plus reads of record sets and change status. A compromised cluster cannot alter any other record in the zone, including the public sites'. The access key is stored in Vault and synced into the `cert-manager` namespace by External Secrets ([ADR-007](007-vault-eso-secrets.md)).

### Migration and the internal CA

- **Both names in parallel**: During migration the Gateway serves the existing `*.homelab.local` listener with its internal-CA certificate alongside a `*.home.seneker.io` listener with the Let's Encrypt certificate. HTTPRoutes carry both hostnames, except that an Authentik proxy provider answers on one hostname, so the old names of SSO-protected apps redirect to the new ones.
- **What moves**: Configuration that embeds a hostname moves to the new name. That covers Authentik's provider URLs and redirect URIs, the ArgoCD and Grafana OIDC clients, Blackbox probes, Homepage links and the documentation.
- **What is retired after**: Once nothing uses the old names, the `homelab.local` names, the internal CA chain, the trust-manager Bundle and the CA trust guide are removed. In-cluster clients and the Blackbox exporter then trust Let's Encrypt through their images' system root stores, which each consumer must be verified to ship. This ADR then replaces ADR-005 and ADR-020.

## Alternatives Considered

- **Keep the internal CA and install it on every device**: No new dependencies, but every phone, tablet and TV needs a manually installed and trusted profile, repeated for each new device and person.
- **`home.arpa` with the internal CA**: The name reserved for home networks ([RFC 8375](https://www.rfc-editor.org/rfc/rfc8375)) avoids `.local`'s ambiguity, but still needs the CA on every device.
- **HTTP-01 challenges**: Need the internet to reach port 80. Adding an inbound path only to obtain certificates is not justified.
- **Per-service certificates**: Publish every service name in Certificate Transparency logs and multiply issuance against Let's Encrypt's rate limits.
- **A personal domain**: Family-facing services under one person's name.
- **Services directly under `seneker.io`**: Shorter names, but internal services would share a namespace, a wildcard certificate and a challenge record with public sites. A compromise of the cluster's certificate or DNS credentials would then reach them too.
- **A delegated subdomain zone for cert-manager**: Isolates challenge records in their own zone. The record-name IAM condition gives the same scope without a second zone.
- **Another DNS provider**: Cloudflare and others are supported by cert-manager. Route 53 is already in the homelab's AWS account and Terraform, and GoDaddy's DNS API has been restricted for small accounts.
- **Tunnel or overlay certificates (Tailscale, Cloudflare Tunnel)**: Couple internal TLS to an external-access decision ([Phase 3.3](../roadmap/phase-3-network.md#33-plan-external-access-for-jellyfin)) and to a third party.

## Consequences

- **Renewal depends on outside services**: Let's Encrypt and Route 53 must be reachable when a certificate renews. Renewal starts a month before expiry, so a short outage has no effect, and the existing certificate expiry alerts still apply.
- **The wildcard key covers everything**: Whoever can read the Gateway's TLS Secret can impersonate every service, so access to that Secret is administrative access.
- **Clients must use the gateway's DNS**: Devices using their own encrypted DNS or a relay may not see internal-only records. If that matters for a household device, a public wildcard record pointing at the private gateway address would fix it, revealing only an RFC 1918 address.
- **The domain becomes a dependency**: If it lapses, every service breaks. Auto-renew is managed in Terraform, and Route 53 sends renewal notices to the registrant.
- **`.io` has a long-term question**: It is a country-code domain whose territory is changing sovereignty. Retirement would come with a five-to-ten-year runway, and split-horizon DNS keeps a move to another domain a rename.
- **Some details become public**: The domain, its wildcard certificate and its WHOIS record are public. Contact privacy hides the registrant except state and country.
- **Credentials and limits**: Terraform state holds the IAM access key, like the existing keys. Let's Encrypt rate limits make the staging issuer the place to test changes.
- **The migration touches every service**: Every route and every hostname-dependent configuration changes, so it proceeds service by service with both names live.
