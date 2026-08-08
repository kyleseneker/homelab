# Authentik Emergency Bypass

What to do when Authentik goes down and OIDC logins stop working.

## Impact Assessment

Only Grafana and ArgoCD depend on Authentik. Nothing sits behind edge authentication -- see [Auth & SSO](../architecture/auth.md) for why -- so no app becomes *unreachable* when Authentik is down.

| App Type | Impact |
|----------|--------|
| OIDC apps (Grafana, ArgoCD) | **SSO login fails** -- fall back to local admin credentials, below |
| *arr apps, qBittorrent, Tdarr, Homepage | **Unaffected** -- no edge auth |
| Jellyfin | **Unaffected** -- has its own auth, no SSO dependency |

## Fallback: Local Admin Logins

Both OIDC apps keep a local account that bypasses Authentik entirely.

### ArgoCD

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

Log in at `https://argocd.homelab.local` as `admin`. If the initial secret has been deleted, reset the password by patching `argocd-secret` with a bcrypt hash of the new password.

### Grafana

The admin credentials are synced from Vault into the `grafana-admin` Secret:

```bash
kubectl -n monitoring get secret grafana-admin \
  -o jsonpath="{.data.admin-password}" | base64 -d; echo
```

Log in at `https://grafana.homelab.local` using the "sign in with username" link below the OAuth button.

!!! warning "Both fallbacks depend on Vault and ESO"
    If Vault is also down, ESO cannot refresh `grafana-admin` -- but the existing Kubernetes Secret persists, so the credential above still resolves. A cluster rebuild is a different matter; see [Disaster Recovery](disaster-recovery.md).

## Debugging Authentik

```bash
# Check pod status
kubectl get pods -n auth

# Check Authentik server logs
kubectl logs -n auth -l app.kubernetes.io/name=authentik -c authentik --tail=100

# Check PostgreSQL
kubectl logs -n auth -l app.kubernetes.io/name=postgresql --tail=50

# Restart Authentik
kubectl rollout restart deployment -n auth authentik-server
kubectl rollout restart deployment -n auth authentik-worker
```

The chart no longer deploys Redis; the task queue runs on PostgreSQL. If PostgreSQL is healthy and the server still fails, check the `authentik-credentials` Secret is populated -- a missing `AUTHENTIK_SECRET_KEY` crash-loops the server without an obvious error.

## Prevention

- Velero daily backup includes the `auth` namespace
- PostgreSQL data persists on NFS via `nfs-client` PVC
- Monitor Authentik health via Prometheus (add a ServiceMonitor if not already present)
