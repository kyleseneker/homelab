# Service URLs

## External URLs (Browser Access)

These are the hostnames routed by the Cilium Gateway API (`homelab-gateway`), with DNS entries in the UniFi gateway pointing to the gateway VIP. They use publicly trusted certificates, which work on any device without extra setup ([ADR-030](../decisions/030-public-domain-and-certificates.md)), and resolve only on the home network or over the VPN.

| Service | URL |
|---------|-----|
| ArgoCD | `https://argocd.home.seneker.io` |
| Homepage | `https://home.seneker.io` |
| Home Assistant | `https://ha.home.seneker.io` |
| Jellyfin | `https://jellyfin.home.seneker.io` |
| Seerr | `https://seerr.home.seneker.io` |
| Sonarr | `https://sonarr.home.seneker.io` |
| Radarr | `https://radarr.home.seneker.io` |
| Prowlarr | `https://prowlarr.home.seneker.io` |
| Bazarr | `https://bazarr.home.seneker.io` |
| Tdarr | `https://tdarr.home.seneker.io` |
| qBittorrent | `https://qbit.home.seneker.io` |
| Grafana | `https://grafana.home.seneker.io` |
| Prometheus | `https://prometheus.home.seneker.io` |
| Alertmanager | `https://alertmanager.home.seneker.io` |
| Uptime Kuma | `https://status.home.seneker.io` |
| Authentik | `https://auth.home.seneker.io` |
| Vault | `https://vault.home.seneker.io` |
| Goldilocks | `https://goldilocks.home.seneker.io` |

## Outside the Cluster

Not routed by the gateway; these are separate devices with their own certificates. `proxmox.home.seneker.io` is a UniFi DNS record for the Proxmox host. Proxmox VE serves a certificate from its own cluster CA, so browsers warn on it.

| Service | URL | Network |
|---------|-----|---------|
| Proxmox VE | `https://proxmox.home.seneker.io:8006` | Homelab VLAN (192.168.10.2) |
| Intel AMT (MS-01) | `https://192.168.99.5:16993` | Management VLAN -- see [ADR-017](../decisions/017-intel-amt-oob-management.md) |
| UNAS Pro | `https://192.168.1.158` | Default VLAN |

## Internal URLs (Kubernetes Service DNS)

Used for app-to-app communication within the cluster. These follow the standard Kubernetes DNS format `<service>.<namespace>.svc.cluster.local:<port>`.

| Service | URL |
|---------|-----|
| Sonarr | `http://sonarr.media.svc.cluster.local:8989` |
| Radarr | `http://radarr.media.svc.cluster.local:7878` |
| Prowlarr | `http://prowlarr.media.svc.cluster.local:9696` |
| Bazarr | `http://bazarr.media.svc.cluster.local:6767` |
| Jellyfin | `http://jellyfin.media.svc.cluster.local:8096` |
| Seerr | `http://seerr.media.svc.cluster.local:80` |
| qBittorrent | `http://downloads.media.svc.cluster.local:8080` |
| Tdarr | `http://tdarr.media.svc.cluster.local:8265` |
| Loki | `http://loki.monitoring.svc.cluster.local:3100` |
| Garage (S3) | `http://garage.backups.svc.cluster.local:3900` |
| Garage (admin, metrics) | `http://garage.backups.svc.cluster.local:3903` |
| Exportarr (Sonarr) | `http://exportarr-sonarr.media.svc.cluster.local:9707` |
| Exportarr (Radarr) | `http://exportarr-radarr.media.svc.cluster.local:9708` |
| Exportarr (Prowlarr) | `http://exportarr-prowlarr.media.svc.cluster.local:9709` |
| Exportarr (Bazarr) | `http://exportarr-bazarr.media.svc.cluster.local:9710` |
| FlareSolverr | `http://flaresolverr.media.svc.cluster.local:8191` |
| Unpackerr | `http://unpackerr.media.svc.cluster.local:5656` |
| Uptime Kuma | `http://uptime-kuma.monitoring.svc.cluster.local:3001` |
| NUT Exporter | `http://nut-exporter.monitoring.svc.cluster.local:9199` |
| Authentik | `http://authentik-server.auth.svc.cluster.local` |
| Vault | `http://vault.vault.svc.cluster.local:8200` |
