# Authentik

Authentik provides identity for native OIDC clients and authenticates browser traffic through its proxy outpost.

## Details

| Field | Value |
|-------|-------|
| Chart | `authentik` |
| Repository | <https://charts.goauthentik.io> |
| Version | 2026.8.5 |
| Namespace | `auth` |

## Architecture

The server and worker use bundled PostgreSQL with a 5Gi `nfs-client` PVC. This chart deploys no Redis. A single PostgreSQL instance and the outpost are availability dependencies; a PodDisruptionBudget does not make them redundant.

`values.yml` pins the bundled PostgreSQL image to `17.11-bookworm`. Chart 2026.8 defaults to a Debian 13 (trixie) image, whose newer glibc changes the `en_US.utf8` collation the database was created with (version 2.36) and would require a full reindex. Change the base image only as a planned step that refreshes the collation version. The subchart's Bitnami FIPS setting is turned off because the official image does not use it.

### Upgrades

Upgrade one minor release at a time (2026.2 → 2026.5 → 2026.8), as upstream requires, with a fresh `authentik-backup` dump before each step. The worker applies migrations and blueprints on startup. Afterwards, check that every blueprint instance is `successful`, that the OIDC issuers still report `https://`, and that the blackbox probes for proxied routes still return their login redirect. Since 2026.8, Authentik honors forwarded headers only from `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS`; the defaults cover the pod and node networks the Cilium Gateway connects from.

PostgreSQL stays on the major version the Authentik chart defaults to (17 through chart 2026.8.5), and Renovate holds it there. Change the major as part of the Authentik upgrade whose chart moves to it, by dump and restore: a data directory from an older major does not start on a newer server.

1. Rehearse in the restore lab. Its `authentik-database` starts from a fresh PVC and sets `PGDATA` explicitly, so the 18 image's new default data path does not apply.
2. Scale the server and worker to 0 and take a final `pg_dump`.
3. Move `/bitnami/postgresql/data` aside on the same PVC, so the new image initializes an empty directory. The chart sets `PGDATA` explicitly, so the new default path does not apply here either.
4. Bump `backup.yml` to the same major in the same change. `pg_dump` refuses to dump a newer server.
5. Restore with `pg_restore`, run `ANALYZE`, then scale back up.

The new cluster is also the point to move from bookworm to trixie, since a restore builds every index under the new collation.

The **Base URL** system setting holds `https://auth.home.seneker.io`. Authentik 2026.11 refuses to start without it; `AUTHENTIK_WEB__BASE_URL` in `values.yml` seeds it on a fresh install and is ignored once the setting has a value.

### Proxy Authentication

The public HTTPRoute points to `ak-outpost-authentik-embedded-outpost` in `auth` on port 9000. The outpost authenticates the browser and forwards the request to the provider's internal Service URL:

```text
Browser -> Cilium Gateway -> Authentik outpost -> backend Service
                                  |
                             Authentik login
```

**Protected web routes:** Sonarr, Radarr, Prowlarr, Bazarr, Tdarr, qBittorrent, Goldilocks, Prometheus and Alertmanager.

`blueprints-configmap.yml` declares one provider in `proxy` mode and one application for each route. It also owns the outpost's complete provider assignment and its Authentik URLs, `https://auth.home.seneker.io` for both the API and browser redirects. Forward-auth mode expects an auth subrequest from the gateway and is not used here. The blueprint must not depend on a manually created `homelab-forward-auth` provider.

A proxy provider answers on exactly one hostname, its `external_host`. The protected routes use their `home.seneker.io` names, and `gateway/homelab-local-redirects.yml` redirects the old `homelab.local` names to them.

The *arr and qBittorrent proxy providers exempt API/feed/ping paths from browser login. Their native authentication must remain enabled. The outpost is still in their network path. A successful login redirect proves the auth entry point is reachable; it does not prove the backend is healthy.

Cross-namespace HTTPRoutes require `referencegrant.yml`. Cilium must permit both outpost egress and backend ingress. See [Adding an App to SSO](../runbooks/adding-app-to-sso.md).

### Native OIDC and Direct Routes

Grafana and ArgoCD authenticate with dedicated OIDC providers, declared in the `oidc-clients.yaml` blueprint. The blueprint reads each client secret from `authentik-credentials` through `!Env`, so Authentik and the client share one Vault value. Grafana accesses token/userinfo endpoints over the internal Service. ArgoCD uses the external issuer `https://auth.home.seneker.io/application/o/argocd/` and trusts it through the system roots. Both retain local administrator login for recovery.

Each provider allows both the `homelab.local` and `home.seneker.io` callbacks. The issuer follows the hostname the client calls, so a client's configured issuer must match the Authentik name it uses. ArgoCD caches the issuer for session checks: after changing `oidc.config`, restart `argocd-server`, or every sign-in loops back to the login page.

Jellyfin and Seerr use their media login flow. Homepage, Vault and Uptime Kuma have direct routes with the native controls described in [Authentication & SSO](../architecture/auth.md). Grafana's internal Prometheus and Alertmanager data sources use Services directly, so protecting the public web routes does not interrupt metrics queries.

## Secrets

| Secret | Namespace | Keys |
|--------|-----------|------|
| `authentik-credentials` | `auth` | Authentik environment variables, PostgreSQL credentials and the OIDC client secrets the blueprint reads; see the ExternalSecret manifest |
| `grafana-oidc-secret` | `monitoring` | `GRAFANA_OIDC_CLIENT_SECRET` |
| `argocd-secret` (merge) | `argocd` | `oidc.authentik.clientSecret` |

External Secrets Operator syncs these from Vault. Bootstrap credentials initialize the first account; changing a bootstrap environment variable does not serve as an ongoing password rotation mechanism.

## Post-Deploy Setup

Prerequisites: Authentik pods running in `auth`, DNS configured, and credentials populated in Vault.

1. Store each OIDC client secret at its Vault path using `make vault-put-secret` before the first start, because the `oidc-clients.yaml` blueprint reads them when it imports. The ExternalSecret manifests identify the paths and keys.
2. Sign in to `https://auth.home.seneker.io/if/admin/` with the bootstrapped administrator account. Use the initial setup flow only if the installation has not initialized an account.
3. Confirm the `edge-auth.yaml` and `oidc-clients.yaml` blueprints apply successfully, all nine providers exist in proxy mode, and the Grafana and ArgoCD providers exist. ConfigMap data keys must end in `.yaml`.
4. Verify the outpost integration and the Service referenced by the routes exist. The repository does not declare the integration setup.
5. Ensure token claims contain the `authentik Admins` group expected by both OIDC clients.
6. Test a fresh browser login, native OIDC role mapping, an unauthenticated API request, and backend reachability separately. The [SSO runbook](../runbooks/adding-app-to-sso.md) gives the network checks.

## Recovery and Backups

`authentik-backup` runs at 01:45 UTC, creating a custom-format PostgreSQL dump on the `authentik-backups` NFS PVC. It publishes the archive only after `pg_dump` and archive-list validation succeed. A holder Deployment keeps it mounted for daily Garage and weekly S3 backups. Alerts cover a missing/stale successful dump and an unavailable holder.

An S3 copy has been restored into empty lab PostgreSQL with source/restored table and key object counts matching. See [the recovery procedure and evidence](../runbooks/backup-and-restore.md#authentik-postgresql-recovery). Emergency administrator login and the restored ArgoCD provider’s OIDC code exchange also passed with an isolated lab callback. Preserve `AUTHENTIK_SECRET_KEY` separately; ordinary login/MFA, real clients and proxy/worker recovery remain unverified. The raw live PostgreSQL volume is not the logical recovery method.

During an Authentik outage, proxy routes can fail. Use the [emergency bypass runbook](../runbooks/authentik-emergency-bypass.md) for local admin login and loopback port-forwarding without changing public routes.
