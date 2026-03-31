# Phase 3 -- Network

**Status:** Not started

**Goal:** Unlock the hardware capabilities already in the rack, improve network segmentation, and enable remote access.

**Addresses:** [P3](assessment.md#physical-layer) (GbE bottleneck), [N3, N4, N5](assessment.md#network-layer)

---

## 3.1 Enable 10G Networking

- [ ] Choose a 10G switch option (see below)
- [ ] Connect the MS-01's SFP+ ports to the new switch via DAC cables
- [ ] Verify link negotiation at 10 Gbps
- [ ] Reconfigure Proxmox networking for the new interface
- [ ] Benchmark NFS throughput before and after

| | |
|---|---|
| **Why** | The MS-01 has 2x 10G SFP+ ports unused. Everything runs over a single 1 GbE connection. NFS throughput, backup speed, and future live migration are all bottlenecked. |

**Options:**

| Option | Device | Cost | Pros | Cons |
|--------|--------|------|------|------|
| A | MikroTik CRS305-1G-4S+ | ~$150 | 4x SFP+, cheapest 10G option, small form factor | Non-UniFi, separate management interface |
| B | USW-Aggregation | ~$300 | 8x SFP+, UniFi-native, single management pane | More expensive, overkill for current needs |
| C | DAC cable direct to NAS | ~$20 | Cheapest, zero config | Only benefits NFS traffic, no switch for future hosts |

**Recommendation:** Option A. Connect both MS-01 SFP+ ports. When a second host is added (Phase 4.1), it connects at 10G immediately.

## 3.2 Configure WireGuard VPN

- [ ] Create WireGuard client profiles on the Dream Router 7 (phone, laptop)
- [ ] Configure split-tunnel routing (only homelab traffic through VPN)
- [ ] Grant VPN access to the Homelab VLAN (192.168.10.0/24)
- [ ] Grant VPN access to the Management VLAN (192.168.99.0/24)
- [ ] Test access to homelab services from an external network

| | |
|---|---|
| **Why** | No way to reach the homelab off-site. Blocks remote management, media streaming, and dashboard access. The Dream Router 7 already has WireGuard enabled. |

## 3.3 Automate Internal DNS

- [ ] Choose a DNS approach (see below)
- [ ] Deploy and configure
- [ ] Migrate existing `*.homelab.local` entries
- [ ] Update [network infrastructure docs](../architecture/network-infrastructure.md)
- [ ] Write an ADR

| | |
|---|---|
| **Why** | DNS is manual static entries in the UniFi console. Every new service requires a manual edit. |

**Options:**

| Option | Approach | Automation | Bonus |
|--------|----------|------------|-------|
| A | external-dns + CoreDNS/Pi-hole (RFC2136) | Full -- watches HTTPRoutes, auto-creates records | DNS automation end-to-end |
| B | Pi-hole or AdGuard Home on K8s | Manual entries, but centralized | Ad-blocking, DNS query dashboard |
| C | Stay with UniFi static entries | None | No new components |

**Recommendation:** Option B as a middle ground. Provides a DNS dashboard and ad-blocking. Layer external-dns on top later if full automation is needed.

## 3.4 Plan External Access for Jellyfin

- [ ] Choose an external access approach (see below)
- [ ] Implement and test
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Streaming media while traveling. VPN (3.2) works for personal devices. Sharing with friends/family needs something that doesn't require VPN setup on their end. |

**Options:**

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A | VPN-only | Simplest, most secure, no public exposure | Requires VPN client on every device |
| B | Cloudflare Tunnel | Zero-trust, no port forwarding, free tier, WAF/DDoS protection | Requires a domain (~$10/year) |
| C | Tailscale Funnel | Simple setup, no port forwarding | Tailscale manages TLS and routing |

**Recommendation:** Start with VPN-only (A) for personal use. Add Cloudflare Tunnel (B) for Jellyfin when sharing with others becomes a priority.

---

## Definition of Done

- [ ] 10G link between MS-01 and at least one other device
- [ ] WireGuard VPN functional for remote access
- [ ] DNS centralized (automated or in a dedicated server)
- [ ] External access path chosen and implemented for Jellyfin
