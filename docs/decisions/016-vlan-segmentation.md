# ADR-016: VLAN Segmentation for Management Isolation

## Status

Accepted

## Context

The site has two VLANs: Default (VLAN 1, 192.168.1.0/24) for household devices and the NAS, and Homelab (VLAN 10, 192.168.10.0/24) for Proxmox and Kubernetes. Infrastructure management interfaces -- the Proxmox web UI, switch management, PDU management, and NAS management -- share these VLANs with production and household traffic. A misconfigured firewall rule or compromised device on either VLAN could reach management interfaces that control power, networking, storage, and the hypervisor.

## Decision

Add a Management VLAN (VLAN 99, 192.168.99.0/24) dedicated to infrastructure management interfaces. Firewall rules restrict access to the Management VLAN to the workstation and WireGuard VPN clients only. Production data paths are unchanged -- Kubernetes traffic stays on the Homelab VLAN and NFS stays on the Default VLAN.

### VLAN Layout

| VLAN ID | Name | Subnet | Purpose |
|---------|------|--------|---------|
| 1 | Default | 192.168.1.0/24 | Household devices, NAS data plane, Wi-Fi clients |
| 10 | Homelab | 192.168.10.0/24 | Proxmox host, Kubernetes VMs, cluster services |
| 99 | Management | 192.168.99.0/24 | Infrastructure management interfaces |

VLAN IDs follow a convention where the ID matches the third octet of the subnet (VLAN 10 = 192.168.10.0/24, VLAN 99 = 192.168.99.0/24). VLAN 1 is the exception as the default/native VLAN.

### Management IP Assignments

| Device | Management IP | Data IP | Notes |
|--------|--------------|---------|-------|
| Dream Router 7 | 192.168.99.1 | 192.168.1.1 | Gateway for Management VLAN |
| Proxmox (MS-01) | 192.168.99.2 | 192.168.10.2 | Dual-homed: mgmt + homelab |
| USW-16-PoE | DHCP | -- | Management only |
| USP PDU Pro | DHCP | -- | Management only |
| Intel AMT (MS-01) | 192.168.99.5 | -- | Out-of-band management, dedicated NIC (ADR-017) |
| UNAS Pro | N/A (stays on Default) | 192.168.1.158 | Cannot dual-home; management stays on Default VLAN |

### Switch Port Configuration

Devices that need both data and management access use trunk ports:

- **MS-01 (nic0)**: Native VLAN = Homelab (10), tagged VLAN = Management (99). Proxmox has a VLAN 99 subinterface for management. STP disabled on this port to prevent flapping from the Linux bridge.
- **MS-01 (nic1)**: Access port on Management (99). Dedicated to Intel AMT out-of-band management (ADR-017).
- **UNAS Pro**: Default VLAN access port only. The UNAS Pro does not support dual-homing -- setting a management VLAN override moves its only interface off the Default VLAN, breaking NFS. Management stays on the Default VLAN.
- **USW-16-PoE and USP PDU Pro**: Management VLAN assigned through the UniFi controller.

### Firewall Rules

Management VLAN rules are evaluated before inter-VLAN rules:

1. Workstation -> Management: Allow
2. WireGuard VPN -> Management: Allow
3. Any -> Management: Deny
4. Management -> Any: Allow (updates, NTP)

## Alternatives Considered

- **Keep management on existing VLANs with firewall rules only**: Simpler to implement -- just add firewall rules to restrict management ports (8006, 443 for switch/PDU/NAS). However, this relies on port-based filtering which is fragile. A VLAN boundary is a stronger isolation primitive that does not depend on knowing every management port.
- **Separate physical management network**: Dedicated NICs and a dedicated switch for management traffic. Strongest isolation but requires additional hardware and cabling. Overkill for a homelab with four managed devices.
- **Management on the Homelab VLAN (move switch/PDU/NAS there)**: Consolidates infrastructure on one VLAN. However, this exposes management interfaces to all Kubernetes pods via the node network, and to any future Homelab VLAN device. A dedicated VLAN with restrictive firewall rules is more defensible.

## Rationale

- **VLAN isolation over port-based filtering**: A VLAN boundary means management traffic is invisible to devices on other VLANs at Layer 2. Firewall rules provide additional protection, but the VLAN alone prevents accidental exposure if a rule is misconfigured.
- **Dual-homing Proxmox rather than moving it**: Proxmox must remain on the Homelab VLAN (192.168.10.2) because Terraform, Ansible, and kubeconfig all reference that IP. Adding a management interface on VLAN 99 provides an independent path to the hypervisor without changing any automation.
- **NAS data path stays on Default VLAN**: The NAS IP (192.168.1.158) is referenced in NFS mounts, Kubernetes PVs, and CiliumNetworkPolicy egress rules across the cluster. Moving NFS to a different VLAN would require changes to dozens of files and would break Kubernetes storage during the transition. Only the management interface moves.
- **DHCP for most management devices**: The gateway and Proxmox host use static IPs (configured on the devices themselves). Other management devices (switch, PDU, AMT) use DHCP for simplicity. DHCP reservations can be added later if stable addressing becomes important.
- **VLAN 99 as the ID**: A high, distinctive number that is unlikely to collide with future VLANs (IoT, guest, etc.) and is immediately recognizable as management in firewall logs and switch configs.

## Consequences

- Proxmox is now dual-homed. If the VLAN 99 subinterface is misconfigured, it could affect the primary Homelab interface. Changes to `/etc/network/interfaces` should be tested carefully with console access available.
- Four additional firewall rules increase the rule set. Rules must be ordered correctly -- management deny rules must precede the existing Default-to-Homelab allow rule to prevent Default VLAN devices from reaching management IPs.
- Switch ports for the MS-01 and NAS become trunk ports carrying two VLANs. Port profile changes must update both the native and tagged VLAN assignments atomically to avoid connectivity loss.
- The UNAS Pro does not support dual-homing. Setting a management VLAN override moves its only network interface, breaking NFS access for the entire cluster. The NAS management interface remains on the Default VLAN.
