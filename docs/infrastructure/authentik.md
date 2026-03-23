# Authentik

Authentik is the centralized identity provider for the homelab, handling SSO via forward-auth (for arr apps and Homepage) and native OIDC (for Grafana, ArgoCD, and Jellyseerr).

## Details

| Field | Value |
|-------|-------|
| Chart | `authentik` |
| Repository | <https://charts.goauthentik.io> |
| Version | 2026.2.1 |
| Namespace | `auth` |
| Sync Wave | 0 |

## Architecture

Authentik uses two authentication mechanisms depending on the application:

### Forward Auth (Domain-Level)

Apps that lack native SSO support are protected via nginx-ingress `auth_request` subrequests. When a user visits a protected app, nginx checks the session with Authentik's embedded outpost before allowing access.

```
User -> nginx-ingress -> auth_request -> Authentik outpost
                      |                        |
                      |<-- 200 (authenticated) -|
                      |-> proxy to backend app
```

**Protected apps:** Sonarr, Radarr, Prowlarr, Bazarr, Tdarr, qBittorrent/SABnzbd, Homepage

### Native OIDC

Apps with built-in OAuth2/OIDC support authenticate directly with Authentik as an identity provider.

**OIDC apps:** Grafana, ArgoCD, Jellyseerr

### Unprotected (with rationale)

- **Jellyfin** -- has its own user auth; media clients (Roku, Apple TV, mobile) can't do browser-based SSO
- **Prometheus/Alertmanager** -- internal monitoring; forward-auth would break Grafana datasource scraping

## Key Configuration

- PostgreSQL persistence via `nfs-client` (5Gi)
- Redis in standalone mode with `nfs-client` persistence (1Gi)
- Ingress at `auth.homelab.local` with TLS via `homelab-ca-issuer`
- Outpost cookie domain: `.homelab.local` (enables cross-subdomain SSO sessions)
- Forward-auth `auth-url` uses internal service URL (`http://authentik-server.auth.svc.cluster.local/...`) to avoid TLS trust issues
- `auth-signin` uses external URL (`https://auth.homelab.local/...`) for browser redirects

## Secrets

| Secret | Namespace | Keys |
|--------|-----------|------|
| `authentik-credentials` | `auth` | `secret-key`, `postgresql-password`, `bootstrap-password`, `bootstrap-token` |
| `grafana-oidc-secret` | `monitoring` | `GRAFANA_OIDC_CLIENT_SECRET` |
| `argocd-secret` (merge) | `argocd` | `oidc.authentik.clientSecret` |

All managed via Sealed Secrets. See example templates in:

- `infrastructure/authentik/authentik-secret.example`
- `infrastructure/authentik/argocd-oidc-secret.example`
- `infrastructure/kube-prometheus-stack/grafana-oidc-secret.example`

## Post-Deploy Setup

Prerequisites: Authentik pods running in `auth` namespace, `auth.homelab.local` DNS configured in UniFi gateway, sealed secrets applied.

1. Navigate to `https://auth.homelab.local/if/flow/initial-setup/` and set the `akadmin` password.
2. Log in to the admin interface at `https://auth.homelab.local/if/admin/`.
3. Create a **Kubernetes Service-Connection** in System > Outpost Integrations (name: `local-cluster`, leave kubeconfig empty).
4. Edit the **authentik Embedded Outpost** -- set integration to `local-cluster`, set `authentik_host` to `http://authentik-server.auth.svc.cluster.local`.
5. Create a **Proxy Provider** (Applications > Providers):
    - Name: `homelab-forward-auth`
    - Mode: **Forward auth (domain level)**
    - External host: `https://auth.homelab.local`
    - Cookie domain: `.homelab.local`
6. Create an **Application** (name: `Homelab Forward Auth`, provider: `homelab-forward-auth`).
7. Edit the embedded outpost, add the `Homelab Forward Auth` application.
8. Create **OAuth2/OpenID Provider** for Grafana (client ID: `grafana`, redirect URI: `https://grafana.homelab.local/login/generic_oauth`). Seal the client secret:

    ```bash
    cp infrastructure/kube-prometheus-stack/grafana-oidc-secret.example grafana-oidc-secret.yml
    # Edit with client secret, then:
    make k8s-seal FILE=k8s/clusters/homelabk8s01/infrastructure/kube-prometheus-stack/grafana-oidc-secret.yml
    ```

9. Create **OAuth2/OpenID Provider** for ArgoCD (client ID: `argocd`, redirect URI: `https://argocd.homelab.local/auth/callback`). Seal the client secret:

    ```bash
    cp infrastructure/authentik/argocd-oidc-secret.example argocd-oidc-secret.yml
    # Edit with client secret, then:
    make k8s-seal FILE=k8s/clusters/homelabk8s01/infrastructure/authentik/argocd-oidc-secret.yml
    # Manually apply since ArgoCD manages itself:
    kubectl apply -f argocd-oidc-sealed-secret.yml
    ```

10. Create **OAuth2/OpenID Provider** for Jellyseerr (client ID: `jellyseerr`, redirect URI per Jellyseerr settings). Configure in Jellyseerr's Settings > Authentication.
11. Create an `admin` group in Directory > Groups (maps to Grafana Admin and ArgoCD `role:admin`).
12. Create user accounts in Directory > Users and assign to groups.

## Backups

The `auth` namespace is included in the Velero daily stateful backup schedule. The weekly full-cluster backup (`"*"`) also covers it.
