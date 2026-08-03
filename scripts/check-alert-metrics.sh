#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

KUBECONFIG_PATH="${KUBECONFIG:-$ROOT/kubeconfig}"
PROM_NS="${PROM_NS:-monitoring}"
PROM_STS="${PROM_STS:-statefulset/prometheus-kube-prometheus-stack-prometheus}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

query() {
  enc="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1")"
  kubectl --kubeconfig "$KUBECONFIG_PATH" -n "$PROM_NS" exec -c prometheus "$PROM_STS" -- \
    wget -qO- "http://localhost:9090/api/v1/query?query=$enc" 2>/dev/null
}

if ! query 'vector(1)' | grep -q '"success"'; then
  echo "cannot reach Prometheus via $PROM_NS/$PROM_STS -- is the cluster reachable?"
  exit 2
fi

find k8s -name '*.yml' -print0 | xargs -0 grep -l 'kind: PrometheusRule' 2>/dev/null > "$TMP/files" || true

python3 - "$TMP/files" "$TMP/selectors" <<'PY'
import yaml, sys, re
files = [l.strip() for l in open(sys.argv[1]) if l.strip()]
FUNCS = set('''time vector scalar absent absent_over_time increase rate irate sum max min avg count count_values
quantile stddev stdvar topk bottomk predict_linear delta idelta deriv changes clamp clamp_max clamp_min round floor
ceil abs exp ln log2 log10 sqrt histogram_quantile label_replace label_join timestamp sort sort_desc last_over_time
max_over_time min_over_time avg_over_time sum_over_time count_over_time stddev_over_time quantile_over_time
group by on without and or unless offset bool group_left group_right ignoring if end'''.split())
out = []
for f in files:
    for doc in yaml.safe_load_all(open(f)):
        if not doc or doc.get('kind') != 'PrometheusRule':
            continue
        for g in doc['spec'].get('groups', []):
            for r in g.get('rules', []):
                name = r.get('alert') or r.get('record') or '?'
                expr = str(r.get('expr', ''))
                guarded = set()
                for a in re.finditer(r'absent(?:_over_time)?\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\{[^}]*\})?)', expr):
                    guarded.add(re.sub(r'\s+', '', a.group(1)))
                for m in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)(\{[^}]*\})?', expr):
                    metric, lbls = m.group(1), m.group(2) or ''
                    if metric in FUNCS or metric.isdigit():
                        continue
                    if '_' not in metric and not lbls:
                        continue
                    if expr[m.end():m.end()+1] == '(':
                        continue
                    if re.sub(r'\s+', '', metric + lbls) in guarded:
                        continue
                    out.append(f'{name}\t{metric}{lbls}')
seen, uniq = set(), []
for o in out:
    if o not in seen:
        seen.add(o); uniq.append(o)
open(sys.argv[2], 'w').write('\n'.join(uniq))
print(f'extracted {len(uniq)} unique selectors from {len(files)} PrometheusRule files')
PY

fail=0; checked=0
while IFS="$(printf '\t')" read -r alert sel; do
  [ -z "${sel:-}" ] && continue
  checked=$((checked + 1))
  res="$(query "$sel")"
  if ! echo "$res" | grep -q '"success"'; then
    echo "  QUERY ERROR  $alert -> $sel"; fail=$((fail + 1)); continue
  fi
  if echo "$res" | grep -q '"result":\[\]'; then
    echo "  NO SERIES    $alert -> $sel"; fail=$((fail + 1))
  fi
done < "$TMP/selectors"

echo
if [ "$fail" -gt 0 ]; then
  echo "FAILED: $fail of $checked selectors match no series."
  echo "An alert whose selector matches nothing can never fire, yet reports health=ok."
  exit 1
fi
echo "OK: all $checked alert selectors match at least one live series"
