# ADR-010: Authentik for SSO

## Status

Accepted

## Context

Multiple web applications need authentication. Without centralized SSO, each application manages its own user accounts, requiring separate logins and independent credential management.

## Decision

Use Authentik as the centralized identity provider with two authentication mechanisms: a proxy-mode outpost for applications without native SSO support, and OIDC for applications that support it natively.

## Alternatives Considered

- **Authelia**: Lightweight authenticating proxy. Simpler than Authentik but limited to proxying -- no native OIDC provider capability without external dependencies.
- **Keycloak**: Enterprise-grade identity provider. Feature-rich but heavyweight (Java-based, higher resource consumption). More complexity than a homelab needs.
- **No SSO**: Each app manages its own auth. Workable but tedious with 15+ applications.

## Rationale

- **Dual auth modes**: The outpost handles apps without native SSO (the \*arr stack, qBittorrent, Tdarr, Goldilocks, Prometheus, Alertmanager). OIDC handles apps that support it natively (Grafana, ArgoCD). One tool covers both patterns.
- **Routing, not annotations**: An HTTPRoute has no equivalent to a subrequest auth hook, so a protected app's route points at the outpost Service and the outpost proxies to the app after authenticating. It dispatches on the `Host` header, so one outpost serves every protected app and no ext_authz filter is required.
- **Single domain cookie**: The embedded outpost sets a cookie scoped to `homelab.local`, enabling single sign-on across all subdomains without re-authentication.
- **Group-based RBAC**: Authentik groups map to application roles (e.g., ArgoCD `role:admin`), centralizing access control.
- **Lightweight deployment**: Single replica with PostgreSQL. Lower resource footprint than Keycloak.

## Consequences

- If Authentik is unavailable, every proxied application becomes inaccessible at the edge, because the outpost is in the request path rather than beside it. OIDC-integrated apps fall back to their own login. In-cluster traffic is unaffected, so the operator, Prowlarr's sync and Grafana's datasources keep working.
- The outpost originates the proxied request, so each protected app needs a network path from the `auth` namespace as well as from the gateway. Missing either direction produces a login redirect followed by a hang rather than a clear error.
- Vault is deliberately excluded: Authentik reads its own credentials from Vault through External Secrets, so protecting Vault with Authentik would deadlock an unseal. Jellyfin is excluded because media clients cannot complete a browser login.
- Emergency bypass procedure is documented in a dedicated runbook for SSO lockout scenarios.
- Authentik is a stateful service (PostgreSQL) that must be included in the cluster backup strategy.
