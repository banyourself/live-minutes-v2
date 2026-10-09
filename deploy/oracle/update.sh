#!/bin/sh
set -eu
export MSYS_NO_PATHCONV=1

if [ $# -lt 2 ]; then
    echo "usage: deploy/oracle/update.sh ubuntu@VM_IP path/to/private.key" >&2
    exit 2
fi
host="$1"
key="$2"
cd "$(dirname "$0")/../.."
ssh_opts="-i $key -o StrictHostKeyChecking=accept-new"
work="$(mktemp -d .move.XXXXXX)"
trap 'rm -rf "$work"' EXIT

git archive --format=tar.gz -o "$work/app.tgz" HEAD
scp $ssh_opts "$work/app.tgz" "$host:/opt/live-minutes/app.tgz"

ssh $ssh_opts "$host" sh -s <<'EOF'
set -eu
cd /opt/live-minutes
rm -rf next
install -d next
tar -xzf app.tgz -C next
rm app.tgz
cp -p app/.env next/.env
rm -rf previous
mv app previous
mv next app
cd app
docker compose --profile tunnel up -d --build --remove-orphans
docker image prune -f >/dev/null
site="$(grep '^PUBLIC_URL=' .env | cut -d/ -f3)"
for i in $(seq 1 60); do
    if curl -fsS -H "Host: $site" http://127.0.0.1:8000/api/ready >/dev/null 2>&1; then echo "Updated and ready."; exit 0; fi
    sleep 3
done
docker compose logs --tail 50 web
exit 1
EOF
