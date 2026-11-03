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

Native backups are UI state under **Settings** > **System** > **Backups**:

- **Automatic backups**: daily, keeping 7, including history.
- **Locations**: this system only, which writes to `/config/backups`. Encryption is set per location; keep it on.
- **Encryption key**: store it in Vault before relying on a backup, since a restore needs it. With `VAULT_TOKEN` exported:

```bash
read -rs VAL; export VAL
make vault-put-secret SECRET_PATH=apps/home-assistant KEY=backup-encryption-key
unset VAL
```

`HomeAssistantBackupStale` fires when `sensor.backup_last_successful_automatic_backup` is more than 36 hours old, or missing while Prometheus can scrape.

## Network

- Ingress on 8123 comes only from the gateway and Prometheus. Egress is cluster DNS and public HTTPS; LAN or in-cluster integrations need an explicit rule.
- **IoT VLAN attachment**: `ha-iot` gives the pod `net1` at 192.168.20.10, MAC `02:00:00:14:00:0a`, IPv4 only, with only the connected route. It is recorded in `iot_nic.attachments` in `terraform/hosts/homelabk8s01/terraform.tfvars`, so the workers' Proxmox filter lets that address send. Changing the attachments recreates each worker's `ipfilter-net1` set, briefly dropping the attachment's IoT traffic.
- Household clients cannot reach 192.168.20.10; UniFi blocks it and they use `ha.home.seneker.io`.

| Ports open from the IoT VLAN | Purpose |
|------------------------------|---------|
| UDP 5353 | mDNS |
| UDP 1900, and replies from UDP 1900 | SSDP |

## Monitoring

The `prometheus` integration exports every entity at `/api/prometheus`. Prometheus scrapes it each minute with the scrape user's long-lived token, from the `home-assistant-prometheus` Secret (Vault `homelab/apps/home-assistant`, `prometheus-token`). Blackbox probes `https://ha.home.seneker.io` through the gateway.

| Alert | Source | Severity | Condition |
|-------|--------|----------|-----------|
| `HomeAssistantMetricsUnavailable` | Prometheus | warning | No successful scrape for 15 minutes |
| `HomeAssistantBackupStale` | Prometheus | warning | No successful automatic backup in 36 hours |
| `HomeAssistantLoginFailures` | Loki | warning | 3 or more failed logins or invalid tokens from one address in 15 minutes |
| `HomeAssistantIPBanned` | Loki | critical | Home Assistant banned an address |

The Loki rules are in `infrastructure/loki/home-assistant-rules.yml`, because the ruler loads rules only from the `monitoring` namespace.

### Scrape User

The token carries its user's rights, so it belongs to a dedicated non-admin user:

1. Under **Settings** > **People**, add a user named `prometheus` with **Can only log in from the local network** on and **Administrator** off. Give it a long random password and do not keep it; to rotate the token, the owner resets the password there. Local only also applies to its token: Home Assistant refuses it from any address that is not private, loopback or link-local, and through Home Assistant Cloud. Prometheus scrapes from the pod network, which is private.
2. Sign in as `prometheus` in a private window, enable an authenticator app, and create a long-lived access token under the profile's **Security** tab.
3. Store it in Vault, then sign out:

    ```bash
    read -rs VAL; export VAL
    make vault-put-secret SECRET_PATH=apps/home-assistant KEY=prometheus-token
    unset VAL
    ```

A rejected token counts as a failed login, so five failed scrapes ban the Prometheus pod's address. To rotate, create the new token, store it the same way, force an External Secrets refresh, wait for the scrape to succeed with it, and only then delete the old one ([secret rotation](../runbooks/secret-rotation.md)).

### Unbanning an Address

Bans persist in `/config/ip_bans.yaml`, and failed-login counts reset only on restart. Remove the address's entry, then restart:

```bash
kubectl -n home-automation exec -it deploy/home-assistant -- vi /config/ip_bans.yaml
kubectl -n home-automation rollout restart deploy/home-assistant
```

## Accounts

Every user has an authenticator app enabled. Household members get non-admin accounts under **Settings** > **People**, created by the owner; they sign in at `ha.home.seneker.io`.

## Onboarding

A new or recovered installation starts without the route and the attachment. Onboard through a port-forward, so no one else can claim the owner account:

```bash
kubectl -n home-automation port-forward deploy/home-assistant 8123:8123
```

Then open `http://localhost:8123`, create the owner account, enable an authenticator app under the profile's Security settings, and set the HTTP settings above. The URLs come from `configuration.yaml`.

## Credentials Home Assistant Holds

None yet. Record each integration's credential here, so it can be revoked.
