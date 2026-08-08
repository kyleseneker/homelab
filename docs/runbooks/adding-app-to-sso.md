# Adding an App to SSO

How to protect a new application behind Authentik SSO.

## Forward Auth (apps without native SSO)

!!! danger "No forward-auth path exists today"
    Forward auth used to work through `ingress-nginx` `auth_request` annotations. `ingress-nginx` was removed when every app moved to Gateway API HTTPRoutes, and nothing replaced it. There is no annotation you can add to an HTTPRoute to protect an app.

    Until an ext_authz filter is wired through Cilium's Envoy, an app without native OIDC **cannot** be put behind SSO. Treat any such app as open on the LAN. Tracked as [K21](../roadmap/assessment.md).

## Native OIDC (apps with built-in support)

For apps that support OAuth2/OIDC natively (e.g., Grafana, ArgoCD, Seerr).

### 1. Create OIDC Provider in Authentik

1. Go to **Applications > Providers** in the Authentik admin UI
2. Create a new **OAuth2/OpenID Provider**
   - Set client ID, generate client secret
   - Set redirect URI to the app's OAuth callback URL
   - Scopes: `openid`, `email`, `profile`
3. Create a matching **Application** linked to the provider

### 2. Store the Client Secret in Vault

1. Write the client secret to Vault: `vault kv put homelab/infrastructure/<app>-oidc <key>=<client_secret>`
2. Create an ExternalSecret manifest referencing the Vault path and commit it

### 3. Configure the App

Add the OIDC configuration to the app's Helm values or configuration, using:

- **`auth_url`** (browser redirect): `https://auth.homelab.local/application/o/authorize/`
- **`token_url`** (server-to-server): `http://authentik-server.auth.svc.cluster.local/application/o/token/`
- **`api_url`** (server-to-server): `http://authentik-server.auth.svc.cluster.local/application/o/userinfo/`

The split between external and internal URLs avoids TLS trust issues with the homelab CA for server-to-server communication.

## When NOT to Add SSO

- **Media clients** (Jellyfin) -- Roku, Apple TV, and mobile apps can't do browser-based SSO
- **Monitoring backends** (Prometheus, Alertmanager) -- edge auth would break internal scraping from Grafana datasources
- **Authentik itself** -- circular dependency
