# Adding a New Application

This runbook walks through adding a new application to the cluster. All apps are deployed as ArgoCD Application resources backed by Helm charts, and ArgoCD discovers them automatically through recursive directory scanning from the root application.

## Step 1: Create the Application Directory

Create a directory for the new app under the appropriate location:

- **Media/arr apps**: `k8s/clusters/homelabk8s01/apps/arr/<app-name>/`
- **Other apps**: `k8s/clusters/homelabk8s01/apps/<app-name>/`

```bash
mkdir -p k8s/clusters/homelabk8s01/apps/arr/<app-name>
```

## Step 2: Create the Application Manifest

Create `application.yml` in the new directory. The manifest defines an ArgoCD Application that uses the bjw-s app-template Helm chart with inline values.

### Minimal Template

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: arr-<app-name>
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://bjw-s-labs.github.io/helm-charts
    chart: app-template
    targetRevision: 4.6.2
    helm:
      valuesObject:
        defaultPodOptions:
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            fsGroup: 1000
            runAsNonRoot: true

        controllers:
          main:
            containers:
              main:
                image:
                  repository: <image-repository>
                  tag: <image-tag>
                envFrom:
                  - configMapRef:
                      name: arr-env
                securityContext:
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true
                  capabilities:
                    drop:
                      - ALL
                resources:
                  requests:
                    cpu: 100m
                    memory: 256Mi
                  limits:
                    memory: 512Mi
                probes:
                  liveness:
                    enabled: true
                  readiness:
                    enabled: true
                  startup:
                    enabled: true

        service:
          main:
            controller: main
            ports:
              http:
                port: <port>

        route:
          main:
            enabled: true
            kind: HTTPRoute
            parentRefs:
              - group: gateway.networking.k8s.io
                kind: Gateway
                name: homelab-gateway
                namespace: default
                sectionName: https
            hostnames:
              - <app-name>.homelab.local
            rules:
              - matches:
                  - path:
                      type: PathPrefix
                      value: /
                backendRefs:
                  - name: arr-<app-name>
                    port: <port>

        persistence:
          tmp:
            type: emptyDir
            globalMounts:
              - path: /tmp
          config:
            type: persistentVolumeClaim
            storageClass: nfs-client
            accessMode: ReadWriteOnce
            size: 1Gi
            globalMounts:
              - path: /config
          data:
            type: persistentVolumeClaim
            existingClaim: arr-data
            globalMounts:
              - path: /data

  destination:
    server: https://kubernetes.default.svc
    namespace: arr
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - ServerSideDiff=true
```

Replace the `<placeholder>` values with your application's specifics.

!!! tip
    Use an existing app's `application.yml` as a starting point. The Sonarr manifest at `k8s/clusters/homelabk8s01/apps/arr/sonarr/application.yml` is a good reference for a typical arr-stack application.

!!! note "linuxserver.io images"
    If the image is from linuxserver.io, you will need to remove `readOnlyRootFilesystem: true` and add `SETUID`/`SETGID` capabilities for the s6-overlay init system. See the Sonarr or Radarr manifests for examples.

### Key Fields

| Field | Description |
|-------|-------------|
| `metadata.name` | Unique name for the ArgoCD Application (prefix with `arr-` for media apps) |
| `metadata.annotations.argocd.argoproj.io/sync-wave` | Deploy order -- use `"1"` for standard apps, `"2"` for dashboards like Homepage |
| `spec.source.targetRevision` | Helm chart version -- keep consistent across apps unless testing a new version |
| `spec.destination.namespace` | Target namespace (`arr` for media apps, or create a new one) |
| `helm.valuesObject` | Inline Helm values -- configure containers, service, route, and persistence here |

## Step 3: Add Secrets (If Needed)

If the application requires secrets (API keys, credentials, etc.):

1. Create an `ExternalSecret` manifest that references a Vault path:

    ```yaml
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: <app-name>-secrets
      namespace: arr
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: ClusterSecretStore
        name: vault-backend
      target:
        name: <app-name>-secrets
      data:
        - secretKey: API_KEY
          remoteRef:
            key: apps/<app-name>
            property: API_KEY
    ```

2. Write the actual values to Vault:

    ```bash
    vault kv put homelab/apps/<app-name> API_KEY=your_real_key
    ```

3. Reference the secret in `application.yml` via `envFrom` or `env.valueFrom`.

## Step 4: Add a DNS Entry

Add a DNS record for the new hostname (`<app-name>.homelab.local`) pointing to the Cilium L2 VIP assigned to the `homelab-gateway`. The gateway IP can be found with:

```bash
kubectl get gateway homelab-gateway -n default -o jsonpath='{.status.addresses[0].value}'
```

## Step 5: Commit and Push

```bash
git add k8s/clusters/homelabk8s01/apps/arr/<app-name>/
git commit -m "add <app-name>"
git push
```

ArgoCD's root application uses recursive directory scanning, so the new application will be discovered and synced automatically. Monitor the deployment in the ArgoCD UI at `https://argocd.homelab.local`.

## Verification

1. Check that ArgoCD picked up the new application:

    ```bash
    kubectl get application -n argocd arr-<app-name>
    ```

2. Verify the pod is running:

    ```bash
    kubectl get pods -n arr -l app.kubernetes.io/instance=arr-<app-name>
    ```

3. Open the web UI at `https://<app-name>.homelab.local` and confirm it loads.
