# Home Assistant

Home Assistant is the home automation hub: device integrations, automations and dashboards. It runs as Home Assistant Container in the `home-automation` namespace ([ADR-029](../decisions/029-home-assistant.md)).

## Details

| Property | Value |
|----------|-------|
| Helm chart | `app-template` v5.3.0 ([bjw-s](https://bjw-s-labs.github.io/helm-charts)) |
| Image | `ghcr.io/home-operations/home-assistant`, pinned by version and digest |
| Port | 8123 |
| HTTPRoute | `ha.home.seneker.io` |
| Namespace | `home-automation`, Pod Security `restricted` |
| ArgoCD app | `home-assistant` |

## Key Configuration

- Runs as UID 1000 with a read-only root filesystem, no capabilities, `RuntimeDefault` seccomp and no ServiceAccount token. The image runs without s6-overlay.
- Scheduled only on workers labelled `home.seneker.io/iot-vlan=true`, which can carry its IoT VLAN attachment ([ADR-028](../decisions/028-multus-iot-attachments.md)).
- The image rebuilds its Python virtualenv at `/config/.venv` whenever the image changes; it is an `emptyDir`, outside the config volume and its backups.
- `configuration.yaml` comes from the `home-assistant-configuration` ConfigMap, mounted read-only; Reloader restarts the pod when it changes. It sets the external and internal URL to `https://ha.home.seneker.io`. Automations, scripts and scenes made in the UI stay in their own files on the config volume.
- HTTP settings are UI state under **Settings** > **System** > **Network**, stored in `/config/.storage/http`; Home Assistant imports an `http:` YAML block only once and ignores it afterwards. They must be: **Use X-Forwarded-For** on, **Trusted proxies** `10.0.0.0/8` (the pod CIDR the gateway connects from; only the gateway and Prometheus may reach port 8123, so no other pod can forge a client address), **IP ban** on, and **Login attempts threshold** 5. Until the trusted proxies are set, requests through the gateway get HTTP 400.

## Storage and Backups

| Volume | Storage | Purpose |
|--------|---------|---------|
| `home-assistant-config` | `local-path`, 5Gi | `/config`, including the recorder's SQLite database, which must not live on NFS |
| `home-assistant-backups` | `nfs-client`, 10Gi | `/config/backups`, Home Assistant's native encrypted backups |

Velero's daily and weekly offsite schedules include the namespace and copy only the backups volume; the config volume is excluded, so the plaintext `.storage` leaves the node only inside Home Assistant's encrypted backups.

## Network

- Ingress on 8123 comes only from the gateway and Prometheus. Egress is cluster DNS and public HTTPS; LAN or in-cluster integrations need an explicit rule.
- **IoT VLAN attachment**: `ha-iot` gives the pod `net1` at 192.168.20.10, MAC `02:00:00:14:00:0a`, IPv4 only, with only the connected route. It is recorded in `iot_nic.attachments` in `terraform/hosts/homelabk8s01/terraform.tfvars`, so the workers' Proxmox filter lets that address send. Changing the attachments recreates each worker's `ipfilter-net1` set, briefly dropping the attachment's IoT traffic.
- Household clients cannot reach 192.168.20.10; UniFi blocks it and they use `ha.home.seneker.io`.

| Ports open from the IoT VLAN | Purpose |
|------------------------------|---------|
| UDP 5353 | mDNS |
| UDP 1900, and replies from UDP 1900 | SSDP |

## Onboarding

A new or recovered installation starts without the route and the attachment. Onboard through a port-forward, so no one else can claim the owner account:

```bash
kubectl -n home-automation port-forward deploy/home-assistant 8123:8123
```

Then open `http://localhost:8123`, create the owner account, enable an authenticator app under the profile's Security settings, and set the HTTP settings above. The URLs come from `configuration.yaml`.

## Credentials Home Assistant Holds

None yet. Record each integration's credential here, so it can be revoked.
