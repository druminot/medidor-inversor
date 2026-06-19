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

## Hardware: Riello H.P.6065REL-D

- **Single-phase** 220V AC grid output (NOT three-phase as old docs say)
- 3 MPPT DC inputs; only MPPT2 has panels connected (~230-280V, 0.1-0.8A)
- MPPT1 and MPPT3 show 0V/0A
- Protocol L1/L2/L3 AC offsets are redundant copies of the same single-phase measurement
  (the protocol was designed for SENTR 3/3 three-phase; H.P.6065REL-D reuses same layout)
- `pac` = `vac1 × iac1` is the correct total AC power; do NOT sum L1+L2+L3

## Project Structure

- `Proyecto/` — all runnable code and Docker configs
- `Proyecto/siser-reader/` — **active** daemon (single file: `siser_reader.py`)
- `Proyecto/modbus-reader/` — **legacy, do not use**
- `Proyecto/inverter-simulator/` — simulator for dev/testing (no hardware needed)
- `Proyecto/db/` — `init.sql` (schema), `seed.sql` (dev data), `sunrise_functions.sql` (solar position math), `migrate_db.sh` (apply CAGGs v2 + triggers to existing DB)
- `Proyecto/grafana/` — provisioning + 4 dashboards
- `Proyecto/tools/` — diagnostic scripts (`modbus_scan.py`, `diagnose_inverter.py`)
- `Proyecto/tests/` — pytest unit tests (`test_siser_protocol.py`)
- `Proyecto/ruff.toml` — Python linting config
- `Proyecto/deploy.sh` — uploads files to lautaro via ngrok cmd-server (uses `DEPLOY_PASS` env var or `~/.netrc`)
- `.githooks/pre-commit` — detects hardcoded passwords
- `.github/workflows/ci.yml` — ruff + pytest + docker build
- Root-level `NN_*.md` files — project documentation/decisions

## Commands

```bash
# Production (on lautaro server /opt/solar-monitor/)
cd /opt/solar-monitor
docker compose up -d
docker compose logs -f siser-reader
docker compose ps

# Apply CAGGs v2 + triggers + view to existing DB (idempotent)
bash db/migrate_db.sh | docker compose exec -T timescaledb \
    psql -U solar -d solar_monitor

# Local dev (simulator, no real hardware)
cd Proyecto
docker compose -f docker-compose.dev.yml up -d
# Seeds DB with 48h of fake data, uses modbus-reader simulator

# Scan serial port (requires real hardware)
python3 Proyecto/tools/modbus_scan.py /dev/inverter-serial

# Deploy from local to production
DEPLOY_PASS=lsistem19 bash Proyecto/deploy.sh
# After deploy: rebuild + recreate containers to apply code changes
cd /opt/solar-monitor
docker compose build siser-reader timerange-updater
docker compose stop siser-reader timerange-updater
docker compose rm -f siser-reader timerange-updater
docker compose up -d siser-reader timerange-updater
```

## Docker Services

**Production** (`docker-compose.yml`): 4 services — siser-reader, timescaledb, grafana, timerange-updater
**Dev** (`docker-compose.dev.yml`): modbus-reader (with simulator), timescaledb (with seed.sql), grafana

All services have: `no-new-privileges`, `cap_drop: ALL`, healthchecks, log rotation (10m max-size, 3 files), mem_limit.

Required env vars: `DB_PASSWORD`, `GRAFANA_PASSWORD`, `GRAFANA_READER_PASSWORD`.

## Database Schema

- `siser-reader` writes to `realtime` every 5s (also daemon self-heartbeat every 5min with `status=4`)
- `realtime` has 30d retention, compressed after 3 days
- Triggers on `realtime` automatically populate:
  - `events_v2`: connectivity + inverter_status changes with severity 1-4
  - `cumulatives`: extracts energy_total/hours_total and computes energy_daily + co2_saved (max ~24 rows/day)
- Continuous aggregates v2 (`slow_samples_v2`, `hourly_energy_v2`, `daily_energy_v2`) are populated from `realtime` directly
  (the old `slow_samples`/`hourly_energy`/`daily_energy` are empty because nothing writes to `fast_samples`)
- View `realtime_clean` is `SELECT * FROM realtime WHERE is_stale = false` — used by all Grafana dashboards
- Original `fast_samples`/`cumulatives` (legacy C daemon data) preserved but not updated

## Serial Port

- Device: `/dev/inverter-serial` (udev symlink for CH340 USB-RS232 adapter)
- Baud: 9600, 8N1
- Docker maps `/dev/inverter-serial` into the container with `device_cgroup_rules: 'c 188:* rwm'` and `group_add: dialout`

## siser-reader State Persistence

`/tmp/siser_state.json` (configurable via `SISER_STATE_FILE`) is created after a successful handshake/read and used to skip the handshake on the next restart (~6s saved). TTL is 24h by default.

State file fields:
- `registered`: bool — set True after first successful read
- `last_success`: float — unix timestamp
- `inverter_addr`: int — usually 33
- `serial_number_hex` / `serial_str`: optional, only set after full handshake (offlineEnquiry + sendAddress)

Healthcheck verifies file exists: `pgrep -f siser_reader.py > /dev/null && [ -e /tmp/siser_state.json ]`

## Deployment

- Target: Ubuntu Server `lautaro` at `/opt/solar-monitor/`
- `deploy.sh` uploads files via base64 chunks through the ngrok cmd-server
- **Critical**: `restart` alone does NOT pick up Python code changes — you must `build + rm + up` (see Commands section)
- Remote access: ngrok + nginx reverse proxy (Grafana on anonymous viewer, ttyd/cmd-server with basic auth)
- **Never commit** `.env`, passwords, or the ngrok URL to the repo
