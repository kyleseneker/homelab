# ADR-031: NUT 2.8.5 Backport on the Proxmox Host

## Status

Accepted

## Context

The CyberPower CP1500PFCRM2U is connected to `homelabpve01` over USB. The `pve_ups`
Ansible role runs the `usbhid-ups` driver, `upsd` and `upsmon` from Debian packages,
and the [NUT exporter](../infrastructure/nut-exporter.md) scrapes `upsd`. Proxmox VE 9
is based on Debian trixie, which ships NUT 2.8.1.

The UPS fails some HID `GET_REPORT` requests when they arrive back to back, as they do
during full updates and reconnection, in about one update cycle in six. NUT releases
before 2.8.5 treat a transient `LIBUSB_ERROR_IO` as a lost device and reconnect. In
2.8.1 the error is also passed up as a stale `errno` (`Resource temporarily
unavailable`). Each reconnection sends another burst of requests, so reconnections
cascade. When the reopen also fails, `upsd` marks the data stale, which happens 50-80
times a day, and the exporter's scrapes fail. The same failures can make the driver
need several attempts to start.

NUT 2.8.5 skips a report that fails with an I/O error and reconnects only when every
poll in an update cycle fails
([nut#3259](https://github.com/networkupstools/nut/pull/3259), fixing
[nut#3116](https://github.com/networkupstools/nut/issues/3116) for the same CyberPower
USB ID). The reporters found that `pollonly`, `pollinterval`, `pollfreq`, `maxretry`,
`MAXAGE` and `DEADTIME` do not help, which matches the results on this host. Debian
ships 2.8.5-1 only in forky and sid, and trixie-backports has no NUT package
([package versions](https://qa.debian.org/madison.php?package=nut-server)).

## Decision

Rebuild Debian's 2.8.5-1 source package for trixie and install it on the Proxmox host
from this repository's GitHub releases.

- `packaging/nut/build.sh` downloads the source package with `dget`, which verifies the
  `.dsc` signature against the Debian keyring and the checksums of the source files. It
  adds the local revision `~homelab13+1` and builds the binary packages in a
  `debian:trixie` container.
- The `nut-backport` workflow builds on every change to `packaging/nut/` and publishes
  the packages and `SHA256SUMS` as a release on `main`. It does not replace an existing
  release; a new build needs a new local revision.
- The `pve_ups` role downloads the packages the host uses, checks the SHA-256 checksums
  pinned in its defaults and installs them.
- Return to the distribution package once trixie-backports or a later Proxmox VE
  release ships NUT 2.8.5 or later. The local revision sorts below Debian's `2.8.5-1`,
  so a host upgrade to a Debian release that ships it replaces the backport; a
  trixie-backports package needs the role changed back to the distribution packages.

## Alternatives Considered

- **Stay on 2.8.1**: Needs no maintenance, but keeps the stale-data windows, the scrape
  failures the alerts have to tolerate, and driver starts that need several attempts.
- **Install forky's binary packages**: Avoids a build, but puts packages built against
  Debian testing on the hypervisor, with dependencies trixie may not satisfy.
- **Patch 2.8.1 with the upstream fix**: A smaller change, but the fix also depends on
  the error propagation corrected in 2.8.2 and on driver code from three later
  releases, so the patches would have to be carried and rebased.
- **Build NUT from the upstream source**: Loses Debian's packaging: the systemd units,
  maintainer scripts and file layout the role relies on.

## Consequences

- Security and bug fixes for NUT on the host come from rebuilding this package until the
  distribution package returns. Debian's trixie updates for 2.8.1 no longer apply; the
  fix in `2.8.1-5+deb13u1` (`upsmon` clearing the calibration flag) has been upstream
  since 2.8.2.
- Rebuilding needs only a change to `NUT_DEBIAN_VERSION` or `LOCAL_REVISION` and new
  checksums in the role's defaults.
- A failed report read leaves that value unchanged for one update cycle instead of
  forcing a reconnection.
- Rolling back means installing Debian's 2.8.1 packages again with
  `--allow-downgrades`.
