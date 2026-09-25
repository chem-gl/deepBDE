#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/root/deepBDE
cd "$APP_DIR"

PREV=$(git rev-parse HEAD)
git fetch origin main
git reset --hard origin/main
git submodule update --init --recursive

if [ ! -f .env ]; then
    cp .env.example .env
    secret_key=$(openssl rand -hex 32)
    sed -i -E "s|^SECRET_KEY=.*|SECRET_KEY=${secret_key}|" .env

    set_env_var() {
        local name=$1 value=$2
        if grep -q "^${name}=" .env; then
            sed -i -E "s|^${name}=.*|${name}=${value}|" .env
        else
            printf '%s=%s\n' "$name" "$value" >> .env
        fi
    }

    set_env_var DEBUG False
    set_env_var DJANGO_ALLOWED_HOSTS deepbde.ginodilabio.com,www.deepbde.ginodilabio.com,test1.guzman-lopez.com,test2.guzman-lopez.com,localhost,127.0.0.1
    # Los dominios legacy son servidos por el mismo stack.
    set_env_var CSRF_TRUSTED_ORIGINS http://deepbde.ginodilabio.com,https://deepbde.ginodilabio.com,http://www.deepbde.ginodilabio.com,https://www.deepbde.ginodilabio.com,http://test1.guzman-lopez.com,https://test1.guzman-lopez.com,http://test2.guzman-lopez.com,https://test2.guzman-lopez.com
    set_env_var CORS_ALLOWED_ORIGINS http://deepbde.ginodilabio.com,https://deepbde.ginodilabio.com,http://www.deepbde.ginodilabio.com,https://www.deepbde.ginodilabio.com,http://test1.guzman-lopez.com,https://test1.guzman-lopez.com,http://test2.guzman-lopez.com,https://test2.guzman-lopez.com
    chmod 600 .env
fi

free_gb() {
    df --output=avail -BG / | tail -n 1 | tr -dc '0-9'
}

free_space=$(free_gb)
if [ "$free_space" -lt 8 ]; then
    docker builder prune -f --keep-storage 2GB
    docker image prune -f
    free_space=$(free_gb)
fi
if [ "$free_space" -lt 5 ]; then
    echo "Insufficient disk space: ${free_space}G free; at least 5G required before build" >&2
    exit 1
fi

COMPOSE=(docker compose -f compose.yml -f compose.prod.yml)
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --remove-orphans

healthcheck() {
    curl -fsS http://127.0.0.1:8002/api/v1/health/ >/dev/null \
        && curl -fsS -o /dev/null http://127.0.0.1:8082/
}

healthy=false
for _ in $(seq 1 180); do
    if healthcheck; then
        healthy=true
        break
    fi
    sleep 1
done

if [ "$healthy" != true ]; then
    "${COMPOSE[@]}" logs --tail=60 backend web >&2 || true
    set +e
    git reset --hard "$PREV"
    git submodule update --init --recursive
    "${COMPOSE[@]}" up -d --remove-orphans
    rollback_healthy=false
    for _ in $(seq 1 60); do
        if healthcheck; then
            rollback_healthy=true
            break
        fi
        sleep 1
    done
    if [ "$rollback_healthy" != true ]; then
        echo "Rollback healthcheck failed; inspect the previous deployment" >&2
    fi
    echo "ROLLBACK a $PREV aplicado"
    exit 1
fi

docker image prune -f
# El cache limitado acelera rebuilds sin permitir que consuman todo el disco.
docker builder prune -f --keep-storage 5GB

echo 'Deployment summary:'
docker compose -f compose.yml -f compose.prod.yml ps
