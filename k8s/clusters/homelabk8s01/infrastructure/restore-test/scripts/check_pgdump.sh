set -eu
dump="$1"
stamp="$2"
entries=$(pg_restore --list "$dump" | grep -vc '^;')
pg_restore --file=/dev/null "$dump"
printf '{"toc_entries": %s, "bytes": %s, "timestamp": "%s"}\n' "$entries" "$(stat -c %s "$dump")" "$(cat "$stamp")"
