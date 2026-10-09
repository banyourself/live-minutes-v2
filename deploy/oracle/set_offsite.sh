#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."
env_file=.env
if [ ! -f "$env_file" ] || [ ! -f docker-compose.yml ]; then
    echo "run this on the server: sh /opt/live-minutes/app/deploy/oracle/set_offsite.sh" >&2
    exit 1
fi
trap 'stty echo 2>/dev/null || true' EXIT INT TERM

current() {
    grep "^$1=" "$env_file" | tail -n 1 | cut -d= -f2-
}

put() {
    tmp="$(mktemp "$env_file.XXXXXX")"
    chmod 600 "$tmp"
    grep -v "^$1=" "$env_file" > "$tmp" || true
    printf '%s=%s\n' "$1" "$2" >> "$tmp"
    mv "$tmp" "$env_file"
}

ask() {
    printf '%s: ' "$2"
    if [ "$3" = hidden ]; then
        stty -echo
        IFS= read -r value
        stty echo
        echo
    else
        IFS= read -r value
    fi
    value="$(printf '%s' "$value" | tr -d '[:space:]')"
    if [ -z "$value" ]; then
        echo "$2 was empty, so nothing was changed." >&2
        exit 1
    fi
    put "$1" "$value"
}

if [ "${1:-}" = status ]; then
    started=0
    tries=1
else
    [ -n "$(current OFFSITE_S3_ENDPOINT)" ] || ask OFFSITE_S3_ENDPOINT "R2 endpoint (https://<account id>.r2.cloudflarestorage.com)" shown
    [ -n "$(current OFFSITE_S3_BUCKET)" ] || ask OFFSITE_S3_BUCKET "Bucket name" shown
    [ -n "$(current OFFSITE_BACKUP_PUBLIC_KEY)" ] || ask OFFSITE_BACKUP_PUBLIC_KEY "Public key printed by offsite_keys.py" shown
    ask OFFSITE_S3_ACCESS_KEY_ID "R2 Access Key ID (hidden as you type or paste)" hidden
    ask OFFSITE_S3_SECRET_ACCESS_KEY "R2 Secret Access Key (hidden as you type or paste)" hidden
    echo "Saved to $(pwd)/$env_file. Restarting Live Minutes so it reads them."
    started="$(date +%s)"
    tries=36
    docker compose --profile tunnel up -d
    echo "Waiting for the first offsite upload (up to 3 minutes)."
fi
docker compose exec -T worker python - "$started" "$tries" <<'PY'
import sys
import time

from server.app import models
from server.app.db import SessionLocal

started = float(sys.argv[1])
for _ in range(int(sys.argv[2])):
    db = SessionLocal()
    try:
        row = db.get(models.PlatformSetting, "offsite_backup")
        state = dict((row.value if row else None) or {})
    finally:
        db.close()
    if state.get("last_error") and (state.get("last_error_at") or 0) >= started:
        print("Offsite backup failed: " + state["last_error"])
        sys.exit(1)
    if state.get("last_at") and state["last_at"] >= started:
        print("Offsite backup uploaded: " + ", ".join(state.get("uploaded", [])[-2:]))
        sys.exit(0)
    if started:
        time.sleep(5)
print("Nothing uploaded yet. The worker tries every hour. To check later: sh deploy/oracle/set_offsite.sh status")
PY
