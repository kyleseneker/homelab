# Adding an App to SSO

How to protect a new application behind Authentik SSO.

## Forward Auth (apps without native SSO)

An HTTPRoute has no annotation that triggers an auth subrequest, so protection comes from routing traffic *through* Authentik's embedded outpost instead. The outpost is an ordinary Service: the HTTPRoute points at it, it authenticates the browser, then proxies to the app. It dispatches on the `Host` header, so one outpost serves every protected app.

This needs a proxy provider in **`proxy`** mode. A provider in `forward_domain` mode expects the gateway to make an auth subrequest and will not work here.

### 1. Declare the provider in the blueprint

Add a provider and application to `infrastructure/authentik/blueprints-configmap.yml`. Keys in that ConfigMap must end in `.yaml` -- authentik ignores `.yml`, and the blueprint will silently never apply.

Set `internal_host` to the app's in-cluster Service URL and `external_host` to its public hostname. Re-assert the outpost's full provider list, including the providers already on it, because the list is replaced rather than merged.

### 2. Point the HTTPRoute at the outpost

Replace the route's `backendRefs` with the outpost Service in the `auth` namespace on port 9000. A backendRef that crosses namespaces needs a matching `ReferenceGrant` in `auth`, or the route reports `ResolvedRefs=False` and the gateway serves a 500.

### 3. Allow the outpost to reach the app

The outpost now originates the request, so it needs a network path the gateway previously had:

- ingress on the app's namespace allowing the `auth` namespace on the app's port
- egress from `auth` to that pod and port

Both are required. Miss either and the browser reaches the outpost, gets its login redirect, then hangs until the proxy times out -- the redirect is issued before the outpost ever contacts the backend, so an unreachable app looks identical to a working one until the moment it stalls.

Cilium matches the **pod** port, not the Service port. Check `targetPort` before writing the rule.

### 4. Verify

An unauthenticated request must answer `302` toward `/outpost.goauthentik.io/start` quickly. Confirm the backend hop separately, because the redirect alone does not prove the app is reachable:

```sh
kubectl -n auth exec deploy/authentik-server -- \
  curl -sS -o /dev/null -m 10 -w '%{http_code} %{time_total}s\n' http://<app>.<ns>.svc.cluster.local:<port>/
```

A time near the timeout means a policy is still blocking the path.

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
