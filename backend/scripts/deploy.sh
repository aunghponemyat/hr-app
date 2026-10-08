#!/usr/bin/env bash

#
# Deploy the bot to the do-sg VPS (armored-shield) and (re)start its
# systemd service. Run from the project root on the workstation.
#
#     $ ./scripts/deploy.sh
#
# The service unit is installed on the host via a privileged chroot
# container because the reiner account has no passwordless sudo but is in
# the docker group.
#

set -euo pipefail

REMOTE="${REMOTE:-do-sg}"
REMOTE_DIR="${REMOTE_DIR:-/home/reiner/reminder-bot}"
SERVICE_NAME="reminder-bot"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Syncing project to ${REMOTE}:${REMOTE_DIR}"
rsync -az --delete \
    --exclude '.venv' \
    --exclude '.git' \
    --exclude 'data' \
    --exclude '.certs' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude '.ruff_cache' \
    --exclude '*:Zone.Identifier' \
    "${SCRIPT_DIR}/" "${REMOTE}:${REMOTE_DIR}/"

echo "==> Running setup.sh on remote"
ssh "${REMOTE}" "cd ${REMOTE_DIR} && chmod +x scripts/setup.sh && ./scripts/setup.sh"

echo "==> Installing systemd unit"
ssh "${REMOTE}" "docker run --rm --privileged --pid=host -v /:/host alpine sh -c '
    cp /host${REMOTE_DIR}/deploy/${SERVICE_NAME}.service /host/etc/systemd/system/${SERVICE_NAME}.service &&
    chroot /host systemctl daemon-reload &&
    chroot /host systemctl enable ${SERVICE_NAME}.service &&
    chroot /host systemctl restart ${SERVICE_NAME}.service &&
    chroot /host systemctl --no-pager --full status ${SERVICE_NAME}.service | head -20
'"

echo "==> Done. Logs: ssh ${REMOTE} 'docker run --rm --privileged -v /:/host alpine chroot /host journalctl -u ${SERVICE_NAME} -n 50'"