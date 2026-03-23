# Intel GPU (Operator + Plugin)

The Intel GPU stack enables iGPU passthrough for hardware-accelerated video transcoding in workloads such as Jellyfin and Tdarr.

## Details

| Field | Value |
|-------|-------|
| Charts | `intel-device-plugins-operator`, `intel-device-plugins-gpu` |
| Repository | <https://intel.github.io/helm-charts> |
| Version | 0.31.1 (both) |
| Namespace | `intel-gpu-operator` (CreateNamespace=true) |
| Sync Waves | Operator: -2, Plugin: -1 |

## Key Configuration

The stack is split into two ArgoCD Applications:

### Intel Device Plugins Operator (sync wave -2)

Installs the operator that manages GPU device plugin lifecycle. Uses a retry policy of limit 30 with exponential backoff (10s to 5m) and `SkipDryRunOnMissingResource=true` to handle CRD creation timing.

### Intel Device Plugins GPU (sync wave -1)

Deploys the `GpuDevicePlugin` custom resource that the operator reconciles into a DaemonSet.

- **sharedDevNum**: `5` -- up to 5 pods can share the same GPU simultaneously.
- **nodeFeatureRule**: `false`
- **ignoreDifferences**: The `.spec` field of `GpuDevicePlugin` is excluded from ArgoCD diff detection because the operator actively manages the spec after initial creation.

Both applications share the same retry policy and `SkipDryRunOnMissingResource` setting.

## Cluster Integration

Applications that require GPU access are configured with:

```yaml
nodeSelector:
  gpu: intel
resources:
  limits:
    gpu.intel.com/i915: "1"
volumeMounts:
  - name: dev-dri
    mountPath: /dev/dri
volumes:
  - name: dev-dri
    hostPath:
      path: /dev/dri
```

!!! note "PCI Passthrough"
    The physical iGPU is passed through to the Kubernetes node VMs at the Terraform/Proxmox layer via `pci_devices` and `pci_mappings` configuration. The Intel GPU plugin only handles the in-cluster device advertisement.

## Upstream Documentation

<https://github.com/intel/intel-device-plugins-for-kubernetes>
