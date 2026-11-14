#!/usr/bin/env bash
set -euo pipefail

NUT_DEBIAN_VERSION="${NUT_DEBIAN_VERSION:-2.8.5-1}"
LOCAL_REVISION="${LOCAL_REVISION:-~homelab13+1}"
OUT="${1:-/out}"

export DEBIAN_FRONTEND=noninteractive
export DEBFULLNAME="homelab backport"
export DEBEMAIL="homelab-backport@invalid"

apt-get update
apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl debian-keyring devscripts dpkg-dev equivs

work="$(mktemp -d)"
cd "$work"
dget --extract "https://deb.debian.org/debian/pool/main/n/nut/nut_${NUT_DEBIAN_VERSION}.dsc"
cd "nut-${NUT_DEBIAN_VERSION%-*}"

dch --force-bad-version --newversion "${NUT_DEBIAN_VERSION}${LOCAL_REVISION}" --distribution trixie --force-distribution \
  "Rebuild of Debian ${NUT_DEBIAN_VERSION} for trixie."
mk-build-deps --install --remove --tool 'apt-get -y --no-install-recommends' debian/control
dpkg-buildpackage -us -uc -b

mkdir -p "$OUT"
for deb in ../*.deb; do
  cp "$deb" "$OUT/$(basename "$deb" | tr '~+' '-.')"
done
cd "$OUT"
sha256sum ./*.deb | sed 's# \./# #' > SHA256SUMS
cat SHA256SUMS
