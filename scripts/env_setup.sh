#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# env_setup.sh — Load environment variables from .env file
# ──────────────────────────────────────────────────────────
#
# Usage (must be sourced, not executed):
#   source scripts/env_setup.sh
#   . scripts/env_setup.sh
#
# Creates .env from .env.example if it does not exist.
# ──────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "[env_setup] Created .env from .env.example"
        echo "[env_setup] Edit .env to set your local PostgreSQL credentials."
    else
        echo "[env_setup] ERROR: .env.example not found at $ENV_EXAMPLE"
        return 1 2>/dev/null || exit 1
    fi
fi

set -a
while IFS='=' read -r key value; do
    key=$(echo "$key" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    [[ -z "$key" || "$key" == \#* ]] && continue
    value=$(echo "$value" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    export "$key=$value"
done < "$ENV_FILE"
set +a

echo "[env_setup] Loaded environment from $ENV_FILE"
echo "[env_setup] PERSISTENCE_BACKEND=${PERSISTENCE_BACKEND:-json}"
echo "[env_setup] DATABASE_URL=${DATABASE_URL:-(not set)}"
