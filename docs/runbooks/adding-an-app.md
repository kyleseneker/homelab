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
    targetRevision: 3.6.0
    helm:
      valuesObject:
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

        ingress:
          main:
            enabled: true
            className: nginx
            annotations:
              cert-manager.io/cluster-issuer: homelab-ca-issuer
            hosts:
              - host: <app-name>.homelab.local
                paths:
                  - path: /
                    service:
                      identifier: main
                      port: http
            tls:
              - hosts:
                  - <app-name>.homelab.local
                secretName: <app-name>-tls

        persistence:
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

### Key Fields

| Field | Description |
|-------|-------------|
| `metadata.name` | Unique name for the ArgoCD Application (prefix with `arr-` for media apps) |
| `metadata.annotations.argocd.argoproj.io/sync-wave` | Deploy order -- use `"1"` for standard apps, `"2"` for dashboards like Homepage |
| `spec.source.targetRevision` | Helm chart version -- keep consistent across apps unless testing a new version |
| `spec.destination.namespace` | Target namespace (`arr` for media apps, or create a new one) |
| `helm.valuesObject` | Inline Helm values -- configure containers, service, ingress, and persistence here |

## Step 3: Add Secrets (If Needed)

If the application requires secrets (API keys, credentials, etc.):

1. Create a `<name>-secret.example` file with the secret structure and placeholder values:

    ```yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: <app-name>-secrets
      namespace: arr
    type: Opaque
    stringData:
      API_KEY: "changeme"
    ```

2. Copy the example, fill in real values, and seal it:

    ```bash
    cp <name>-secret.example <name>-secret.yml
    # Edit <name>-secret.yml with real values
    make k8s-seal FILE=<name>-secret.yml
    mv <name>-sealed-secret.yml k8s/clusters/homelabk8s01/apps/arr/<app-name>/
    rm <name>-secret.yml
    ```

3. Reference the secret in `application.yml` via `envFrom` or `env.valueFrom`.

## Step 4: Add a DNS Entry

Add a DNS record for the new hostname (`<app-name>.homelab.local`) pointing to the ingress LoadBalancer IP address. The MetalLB-assigned IP can be found with:

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
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
