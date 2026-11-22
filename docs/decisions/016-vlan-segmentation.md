# ADR-016: VLAN Segmentation for Management Isolation

## Status

Accepted. The IoT VLAN (20) is recorded separately in [ADR-026](026-iot-vlan.md).

## Context

The site has two VLANs: Default (VLAN 1, 192.168.1.0/24) for household devices, and Homelab (VLAN 10, 192.168.10.0/24) for Proxmox, Kubernetes and the NAS. Infrastructure management interfaces -- the Proxmox web UI, switch management, PDU management, and NAS management -- share these VLANs with production and household traffic. A misconfigured firewall rule or compromised device on either VLAN could reach management interfaces that control power, networking, storage, and the hypervisor.

The Kubernetes nodes are virtual machines on the same Proxmox bridge as the host's management interface, and the MS-01's switch port is a trunk. Two properties of that setup decide whether VLAN boundaries hold for the guests:

- **VLAN filtering**: A Linux bridge without VLAN filtering forwards 802.1Q frames by MAC with their tags unchanged ([kernel bridge docs](https://github.com/torvalds/linux/blob/v6.8/Documentation/networking/bridge.rst)). Tagged frames for the host's management subinterface would reach every VM, and a VM's own tagged frames would leave on the trunk. Making the bridge VLAN-aware is not enough by itself: Proxmox gives a VM NIC with no tag and no trunks VLANs 2 -- 4094 in addition to the untagged native VLAN ([`PVE::Network`](https://git.proxmox.com/?p=pve-common.git;a=blob;f=src/PVE/Network.pm;hb=HEAD)).
- **Source filtering**: Without MAC or IP filtering on its NIC, a VM can send from any address, including one a firewall rule trusts.

Without both, root on any node, or a pod with host networking and `NET_RAW` or `NET_ADMIN`, could join the Management VLAN directly or impersonate a trusted client, with the zone firewall never applying.

## Decision

Add a Management VLAN (VLAN 99, 192.168.99.0/24) dedicated to infrastructure management interfaces. Firewall rules restrict access to the Management VLAN to the workstation and WireGuard VPN clients only. Production data paths are unchanged -- Kubernetes traffic stays on the Homelab VLAN and NFS stays on the Default VLAN.

### VLAN Layout

| VLAN ID | Name | Subnet | Purpose |
|---------|------|--------|---------|
| 1 | Default | 192.168.1.0/24 | Household devices, Wi-Fi clients |
| 10 | Homelab | 192.168.10.0/24 | Proxmox host, Kubernetes VMs, NAS, cluster services |
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
| UNAS Pro | N/A (shares its data address) | 192.168.10.10 | Cannot dual-home; Homelab VLAN with the nodes |

### Switch Port Configuration

Devices that need both data and management access use trunk ports:

- **MS-01 (nic0)**: Native VLAN = Homelab (10), tagged VLAN = Management (99). Proxmox has a VLAN 99 subinterface for management. STP disabled on this port to prevent flapping from the Linux bridge.
- **MS-01 (nic1)**: Access port on Management (99). Dedicated to Intel AMT out-of-band management (ADR-017).
- **UNAS Pro**: Homelab VLAN access port. Only the homelab uses the NAS, so it sits with the nodes that mount it. The UNAS Pro does not support dual-homing -- a management VLAN override would move its only interface and break NFS -- so its web UI shares the data address.
- **USW-16-PoE and USP PDU Pro**: Management VLAN assigned through the UniFi controller.

### Firewall Rules

The UniFi zone-based firewall denies inter-zone traffic by default, so Management isolation is achieved by the absence of a rule rather than an explicit deny. Only these sources are permitted in:

1. Workstation -> Management: Allow, scoped to the Homelab DHCP block `192.168.10.160/27`
2. WireGuard VPN -> Management: Allow, from the `Vpn` zone
3. Management -> Any: Allow, via zone defaults (updates, NTP)

Rule 1 matches an address range rather than a host. The workstation uses a rotating private Wi-Fi address enforced by device management, so any rule pinned to a MAC or a single IP stops matching when the address rotates -- failing closed and silently. The `/27` covers every address DHCP can issue on the Homelab VLAN while excluding the statically addressed Proxmox host and Kubernetes nodes. The hypervisor and pod traffic masquerading behind a node IP stay outside the grant, because the hypervisor stops VMs from sending from any other address (below).

The Default VLAN is not permitted into Management. It carries household devices, which would otherwise gain an unrestricted path to the hypervisor, the switch, the PDU, and Intel AMT.

Household clients reach the Homelab VLAN only at the gateway VIP, on 80 and 443. They have no path to the Proxmox host, node ports or Cilium's overlay, and administration happens from the Homelab Wi-Fi or the VPN. The limit is built from block rules with negated matches ahead of the zone pair's allow rule, because an allow rule restricted by address and port did not match traffic there.

The UniFi console on the Dream Router 7 is also a management interface. It is managed day to day from household phones and laptops, so household clients, the workstation block and VPN clients reach its web console, and its own login protects it. SSH to the gateway is limited to the workstation block and VPN clients. The rest of the Homelab zone (the Proxmox host, the nodes, and pod traffic behind them) and the IoT zone reach the gateway only for DHCP, DNS, NTP, mDNS and ICMP.

### Proxmox Host Firewall

The nodes, their pods and the Proxmox host share the Homelab VLAN, so traffic between them never reaches the zone firewall. The host firewall (`pve_firewall` role) controls access to the host itself:

- **Administration**: SSH (22), the web UI and API (8006) and the SPICE proxy (3128) accept connections only from Proxmox's `management` IP set: the workstation block `192.168.10.160/27`, WireGuard clients `192.168.3.0/24` and the Management VLAN.
- **`local_network`**: Proxmox adds this alias to the `management` set, and auto-detects it as the host's whole subnet, which would admit every node and pod. It is set to the Management VLAN instead.
- **Cluster access**: the node addresses reach only NUT (3493) and node-exporter (9100), which the cluster's monitoring uses. Pod traffic to the host arrives from the node addresses.
- **Everything else**, including rpcbind (111), is dropped. ICMP is accepted.

Pods face a second boundary in the cluster itself: a cluster-wide Cilium policy denies every pod the host's administration ports, the NAS's administration ports and the whole Management VLAN ([Network Policies](../infrastructure/network-policies.md#infrastructure-administration)).

### Hypervisor Enforcement

The Proxmox host keeps each VM on its own VLAN and addresses, so compromising a guest does not grant Layer 2 access to another VLAN or another host's identity.

- **VLAN filtering**: Make `vmbr0` VLAN-aware in the `pve_network` role, with the uplink carrying only the tagged VLANs in use. The host keeps `vmbr0.99` and gets no other VLAN interface.
- **Access-port NICs**: Give every VM NIC exactly one VLAN through an explicit `tag`/`trunks` setting in the `proxmox-vm` module. NICs on the Homelab VLAN carry only the untagged native VLAN. A NIC on another VLAN is tagged with that VLAN alone. No VM NIC is a trunk.
- **Source filtering**: Enable the Proxmox VE firewall at the datacenter level and turn on the VM firewall for node NICs with input and output policies of ACCEPT, so it drops spoofed sources without filtering ports. Each Homelab NIC's `ipfilter-net<id>` set allows only the node's own address and the Cilium L2 pool (192.168.10.200 -- .250); Proxmox implicitly allows the NIC's MAC-derived IPv6 link-local address ([Proxmox firewall](https://pve.proxmox.com/pve-docs/pve-firewall.8.html)). MAC filtering is a per-VM option, so it is on for VMs whose NICs carry only their own MAC and off for workers with a macvlan parent NIC ([ADR-028](028-multus-iot-attachments.md)), where the per-NIC IP filters prevent spoofing. Terraform manages the firewall options, IP sets and rules alongside the VM definitions.
- **Overlay filtering**: Each node NIC accepts Cilium's VXLAN traffic (UDP 8472) only from the cluster's node addresses, through a `vxlan-peers` set. The overlay is unauthenticated, so a packet that reaches the port is delivered into the pod network past network policy. The filter stops other Homelab and VPN hosts from sending it. A client on the Homelab VLAN can still forge a node's address, because the Wi-Fi network does not filter sources; encrypting the overlay would close that.
- **Verification**: `bridge vlan show` lists one VLAN per tap, a passive capture for VLAN 99 on a node's `eth0` shows nothing, raw VLAN 99 frames a node sends never leave on the uplink, and in the restore lab a node sending from an unassigned address is dropped. Cilium's eBPF program on a node's `eth0` drops tagged frames from ordinary VLAN interfaces, so the tagged-frame test sends raw frames that bypass it, as root on a compromised node could.
- **Ordering**: No additional VLAN is trunked to the host before this is in place.

## Alternatives Considered

- **Keep management on existing VLANs with firewall rules only**: Simpler to implement -- just add firewall rules to restrict management ports (8006, 443 for switch/PDU/NAS). However, this relies on port-based filtering which is fragile. A VLAN boundary is a stronger isolation primitive that does not depend on knowing every management port.
- **Separate physical management network**: Dedicated NICs and a dedicated switch for management traffic. Strongest isolation but requires additional hardware and cabling. Overkill for a homelab with four managed devices.
- **Management on the Homelab VLAN (move switch/PDU/NAS there)**: Consolidates infrastructure on one VLAN. However, this exposes management interfaces to all Kubernetes pods via the node network, and to any future Homelab VLAN device. A dedicated VLAN with restrictive firewall rules is more defensible.
- **Proxmox management on its own cable instead of the trunk**: Physical separation for the host's management address. `nic1` is reserved for Intel AMT ([ADR-017](017-intel-amt-oob-management.md)), and the SFP+ ports have no 10G switch yet ([Phase 3.1](../roadmap/phase-3-network.md#31-enable-10g-networking)). It also leaves source spoofing on the Homelab VLAN unaddressed. Revisit with the 10G switch.
- **ebtables rules on the taps instead of the Proxmox firewall**: Blocks tagged frames, but Proxmox does not manage them, and taps are recreated whenever a VM restarts.
- **Tag the Homelab VLAN on the trunk too**: Every NIC would carry an explicit tag, but the host's primary address would move onto a VLAN subinterface. That is a larger change to the only data path, and it adds no isolation once taps are access ports.
- **Kubernetes admission alone**: Restricting host networking and privileged pods ([Phase 2.2](../roadmap/phase-2-kubernetes-hardening.md#22-make-least-privilege-real)) reduces who can reach a node's network stack, but does nothing against node root or a container escape. Both controls are worth having.

## Rationale

- **VLAN isolation over port-based filtering**: A VLAN boundary means management traffic is invisible to devices on other VLANs at Layer 2. That holds for virtual machines only when the hypervisor enforces VLAN membership: a non-filtering bridge on a trunk port makes every guest a member of every trunked VLAN. Firewall rules provide additional protection, but the VLAN alone prevents accidental exposure if a rule is misconfigured.
- **Dual-homing Proxmox rather than moving it**: Proxmox must remain on the Homelab VLAN (192.168.10.2) because Terraform, Ansible, and kubeconfig all reference that IP. Adding a management interface on VLAN 99 provides an independent path to the hypervisor without changing any automation.
- **NAS on the Default VLAN**: Household devices could reach it directly, but nothing outside the homelab uses it. NFS would cross the gateway, so gateway restarts would interrupt storage, and the firewall would need a Homelab-to-NAS allow rule plus a return path for NFSv3 lock callbacks, opening the NAS web UI to every node and pod.
- **DHCP for most management devices**: The gateway and Proxmox host use static IPs (configured on the devices themselves). Other management devices (switch, PDU) use DHCP for simplicity; AMT has a static address so emergency access does not depend on DHCP (ADR-017). DHCP reservations can be added later if stable addressing becomes important.
- **VLAN 99 as the ID**: A high, distinctive number that is unlikely to collide with future VLANs (IoT, guest, etc.) and is immediately recognizable as management in firewall logs and switch configs.

## Consequences

- Proxmox is now dual-homed. If the VLAN 99 subinterface is misconfigured, it could affect the primary Homelab interface. Changes to `/etc/network/interfaces` should be tested carefully with console access available.
- The household-to-Homelab block rules work only ahead of that zone pair's allow rule. UniFi appends new policies to the end of a zone pair, so the order is set explicitly, through the UniFi Integration API or the UI, and any new rule there needs the same care.
- The MS-01's switch port becomes a trunk carrying several VLANs. Port profile changes must update both the native and tagged VLAN assignments atomically to avoid connectivity loss.
- The NAS web UI shares the Homelab VLAN with the nodes, which reach it at Layer 2; the UNAS Pro has no host firewall. The cluster-wide Cilium policy keeps pods off it.
- Hypervisor enforcement and host firewall changes affect the host's only data path. Make them with the AMT console ([ADR-017](017-intel-amt-oob-management.md)) or a revert timer on the host that restores the previous configuration unless it is cancelled, after rehearsing VLAN filtering and the VM firewall on the restore lab's VMs. Those VMs share the host, so the datacenter-level firewall switch affects production even during rehearsal.
- A VM firewall left at Proxmox's default input policy of DROP would cut the node off. The ACCEPT policies are part of the change, not an afterthought.
- With the datacenter firewall on, Proxmox sets `bridge-nf-call-iptables`, so traffic between VMs on the same bridge also passes the host's netfilter hooks and connection tracking. Host nftables rules written for routed traffic must accept traffic that stays within its bridge, as the restore lab's rules do. A VM whose traffic the host masquerades also needs its firewall-bridge leg in a separate conntrack zone, or the NAT decision is made before routing and egress leaves unmasqueraded ([Proxmox network configuration](https://pve.proxmox.com/wiki/Network_Configuration)); the restore lab's rules set that zone.
- The Proxmox firewall becomes part of the network model. A missing address drops a node's traffic, so changing the Cilium L2 pool or a node address means updating the IP filter in the same change. New VM NICs must declare their VLAN.
- Anything new the cluster needs from the host needs a host firewall rule, and the `management` set changes with the workstation block or the VPN subnet. A host firewall enabled without that set and the `local_network` override admits the whole Homelab VLAN, so the role refuses to enable it.
- Every household client reaches the UniFi web console, so the Default VLAN should hold only trusted personal devices. Smart home devices belong on the IoT VLAN ([ADR-026](026-iot-vlan.md)), and the console login should use multi-factor authentication where the account supports it.
