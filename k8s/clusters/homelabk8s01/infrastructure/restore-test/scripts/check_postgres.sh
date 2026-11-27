set -eu
dump="$1"
shift
export PGHOST=127.0.0.1 PGUSER=postgres HOME=/tmp
tries=0
until pg_isready --quiet; do
  tries=$((tries + 1))
  if [ "$tries" -ge 120 ]; then
    echo '{"started": false}'
    exit 1
  fi
  sleep 2
done
createdb restored
if ! pg_restore --dbname=restored --no-owner --no-acl --exit-on-error --single-transaction "$dump" 2>/tmp/restore.log; then
  echo '{"started": true, "restored": false}'
  exit 1
fi
counts=""
for table in "$@"; do
  counts="$counts${counts:+, }'$table', (SELECT count(*) FROM $table)"
done
psql --dbname=restored --set=ON_ERROR_STOP=1 --tuples-only --no-align --command \
  "SELECT json_build_object('started', true, 'restored', true, 'version', current_setting('server_version'), 'rows', json_build_object($counts))"
