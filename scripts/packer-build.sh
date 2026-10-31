#!/usr/bin/env bash
# Build the Packer node template with a temporary Proxmox token scoped to the
# build. The token expires after 24 hours and is revoked when this script exits.
# Extra arguments pass through to `packer build`, e.g. -var iso_file=local:iso/x.iso.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PVE_HOST="${PVE_HOST:-homelabpve01}"
PVE_NODE="${PVE_NODE:-$PVE_HOST}"
PVE_SSH="${PVE_SSH:-root@$(awk '/ansible_host:/ {print $2; exit}' "$ROOT/ansible/inventory/$PVE_HOST/hosts.yml")}"
PVE_SSH_KEY="${PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_homelab}"
TEMPLATE_ID="${TEMPLATE_ID:-9000}"
NETWORK_BRIDGE="${NETWORK_BRIDGE:-vmbr0}"
ISO_STORAGE="${ISO_STORAGE:-local}"
DISK_STORAGE="${DISK_STORAGE:-local-lvm}"
BUILD_USER="packer-build@pve"
BUILD_ROLE="PackerBuildISO"

ssh_args=(-o BatchMode=yes -o ConnectTimeout=10)
if [[ -f "$PVE_SSH_KEY" ]]; then
  ssh_args+=(-i "$PVE_SSH_KEY" -o IdentitiesOnly=yes)
fi
pve() { ssh "${ssh_args[@]}" "$PVE_SSH" "$@"; }

if pve "qm status $TEMPLATE_ID" >/dev/null 2>&1; then
  echo "VM $TEMPLATE_ID already exists. Back it up and remove it before rebuilding." >&2
  exit 1
fi
if pve "pveum user list --output-format json" | python3 -c \
  'import json, sys; sys.exit(0 if any(u["userid"] == sys.argv[1] for u in json.load(sys.stdin)) else 1)' "$BUILD_USER"; then
  echo "$BUILD_USER already exists from another build. Delete it and role $BUILD_ROLE first." >&2
  exit 1
fi

work="$(mktemp -d)"
chmod 700 "$work"
created=false
cleanup() {
  local rc=$?
  if $created; then
    pve "pveum user delete $BUILD_USER; pveum role delete $BUILD_ROLE" >/dev/null 2>&1 ||
      echo "WARNING: revoke failed; delete $BUILD_USER and role $BUILD_ROLE on $PVE_SSH." >&2
  fi
  rm -rf "$work"
  exit "$rc"
}
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -C "packer-build-$TEMPLATE_ID" -f "$work/build_ed25519"

created=true
umask 077
# Seed ISO removal needs Datastore.Allocate on the ISO storage in Proxmox VE 9.
pve "set -euo pipefail
exp=\$(date -d '+24 hours' +%s)
pveum role add $BUILD_ROLE -privs Datastore.Allocate,Datastore.AllocateTemplate,Datastore.AllocateSpace,Datastore.Audit
pveum user add $BUILD_USER -expire \$exp -comment 'Temporary Packer template build'
pveum aclmod /vms/$TEMPLATE_ID -user $BUILD_USER -role PVEVMAdmin
pveum aclmod /storage/$DISK_STORAGE -user $BUILD_USER -role PVEDatastoreUser
pveum aclmod /storage/$ISO_STORAGE -user $BUILD_USER -role $BUILD_ROLE
pveum aclmod /sdn/zones/localnetwork/$NETWORK_BRIDGE -user $BUILD_USER -role PVESDNUser
pveum aclmod /nodes/$PVE_NODE -user $BUILD_USER -role PVEAuditor
pveum user token add $BUILD_USER build --privsep 0 --expire \$exp --output-format json" |
  python3 -c '
import json, sys
token = json.load(sys.stdin)
print("proxmox_api_token_id     = \"%s\"" % token["full-tokenid"])
print("proxmox_api_token_secret = \"%s\"" % token["value"])
' >"$work/token.pkrvars.hcl"

cd "$ROOT/packer/k8s-node"
# The build VM only needs the generated key; keep agent identities out of it.
env -u SSH_AUTH_SOCK packer build \
  -var-file="$work/token.pkrvars.hcl" \
  -var "proxmox_url=https://${PVE_SSH#*@}:8006/api2/json" \
  -var "template_id=$TEMPLATE_ID" \
  -var "network_bridge=$NETWORK_BRIDGE" \
  -var "iso_storage_pool=$ISO_STORAGE" \
  -var "disk_storage_pool=$DISK_STORAGE" \
  -var "proxmox_node=$PVE_NODE" \
  -var "ssh_public_key=$(cat "$work/build_ed25519.pub")" \
  -var "ssh_private_key_file=$work/build_ed25519" \
  "$@" .
