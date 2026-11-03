# Hypervisor Network Isolation

Turns on the Proxmox enforcement in [ADR-016](../decisions/016-vlan-segmentation.md#hypervisor-enforcement): VLAN filtering on `vmbr0`, access-port VM NICs, and per-NIC anti-spoofing filters. It closes assessment findings N9 (node VMs reach the Management VLAN at Layer 2) and N10 (nodes can send from addresses the firewall trusts).

The controls are gated so that nothing changes until a phase turns it on:

| Control | Where | Gate |
|---|---|---|
| Datacenter firewall switch, host firewall off | `pve_firewall` role | `pve_firewall_enabled` |
| VLAN-aware `vmbr0` trunking VLAN 99 | `pve_network` role | `pve_network_vlan_aware` |
| Anti-spoofing IP filters on node NICs | `proxmox-vm` module | `l2_pool_cidrs` in each cluster's `terraform.tfvars` |
| Access-port NICs on the native VLAN | `proxmox-vm` module | `nic_vlan_id = 1` |
| Cilium VXLAN accepted only from node addresses | `proxmox-vm` module | `firewall_vxlan_peers`, set from the cluster's node addresses; needs the VM firewall |

## Before you start

- **A way back if the host loses its network.** Intel AMT is not connected yet ([Phase 3.5](../roadmap/phase-3-network.md#35-complete-intel-amt-connectivity)), and Phase 4 changes the host's only data path. Either be at the console, or use Phase 4's revert timer and stay where you can reach the MS-01.
- The cluster is healthy. Every node is Ready, Argo applications are Synced and Healthy, and no alerts are firing other than Watchdog.
- Commands that change the host or production nodes run in manual mode.
- Record the baseline:

    ```bash
    ssh root@192.168.10.2 'bridge vlan show; cat /sys/class/net/vmbr0/bridge/vlan_filtering'
    # On a worker: VLAN 99 frames are visible today
    ssh media@192.168.10.52 'sudo timeout 30 tcpdump -i eth0 -nn -e -c 5 vlan 99'
    ```

- Pick an unused Homelab address for spoofing tests and confirm nothing answers for it, for example `192.168.10.199`. It is outside the DHCP block, the node addresses and the L2 pool.

## Emergency rollback

These work from the Proxmox console when the network is unreachable.

| Symptom | Command on the host |
|---|---|
| A node lost its network after a firewall change | `pvesh set /cluster/firewall/options --enable 0` turns off every VM firewall at once |
| One VM NIC is misconfigured | `qm set <vmid> --net0 virtio=<mac>,bridge=vmbr0,firewall=0` |
| The host lost its network after the bridge change | `cp /etc/network/interfaces.<timestamp>~ /etc/network/interfaces && ifreload -a`, using Ansible's backup next to the file |

Afterwards, reset the corresponding gate in Git so the next run does not reapply the change.

## Phase 1: Datacenter switch

This affects no VM, because every VM NIC has its firewall flag off.

1. Set `pve_firewall_enabled: true` in `ansible/inventory/homelabpve01/group_vars/all/vars.yml`, then run:

    ```bash
    make pve-firewall
    ```

    The role disables the host firewall before turning on the datacenter switch. Once the switch is on, the host firewall would otherwise default to enabled with a DROP input policy.

    The switch also sets `bridge-nf-call-iptables`, so bridged VM-to-VM traffic starts passing the host's own nftables rules. The restore lab's forward chain accepts traffic that stays on `vmbr1` before its private-address drop; without that rule, the lab nodes lose each other within a minute.

2. Verify:
    - `pve-firewall status` reports `enabled/running`, and `pvesh get /nodes/homelabpve01/firewall/options` shows `enable: 0`.
    - The Proxmox UI and SSH answer on both `192.168.10.2` and `192.168.99.2`.
    - All nodes are Ready, in production and in the restore lab.

## Phase 2: Rehearse

### ifupdown2 with a VLAN-aware bridge and a VLAN subinterface

This uses a scratch bridge with no ports, so nothing else is affected:

```bash
cat > /etc/network/interfaces.d/zz-vlan-rehearsal <<'EOF'
auto vmbr9
iface vmbr9 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 99

auto vmbr9.99
iface vmbr9.99 inet static
    address 198.18.99.1/24
EOF
ifup vmbr9 vmbr9.99
bridge vlan show dev vmbr9          # expect: 1 PVID Egress Untagged, and 99
ip -br addr show vmbr9.99           # expect: UP with 198.18.99.1/24
ifdown vmbr9.99 vmbr9 && rm /etc/network/interfaces.d/zz-vlan-rehearsal
```

If the bridge itself does not list VLAN 99, a `vmbr0.99` subinterface would lose Management after the change. Stop and fix the template before Phase 4.

### Anti-spoofing on the restore lab

1. Set `l2_pool_cidrs = ["172.26.0.240/28"]` in `terraform/hosts/homelabrestore01/terraform.tfvars`, then plan and apply that workspace. The plan creates an `ipfilter-net0` set and firewall options per VM, and sets `firewall = true` on `net0`. Proxmox re-plugs each tap, which briefly interrupts its traffic.
2. Verify the lab end to end as in the [restore lab runbook](restore-lab.md): nodes Ready, cross-node Pod traffic, DNS, and TCP egress through the host (`curl -4 http://1.1.1.1/`). A cached DNS answer can hide broken egress, so test TCP directly. Lab egress is masqueraded by the host, which only works with the conntrack zone that `restore-lab.nft` sets for firewall bridges.
3. On a lab worker, confirm a spoofed source is dropped:

    ```bash
    sudo ip addr add 172.26.0.99/32 dev eth0
    ping -c2 -W2 -I 172.26.0.99 172.26.0.10    # expect: 100% packet loss
    sudo ip addr del 172.26.0.99/32 dev eth0
    ```

### Access-port NICs on the restore lab

1. Make the lab bridge VLAN-aware at runtime only: `ip link set vmbr1 type bridge vlan_filtering 1`.
2. Set `nic_vlan_id = 1` for the lab, then apply. `bridge vlan show dev tap300i0` (and `tap301i0`, or their `fwpr` peers) must list only VLAN 1 as PVID Egress Untagged.
3. Re-verify the lab with the tagged-frame test below: frames from one lab node must not reach the other node's tap.
4. Revert the lab: set `nic_vlan_id = null` and apply, then `ip link set vmbr1 type bridge vlan_filtering 0`. The lab bridge's persistent configuration is not VLAN-aware, and a tagged NIC on a non-VLAN-aware bridge makes Proxmox create a separate per-VLAN bridge. Keep the lab's anti-spoofing filters, or clear `l2_pool_cidrs` too.

#### Tagged-frame test

Cilium's eBPF program on a node's `eth0` drops tagged frames from an ordinary VLAN interface before they leave the guest, so an `ip link add ... type vlan` test proves nothing. Send raw frames that bypass the qdisc layer, as root on a compromised node could, and capture along the path on the host. The interface names carry the node's VM ID (`202` here):

```bash
# On the host: the node's tap must show the frames; the bridge uplink must not
for i in tap202i0 fwpr202p0 nic0; do (timeout 10 tcpdump -i $i -nn -e "vlan 99" > /tmp/v99-$i.txt) & done

# On the node: three VLAN 99 ARP requests for 192.168.99.1
sudo python3 - <<'EOF'
import socket, struct, time
mac = bytes.fromhex(open("/sys/class/net/eth0/address").read().strip().replace(":", ""))
arp = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 1, mac, socket.inet_aton("192.168.99.249"),
                  b"\x00" * 6, socket.inet_aton("192.168.99.1"))
frame = b"\xff" * 6 + mac + struct.pack("!HHH", 0x8100, 99, 0x0806) + arp
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
s.setsockopt(263, 20, 1)  # SOL_PACKET, PACKET_QDISC_BYPASS
s.bind(("eth0", 0))
for _ in range(3):
    s.send(frame); time.sleep(0.5)
EOF
```

The tap and its `fwpr` peer each show three frames, and `nic0` shows none from the node's MAC: the bridge drops them at the port's VLAN filter.

## Phase 3: Production anti-spoofing

1. Set `l2_pool_cidrs` in `terraform/hosts/homelabk8s01/terraform.tfvars` to the Cilium L2 pool, 192.168.10.200 -- .250:

    ```hcl
    l2_pool_cidrs = [
      "192.168.10.200/29",
      "192.168.10.208/28",
      "192.168.10.224/28",
      "192.168.10.240/29",
      "192.168.10.248/31",
      "192.168.10.250/32",
    ]
    ```

2. Apply one node at a time, workers first, and verify between nodes:

    ```bash
    terraform -chdir=terraform/hosts/homelabk8s01 apply \
      -target='module.vm["homelabk8s01-node-2"]'
    ```

    After each node, check:
    - the node is Ready
    - `https://home.seneker.io` and `https://jellyfin.home.seneker.io` load, which exercises the L2 VIPs the node may answer for
    - NFS mounts respond
    - no Blackbox probe fails
    - NUT metrics are still current, since the exporter reaches `upsd` on the host itself

3. On a worker, run the spoofing test with the address chosen earlier:

    ```bash
    sudo ip addr add 192.168.10.199/32 dev eth0
    ping -c2 -W2 -I 192.168.10.199 192.168.10.1    # expect: 100% packet loss
    sudo ip addr del 192.168.10.199/32 dev eth0
    ```

4. Run a full `terraform plan` and confirm it shows no changes.

### VXLAN filter

The hosts pass their node addresses as `firewall_vxlan_peers`, so the same applies add a `vxlan-peers` set and two rules to each node: accept UDP 8472 from the set, drop it from anywhere else. Rehearse on the lab, then apply production one node at a time. On each node, send a junk packet to its VXLAN port from a non-node host (the Proxmox host for the lab, the workstation for production) while capturing on the node:

```bash
ssh media@192.168.10.52 'sudo timeout 10 tcpdump -i eth0 -nn -q "udp port 8472"' &
echo vxlan-filter-test | nc -u -w1 192.168.10.52 8472
```

Before the apply the packet arrives; afterwards it does not, while VXLAN from the other nodes still does. `cilium-health status --probe` on every agent must report all nodes and endpoints reachable.

## Phase 4: Production VLAN filtering

1. Set `pve_network_vlan_aware: true` in the host's inventory variables and commit it **before** any NIC is tagged, so a host reboot keeps the bridge VLAN-aware.
2. Without someone at the console, arm a revert timer on the host first. It runs on the host itself, so it fires even if the network, and your SSH session, are gone:

    ```bash
    cp /etc/network/interfaces /root/interfaces.pre-vlan
    systemd-run --unit=pve-net-revert --on-active=300 --timer-property=AccuracySec=1s /bin/sh -c \
      "cp /root/interfaces.pre-vlan /etc/network/interfaces; ip link set vmbr0 type bridge vlan_filtering 0; ifreload -a"
    ```

3. Run:

    ```bash
    make pve-network
    ```

    The handler reloads networking. Taps that are already plugged keep only VLAN 1, so the nodes stay on the native VLAN.

4. Verify on the host:
    - `cat /sys/class/net/vmbr0/bridge/vlan_filtering` is `1`.
    - `bridge vlan show`: `nic0` and `vmbr0` list VLAN 1 (PVID, untagged) and VLAN 99. Each tap lists only VLAN 1.
    - `ping 192.168.99.1` works from the host, and the workstation still reaches the switch, PDU and Proxmox on `192.168.99.2`.
    - All nodes are Ready and services respond.

    If any check fails, let the timer revert the host rather than repairing it in place. Once all pass, disarm it with `systemctl stop pve-net-revert.timer` and delete `/root/interfaces.pre-vlan`.

## Phase 5: Access-port NICs

1. Set `nic_vlan_id = 1` for production, and apply one node at a time as in Phase 3. Proxmox re-plugs each tap with VLAN 1 only. Without a tag, a VM started on a VLAN-aware bridge receives VLANs 2 -- 4094.
2. Verify:
    - Each tap lists only VLAN 1.
    - A passive capture for VLAN 99 on a node's `eth0` shows nothing:

        ```bash
        ssh media@192.168.10.52 'sudo timeout 60 tcpdump -i eth0 -nn -e -c 5 vlan 99'   # expect: 0 packets
        ```

    - The [tagged-frame test](#tagged-frame-test) from a production node shows the frames on its tap and `fwpr` peer, and none on `nic0`.

## Record the result

- Remove the completed tasks from [Phase 3.6](../roadmap/phase-3-network.md#36-verify-management-isolation-and-address-planning), and remove findings N9 and N10 from the [assessment](../roadmap/assessment.md).
- Update the [network infrastructure](../architecture/network-infrastructure.md) page: the bridge is VLAN-aware, and rule 3's boundary now holds at Layer 2.
- VLAN 20 for [ADR-028](../decisions/028-multus-iot-attachments.md) is in `pve_network_trunk_vlans`, and each worker's `net1` is an access port on it. A further VLAN follows the same path: tag it on switch port 2, append it to `pve_network_trunk_vlans` with the revert timer armed, then give only the VMs that need it an access-port NIC.
