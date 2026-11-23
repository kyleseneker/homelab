# ADR-033: Network Monitoring

## Status

Accepted

## Context

Lag and Wi-Fi drops leave nothing to investigate afterwards. The UniFi controller keeps 5-minute statistics for a day. The Blackbox probes ([ADR-022](022-synthetic-monitoring-and-delivery.md)) test HTTPS services; nothing records Wi-Fi quality, internet health or gateway, access point and Wi-Fi client events over time.

## Decision

Feed the network into the existing Prometheus, Loki and Alertmanager stack from the UniFi controller with [unpoller](https://github.com/unpoller/unpoller). It reads the UniFi Network API on the Dream Router every 30 seconds with a View Only API key. It exports per-radio channel use, per-client signal, experience score and retries, extender uplink signal, switch ports, the gateway's own internet checks and speed tests to Prometheus, and forwards the controller's system log to Loki.

The API is on the console, so [ADR-016](016-vlan-segmentation.md) opens 192.168.10.1:443 to the Kubernetes nodes and a cluster-wide Cilium policy keeps every pod but unpoller off it. unpoller pins the console's self-signed certificate and skips the device-tags endpoint, which leaks memory on UniFi OS consoles ([unpoller#1119](https://github.com/unpoller/unpoller/issues/1119)).

## Alternatives Considered

- **Continuous ICMP probes from the cluster ([smokeping_prober](https://github.com/SuperQ/smokeping_prober))**: Once-a-second latency and loss to the gateway, the NAS and public resolvers, measured independently of the gateway. Run alongside unpoller, it duplicated the gateway's own internet checks for alerting purposes; what it added was second-level detail on the wired and internet path, while the lag that matters comes from Wi-Fi, which probes from wired nodes cannot see.
- **Gateway syslog to Loki**: The Dream Router can push its activity log as CEF over UDP syslog. It omits the syslog priority header, so Alloy accepts it only in its experimental `raw` format, which needs a dedicated instance at `--stability.level=experimental`, a LoadBalancer address with `externalTrafficPolicy: Local`, and an ingress exception from `world`. Run alongside unpoller, it carried the same network events with receive-time timestamps; the only additions were UniFi OS account events (admins and users added, removed or deactivated).
- **SNMP from the UniFi devices**: The switch and access points sit on the Management and Default VLANs, which the cluster cannot reach, and their agents carry no Wi-Fi client data.
- **An administrator API key for unpoller**: Works, but unpoller only reads, and a View Only key cannot change the network if it leaks.
- **NetFlow/IPFIX**: Shows which devices used the bandwidth, not when the network failed. It remains a later addition.

## Rationale

- **The controller already measures the network**: Radios, clients, extenders, switch ports, internet checks and events are all in one API, with the controller's own timestamps and every field structured.
- **Least privilege into the management plane**: One address and port, the nodes only at the gateway, unpoller only inside the cluster, and a read-only key.
- **Fewest moving parts**: One collector, no experimental features, no extra LoadBalancer address and no ingress from outside the cluster.
- **One alerting path**: Network alerts share Alertmanager routing, silences and the external heartbeat with every other alert.

## Consequences

- The nodes, and host-network pods on them, reach the console's login page. Cilium policies do not cover host-network pods; the console's own login is the remaining protection there.
- unpoller accepts only the pinned certificate, which expires on 2027-08-26. When the console regenerates it, `UnpollerAbsent` fires until the new certificate is pinned.
- Everything depends on the gateway. While it reboots or hangs, metrics and events stop; `UniFiDeviceRestarted` and `UnpollerAbsent` report it afterwards, and the external heartbeat covers a full outage.
- Internet latency is the gateway's average, refreshed every minute or two, so few-second blips on the internet path are not visible.
- Events arrive in Loki in batches every two minutes.
- UniFi OS account events, such as a new admin, are not collected; the Network application's system log does not contain them.
- Short outages, such as the gateway's unattended firmware updates, stay inside the internet alerts' windows.
