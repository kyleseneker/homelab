# ADR-007: Authentik for SSO

## Status

Accepted

## Context

Multiple web applications need authentication. Without centralized SSO, each application manages its own user accounts, requiring separate logins and independent credential management.

## Decision

Use Authentik as the centralized identity provider with two authentication mechanisms: forward-auth proxy for applications without native SSO support, and OIDC for applications that support it natively (Grafana, ArgoCD).

## Alternatives Considered

- **Authelia**: Lightweight forward-auth proxy. Simpler than Authentik but limited to forward-auth only -- no native OIDC provider capability without external dependencies.
- **Keycloak**: Enterprise-grade identity provider. Feature-rich but heavyweight (Java-based, higher resource consumption). More complexity than a homelab needs.
- **No SSO**: Each app manages its own auth. Workable but tedious with 15+ applications.

## Rationale

- **Dual auth modes**: Forward-auth handles apps without native SSO (arr stack, Homepage). OIDC handles apps that support it natively (Grafana, ArgoCD). One tool covers both patterns.
- **Single domain cookie**: The embedded outpost sets a cookie scoped to `homelab.local`, enabling single sign-on across all subdomains without re-authentication.
- **Group-based RBAC**: Authentik groups map to application roles (e.g., Grafana Admin, ArgoCD `role:admin`), centralizing access control.
- **Lightweight deployment**: Single replica with PostgreSQL and Redis. Lower resource footprint than Keycloak.

## Consequences

- If Authentik is unavailable, forward-auth-protected applications become inaccessible. OIDC-integrated apps (Grafana, ArgoCD) fall back to local login.
- Emergency bypass procedure is documented in a dedicated runbook for SSO lockout scenarios.
- Authentik is backed up daily via Velero (auth namespace).
