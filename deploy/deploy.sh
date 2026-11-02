#!/usr/bin/env bash
# Build the catalog locally and push everything to the Hetzner server.
#
# Usage:
#   SERVER=tuning@1.2.3.4 DEST=/srv/tuning-files bash deploy/deploy.sh
#
# NOTE: files/_inbox/ is deliberately EXCLUDED from the rsync -- pending
# submissions living on the server must never be wiped by a deploy.
set -euo pipefail

SERVER="${SERVER:-user@YOUR.HETZNER.IP}"
DEST="${DEST:-/srv/tuning-files}"

echo "== Building catalog =="
python build_catalog.py

echo "== Syncing to ${SERVER}:${DEST} =="
rsync -av --delete ./catalog/       "${SERVER}:${DEST}/catalog/"
rsync -av --delete ./app_templates/ "${SERVER}:${DEST}/app_templates/"
rsync -av ./app.py                  "${SERVER}:${DEST}/app.py"
rsync -av --delete --exclude '_inbox/' ./files/ "${SERVER}:${DEST}/files/"

echo "== Restarting submission server =="
if ssh "$SERVER" "sudo systemctl restart tuning-files-upload"; then
  echo "service restarted"
else
  echo "NOTE: could not restart tuning-files-upload - do it manually on the server."
fi

echo "Done. Site: http://<server-ip>/   Submit: /submit   Review: /review"
