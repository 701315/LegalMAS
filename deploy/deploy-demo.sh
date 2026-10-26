#!/usr/bin/env bash
set -Eeuo pipefail

LOCKFILE="/tmp/steloom-demo-maintenance.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "FATAL: another deploy/rollback is already running"
  exit 1
fi

DEV_DIR="/srv/steloom-dev"
DEMO_DIR="/srv/steloom-demo"
BACKUP_ROOT="/mnt/backups/steloom-demo/releases"
TS="$(date +%F-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$TS"

STOP_ORDER=(
  steloom-demo-beat
  steloom-demo-worker
  steloom-demo-backend
)

START_ORDER=(
  steloom-demo-backend
  steloom-demo-worker
  steloom-demo-beat
)

SYSTEMD_UNITS=(
  steloom-demo-backend.service
  steloom-demo-worker.service
  steloom-demo-beat.service
)

EXPECTED_WORKER_QUEUES="high_priority,default,system,low_priority,heavy_llm_enrichment,heavy_llm_segment_classification,heavy_llm_checks"

log() {
  echo
  echo "==> $*"
}

same_file() {
  local a="$1"
  local b="$2"
  [[ -f "$a" && -f "$b" ]] || return 1
  cmp -s "$a" "$b"
}

wait_for_service() {
  local svc="$1"
  local tries="${2:-15}"
  local delay="${3:-2}"

  for ((i=1; i<=tries; i++)); do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"
    if [[ "$state" == "active" ]]; then
      echo "   $svc -> active"
      return 0
    fi
    sleep "$delay"
  done

  echo "ERROR: service $svc did not become active"
  sudo systemctl status "$svc" --no-pager -l || true
  sudo journalctl -u "$svc" -n 80 --no-pager || true
  return 1
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local tries="${3:-20}"
  local delay="${4:-2}"

  for ((i=1; i<=tries; i++)); do
    if curl -fsS "$url" >/dev/null; then
      echo "   $name -> OK ($url)"
      return 0
    fi
    sleep "$delay"
  done

  echo "ERROR: $name did not respond: $url"
  return 1
}

wait_for_caddy_path() {
  local path="$1"
  local name="$2"
  local tries="${3:-20}"
  local delay="${4:-2}"

  for ((i=1; i<=tries; i++)); do
    if curl -fsS --connect-timeout 5 --max-time 10 \
      --resolve app.steloom.com:443:127.0.0.1 \
      "https://app.steloom.com$path" >/dev/null; then
      echo "   $name -> OK ($path via local Caddy)"
      return 0
    fi
    sleep "$delay"
  done

  echo "ERROR: $name did not respond via local Caddy: $path"
  return 1
}

run_env_contract_audit() {
  log "Auditing dev/demo env contract"

  if [[ ! -x "$DEV_DIR/scripts/audit_env_contract.py" ]]; then
    echo "FATAL: missing env audit script: $DEV_DIR/scripts/audit_env_contract.py"
    exit 1
  fi

  if ! "$DEV_DIR/scripts/audit_env_contract.py"; then
    echo
    echo "FATAL: env contract audit failed."
    echo "Fix MUST MATCH / SHOULD DIFFER errors before deploy."
    exit 1
  fi
}

install_systemd_units() {
  log "Installing systemd units from repo"
  for unit in "${SYSTEMD_UNITS[@]}"; do
    local src="$DEMO_DIR/deploy/systemd/$unit"
    local dst="/etc/systemd/system/$unit"

    if [[ ! -f "$src" ]]; then
      echo "FATAL: missing versioned systemd unit: $src"
      exit 1
    fi

    sudo install -m 0644 "$src" "$dst"
    echo "   installed: $unit"
  done

  sudo systemctl daemon-reload
  echo "   daemon-reload done"
}

verify_demo_worker_queues() {
  log "Verifying demo worker queue topology"

  local execstart
  execstart="$(systemctl show steloom-demo-worker.service -p ExecStart --value 2>/dev/null || true)"

  if [[ "$execstart" != *"$EXPECTED_WORKER_QUEUES"* ]]; then
    echo "FATAL: demo worker queues do not match expected topology"
    echo "Expected queues: $EXPECTED_WORKER_QUEUES"
    echo "Actual ExecStart: $execstart"
    exit 1
  fi

  echo "   worker queues -> OK"
}

verify_systemd_units_contain_q6() {
  log "Verifying systemd units contain Q6 fix (--proxy-headers)"

  local backend_unit="$DEV_DIR/deploy/systemd/steloom-demo-backend.service"
  if [[ ! -f "$backend_unit" ]]; then
    echo "FATAL: missing $backend_unit"
    exit 1
  fi

  if ! grep -q -- '--proxy-headers' "$backend_unit"; then
    echo "FATAL: $backend_unit missing --proxy-headers (Q6 fix regressed)"
    echo "Add: --proxy-headers --forwarded-allow-ips=127.0.0.1 to ExecStart"
    exit 1
  fi

  if ! grep -q -- '--forwarded-allow-ips=127.0.0.1' "$backend_unit"; then
    echo "FATAL: $backend_unit missing --forwarded-allow-ips=127.0.0.1"
    exit 1
  fi

  echo "   Q6 fix present in systemd units -> OK"
}

REQUIREMENTS_CHANGED=0
FRONTEND_DEPS_CHANGED=0

if ! same_file "$DEV_DIR/requirements.txt" "$DEMO_DIR/requirements.txt"; then
  REQUIREMENTS_CHANGED=1
fi

if ! same_file "$DEV_DIR/requirements-base.txt" "$DEMO_DIR/requirements-base.txt"; then
  REQUIREMENTS_CHANGED=1
fi

if ! same_file "$DEV_DIR/frontend/package.json" "$DEMO_DIR/frontend/package.json"; then
  FRONTEND_DEPS_CHANGED=1
fi

if [[ -f "$DEV_DIR/frontend/package-lock.json" || -f "$DEMO_DIR/frontend/package-lock.json" ]]; then
  if ! same_file "$DEV_DIR/frontend/package-lock.json" "$DEMO_DIR/frontend/package-lock.json"; then
    FRONTEND_DEPS_CHANGED=1
  fi
fi

if [[ ! -d "$DEMO_DIR/frontend/node_modules" ]]; then
  FRONTEND_DEPS_CHANGED=1
fi

log "Pre-check"
echo "DEV  dir: $DEV_DIR"
echo "DEMO dir: $DEMO_DIR"
echo "Backup:   $BACKUP_DIR"
echo "requirements changed: $REQUIREMENTS_CHANGED"
echo "frontend deps changed: $FRONTEND_DEPS_CHANGED"

DEMO_REQUIRED_FILES=(
  "$DEMO_DIR/.env"
  "$DEMO_DIR/.venv/bin/python"
  "$DEMO_DIR/.venv/bin/alembic"
  "$DEMO_DIR/frontend/package.json"
  "$DEMO_DIR/frontend/.env.production"
)

for f in "${DEMO_REQUIRED_FILES[@]}"; do
  if [[ ! -e "$f" ]]; then
    echo "FATAL: required demo file missing: $f"
    echo "Deploy aborted. Fix this before retrying."
    exit 1
  fi
done

echo "All required demo files present."

run_env_contract_audit
verify_systemd_units_contain_q6

log "Current service state before deploy"
for svc in "${START_ORDER[@]}"; do
  echo " - $svc: $(systemctl is-active "$svc" 2>/dev/null || true)"
done

log "Creating backup"
mkdir -p "$BACKUP_DIR"

backup_items=()
for item in \
  src \
  alembic \
  frontend \
  playbooks \
  prompts \
  deploy \
  alembic.ini \
  requirements.txt \
  requirements-base.txt \
  requirements-dev.txt \
  pyproject.toml \
  Makefile \
  .env
do
  [[ -e "$DEMO_DIR/$item" ]] && backup_items+=("$item")
done

if [[ "${#backup_items[@]}" -gt 0 ]]; then
  tar -czf "$BACKUP_DIR/demo-project.tgz" \
    --exclude='.venv' \
    --exclude='frontend/node_modules' \
    --exclude='frontend/dist' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    -C "$DEMO_DIR" \
    "${backup_items[@]}"
fi

if [[ -d "$DEMO_DIR/frontend/dist" ]]; then
  tar -czf "$BACKUP_DIR/frontend-dist.tgz" -C "$DEMO_DIR/frontend" dist
fi

rotate_backups() {
  log "Rotating backups (retention: 30 days + keep latest 10)"

  if [[ ! -d "$BACKUP_ROOT" ]]; then
    return 0
  fi

  local keep_10
  keep_10=$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -10 | sed 's:/*$::')

  while IFS= read -r dir; do
    [[ -z "$dir" ]] && continue
    dir="${dir%/}"
    if echo "$keep_10" | grep -qxF "$dir"; then
      continue
    fi
    if [[ -d "$dir" ]]; then
      echo "   removing old backup: $(basename "$dir")"
      rm -rf "$dir"
    fi
  done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +30 2>/dev/null)

  echo "   backups after rotation: $(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l)"
}

rotate_backups

log "Stopping demo services"
for svc in "${STOP_ORDER[@]}"; do
  echo " - stopping $svc"
  sudo systemctl stop "$svc" || true
done

log "Syncing code dev -> demo (whitelist only)"

rsync -a --delete \
  "$DEV_DIR/src/" "$DEMO_DIR/src/"

rsync -a --delete \
  "$DEV_DIR/alembic/" "$DEMO_DIR/alembic/"

rsync -a --delete \
  "$DEV_DIR/playbooks/" "$DEMO_DIR/playbooks/"

rsync -a --delete \
  "$DEV_DIR/prompts/" "$DEMO_DIR/prompts/"

rsync -a --delete \
  "$DEV_DIR/deploy/" "$DEMO_DIR/deploy/"

rsync -a --delete \
  --exclude 'node_modules/' \
  --exclude 'dist/' \
  --exclude 'dist.backup-*/' \
  --exclude '.env' \
  --exclude '.env.*' \
  "$DEV_DIR/frontend/" "$DEMO_DIR/frontend/"

for f in \
  alembic.ini \
  requirements.txt \
  requirements-base.txt \
  requirements-dev.txt \
  pyproject.toml \
  Makefile
do
  if [[ -f "$DEV_DIR/$f" ]]; then
    rsync -a "$DEV_DIR/$f" "$DEMO_DIR/$f"
  fi
done

log "Updating Python dependencies (if needed)"
if [[ "$REQUIREMENTS_CHANGED" -eq 1 ]]; then
  "$DEMO_DIR/.venv/bin/pip" install -r "$DEMO_DIR/requirements.txt"
else
  echo " - skipped (requirements unchanged)"
fi

log "Updating frontend dependencies (if needed)"
if [[ "$FRONTEND_DEPS_CHANGED" -eq 1 ]]; then
  cd "$DEMO_DIR/frontend"
  if [[ -f package-lock.json ]]; then
    npm ci --no-fund --no-audit
  else
    npm install --no-fund --no-audit
  fi
else
  echo " - skipped (frontend deps unchanged)"
fi

log "Running demo DB migrations"
(
  cd "$DEMO_DIR"
  set -a
  source "$DEMO_DIR/.env"
  set +a
  export PYTHONPATH="$DEMO_DIR/src"
  "$DEMO_DIR/.venv/bin/alembic" upgrade head
)

log "Building demo frontend"
cd "$DEMO_DIR/frontend"
rm -rf dist
npm run build

log "Validating frontend build"
if grep -Rqs 'http://localhost:8000' "$DEMO_DIR/frontend/dist/assets"; then
  echo "FATAL: frontend build contains localhost:8000 as API URL!"
  echo "Check $DEMO_DIR/frontend/.env.production and frontend/src/api/client.ts"
  exit 1
fi
echo "Frontend build validation passed."

install_systemd_units

log "Starting demo services"
for svc in "${START_ORDER[@]}"; do
  echo " - starting $svc"
  sudo systemctl start "$svc"
  wait_for_service "$svc"
done

verify_demo_worker_queues

log "Health checks"
wait_for_url "http://127.0.0.1:8001/docs" "demo backend local docs"
wait_for_caddy_path "/" "public app root"
wait_for_caddy_path "/login" "public app login"

log "Final service state"
for svc in "${START_ORDER[@]}"; do
  echo " - $svc: $(systemctl is-active "$svc" 2>/dev/null || true)"
done

echo
echo "DEPLOY SUCCESS"
echo "Backup saved to: $BACKUP_DIR"

# --- deploy metadata (R-38) ---
DEPLOY_META="$DEMO_DIR/.deploy-meta.json"
DEV_HEAD="$(cd "$DEV_DIR" && git rev-parse HEAD 2>/dev/null || echo "unknown")"
DEV_HEAD_SHORT="$(cd "$DEV_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")"
DEMO_HEAD_BEFORE="$(cd "$DEMO_DIR" && git rev-parse HEAD 2>/dev/null || echo "n/a")"

cat > "$DEPLOY_META" <<METAEOF
{
  "schema_version": 1,
  "dev_head": "$DEV_HEAD",
  "dev_head_short": "$DEV_HEAD_SHORT",
  "deployed_at": "$(date -Iseconds)",
  "deployer": "$(whoami)",
  "host": "$(hostname)",
  "backup_dir": "$BACKUP_DIR",
  "demo_git_head_before_deploy": "$DEMO_HEAD_BEFORE",
  "note": "demo_git_head is not authoritative (rsync without git commit). Use dev_head for exact deployed source."
}
METAEOF
echo "[deploy] wrote $DEPLOY_META"
cat "$DEPLOY_META"
# --- end deploy metadata ---
