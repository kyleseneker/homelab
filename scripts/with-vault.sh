#!/usr/bin/env bash
# Run a command against a port-forward owned by this process.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$ROOT/kubeconfig}"
export VAULT_ADDR="http://127.0.0.1:${VAULT_PORT:-8200}"
work="$(mktemp -d)"
pid=""
cleanup() {
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
kubectl port-forward --address 127.0.0.1 -n "${VAULT_NS:-vault}" \
  "pod/${VAULT_POD:-vault-0}" "${VAULT_PORT:-8200}:8200" >"$work/forward.log" 2>&1 &
pid=$!
for ((attempt=0; attempt<100; attempt++)); do
  if ! kill -0 "$pid" 2>/dev/null; then
    cat "$work/forward.log" >&2
    exit 1
  fi
  if grep -q '^Forwarding from 127.0.0.1:' "$work/forward.log"; then
    "$@"
    exit $?
  fi
  sleep 0.1
done
echo 'Vault port-forward did not become ready.' >&2
exit 1
