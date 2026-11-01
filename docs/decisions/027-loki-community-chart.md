# ADR-027: Loki Chart from grafana-community

## Status

Accepted

## Context

[ADR-011](011-observability-stack.md) runs Loki as a single binary with filesystem
storage, installed from the `loki` chart at `https://grafana.github.io/helm-charts`.
That chart was built from the Loki repository; 6.55.0 (Loki 3.6.7) was its last
release there. The open-source chart moved to the
[grafana-community/helm-charts](https://github.com/grafana-community/helm-charts)
repository, forked at 6.55.0. From 7.0.0, the chart that remains in the Grafana
repository is maintained for Grafana Enterprise Logs and stays on Loki 3.6.x
([migration guide](https://grafana.com/docs/loki/latest/setup/upgrade/upgrade-helm-to-community/)).

Renovate proposed the Grafana repository's 7.5.0, which would have kept Loki on 3.6.x.

## Decision

Install Loki from the community chart at
`https://grafana-community.github.io/helm-charts`. The deployment is unchanged: a
single `Monolithic` (single-binary) replica with filesystem storage on the existing
`nfs-client` volume.

Take chart majors one at a time, each as its own change verified before the next.
Renovate opens one pull request per major.

The move went from 6.55.0 through the latest release of each major to 20.2.1
(Loki 3.6.7 to 3.7.9) and kept the `storage-loki-0` volume claim.

## Alternatives Considered

- **Stay on the Grafana repository's chart**: Needs no migration, but is maintained
  for an enterprise product this cluster does not run, and does not follow Loki
  past 3.6.x.
- **Render Loki from the bjw-s app-template chart (ADR-008)**: Removes the dependency on a
  third-party chart, but moves the Loki configuration, Services, probes and
  ServiceMonitor into this repository to maintain.
- **Loki Operator**: Its `LokiStack` resource requires object storage and targets
  distributed deployments, which ADR-011 rejected for this cluster's log volume.

## Consequences

- Chart majors are frequent: 7.0.0 shipped on 2026-03-21 and 20.0.0 on 2026-10-25.
  Most change values or defaults, so each major needs its render reviewed against
  the README's upgrading notes.
- The values schema rejects unknown top-level keys from chart 20. A leftover or
  misspelled key fails rendering rather than being ignored.
- Chart defaults changed during the move:
  - Loki exits when its startup memberlist join fails. The memberlist Service
    therefore publishes not-ready addresses, so the single replica can join itself
    before it is ready.
  - The volume claim retention policy is `Retain`.
  - Loki's metrics use the `app_instance` label instead of `cluster`.
- Alloy still comes from the Grafana repository.
