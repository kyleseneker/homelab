#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${VAULT_TOKEN:?Export VAULT_TOKEN first}"
export SECRET_PATH=apps/media
for app in sonarr radarr prowlarr bazarr; do
  if [[ "$app" == bazarr ]]; then
    VAL="$(kubectl -n media exec deploy/bazarr -c main -- \
      python3 -c 'import yaml; print(yaml.safe_load(open("/config/config/config.yaml"))["auth"]["apikey"])')"
  else
    VAL="$(kubectl -n media exec "deploy/$app" -c main -- \
      sed -n 's:.*<ApiKey>\(.*\)</ApiKey>.*:\1:p' /config/config.xml)"
  fi
  [[ -n "$VAL" ]] || { echo "Could not read $app API key" >&2; exit 1; }
  export VAL KEY="$app-api-key"
  "$ROOT/scripts/vault-put-secret.sh"
  echo "$app: adopted"
done
