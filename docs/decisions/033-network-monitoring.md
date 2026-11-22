# ADR-033: Network Monitoring

## Status

Accepted

## Context

Lag and Wi-Fi drops leave nothing to investigate afterwards. The UniFi controller keeps 5-minute statistics for a day, and its event log is reachable only through the console API, which [ADR-016](016-vlan-segmentation.md) keeps the nodes and pods away from. The Blackbox probes ([ADR-022](022-synthetic-monitoring-and-delivery.md)) test HTTPS services; nothing measures latency or packet loss on the network itself or records gateway, access point and Wi-Fi client events.

## Decision

Feed the network into the existing Prometheus, Loki and Alertmanager stack from two sources that need no access to the UniFi console:

- **Gateway events over syslog.** The Dream Router sends its activity log as CEF over UDP syslog to 192.168.10.202:514, a LoadBalancer address served by `alloy-syslog`, a dedicated single-replica Alloy Deployment. The router omits the syslog priority header, so the instance reads raw lines with Alloy's experimental `raw` syslog format and parses the timestamp, hostname and CEF header itself, keeping the event fields as structured metadata in Loki. The Service uses `externalTrafficPolicy: Local`: Cilium announces the address only from the node running the pod and keeps the router's source address, so a Cilium policy admits only 192.168.10.1 from outside the cluster.
- **Continuous latency and loss probes.** [smokeping_prober](https://github.com/SuperQ/smokeping_prober) pings the gateway, the NAS and three public resolvers once a second from inside the cluster and exports round-trip histograms and loss counters. Prometheus alerts on sustained loss; the Network dashboard shows short blips.

Per-radio and per-client Wi-Fi metrics need the controller's API. Polling it from the cluster requires an exception to the console boundary in ADR-016, which is a separate decision.

## Alternatives Considered

- **Blackbox ICMP probes**: One ping per scrape, so loss between scrapes goes unseen and there is no latency distribution.
- **Polling the controller's event log**: The same events as syslog, but it needs the console access ADR-016 denies to nodes and pods.
- **Receiving syslog in the node-log Alloy DaemonSet**: Avoids a second instance, but the `raw` format needs `--stability.level=experimental`, which [may enable experimental behavior](https://grafana.com/docs/alloy/latest/reference/cli/run/) in every component of the collector that ships all pod and audit logs.
- **A relay that adds the priority header (rsyslog, syslog-ng, Vector)**: Lets Alloy parse standard RFC3164, but adds another component and configuration language for one sender.
- **`otelcol.receiver.syslog` with `allow_skip_pri_header`**: Public preview, so it also lowers the stability level, and adds an OTLP-to-Loki conversion.
- **`externalTrafficPolicy: Cluster`**: Cilium translates traffic forwarded to another node's backend to that node's address, so a policy cannot tell the router from any other source.
- **SNMP from the UniFi devices**: The switch and access points sit on the Management and Default VLANs, which the cluster cannot reach, and their agents carry no Wi-Fi client data.
- **NetFlow/IPFIX**: Shows which devices used the bandwidth, not when the network failed. It remains a later addition.

## Rationale

- **No new paths into management planes**: Syslog flows from the gateway into the Homelab zone, which the zone defaults allow, and the probes use ICMP, which the gateway rules leave open.
- **Blips need continuous measurement**: One ping per second, kept as histograms, records loss and latency bursts shorter than a scrape interval.
- **One alerting path**: Network alerts share Alertmanager routing, silences and the external heartbeat with every other alert.

## Consequences

- The probes run from the wired cluster. They measure the switch, the gateway, the WAN link and the ISP, not Wi-Fi. Until controller metrics are added, Wi-Fi quality is visible only through the gateway's client events.
- UDP syslog has no delivery guarantee. Messages sent while `alloy-syslog` restarts, or while it moves to another node and Cilium moves the announcement with it, are lost.
- `alloy-syslog` runs at `--stability.level=experimental` for the `raw` format; the node-log DaemonSet stays at generally available.
- The gateway's syslog destination and categories live in the UniFi UI, not Git ([Network Infrastructure](../architecture/network-infrastructure.md#syslog)).
- Loki stores events at receive time, because the router's timestamps carry no year or time zone.
- Public resolvers may rate-limit ICMP. The internet loss alert takes the lowest loss across three providers, so one provider's limiting does not fire it.
- Short outages, such as the gateway's unattended firmware updates, appear on the dashboard but stay inside the alerts' 10-minute windows.
- `monitoring-default-deny` does not select `alloy-syslog`. `monitoring-alloy-syslog` denies every source outside the cluster except the gateway in its place ([Network Policies](../infrastructure/network-policies.md)).
