FROM eclipse-temurin:8-jdk

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify socat \
    libgl1 libglib2.0-0 libgtk2.0-0 libxtst6 xauth \
    && rm -rf /var/lib/apt/lists/*

COPY sv_cab/ /opt/sunvision/

ENV DISPLAY=:99

# Generate X authority file for x11vnc to work with Xvfb
RUN touch /root/.Xauthority

CMD ["bash", "-c", " \
    Xvfb :99 -screen 0 1280x720x24 -auth /root/.Xauthority & \
    XVFB_PID=$!; \
    sleep 3; \
    if ! kill -0 $XVFB_PID 2>/dev/null; then echo 'Xvfb failed to start'; exit 1; fi; \
    export DISPLAY=:99; \
    export XAUTHORITY=/root/.Xauthority; \
    x11vnc -display :99 -auth /root/.Xauthority -forever -nopw -listen 0.0.0.0 -rfbport 5900 & \
    X11VNC_PID=$!; \
    sleep 2; \
    if ! kill -0 $X11VNC_PID 2>/dev/null; then echo 'x11vnc failed, retrying without auth'; x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 & sleep 1; fi; \
    websockify --web /usr/share/novnc 8006 localhost:5900 & \
    socat PTY,link=/dev/ttyS0,raw,echo=0,b9600 TCP:inverter-simulator:5503 & \
    cd /opt/sunvision && \
    java -Djava.library.path=/opt/sunvision -cp '.:*' com.ups.sunvision.SunVision \
"]