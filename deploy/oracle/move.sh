#!/bin/sh
set -eu
export MSYS_NO_PATHCONV=1

if [ $# -lt 2 ]; then
    echo "usage: deploy/oracle/move.sh ubuntu@VM_IP path/to/private.key" >&2
    exit 2
fi
host="$1"
key="$2"
cd "$(dirname "$0")/../.."
ssh_opts="-i $key -o StrictHostKeyChecking=accept-new"
work="$(mktemp -d .move.XXXXXX)"
trap 'rm -rf "$work"' EXIT

tunnel_dir="$(grep '^TUNNEL_DIR=' .env | cut -d= -f2- | tr -d '\r')"
[ -f "$tunnel_dir/config.yml" ] || { echo "no config.yml in $tunnel_dir" >&2; exit 1; }

ssh $ssh_opts "$host" true

git archive --format=tar.gz -o "$work/app.tgz" HEAD
tar -czf "$work/tunnel.tgz" -C "$tunnel_dir" .
tr -d '\r' < .env | grep -v -e '^TUNNEL_DIR=' -e '^BACKUP_DIR=' > "$work/env"
printf '%s\n' "TUNNEL_DIR=/opt/live-minutes/tunnel" "BACKUP_DIR=/opt/live-minutes/backups" >> "$work/env"

docker compose --profile tunnel stop tunnel web worker backup
docker compose exec -T db pg_dump -U liveminutes -d liveminutes -Fc > "$work/db.dump"
docker compose run --rm --no-deps -T --entrypoint tar web -czf - -C /data/files . > "$work/files.tgz"

ssh $ssh_opts "$host" "install -d -m 700 /opt/live-minutes/incoming"
scp $ssh_opts "$work/app.tgz" "$work/tunnel.tgz" "$work/env" "$work/db.dump" "$work/files.tgz" "$host:/opt/live-minutes/incoming/"

ssh $ssh_opts "$host" sh -s <<'EOF'
set -eu
export MSYS_NO_PATHCONV=1
cd /opt/live-minutes
in=incoming
install -d -m 700 tunnel
tar -xzf $in/tunnel.tgz -C tunnel
install -d app
tar -xzf $in/app.tgz -C app
install -m 600 $in/env app/.env
cd app
docker compose build
docker compose up -d db
until docker compose exec -T db pg_isready -U liveminutes -d liveminutes >/dev/null 2>&1; do sleep 2; done
docker compose exec -T db pg_restore -U liveminutes -d liveminutes --clean --if-exists --no-owner < ../$in/db.dump
docker compose run --rm --no-deps -T --entrypoint tar web -xzf - -C /data/files < ../$in/files.tgz
docker compose --profile tunnel up -d
rm -rf ../$in
site="$(grep '^PUBLIC_URL=' .env | cut -d/ -f3)"
for i in $(seq 1 60); do
    if curl -fsS -H "Host: $site" http://127.0.0.1:8000/api/ready >/dev/null 2>&1; then echo "Live Minutes is running on Oracle."; exit 0; fi
    sleep 3
done
docker compose logs --tail 50 web
exit 1
EOF

echo "Your PC's copy is stopped. To switch back: docker compose --profile tunnel up -d"
