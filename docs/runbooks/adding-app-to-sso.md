# Adding an App to SSO

How to protect a new application behind Authentik SSO.

## Proxy Mode (apps without native SSO)

An HTTPRoute has no annotation that triggers an auth subrequest, so protection comes from routing traffic *through* Authentik's embedded outpost instead. The outpost is an ordinary Service: the HTTPRoute points at it, it authenticates the browser, then proxies to the app. It dispatches on the `Host` header, so one outpost serves every protected app.

This needs a proxy provider in **`proxy`** mode. A provider in `forward_domain` mode expects the gateway to make an auth subrequest and will not work here.

### 1. Declare the provider in the blueprint

Add a provider and application to `infrastructure/authentik/blueprints-configmap.yml`. Keys in that ConfigMap must end in `.yaml` -- authentik ignores `.yml`, and the blueprint will silently never apply.

Set `internal_host` to the app's in-cluster Service URL and `external_host` to `https://<app>.home.seneker.io`. A provider answers on that one hostname only. Re-assert the outpost's full provider list, including the providers already on it, because the list is replaced rather than merged.

### 2. Point the HTTPRoute at the outpost

Attach the route to the gateway's `https-home` listener with the `<app>.home.seneker.io` hostname, and add a UniFi DNS record for it pointing to the gateway VIP. Replace the route's `backendRefs` with the outpost Service in the `auth` namespace on port 9000. A backendRef that crosses namespaces needs a matching `ReferenceGrant` in `auth`, or the route reports `ResolvedRefs=False` and the gateway serves a 500.

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

Add the app's URL to the `sso-protected` Probe in `infrastructure/blackbox-exporter/probes.yml`, so a missing login redirect alerts.

## Native OIDC (apps with built-in support)

For apps that support OAuth2/OIDC natively (for example, Grafana and ArgoCD).

### 1. Store the Client Secret in Vault

1. Generate a client secret and write it to Vault: `vault kv put homelab/infrastructure/<app>-oidc <key>=<client_secret>`
2. Add it to `infrastructure/authentik/authentik-external-secret.yml` as `<APP>_OIDC_CLIENT_SECRET`, and create the app's own ExternalSecret from the same Vault path. Both sides then read one value.

### 2. Declare the Provider in the Blueprint

Add an OAuth2 provider and an application to the `oidc-clients.yaml` key of `infrastructure/authentik/blueprints-configmap.yml`, following the Grafana and ArgoCD entries:

- a confidential client with `client_secret: !Env <APP>_OIDC_CLIENT_SECRET`
- a strict redirect URI on the app's `home.seneker.io` callback
- the `openid`, `email` and `profile` scope mappings, found by their managed names

### 3. Configure the App

Add the OIDC configuration to the app's Helm values or configuration, using:

- **`auth_url`** (browser redirect): `https://auth.home.seneker.io/application/o/authorize/`
- **`token_url`** (server-to-server): `http://authentik-server.auth.svc.cluster.local/application/o/token/`
- **`api_url`** (server-to-server): `http://authentik-server.auth.svc.cluster.local/application/o/userinfo/`

This split is used by Grafana and requires Cilium egress to Authentik and ingress on the server's port. ArgoCD discovers endpoints from its external issuer on `auth.home.seneker.io` instead, verified against the system roots. Prefer HTTPS with verified trust when the application supports it.

## When NOT to Add SSO

- **Media clients** (Jellyfin) -- Roku, Apple TV, and mobile apps can't do browser-based SSO
- **Internal metrics traffic** -- keep Grafana and scrapers on in-cluster Services; their public Prometheus and Alertmanager web routes are already proxy-protected
- **Authentik itself** -- circular dependency
