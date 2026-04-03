# ADR-017: Intel AMT for Out-of-Band Management

## Status

Accepted

## Context

The MS-01 runs Proxmox VE and hosts all Kubernetes VMs. If Proxmox hangs or the host becomes unresponsive, the only recovery option is physical access -- walking to the network closet to power cycle the machine or attach a keyboard and monitor. This is inconvenient during normal operation and makes the homelab unmanageable during travel.

The MS-01's Intel Core i9-13900H includes vPro Enterprise with Intel AMT, which provides IPMI-like out-of-band management: remote power control (on, off, reset, graceful shutdown), serial-over-LAN console, and KVM remote desktop -- all independent of the host OS. AMT operates on a dedicated Management Engine (ME) that remains active as long as the system has standby power from the PSU.

The Management VLAN (VLAN 99, 192.168.99.0/24) is already in place with firewall rules restricting access to the workstation and WireGuard VPN clients (ADR-016). This provides the network isolation needed to safely expose AMT.

## Decision

Enable Intel AMT on the MS-01 and place it on the Management VLAN using a dedicated NIC. AMT is configured with a static IP on VLAN 99.

### Physical Connectivity

The MS-01 has two 2.5G RJ45 NICs with different Intel controllers:

| NIC | Controller | MAC | Purpose |
|-----|-----------|-----|---------|
| nic0 | Intel I226-V (57:00.0) | 38:05:25:31:07:20 | Proxmox host bridge (vmbr0) |
| nic1 | Intel I226-LM (58:00.0) | 38:05:25:31:07:21 | Intel AMT (dedicated) |

AMT binds to the I226-LM (nic1), not the I226-V (nic0). The "LM" variant includes the vPro manageability features. AMT's ME has its own network stack that operates independently of the host OS on this NIC.

AMT cannot share a NIC that is a Linux bridge port -- the bridge intercepts DHCP responses before the ME sees them, preventing AMT from obtaining an IP address. A dedicated cable from nic1 to a separate switch port is required.

### AMT Configuration

| Setting | Value |
|---------|-------|
| NIC | nic1 (I226-LM), dedicated cable to switch |
| Network | Static IP 192.168.99.5/24, gateway 192.168.99.1 |
| Transport | TLS only (CSME 16.x enforces this; ports 16993, 16995, 664) |
| Authentication | Digest authentication with a strong, unique password |
| KVM | Enabled (port 16995) |
| Serial-over-LAN | Enabled (port 664) |
| Storage Redirection | Disabled (not needed for normal operations) |
| User Consent | None (operator is always the homelab admin) |

### Switch Port Configuration

Two switch ports are required for the MS-01:

1. **nic0 port** (Proxmox host): Native VLAN = Homelab (10), tagged VLAN = Management (99). Disable STP on this port to prevent STP state flapping caused by the Linux bridge.
2. **nic1 port** (AMT): Access port on Management VLAN (99). No trunking needed -- AMT sends only untagged traffic.

### MEBx Setup Steps

Enter MEBx via DEL at POST, then Setup > MEBx. Log in with the MEBx password.

```
Intel(R) AMT Configuration
├── Manageability Feature Selection        → Enabled
├── SOL/Storage Redirection/KVM
│   ├── SOL                                → Enabled
│   ├── Storage Redirection                → Disabled
│   ├── KVM Feature Selection              → Enabled
├── User Consent
│   ├── User Opt-in                        → None
│   └── Opt-in Configurable from Remote IT → Enable
├── Password Policy                        → Anytime
├── Network Setup
│   ├── ME Network Name Settings
│   │   └── FQDN                           → ms01-amt.homelab.local (Dedicated)
│   └── TCP/IP Settings
│       └── Wired LAN IPV4 Configuration
│           ├── DHCP Mode                  → Disabled
│           ├── IP Address                 → 192.168.99.5
│           ├── Subnet Mask                → 255.255.255.0
│           └── Default Gateway            → 192.168.99.1
└── Activate Network Access                → Y (do this last)
```

Notes:
- **TLS is enforced by hardware.** CSME 16.1+ (Raptor Lake) permanently disables insecure ports 16992, 16994, and 623. There is no MEBx option to toggle this.
- **User Consent "None" may not be available** in Client Control Mode (manual MEBx provisioning). If greyed out, set to "KVM" and change to "None" later via MeshCommander after activating Admin Control Mode.
- **Activate Network Access** transitions AMT from pre-provisioned to operational. Do this after all other settings are configured.

### Verification

1. Cable nic1 to a switch port configured as an access port on VLAN 99
2. From the workstation, browse to `https://192.168.99.5:16993` and accept the self-signed certificate
3. Log in with username `admin` and the MEBx password
4. Test a power action (e.g., graceful restart) to confirm remote control works
5. Install MeshCommander for KVM and Serial-over-LAN access

### Access Methods

- **Web UI**: `https://192.168.99.5:16993` -- browser-based management console for power control and settings
- **MeshCommander**: Open-source desktop client for KVM, Serial-over-LAN, and power control
- **Power actions**: On, off, hard reset, graceful shutdown via web UI or MeshCommander

### Network Security

AMT inherits the Management VLAN firewall rules from ADR-016:

1. Workstation -> Management VLAN: Allow
2. WireGuard VPN -> Management VLAN: Allow
3. Any -> Management VLAN: Deny

No additional firewall rules are needed. AMT is unreachable from the Default VLAN, Homelab VLAN, and the internet.

## Alternatives Considered

- **Proxmox watchdog timer only**: A software watchdog can reboot a hung host automatically, but cannot help with kernel panics, boot failures, BIOS issues, or situations requiring interactive console access. AMT covers all of these.
- **Smart plug for remote power cycle**: The USP PDU Pro already provides remote outlet switching, which can force a power cycle. However, this is a blunt instrument -- it cannot distinguish between a hung OS and a kernel panic, cannot provide console access for debugging, and a cold power cut risks filesystem corruption. AMT provides graceful shutdown and interactive console.
- **Dedicated IPMI/BMC add-in card**: Provides similar functionality but requires the PCIe x16 slot, adds cost, and duplicates capabilities the CPU already has via vPro.
- **Shared NIC with VLAN-aware bridge**: AMT and the host could share nic0 if the Linux bridge were VLAN-aware and the switch port's native VLAN carried AMT's untagged traffic. In practice, the Linux bridge intercepts AMT's DHCP responses, preventing the ME from obtaining an address. A dedicated NIC is the only reliable approach.

## Rationale

- **Static IP over DHCP**: AMT's ME cannot reliably receive DHCP responses when the NIC is shared with a Linux bridge. Even on a dedicated NIC, a static IP avoids dependency on the DHCP server and makes the AMT address predictable for emergency access.
- **Dedicated NIC**: The I226-LM (nic1) is the vPro-capable NIC and must have its own cable and switch port. The I226-V (nic0) does not support AMT.
- **TLS only**: CSME 16.1+ (13th gen Raptor Lake) permanently disables insecure ports. TLS is the only option on this hardware, which is the desired state regardless.
- **No Storage Redirection**: Storage Redirection allows mounting ISO images remotely for OS reinstallation. This is useful for initial setup but not for day-to-day management. It can be enabled temporarily if a Proxmox reinstall is needed.
- **No user consent requirement**: AMT can require a user physically present at the console to approve remote KVM sessions. This defeats the purpose of out-of-band management for a single-admin homelab.
- **Disable STP on the host switch port**: The Linux bridge with `bridge-stp off` causes STP state flapping alerts on the UniFi switch. Disabling STP on the port eliminates the alert. There is no loop risk -- the host is an endpoint, not a switch.

## Consequences

- AMT requires a second Ethernet cable from the MS-01 to the switch, consuming an additional switch port.
- AMT has its own network stack and MAC address on nic1. It appears as a separate device on VLAN 99.
- AMT firmware should be kept up to date. Intel publishes ME/AMT firmware updates that address security vulnerabilities. These updates require a BIOS update or Intel's firmware update tool and a reboot.
- If AMT is misconfigured (wrong IP, wrong credentials), recovery requires physical console access to re-enter BIOS setup. The AMT password cannot be reset remotely without the current password.
- AMT's TLS certificate is self-signed by default. MeshCommander and browsers will show certificate warnings. This is acceptable for a homelab with a single admin.
