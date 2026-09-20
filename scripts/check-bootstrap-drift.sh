#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export KUBECONFIG="${KUBECONFIG:-$ROOT/kubeconfig}"
status=0
for dir in k8s/bootstrap/*/; do
  [[ -f "$dir/kustomization.yml" ]] || continue
  # kubectl diff: 0=same, 1=different, >1=error. Never hide an API error as clean.
  result=0
  kubectl --request-timeout=30s diff --server-side --field-manager=kubectl -k "$dir" || result=$?
  if ((result > 1)); then
    echo "Could not check bootstrap drift: $dir" >&2
    exit "$result"
  elif ((result == 1)); then
    status=1
  fi
done
exit "$status"
