#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UTXO_FILE="${ROOT_DIR}/data/simulation-runs/utxo-runs.json"
ACCOUNT_FILE="${ROOT_DIR}/data/simulation-runs/account-runs.json"
WALLET_FILE="${ROOT_DIR}/data/multiuser/wallet-ledger.json"

mkdir -p "${ROOT_DIR}/data/simulation-runs" "${ROOT_DIR}/data/multiuser"

cat > "${UTXO_FILE}" <<'EOF'
{
  "schema_version": 1,
  "updated_at": "1970-01-01T00:00:00+00:00",
  "runs": []
}
EOF

cat > "${ACCOUNT_FILE}" <<'EOF'
{
  "schema_version": 1,
  "updated_at": "1970-01-01T00:00:00+00:00",
  "runs": []
}
EOF

cat > "${WALLET_FILE}" <<'EOF'
{
  "schema_version": 1,
  "updated_at": "1970-01-01T00:00:00+00:00",
  "current_revision_id": "",
  "snapshot": {
    "users": [],
    "wallets": [],
    "policies": [],
    "risk_profiles": [],
    "utxos": [],
    "transfers": [],
    "alerts": []
  },
  "revisions": []
}
EOF

echo "Persistence JSON reset completed:"
echo "- ${UTXO_FILE}"
echo "- ${ACCOUNT_FILE}"
echo "- ${WALLET_FILE}"
