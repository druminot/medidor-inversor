#!/usr/bin/env python3
"""
airplay_verify.py — Completa el emparejamiento AirPlay ingresando el PIN
que se muestra en la Roku TV.

Uso:
  python3 airplay_verify.py <IP_ROKU> <DEVICE_ID> <PIN>

Ejemplo:
  python3 airplay_verify.py 192.168.0.176 abc123-def456-... 1234
"""

import sys
import uuid
import json
import http.client


def verify_pin(host, port, device_id, pin):
    print(f"[*] Verificando PIN {pin} con {host}:{port}")
    print(f"[*] Device ID: {device_id}")
    print()

    try:
        conn = http.client.HTTPConnection(host, port, timeout=10)

        body = json.dumps({
            "deviceID": device_id,
            "pin": pin,
        })

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AirPlay/540.31",
            "X-Apple-Device-ID": device_id.replace("-", "").upper(),
            "X-Apple-Session-ID": str(uuid.uuid4()).upper(),
        }

        conn.request("POST", "/pair-verify", body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode()

        print(f"[+] Response: {resp.status} {resp.reason}")
        if data:
            print(f"[+] Body: {data}")

        if resp.status == 200:
            print()
            print("[OK] Emparejamiento exitoso! El dispositivo está autorizado para AirPlay.")
        else:
            print()
            print("[X] PIN incorrecto o error. Reintentá con el PIN que muestra la TV.")

        conn.close()

    except Exception as e:
        print(f"[X] Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <IP_ROKU> <DEVICE_ID> <PIN>")
        print()
        print("El DEVICE_ID lo obtenés al ejecutar airplay_pair.py")
        sys.exit(1)

    roku_ip = sys.argv[1]
    dev_id = sys.argv[2]
    pin = sys.argv[3]
    verify_pin(roku_ip, 7000, dev_id, pin)