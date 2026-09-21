#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${1:-$ROOT/.crd-schemas}"
mkdir -p "$OUT"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

val() { sed -n "s/^$2:[[:space:]]*//p" "$1" | head -1 | tr -d "'\"" ; }

count=0
touch "$work/pulled-charts"
while IFS= read -r cfg; do
  repo="$(val "$cfg" chartRepo)"
  name="$(val "$cfg" chartName)"
  ver="$(val "$cfg" chartVersion)"
  [ -n "$name" ] || continue
  chart="oci://${repo}/${name}"
  # Multiple clusters may pin the same chart; Helm cannot untar it twice.
  if grep -Fxq "${chart}@${ver}" "$work/pulled-charts"; then
    continue
  fi
  helm pull "oci://${repo}/${name}" --version "$ver" --untar --untardir "$work" >/dev/null 2>&1 || {
    echo "  FAILED to pull ${name} ${ver}" >&2; exit 1; }
  printf '%s\n' "${chart}@${ver}" >> "$work/pulled-charts"
  count=$((count+1))
done < <(grep -rl 'chartRepo: ghcr.io/kyleseneker/media-operator' k8s/clusters/*/apps/*/config.yml | sort)

python3 - "$work" "$OUT" <<'PY'
import glob, json, os, sys, yaml

# Kyverno CRD enums contain a plain '=' scalar, tagged specially by YAML1.1.
yaml.SafeLoader.add_constructor("tag:yaml.org,2002:value", lambda loader, node: loader.construct_scalar(node))
work, out = sys.argv[1], sys.argv[2]
n = 0
paths = glob.glob(os.path.join(work, "*", "crds", "*.yaml"))
paths += glob.glob(os.path.join(work, "*", "crds", "*.yml"))
paths += glob.glob("k8s/components/gateway-api/*.yml")
if os.environ.get("RENDERED_MANIFESTS_DIR"):
    paths += glob.glob(os.path.join(os.environ["RENDERED_MANIFESTS_DIR"], "rendered-*.yml"))
for path in sorted(paths):
    for doc in yaml.safe_load_all(open(path)):
        if not doc or doc.get("kind") != "CustomResourceDefinition":
            continue
        kind = doc["spec"]["names"]["kind"]
        for version in doc["spec"]["versions"]:
            schema = version.get("schema", {}).get("openAPIV3Schema")
            if not schema:
                continue
            schema.setdefault("$schema", "http://json-schema.org/draft-07/schema#")
            dest = os.path.join(out, f"{kind.lower()}_{version['name']}.json")
            with open(dest, "w") as fh:
                json.dump(schema, fh, indent=2)
            n += 1
print(f"  {n} CRD schemas written to {out}")
PY

echo "  ($count charts pulled)"
