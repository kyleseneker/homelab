# ADR-022: Prometheus Synthetic Monitoring with an External Heartbeat

## Status

Accepted

## Context

Pod readiness does not establish that a service is reachable through DNS, the Gateway and TLS. Endpoint checks need to feed the existing Prometheus alerting system and remain reproducible from Git. Monitors running inside the cluster also share its failure domain and cannot deliver an alert after complete cluster loss.

## Decision

Use Blackbox Exporter with Git-managed Probe resources for endpoint reachability, certificate validation and expected HTTP responses. Prometheus evaluates probe results, exporter availability and missing-series alerts. Alertmanager sends an external Watchdog heartbeat so an independent service can detect loss of the monitoring and notification path.

Prometheus Probe resources are the endpoint inventory for this monitoring path. Uptime Kuma remains separate for its status page and integrations.

## Alternatives Considered

- **Pod readiness and application metrics alone**: Describe workload health but miss failures in DNS, routing and client-facing TLS.
- **Uptime Kuma alone**: Provides endpoint checks and a status page, but leaves monitor definitions in runtime state and outside the native Prometheus rule workflow.
- **In-cluster probes without an external heartbeat**: Detect individual service failures while the monitoring stack works, but cannot independently report total cluster loss.

## Rationale

- **Git-managed coverage**: Endpoint definitions and expected responses are reviewable and reproducible.
- **Prometheus integration**: Probe metrics use the existing alert routing and can support service-level measurements.
- **Independent failure detection**: A missed external heartbeat detects interruption of the path that would otherwise report failures.

## Consequences

- A successful login redirect establishes authentication-edge reachability, not authenticated backend behavior or media playback. Those require separate checks.
- An external heartbeat detects loss of the monitoring path without identifying which component failed.
- Internal HTTPS probes depend on the CA bundle distributed through [trust-manager](020-ca-trust-distribution.md).
- Uptime Kuma retains its own configuration and backup requirements while it remains deployed.
