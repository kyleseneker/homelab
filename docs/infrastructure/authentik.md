# Authentik

Authentik provides identity for native OIDC clients and authenticates browser traffic through its proxy outpost.

## Details

| Field | Value |
|-------|-------|
| Chart | `authentik` |
| Repository | <https://charts.goauthentik.io> |
| Version | 2026.2.1 |
| Namespace | `auth` |

## Architecture

The server and worker use bundled PostgreSQL with a 5Gi `nfs-client` PVC. This chart deploys no Redis. A single PostgreSQL instance and the outpost are availability dependencies; a PodDisruptionBudget does not make them redundant.

### Proxy Authentication

The public HTTPRoute points to `ak-outpost-authentik-embedded-outpost` in `auth` on port 9000. The outpost authenticates the browser and forwards the request to the provider's internal Service URL:

```text
Browser -> Cilium Gateway -> Authentik outpost -> backend Service
                                  |
                             Authentik login
```

**Protected web routes:** Sonarr, Radarr, Prowlarr, Bazarr, Tdarr, qBittorrent, Goldilocks, Prometheus and Alertmanager.

`blueprints-configmap.yml` declares one provider in `proxy` mode and one application for each route, and owns the complete provider assignment on the existing outpost. Forward-auth mode expects an auth subrequest from the gateway and is not used here. The blueprint must not depend on a manually created `homelab-forward-auth` provider.

The *arr and qBittorrent proxy providers exempt API/feed/ping paths from browser login. Their native authentication must remain enabled. The outpost is still in their network path. A successful login redirect proves the auth entry point is reachable; it does not prove the backend is healthy.

Cross-namespace HTTPRoutes require `referencegrant.yml`. Cilium must permit both outpost egress and backend ingress. See [Adding an App to SSO](../runbooks/adding-app-to-sso.md).

### Native OIDC and Direct Routes

Grafana and ArgoCD authenticate with dedicated OIDC providers. Grafana accesses token/userinfo endpoints over the internal Service; ArgoCD uses the external HTTPS issuer with the homelab CA. Both retain local administrator login for recovery.

Jellyfin and Seerr use their media login flow. Homepage, Vault, OpenClaw and Uptime Kuma have direct routes with the native controls described in [Authentication & SSO](../architecture/auth.md). Grafana's internal Prometheus and Alertmanager data sources use Services directly, so protecting the public web routes does not interrupt metrics queries.

## Secrets

| Secret | Namespace | Keys |
|--------|-----------|------|
| `authentik-credentials` | `auth` | Authentik environment variables and PostgreSQL credentials; see the ExternalSecret manifest |
| `grafana-oidc-secret` | `monitoring` | `GRAFANA_OIDC_CLIENT_SECRET` |
| `argocd-secret` (merge) | `argocd` | `oidc.authentik.clientSecret` |

External Secrets Operator syncs these from Vault. Bootstrap credentials initialize the first account; changing a bootstrap environment variable does not serve as an ongoing password rotation mechanism.

## Post-Deploy Setup

Prerequisites: Authentik pods running in `auth`, DNS configured, and credentials populated in Vault.

1. Sign in to `https://auth.homelab.local/if/admin/` with the bootstrapped administrator account. Use the initial setup flow only if the installation has not initialized an account.
2. Confirm the `edge-auth.yaml` blueprint applies successfully and all nine providers exist in proxy mode. ConfigMap data keys must end in `.yaml`.
3. Verify the outpost integration and the Service referenced by the routes exist. Set its browser-facing Authentik URL to `https://auth.homelab.local` and verify the blueprint's provider assignments. The repository does not yet declare the integration setup or outpost host configuration.
4. Create or verify the Grafana OAuth2 provider (`client_id: grafana`, redirect URI `https://grafana.homelab.local/login/generic_oauth`) and ArgoCD provider (`client_id: argocd`, redirect URI `https://argocd.homelab.local/auth/callback`). These OIDC provider definitions are not yet part of the blueprint.
5. Store each client secret at its corresponding Vault path using `make vault-put-secret`; the ExternalSecret manifests identify the paths and keys. Ensure token claims contain the `authentik Admins` group expected by both clients.
6. Test a fresh browser login, native OIDC role mapping, an unauthenticated API request, and backend reachability separately. The [SSO runbook](../runbooks/adding-app-to-sso.md) gives the network checks.

## Recovery and Backups

`authentik-backup` runs at 01:45 UTC, creating a custom-format PostgreSQL dump on the `authentik-backups` NFS PVC. It publishes the archive only after `pg_dump` and archive-list validation succeed. A holder Deployment keeps it mounted for daily MinIO and weekly S3 backups. Alerts cover a missing/stale successful dump and an unavailable holder.

An S3 copy has been restored into empty lab PostgreSQL with source/restored table and key object counts matching. See [the recovery procedure and evidence](../runbooks/backup-and-restore.md#authentik-postgresql-recovery). Preserve `AUTHENTIK_SECRET_KEY` separately and test application/OIDC recovery before declaring identity recovery complete; the raw live PostgreSQL volume is not the logical recovery method.

During an Authentik outage, proxy routes can fail. Use the [emergency bypass runbook](../runbooks/authentik-emergency-bypass.md) for local admin login and loopback port-forwarding without changing public routes.
