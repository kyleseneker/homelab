# Phase 3 -- Network

**Status:** In progress. WireGuard, Teleport, and management-VLAN access are implemented; 10G networking and DNS automation remain planned.

**Goal:** Unlock the hardware capabilities already in the rack, improve network segmentation, and enable remote access.

**Addresses:** P3, P6, N1–N8, and M2 in the [assessment](assessment.md).

---

## 3.1 Enable 10G Networking

- [ ] Choose a 10G switch option (see below)
- [ ] Connect the MS-01's SFP+ ports to the new switch via compatible DAC cables
- [ ] Connect the NAS at 10G after verifying its exact model and interface
- [ ] Verify link negotiation at 10 Gbps
- [ ] Reconfigure Proxmox networking for the new interface, preserving VLANs and management access
- [ ] Benchmark NFS throughput and backup transfers before and after
- [ ] Update the [network infrastructure docs](../architecture/network-infrastructure.md) and [hardware inventory](../reference/hardware.md)

| | |
|---|---|
| **Why** | The MS-01 has two unused 10G SFP+ ports. Its current GbE path limits NFS transfers, backups, and traffic to a future second host. |

**Options:**

| Option | Device | Pros | Cons |
|--------|--------|------|------|
| A | [MikroTik CRS305-1G-4S+IN](https://mikrotik.com/product/crs305_1g_4s_in) | Four SFP+ ports, compact, fanless | Separate management interface; limited ports for expansion |
| B | [USW-Aggregation](https://techspecs.ui.com/unifi/switching/usw-aggregation) | Eight SFP+ ports, UniFi-native, room for additional hosts | Larger initial investment and 1U rack space |
| C | DAC cable direct to NAS | No additional switch; dedicated storage link | Requires compatible NAS interface and explicit addressing/routing; no switch for future hosts |

**Planned starting point:** Option A. Budget ports for the NAS and the second host in Phase 4.1 before deciding whether to connect both MS-01 ports. Option B provides more room for dual links and a third host.

## 3.2 Configure WireGuard VPN

- [ ] Record client profiles and split-tunnel routes for phone and laptop
- [ ] Record an off-LAN test of DNS, TLS, application login, and management access

The VPN is implemented. The remaining tasks document client configuration and verification of the existing remote-access path.

## 3.3 Automate Internal DNS

- [ ] Choose a DNS approach (see below)
- [ ] Deploy and configure the chosen service with a recovery path available when Kubernetes is down
- [ ] Migrate existing `*.homelab.local` entries and verify client lookups
- [ ] Test record creation, updates, and deletion if using external-dns
- [ ] Update the [network infrastructure docs](../architecture/network-infrastructure.md)

| | |
|---|---|
| **Why** | DNS uses static entries in the UniFi console. Every new service requires a manual edit. |

**Options:**

| Option | Approach | Automation | Bonus |
|--------|----------|------------|-------|
| A | external-dns + an authoritative DNS service with a supported update API | Watches supported Kubernetes resources and manages records | DNS automation end-to-end |
| B | Pi-hole or AdGuard Home | Centralized manual entries unless separately integrated with a supported updater | Ad-blocking and a DNS query dashboard |
| C | Stay with UniFi static entries | Manual | No new components |

Pi-hole or AdGuard Home remains an option for centralized DNS and ad-blocking. Full record automation requires a supported provider/API; it does not follow automatically from deploying either service. Any migration away from `.local` also needs a plan for service URLs, certificates, and clients.

## 3.4 Plan External Access for Jellyfin

- [ ] Choose an external access approach (see below)
- [ ] Implement and test on the intended client devices
- [ ] Test long playback sessions, seeking, subtitles, and authentication
- [ ] Keep administrative UIs private

| | |
|---|---|
| **Why** | VPN supports streaming while traveling on personal devices. Sharing with friends and family may need an access path that does not require a VPN client. |

**Options:**

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A | VPN-only | Existing private access path | Requires a VPN client on every device |
| B | Cloudflare Tunnel | No inbound port forwarding | Requires a public domain and verification that the selected service's current terms support media streaming |
| C | Tailscale Funnel | No inbound port forwarding; managed TLS | Verify current bandwidth limits and client suitability for media streaming |

**Planned starting point:** VPN-only for personal use. Select and test a public access method when enabling sharing with friends and family.

## 3.5 Complete Intel AMT Connectivity

- [ ] Connect the MS-01's `nic1` management interface to the reserved USW-16-PoE port 4 on native Management VLAN 99
- [ ] Verify TLS access to AMT at `192.168.99.5` from a permitted management client
- [ ] Test remote power control and console access with the host OS unavailable
- [ ] Update the hardware and port inventory

AMT is configured in firmware. This completes the physical management connection described in [ADR-017](../decisions/017-intel-amt-oob-management.md).

## 3.6 Verify Management Isolation and Address Planning

- [ ] Record which interfaces expose Proxmox, NAS and AMT management; test access from permitted clients and ordinary workloads
- [ ] Move or filter management endpoints that remain reachable outside their intended boundary, preserving a tested administration path
- [ ] Inventory Cilium pod allocations, the Kubernetes service range and routed/VPN networks; the configured `10.0.0.0/8` pool contains the `10.96.0.0/12` service range
- [ ] Document and rehearse the production address migration, using the lab's verified separate pod/service ranges as a baseline
- [ ] Record Gateway IP and DNS allocations so they can be recovered when Kubernetes is unavailable

---

## Definition of Done

- [ ] 10G link between MS-01 and at least one other device
- [ ] Remote client verification recorded
- [ ] DNS centralized or automated through the chosen approach
- [ ] External access path chosen and implemented for Jellyfin
- [ ] Intel AMT connected and remote management tested
- [ ] Management reachability and pod/service/VPN address boundaries verified
