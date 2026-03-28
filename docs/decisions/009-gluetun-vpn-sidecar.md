# ADR-009: Gluetun VPN Sidecar for Downloads

## Status

Accepted

## Context

The download client (qBittorrent) must route all traffic through a VPN to protect privacy. The VPN solution must enforce a kill-switch (no traffic leaks if the tunnel drops) and coexist with the cluster's Cilium networking and network policies.

## Decision

Run Gluetun as a sidecar container in the same pod as qBittorrent. Gluetun establishes a WireGuard tunnel to Private Internet Access (PIA), and qBittorrent shares Gluetun's network namespace so all its traffic is encapsulated. A CiliumNetworkPolicy (`arr-egress-vpn`) grants the VPN pod unrestricted world egress while all other arr pods are restricted to internal traffic only.

## Alternatives Considered

- **Cilium egress gateway**: Route traffic from labeled pods through a dedicated gateway node with a VPN tunnel. Cleaner separation but significantly more complex to set up, requires a dedicated egress node, and Cilium's egress gateway feature is still maturing.
- **VPN at the router/firewall level**: Route all traffic from specific VMs through a VPN. Simpler network config but overly broad — would VPN traffic for all pods on that node, not just the download client.
- **Standalone VPN pod with proxy**: Run Gluetun separately and configure qBittorrent to use it as a SOCKS/HTTP proxy. Adds network hops and proxy configuration complexity. Proxy misconfiguration could leak traffic.
- **No VPN**: Not acceptable for torrent traffic.

## Rationale

- **Kill-switch by design**: Gluetun's built-in firewall blocks all non-tunnel traffic. If the VPN drops, qBittorrent has no network path — it cannot leak.
- **Shared network namespace**: The sidecar pattern means qBittorrent doesn't need any VPN configuration. It sees Gluetun's network as its own. Port forwarding from PIA is passed through automatically.
- **Network policy isolation**: The `arr-egress-vpn` CiliumNetworkPolicy selectively allows world egress only for the VPN pod. Other arr pods (Sonarr, Radarr) are limited to DNS, intra-namespace, HTTPS, and NFS.
- **Simplicity**: One pod, one VPN tunnel, one download client. No proxy chains or gateway nodes to manage.
- **Health checks**: Gluetun exposes a health endpoint via its control server. qBittorrent's container startup depends on Gluetun readiness, preventing traffic before the tunnel is up.

## Consequences

- The `NET_ADMIN` capability is required for Gluetun to create the WireGuard interface. This is an exception to the default security posture.
- PIA credentials are stored in Vault and synced via ExternalSecret. If the VPN provider is changed, both the secret and Gluetun environment variables must be updated.
- VPN tunnel failures make the download client completely unavailable (by design). Monitoring relies on Gluetun's health check and pod restart behavior.
