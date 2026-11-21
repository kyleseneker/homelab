# Intel AMT Console Access

Out-of-band access to the MS-01 when Proxmox, its network or its VMs are down. The decision and firmware settings are in [ADR-017](../decisions/017-intel-amt-oob-management.md).

## What Each Path Gives You

| Need | Use | Notes |
|------|-----|-------|
| Power on, off, reset, graceful shutdown | Web UI at `https://192.168.99.5:16993`, or MeshCommander | Works with the host off; power policy is "ON in S0, ME Wake in S3, S4-5 (AC only)" |
| Host shell, kernel messages, emergency shell | MeshCommander Serial-over-LAN terminal | `ttyS4` on the host, set up by the `pve_serial_console` role; log in as `root` |
| Firmware setup, GRUB menu, early boot | MeshCommander remote desktop (KVM) | Goes black once the host boots, because the integrated GPU belongs to `homelabk8s01-node-3` |

AMT is reachable from the workstation range `192.168.10.160/27` and from the VPN ([ADR-016](../decisions/016-vlan-segmentation.md)). Log in as `admin` with the AMT password set in MEBx. The web UI cannot open either console.

## Start MeshCommander

Run MeshCommander in a disposable container on the workstation:

```sh
podman run -d --rm --name meshcommander -p 127.0.0.1:3000:3000 docker.io/library/node:22-alpine sh -c '
printf "nodejs_conf = openssl_init\n[openssl_init]\nssl_conf = ssl_sect\n[ssl_sect]\nsystem_default = system_default_sect\n[system_default_sect]\nOptions = UnsafeLegacyServerConnect\n" > /tmp/amt-openssl.cnf &&
cd /tmp && npm install --silent --no-audit --no-fund meshcommander@0.9.5-a &&
exec node --openssl-config=/tmp/amt-openssl.cnf node_modules/meshcommander --any'
```

Open `http://localhost:3000`. Stop it with `podman stop meshcommander`, which also removes the container.

AMT's TLS does not support secure renegotiation, and OpenSSL 3 refuses such servers by default. The OpenSSL setting allows them for this one process. Without it, **Connect** stays on "Loading" and no error is shown.

## Connect

1. **Add Computer**: host `192.168.99.5`, user `admin`, Security **TLS**. With Security set to None, MeshCommander uses port 16992, which CSME 16.1 removed, and also stays on "Loading".
2. **Terminal**: open **Serial-over-LAN Terminal**, click **Connect**, click inside the terminal and press Enter. Output from before you connected is not replayed, so the login prompt appears only after Enter.
3. **Remote desktop**: open it before rebooting the host, to see firmware setup and the GRUB menu.

## Recover a Host That Will Not Boot

1. Open the remote desktop and the Serial-over-LAN terminal in separate MeshCommander tabs.
2. Reset the host from **Power Actions**. Use a graceful shutdown first if Proxmox still responds.
3. In GRUB, on the remote desktop, choose **Advanced options** to boot an older kernel or recovery mode.
4. Once the kernel starts, follow it on the terminal: kernel messages and any emergency shell appear there, and the remote desktop goes black.
