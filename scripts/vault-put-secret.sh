#!/usr/bin/env bash
# Patch existing KV v2 data; create only if no version has ever existed.
set -euo pipefail
: "${VAULT_TOKEN:?Export VAULT_TOKEN first}"
: "${SECRET_PATH:?Set SECRET_PATH}"
: "${KEY:?Set KEY}"
: "${VAL:?Set VAL}"
payload="$(python3 -c 'import json,os; print(json.dumps({os.environ["KEY"]: os.environ["VAL"]}))')"
if printf '%s' "$payload" | vault kv patch "homelab/$SECRET_PATH" - >/dev/null; then
  exit 0
fi
# CAS=0 prevents an authorization, network or concurrent-write failure on patch
# from replacing an existing secret and discarding its other keys.
printf '%s' "$payload" | vault kv put -cas=0 "homelab/$SECRET_PATH" - >/dev/null
