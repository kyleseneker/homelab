# Intel GPU (Operator + Plugin)

The Intel GPU stack enables iGPU passthrough for hardware-accelerated video transcoding in workloads such as Jellyfin and Tdarr.

## Details

| Field | Value |
|-------|-------|
| Charts | `intel-device-plugins-operator`, `intel-device-plugins-gpu` |
| Repository | <https://intel.github.io/helm-charts> |
| Version | 0.35.0 (both) |
| Namespace | `intel-gpu-operator` (CreateNamespace=true) |

## Key Configuration

The stack is split into two ArgoCD Applications:

### Intel Device Plugins Operator

Installs the operator that manages GPU device plugin lifecycle. Uses the shared ApplicationSet retry policy of limit 10 with exponential backoff (10s to 3m) and `SkipDryRunOnMissingResource=true` to handle CRD creation timing.

### Intel Device Plugins GPU

Deploys the `GpuDevicePlugin` custom resource that the operator reconciles into a DaemonSet.

- **sharedDevNum**: `5` -- up to 5 pods can share the same GPU simultaneously.
- **nodeFeatureRule**: `false`
- **Diff handling**: Server-side diff includes mutation webhooks for this Application. The whole `GpuDevicePlugin.spec` is not ignored: image, sharing and scheduling changes must remain visible to GitOps. The operator defaults a missing image and reconciles a DaemonSet; it does not own arbitrary changes to the desired CR spec.

Both applications share the same retry policy and `SkipDryRunOnMissingResource` setting.

## Cluster Integration

Applications that require GPU access are configured with:

```yaml
nodeSelector:
  gpu: intel
resources:
  limits:
    gpu.intel.com/i915: "1"
```

The device plugin injects the allocated device into the container. Do not add a broad `/dev/dri` hostPath merely to request a GPU; the resource limit is the allocation boundary. Confirm the worker has the labels selected by the plugin and workload.

!!! note "PCI Passthrough"
    The physical iGPU is passed through to the Kubernetes node VMs at the Terraform/Proxmox layer via the `pci_mappings` field in `terraform.tfvars`, which references a Proxmox PCI device mapping. The Intel GPU plugin only handles the in-cluster device advertisement.

## Upstream Documentation

<https://github.com/intel/intel-device-plugins-for-kubernetes>
