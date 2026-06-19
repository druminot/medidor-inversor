# Medidor Inversor — Agent Instructions

## Protocol: SISER (NOT Modbus)

The inverter uses the **SISER (Phoenixtec) binary protocol**, discovered by reverse-engineering SunVision. The old `modbus-reader` (C) is **legacy and inactive**. The active daemon is `siser-reader` (Python).

Key SISER details an agent would get wrong:
- **Not Modbus RTU** — despite filenames like `04_PROTOCOLO_MODBUS.md` and `modbus_scan.py`, the current protocol is SISER
- Handshake required: `offlineEnquiry` → `sendAddress` (assigns address 33) before reading data
- RTS/DTR control mandatory: RTS=True before TX, RTS=False after TX; DTR=True always (powers the opto-coupler RX circuit)
- 600ms delay before each command
- Frame format: `AA AA 01 00 00 [addr] [group] [cmd] [dlen] [data...] [chkH] [chkL]` (additive checksum)
- `0xFFFF` = not connected / invalid value

## Project Structure

- `Proyecto/` — all runnable code and Docker configs
- `Proyecto/siser-reader/` — **active** daemon (single file: `siser_reader.py`)
- `Proyecto/modbus-reader/` — **legacy, do not use**
- `Proyecto/inverter-simulator/` — simulator for dev/testing (no hardware needed)
- `Proyecto/db/` — `init.sql` (schema), `seed.sql` (dev data), `sunrise_functions.sql` (solar position math)
- `Proyecto/grafana/` — provisioning + 4 dashboards
- `Proyecto/tools/` — diagnostic scripts (`modbus_scan.py`, `diagnose_inverter.py`)
- Root-level `NN_*.md` files — project documentation/decisions

## Commands

```bash
# Production (on lautaro server /opt/solar-monitor/)
docker compose up -d
docker compose logs -f siser-reader
docker compose ps

# Local dev (simulator, no real hardware)
cd Proyecto
docker compose -f docker-compose.dev.yml up -d
# Seeds DB with 48h of fake data, uses modbus-reader simulator

# Scan serial port (requires real hardware)
python3 Proyecto/tools/modbus_scan.py /dev/inverter-serial
```

## Docker Services

**Production** (`docker-compose.yml`): 3 services — siser-reader, timescaledb, grafana
**Dev** (`docker-compose.dev.yml`): modbus-reader (with simulator), timescaledb (with seed.sql), grafana

No `.env.example` exists — required vars are visible in `docker-compose.yml`: `DB_PASSWORD`, `GRAFANA_PASSWORD`, `GRAFANA_READER_PASSWORD`.

## Database Schema Gotchas

- `siser-reader` **only writes to `realtime`** table currently; `fast_samples`, `cumulatives`, `daily_production` tables exist but are empty
- Continuous aggregates (`slow_samples`, `hourly_energy`, `daily_energy`) depend on `fast_samples` and will be empty
- Schema auto-migrates on startup: `_ensure_schema()` in `siser_reader.py` adds columns via `ALTER TABLE IF NOT EXISTS`
- `realtime` has both legacy single-value columns (`vpv`, `ipv`, `vac`, `iac`, `pac`) and MPPT-specific columns (`vpv1`–`vpv3`, `ppv1`–`ppv3`, etc.)
- Only MPPT2 has panels connected; MPPT1 and MPPT3 show 0V/0A

## Serial Port

- Device: `/dev/inverter-serial` (udev symlink for CH340 USB-RS232 adapter)
- Baud: 9600, 8N1
- Docker maps `/dev/inverter-serial` into the container with `device_cgroup_rules: 'c 188:* rwm'` and `group_add: dialout`

## Deployment

- Target: Ubuntu Server `lautaro` at `/opt/solar-monitor/`
- `deploy.sh` uploads files via base64 chunks through the ngrok cmd-server
- Remote access: ngrok + nginx reverse proxy (Grafana on anonymous viewer, ttyd/cmd-server with basic auth)
- **Never commit** `.env`, passwords, or the ngrok URL to the repo