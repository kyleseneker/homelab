# Media Operator

A Kubernetes operator that reconciles Sonarr, Radarr, Prowlarr, Jellyfin, and qBittorrent configuration from custom resources. It moves the *arr stack's runtime state -- root folders, download clients, indexers, quality settings -- out of each app's SQLite database and into Git.

## Details

| Property | Value |
|----------|-------|
| Charts | `media-operator-servarr`, `media-operator-downloads` |
| Repository | `ghcr.io/kyleseneker/media-operator` (OCI) |
| Version | 0.4.0 |
| Namespace | `arr` |
| ArgoCD apps | `media-operator`, `media-operator-downloads` |
| Watch namespace | `arr` |
| API group | `media-operator.dev/v1alpha1` |

Two operators are deployed: the servarr operator handles the *arr applications and Jellyfin, the downloads operator handles qBittorrent.

## Custom Resources

The CRs live in `k8s/clusters/homelabk8s01/apps/arr/media-config/`, deployed as the `arr-media-config` Application.

| Kind | Configures |
|------|-----------|
| `SonarrConfig` | Root folders, download clients, download-client behaviour |
| `RadarrConfig` | Root folders, download clients, download-client behaviour |
| `ProwlarrConfig` | Indexers, applications to sync to, indexer proxies |
| `JellyfinConfig` | Libraries and server settings |
| `QBittorrentConfig` | Categories, save paths, connection settings |

Each CR points at its application's in-cluster service and reads that application's API key from the `arr-api-keys` Secret:

```yaml
spec:
  connection:
    url: http://arr-sonarr.arr.svc.cluster.local:8989
    apiKeySecretRef:
      name: arr-api-keys
      key: sonarr-api-key
  reconcile:
    interval: 5m
    deletionPolicy: orphan
```

## Reconciliation

The operator polls each application's API on the configured `interval` and applies any drift. `deletionPolicy: orphan` means deleting a CR leaves the configuration in place rather than tearing it down -- deliberate, so an accidental `kubectl delete` cannot wipe a working *arr setup.

Because reconciliation runs against a live API, the target application must be up and its API key must be valid. A rotated key that has not been re-adopted into Vault causes silent 401s.

!!! note "API keys still flow the wrong way"
    Each *arr app generates its own API key on first boot; the operator consumes it. `make arr-keys-adopt` copies the live keys into Vault at `homelab/apps/arr`, from where ESO syncs them into `arr-api-keys`. A cold rebuild therefore still needs a human to visit each web UI once before the operator can do anything.

## Metrics

Both operators expose Prometheus metrics with a ServiceMonitor enabled.

## Upstream Documentation

<https://github.com/kyleseneker/media-operator>
