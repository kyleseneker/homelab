# ADR-033: Network Monitoring

## Status

Accepted

## Context

Lag and Wi-Fi drops leave nothing to investigate afterwards. The UniFi controller keeps 5-minute statistics for a day. The Blackbox probes ([ADR-022](022-synthetic-monitoring-and-delivery.md)) test HTTPS services; nothing measures latency or packet loss on the network, records Wi-Fi quality over time, or keeps gateway, access point and Wi-Fi client events.

## Decision

Feed the network into the existing Prometheus, Loki and Alertmanager stack from three sources:

- **Controller metrics and events.** [unpoller](https://github.com/unpoller/unpoller) reads the UniFi Network API on the Dream Router every 30 seconds with a View Only API key. It exports per-radio channel use, per-client signal, experience score and retries, extender uplink signal, switch ports, the gateway's WAN monitors and speed tests to Prometheus, and forwards the controller's system log to Loki. The API is on the console, so [ADR-016](016-vlan-segmentation.md) opens 192.168.10.1:443 to the Kubernetes nodes and a cluster-wide Cilium policy keeps every pod but unpoller off it. unpoller pins the console's self-signed certificate and skips the device-tags endpoint, which leaks memory on UniFi OS consoles ([unpoller#1119](https://github.com/unpoller/unpoller/issues/1119)).
- **Gateway events over syslog.** The Dream Router sends its activity log as CEF over UDP syslog to 192.168.10.202:514, a LoadBalancer address served by `alloy-syslog`, a dedicated single-replica Alloy Deployment. The router omits the syslog priority header, so the instance reads raw lines with Alloy's experimental `raw` syslog format and parses the timestamp, hostname and CEF header itself, keeping the event fields as structured metadata in Loki. The Service uses `externalTrafficPolicy: Local`: Cilium announces the address only from the node running the pod and keeps the router's source address, so a Cilium policy admits only 192.168.10.1 from outside the cluster.
- **Continuous latency and loss probes.** [smokeping_prober](https://github.com/SuperQ/smokeping_prober) pings the gateway, the NAS and three public resolvers once a second from inside the cluster and exports round-trip histograms and loss counters. Prometheus alerts on sustained loss; the Network dashboard shows short blips.

Each source covers a gap in the others. unpoller is the controller's view of Wi-Fi state, sampled. Syslog pushes each event as it happens, independently of the poller's credentials and firewall exception. The probes measure from outside the gateway, once a second, and keep recording while the gateway is down.

## Alternatives Considered

- **Blackbox ICMP probes**: One ping per scrape, so loss between scrapes goes unseen and there is no latency distribution.
- **SNMP from the UniFi devices**: The switch and access points sit on the Management and Default VLANs, which the cluster cannot reach, and their agents carry no Wi-Fi client data.
- **An administrator API key for unpoller**: Works, but unpoller only reads, and a View Only key cannot change the network if it leaks.
- **Receiving syslog in the node-log Alloy DaemonSet**: Avoids a second instance, but the `raw` format needs `--stability.level=experimental`, which [may enable experimental behavior](https://grafana.com/docs/alloy/latest/reference/cli/run/) in every component of the collector that ships all pod and audit logs.
- **A relay that adds the priority header (rsyslog, syslog-ng, Vector)**: Lets Alloy parse standard RFC3164, but adds another component and configuration language for one sender.
- **`otelcol.receiver.syslog` with `allow_skip_pri_header`**: Public preview, so it also lowers the stability level, and adds an OTLP-to-Loki conversion.
- **`externalTrafficPolicy: Cluster`**: Cilium translates traffic forwarded to another node's backend to that node's address, so a policy cannot tell the router from any other source.
- **NetFlow/IPFIX**: Shows which devices used the bandwidth, not when the network failed. It remains a later addition.

## Rationale

- **Least privilege into the management plane**: One address and port, the nodes only at the gateway, unpoller only inside the cluster, and a read-only key.
- **Blips need continuous measurement**: One ping per second, kept as histograms, records loss and latency bursts shorter than a scrape interval.
- **Independent views**: A gateway that reboots or hangs takes the controller's metrics with it; the probes and pushed events still describe the outage.
- **One alerting path**: Network alerts share Alertmanager routing, silences and the external heartbeat with every other alert.

## Consequences

- The nodes, and host-network pods on them, reach the console's login page. Cilium policies do not cover host-network pods; the console's own login is the remaining protection there.
- unpoller accepts only the pinned certificate, which expires on 2027-08-26. When the console regenerates it, `UnpollerAbsent` fires until the new certificate is pinned.
- The probes run from the wired cluster. They measure the switch, the gateway, the WAN link and the ISP, not Wi-Fi; Wi-Fi quality comes from the controller's metrics and events.
- UDP syslog has no delivery guarantee. Messages sent while `alloy-syslog` restarts, or while it moves to another node and Cilium moves the announcement with it, are lost.
- `alloy-syslog` runs at `--stability.level=experimental` for the `raw` format; the node-log DaemonSet stays at generally available.
- The gateway's syslog destination and categories live in the UniFi UI, not Git ([Network Infrastructure](../architecture/network-infrastructure.md#syslog)).
- Loki stores syslog events at receive time, because the router's timestamps carry no year or time zone. unpoller's copies of the same events keep the controller's timestamps.
- Public resolvers may rate-limit ICMP. The internet loss alert takes the lowest loss across three providers, so one provider's limiting does not fire it.
- Short outages, such as the gateway's unattended firmware updates, appear on the dashboard but stay inside the loss alerts' 10-minute windows.
- `monitoring-default-deny` does not select `alloy-syslog`. `monitoring-alloy-syslog` denies every source outside the cluster except the gateway in its place ([Network Policies](../infrastructure/network-policies.md)).
