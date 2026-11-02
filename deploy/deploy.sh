#!/usr/bin/env bash
# Build the catalog locally and push the served parts to the Hetzner server.
#
# Usage:
#   SERVER=tuning@1.2.3.4 DEST=/srv/tuning-files bash deploy/deploy.sh
# (or export SERVER/DEST beforehand; defaults below)
set -euo pipefail

SERVER="${SERVER:-user@YOUR.HETZNER.IP}"
DEST="${DEST:-/srv/tuning-files}"

echo "== Building catalog =="
python build_catalog.py

echo "== Syncing to ${SERVER}:${DEST} =="
rsync -av --delete ./catalog/ "${SERVER}:${DEST}/catalog/"
rsync -av --delete ./files/   "${SERVER}:${DEST}/files/"

echo "Done. Site is live at http://${SERVER#*@}/ (or your server hostname)."
