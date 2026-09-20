#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
rendered=0

val() { sed -n "s/^$2:[[:space:]]*//p" "$1" | head -1 | tr -d "'\"" ; }

echo "==> Validating config.yml against the ApplicationSet contract"
python3 scripts/check-appset-contract.py || exit 1
[[ "${1:-}" == "--contract-only" ]] && exit 0
for tool in helm kustomize kubeconform; do
  command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done
work="$(mktemp -d)"
schema_work="$(mktemp -d)"
if [[ "${KEEP_RENDERED:-false}" == true ]]; then
  echo "Rendered output directory: $work"
  echo "Generated schema directory: $schema_work"
else
  trap 'rm -rf "$work" "$schema_work"' EXIT
fi
kube_version="$(python3 -c 'import yaml; print(yaml.safe_load(open("ansible/group_vars/all/vars.yml"))["k8s_control_plane_version"])')"

echo "==> Rendering apps from config.yml"
while IFS= read -r cfg; do
  dir="$(dirname "$cfg")"
  app="$(val "$cfg" appName)"
  src="$(val "$cfg" sourceType)"
  ns="$(val "$cfg" namespace)"; ns="${ns:-default}"

  if [ "$src" = "helm" ]; then
    repo="$(val "$cfg" chartRepo)"
    name="$(val "$cfg" chartName)"
    ver="$(val "$cfg" chartVersion)"
    if [ -z "$repo" ] || [ -z "$name" ] || [ -z "$ver" ]; then
      echo "  FAIL $app -- sourceType=helm but chartRepo/chartName/chartVersion incomplete ($cfg)"
      fail=$((fail+1)); continue
    fi
    if [[ "$repo" == http* ]]; then
      chart_args=(--repo "$repo" "$name")
    else
      chart_args=("oci://${repo}/${name}")
    fi
    if out=$(helm template "$app" "${chart_args[@]}" --version "$ver" \
               --namespace "$ns" --kube-version "$kube_version" --include-crds \
               --api-versions monitoring.coreos.com/v1 --api-versions monitoring.coreos.com/v1/ServiceMonitor \
               --api-versions gateway.networking.k8s.io/v1 --api-versions gateway.networking.k8s.io/v1/HTTPRoute \
               -f "$dir/values.yml" 2>"$work/tool.log"); then
      rendered=$((rendered+1))
      printf '%s\n' "$out" > "$work/rendered-$rendered.yml"
    else
      echo "  FAIL $app -- helm template failed"
      { printf '%s\n' "$out"; cat "$work/tool.log"; } | tail -5 | sed 's/^/        /'
      fail=$((fail+1))
    fi
  else
    path="$(val "$cfg" gitPath)"
    if [ -z "$path" ]; then
      echo "  FAIL $app -- sourceType=$src but no gitPath ($cfg)"
      fail=$((fail+1)); continue
    fi
    if [ ! -d "$path" ]; then
      echo "  FAIL $app -- gitPath does not exist: $path"
      fail=$((fail+1)); continue
    fi
    if [ -f "$path/kustomization.yml" ] || [ -f "$path/kustomization.yaml" ]; then
      if out=$(kustomize build "$path" 2>"$work/tool.log"); then
        rendered=$((rendered+1))
      else
        echo "  FAIL $app -- kustomize build $path failed"
        { printf '%s\n' "$out"; cat "$work/tool.log"; } | tail -5 | sed 's/^/        /'
        fail=$((fail+1))
      fi
    else
      if out=$(python3 -c "
import sys,glob,yaml
n=0
for f in sorted(glob.glob('$path/*.yml')):
    list(yaml.safe_load_all(open(f))); n+=1
print(n)
" 2>"$work/tool.log"); then
        rendered=$((rendered+1))
      else
        echo "  FAIL $app -- unparseable YAML in $path"
        { printf '%s\n' "$out"; cat "$work/tool.log"; } | tail -5 | sed 's/^/        /'
        fail=$((fail+1))
      fi
    fi
  fi
done < <(find k8s/clusters -name config.yml | sort)

echo "==> Building every kustomization"
while IFS= read -r k; do
  d="$(dirname "$k")"
  if out=$(kustomize build "$d" 2>"$work/tool.log"); then
    rendered=$((rendered+1))
    printf '%s\n' "$out" > "$work/rendered-$rendered.yml"
  else
    echo "  FAIL kustomize build $d"
    { printf '%s\n' "$out"; cat "$work/tool.log"; } | tail -5 | sed 's/^/        /'
    fail=$((fail+1))
  fi
done < <(find k8s \( -name kustomization.yml -o -name kustomization.yaml \) | sort)

echo "==> Validating source and rendered manifests against schemas"
if ! RENDERED_MANIFESTS_DIR="$work" ./scripts/gen-crd-schemas.sh "$schema_work"; then
  echo "  FAIL could not generate schemas from pinned CRDs"
  fail=$((fail+1))
else
  if ! kubeconform -strict -kubernetes-version "$kube_version" \
      -schema-location default \
      -schema-location "$schema_work/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json" \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
      -skip Kustomization,CustomResourceDefinition \
      -ignore-filename-pattern '.*kustomization\.(yml|yaml)$' \
      -ignore-filename-pattern '.*config\.yml$' \
      -ignore-filename-pattern '.*values\.yml$' \
      -ignore-filename-pattern '.*slack-app-manifest\.json$' \
      -summary k8s/ "$work/"; then
    fail=$((fail+1))
  fi
fi

echo "==> Checking for orphaned manifests"
while IFS= read -r k; do
  d="$(dirname "$k")"
  for f in "$d"/*.yml "$d"/*.yaml; do
    [[ -f "$f" ]] || continue
    b="$(basename "$f")"
    case "$b" in kustomization.yml|kustomization.yaml|config.yml|values.yml) continue ;; esac
    if ! grep -qE "^[[:space:]]*-[[:space:]]+$b\$" "$k"; then
      echo "  FAIL $f is not referenced by $k -- it will never be applied"
      fail=$((fail+1))
    fi
  done
done < <(find k8s \( -name kustomization.yml -o -name kustomization.yaml \) | sort)

echo
if [ "$fail" -gt 0 ]; then
  echo "FAILED: $fail problem(s); $rendered rendered cleanly"
  exit 1
fi
echo "OK: $rendered manifests rendered cleanly"
