# ADR-028: Multus for IoT VLAN Attachments

## Status

Accepted

## Context

Home automation workloads ([ADR-029](029-home-assistant.md)) need to sit on the IoT VLAN ([ADR-026](026-iot-vlan.md)). Device discovery (mDNS, SSDP), HomeKit and Matter use link-local multicast. Matter's controller needs Wi-Fi devices and Thread border routers on its own VLAN, and its documentation advises against mDNS forwarders ([Matter integration](https://www.home-assistant.io/integrations/matter/), [matter.js server OS requirements](https://github.com/matter-js/matterjs-server/blob/main/docs/os_requirements.md)). Routing to VLAN 20 through the gateway reaches devices by unicast but not by discovery.

Nothing in the cluster can reach VLAN 20 today. Pods use Cilium's VXLAN overlay, which does not carry LAN multicast into pods. Each node VM has one NIC, `eth0`, on the Homelab VLAN, and the MS-01's switch port excludes VLAN 20.

Cilium does not give a pod more than one interface. A maintainer states that "Cilium doesn't support having multiple interfaces for a single pod" ([cilium/cilium#23483](https://github.com/cilium/cilium/issues/23483)), and its documentation has no Multus guidance. Cilium removes other CNI configuration files by default (`cni.exclusive: true`, [Kubernetes configuration](https://docs.cilium.io/en/stable/network/kubernetes/configuration/)). The workers ship the reference CNI plugins from `kubernetes-cni`, including `macvlan`, `ipvlan`, `vlan`, `host-device`, `static` and `tuning`.

Trunking VLAN 20 to the host relies on [ADR-016's hypervisor enforcement](016-vlan-segmentation.md#hypervisor-enforcement), which keeps each VM on its own VLAN and addresses.

Several defaults matter for the boundary this design creates:

- **Pods inherit IPv4 forwarding.** New network namespaces copy the node's IPv4 `all` and `default` settings, so pods start with `ip_forward=1`; IPv6 is reset to defaults ([`devconf_inherit_init_net`](https://github.com/torvalds/linux/blob/v6.8/Documentation/admin-guide/sysctl/net.rst)). A worker's pods confirmed this. A new interface also takes IPv6 link-local addressing and Router Advertisement processing by default.
- **Cilium only guards its own interface.** It drops endpoint packets with a foreign source IP by default ([`enableSourceIPVerification`](https://github.com/cilium/cilium/blob/main/pkg/defaults/defaults.go)), but only on the interface it manages.
- **Multus can bypass Cilium entirely.** It always honors the `v1.multus-cni.io/default-network` annotation, which replaces a pod's primary network. No option disables it, and namespace isolation does not apply to it ([configuration reference](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/docs/configuration.md), [k8sclient.go](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/pkg/k8sclient/k8sclient.go)). Even with isolation on, definitions in the `default` namespace stay usable from every namespace.
- **The upstream manifest grants wide RBAC.** Its ClusterRole allows `update` on every pod in the cluster.

## Decision

Add [Multus](https://github.com/k8snetworkplumbingwg/multus-cni) as a CNI meta-plugin, so selected pods get a second interface on VLAN 20 while Cilium remains the primary network for every pod. Each layer below fails closed on its own, so a pod or node compromise does not by itself open a path between VLAN 20, the cluster and the other VLANs.

### Hypervisor

- [ADR-016's hypervisor enforcement](016-vlan-segmentation.md#hypervisor-enforcement) comes first: VLAN filtering on `vmbr0`, access-port NICs, and Proxmox source filtering. VLAN 20 is added to switch port 2 only after that.
- Give each worker VM a second NIC (`net1`), an access port tagged VLAN 20, through the `proxmox-vm` module's `iot_nic`. The control plane gets none. Its IP filter, `ipfilter-net1`, starts empty, so the NIC sends nothing until an attachment is recorded.
- MAC filtering is a per-VM Proxmox option and macvlan needs extra MACs, so it is off for the whole worker VM. The NIC's IP filter allows only the recorded attachment addresses, plus the MAC-derived IPv6 link-local address of any attachment that keeps IPv6. An inbound rule set admits only what attached workloads need: mDNS and SSDP, plus each workload's listed ports from 192.168.20.0/24. This filter runs outside the pod and the node, so compromising either does not remove it.

### Nodes

- Bring each worker's VLAN 20 NIC (`ens19`, the kernel's name for `net1`) up as a link only, through the `k8s_iot_nic` role, with:
    - no IPv4 address and `disable_ipv6=1`
    - `accept_ra=0`, `arp_ignore=8`, `rp_filter=1` and `forwarding=0`
- Add an nftables `inet` table that drops prerouting, input and forward traffic arriving on that NIC, so a node never accepts or routes traffic from VLAN 20. Never use a `netdev` ingress hook: it runs before the macvlan handler and would cut off the attached pods ([dev.c](https://github.com/torvalds/linux/blob/v6.8/net/core/dev.c)).
- Load that table from its own systemd unit before networking starts, never through the stock `nftables.service`, whose default configuration flushes Cilium's and Kubernetes' rules.
- Label the workers `home.seneker.io/iot-vlan=true` so attached pods can select them.

### Cilium

- Set `cni.exclusive: false` so Cilium keeps Multus's configuration file. Cilium stays the default network.
- Set Cilium's `devices` to `eth0` and pin the L2 announcement policy to `^eth0$`, so no LoadBalancer IP is ever announced on VLAN 20.

### Multus

- Run the thick plugin from the v4.3.1 release manifest, pulled as a Kustomize remote resource pinned to the release commit, with patches for this cluster's changes. The manifest references the floating `snapshot-thick` image even at release tags, so pin the `v4.3.1-thick` image by digest. Deploy it through the ApplicationSet as a `git` source in `kube-system`.
- Grant the Multus ServiceAccount read access to attachment definitions and pods, and `update` only on `pods/status`, through which it writes the `k8s.v1.cni.cncf.io/network-status` annotation. An admission policy limits those writes to that annotation.
- Make Cilium's configuration file Multus's readiness indicator, so Multus never serves a pod before Cilium is ready on the node.
- Enable `namespaceIsolation`, and set `globalNamespaces` to a namespace that does not exist, which removes the `default` exemption. Verify both with a denied cross-namespace reference.

### Attachment definitions

- Use one macvlan definition per attached workload, in that workload's namespace, in bridge mode on the worker's VLAN 20 NIC.
- Fix each definition's address (from 192.168.20.10 -- .49) and its locally administered MAC in static IPAM in Git. Pods cannot choose an address, because the `ips` and `mac` capabilities are off. Record each allocation in the network docs and in the Proxmox IP filter.
- Put only the connected 192.168.20.0/24 route on the attachment. The default route stays on Cilium's `eth0`, so cluster, gateway and internet traffic keep Cilium policy and Hubble visibility.
- Set these sysctls on the attachment with the `tuning` plugin:
    - `forwarding=0`, since pods inherit IPv4 forwarding
    - `rp_filter=1`, `arp_ignore=1` and `arp_announce=2`
    - `disable_ipv6=1`, unless the workload needs IPv6
- A Matter server keeps IPv6 with `accept_ra=1` and `accept_ra_rt_info_max_plen=64` for Thread routes, plus `accept_ra_defrtr=0` so a rogue Router Advertisement cannot install a default route.

### Admission

These are Kyverno policies with `failurePolicy: Fail`. Unlike the existing policies, they also cover `kube-system`. The pod rules and the status-write rule use only standard CEL, so Kyverno generates them as native `ValidatingAdmissionPolicy` objects, which the API server enforces without a webhook. A fail-closed webhook covering `kube-system` would sit in the path of Cilium's own pods, so a Kyverno outage during a Cilium rollout could leave no network for Kyverno to recover on. The definition rule parses the CNI configuration with Kyverno's `json.unmarshal` and stays a webhook policy; definitions never live in `kube-system`.

Namespaces that may hold definitions are labelled `home.seneker.io/iot-attachments: "true"`, and workloads that may use them `home.seneker.io/iot-attachment: "true"`.

- **On pods:**
    - Deny `v1.multus-cni.io/default-network` everywhere.
    - Allow `k8s.v1.cni.cncf.io/networks` only on labelled workloads in namespaces that hold attachment definitions.
    - Allow only the plain name-list form, without `namespace`, `default-route`, `ips`, `mac` or `interface` keys.
- **On definitions:** allow them only in those namespaces, and require macvlan in bridge mode on the VLAN 20 NIC with one static address from 192.168.20.10 -- .49, a fixed locally administered MAC and no gateway, routes or runtime capabilities, followed by the `tuning` plugin. Reject other plugin types, such as `host-device`, `vlan`, `ipvlan` and `bridge`, and any other parent interface.
- **On status writes:** the Multus ServiceAccount may change only the `network-status` annotation; spec, status, labels, owners and other annotations must stay the same.
- **RBAC:** only cluster administrators and ArgoCD may create definitions. The upstream CRDs add no aggregated roles.

## Alternatives Considered

- **`hostNetwork` on a dual-homed worker**: No new component; the community Kubernetes write-up for Matter and Thread uses this approach ([forum post](https://community.home-assistant.io/t/running-matter-thread-with-an-external-otbr-alongside-home-assistant-on-kubernetes/1027093)). The worker would need an address on VLAN 20, exposing kubelet, NodePorts and every other host listener to the least trusted network and bypassing the zone firewall.
- **Unicast through the gateway**: A Homelab-to-IoT firewall rule reaches devices that are addressed directly. Discovery, HomeKit and Matter still fail, and the mDNS proxy is not a substitute for Matter.
- **Filtering inside the pod**: An init container with `NET_ADMIN` could install nftables rules in the pod's namespace. It needs a capability and a policy exception for the workload being protected, and anything that compromises the pod can undo it. The Proxmox filter sits outside both the pod and the node.
- **ipvlan instead of macvlan**: One MAC per parent, but all attached pods share it. That breaks per-client identification and the per-address Proxmox filter.
- **Cilium multi-network**: Not available in open-source Cilium, per the issue above.
- **Multus thin plugin or a community Helm chart**: Upstream recommends the thick plugin, and a third-party chart wraps the same manifests with less control over RBAC and image pinning.

## Consequences

- Multus sits in the sandbox-creation path for every pod on every node. A failed Multus daemon stops new pods on that node, including unrelated workloads. It needs a node-critical priority class, resource requests, and an alert alongside Cilium's.
- Upstream does not support this combination. Each Cilium upgrade must re-verify pod creation through Multus and an attachment on VLAN 20, and the [Kubernetes upgrade runbook](../runbooks/upgrading-kubernetes.md) gains that check. With `cni.exclusive: false`, Cilium no longer removes stray CNI configurations.
- The Multus DaemonSet runs privileged with host networking, the host PID namespace and host mounts. It lives in `kube-system`, which the general Kyverno policies exclude; the Multus policies above do not.
- Traffic on an attachment bypasses CiliumNetworkPolicy and Hubble, and traffic within VLAN 20 never passes the UniFi zone firewall. The Proxmox NIC filter is the only network control between IoT devices and an attached pod. An attached pod also bridges the IoT network to its own Cilium-side permissions, so attach only pods that need it and keep their Cilium-side policies narrow.
- Addresses on VLAN 20 are not authenticated. Any IoT device can claim an attachment's address or impersonate one by ARP. Protocols between attached workloads and devices should authenticate and encrypt where they can.
- This design depends on ADR-016's hypervisor enforcement, with its console and rehearsal requirements.
- The restore lab has no VLAN 20. It can rehearse the Cilium setting and Multus pod creation, but not the attachment itself.
- Attached pods can only run on workers with the VLAN 20 NIC. Each needs a recorded address in its definition and in the Proxmox filter.
- Node rebuilds pick up the second NIC, its sysctls and its nftables table from Terraform and Ansible.
