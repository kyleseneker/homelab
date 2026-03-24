# Service URLs

## External URLs (Browser Access)

These are the ingress hostnames exposed by ingress-nginx. All require DNS entries pointing to the MetalLB LoadBalancer IP and trusting the homelab CA certificate.

| Service | URL |
|---------|-----|
| ArgoCD | `https://argocd.homelab.local` |
| Homepage | `https://home.homelab.local` |
| Jellyfin | `https://jellyfin.homelab.local` |
| Jellyseerr | `https://jellyseerr.homelab.local` |
| Sonarr | `https://sonarr.homelab.local` |
| Radarr | `https://radarr.homelab.local` |
| Prowlarr | `https://prowlarr.homelab.local` |
| Bazarr | `https://bazarr.homelab.local` |
| Tdarr | `https://tdarr.homelab.local` |
| qBittorrent | `https://qbit.homelab.local` |
| SABnzbd | `https://sabnzbd.homelab.local` |
| Grafana | `https://grafana.homelab.local` |
| Prometheus | `https://prometheus.homelab.local` |
| Alertmanager | `https://alertmanager.homelab.local` |
| Uptime Kuma | `https://status.homelab.local` |
| Authentik | `https://auth.homelab.local` |

## Internal URLs (Kubernetes Service DNS)

Used for app-to-app communication within the cluster. These follow the standard Kubernetes DNS format `<service>.<namespace>.svc.cluster.local:<port>`.

| Service | URL |
|---------|-----|
| Sonarr | `http://arr-sonarr.arr.svc.cluster.local:8989` |
| Radarr | `http://arr-radarr.arr.svc.cluster.local:7878` |
| Prowlarr | `http://arr-prowlarr.arr.svc.cluster.local:9696` |
| Bazarr | `http://arr-bazarr.arr.svc.cluster.local:6767` |
| Jellyfin | `http://arr-jellyfin.arr.svc.cluster.local:8096` |
| Jellyseerr | `http://arr-jellyseerr.arr.svc.cluster.local:5055` |
| qBittorrent | `http://arr-vpn-downloads.arr.svc.cluster.local:8080` |
| SABnzbd | `http://arr-vpn-downloads.arr.svc.cluster.local:8085` |
| Tdarr | `http://arr-tdarr.arr.svc.cluster.local:8265` |
| Loki | `http://loki.monitoring.svc.cluster.local:3100` |
| MinIO | `http://minio.backups.svc.cluster.local:9000` |
| Exportarr (Sonarr) | `http://arr-exportarr-sonarr.arr.svc.cluster.local:9707` |
| Exportarr (Radarr) | `http://arr-exportarr-radarr.arr.svc.cluster.local:9708` |
| Exportarr (Prowlarr) | `http://arr-exportarr-prowlarr.arr.svc.cluster.local:9709` |
| Exportarr (Bazarr) | `http://arr-exportarr-bazarr.arr.svc.cluster.local:9710` |
| Uptime Kuma | `http://uptime-kuma.monitoring.svc.cluster.local:3001` |
| Authentik | `http://authentik-server.auth.svc.cluster.local` |
