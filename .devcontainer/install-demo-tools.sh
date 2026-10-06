#!/usr/bin/env bash
set -euo pipefail

vhs_version=0.12.1
ttyd_version=1.7.7
case "$(uname -m)" in
  aarch64|arm64) vhs_arch=arm64; ttyd_arch=aarch64 ;;
  x86_64|amd64) vhs_arch=x86_64; ttyd_arch=x86_64 ;;
  *) echo "Unsupported recording tools architecture: $(uname -m)" >&2; exit 1 ;;
esac

tools_tmp=$(mktemp -d)
trap 'rm -rf "$tools_tmp"' EXIT
cd "$tools_tmp"
vhs_archive="vhs_${vhs_version}_Linux_${vhs_arch}.tar.gz"
vhs_url="https://github.com/charmbracelet/vhs/releases/download/v${vhs_version}"
curl -fsSLo "$vhs_archive" "$vhs_url/$vhs_archive"
curl -fsSLo checksums.txt "$vhs_url/checksums.txt"
sha256sum --ignore-missing -c checksums.txt
tar -xzf "$vhs_archive" --strip-components=1
install -m 0755 vhs /usr/local/bin/vhs

ttyd_url="https://github.com/tsl0922/ttyd/releases/download/${ttyd_version}"
curl -fsSLo "ttyd.${ttyd_arch}" "$ttyd_url/ttyd.${ttyd_arch}"
curl -fsSLo SHA256SUMS "$ttyd_url/SHA256SUMS"
sha256sum --ignore-missing -c SHA256SUMS
install -m 0755 "ttyd.${ttyd_arch}" /usr/local/bin/ttyd
