#!/usr/bin/env python3
"""
airplay_pair.py — Envía request de emparejamiento AirPlay a una Roku TV.
El PIN se muestra en la TV y debe ingresarse manualmente luego.

Uso:
  python3 airplay_pair.py <IP_ROKU> [DEVICE_NAME]

Ejemplo:
  python3 airplay_pair.py 192.168.0.176 lautaro-linux
"""

import http.client
import json
import socket
import sys
import uuid


def get_device_id():
    return str(uuid.uuid4())


def send_pair_request(host, port=7000, device_name="lautaro-linux"):
    device_id = get_device_id()

    print(f"[*] Enviando request de emparejamiento AirPlay a {host}:{port}")
    print(f"[*] Device ID: {device_id}")
    print(f"[*] Device Name: {device_name}")
    print()

    try:
        conn = http.client.HTTPConnection(host, port, timeout=10)

        body = json.dumps({
            "deviceID": device_id,
            "serviceName": device_name,
            "features": "0x5A7FFFF7,0x1E",
            "statusFlags": "4",
            "protocolVersion": "1.1",
            "model": "Linux",
            "name": device_name,
            "os": "Linux"
        })

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AirPlay/540.31",
            "X-Apple-Device-ID": device_id.replace("-", "").upper(),
            "X-Apple-Session-ID": str(uuid.uuid4()).upper(),
        }

        conn.request("POST", "/pair-pin-start", body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode()

        print(f"[+] Response: {resp.status} {resp.reason}")
        if data:
            print(f"[+] Body: {data}")

        if resp.status == 200:
            print()
            print("[OK] Request de emparejamiento enviado con éxito.")
            print("     Deberías ver un PIN en la pantalla de la Roku TV.")
            print("     Para completar el pairing, ejecuta:")
            print(f"     python3 airplay_verify.py {host} {device_id} <PIN>")
        elif resp.status == 470:
            print()
            print("[!] La TV ya requiere un PIN. Mirá la pantalla de la TV.")
        else:
            print()
            print(f"[!] Respuesta inesperada: {resp.status}")

        conn.close()

    except ConnectionRefusedError:
        print(f"[X] Conexión rechazada en {host}:{port}")
        print("    ¿AirPlay está habilitado en la Roku TV?")
        print("    Settings > Apple AirPlay and HomeKit > Enable AirPlay")
    except socket.timeout:
        print(f"[X] Timeout conectando a {host}:{port}")
        print("    ¿La Roku TV está encendida y en la misma red?")
    except Exception as e:
        print(f"[X] Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <IP_ROKU> [DEVICE_NAME]")
        sys.exit(1)

    roku_ip = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "lautaro-linux"
    send_pair_request(roku_ip, device_name=name)
