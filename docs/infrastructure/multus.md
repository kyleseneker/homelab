# Multus

Multus is a CNI meta-plugin. It wraps Cilium as every pod's network, so selected pods can get a second interface on the IoT VLAN while Cilium stays their default network ([ADR-028](../decisions/028-multus-iot-attachments.md)).

## Details

| Field | Value |
|-------|-------|
| Version | v4.3.1, thick plugin |
| Source | `infrastructure/multus/kustomization.yml` |
| Namespace | `kube-system` |
| DaemonSet | `kube-multus-ds`, on every node |

## Configuration

The kustomization pulls the upstream `multus-daemonset-thick.yml` pinned to the v4.3.1 release commit and patches only what differs here:

- **Image**: the release manifest references the floating `snapshot-thick` image, so `v4.3.1-thick` is pinned by digest.
- **Permissions**: Multus reads attachment definitions and pods. It writes a pod's `k8s.v1.cni.cncf.io/network-status` annotation through the `pods/status` subresource and has no `update` on pods themselves. Upstream grants every verb on attachment definitions and `update` on pods.
- **Daemon configuration**: `namespaceIsolation` limits a pod to definitions in its own namespace, and `globalNamespaces` names a namespace that does not exist, so `default` is not exempt. Cilium's `05-cilium.conflist` is the readiness indicator, so Multus never serves a pod before Cilium is ready on the node.
- **Scheduling**: `system-node-critical`, with memory headroom and no CPU limit, because Multus is in every pod's sandbox creation.

On each node the daemon writes `/etc/cni/net.d/00-multus.conf`, which sorts ahead of Cilium's configuration and names it as the cluster network. Cilium runs with `cni.exclusive: false` so it keeps that file, and with `devices: eth0` so a second node NIC never carries Cilium traffic.

## Admission

| Policy | Enforced by | Rule |
|--------|-------------|------|
| `disallow-multus-default-network` | API server | Denies `v1.multus-cni.io/default-network`, which would replace a pod's Cilium network, in every namespace |
| `restrict-multus-networks` | API server | Allows `k8s.v1.cni.cncf.io/networks` only on pods labelled `home.seneker.io/iot-attachment=true` in namespaces labelled `home.seneker.io/iot-attachments=true`, as plain definition names |
| `restrict-multus-status-updates` | API server | Lets Multus's ServiceAccount change only the `network-status` annotation; spec, status, labels and other annotations must stay the same |
| `restrict-network-attachment-definitions` | Kyverno webhook | Allows definitions only in labelled namespaces, as macvlan in bridge mode on the VLAN 20 NIC with one static address from 192.168.20.10 -- .49 and a fixed, locally administered MAC, followed by the tuning plugin. The parent is `ens19`, the kernel's name for each worker's second NIC |

The first three are Kyverno `ValidatingPolicy` resources that Kyverno generates as native `ValidatingAdmissionPolicy` objects. The API server evaluates them in every namespace, including `kube-system`, without a fail-closed webhook in the path of the CNI's own pods. The definition policy parses the CNI configuration with Kyverno's `json.unmarshal`, so it stays a webhook policy; definitions never live in `kube-system`. Kubernetes' built-in `admin`, `edit` and `view` roles grant nothing on attachment definitions, so only cluster administrators and ArgoCD create them.

## Attaching a Workload

1. Label the workload's namespace `home.seneker.io/iot-attachments: "true"`.
2. Record the attachment in `iot_nic.attachments` in `terraform/hosts/homelabk8s01/terraform.tfvars`, with its address and the ports devices connect to, and apply it to both workers. The address becomes a source `ipfilter-net1` allows, and the ports open from 192.168.20.0/24.
3. Add the workload's definition to that namespace: one macvlan definition per workload on `ens19`, with its address and MAC recorded in the network docs, and the `tuning` sysctls from ADR-028.
4. Label the pod template `home.seneker.io/iot-attachment: "true"`, annotate it with `k8s.v1.cni.cncf.io/networks: <definition-name>`, and select nodes labelled `home.seneker.io/iot-vlan=true`.

The attachment carries only its connected 192.168.20.0/24 route; the default route stays on Cilium's `eth0`.

## Worker NICs

Each worker has a second NIC, `net1` in Proxmox and `ens19` in the VM, as an access port on VLAN 20. Proxmox filters it outside the node: MAC filtering is off for the worker VMs, because macvlan needs extra MACs, but `ipfilter-net1` allows only the recorded attachment addresses, and inbound it admits only mDNS, SSDP and the recorded ports from 192.168.20.0/24. The `k8s_iot_nic` role (`make k8s-iot-nic`) keeps `ens19` a bare link with no addresses, IPv6 or forwarding, and an nftables table that drops anything the node itself would accept, route or send on it.

## Operations

- `MultusUnavailable` fires when the DaemonSet has unavailable or missing pods for five minutes. New pods cannot start on a node whose Multus daemon is down.
- After any Cilium upgrade or restart, confirm each node still holds `00-multus.conf` ahead of `05-cilium.conflist`, and that a new pod on every node becomes Ready with a `network-status` annotation listing `cilium` on `eth0`.
- To remove Multus from a node or the cluster, delete the DaemonSet, then remove `00-multus.conf`, the `multus-shim` and `passthru` binaries and `/var/lib/cni/multus` from each node. Leaving `00-multus.conf` behind without the daemon stops new pods from starting.
