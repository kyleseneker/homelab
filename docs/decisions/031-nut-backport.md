# ADR-031: NUT Backport on the Proxmox Host

## Status

Accepted

## Context

The CyberPower CP1500PFCRM2U is connected to `homelabpve01` over USB. The `pve_ups`
Ansible role runs the `usbhid-ups` driver, `upsd` and `upsmon` from Debian packages,
and the [NUT exporter](../infrastructure/nut-exporter.md) scrapes `upsd`. Proxmox VE 9
is based on Debian trixie, whose NUT release predates the fix described below.

The UPS fails some HID `GET_REPORT` requests when they arrive back to back, as they do
during full updates and reconnection, in about one update cycle in six. Older NUT
releases treat a transient `LIBUSB_ERROR_IO` as a lost device and reconnect, and
trixie's release also passes the error up as a stale `errno` (`Resource temporarily
unavailable`). Each reconnection sends another burst of requests, so reconnections
cascade. When the reopen also fails, `upsd` marks the data stale, which happens 50-80
times a day, and the exporter's scrapes fail. The same failures can make the driver
need several attempts to start.

Newer NUT releases skip a report that fails with an I/O error and reconnect only when
every poll in an update cycle fails
([nut#3259](https://github.com/networkupstools/nut/pull/3259), fixing
[nut#3116](https://github.com/networkupstools/nut/issues/3116) for the same CyberPower
USB ID). The reporters found that `pollonly`, `pollinterval`, `pollfreq`, `maxretry`,
`MAXAGE` and `DEADTIME` do not help, which matches the results on this host. Debian
ships a release with that fix only in forky and sid, and trixie-backports has no NUT package
([package versions](https://qa.debian.org/madison.php?package=nut-server)).

## Decision

Rebuild Debian's forky NUT source package for trixie and install it on the Proxmox host
from a signed APT repository, [kyleseneker/apt](https://github.com/kyleseneker/apt),
served by GitHub Pages at `https://kyleseneker.github.io/apt`.

- The repository's build script downloads the source package with `dget`, which
  verifies the `.dsc` signature against the Debian keyring and the checksums of the
  source files. It adds a `~homelab` local revision and builds the binary
  packages in a `debian:trixie` container.
- The build applies upstream fixes that are not in a NUT release yet as Debian patches.
  It carries [edc06fb](https://github.com/networkupstools/nut/commit/edc06fb39435b892d5daeec53cb4845cb12d1d50)
  ([nut#3136](https://github.com/networkupstools/nut/issues/3136)), which fixes a
  regression in that release. When both report descriptor reads fail, it retries with
  lengths read past the end of an array and can accept a truncated descriptor. The driver then
  runs with no readings and an empty `ups.status`, which happened on about one start in
  eight on this UPS. With the fix the driver exits and systemd starts it again.
- Its workflow publishes each package version once. It adds the packages to `pool/`,
  regenerates the indexes with `apt-ftparchive` and signs `InRelease` with a dedicated
  ed25519 key. A published file is never replaced; a new build needs a new local
  revision.
- The `pve_ups` role installs the repository's public key from this repository, adds
  the source with `Signed-By`, and pins the repository to priority 1 except for the
  NUT packages. It installs `nut`, `nut-client` and `nut-server` at the pinned version
  with `apt`.
- Return to the distribution package once trixie-backports or a later Proxmox VE
  release ships a NUT version with the fix. The local revision sorts below Debian's own
  revision of the same release, so a host upgrade to a Debian release that ships it
  replaces the backport; a
  trixie-backports package needs the role changed back to the distribution packages.

## Alternatives Considered

- **Stay on trixie's NUT**: Needs no maintenance, but keeps the stale-data windows, the scrape
  failures the alerts have to tolerate, and driver starts that need several attempts.
- **Install forky's binary packages**: Avoids a build, but puts packages built against
  Debian testing on the hypervisor, with dependencies trixie may not satisfy.
- **Patch trixie's NUT with the upstream fix**: A smaller change, but the fix also
  depends on an error-propagation fix and driver code from several later releases, so the patches would have to be carried and rebased.
- **Build NUT from the upstream source**: Loses Debian's packaging: the systemd units,
  maintainer scripts and file layout the role relies on.
- **Publish the packages as release assets of this repository**: Needs no signing key,
  but presents a package as a release of the homelab, and the role has to download,
  verify and install the files itself, including the ordering that `nut-client`'s
  `Breaks` on older `nut-server` requires and the handling of modified configuration
  files.
- **Publish the packages as OCI artifacts in GitHub's container registry**: GitHub
  Packages has no Debian registry, so the host would need an OCI client such as `oras`,
  and apt could not use it as a source.

## Consequences

- Security and bug fixes for NUT on the host come from rebuilding this package until the
  distribution package returns. Debian's trixie updates for NUT no longer apply; the
  trixie fixes published so far, such as `upsmon` clearing the calibration flag, are
  already in the backported release.
- Each carried patch is dropped when the package is rebuilt from a NUT release that
  includes it.
- The signing key expires on 2031-11-13. The private key exists only as the
  repository's `APT_SIGNING_KEY` Actions secret. Replacing the key means updating the
  public key in both repositories and re-signing the indexes.
- The pin keeps the repository from replacing any package outside the NUT set, even if
  it later publishes one.
- `apt-get update` on the Proxmox host depends on GitHub Pages for this source.
- A failed report read leaves that value unchanged for one update cycle instead of
  forcing a reconnection.
- Rolling back means removing the pin and installing trixie's NUT packages again with
  `--allow-downgrades`.
