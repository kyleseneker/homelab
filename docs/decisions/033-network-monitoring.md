# ADR-033: Network Monitoring

## Status

Accepted

## Context

Lag and Wi-Fi drops leave nothing to investigate afterwards. The UniFi controller keeps 5-minute statistics for a day. The Blackbox probes ([ADR-022](022-synthetic-monitoring-and-delivery.md)) test HTTPS services; nothing measures latency or packet loss on the network, records Wi-Fi quality over time, or keeps gateway, access point and Wi-Fi client events.

## Decision

Feed the network into the existing Prometheus, Loki and Alertmanager stack from two sources:

- **Controller metrics and events.** [unpoller](https://github.com/unpoller/unpoller) reads the UniFi Network API on the Dream Router every 30 seconds with a View Only API key. It exports per-radio channel use, per-client signal, experience score and retries, extender uplink signal, switch ports, the gateway's WAN monitors and speed tests to Prometheus, and forwards the controller's system log to Loki. The API is on the console, so [ADR-016](016-vlan-segmentation.md) opens 192.168.10.1:443 to the Kubernetes nodes and a cluster-wide Cilium policy keeps every pod but unpoller off it. unpoller pins the console's self-signed certificate and skips the device-tags endpoint, which leaks memory on UniFi OS consoles ([unpoller#1119](https://github.com/unpoller/unpoller/issues/1119)).
- **Continuous latency and loss probes.** [smokeping_prober](https://github.com/SuperQ/smokeping_prober) pings the gateway, the NAS and three public resolvers once a second from inside the cluster and exports round-trip histograms and loss counters. Prometheus alerts on sustained loss; the Network dashboard shows short blips.

unpoller is the controller's view of Wi-Fi state and its events, sampled. The probes measure from outside the gateway, once a second, and keep recording while the gateway is down.

## Alternatives Considered

- **Gateway syslog to Loki**: The Dream Router can push its activity log as CEF over UDP syslog. It omits the syslog priority header, so Alloy accepts it only in its experimental `raw` format, which needs a dedicated instance at `--stability.level=experimental`, a LoadBalancer address with `externalTrafficPolicy: Local`, and an ingress exception from `world`. Run alongside unpoller, it carried the same network events with receive-time timestamps; the only additions were UniFi OS account events (admins and users added, removed or deactivated).
- **Blackbox ICMP probes**: One ping per scrape, so loss between scrapes goes unseen and there is no latency distribution.
- **SNMP from the UniFi devices**: The switch and access points sit on the Management and Default VLANs, which the cluster cannot reach, and their agents carry no Wi-Fi client data.
- **An administrator API key for unpoller**: Works, but unpoller only reads, and a View Only key cannot change the network if it leaks.
- **NetFlow/IPFIX**: Shows which devices used the bandwidth, not when the network failed. It remains a later addition.

## Rationale

- **Least privilege into the management plane**: One address and port, the nodes only at the gateway, unpoller only inside the cluster, and a read-only key.
- **Blips need continuous measurement**: One ping per second, kept as histograms, records loss and latency bursts shorter than a scrape interval.
- **Independent views**: A gateway that reboots or hangs takes the controller's metrics with it; the probes still describe the outage.
- **Fewest moving parts**: The controller's system log already holds the network events, with the controller's own timestamps and every field structured, so no second event pipeline is needed.
- **One alerting path**: Network alerts share Alertmanager routing, silences and the external heartbeat with every other alert.

## Consequences

- The nodes, and host-network pods on them, reach the console's login page. Cilium policies do not cover host-network pods; the console's own login is the remaining protection there.
- unpoller accepts only the pinned certificate, which expires on 2027-08-26. When the console regenerates it, `UnpollerAbsent` fires until the new certificate is pinned.
- Events arrive in Loki in batches every two minutes, and stop while unpoller cannot reach the console.
- UniFi OS account events, such as a new admin, are not collected; the Network application's system log does not contain them.
- The probes run from the wired cluster. They measure the switch, the gateway, the WAN link and the ISP, not Wi-Fi; Wi-Fi quality comes from the controller's metrics and events.
- Public resolvers may rate-limit ICMP. The internet loss alert takes the lowest loss across three providers, so one provider's limiting does not fire it.
- Short outages, such as the gateway's unattended firmware updates, appear on the dashboard but stay inside the loss alerts' 10-minute windows.
