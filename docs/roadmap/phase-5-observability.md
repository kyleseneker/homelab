# Phase 5 -- Observability

**Status:** Not started

**Goal:** Complete the observability trifecta (metrics, logs, traces) and shift from threshold-based alerting to SLO-driven operations.

**Addresses:** [K10, K14, K8](assessment.md#kubernetes--software-layer)

---

## 5.1 Add Distributed Tracing

- [ ] Deploy OpenTelemetry Collector as a DaemonSet (OTLP receiver)
- [ ] Deploy Grafana Tempo for trace storage
- [ ] Add Tempo as a Grafana datasource
- [ ] Instrument the request path: Cilium Gateway, Authentik forward-auth, application backends
- [ ] Verify traces appear in Grafana and correlate with metrics and logs
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Metrics tell you *what* is broken. Logs tell you *where*. Traces tell you *why* by showing the full request lifecycle across services. Debugging slow Jellyfin loads or intermittent auth failures currently requires manually correlating timestamps. |
| **Stack** | OpenTelemetry Collector (DaemonSet) &rarr; Grafana Tempo (storage) &rarr; Grafana (visualization). |

## 5.2 Grafana Dashboards-as-Code

- [ ] Export existing Grafana dashboards to JSON
- [ ] Store in Git under the kube-prometheus-stack component
- [ ] Enable the Grafana sidecar to load dashboards from labeled ConfigMaps
- [ ] Deploy via ArgoCD
- [ ] Verify dashboards survive a full Grafana PVC wipe

| | |
|---|---|
| **Why** | Dashboards are created in the Grafana UI and stored in the PVC. A DR event loses dashboards created between the last backup and the failure. Dashboards-as-code makes them reproducible and reviewable. |
| **Approach** | kube-prometheus-stack already supports `sidecar.dashboards.enabled`. ConfigMaps with a specific label are auto-loaded. |

## 5.3 SLO-Based Alerting

- [ ] Choose a tool: Pyrra or Sloth
- [ ] Define SLOs for critical services (see below)
- [ ] Generate Prometheus recording rules and multi-window burn rate alerts
- [ ] Add SLO dashboards to Grafana
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Current alerts fire on fixed thresholds (CPU > 85%, restarts > 5/hr). These are guesses that cause alert fatigue or fire too late. SLO-based alerting fires when users are impacted, measured by error budget burn rate. |

**Example SLOs:**

| Service | SLO | Error Budget |
|---------|-----|-------------|
| Jellyfin | 99.5% availability | ~3.6 hours/month |
| Authentik | 99.9% availability | ~43 minutes/month |
| ArgoCD | 99% sync success rate | ~7.3 hours/month |

## 5.4 Upgrade Synthetic Monitoring to Prometheus-Native Probes

Uptime Kuma already provides synthetic monitoring and a status page. This task upgrades to Blackbox Exporter for tighter Prometheus integration and SLO-compatible metrics.

- [ ] Deploy Blackbox Exporter
- [ ] Configure probes for every HTTPRoute endpoint
- [ ] Add PrometheusRules for probe failure and response time thresholds
- [ ] Add a Grafana dashboard for probe status
- [ ] Evaluate whether Uptime Kuma remains valuable alongside Blackbox Exporter (status page, external notifications) or should be retired

| | |
|---|---|
| **Why** | Uptime Kuma validates endpoint reachability but its metrics are not in Prometheus. Blackbox Exporter tests the full request path (DNS &rarr; Gateway &rarr; TLS &rarr; Authentik forward-auth &rarr; backend) and feeds directly into SLO burn-rate alerts (5.3). |

---

## Definition of Done

- [ ] Request traces visible in Grafana for auth-gated flows
- [ ] All Grafana dashboards versioned in Git, deployed via ArgoCD
- [ ] SLOs defined for Jellyfin, Authentik, and ArgoCD with burn-rate alerts
- [ ] Synthetic probes testing every HTTPS endpoint
