# Troubleshooting

This runbook covers common issues and the commands used to diagnose them.

## General Debugging

Start any investigation with these commands:

```bash
# Pod status overview
kubectl get pods -n <namespace>

# Detailed pod information and events
kubectl describe pod -n <namespace> <pod>

# Pod logs (current instance)
kubectl logs -n <namespace> <pod> [-c <container>]

# Pod logs (previous crashed instance)
kubectl logs -n <namespace> <pod> --previous

# Recent events sorted by time
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

## ArgoCD Sync Issues

### App Stuck in "Progressing"

The application reports `Progressing` but never reaches `Healthy`.

**Possible causes:**

- Resource quotas preventing pod scheduling
- Missing CRDs that the application depends on (check sync wave ordering)
- Failed health checks (readiness/liveness probes misconfigured)
- Pods stuck in `Pending` due to insufficient node resources

**Diagnosis:**

```bash
kubectl get application -n argocd <app-name> -o yaml
kubectl get pods -n <namespace> -l app.kubernetes.io/instance=<app-name>
kubectl describe pod -n <namespace> <pod>
```

### App Shows "OutOfSync" but Is Healthy

The application is running correctly but ArgoCD reports it as out of sync.

**Possible causes:**

- Server-side apply drift -- fields managed by controllers (e.g., defaulted values) differ from the Git source
- Missing `ignoreDifferences` configuration for fields that are legitimately modified at runtime

**Resolution:**

Check which fields are out of sync in the ArgoCD UI (App > Diff). If the drift is expected, add an `ignoreDifferences` block to the Application spec.

### Force Sync

If an application is stuck, force a sync with replacement from the ArgoCD UI:

1. Open `https://argocd.homelab.local`
2. Select the application
3. Click **Sync**, enable **Replace**, and click **Synchronize**

## Pod CrashLoopBackOff

The pod starts, crashes, and Kubernetes keeps restarting it with increasing backoff delays.

**Diagnosis:**

```bash
kubectl logs -n <namespace> <pod> --previous
kubectl describe pod -n <namespace> <pod>
```

**Common causes:**

| Cause | Symptoms in Logs |
|-------|-----------------|
| Missing secret | `Error: secret "<name>" not found` or env var is empty |
| Wrong image tag | `ImagePullBackOff` or `ErrImagePull` |
| Configuration error | Application-specific error messages at startup |
| Resource limits too low | `OOMKilled` in pod events |

## Volume Mount Issues

### NFS Timeouts

Pods are stuck in `ContainerCreating` with mount errors referencing the NFS server.

**Diagnosis:**

```bash
# Verify NAS is reachable
ping 192.168.1.158

# Check NFS provisioner pod
kubectl get pods -n nfs-provisioner
kubectl logs -n nfs-provisioner -l app=nfs-subdir-external-provisioner
```

### PVC Stuck in Pending

A PersistentVolumeClaim remains in `Pending` state and is never bound.

**Diagnosis:**

```bash
kubectl describe pvc -n <namespace> <pvc-name>
kubectl get storageclass
kubectl logs -n nfs-provisioner -l app=nfs-subdir-external-provisioner
```

**Common causes:**

- NFS provisioner pod is not running
- The `nfs-client` StorageClass does not exist
- NAS NFS exports are misconfigured or unreachable

### Permission Issues

Applications report permission denied errors when accessing files on NFS volumes.

**Resolution:**

Check that the `PUID` and `PGID` values in the `arr-env` ConfigMap match the user/group ownership on the NAS share. LinuxServer.io containers use these environment variables to set the runtime user.

```bash
kubectl get configmap -n arr arr-env -o yaml
```

## Network Issues

### Service Unreachable

An application's service does not respond.

```bash
kubectl get svc -n <namespace>
kubectl get endpoints -n <namespace> <service-name>
```

If endpoints are empty, the service selector does not match any running pods.

### Ingress Not Working

The application is running but not reachable via its hostname.

**Diagnosis:**

```bash
# Check HTTPRoute resources
kubectl get httproute -n <namespace>

# Check Gateway status
kubectl get gateway homelab-gateway -n default

# Verify DNS resolves to the Cilium L2 VIP
dig <app-name>.homelab.local
```

**Common causes:**

- DNS does not point to the Cilium L2 LoadBalancer IP
- HTTPRoute parentRef does not reference the correct Gateway
- The backend service name or port is misconfigured

### VPN Not Connecting

The Gluetun VPN container fails to establish a connection, blocking qBittorrent.

```bash
kubectl logs -n arr -l app.kubernetes.io/instance=arr-vpn-downloads -c gluetun
```

**Common causes:**

- VPN credentials secret is missing or contains incorrect values
- VPN provider is experiencing an outage
- Firewall rules blocking the VPN connection

## Certificate Issues

### TLS Errors in Browser

The browser reports certificate errors beyond the expected self-signed CA warning.

**Diagnosis:**

```bash
# Check Certificate resources
kubectl get certificates --all-namespaces

# Check cert-manager logs
kubectl logs -n cert-manager -l app.kubernetes.io/name=cert-manager

# Check ClusterIssuer
kubectl get clusterissuer
kubectl describe clusterissuer homelab-ca-issuer
```

**Common causes:**

- The `homelab-ca-issuer` ClusterIssuer does not exist or is not ready
- cert-manager pods are not running
- The Certificate resource failed to issue (check events with `kubectl describe certificate`)

!!! note
    Self-signed CA warnings are expected unless you have [trusted the homelab CA](../getting-started/trust-ca.md) on your machine.


## Vault Issues

### Vault Pod Fails to Start (`CreateContainerConfigError`)

The `vault-aws-kms` Secret is missing from the `vault` namespace. Vault requires this Secret to decrypt the master key via AWS KMS before it can start.

Create it before the pod starts:

```bash
kubectl create namespace vault  # if it doesn't exist yet
kubectl create secret generic vault-aws-kms \
  --namespace vault \
  --from-literal=AWS_ACCESS_KEY_ID="<access_key_id>" \
  --from-literal=AWS_SECRET_ACCESS_KEY="<secret_access_key>" \
  --from-literal=AWS_REGION="us-east-1" \
  --from-literal=VAULT_AWSKMS_SEAL_KEY_ID="<kms_key_id>"
```

### Vault Starts but Remains Sealed

Vault is running but KMS connectivity is failing. Check the logs:

```bash
kubectl -n vault logs vault-0
```

Look for `failed to unseal` or `AccessDeniedException`. Verify the IAM policy attached to the Vault user allows `kms:Decrypt`, `kms:Encrypt`, and `kms:DescribeKey` on the key, and that the credentials in `vault-aws-kms` are correct.

### ESO Shows `SecretSyncError`

If Vault is unsealed but ExternalSecrets are failing to sync, the ESO Kubernetes auth token may have expired. Force a resync:

```bash
kubectl annotate externalsecret <name> -n <namespace> \
  force-sync=$(date +%s) --overwrite
```
