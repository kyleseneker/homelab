# Phase 5 — Observability

**Status:** In progress. Metrics, Loki/Alloy logs, capacity and Exportarr dashboards, Blackbox probes and an external heartbeat are implemented. Tracing and SLO-based alerting remain planned.

**Goal:** Complete metrics, logs and traces, make dashboards reproducible, and add SLO-driven operations alongside tested alert delivery.

**Addresses:** K10, K14, K15, K30–K32, K35, K37 and K42 in the [assessment](assessment.md).

## 5.1 Add Distributed Tracing

- [ ] Configure OpenTelemetry collection for the request path. Evaluate the existing Alloy deployment and a dedicated OpenTelemetry Collector for the required receivers and processors.
- [ ] Deploy Grafana Tempo for trace storage and add it as a Grafana datasource.
- [ ] Instrument supported portions of the Cilium Gateway, Authentik proxy and application request path; document propagation gaps where a component lacks tracing support.
- [ ] Verify traces appear in Grafana and correlate with metrics and logs.
- [ ] Define retention and resource budgets for the trace pipeline.

Tracing provides a way to investigate request latency across services and practice OpenTelemetry instrumentation. The planned storage and visualization path is Tempo → Grafana; collector placement remains an implementation choice to evaluate.

## 5.2 Grafana Dashboards as Code

- [x] Provision cluster-capacity, namespace-resource and Exportarr dashboards from Git.
- [x] Load labeled dashboard ConfigMaps through the Grafana sidecar.
- [ ] Export remaining useful UI-created dashboards to Git under kube-prometheus-stack and remove duplicates.
- [ ] Verify provisioned dashboards survive an empty Grafana database in staging.
- [ ] Add views for synthetic probe status, backup age and node disk headroom.

## 5.3 SLO-Based Alerting

- [ ] Define service-level indicators and targets for Jellyfin playback/reachability, Authentik login and ArgoCD reconciliation.
- [ ] Evaluate Pyrra or Sloth for generating Prometheus recording rules and multi-window burn-rate alerts.
- [ ] Add SLO dashboards to Grafana.
- [ ] Validate missing-data behavior and notification delivery before relying on the alerts.

Set targets from household needs and observed behavior. Application availability, successful login and GitOps reconciliation measure different outcomes; use an indicator appropriate to each service.

## 5.4 Prometheus-Native Synthetic Monitoring

- [x] Deploy Blackbox Exporter with Git-managed Probe resources.
- [x] Add probe failure, missing-series and exporter alerts.
- [x] Configure an external Watchdog heartbeat.
- [ ] Check the probe inventory against every HTTPRoute endpoint and its expected response.
- [ ] Verify Blackbox rejects untrusted or expired certificates.
- [ ] Add an authenticated request/playback check. A login redirect only establishes that the authentication edge is responding.
- [ ] Confirm the external heartbeat alarms when the monitoring or delivery path disappears.
- [ ] Evaluate Uptime Kuma's status page and separate integrations alongside the Prometheus probes.

## 5.5 Verify Log and Alert Delivery

- [ ] Verify one log record is ingested once after the Alloy node-filter changes.
- [ ] Exercise exporter failure, missing metrics, certificate readiness failure and a failed backup through notification delivery.
- [ ] Exercise receiver downtime and confirm the intended fallback or independent detection path.

## Definition of Done

- [ ] Request traces are visible in Grafana with documented instrumentation coverage.
- [ ] Retained dashboards are versioned in Git and reproducible on an empty Grafana database.
- [ ] Service objectives have recording rules, burn-rate alerts and dashboards.
- [ ] Synthetic probes cover HTTPS endpoints with clear expected responses.
- [ ] Log collection, alert delivery and the external heartbeat are tested.
