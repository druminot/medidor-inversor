#!/bin/bash

USER_NAME=${USER_NAME:-wineuser}
USER_UID=${USER_UID:-1010}
USER_GID=${USER_GID:-"${USER_UID}"}
USER_HOME=${USER_HOME:-/home/"${USER_NAME}"}
USER_PASSWD=${USER_PASSWD:-"$(openssl passwd -1 -salt "$(openssl rand -base64 6)" "${USER_NAME}")"}
USER_SUDO=${USER_SUDO:-yes}
FORCED_OWNERSHIP=${FORCED_OWNERSHIP:-no}
TZ=${TZ:-UTC}

grep -q ":${USER_GID}:$" /etc/group || groupadd --gid "${USER_GID}" "${USER_NAME}"
grep -q "^${USER_NAME}:" /etc/passwd || useradd --shell /bin/bash --uid "${USER_UID}" --gid "${USER_GID}" --password "${USER_PASSWD}" --no-create-home --home-dir "${USER_HOME}" "${USER_NAME}"
[ -d "${USER_HOME}" ] || mkdir -p "${USER_HOME}"
chown -R "${USER_UID}":"${USER_GID}" "${USER_HOME}"

# Start Xvfb
XVFB_SERVER=${XVFB_SERVER:-:99}
XVFB_SCREEN=${XVFB_SCREEN:-0}
XVFB_RESOLUTION=${XVFB_RESOLUTION:-1024x768x24}
nohup /usr/bin/Xvfb "${XVFB_SERVER}" -screen "${XVFB_SCREEN}" "${XVFB_RESOLUTION}" >/dev/null 2>&1 &
sleep 3
export DISPLAY=${XVFB_SERVER}

# Initialize Wine prefix
if [ ! -d "${USER_HOME}/.wine" ]; then
    echo "Initializing Wine prefix..."
    su - "${USER_NAME}" -c "export DISPLAY=${DISPLAY} && wineboot --init" || echo "wineboot init had warnings"
    sleep 5
fi

# Install JDK6 if not already installed
if [ ! -f "${USER_HOME}/.wine/drive_c/Program Files/Java/jdk1.6.0_45/bin/java.exe" ]; then
    echo "Installing JDK6..."
    cp /tmp/jdk6.exe "${USER_HOME}/jdk6.exe"
    chown "${USER_UID}":"${USER_GID}" "${USER_HOME}/jdk6.exe"
    su - "${USER_NAME}" -c "export DISPLAY=${DISPLAY} && wine '${USER_HOME}/jdk6.exe' /s /v'/qn REBOOT=Suppress IEXPLORE=1'" 2>&1 | tail -5 || true
    sleep 10
    rm -f "${USER_HOME}/jdk6.exe"
    if [ -f "${USER_HOME}/.wine/drive_c/Program Files/Java/jdk1.6.0_45/bin/java.exe" ]; then
        echo "JDK6 installation complete."
    else
        echo "ERROR: JDK6 installation may have failed - java.exe not found"
        ls -la "${USER_HOME}/.wine/drive_c/Program Files/Java/" 2>/dev/null || true
    fi
else
    echo "JDK6 already installed, skipping."
fi

# Start VNC
x11vnc -display ${DISPLAY} -forever -nopw -listen 0.0.0.0 -port 5900 -auth guess 2>/dev/null &
websockify --web /usr/share/novnc 8006 localhost:5900 &

# Start socat for serial port
socat PTY,link=/dev/ttyS0,raw,echo=0,b9600 TCP:inverter-simulator:5503 &

sleep 3

# Run SunVision as wineuser
cd /opt/sunvision
exec gosu "${USER_NAME}" wine "C:\\Program Files\\Java\\jdk1.6.0_45\\bin\\java.exe" -jar SunVision.jar