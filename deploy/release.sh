#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/crypto-platform

tag=${1:?Pass the immutable image tag}
repository=${2:?Pass owner/repository}
[[ "$tag" =~ ^[a-f0-9]{40}$ ]] || { echo 'Expected a commit SHA image tag' >&2; exit 1; }
[[ "$repository" =~ ^[a-z0-9_.-]+/[a-z0-9_.-]+$ ]] || exit 1
test -f .env.production && test -f tls/fullchain.pem && test -f tls/privkey.pem
domain=$(sed -n 's/^APP_DOMAIN=//p' .env.production | tail -1)
[[ "$domain" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ ]] || { echo 'Invalid APP_DOMAIN' >&2; exit 1; }
openssl x509 -in tls/fullchain.pem -checkend 604800 -noout
openssl x509 -in tls/fullchain.pem -checkhost "$domain" -noout
cert_key=$(openssl x509 -in tls/fullchain.pem -pubkey -noout | openssl pkey -pubin -outform der | sha256sum | cut -d' ' -f1)
private_key=$(openssl pkey -in tls/privkey.pem -pubout -outform der | sha256sum | cut -d' ' -f1)
[[ "$cert_key" == "$private_key" ]] || { echo 'TLS key does not match certificate' >&2; exit 1; }

tmp=$(mktemp .release.env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
printf 'BACKEND_IMAGE=ghcr.io/%s-backend:%s\nFRONTEND_IMAGE=ghcr.io/%s-frontend:%s\n' "$repository" "$tag" "$repository" "$tag" > "$tmp"
compose=(docker compose --env-file .env.production --env-file "$tmp" -f compose.prod.yml)
"${compose[@]}" config --quiet
"${compose[@]}" pull
"${compose[@]}" run --rm --no-deps migrate python -m app.ops.preflight
"${compose[@]}" up -d postgres mongodb redis

if test -f .release.env; then
    # No schema change may start before both databases are recoverable offsite.
    /opt/crypto-platform/deploy/backup.sh
    cp .release.env .release.previous.env
fi

rollback() {
    if test -f .release.previous.env; then
        cp .release.previous.env .release.env
        docker compose --env-file .env.production --env-file .release.env -f compose.prod.yml up -d --no-deps backend frontend gateway market-ingestion trading-worker notification-worker || true
    fi
}
trap 'rollback; rm -f "$tmp"' ERR

"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --no-deps backend frontend
ready=false
for attempt in $(seq 1 60); do
    if "${compose[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready',timeout=3)" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 3
done
if [[ "$ready" != true ]]; then
    echo 'Backend did not become ready' >&2
    false
fi
"${compose[@]}" up -d --no-deps gateway market-ingestion trading-worker notification-worker
ready=false
for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --resolve "${domain}:443:127.0.0.1" "https://${domain}/api/v1/health" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [[ "$ready" != true ]]; then
    echo 'HTTPS gateway did not become ready' >&2
    false
fi
mv "$tmp" .release.env
trap - ERR EXIT
echo "Release $tag healthy"
