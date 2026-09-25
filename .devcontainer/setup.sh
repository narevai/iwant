#!/usr/bin/env bash
set -euo pipefail
# Docker creates the ~/.config/gcloud mount and ~/.sky volume as root
# before the container user exists - hand them back to vscode.
sudo chown -R vscode:vscode "${HOME}/.config/gcloud" "${HOME}/.sky" 2>/dev/null || true
mkdir -p "${HOME}/.sky"
