#!/usr/bin/env bash
# =============================================================================
# demo_cli.sh — Full CLI demo for blockchain-data-model v2.8.1
# Covers: users, wallets, mint, transfer, exchange, treasury, policies, risk,
#         permissions, freeze, ban, soft delete, temp password, audit log.
# Usage: bash scripts/demo_cli.sh
# =============================================================================
set -e

STORE="data/multiuser/wallet-ledger.json"
CLI="py scripts/multiuser_wallet_cli.py --store-file $STORE"

# Token globals (populated during execution)
ADMIN_TOKEN=""
ALICE_WALLET_TOKEN=""
BOB_WALLET_TOKEN=""

# ── Colors ────────────────────────────────────────────────────────────────────
BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
DIM="\033[2m"
RESET="\033[0m"

# ── Helpers ───────────────────────────────────────────────────────────────────
section() {
  echo -e "\n${CYAN}${BOLD}══════════════════════════════════════════════════${RESET}"
  echo -e "${CYAN}${BOLD}  $1${RESET}"
  echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════${RESET}"
}

step() { echo -e "\n${YELLOW}${BOLD}▶ $1${RESET}"; }
ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }
note() { echo -e "${DIM}  # $1${RESET}"; }

# Run command AS ADMIN (requires ADMIN_TOKEN set)
adm() {
  local label="$1"; shift
  step "$label"
  $CLI --token "$ADMIN_TOKEN" "$@" --json
}

# Run command without user token (login, register, verify-integrity, etc.)
pub() {
  local label="$1"; shift
  step "$label"
  $CLI "$@" --json
}

# Run command that is expected to fail (non-zero exit)
expect_fail() {
  local label="$1"; shift
  step "$label"
  note "Fallo controlado esperado (set +e)"
  set +e
  $CLI --token "$ADMIN_TOKEN" "$@" --json
  RC=$?
  set -e
  if [ $RC -ne 0 ]; then
    ok "Fallo esperado — exit code=$RC"
  else
    echo -e "${RED}  ✗ Se esperaba error pero el comando tuvo exito${RESET}"
  fi
}

# Extract a field from JSON piped to stdin
# Usage: echo "$JSON" | jfield "['result']['key']"
jfield() { py -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }

# =============================================================================
echo -e "\n${BOLD}Blockchain Data Model v2.8.1 — Demo CLI completo${RESET}"
echo -e "${DIM}Reseteando datos persistidos...${RESET}"
bash scripts/reset_persistence_json.sh
ok "Store limpio: $STORE"

# =============================================================================
section "1 · USUARIOS — Registro, login y perfil"

step "[1] Registrar primer usuario (bootstrap → ADMIN automático)"
note "Ledger vacio: primer register ignora invitation-token y asigna ADMIN"
$CLI register --user-id u-alice --display-name "Alice Admin" \
  --password alice1234 --json

step "[2] Login como alice → obtener JWT ADMIN"
LOGIN_JSON=$($CLI login --user-id u-alice --password alice1234 --json)
echo "$LOGIN_JSON"
ADMIN_TOKEN=$(echo "$LOGIN_JSON" | jfield "['result']['access_token']")
ok "Token ADMIN obtenido (${ADMIN_TOKEN:0:20}...)"

adm "[3] Crear usuario bob (OPERATOR) con perfil completo" \
  create-user \
  --user-id u-bob --display-name "Bob Operator" \
  --username bobsmith --email bob@example.com \
  --first-name Bob --last-name Smith \
  --password bob1234

adm "[4] Crear usuario carlos (VIEWER)" \
  create-user \
  --user-id u-carlos --display-name "Carlos Viewer" \
  --username carlosv --email carlos@example.com \
  --first-name Carlos --last-name Viewer \
  --password carlos1234

adm "[5] Asignar rol OPERATOR a bob" \
  assign-role --user-id u-bob --role OPERATOR

adm "[6] Asignar rol VIEWER a carlos" \
  assign-role --user-id u-carlos --role VIEWER

adm "[7] Actualizar perfil de carlos (email)" \
  update-profile \
  --user-id u-carlos --email carlos.viewer@example.com

adm "[8] Listar usuarios" list-users

# =============================================================================
section "2 · WALLETS — Creacion y tokens"

step "[9] Crear wallet UTXO para alice"
ALICE_WALLET_JSON=$($CLI --token "$ADMIN_TOKEN" create-wallet \
  --user-id u-alice --wallet-id wallet_user_alice_utxo_01 --model UTXO --json)
echo "$ALICE_WALLET_JSON"
ALICE_WALLET_TOKEN=$(echo "$ALICE_WALLET_JSON" | jfield "['result']['auth_token']")
ok "Wallet token alice: ${ALICE_WALLET_TOKEN:0:20}..."

step "[10] Crear wallet UTXO para bob"
BOB_WALLET_JSON=$($CLI --token "$ADMIN_TOKEN" create-wallet \
  --user-id u-bob --wallet-id wallet_user_bravo_utxo_02 --model UTXO --json)
echo "$BOB_WALLET_JSON"
BOB_WALLET_TOKEN=$(echo "$BOB_WALLET_JSON" | jfield "['result']['auth_token']")
ok "Wallet token bob: ${BOB_WALLET_TOKEN:0:20}..."

adm "[11] Crear wallet ACCOUNT para carlos" \
  create-wallet --user-id u-carlos --wallet-id wallet_user_carlos_acc_03 --model ACCOUNT

adm "[12] Listar todas las wallets" list-wallets

# =============================================================================
section "3 · MINT y TRANSFERENCIAS"

adm "[13] Mint 100 USDX → alice" mint --wallet-id wallet_user_alice_utxo_01 --amount 100

adm "[14] Balance alice (pre-transferencia)" balance --wallet-id wallet_user_alice_utxo_01

step "[15] Transferencia alice → bob (nonce=1, fee=1)"
note "--token = JWT usuario (permisos); --sender-token = token de wallet (anti-replay)"
$CLI --token "$ADMIN_TOKEN" transfer \
  --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 20 --fee 1 \
  --sender-token "$ALICE_WALLET_TOKEN" --expected-nonce 1 --json

step "[16] Transferencia alice → bob (nonce=2, fee=0.5)"
$CLI --token "$ADMIN_TOKEN" transfer \
  --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 10 --fee 0.5 \
  --sender-token "$ALICE_WALLET_TOKEN" --expected-nonce 2 --json

adm "[17] Balance alice (post)" balance --wallet-id wallet_user_alice_utxo_01
adm "[18] Balance bob" balance --wallet-id wallet_user_bravo_utxo_02
adm "[19] UTXOs bob" list-utxos --wallet-id wallet_user_bravo_utxo_02

step "[20] Refresh token alice (rota wallet token)"
REFRESH_JSON=$($CLI --token "$ADMIN_TOKEN" \
  refresh-token --user-id u-alice --wallet-id wallet_user_alice_utxo_01 \
  --current-token INVALID --json)
echo "$REFRESH_JSON"
ALICE_WALLET_TOKEN=$(echo "$REFRESH_JSON" | jfield "['result']['auth_token']")
ok "Wallet token alice renovado: ${ALICE_WALLET_TOKEN:0:20}..."

step "[21] Transferencia con token renovado (nonce=3)"
$CLI --token "$ADMIN_TOKEN" transfer \
  --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 5 --sender-token "$ALICE_WALLET_TOKEN" --expected-nonce 3 --json

# =============================================================================
section "4 · EXCHANGE — Tasas de cambio y conversion cross-currency"

adm "[22] Configurar USD → USDX (rate=1.0, requerida para top-up treasury)" \
  set-exchange-rate --from-currency USD --to-currency USDX --rate 1.0 --commission 0.0

adm "[23] Configurar USD → EUR (rate=0.92, comision=1%)" \
  set-exchange-rate --from-currency USD --to-currency EUR --rate 0.92 --commission 0.01

adm "[24] Configurar USD → BTC (rate=0.000015, comision=2%)" \
  set-exchange-rate --from-currency USD --to-currency BTC --rate 0.000015 --commission 0.02

adm "[25] Listar tasas de cambio configuradas" list-exchange-rates

# =============================================================================
section "5 · TESORERIA — Treasury wallets y top-up"

step "[26] Crear treasury wallet USD"
TREASURY_JSON=$($CLI --token "$ADMIN_TOKEN" \
  create-treasury-wallet --currency USD --model ACCOUNT --json)
echo "$TREASURY_JSON"
TREASURY_ID=$(echo "$TREASURY_JSON" | jfield "['result']['wallet_id']")
ok "Treasury ID: $TREASURY_ID"

adm "[27] Listar treasury wallets" list-treasury-wallets

adm "[28] Mint 10000 fondos a treasury" \
  mint --wallet-id "$TREASURY_ID" --amount 10000

step "[29] Top-up carlos desde treasury (500 USD → USDX)"
note "Cross-currency: usa tasa USD→USDX configurada en paso [22]"
$CLI --token "$ADMIN_TOKEN" top-up \
  --treasury-wallet-id "$TREASURY_ID" \
  --target-wallet-id wallet_user_carlos_acc_03 \
  --amount 500 --json

adm "[30] Balance carlos (post top-up)" balance --wallet-id wallet_user_carlos_acc_03

# =============================================================================
section "6 · POLITICAS Y RIESGO"

adm "[31] Bloquear transferencias de alice (can-transfer=false)" \
  set-policy --user-id u-alice --can-transfer false

adm "[32] Verificar politica alice" get-policy --user-id u-alice

expect_fail "[33] Transferencia alice → bloqueada por politica" \
  transfer --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 1 --sender-token "$ALICE_WALLET_TOKEN"

adm "[34] Restaurar politica + daily limit=200" \
  set-policy --user-id u-alice --can-transfer true --daily-limit 200

adm "[35] Set risk profile HIGH para alice (alert threshold=3)" \
  set-risk-profile --user-id u-alice \
  --profile-name HIGH --transfer-alert-threshold 3 --daily-alert-threshold 50

adm "[36] Get risk profile alice" get-risk-profile --user-id u-alice
adm "[37] List risk profiles" list-risk-profiles

step "[38] Transferencia que supera threshold → genera alerta"
$CLI --token "$ADMIN_TOKEN" transfer \
  --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 5 --sender-token "$ALICE_WALLET_TOKEN" --expected-nonce 4 --json

adm "[39] Listar alertas alice" list-alerts --user-id u-alice
adm "[40] List policies" list-policies

# =============================================================================
section "7 · PERMISOS RBAC"

adm "[41] Permisos efectivos del rol OPERATOR" \
  list-role-permissions --role OPERATOR

adm "[42] Conceder permiso MINT al rol OPERATOR" \
  grant-permission --role OPERATOR --permission MINT

adm "[43] Permisos directos de bob (user-level override)" \
  list-user-permissions --user-id u-bob

adm "[44] Conceder permiso EXCHANGE directo a carlos" \
  grant-user-permission --user-id u-carlos --permission EXCHANGE

adm "[45] Revocar permiso MINT del rol OPERATOR" \
  revoke-permission --role OPERATOR --permission MINT

adm "[46] Reset permisos OPERATOR a defaults" \
  reset-role-permissions --role OPERATOR

# =============================================================================
section "8 · MODERACION — Freeze wallet y ban usuario"

adm "[47] Freeze wallet bob" freeze-wallet --wallet-id wallet_user_bravo_utxo_02

step "[48] Transferencia alice → wallet congelada (bloqueada)"
note "Fallo controlado esperado"
set +e
$CLI --token "$ADMIN_TOKEN" transfer \
  --from-wallet wallet_user_alice_utxo_01 --to-wallet wallet_user_bravo_utxo_02 \
  --amount 1 --sender-token "$ALICE_WALLET_TOKEN" --json
RC=$?
set -e
if [ $RC -ne 0 ]; then ok "Bloqueado correctamente (exit=$RC)"; fi

adm "[49] Unfreeze wallet bob" unfreeze-wallet --wallet-id wallet_user_bravo_utxo_02
ok "Wallet bob descongelada"

adm "[50] Ban carlos (congela wallets automáticamente)" ban-user --user-id u-carlos

step "[51] Login carlos (bloqueado: cuenta baneada)"
note "Fallo esperado"
set +e
$CLI login --user-id u-carlos --password carlos1234 --json
set -e

adm "[52] Unban carlos (restaura wallets)" \
  unban-user --user-id u-carlos --unfreeze-wallets true
ok "Carlos desbaneado"

# =============================================================================
section "9 · GESTION AVANZADA DE USUARIOS"

adm "[53] Actualizar display name de carlos" \
  update-user --user-id u-carlos --new-display-name "Carlos V."

step "[54] Soft delete bob (wallets congeladas automáticamente)"
$CLI --token "$ADMIN_TOKEN" delete-user --user-id u-bob --json

step "[55] Login bob (bloqueado: cuenta eliminada)"
note "Fallo esperado"
set +e
$CLI login --user-id u-bob --password bob1234 --json
set -e

adm "[56] Restore bob (wallets descongeladas)" \
  restore-user --user-id u-bob --unfreeze-wallets true
ok "Bob restaurado"

step "[57] Generar password temporal para bob"
TEMP_PW_JSON=$($CLI --token "$ADMIN_TOKEN" generate-temp-password --user-id u-bob --json)
echo "$TEMP_PW_JSON"
TEMP_PW=$(echo "$TEMP_PW_JSON" | jfield "['result']['temp_password']")
ok "Password temporal generado: $TEMP_PW"

step "[58] Login bob con password temporal"
note "Respuesta incluye must_change_password: true"
$CLI login --user-id u-bob --password "$TEMP_PW" --json
note "En el terminal interactivo, este flag fuerza cambio de password inmediato"

# =============================================================================
section "10 · AUDITORIA"

adm "[59] Audit log completo (últimas 30 acciones)" \
  list-audit-log --limit 30

adm "[60] Filtrar: solo LOGIN_FAILED" \
  list-audit-log --action LOGIN_FAILED

adm "[61] Filtrar: acciones del usuario alice" \
  list-audit-log --user-id u-alice

# =============================================================================
section "11 · INTEGRIDAD Y SNAPSHOTS"

adm "[62] Verify integrity" verify-integrity
adm "[63] Snapshot" snapshot
adm "[64] Revisions (últimas 5)" list-revisions --limit 5

# =============================================================================
section "DEMO COMPLETADO"
echo -e "${GREEN}${BOLD}"
echo "  Pasos ejecutados   : 64"
echo "  Usuarios creados   : 3  (alice ADMIN · bob OPERATOR · carlos VIEWER)"
echo "  Wallets             : 3 usuario + 1 treasury"
echo ""
echo "  Features demostradas:"
echo "    ✓ Bootstrap registro / Login JWT"
echo "    ✓ Perfiles de usuario (nombre, email, username)"
echo "    ✓ Wallets UTXO + ACCOUNT"
echo "    ✓ Mint · Transfer con fee y nonce anti-replay"
echo "    ✓ Refresh de wallet token"
echo "    ✓ Exchange rates USD→USDX / USD→EUR / USD→BTC"
echo "    ✓ Treasury wallet + Top-up cross-currency"
echo "    ✓ Politicas: bloqueo y daily limit"
echo "    ✓ Risk profiles + alertas automáticas"
echo "    ✓ RBAC: grant/revoke por rol y por usuario"
echo "    ✓ Freeze / Unfreeze wallet"
echo "    ✓ Ban / Unban usuario"
echo "    ✓ Soft delete / Restore usuario"
echo "    ✓ Password temporal (must_change_password)"
echo "    ✓ Audit log completo + filtros"
echo "    ✓ Verify integrity / Snapshot / Revisions"
echo -e "${RESET}"
