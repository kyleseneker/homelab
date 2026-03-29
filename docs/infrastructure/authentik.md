# Authentik

Authentik is the centralized identity provider for the homelab, handling SSO via forward-auth (for arr apps and Homepage) and native OIDC (for Grafana and ArgoCD).

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

Apps that lack native SSO support are protected via Authentik's embedded outpost using forward-auth. When a user visits a protected app, the gateway checks the session with Authentik before allowing access.

```
User -> Cilium Gateway -> forward-auth -> Authentik outpost
                       |                        |
                       |<-- 200 (authenticated) -|
                       |-> proxy to backend app
```

**Protected apps:** Sonarr, Radarr, Prowlarr, Bazarr, Tdarr, qBittorrent, Homepage

### Native OIDC

Apps with built-in OAuth2/OIDC support authenticate directly with Authentik as an identity provider.

**OIDC apps:** Grafana, ArgoCD

### Unprotected (with rationale)

- **Jellyfin** -- has its own user auth; media clients (Roku, Apple TV, mobile) can't do browser-based SSO
- **Prometheus/Alertmanager** -- internal monitoring; forward-auth would break Grafana datasource scraping

## Key Configuration

- PostgreSQL persistence via `nfs-client` (5Gi)
- Redis in standalone mode with `nfs-client` persistence (1Gi)
- HTTPRoute at `auth.homelab.local` via the `homelab-gateway` with TLS via `homelab-ca-issuer`
- Outpost cookie domain: `.homelab.local` (enables cross-subdomain SSO sessions)
- Forward-auth uses the embedded outpost's internal service URL (`http://ak-outpost-authentik-embedded-outpost.auth.svc.cluster.local:9000/...`)

## Secrets

| Secret | Namespace | Keys |
|--------|-----------|------|
| `authentik-credentials` | `auth` | `secret-key`, `postgresql-password`, `bootstrap-password`, `bootstrap-token` |
| `grafana-oidc-secret` | `monitoring` | `GRAFANA_OIDC_CLIENT_SECRET` |
| `argocd-secret` (merge) | `argocd` | `oidc.authentik.clientSecret` |

All managed via External Secrets Operator (synced from Vault). See the corresponding `*-external-secret.yml` manifests for the full key structure.

## Post-Deploy Setup

Prerequisites: Authentik pods running in `auth` namespace, `auth.homelab.local` DNS configured in UniFi gateway, secrets populated in Vault.

1. Navigate to `https://auth.homelab.local/if/flow/initial-setup/` and set the `akadmin` password.
2. Log in to the admin interface at `https://auth.homelab.local/if/admin/`.
3. Create a **Kubernetes Service-Connection** in System > Outpost Integrations (name: `local-cluster`, leave kubeconfig empty).
4. Edit the **authentik Embedded Outpost** -- set integration to `local-cluster`. In Advanced settings, set `authentik_host` to `https://auth.homelab.local` and `authentik_host_browser` to `https://auth.homelab.local`.
5. Create a **Proxy Provider** (Applications > Providers):
    - Name: `homelab-forward-auth`
    - Mode: **Forward auth (domain level)**
    - External host: `https://auth.homelab.local`
    - Cookie domain: `homelab.local`
6. Create an **Application** (name: `Homelab Forward Auth`, provider: `homelab-forward-auth`).
7. Edit the embedded outpost, add the `Homelab Forward Auth` application.
8. Create **OAuth2/OpenID Provider** for Grafana (client ID: `grafana`, redirect URI: `https://grafana.homelab.local/login/generic_oauth`). Write the client secret to Vault:

    ```bash
    vault kv put homelab/infrastructure/grafana-oidc \
      GRAFANA_OIDC_CLIENT_SECRET=your_client_secret
    ```

9. Create **OAuth2/OpenID Provider** for ArgoCD (client ID: `argocd`, redirect URI: `https://argocd.homelab.local/auth/callback`). Write the client secret to Vault:

    ```bash
    vault kv put homelab/infrastructure/argocd-oidc \
      oidc.authentik.clientSecret=your_client_secret
    ```

10. The built-in `authentik Admins` group maps to Grafana Admin and ArgoCD `role:admin`. Ensure your user is a member.
12. Create additional user accounts in Directory > Users as needed.

## Backups

The `auth` namespace is included in the Velero daily stateful backup schedule. The weekly full-cluster backup (`"*"`) also covers it.
