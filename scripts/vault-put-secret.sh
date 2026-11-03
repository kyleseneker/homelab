#!/usr/bin/env bash
# Patch existing KV v2 data; create only if no version has ever existed.
set -euo pipefail
: "${VAULT_TOKEN:?Export VAULT_TOKEN first}"
: "${SECRET_PATH:?Set SECRET_PATH}"
: "${KEY:?Set KEY}"
# Without an exported VAL, prompt without echo so the value stays out of history.
if [[ -z "${VAL:-}" ]]; then
  if [[ ! -t 0 ]]; then
    echo "Set VAL, or run from a terminal to be prompted." >&2
    exit 1
  fi
  read -rsp "Value for homelab/$SECRET_PATH $KEY: " VAL
  echo >&2
  if [[ -z "$VAL" ]]; then
    echo "Empty value; nothing written." >&2
    exit 1
  fi
  export VAL
fi
payload="$(python3 -c 'import json,os; print(json.dumps({os.environ["KEY"]: os.environ["VAL"]}))')"
if patch_error="$(printf '%s' "$payload" | vault kv patch "homelab/$SECRET_PATH" - 2>&1 >/dev/null)"; then
  exit 0
fi
# A new path answers the patch with 404, so its error is shown only if creating
# fails too. CAS=0 prevents an authorization, network or concurrent-write
# failure on patch from replacing an existing secret and discarding its other keys.
if ! printf '%s' "$payload" | vault kv put -cas=0 "homelab/$SECRET_PATH" - >/dev/null; then
  printf 'The patch before it failed with:\n%s\n' "$patch_error" >&2
  exit 1
fi
