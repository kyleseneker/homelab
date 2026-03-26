# FlareSolverr

FlareSolverr is a proxy server that bypasses Cloudflare and DDoS-GUARD protection by running a headless browser (Chromium) to solve challenges automatically. Prowlarr uses it as an indexer proxy so that protected trackers can be queried without manual intervention.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/flaresolverr/flaresolverr:v3.4.6` |
| Port | 8191 |
| HTTPRoute | -- (internal only) |
| Namespace | `arr` |
| ArgoCD app | `arr-flaresolverr` |
| Sync wave | 1 |
| Internal URL | `http://arr-flaresolverr.arr.svc.cluster.local:8191` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 100m | 256Mi |
| Limits | -- | 512Mi |

## Key Configuration

- Timezone injected from ConfigMap `arr-env`.
- `LOG_LEVEL` set to `info` (options: `debug`, `info`, `warn`, `error`).
- Stateless -- no persistent storage required.
- No ingress -- accessed only by Prowlarr via in-cluster service DNS.
- Liveness, readiness, and startup probes are enabled.
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.

## Post-Deploy Setup

FlareSolverr itself requires no configuration. To connect it to Prowlarr:

1. Open `https://prowlarr.homelab.local`.
2. Go to **Settings > Indexers**.
3. Click **+** and select **FlareSolverr**.
4. Set the **Tag** (e.g., `flaresolverr`) and the **Host**: `http://arr-flaresolverr.arr.svc.cluster.local:8191`.
5. Save.
6. On any indexer that requires Cloudflare solving, add the `flaresolverr` tag.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Prowlarr | Sends captcha-protected requests through FlareSolverr |

## Upstream

- [https://github.com/FlareSolverr/FlareSolverr](https://github.com/FlareSolverr/FlareSolverr)
