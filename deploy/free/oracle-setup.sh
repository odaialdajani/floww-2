#!/usr/bin/env bash
# deploy/free/oracle-setup.sh — Oracle Cloud Always Free (ARM A1) bootstrap.
# Run ONCE on a fresh Ubuntu 22.04+/24.04 VM as the default user (ubuntu/opc), via sudo.
#
# Usage:
#   scp -i <key> deploy/free/{oracle-setup.sh,deploy_key_ed25519,server-setup.sh} ubuntu@<VM_IP>:~/
#   ssh -i <key> ubuntu@<VM_IP>
#   chmod 600 ~/deploy_key_ed25519 && sudo bash ~/oracle-setup.sh
#
# The script stops once to let you fill secrets, then re-runs to build & start.

set -euo pipefail

APP_DIR="/opt/floww"
REPO_SSH="git@github.com:odaialdajani/floww-2.git"
DEPLOY_KEY_SRC="$HOME/deploy_key_ed25519"
# Under `sudo bash` HOME may reset to /root while the key was scp'd to the
# invoking user's home — fall back to that path.
if [ ! -f "$DEPLOY_KEY_SRC" ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    DEPLOY_KEY_SRC="/home/${SUDO_USER}/deploy_key_ed25519"
fi

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$DEPLOY_KEY_SRC" ] || { echo "missing $DEPLOY_KEY_SRC — scp deploy/free/deploy_key_ed25519 up first"; exit 1; }

echo "── 1. System packages ──"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw

echo "── 2. Docker ──"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
docker --version
docker compose version

echo "── 2b. Node.js (frontend build) ──"
if ! command -v npm >/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi
node --version
npm --version

echo "── 2c. Swap (1G) — absorbs npm build / numba JIT RAM spikes ──"
# Oracle A1 free-tier VMs ship with NO swap; the frontend build (~2GB peak)
# plus cold-start JIT can OOM-kill otherwise.
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show
# Low swappiness: swap is an emergency buffer, not working-set storage.
sysctl -qw vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf

echo "── 3. Firewall: only SSH + web ──"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "── 4. Install read-only GitHub deploy key ──"
install -m 600 -o root -g root "$DEPLOY_KEY_SRC" /root/.ssh/floww_deploy_key
grep -q "github.com" /root/.ssh/config 2>/dev/null || cat >> /root/.ssh/config <<'EOF'
Host github.com
    IdentityFile /root/.ssh/floww_deploy_key
    StrictHostKeyChecking accept-new
EOF
chmod 600 /root/.ssh/config

echo "── 5. Clone repo ──"
if [ ! -d "$APP_DIR" ]; then
    git clone "$REPO_SSH" "$APP_DIR"
fi
cd "$APP_DIR"

echo "── 6. Secrets file ──"
if [ ! -s deploy/free/.env.prod ] || grep -q "your.domain.com" deploy/free/.env.prod; then
    cp -n deploy/free/.env.prod.template deploy/free/.env.prod || true
    chmod 600 deploy/free/.env.prod
    echo "!! EDIT $APP_DIR/deploy/free/.env.prod — set:"
    echo "!!   DOMAIN=confluencedecoder.duckdns.org"
    echo "!!   ADMIN_EMAIL, CORS_ORIGINS=https://confluencedecoder.duckdns.org"
    echo "!!   fresh API_SECRET_KEY + JWT_SECRET_KEY (python3 -c \"import secrets; print(secrets.token_hex(32))\")"
    echo "!!   data provider keys from local backend/.env"
    echo "!! Then re-run: sudo bash $APP_DIR/deploy/free/oracle-setup.sh"
    exit 1
fi
for k in API_SECRET_KEY JWT_SECRET_KEY; do
    if ! grep -Eq "^${k}=.+" deploy/free/.env.prod; then
        echo "!! ${k} is empty in deploy/free/.env.prod — set it before re-running."
        echo "!!   python3 -c \"import secrets; print(secrets.token_hex(32))\""
        exit 1
    fi
done

echo "── 7. Build frontend ──"
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..

echo "── 8. Start stack ──"
docker compose -f deploy/free/docker-compose.yml --env-file deploy/free/.env.prod up -d --build

echo ""
echo "Waiting for backend health..."
# 60 x 5s = 300s: cold numba JIT on first request can take ~90s+ on ARM,
# plus Mongo init + Caddy cert issuance. smoke.sh has its own longer warm-up.
for i in $(seq 1 60); do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        DOMAIN=$(grep '^DOMAIN=' deploy/free/.env.prod | cut -d= -f2)
        echo "✅ Confluence Decoder LIVE on https://${DOMAIN}"
        echo "   Verify: DOMAIN=${DOMAIN} bash deploy/free/smoke.sh"
        echo "   Don't forget: update DuckDNS to point at THIS VM's public IP:"
        echo "   curl \"https://www.duckdns.org/update?domains=confluencedecoder&token=<TOKEN>&ip=$(curl -s ifconfig.me)\""
        exit 0
    fi
    sleep 5
done
echo "⚠ Backend not healthy yet — check: docker compose -f deploy/free/docker-compose.yml logs backend"
exit 1
