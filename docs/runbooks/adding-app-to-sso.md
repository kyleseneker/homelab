# Adding an App to SSO

How to protect a new application behind Authentik SSO.

## Forward Auth (apps without native SSO)

For apps that don't support OIDC/OAuth2 natively, use nginx-ingress forward-auth. The domain-level proxy provider handles all `*.homelab.local` subdomains, so you only need to add annotations.

### 1. Add Ingress Annotations

In the app's `values.yaml`, add these annotations to the ingress section:

```yaml
ingress:
  main:
    annotations:
      nginx.ingress.kubernetes.io/auth-url: "http://ak-outpost-authentik-embedded-outpost.auth.svc.cluster.local:9000/outpost.goauthentik.io/auth/nginx"
      nginx.ingress.kubernetes.io/auth-signin: "https://auth.homelab.local/outpost.goauthentik.io/start?rd=$scheme://$http_host$request_uri"
      nginx.ingress.kubernetes.io/auth-response-headers: "Set-Cookie,X-authentik-username,X-authentik-groups,X-authentik-email"
      nginx.ingress.kubernetes.io/auth-snippet: |
        proxy_set_header X-Forwarded-Host $http_host;
```

### 2. Commit and Push

ArgoCD will sync the updated ingress with the new annotations.

### 3. Test

Visit the app's URL. You should be redirected to Authentik's login page. After authenticating, you'll be redirected back to the app.

## Native OIDC (apps with built-in support)

For apps that support OAuth2/OIDC natively (e.g., Grafana, ArgoCD, Jellyseerr).

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
- **Monitoring backends** (Prometheus, Alertmanager) -- forward-auth would break internal scraping from Grafana datasources
- **Authentik itself** -- circular dependency
