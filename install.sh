#!/bin/bash
# ============================================================================
# iwant installer
# ============================================================================
# Installation script for Linux and macOS.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/narevai/iwant/main/install.sh | bash
#
# Or with options:
#   curl -fsSL ... | bash -s -- --branch dev --skip-auth
#
# ============================================================================

set -euo pipefail

# A pre-set PYTHONPATH/PYTHONHOME can make the venv import a different
# checkout than the one being installed.
unset PYTHONPATH PYTHONHOME

# Don't let uv pick up uv.toml/pyproject.toml from wherever this was run.
export UV_NO_CONFIG=1

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
REPO_URL_SSH="git@github.com:narevai/iwant.git"
REPO_URL_HTTPS="https://github.com/narevai/iwant.git"
IWANT_HOME="${IWANT_HOME:-$HOME/.iwant}"
INSTALL_DIR="${IWANT_INSTALL_DIR:-$IWANT_HOME/iwant}"
COMMAND_LINK_DIR="$HOME/.local/bin"
PYTHON_VERSION="3.12"
PYTHON_SUPPORTED_RANGE=">=3.10,<3.14" # pyproject requires-python; keep in sync
# Umami website id is public by design (Umami ids are never secret).
UMAMI_URL="https://api-gateway.umami.dev/api/send"
UMAMI_WEBSITE_ID="83080a32-0b95-4e90-b948-90929086b256"

# Options
RUN_SETUP=true
BRANCH="main"

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-auth)
            RUN_SETUP=false
            shift
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "iwant installer"
            echo ""
            echo "Usage: install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-auth    Don't run 'iwant auth' after installing"
            echo "  --branch NAME  Git branch to install (default: main)"
            echo "  --dir PATH     Installation directory (default: ~/.iwant/iwant)"
            echo "  -h, --help     Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# Helper functions
# ============================================================================

print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│                    iwant installer                      │"
    echo "├─────────────────────────────────────────────────────────┤"
    echo "│  vLLM model servers on cloud GPUs, one command away.    │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

log_info() {
    echo -e "${CYAN}→${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Anonymous install event: OS, CPU arch and whether the install succeeded -
# nothing else. Opt out with IWANT_NO_TELEMETRY=1 or DO_NOT_TRACK=1.
send_event() {
    if [ -n "${IWANT_NO_TELEMETRY:-}" ] || [ -n "${DO_NOT_TRACK:-}" ]; then
        return 0
    fi
    local data="{\"os\":\"${OS:-unknown}\",\"arch\":\"$(uname -m)\",\"status\":\"$1\"}"
    # Umami drops bot-like User-Agents (curl's included); this format, like
    # the one @umami/node sends, gets through.
    curl -fsS -m 2 -X POST \
        -H 'Content-Type: application/json' \
        -H 'User-Agent: Mozilla/5.0 iwant-installer/1' \
        --data "{\"type\":\"event\",\"payload\":{\"website\":\"$UMAMI_WEBSITE_ID\",\"hostname\":\"iwant.narev.ai\",\"url\":\"/install\",\"name\":\"iwant_install\",\"data\":$data}}" \
        "$UMAMI_URL" >/dev/null 2>&1 || true
}

on_exit() {
    if [ "$1" -ne 0 ] && [ "$EVENT_SENT" = false ]; then
        send_event failed
    fi
}

# ============================================================================
# System detection
# ============================================================================

detect_os() {
    case "$(uname -s)" in
        Linux*)
            OS="linux"
            DISTRO="unknown"
            if [ -f /etc/os-release ]; then
                DISTRO="$(. /etc/os-release && echo "${ID:-unknown}")"
            fi
            ;;
        Darwin*)
            OS="macos"
            DISTRO="macos"
            ;;
        *)
            log_error "Unsupported OS: $(uname -s). iwant supports Linux and macOS (use WSL on Windows)."
            exit 1
            ;;
    esac

    log_success "Detected: $OS ($DISTRO)"
}

# ============================================================================
# Dependency checks
# ============================================================================

install_uv() {
    # iwant owns its own uv at $IWANT_HOME/bin/uv - no PATH probing, so a
    # user's own (older/newer/conda) uv never gets in the way.
    local managed_uv="$IWANT_HOME/bin/uv"

    if [ -x "$managed_uv" ]; then
        UV_CMD="$managed_uv"
        log_success "Managed uv found ($($UV_CMD --version 2>/dev/null))"
        return 0
    fi

    log_info "Installing managed uv into $IWANT_HOME/bin ..."
    mkdir -p "$IWANT_HOME/bin"

    # Download first, then run: `curl | sh` hides curl failures (sh exits 0
    # on empty stdin).
    local installer
    installer="$(mktemp)"
    if ! curl -LsSf https://astral.sh/uv/install.sh -o "$installer"; then
        log_error "Failed to download the uv installer from https://astral.sh/uv/install.sh"
        log_info "Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        rm -f "$installer"
        exit 1
    fi
    # UV_UNMANAGED_INSTALL puts the binary straight into $IWANT_HOME/bin
    # and skips touching the user's shell config.
    if ! UV_UNMANAGED_INSTALL="$IWANT_HOME/bin" sh "$installer" >/dev/null 2>&1 || [ ! -x "$managed_uv" ]; then
        log_error "Failed to install uv"
        log_info "Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        rm -f "$installer"
        exit 1
    fi
    rm -f "$installer"

    UV_CMD="$managed_uv"
    log_success "Managed uv installed ($($UV_CMD --version 2>/dev/null))"
}

check_python() {
    log_info "Checking Python..."

    # Any supported interpreter already on the system is fine - reuse it
    # instead of downloading one.
    if PYTHON_PATH="$("$UV_CMD" python find --system "$PYTHON_SUPPORTED_RANGE" 2>/dev/null)"; then
        PYTHON_VERSION="$PYTHON_PATH"
        log_success "Python found: $("$PYTHON_PATH" --version 2>/dev/null)"
        return 0
    fi

    # None found - uv downloads one, no sudo needed.
    log_info "No supported Python found, installing $PYTHON_VERSION via uv..."
    if ! "$UV_CMD" python install "$PYTHON_VERSION"; then
        log_error "Failed to install Python $PYTHON_VERSION"
        log_info "Install Python $PYTHON_SUPPORTED_RANGE manually, then re-run this script"
        exit 1
    fi
    log_success "Python $PYTHON_VERSION installed"
}

check_git() {
    log_info "Checking Git..."

    # On fresh macOS /usr/bin/git is a stub that fails until the CLT are installed.
    if command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1; then
        log_success "Git $(git --version | awk '{print $3}') found"
        return 0
    fi

    log_error "Git not found. Install it and re-run this script:"
    case "$DISTRO" in
        macos) log_info "  xcode-select --install   (or: brew install git)" ;;
        ubuntu|debian) log_info "  sudo apt update && sudo apt install git" ;;
        fedora) log_info "  sudo dnf install git" ;;
        arch) log_info "  sudo pacman -S git" ;;
        *) log_info "  Use your package manager to install git" ;;
    esac
    exit 1
}

check_cloud_tools() {
    # Not required to install iwant - only to launch anything with it - so
    # these warn instead of aborting.
    log_info "Checking cloud tooling..."

    if command -v gcloud >/dev/null 2>&1; then
        log_success "gcloud found"
        HAS_GCLOUD=true
    else
        log_warn "gcloud not found - needed to launch on GCP: https://cloud.google.com/sdk/docs/install"
        HAS_GCLOUD=false
    fi

    # SkyPilot syncs files to the cluster with rsync and connects over ssh.
    local tool
    for tool in rsync ssh; do
        if command -v "$tool" >/dev/null 2>&1; then
            log_success "$tool found"
        else
            log_warn "$tool not found - SkyPilot needs it to reach launched clusters"
        fi
    done
}

# ============================================================================
# Installation
# ============================================================================

clone_repo() {
    log_info "Installing to $INSTALL_DIR..."

    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Existing installation found, updating..."
        cd "$INSTALL_DIR"
        if [ -n "$(git status --porcelain)" ]; then
            log_error "Local changes in $INSTALL_DIR - commit/stash them or remove the directory, then re-run."
            exit 1
        fi
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        if ! git pull --ff-only origin "$BRANCH"; then
            log_error "Can't fast-forward $INSTALL_DIR to origin/$BRANCH - remove the directory and re-run."
            exit 1
        fi
    elif [ -e "$INSTALL_DIR" ]; then
        log_error "Directory exists but is not a git repository: $INSTALL_DIR"
        log_info "Remove it or choose a different directory with --dir"
        exit 1
    else
        mkdir -p "$(dirname "$INSTALL_DIR")"
        # SSH first (works for private access), fail fast instead of
        # prompting when no key is set up, then fall back to HTTPS.
        if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" \
           git clone --depth 1 --branch "$BRANCH" "$REPO_URL_SSH" "$INSTALL_DIR" 2>/dev/null; then
            log_success "Cloned via SSH"
        else
            rm -rf "$INSTALL_DIR"
            if ! git clone --depth 1 --branch "$BRANCH" "$REPO_URL_HTTPS" "$INSTALL_DIR"; then
                log_error "Failed to clone $REPO_URL_HTTPS"
                exit 1
            fi
            log_success "Cloned via HTTPS"
        fi
    fi

    cd "$INSTALL_DIR"
    log_success "Repository ready"
}

setup_venv() {
    log_info "Creating virtual environment..."

    rm -rf venv
    if ! "$UV_CMD" venv venv --python "$PYTHON_VERSION" || [ ! -x venv/bin/python ]; then
        log_error "Failed to create the virtual environment"
        exit 1
    fi

    # An inherited UV_PYTHON would make later uv calls recreate the venv
    # with a different interpreter - pin it to the one just created.
    export UV_PYTHON="$INSTALL_DIR/venv/bin/python"

    log_success "Virtual environment ready ($(venv/bin/python --version 2>/dev/null))"
}

install_deps() {
    log_info "Installing iwant and its dependencies (SkyPilot is large - this can take a minute)..."

    if ! "$UV_CMD" pip install --python venv/bin/python -e .; then
        log_error "Failed to install dependencies"
        log_info "Try: cd $INSTALL_DIR && $UV_CMD pip install --python venv/bin/python -e ."
        exit 1
    fi

    log_success "Dependencies installed"
}

setup_path() {
    log_info "Setting up iwant command..."

    if [ ! -x "$INSTALL_DIR/venv/bin/iwant" ]; then
        log_error "venv/bin/iwant is missing - the package install didn't complete"
        exit 1
    fi

    mkdir -p "$COMMAND_LINK_DIR"
    rm -f "$COMMAND_LINK_DIR/iwant"
    cat > "$COMMAND_LINK_DIR/iwant" <<EOF
#!/usr/bin/env bash
unset PYTHONPATH
unset PYTHONHOME
exec "$INSTALL_DIR/venv/bin/iwant" "\$@"
EOF
    chmod +x "$COMMAND_LINK_DIR/iwant"
    log_success "Installed iwant launcher → ~/.local/bin/iwant"

    if echo "$PATH" | tr ':' '\n' | grep -qx "$COMMAND_LINK_DIR"; then
        log_info "~/.local/bin already on PATH"
        return 0
    fi

    # Add ~/.local/bin to the user's *login* shell config (the shell running
    # this script is always bash when piped from curl).
    local shell_config=""
    case "$(basename "${SHELL:-/bin/bash}")" in
        zsh) shell_config="$HOME/.zshrc" ;;
        bash)
            if [ "$OS" = "macos" ]; then
                shell_config="$HOME/.bash_profile"
            else
                shell_config="$HOME/.bashrc"
            fi
            ;;
        fish) shell_config="$HOME/.config/fish/config.fish" ;;
    esac

    if [ -z "$shell_config" ]; then
        log_warn "Could not detect your shell config - add this to it manually:"
        log_info '  export PATH="$HOME/.local/bin:$PATH"'
    elif ! grep -qs '\.local/bin' "$shell_config"; then
        mkdir -p "$(dirname "$shell_config")"
        echo "" >> "$shell_config"
        echo "# iwant - ensure ~/.local/bin is on PATH" >> "$shell_config"
        if [[ "$shell_config" == *config.fish ]]; then
            echo 'fish_add_path "$HOME/.local/bin"' >> "$shell_config"
        else
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_config"
        fi
        log_success "Added ~/.local/bin to PATH in $shell_config"
        SHELL_CONFIG_CHANGED="$shell_config"
    fi

    export PATH="$COMMAND_LINK_DIR:$PATH"
}

run_setup() {
    if [ "$RUN_SETUP" = false ]; then
        log_info "Skipping 'iwant auth' (--skip-auth)"
        return 0
    fi

    # Probe by actually opening /dev/tty - it can exist but fail to open
    # (Docker builds, CI). `iwant auth` needs it for its picker when this
    # script itself is piped from curl.
    if ! (: </dev/tty) 2>/dev/null; then
        log_info "No terminal available - run 'iwant auth' after install."
        return 0
    fi

    echo ""
    log_info "Running 'iwant auth' to check which clouds are ready..."
    echo ""
    "$COMMAND_LINK_DIR/iwant" auth </dev/tty || log_warn "'iwant auth' failed - re-run it after install."
}

print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│              ✓ Installation Complete!                   │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
    echo -e "   ${YELLOW}Code:${NC}  $INSTALL_DIR"
    echo ""
    echo -e "${CYAN}${BOLD}Commands:${NC}"
    echo ""
    echo -e "   ${GREEN}iwant up${NC}      Deploy model"
    echo -e "   ${GREEN}iwant down${NC}    Tear down a model"
    echo -e "   ${GREEN}iwant auth${NC}    Login to your cloud provider"
    echo -e "   ${GREEN}iwant list${NC}    Show deployed models"
    echo -e "   ${GREEN}iwant ssh${NC}     SSH into a cluster"
    echo ""

    if [ "$HAS_GCLOUD" = false ]; then
        echo -e "${YELLOW}Next: install gcloud (https://cloud.google.com/sdk/docs/install), then:${NC}"
        echo "   gcloud auth login && gcloud auth application-default login"
        echo ""
    fi

    if [ -n "$SHELL_CONFIG_CHANGED" ]; then
        echo -e "${YELLOW}Reload your shell to use 'iwant':${NC}"
        echo "   source $SHELL_CONFIG_CHANGED"
        echo ""
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    HAS_GCLOUD=false
    SHELL_CONFIG_CHANGED=""
    EVENT_SENT=false
    trap 'on_exit $?' EXIT

    print_banner

    detect_os
    install_uv
    check_python
    check_git
    check_cloud_tools

    clone_repo
    setup_venv
    install_deps
    setup_path
    send_event ok
    EVENT_SENT=true
    run_setup

    print_success
}

main
