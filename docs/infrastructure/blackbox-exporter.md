# Blackbox Exporter

The Prometheus Blackbox Exporter checks the declared HTTP/HTTPS endpoints using Git-managed Probe resources. Prometheus scrapes probe results and evaluates endpoint, exporter and missing-series alerts. This makes the monitor inventory reproducible.

The exporter mounts the homelab CA from trust-manager and verifies HTTPS certificates. Proxy-protected applications have expected authentication-redirect behavior; native-login applications are checked separately. A login redirect shows that the edge responds, not that an authenticated backend or media playback is healthy.

Test endpoint failure, a bad certificate, a stopped exporter and missing metrics as separate cases. In-cluster probes share the cluster's failure domain; the external Watchdog heartbeat is still needed for total monitoring failure. Uptime Kuma can remain for its status page and retained UI state, but is not the source of the Probe inventory.

Source: `k8s/clusters/homelabk8s01/infrastructure/blackbox-exporter/`. See [ADR-022](../decisions/022-synthetic-monitoring-and-delivery.md).
