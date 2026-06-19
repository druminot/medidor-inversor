#!/bin/bash
set -euo pipefail

PROJECT_DIR="/opt/solar-monitor"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Solar Monitor Deploy Script ==="
echo "Source: ${REPO_DIR}"
echo "Target: ${PROJECT_DIR}"
echo ""

# Check running as lautaro user
if [ "$(whoami)" != "root" ] && [ "$(whoami)" != "lautaro" ]; then
    echo "WARN: Running as $(whoami). Expected 'lautaro' or root."
fi

# Step 1: Install Docker if not present
if ! command -v docker &>/dev/null; then
    echo ">>> Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Log out and back in for group changes to take effect."
    echo "Then re-run this script."
    exit 0
fi

# Step 2: Install build dependencies
echo ">>> Installing build dependencies..."
sudo apt-get install -y libmodbus-dev libpq-dev gcc make

# Step 3: Create project directory structure
echo ">>> Creating directory structure..."
sudo mkdir -p "${PROJECT_DIR}"/{modbus-reader/src,grafana/provisioning/datasources,grafana/provisioning/dashboards,grafana/dashboards,db,cloudflared,backups}
sudo chown -R "$(whoami)":"$(id -gn)" "${PROJECT_DIR}"

# Step 4: Copy project files
echo ">>> Copying project files..."
cp "${REPO_DIR}/docker-compose.yml" "${PROJECT_DIR}/"
cp "${REPO_DIR}/.env" "${PROJECT_DIR}/"
cp "${REPO_DIR}/db/init.sql" "${PROJECT_DIR}/db/"
cp "${REPO_DIR}/db/init-users.sh" "${PROJECT_DIR}/db/"
chmod +x "${PROJECT_DIR}/db/init-users.sh"
cp "${REPO_DIR}/grafana/grafana.ini" "${PROJECT_DIR}/grafana/"
cp "${REPO_DIR}/grafana/provisioning/datasources/datasource.yml" "${PROJECT_DIR}/grafana/provisioning/datasources/"
cp "${REPO_DIR}/grafana/provisioning/dashboards/dashboard.yml" "${PROJECT_DIR}/grafana/provisioning/dashboards/"
cp "${REPO_DIR}/grafana/dashboards/"*.json "${PROJECT_DIR}/grafana/dashboards/"
cp "${REPO_DIR}/modbus-reader/Makefile" "${PROJECT_DIR}/modbus-reader/"
cp "${REPO_DIR}/modbus-reader/Dockerfile" "${PROJECT_DIR}/modbus-reader/"
cp "${REPO_DIR}/modbus-reader/src/"* "${PROJECT_DIR}/modbus-reader/src/"

# Step 5: Set up udev rule for USB-RS232 (CH340)
echo ">>> Setting up udev rule for USB-RS232 (CH340)..."
sudo tee /etc/udev/rules.d/99-serial.rules > /dev/null << 'UDEV'
# USB-RS232 CH340 adapter (Riello H.P.6065REL-D)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
# USB-RS485 FT232 adapter (alternative)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
UDEV
sudo udevadm control --reload-rules
sudo udevadm trigger 2>/dev/null || true

# Step 6: Compile modbus-reader locally (optional, Docker build preferred)
echo ">>> Compiling modbus-reader..."
cd "${PROJECT_DIR}/modbus-reader"
if make clean && make; then
    echo "Compilation successful."
else
    echo "WARN: Local compilation failed. Docker build will handle it."
fi

# Step 7: Edit .env with real passwords
echo ""
echo "=== IMPORTANT ==="
echo "Edit ${PROJECT_DIR}/.env with real passwords before deploying:"
echo "  DB_PASSWORD=          (TimescaleDB superuser password)"
echo "  GRAFANA_PASSWORD=     (Grafana admin password)"
echo "  GRAFANA_READER_PASSWORD= (Grafana read-only DB user)"
echo "  TUNNEL_TOKEN=         (Cloudflare Tunnel token)"
echo ""
echo "After editing .env, run:"
echo "  cd ${PROJECT_DIR} && docker compose up -d"
echo ""
echo "To test without hardware (dev mode):"
echo "  cd ${PROJECT_DIR} && docker compose -f docker-compose.dev.yml up -d"
echo "=================="

# Step 8: Protect .env
chmod 600 "${PROJECT_DIR}/.env"

echo ">>> Deploy script complete."