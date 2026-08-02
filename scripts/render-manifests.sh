#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
rendered=0

val() { sed -n "s/^$2:[[:space:]]*//p" "$1" | head -1 | tr -d "'\"" ; }

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
               --namespace "$ns" -f "$dir/values.yml" 2>&1); then
      rendered=$((rendered+1))
    else
      echo "  FAIL $app -- helm template failed"
      echo "$out" | tail -5 | sed 's/^/        /'
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
      if out=$(kustomize build "$path" 2>&1); then
        rendered=$((rendered+1))
      else
        echo "  FAIL $app -- kustomize build $path failed"
        echo "$out" | tail -5 | sed 's/^/        /'
        fail=$((fail+1))
      fi
    else
      if out=$(python3 -c "
import sys,glob,yaml
n=0
for f in sorted(glob.glob('$path/*.yml')):
    list(yaml.safe_load_all(open(f))); n+=1
print(n)
" 2>&1); then
        rendered=$((rendered+1))
      else
        echo "  FAIL $app -- unparseable YAML in $path"
        echo "$out" | tail -5 | sed 's/^/        /'
        fail=$((fail+1))
      fi
    fi
  fi
done < <(find k8s/clusters -name config.yml | sort)

echo "==> Building every kustomization"
while IFS= read -r k; do
  d="$(dirname "$k")"
  if out=$(kustomize build "$d" 2>&1); then
    rendered=$((rendered+1))
  else
    echo "  FAIL kustomize build $d"
    echo "$out" | tail -5 | sed 's/^/        /'
    fail=$((fail+1))
  fi
done < <(find k8s -name kustomization.yml | sort)

echo "==> Checking for orphaned manifests"
while IFS= read -r k; do
  d="$(dirname "$k")"
  for f in "$d"/*.yml; do
    b="$(basename "$f")"
    case "$b" in kustomization.yml|config.yml|values.yml) continue ;; esac
    if ! grep -qE "^[[:space:]]*-[[:space:]]+$b\$" "$k"; then
      echo "  FAIL $f is not referenced by $k -- it will never be applied"
      fail=$((fail+1))
    fi
  done
done < <(find k8s -name kustomization.yml | sort)

echo
if [ "$fail" -gt 0 ]; then
  echo "FAILED: $fail problem(s); $rendered rendered cleanly"
  exit 1
fi
echo "OK: $rendered manifests rendered cleanly"
