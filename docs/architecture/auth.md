# Authentication & SSO

The homelab uses Authentik as the centralized identity provider. Applications authenticate through native OIDC, by routing their traffic through Authentik's embedded outpost, or, for Jellyfin, by checking passwords against Authentik's LDAP outpost.

## Authentication Flows

```mermaid
flowchart TB
    subgraph authNS ["auth namespace"]
        AuthentikServer["Authentik Server"]
        AuthentikWorker["Authentik Worker"]
        PostgreSQL["PostgreSQL"]
        LDAPOutpost["LDAP Outpost"]
        AuthentikServer --> PostgreSQL
        AuthentikWorker --> PostgreSQL
        LDAPOutpost --> AuthentikServer
    end

    User["User"] --> Gateway["Cilium Gateway"]
    Gateway --> Outpost["Authentik Outpost"]
    Outpost --> ProtectedApps["*arr apps, qBittorrent, Tdarr,<br/>Goldilocks, Prometheus,<br/>Alertmanager<br/>(auth at the edge)"]
    Outpost --> AuthentikServer
    Gateway --> UnprotectedApps["Homepage, Vault,<br/>Uptime Kuma<br/>(no auth at the edge)"]

    Grafana["Grafana"] -->|"OIDC"| AuthentikServer
    ArgoCD["ArgoCD"] -->|"OIDC"| AuthentikServer
    Gateway --> Jellyfin["Jellyfin<br/>(own login page)"]
    Jellyfin -->|"LDAP bind"| LDAPOutpost
```

Authentik runs its server and worker against a bundled PostgreSQL instance. No Redis is deployed; the task queue lives in PostgreSQL.

### Proxied Auth

Tdarr, Goldilocks, Sonarr, Radarr, Prowlarr, Bazarr, qBittorrent, Prometheus and Alertmanager route through the embedded outpost, which authenticates the browser before proxying to the app. The outpost dispatches on the `Host` header, so one instance serves every protected app. Each app declares a proxy-mode provider in `infrastructure/authentik/blueprints-configmap.yml`.

Because the outpost originates the proxied request, it needs its own network path to each backend -- ingress on the app's namespace and egress from `auth`. Without both, the browser gets the login redirect and then hangs. See the [runbook](../runbooks/adding-app-to-sso.md).

Grafana reads Prometheus and Alertmanager over their in-cluster Services, so proxying their web UIs does not affect scraping or dashboards.

The *arr apps and qBittorrent exempt `/api/`, `/feed/` and `/ping` from the proxy via `skip_path_regex`, because mobile and scripted clients cannot complete a browser login. These paths depend on each application's own authentication. The *arr APIs use API keys; qBittorrent uses its Web API session authentication. Verify unauthorized access fails per application rather than assuming every endpoint returns `401`.

!!! warning "Still open on the LAN"
    **Reachable with no edge auth: Homepage, Vault and Uptime Kuma.** Their native controls remain the access boundary. Vault keeps an independent recovery login because Authentik's credentials also depend on Vault and External Secrets.

### Native OIDC

Apps with built-in OAuth2/OIDC support authenticate directly with Authentik. Each gets its own OAuth2 provider and application in Authentik, with a dedicated client ID and secret.

- **Grafana** -- `auth.generic_oauth` with role mapping (`authentik Admins` group -> Admin role)
- **ArgoCD** -- native OIDC via `oidc.config` in `argocd-cm` with RBAC group mapping

Grafana's token and userinfo URLs use the internal Service over HTTP, with Cilium policies controlling reachability. Its browser authorization URL uses the external hostname. ArgoCD uses the external HTTPS issuer, trusted through its image's system root store; it does not use Grafana's split URL configuration.

### LDAP

Jellyfin's TV and mobile clients send a username and password to Jellyfin, so neither the proxy outpost nor an OIDC redirect can sit in front of them. Jellyfin's LDAP Authentication plugin checks those credentials against the `authentik-ldap` outpost in `auth` instead. People sign in to Jellyfin with their Authentik account, and the plugin creates the Jellyfin user on first sign-in.

The plugin searches the directory with the `jellyfin-ldap-bind` service account, then binds as the person signing in. Binds run Authentik's `default-authentication-flow`; MFA support is off, so an account that requires a WebAuthn or TOTP challenge at login cannot bind. Members of `Jellyfin Users` can sign in, and members of `authentik Admins` among them become Jellyfin administrators.

Seerr signs people in through Jellyfin, so the same Authentik accounts work there.

Jellyfin's local administrator does not go through LDAP. It is Arrchitect's account and the emergency login, and its username must not match any Authentik username.

!!! info "Plaintext inside the cluster"
    The outpost serves LDAP without TLS on its in-cluster Service, so bind passwords cross pod-to-pod traffic unencrypted, as Vault's internal traffic does. Cilium admits only the Jellyfin pod.

### Unprotected Services

| Service | Reason |
|---------|--------|
| Homepage | No edge auth; exposes service links and operational widget data to the LAN |
| Vault | Cannot use Authentik -- Authentik's own secrets come from Vault, so this would be circular. Token auth is the control |
| Uptime Kuma | No edge auth; has its own login |
| Authentik | Circular dependency |

## Group-Based Access Control

| Group | Grafana Role | ArgoCD Role | Jellyfin |
|-------|-------------|-------------|----------|
| `authentik Admins` | Admin | `role:admin` | Administrator, when also in `Jellyfin Users` |
| `Jellyfin Users` | -- | -- | User |
| (default) | Viewer | No default role explicitly granted in this repository | No access |

## Resilience

An Authentik server, outpost or PostgreSQL outage can make every proxy-protected route unavailable. The outpost is part of the request path even for API paths exempted from login. Grafana and ArgoCD retain local login accounts; direct-route services retain their own authentication. See the [emergency bypass runbook](../runbooks/authentik-emergency-bypass.md) for scoped port-forward access during recovery.

An Authentik server or LDAP outpost outage blocks new Jellyfin sign-ins. Jellyfin issues its own session tokens, so devices already signed in keep playing. The local Jellyfin administrator still signs in.

The `auth` namespace is included in Velero's daily stateful backup and the weekly full-cluster backup.
