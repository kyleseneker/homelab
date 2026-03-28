# Authentik Emergency Bypass

What to do when Authentik goes down and forward-auth protected apps become inaccessible.

## Impact Assessment

When Authentik is unavailable:

| App Type | Impact |
|----------|--------|
| Forward-auth apps (Sonarr, Radarr, etc.) | **Inaccessible** -- nginx returns 503 on auth subrequest failure |
| OIDC apps (Grafana, ArgoCD) | **Unaffected** -- fall back to their own login pages |
| Jellyfin | **Unaffected** -- has its own auth, no SSO dependency |

## Quick Fix: Patch Ingress In-Cluster

Fastest recovery. Removes forward-auth annotations directly from the ingress resources. No git commit needed.

```bash
# Remove forward-auth from a single app
kubectl annotate ingress <ingress-name> -n arr \
  nginx.ingress.kubernetes.io/auth-url- \
  nginx.ingress.kubernetes.io/auth-signin- \
  nginx.ingress.kubernetes.io/auth-response-headers- \
  nginx.ingress.kubernetes.io/auth-snippet-

# Remove forward-auth from all arr ingresses at once
for ing in $(kubectl get ingress -n arr -o name); do
  kubectl annotate "$ing" -n arr \
    nginx.ingress.kubernetes.io/auth-url- \
    nginx.ingress.kubernetes.io/auth-signin- \
    nginx.ingress.kubernetes.io/auth-response-headers- \
    nginx.ingress.kubernetes.io/auth-snippet-
done
```

ArgoCD's `selfHeal` will revert these changes once Authentik recovers and the auth subrequests start succeeding again.

## Longer Fix: Remove Annotations from Git

If Authentik will be down for an extended period, remove the forward-auth annotations from the `values.yaml` files in Git to prevent ArgoCD from re-adding them.

1. Remove the four `nginx.ingress.kubernetes.io/auth-*` annotations from each protected app's `values.yaml`
2. Commit and push
3. ArgoCD syncs and apps become accessible without SSO

Re-add the annotations once Authentik is back.

## Debugging Authentik

```bash
# Check pod status
kubectl get pods -n auth

# Check Authentik server logs
kubectl logs -n auth -l app.kubernetes.io/name=authentik -c authentik --tail=100

# Check PostgreSQL
kubectl logs -n auth -l app.kubernetes.io/name=postgresql --tail=50

# Check Redis
kubectl logs -n auth -l app.kubernetes.io/name=redis --tail=50

# Restart Authentik
kubectl rollout restart deployment -n auth authentik-server
kubectl rollout restart deployment -n auth authentik-worker
```

## Prevention

- Velero daily backup includes the `auth` namespace
- PostgreSQL data persists on NFS via `nfs-client` PVC
- Monitor Authentik health via Prometheus (add a ServiceMonitor if not already present)
