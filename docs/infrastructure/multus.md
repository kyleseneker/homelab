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
| `restrict-network-attachment-definitions` | Kyverno webhook | Allows definitions only in labelled namespaces, as macvlan in bridge mode on the VLAN 20 NIC with one static address from 192.168.20.10 -- .49 and a fixed, locally administered MAC, followed by the tuning plugin |

The first three are Kyverno `ValidatingPolicy` resources that Kyverno generates as native `ValidatingAdmissionPolicy` objects. The API server evaluates them in every namespace, including `kube-system`, without a fail-closed webhook in the path of the CNI's own pods. The definition policy parses the CNI configuration with Kyverno's `json.unmarshal`, so it stays a webhook policy; definitions never live in `kube-system`. Kubernetes' built-in `admin`, `edit` and `view` roles grant nothing on attachment definitions, so only cluster administrators and ArgoCD create them.

## Attaching a Workload

1. Label the workload's namespace `home.seneker.io/iot-attachments: "true"`.
2. Add the workload's definition to that namespace: one macvlan definition per workload, with its address and MAC recorded in the network docs and in the worker NIC's Proxmox IP filter, and the `tuning` sysctls from ADR-028.
3. Label the pod template `home.seneker.io/iot-attachment: "true"` and annotate it with `k8s.v1.cni.cncf.io/networks: <definition-name>`.

The attachment carries only its connected 192.168.20.0/24 route; the default route stays on Cilium's `eth0`.

## Operations

- `MultusUnavailable` fires when the DaemonSet has unavailable or missing pods for five minutes. New pods cannot start on a node whose Multus daemon is down.
- After any Cilium upgrade or restart, confirm each node still holds `00-multus.conf` ahead of `05-cilium.conflist`, and that a new pod on every node becomes Ready with a `network-status` annotation listing `cilium` on `eth0`.
- To remove Multus from a node or the cluster, delete the DaemonSet, then remove `00-multus.conf`, the `multus-shim` and `passthru` binaries and `/var/lib/cni/multus` from each node. Leaving `00-multus.conf` behind without the daemon stops new pods from starting.
