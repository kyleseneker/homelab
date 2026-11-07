# Kyverno

Kyverno is a Kubernetes-native policy engine that validates, mutates, and generates resources using admission webhooks. It runs as a set of controllers in the `kyverno` namespace and evaluates policies against incoming API requests.

## Details

| Field | Value |
|-------|-------|
| Chart | `kyverno` |
| Repository | <https://kyverno.github.io/kyverno/> |
| Version | 3.9.2 |
| Namespace | `kyverno` |

## Key Configuration

- **Admission Controller**: 3 replicas, one per node including the control plane, with a `maxUnavailable: 1` PDB. Required anti-affinity keeps a drained node's replica Pending until that node returns, so the fail-closed webhook keeps two replicas through each drain and the spread restores itself. Rollouts replace pods in place (`maxSurge: 0`) because no node has room for a surge replica.
- **Resources** (across all controllers):
    - Requests: ~250m CPU, ~320Mi memory
    - Limits: ~896Mi memory
- **Validation Mode**: Enforce (non-compliant pods are rejected at admission)
- **Policy exceptions**: Enabled and honored only in the `kyverno` namespace (`features.policyExceptions`), which only cluster administrators write. A workload's own namespace cannot grant it an exception.

## Policies

Policies are deployed as `ValidatingPolicy` resources (`policies.kyverno.io/v1`) via a separate ArgoCD Application (`kyverno-policies`). All policies use `validationActions: [Deny]` with `failurePolicy: Fail` -- non-compliant pods are rejected at admission time, and the webhook fails closed.

Each policy autogenerates rules for DaemonSets, Deployments, Jobs, CronJobs, ReplicaSets, ReplicationControllers and StatefulSets, so a non-compliant controller is rejected before it creates Pods. Exact namespace exclusions use `matchConstraints.namespaceSelector`; `cilium-test-*` is matched through `namespaceObject`, because autogen rewrites `object.metadata` for controllers. Unlike the legacy `ClusterPolicy`, which allowed updates to objects that already violated it, a ValidatingPolicy denies those updates too: fix existing violations before tightening a policy. Kyverno 1.19 deprecated `ClusterPolicy`; these policies replaced the original five on 2026-10-31 after running beside them in Audit mode with identical results on every workload.

| Policy | What It Checks | Excluded Namespaces |
|--------|----------------|---------------------|
| `require-resource-limits` | All containers have CPU and memory limits | backups, local-path-storage |
| `require-run-as-nonroot` | Containers set `runAsNonRoot: true` | arr, auth, backups, intel-gpu-operator, monitoring, nfs-provisioner, local-path-storage |
| `require-readonly-rootfs` | Containers set `readOnlyRootFilesystem: true` | arr, auth, backups, monitoring, nfs-provisioner, local-path-storage |
| `disallow-latest-tag` | Images use a non-latest tag or SHA-256 digest | |
| `require-labels` | Pods have the `app.kubernetes.io/name` label | backups, intel-gpu-operator, nfs-provisioner |

These five policies also exclude the base system namespaces: kube-system, kyverno, argocd, and cilium-test-*.

Image tags and security contexts are checked on regular, init and ephemeral containers. Resource limits apply to regular and init containers; Kubernetes does not permit resources on ephemeral containers. Namespace exclusions also exempt unrelated workloads sharing those namespaces and should be narrowed after a rendered-workload audit.

### Namespace Exclusions

The five policies above exclude namespaces where compliance is not feasible:

- **arr, auth**: linuxserver and Authentik images require root and writable root filesystems (s6-overlay init system)
- **backups**: Velero dynamically creates backup/restore/maintenance Job pods with specs we do not control
- **intel-gpu-operator**: GPU device plugin DaemonSet requires host-level access
- **monitoring**: Alloy requires root for reading host log files
- **nfs-provisioner**: Requires host-level access for NFS mounts

### Pod Security Baseline

Seven policies enforce the Pod Security baseline. They exclude only `kube-system`, which holds the control plane and Cilium, and `cilium-test-*`.

| Policy | What It Denies |
|--------|----------------|
| `disallow-privileged-containers` | `privileged: true` or a non-default `procMount` |
| `disallow-host-namespaces` | `hostNetwork`, `hostPID` or `hostIPC` |
| `disallow-host-ports` | Container host ports, including the ports a `hostNetwork` pod declares |
| `disallow-host-path` | `hostPath` volumes |
| `restrict-capabilities` | Added capabilities beyond the baseline set |
| `restrict-sysctls` | Sysctls outside the baseline's safe set |
| `restrict-security-profiles` | Unconfined seccomp or AppArmor, and SELinux options other than the container types |

Namespaces are not excluded from these controls, because one workload that needs host access would exempt every other workload sharing its namespace. A workload that needs one gets a `PolicyException` in `baseline-exceptions.yml` instead. The exception lists exactly the values the workload uses in `allowedValues`, and the policy reads them through `exceptions.allowedValues`; anything else is still denied. `disallow-host-path` also accepts a `prefix:<directory>/` value for a workload whose paths differ per pod: it admits paths below that directory, but not the directory itself or a path containing `..`. Other values, including a path with a trailing slash, match exactly. Exceptions match the namespace and the pod template's name label, whether the admitted object is the Pod, its controller or a CronJob. Pods a controller creates have no name at admission, so exceptions cannot match names. Velero's hosting pods are the exception: node-agent creates each one directly, names it after its PodVolumeBackup or PodVolumeRestore and sets the same name in a label, so their exception requires a bare Pod whose label equals its name.

| Workload | Namespace | Allowed |
|----------|-----------|---------|
| Jellyfin, Tdarr | `arr` | `hostPath` `/dev/dri` |
| Gluetun (`arr-vpn-downloads`) | `arr` | `NET_ADMIN`, sysctl `net.ipv4.conf.all.src_valid_mark` |
| Velero node-agent | `backups` | `hostPath` `/var/lib/kubelet/pods`, `/var/lib/kubelet/plugins` |
| Velero pod volume backup/restore hosting pods | `backups` | `hostPath` below `/var/lib/kubelet/pods/` for the volume each pod copies, plus node-agent's `/var/lib/kubelet/pods` and `/var/lib/kubelet/plugins`, which every hosting pod inherits |
| etcd-backup | `backups` | `hostPath` for etcd's PKI and the control-plane configuration |
| Intel GPU plugin | `intel-gpu-operator` | `hostPath` for the device nodes and kubelet plugin sockets; SELinux type `container_device_plugin_t` |
| Alloy | `monitoring` | `hostPath` `/var/log/kubernetes/audit` |
| node-exporter | `monitoring` | `hostNetwork`, `hostPID`, host port 9100, `hostPath` `/`, `/proc`, `/sys` |
| local-path helper pods | `local-path-storage` | `hostPath` `/opt/local-path-provisioner` |

A new workload that needs host access needs its exception before it deploys. An exception trusts its label within its namespace: any pod there with that label receives the exception's values. `kubectl debug node/<node>` creates a pod with the host's namespaces and root filesystem, so run it in `kube-system`: `kubectl debug -n kube-system node/<node> -it --image=<image>`.

### Multus

Four policies guard Multus ([ADR-028](../decisions/028-multus-iot-attachments.md)); see [Multus](multus.md#admission) for their rules. Three set `autogen.validatingAdmissionPolicy.enabled`, so Kyverno generates them as native `ValidatingAdmissionPolicy` objects that the API server enforces in every namespace, including `kube-system`. Kyverno's own webhooks exclude `kube-system` through the chart's `config.webhooks` and `resourceFilters`; the native policies avoid a fail-closed webhook in the path of Cilium's and Multus's pods. Kyverno skips that generation for a policy with pod-controller autogen, so the two pod policies set `autogen.podControllers.controllers: []`; a controller's pods are still checked as they are created.

### Local Regression Checks

`tests/kyverno/container-security` covers valid pods and denied init/ephemeral container bypasses, including an image registry port that must not be mistaken for an image tag, and the `app.kubernetes.io/name` label. `tests/kyverno/multus` covers the default-network and attachment-request policies. `tests/kyverno/pod-security-baseline` covers each baseline control and the exceptions: an exempted workload passes only with its listed values, in its namespace and under its label, and the same request fails anywhere else. Model an exception's test pods on what the workload actually creates, not only its controller: the Velero cases use the hosting pod's full volume list, the per-volume path node-agent logs plus every volume it inherits from the node-agent DaemonSet, because an exception that covered node-agent alone let every pod volume backup fail at admission. Before relying on a new exception, server-side dry-run a pod of that exact shape (`kubectl create --dry-run=server`); it runs Kyverno's admission check without creating anything. Run them with the Kyverno CLI matching the chart application version (currently 1.19.2):

```bash
kyverno test tests/kyverno
```

Before enabling stronger checks, also apply the policies locally to rendered workload manifests with their destination namespaces. Include init containers from dependency charts; admission failures can otherwise block upgrades. Helm test hooks are a separate test execution concern.

### Checking Policy Reports

To see which workloads violate policies (background scan results):

```bash
kubectl get policyreport -A
```

## Network Policies

Kyverno has its own CiliumNetworkPolicy rules:

- **Ingress**: Default deny from world; allow from cluster, kube-apiserver, and host (required for webhook calls)
- **Egress**: DNS, intra-namespace, and kube-apiserver only

## Architecture

Kyverno deploys four controllers:

| Controller | Purpose |
|------------|---------|
| Admission Controller | Intercepts API requests and evaluates policies |
| Background Controller | Scans existing resources against policies |
| Cleanup Controller | Manages resource cleanup based on policy TTLs |
| Reports Controller | Generates and manages policy reports |

## Upstream Documentation

<https://kyverno.io/docs/>
