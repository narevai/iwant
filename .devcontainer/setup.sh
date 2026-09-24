#!/usr/bin/env bash
set -euo pipefail
# The ~/.config/gcloud bind mount and the ~/.sky volume can end
# up root:root because Docker creates them before the container user exists.
# Fix ownership, same pattern as the sibling skypilot repo's devcontainer.
sudo chown -R vscode:vscode "${HOME}/.config/gcloud" "${HOME}/.sky" 2>/dev/null || true
mkdir -p "${HOME}/.sky"
