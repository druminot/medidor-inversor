#!/bin/bash
# test_simulator.sh — Levanta entorno de test con simulador de inversor
#
# Crea puertos serie virtuales con socat y ejecuta el simulador
# El modbus-reader se conecta a /tmp/inverter-master
#
# Uso:
#   ./test_simulator.sh           # Inicia todo
#   ./test_simulator.sh stop      # Detiene todo

set -e

MASTER_PORT="/tmp/inverter-master"
SLAVE_PORT="/tmp/inverter-slave"
SOCAT_PID=""
SIM_PID=""

cleanup() {
    echo "Deteniendo simulador y socat..."
    kill $SIM_PID 2>/dev/null || true
    kill $SOCAT_PID 2>/dev/null || true
    rm -f "$MASTER_PORT" "$SLAVE_PORT"
    echo "Listo."
    exit 0
}

trap cleanup INT TERM

if [ "$1" = "stop" ]; then
    pkill -f "inverter_simulator" 2>/dev/null || true
    pkill -f "socat.*inverter" 2>/dev/null || true
    rm -f "$MASTER_PORT" "$SLAVE_PORT"
    echo "Simulador y socat detenidos."
    exit 0
fi

echo "=== Simulador Modbus RTU - Riello H.P.6065REL-D ==="
echo ""

# Verificar dependencias
if ! command -v socat &>/dev/null; then
    echo "ERROR: socat no instalado"
    echo "Instalar con: sudo apt install socat   (o brew install socat en macOS)"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 no instalado"
    exit 1
fi

# Verificar pymodbus
if ! python3 -c "import pymodbus" 2>/dev/null; then
    echo "Instalando pymodbus..."
    pip3 install pymodbus
fi

# Limpiar puertos anteriores
pkill -f "socat.*inverter" 2>/dev/null || true
rm -f "$MASTER_PORT" "$SLAVE_PORT"
sleep 0.5

# Crear puertos serie virtuales
echo "Creando puertos serie virtuales..."
echo "  Master: $MASTER_PORT (para modbus-reader)"
echo "  Slave:  $SLAVE_PORT (para simulador)"
socat -d -d pty,raw,echo=0,link="$MASTER_PORT" pty,raw,echo=0,link="$SLAVE_PORT" &
SOCAT_PID=$!
sleep 1

# Verificar que los puertos existen
if [ ! -e "$MASTER_PORT" ] || [ ! -e "$SLAVE_PORT" ]; then
    echo "ERROR: No se pudieron crear los puertos virtuales"
    echo "Los puertos pueden aparecer con nombres diferentes."
    echo "Revisa los mensajes de socat arriba."
    cleanup
fi

echo ""
echo "Puertos creados OK."
echo ""

# Iniciar simulador
echo "Iniciando simulador en $SLAVE_PORT..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/inverter_simulator.py" --port "$SLAVE_PORT" --baud 9600 --slave 1 &
SIM_PID=$!

sleep 2

echo ""
echo "=== Entorno de test listo ==="
echo ""
echo "Simulador ejecutandose (PID: $SIM_PID)"
echo "Puerto master: $MASTER_PORT"
echo ""
echo "Para probar con modbus-reader:"
echo "  SERIAL_PORT=$MASTER_PORT ./modbus-reader"
echo ""
echo "Para probar con modbus_scan.py:"
echo "  python3 $SCRIPT_DIR/modbus_scan.py --port $MASTER_PORT --baud 9600 --slave 1 --unlock --scan-regs"
echo ""
echo "Para detener: $0 stop"
echo ""

wait