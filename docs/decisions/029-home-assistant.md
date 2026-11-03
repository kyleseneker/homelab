# ADR-029: Home Assistant on Kubernetes

## Status

Proposed

## Context

The household needs a home automation platform for device control, dashboards, monitoring and integrations. Home Assistant supports two installation types: Home Assistant OS, which is recommended and includes the Supervisor and its apps (formerly add-ons), and Home Assistant Container. Container "doesn't have access to apps", and has "no out-of-the-box support" for Thread or Z-Wave ([installation](https://www.home-assistant.io/installation/)). Core and Supervised installs lost support after 2025.12 ([deprecation](https://home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/)).

The official container runs as root, and its documentation runs it privileged with host networking ([Linux installation](https://www.home-assistant.io/installation/linux)). The cluster's Kyverno policies require non-root containers with read-only root filesystems outside a few excluded namespaces ([ADR-014](014-kyverno-policy-engine.md)).

Home Assistant will hold credentials for every system it integrates with, and will control physical devices. Some properties of its design shape the controls below:

- Long-lived access tokens carry the full rights of the user who created them, for ten years, with no scoping. Non-admin users can still call services that control entities ([auth models](https://github.com/home-assistant/core/blob/dev/homeassistant/auth/models.py), [permissions](https://contributors.home-assistant.io/core/internals/permissions/)).
- Until onboarding completes, whoever first reaches the web UI creates the owner account ([onboarding views](https://github.com/home-assistant/core/blob/dev/homeassistant/components/onboarding/views.py)).
- Since 2026.8, HTTP server settings (trusted proxies, listen addresses) are configured in the UI. Existing YAML is imported once and then ignored ([HTTP integration](https://www.home-assistant.io/integrations/http/)).
- Integration credentials and OAuth refresh tokens are stored unencrypted under `/config/.storage`.

Current smart home devices are Wi-Fi devices that mostly depend on vendor clouds. Discovery and local control need a presence on the IoT VLAN, which [ADR-028](028-multus-iot-attachments.md) provides.

## Decision

Run Home Assistant Container on homelabk8s01 in a `home-automation` namespace, deployed with app-template ([ADR-008](008-bjw-s-app-template.md)) through the ApplicationSet.

### Image and pod security

- Use the rootless `ghcr.io/home-operations/home-assistant` image, pinned by version and digest as its maintainers require ([home-operations/containers](https://github.com/home-operations/containers)). It tracks Home Assistant releases, runs without s6-overlay as `nobody`, and supports a read-only root filesystem with `/config` and `/tmp` writable.
- Set the pod's security context explicitly:
    - `runAsUser`, `runAsGroup` and `fsGroup` of 1000, with `runAsNonRoot`
    - `seccompProfile: RuntimeDefault`
    - all capabilities dropped, and no privilege escalation
    - `automountServiceAccountToken: false`, since Home Assistant needs no Kubernetes API access
- Label the namespace `pod-security.kubernetes.io/enforce: restricted`. It needs no Kyverno exclusions.

### Networking and access

- Cilium's `eth0` carries cluster, gateway and internet traffic, and holds the default route.
- Home Assistant's own attachment definition ([ADR-028](028-multus-iot-attachments.md)) gives it 192.168.20.10 on VLAN 20, IPv4 only, for discovery and local device control. The Proxmox NIC filter admits only discovery traffic and the ports listed for Home Assistant in its app doc.
- People reach Home Assistant only through `https://ha.home.seneker.io` on `homelab-gateway`, with its publicly trusted certificate ([ADR-030](030-public-domain-and-certificates.md)). Household clients reach it through the gateway VIP, the only Homelab address they may open connections to ([ADR-016](016-vlan-segmentation.md#firewall-rules)), and remote access uses the existing WireGuard and Teleport path.
- Add a UniFi rule that blocks Internal to 192.168.20.10, ahead of the Internal-to-IoT allow, so no browser or app ever sends credentials in plaintext over VLAN 20.
- Set trusted proxies to the pod CIDR, since the gateway reaches the pod from there. Limit ingress on port 8123 to the gateway and the Prometheus pod with CiliumNetworkPolicy, so no other pod can forge a client address.
- Set the internal and external URLs to `https://ha.home.seneker.io`, so discovery never hands out the VLAN 20 address.
- Do not place Home Assistant behind the Authentik outpost. Its companion apps cannot complete a proxied browser login, which is the same reason Jellyfin is excluded ([ADR-010](010-authentik-sso.md)).

### Onboarding and authentication

- Deploy first without the route and without the attachment. Complete onboarding through a port-forward. Then set trusted proxies and URLs, and only then add the route and the attachment.
- Recovery follows the same order. Never expose a Home Assistant whose `/config` is empty.
- Require multi-factor authentication for every user. Give household members non-admin accounts.
- Enable IP banning with a login-attempt threshold.
- Never enable the `trusted_networks` auth provider.
- Alert through Loki on authentication failures and bans.

### Credentials Home Assistant holds

- **UniFi**: Use a dedicated local View Only account, which is enough for presence detection. Home Assistant gets no switch, PoE or firewall control, and never the controller's administrative API key ([UniFi integration](https://www.home-assistant.io/integrations/unifi/)).
- **Vendor clouds**: Use dedicated accounts with multi-factor authentication where vendors support it. Prefer local integrations to cloud ones.
- **Prometheus**: The scrape token comes from a dedicated non-admin user. It can still control entities, so it lives in Vault, syncs only into `home-automation` through External Secrets ([ADR-007](007-vault-eso-secrets.md)), and rotates with the other secrets.
- **Inventory**: List every credential Home Assistant holds in its app doc, so each can be revoked.

### State and configuration

- Schedule the pod only on workers labelled `home.seneker.io/iot-vlan=true`, so its `local-path` volume is created on a node that can carry the attachment.
- Keep `/config` on a `local-path` volume, because the recorder's SQLite database must not live on NFS ([ADR-006](006-nfs-local-path-storage.md)). Velero cannot read `local-path` volumes, so the plaintext `.storage` never leaves the node except inside encrypted backups.
- Keep the runtime virtualenv (`/config/.venv`) on an `emptyDir`, out of the config volume and its backups.
- Keep `configuration.yaml` in Git, mounted read-only over the generated file, for the URLs and integrations that still accept YAML, such as the recorder and the Prometheus export. Automations, scripts and scenes made in the UI stay in their own files on the config volume. HTTP settings (forwarded headers, trusted proxies, IP banning) are UI state: Home Assistant imports an `http:` YAML block only once and ignores it afterwards. They are set during onboarding and recorded in the app doc.

### Backups

- Use Home Assistant's scheduled native backups, which are consistent and include the database ([backups](https://www.home-assistant.io/common-tasks/general/backups/)). Write them to an `nfs-client` volume mounted at `/config/backups`.
- Verify encryption is on for every backup location, since it can be turned off per location. Store the key in Vault.
- Add the namespace to Velero's daily stateful schedule and to the separate weekly offsite schedule, which has its own namespace list ([ADR-013](013-backup-strategy.md), [ADR-025](025-garage-velero-local-backups.md)).
- Alert on the backup integration's last-successful-backup sensor through the Prometheus export.

### Network policy and observability

- Add CiliumNetworkPolicies for the namespace:
    - Deny ingress by default, then allow port 8123 from the gateway and the Prometheus pod.
    - For egress, allow DNS to cluster DNS, and HTTPS to `0.0.0.0/0` with the RFC 1918, CGNAT and link-local ranges excluded. Open LAN or in-cluster integrations by explicit address.
    - Allow no egress to the Kubernetes API, Vault, Authentik or the NAS.
- These policies do not cover the VLAN 20 attachment.
- Scrape the `prometheus` integration with a ServiceMonitor, and probe the route with Blackbox ([ADR-022](022-synthetic-monitoring-and-delivery.md)).

### Supply chain

- Install no custom integrations or HACS at first. Any later custom integration is reviewed, pinned by commit, and recorded in the app doc. The image installs their Python dependencies from PyPI on every start.
- Renovate proposes image updates. Read each release's backward-incompatible changes before merging.

### Radios and companion services

- Use no USB passthrough. Zigbee and Thread coordinators are network-attached on VLAN 20, with an administrator password set. Bluetooth comes from ESPHome proxies with API encryption keys.
- Deploy companion services (MQTT with Zigbee2MQTT, the matter.js Matter server) as separate apps when the first device needs them. Each gets the same pod security, its own attachment definition and address, and its own Proxmox filter entry. MQTT requires TLS and per-client credentials.

### Prerequisites

The gateway restrictions in [ADR-016](016-vlan-segmentation.md#firewall-rules) and [ADR-026](026-iot-vlan.md) are in place before Home Assistant gets its VLAN 20 address. The IoT-to-Gateway restriction keeps that address away from the UniFi console and SSH.

## Alternatives Considered

- **Home Assistant OS VM on Proxmox**: Supervisor-managed apps, one-click updates, built-in Thread border router support, and isolation from cluster maintenance. It would sit outside GitOps, Vault, Velero and the monitoring stack, with a second update and backup path to run. Rejected so the platform's operating model covers home automation too.
- **Official `ghcr.io/home-assistant/home-assistant` image**: The upstream build, but it runs as root and is documented as privileged. Running it would need Kyverno exclusions and a privileged Pod Security level for the namespace.
- **`hostNetwork` instead of an attachment**: See [ADR-028](028-multus-iot-attachments.md).
- **Listen only on `eth0`**: Keeps port 8123 off VLAN 20 entirely, but the pod address changes on every restart, and some local devices call back to Home Assistant. The Proxmox filter gives per-port control instead.
- **Recorder on PostgreSQL**: Better for large histories, but the cluster has no shared PostgreSQL; Authentik's database is dedicated to it. Revisit if history volume or query latency becomes a problem.
- **Unauthenticated Prometheus endpoint**: Avoids a control-capable token, but exposes every entity state, including presence and lock state, to anyone who reaches port 8123.
- **Home Assistant's built-in S3 backup target**: Works only with AWS S3, and would duplicate Velero's offsite path with a second IAM credential and retention policy.
- **SSO in front of Home Assistant**: Breaks companion-app login. Home Assistant has no native OIDC; only community integrations exist.

## Consequences

- Home automation now depends on the cluster's control plane, Cilium, Multus and Kyverno. A worker drain, Cilium upgrade or admission outage interrupts automations. Once the household relies on them, schedule disruptive platform work with that in mind.
- `local-path` pins Home Assistant to one worker that has the VLAN 20 NIC. Draining that worker stops Home Assistant until it returns.
- Home Assistant concentrates credentials: vendor clouds, a read-only UniFi account, and control of physical devices. Its compromise is a household-security incident. The pod's own isolation, the restricted credentials and the network filters limit what that compromise reaches.
- Any IoT device can reach whatever ports the Proxmox filter admits, or impersonate an address on VLAN 20. Home Assistant's authentication and encrypted device protocols are the boundary on that side.
- With no apps, each companion service is its own app to deploy, upgrade, secure and back up. Thread border routing has no supported container path, so Thread needs a network border router on VLAN 20. Apple border routers block Matter firmware updates from Home Assistant ([Matter integration](https://www.home-assistant.io/integrations/matter/)).
- Integrations that depend on vendor webhooks need an externally reachable URL, and the homelab has no inbound path ([Phase 3.4](../roadmap/phase-3-network.md#34-plan-external-access-for-jellyfin)). Those integrations fall back to polling or need Home Assistant Cloud, which would add an internet-facing path needing its own decision.
- The Prometheus scrape token can control devices. Anyone who can read its Secret, or Prometheus's generated configuration, holds that control.
- `ha.home.seneker.io` has a publicly trusted certificate but resolves only through UniFi DNS, so companion apps reach Home Assistant only on the home network or over the VPN ([ADR-030](030-public-domain-and-certificates.md)).
- HTTP settings live in UI state, not Git. A restore brings them back from backup, and the app doc records their intended values.
- A native backup restores Home Assistant's configuration and history only. Companion services follow their own backup paths, and a restore drill belongs in the restore lab's checks.
