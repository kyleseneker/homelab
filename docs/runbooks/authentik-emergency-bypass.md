# Authentik Emergency Bypass

What to do when Authentik goes down and proxy routes or OIDC logins stop working.

## Impact Assessment

The embedded outpost proxies protected browser traffic. An outage can affect the full route, including paths that skip login. In-cluster Service access remains available if the backend is healthy.

| App Type | Impact |
|----------|--------|
| OIDC apps (Grafana, ArgoCD) | **SSO login fails** -- fall back to local admin credentials, below |
| *arr apps, qBittorrent, Tdarr, Goldilocks, Prometheus, Alertmanager | **Public route fails** if the proxy outpost is unavailable; use local port forwarding during recovery |
| Homepage, Vault, OpenClaw, Uptime Kuma | **No edge dependency** -- native authentication still applies where configured |
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

!!! warning "Recover credentials before rebuilding"
    Existing Kubernetes Secrets survive a Vault outage, so Grafana's current credential can still be retrieved. ArgoCD's local admin credential is independent of Vault. A cluster rebuild is a different matter; see [Disaster Recovery](disaster-recovery.md).

## Scoped Access to a Proxy-Protected Backend

Bind a port-forward to loopback while recovering Authentik. For example:

```bash
kubectl -n monitoring port-forward --address 127.0.0.1 \
  svc/kube-prometheus-stack-prometheus 9090:9090
```

Open `http://127.0.0.1:9090`. For an *arr application, forward its Service and port and use its local login. Stop the port-forward when finished. This requires an administrator's Kubernetes credentials; the proxy is not involved. Keep public HTTPRoutes pointed at the outpost so recovery does not publish an unauthenticated service to the LAN.

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
