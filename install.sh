#!/usr/bin/env bash
# CLOTE Installer - Self-Hosted File Management System
# Usage: bash install.sh
set -euo pipefail

### CONFIG ###
INSTALL_DIR="/opt/clote"
SERVICE_USER="clote"
REPO_URL="https://github.com/nithishvenkat4/CLOTE"
REPO_BRANCH="dev"
PORT=8000

### COLORS ###
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[CLOTE]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

### CHECKS ###
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash install.sh"
command -v python3 >/dev/null || error "Python 3 not found. Install with: apt install python3"
command -v git     >/dev/null || error "Git not found. Install with: apt install git"

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Found Python $PYTHON_VERSION"

### CREATE USER ###
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating system user: $SERVICE_USER"
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
fi

### CLONE / UPDATE REPO ###
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git fetch origin "$REPO_BRANCH"
    git reset --hard "origin/$REPO_BRANCH"
else
    info "Cloning CLOTE from GitHub..."
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

### SETUP VENV ###
info "Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/server/requirements.txt" --quiet
info "Dependencies installed."

### STORAGE DIRECTORIES ###
info "Creating storage directories..."
mkdir -p "$INSTALL_DIR/server/storage/files"
mkdir -p "$INSTALL_DIR/server/storage/versions"
mkdir -p "$INSTALL_DIR/server/logs"

### GENERATE .env IF MISSING ###
if [ ! -f "$INSTALL_DIR/.env" ]; then
    info "Generating .env with a secure SECRET_KEY..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$INSTALL_DIR/.env" <<EOF
SECRET_KEY=$SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALLOWED_ORIGINS=*
EOF
    warn "Review your config at: $INSTALL_DIR/.env"
fi

### FIX PERMISSIONS ###
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

### INSTALL SYSTEMD SERVICE ###
info "Installing systemd service..."
cp "$INSTALL_DIR/clote.service" /etc/systemd/system/clote.service
sed -i "s|/opt/clote|$INSTALL_DIR|g" /etc/systemd/system/clote.service
systemctl daemon-reload
systemctl enable clote
systemctl restart clote

### DONE ###
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  CLOTE installed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Server URL : ${YELLOW}http://$(hostname -I | awk '{print $1}'):$PORT${NC}"
echo -e "  Client     : ${YELLOW}http://$(hostname -I | awk '{print $1}'):$PORT/client/CLOTE.html${NC}"
echo -e "  API Docs   : ${YELLOW}http://$(hostname -I | awk '{print $1}'):$PORT/docs${NC}"
echo -e "  Config     : ${YELLOW}$INSTALL_DIR/.env${NC}"
echo -e "  Logs       : ${YELLOW}journalctl -u clote -f${NC}"
echo -e "  Status     : ${YELLOW}systemctl status clote${NC}"
echo ""
echo -e "  To update  : sudo bash $INSTALL_DIR/install.sh"
echo ""
