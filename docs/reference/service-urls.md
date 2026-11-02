# Service URLs

## External URLs (Browser Access)

These are the hostnames routed by the Cilium Gateway API (`homelab-gateway`), with DNS entries in the UniFi gateway pointing to the gateway VIP. Services are moving to `home.seneker.io` names with publicly trusted certificates, which work on any device ([ADR-030](../decisions/030-public-domain-and-certificates.md)). The `homelab.local` names stay live during the move and need the `homelab-ca` root certificate installed. For the SSO-protected apps, whose proxy providers answer on one hostname, they redirect to the `home.seneker.io` name.

| Service | `homelab.local` URL | `home.seneker.io` URL |
|---------|-----|---------------|
| ArgoCD | `https://argocd.homelab.local` | `https://argocd.home.seneker.io` |
| Homepage | `https://home.homelab.local` | `https://home.seneker.io` |
| Jellyfin | `https://jellyfin.homelab.local` | `https://jellyfin.home.seneker.io` |
| Seerr | `https://seerr.homelab.local` | `https://seerr.home.seneker.io` |
| Sonarr | `https://sonarr.homelab.local` | `https://sonarr.home.seneker.io` |
| Radarr | `https://radarr.homelab.local` | `https://radarr.home.seneker.io` |
| Prowlarr | `https://prowlarr.homelab.local` | `https://prowlarr.home.seneker.io` |
| Bazarr | `https://bazarr.homelab.local` | `https://bazarr.home.seneker.io` |
| Tdarr | `https://tdarr.homelab.local` | `https://tdarr.home.seneker.io` |
| qBittorrent | `https://qbit.homelab.local` | `https://qbit.home.seneker.io` |
| Grafana | `https://grafana.homelab.local` | `https://grafana.home.seneker.io` |
| Prometheus | `https://prometheus.homelab.local` | `https://prometheus.home.seneker.io` |
| Alertmanager | `https://alertmanager.homelab.local` | `https://alertmanager.home.seneker.io` |
| Uptime Kuma | `https://status.homelab.local` | `https://status.home.seneker.io` |
| Authentik | `https://auth.homelab.local` | `https://auth.home.seneker.io` |
| Vault | `https://vault.homelab.local` | -- |
| Goldilocks | `https://goldilocks.homelab.local` | `https://goldilocks.home.seneker.io` |

## Outside the Cluster

Not routed by the gateway; these are separate devices with their own certificates.

| Service | URL | Network |
|---------|-----|---------|
| Proxmox VE | `https://proxmox.homelab.local:8006` | Homelab VLAN (192.168.10.2) |
| Intel AMT (MS-01) | `https://192.168.99.5:16993` | Management VLAN -- see [ADR-017](../decisions/017-intel-amt-oob-management.md) |
| UNAS Pro | `https://192.168.1.158` | Default VLAN |

## Internal URLs (Kubernetes Service DNS)

Used for app-to-app communication within the cluster. These follow the standard Kubernetes DNS format `<service>.<namespace>.svc.cluster.local:<port>`.

| Service | URL |
|---------|-----|
| Sonarr | `http://arr-sonarr.arr.svc.cluster.local:8989` |
| Radarr | `http://arr-radarr.arr.svc.cluster.local:7878` |
| Prowlarr | `http://arr-prowlarr.arr.svc.cluster.local:9696` |
| Bazarr | `http://arr-bazarr.arr.svc.cluster.local:6767` |
| Jellyfin | `http://arr-jellyfin.arr.svc.cluster.local:8096` |
| Seerr | `http://arr-seerr.arr.svc.cluster.local:80` |
| qBittorrent | `http://arr-vpn-downloads.arr.svc.cluster.local:8080` |
| Tdarr | `http://arr-tdarr.arr.svc.cluster.local:8265` |
| Loki | `http://loki.monitoring.svc.cluster.local:3100` |
| Garage (S3) | `http://garage.backups.svc.cluster.local:3900` |
| Garage (admin, metrics) | `http://garage.backups.svc.cluster.local:3903` |
| Exportarr (Sonarr) | `http://arr-exportarr-sonarr.arr.svc.cluster.local:9707` |
| Exportarr (Radarr) | `http://arr-exportarr-radarr.arr.svc.cluster.local:9708` |
| Exportarr (Prowlarr) | `http://arr-exportarr-prowlarr.arr.svc.cluster.local:9709` |
| Exportarr (Bazarr) | `http://arr-exportarr-bazarr.arr.svc.cluster.local:9710` |
| FlareSolverr | `http://arr-flaresolverr.arr.svc.cluster.local:8191` |
| Unpackerr | `http://arr-unpackerr.arr.svc.cluster.local:5656` |
| Uptime Kuma | `http://uptime-kuma.monitoring.svc.cluster.local:3001` |
| NUT Exporter | `http://nut-exporter.monitoring.svc.cluster.local:9199` |
| Authentik | `http://authentik-server.auth.svc.cluster.local` |
| Vault | `http://vault.vault.svc.cluster.local:8200` |
