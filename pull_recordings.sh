#!/usr/bin/env bash
set -euo pipefail

# Guard: when sourced by bats, skip main()
BATS_TEST_MODE="${BATS_TEST_MODE:-0}"

REQUIRED_VARS=(DEVICE_IP DEVICE_USER SSH_KEY SSH_PORT REMOTE_PATH LOCAL_PATH)

validate_config() {
  for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      echo "ERROR: Required config variable \$${var} is not set." >&2
      return 1
    fi
  done

  if [[ ! -f "$SSH_KEY" ]]; then
    echo "ERROR: SSH_KEY file '${SSH_KEY}' does not exist." >&2
    return 1
  fi

  if [[ ! -d "$LOCAL_PATH" ]]; then
    echo "ERROR: LOCAL_PATH '${LOCAL_PATH}' does not exist. Create it first." >&2
    return 1
  fi
}

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

main() {
  local conf_file
  conf_file="$(dirname "$0")/pull_recordings.conf"

  if [[ ! -f "$conf_file" ]]; then
    echo "ERROR: Config file not found at ${conf_file}" >&2
    echo "       Copy pull_recordings.conf.example to pull_recordings.conf and fill in your values." >&2
    exit 1
  fi

  # shellcheck source=pull_recordings.conf.example
  source "$conf_file"

  # Expand leading ~ in SSH_KEY since ssh -i does not expand tilde in all environments
  SSH_KEY="${SSH_KEY/#\~/$HOME}"

  validate_config || exit 1

  log "Starting sync from ${DEVICE_USER}@${DEVICE_IP}:${REMOTE_PATH} -> ${LOCAL_PATH}"

  rsync \
    --archive \
    --ignore-existing \
    --compress \
    --partial \
    --progress \
    -e "ssh -i ${SSH_KEY} -p ${SSH_PORT} -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "${DEVICE_USER}@${DEVICE_IP}:${REMOTE_PATH}" \
    "${LOCAL_PATH}" && log "Sync complete." || { rc=$?; log "ERROR: rsync exited with code ${rc}."; exit $rc; }
}

if [[ "$BATS_TEST_MODE" == "0" ]]; then
  main "$@"
fi
