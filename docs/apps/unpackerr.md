# Unpackerr

Unpackerr monitors download clients for completed downloads containing compressed archives (rar, zip, etc.) and automatically extracts them. After extraction, it notifies Sonarr and Radarr so they can import the files into the media library.

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v4.6.2 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/unpackerr/unpackerr:v0.15.2` |
| Port | 5656 (health/metrics only) |
| Ingress | -- (internal only) |
| Namespace | `arr` |
| ArgoCD app | `arr-unpackerr` |
| Sync wave | 1 |
| Internal URL | `http://arr-unpackerr.arr.svc.cluster.local:5656` |

### Storage

| Volume | Type | Size | Mount Path |
|--------|------|------|------------|
| `data` | PVC (existing `arr-data`) | -- | `/data` |

### Resources

| | CPU | Memory |
|---|-----|--------|
| Requests | 50m | 128Mi |
| Limits | -- | 256Mi |

## Key Configuration

- Timezone injected from ConfigMap `arr-env`.
- All configuration is via environment variables -- no config file needed.
- Connects to Sonarr, Radarr, qBittorrent, and SABnzbd via in-cluster service DNS.
- API keys and passwords are injected from SealedSecret `unpackerr-secrets`.
- Prometheus metrics exposed on port 5656 when `UN_WEBSERVER_METRICS` is `true`.
- Liveness, readiness, and startup probes are enabled.
- ArgoCD sync policy uses `ServerSideApply` and `ServerSideDiff` with automated pruning and self-heal.

## Post-Deploy Setup

1. Gather the required credentials:

    | Secret Key | Where to Find It |
    |------------|-----------------|
    | `UN_SONARR_0_API_KEY` | Sonarr > Settings > General > API Key |
    | `UN_RADARR_0_API_KEY` | Radarr > Settings > General > API Key |
    | `UN_QBIT_0_PASSWORD` | Your qBittorrent admin password |

2. Create and seal the secret:

    ```bash
    cp k8s/clusters/homelabk8s01/apps/arr/unpackerr/unpackerr-secret.example unpackerr-secret.yml
    # Edit unpackerr-secret.yml with real values
    make k8s-seal FILE=unpackerr-secret.yml
    mv unpackerr-sealed-secret.yml k8s/clusters/homelabk8s01/apps/arr/unpackerr/
    rm unpackerr-secret.yml
    ```

3. Commit and push the sealed secret.

4. Verify the pod is running and check logs for successful connections:

    ```bash
    kubectl logs -n arr -l app.kubernetes.io/instance=arr-unpackerr
    ```

    Look for messages confirming connections to Sonarr, Radarr, qBittorrent, and SABnzbd.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Sonarr | Notified after TV episode archives are extracted |
| Radarr | Notified after movie archives are extracted |
| qBittorrent | Monitored for completed torrent downloads |
| `unpackerr-secrets` | SealedSecret with API keys and passwords |

## Upstream

- [https://unpackerr.zip](https://unpackerr.zip)
