# Networking

This document covers the networking stack from external client access down to individual pods, including load balancing, gateway routing, TLS termination, DNS, and the VPN sidecar architecture.

## Network Architecture

```mermaid
flowchart TD
    client["Client Browser"] -->|"HTTPS request\n*.home.seneker.io"| dns["UniFi DNS"]
    dns --> ciliumVIP["Cilium L2 VIP\n192.168.10.200-250"]
    ciliumVIP --> gateway["Cilium Gateway\n(homelab-gateway)"]
    gateway -->|"TLS termination"| certManager["cert-manager\n(letsencrypt-production)"]
    gateway -->|"Route by hostname\n(HTTPRoute)"| appSvc["Application Service"]
    appSvc --> appPod["Application Pod"]
```

## Cilium Gateway API

Cilium serves as both the CNI and the gateway controller. [Multus](../infrastructure/multus.md) wraps it as each pod's CNI so selected pods can also get an interface on the IoT VLAN; Cilium stays every pod's default network and manages only `eth0`. The `homelab-gateway` Gateway accepts HTTPS on port 443 through two listeners:

| Listener | Hostnames | Certificate |
|----------|-----------|-------------|
| `https-home` | `*.home.seneker.io` | `home-gateway-tls`, from Let's Encrypt |
| `https-home-root` | `home.seneker.io`, which serves Homepage | `home-gateway-tls` |

A wildcard listener does not match the bare `home.seneker.io`, so it has its own listener. Services use their `home.seneker.io` names, which every device trusts without extra setup.

Each application defines an HTTPRoute that binds to the gateway and routes by hostname:

```yaml
route:
  main:
    enabled: true
    kind: HTTPRoute
    parentRefs:
      - group: gateway.networking.k8s.io
        kind: Gateway
        name: homelab-gateway
        namespace: default
        sectionName: https-home
    hostnames:
      - <app>.home.seneker.io
```

The HTTP listeners on port 80, `http-home` and `http-home-root`, only redirect to HTTPS, through a separate HTTPRoute (`gateway/http-redirect.yml`).

### Key Resources

| Resource | Kind | Purpose |
|----------|------|---------|
| `homelab-gateway` | Gateway | Central entry point for all HTTPS traffic |
| `homelab-pool` | CiliumLoadBalancerIPPool | Allocates IPs from `192.168.10.200-250` |
| `homelab-l2` | CiliumL2AnnouncementPolicy | Advertises allocated IPs via ARP on the LAN |
| Per-app routes | HTTPRoute | Hostname-based routing to each application service |

## Cilium L2 Announcements

Cilium replaces MetalLB for LoadBalancer IP allocation. It operates in Layer 2 mode, responding to ARP requests on the local network to advertise virtual IPs from the `homelab-pool`.

- **IP Address Pool:** `192.168.10.200` - `192.168.10.250`
- **Mode:** L2 ARP announcement
- **Consumers:** The `homelab-gateway` Gateway and any LoadBalancer Service

!!! note "L2 Limitations"
    In L2 mode, all traffic for a given VIP is handled by a single node (the current ARP responder). Failover occurs when the node becomes unavailable, at which point another node takes over the VIP.

## Gateway Certificate

`gateway/certificates.yml` declares the gateway certificate explicitly. See [cert-manager](../infrastructure/cert-manager.md) for the issuers.

**`home-gateway-tls`** covers `*.home.seneker.io` and `home.seneker.io`, because a wildcard does not match the bare name. The `letsencrypt-production` ClusterIssuer obtains it with an ACME DNS-01 challenge in Route 53. cert-manager's AWS credentials can change only the `_acme-challenge.home.seneker.io` TXT record, so the public zone never holds a service address.

## DNS

Service names resolve only on the home network and the VPN. The UniFi gateway holds one A record per hostname, pointing to the Cilium L2 VIP assigned to `homelab-gateway`. Public DNS for `home.seneker.io` holds no host records, so the names do not resolve anywhere else. Add a UniFi record with each new route.

### Application Hostnames

| Application | Hostname |
|------------|----------|
| Jellyfin | `jellyfin.home.seneker.io` |
| Sonarr | `sonarr.home.seneker.io` |
| Radarr | `radarr.home.seneker.io` |
| Prowlarr | `prowlarr.home.seneker.io` |
| Bazarr | `bazarr.home.seneker.io` |
| Seerr | `seerr.home.seneker.io` |
| qBittorrent | `qbit.home.seneker.io` |
| Tdarr | `tdarr.home.seneker.io` |
| Homepage | `home.seneker.io` |
| Uptime Kuma | `status.home.seneker.io` |
| Authentik | `auth.home.seneker.io` |
| Grafana | `grafana.home.seneker.io` |
| Prometheus | `prometheus.home.seneker.io` |
| Alertmanager | `alertmanager.home.seneker.io` |
| Vault | `vault.home.seneker.io` |
| Goldilocks | `goldilocks.home.seneker.io` |
| ArgoCD | `argocd.home.seneker.io` |

## Network Policies

CiliumNetworkPolicies enforce ingress and egress isolation in the namespaces that have policies. Rules explicitly allow the gateway, same-namespace traffic and required cross-namespace paths; coverage is not universal. See the [Network Policies infrastructure page](../infrastructure/network-policies.md) for the full policy breakdown per namespace.

!!! warning "Policy coverage and management-network boundaries"
    Selected namespaces use an implicit egress-deny model with explicit DNS, API, NFS and application exceptions. Some exceptions still allow `world` on HTTPS or broad cluster access, and namespaces without policies remain unrestricted. This does not substitute for firewall isolation of Proxmox and NAS management. Verify positive and negative connection tests before tightening those boundaries.

## VPN Sidecar Architecture

qBittorrent runs alongside a Gluetun VPN container in a shared pod. Both containers share a single network namespace, meaning all egress traffic from qBittorrent routes through the VPN tunnel.

```mermaid
flowchart TD
    subgraph vpnPod["Pod: gluetun-qbit"]
        gluetun["Gluetun Container\n(PIA VPN)"]
        qbit["qBittorrent Container"]
        gluetun ---|"shared network\nnamespace"| qbit
    end

    subgraph network["Network Flow"]
        internet["Internet"]
        vpnTunnel["VPN Tunnel\n(PIA)"]
        localNet["Local Network\n192.168.10.0/24"]
    end

    gluetun -->|"all egress via\nVPN tunnel"| vpnTunnel
    vpnTunnel --> internet
    localNet -->|"port 8080 (qBit)"| gluetun
    internet -->|"dynamic port\n(PIA port forwarding)"| gluetun
```

### Gluetun Configuration

| Setting | Value |
|---------|-------|
| VPN Provider | Private Internet Access (PIA) |
| Server Region | CA Montreal |
| Capability | `NET_ADMIN` (required for VPN tunnel creation) |
| Firewall - qBittorrent | Port 8080 |
| Port Forwarding | `VPN_PORT_FORWARDING=on` (PIA assigns port dynamically) |
| Credentials | ExternalSecret (`vpn-credentials`, synced from Vault) |

Gluetun creates the VPN tunnel interface and configures iptables firewall rules. The `NET_ADMIN` capability is required for tunnel and firewall management. Because the containers share a network namespace, qBittorrent automatically uses the VPN tunnel for all outbound connections.

!!! warning "Kill Switch"
    If the VPN tunnel drops, Gluetun's built-in firewall rules prevent any traffic from leaving the pod outside the tunnel. This acts as a kill switch ensuring download traffic is never exposed on the local network.
