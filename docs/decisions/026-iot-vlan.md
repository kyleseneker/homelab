# ADR-026: IoT VLAN for Smart Home Devices

## Status

Accepted

## Context

Smart home devices (thermostats, cameras, appliances, media players and similar) join the household Wi-Fi on the Default VLAN (192.168.1.0/24). That VLAN also carries phones and laptops, and the NAS that serves every NFS-backed volume in the cluster. The NAS's management interface cannot leave it ([ADR-016](016-vlan-segmentation.md)). Most smart devices depend on vendor clouds, run firmware that cannot be inspected, and are patched on the vendor's schedule. A compromised device on Default reaches every household client and the NAS directly, without passing the gateway firewall.

Many of these devices also have 2.4 GHz-only radios. Some fail to join an SSID that advertises WPA3 transition mode or several bands at once, which the household SSID does.

The IoT VLAN was configured on the Dream Router 7 on 2026-08-03. This record documents that design.

## Decision

Add an IoT VLAN (VLAN 20, 192.168.20.0/24) in its own UniFi firewall zone, with a dedicated SSID for smart home devices. The ID follows ADR-016's convention of matching the subnet's third octet.

### Network

| Setting | Value |
|---------|-------|
| VLAN / subnet | 20 / 192.168.20.0/24, gateway 192.168.20.1 |
| DHCP scope | 192.168.20.100 -- 192.168.20.200 |
| IPv6 | None, as on the other VLANs |
| IGMP snooping | Enabled (the other VLANs have it off) |
| Firewall zone | IoT |

The DHCP scope leaves 192.168.20.2 -- .99 and .201 -- .254 free for fixed addresses, such as hubs, radio coordinators or a home automation controller.

### Wireless

A dedicated IoT SSID is broadcast from every access point: 2.4 GHz only, WPA2-PSK without WPA3 transition mode, PMF optional and client isolation off. The household and homelab SSIDs keep 2.4/5/6 GHz with WPA2/WPA3 transition. The IoT SSID uses the settings older radios need, so the household SSID does not have to.

No switch port carries VLAN 20. The MS-01's trunk (port 2) explicitly excludes it, so no homelab host has an interface on the IoT network.

### Firewall

The IoT zone follows the Homelab and Management pattern: zone defaults block traffic to and from the other internal zones and allow External and Gateway. One custom rule opens the household side.

| Source | Destination | Action | Origin |
|--------|-------------|--------|--------|
| Internal | IoT | Allow | Custom rule `Internal to IoT` |
| IoT | Internal | Return traffic only | Zone default |
| IoT | External | Allow; invalid traffic blocked | Zone default |
| IoT | Gateway | Allow, including mDNS on UDP 5353 | Zone default |
| IoT | Homelab, Management, Vpn | Block | Zone default |
| Homelab, Management, Vpn | IoT | Block | Zone default |

Household clients can open device apps, cast to and configure devices. IoT devices reach their clouds but cannot open connections into the household network, the NAS, the cluster or the management interfaces.

### Discovery

The gateway's mDNS proxy runs in automatic mode for all networks with every predefined service enabled, including AirPlay, Chromecast, HomeKit and Matter. Household clients therefore discover services advertised on VLAN 20.

## Alternatives Considered

- **Keep smart devices on Default**: No configuration and no cross-VLAN discovery to manage. It leaves the least trusted devices in the same broadcast domain as household clients and the NAS's data and management interface.
- **Guest network with client isolation**: Isolates devices from the LAN in one setting, but also from each other. Local control between devices, hubs and controllers on the same network depends on that traffic.
- **Per-device rules on Default**: The gateway firewall only sees routed traffic. Devices on the same VLAN still reach household clients and the NAS directly, and every new device needs its own rule. ADR-016 rejected the same fragility for management interfaces.
- **Use the Homelab VLAN**: Internal to Homelab is allowed in full, and that VLAN carries the Proxmox host and cluster nodes. It trades household exposure for hypervisor exposure.
- **Several IoT networks** (for example, separate cloud-only and local-control VLANs): Finer containment, at the cost of more SSIDs, zones and rules for a small device count. Revisit if a device class needs stronger isolation.

## Rationale

- **Zone defaults do the isolation**: The new zone inherits the default-deny matrix the Homelab and Management zones already use. One allow rule is the only addition, so isolation does not depend on getting a list of block rules right.
- **Household use is unchanged**: Allowing Internal to IoT in full keeps phones and tablets controlling and casting to devices as before. The zone default stops IoT-initiated connections in the other direction.
- **A separate SSID, not a weaker household SSID**: IoT compatibility settings stay on the network that needs them.
- **No trunk to the hypervisor**: Leaving VLAN 20 off the MS-01's port keeps the IoT network away from the Proxmox bridge until a workload there needs an interface on it.

## Consequences

- Devices are protected only once moved. Many store a single network and must be re-provisioned through their vendor app or factory reset to join the IoT SSID.
- VPN clients cannot reach VLAN 20. Remote control of devices goes through vendor clouds unless a rule or a controller reachable over the VPN provides it.
- Cross-VLAN discovery depends on the mDNS proxy, which does not cover every protocol. Matter relies on link-local multicast that does not cross VLANs; its controller needs Wi-Fi devices and Thread border routers on its own VLAN, and the Matter server's documentation advises against mDNS forwarders ([Home Assistant Matter integration](https://www.home-assistant.io/integrations/matter/), [matter.js server OS requirements](https://github.com/matter-js/matterjs-server/blob/main/docs/os_requirements.md)). A local controller for such protocols needs its own interface on VLAN 20. No homelab host has one today.
- Matter and Thread use link-local IPv6 and prefixes advertised by Thread border routers on the VLAN itself, so the missing gateway IPv6 does not block them. IPv6 multicast and Router Advertisements must still pass on VLAN 20. The matter.js documentation says IGMP/MLD snooping "may help or hinder" Matter traffic, so check snooping first when multicast discovery fails here.
- The IoT SSID offers no WPA3 protection; its pre-shared key is the only barrier to joining. Keep it distinct from the household SSID's key.
- Devices with 5 GHz radios still connect at 2.4 GHz on this SSID.
- The zone, SSID and rule live in the UniFi controller, outside Git, like the rest of the network configuration ([Phase 7](../roadmap/phase-7-long-term-vision.md) tracks GitOps for network config).
