# Network Infrastructure

Physical and logical network architecture below Kubernetes: VLANs, firewall rules, DNS, and remote access. For Kubernetes-level networking (Cilium Gateway API, TLS, network policies, VPN sidecar), see [Networking](networking.md).

## Physical Topology

```mermaid
flowchart TD
    internet["Internet"] <-->|"WAN"| DR7

    subgraph main_floor ["Main Floor"]
        DR7["Dream Router 7<br/>Router / Firewall<br/>UniFi Controller"]
    end

    subgraph closet ["Network Closet"]
        SW["USW-16-PoE<br/>16x GbE PoE + 2x 1G SFP"]
        PDU["USP PDU Pro"]
        NAS["UNAS Pro<br/>192.168.1.158"]
        MS01["Minisforum MS-01<br/>192.168.10.x"]
    end

    subgraph wifi ["Wi-Fi"]
        U6a["U6 Extender"]
        U6b["U6 Extender"]
    end

    DR7 -->|"GbE"| SW
    SW -->|"GbE (Default VLAN)"| NAS
    SW -->|"GbE (Homelab VLAN)"| MS01
    SW --> PDU
    DR7 -.->|"Wi-Fi backhaul"| U6a
    DR7 -.->|"Wi-Fi backhaul"| U6b
```

All physical links are Gigabit Ethernet. See [Hardware Inventory](../reference/hardware.md) for full device specs.

## VLANs

| VLAN ID | Name | Subnet | Purpose |
|---------|------|--------|---------|
| 1 | Default | 192.168.1.0/24 | Household devices, NAS, UniFi console, Wi-Fi clients |
| 10 | Homelab | 192.168.10.0/24 | Proxmox host, Kubernetes VMs, cluster services |

The NAS sits on the Default VLAN (192.168.1.158) because it serves both household devices and the Kubernetes cluster.

## Firewall Rules

Configured in the UniFi Network controller on the Dream Router 7. Rules are evaluated in order.

| # | Source | Destination | Action | Purpose |
|---|--------|-------------|--------|---------|
| 1 | Default (192.168.1.0/24) | Homelab (192.168.10.0/24) | Allow | Home network access to homelab services |
| 2 | Homelab (192.168.10.0/24) | 192.168.1.158 (NAS) | Allow | Kubernetes NFS access to NAS |
| 3 | Homelab (192.168.10.0/24) | Default (192.168.1.0/24) | Deny | Isolate homelab from household devices |
| 4 | Homelab (192.168.10.0/24) | Internet | Allow | Image pulls, VPN egress, AWS KMS |

Rule 2 is an exception to Rule 3 -- Kubernetes nodes can reach the NAS but not other devices on the Default VLAN.

## DNS

Static entries for each `*.homelab.local` service are configured in the UniFi Network controller's local DNS records, pointing to the Cilium L2 gateway VIP.

See [Networking - Application Hostnames](networking.md#application-hostnames) for the full hostname list.

## Remote Access

| Method | Status |
|--------|--------|
| WireGuard VPN | Server enabled on Dream Router 7 |
| UniFi Teleport | Enabled |

## Kubernetes Network Integration

How the physical network connects to the Kubernetes pod network:

```mermaid
flowchart LR
    client["Client<br/>192.168.1.x"] -->|"HTTPS"| vip["Cilium L2 VIP<br/>192.168.10.200-250"]
    vip --> gateway["Cilium Gateway<br/>(in-cluster)"]
    gateway --> pod["Pod<br/>10.244.0.0/16"]
    pod -->|"NFS"| nas["NAS<br/>192.168.1.158:2049"]
```

| Network | CIDR | Purpose |
|---------|------|---------|
| Default VLAN | 192.168.1.0/24 | Client access, NAS |
| Homelab VLAN | 192.168.10.0/24 | Node IPs, Cilium L2 VIPs |
| Pod network | 10.244.0.0/16 | Kubernetes pod CIDR (Cilium) |
| Service network | 10.96.0.0/12 | Kubernetes service CIDR |
| L2 VIP pool | 192.168.10.200-250 | Cilium LoadBalancer IPs |
