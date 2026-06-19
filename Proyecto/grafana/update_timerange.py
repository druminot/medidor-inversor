#!/usr/bin/env python3
"""
Updates the Grafana dashboard time range based on solar position.

Only writes the dashboard file when the solar period changes (3 transitions per day):
  - At sunrise:  from = sunrise_today (absoluto), to = "now" (relativo Grafana)
  - At sunset:   from = sunrise_today (absoluto), to = sunset_today (absoluto)
  - At midnight: from = sunrise_yesterday (absoluto), to = sunset_yesterday (absoluto)

Between transitions, the file is NOT written, so Grafana does not re-provision
and the user's time picker selection is respected.

Uses sunrise_concepcion() and sunset_concepcion() PostgreSQL functions.
Writes directly to the dashboard JSON file using atomic write (temp + rename).
Uses flock to prevent concurrent instances from flip-flopping the dashboard.
"""
import fcntl
import json
import logging
import os
import sys
import tempfile
import time
from datetime import UTC, datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('update_timerange')

DASHBOARD_PATH = os.environ.get('DASHBOARD_PATH', '/dashboards/realtime.json')
DB_HOST = os.environ.get('DB_HOST', 'timescaledb')
try:
    DB_PORT = int(os.environ.get('DB_PORT', '5432'))
except ValueError:
    DB_PORT = 5432
DB_NAME = os.environ.get('DB_NAME', 'solar_monitor')
DB_USER = os.environ.get('DB_USER', 'solar')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'solar')
try:
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '60'))
    if CHECK_INTERVAL < 1:
        CHECK_INTERVAL = 60
except ValueError:
    CHECK_INTERVAL = 60


def acquire_lock():
    lock_path = '/tmp/timerange_updater.lock'
    lock_fd = open(lock_path, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except OSError:
        log.error("Another instance is already running, exiting")
        sys.exit(1)


def get_solar_period(conn):
    now_utc = datetime.now(UTC)
    today = now_utc.date()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sunrise_concepcion(%s::date),
                       sunset_concepcion(%s::date),
                       sunrise_concepcion(%s::date - 1),
                       sunset_concepcion(%s::date - 1)
            """, [today, today, today, today])
            row = cur.fetchone()
    except Exception as e:
        log.error(f"DB query error: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None

    if not row or not all(row):
        log.error("Could not get sun times from DB (NULL values)")
        return None

    sunrise_today = row[0]
    sunset_today = row[1]
    sunrise_yesterday = row[2]
    sunset_yesterday = row[3]

    if not all([sunrise_today, sunset_today, sunrise_yesterday, sunset_yesterday]):
        log.error("One or more sun times are NULL")
        return None

    if now_utc >= sunrise_today and now_utc < sunset_today:
        period = 'day'
        time_from = sunrise_today.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        time_to = 'now'
    elif now_utc >= sunset_today:
        period = 'after_sunset'
        time_from = sunrise_today.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        time_to = sunset_today.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    else:
        period = 'before_sunrise'
        time_from = sunrise_yesterday.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        time_to = sunset_yesterday.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    return period, time_from, time_to


def update_dashboard(time_from, time_to):
    try:
        with open(DASHBOARD_PATH) as f:
            dashboard = json.load(f)
    except Exception as e:
        log.error(f"Could not read dashboard file: {e}")
        return False

    if not isinstance(dashboard, dict):
        log.error(f"Dashboard JSON is not a dict (type={type(dashboard).__name__})")
        return False

    current_time = dashboard.get('time')
    if isinstance(current_time, dict) and current_time.get('from') == time_from and current_time.get('to') == time_to:
        return True

    dashboard['time'] = {'from': time_from, 'to': time_to}

    dir_path = os.path.dirname(DASHBOARD_PATH) or '.'
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(dashboard, f, indent=2, ensure_ascii=False)
        os.chmod(tmp_path, 0o644)
        os.rename(tmp_path, DASHBOARD_PATH)
        log.info(f"Dashboard time range updated: {time_from} to {time_to}")
        return True
    except Exception as e:
        log.error(f"Could not write dashboard file: {e}")
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return False


def main():
    import psycopg2

    acquire_lock()

    conn = None
    last_period = None

    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg2.connect(
                    host=DB_HOST, port=DB_PORT,
                    dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                    keepalives=1, keepalives_idle=60,
                    keepalives_interval=10, keepalives_count=3
                )
                conn.autocommit = True

            result = get_solar_period(conn)
            if not result:
                log.error("Could not compute solar period")
                last_period = None
                time.sleep(CHECK_INTERVAL)
                continue

            period, time_from, time_to = result

            if period != last_period:
                log.info(f"Solar period changed: {last_period} -> {period}")
                if update_dashboard(time_from, time_to):
                    last_period = period
                else:
                    time.sleep(30)
                    continue

            time.sleep(CHECK_INTERVAL)

        except psycopg2.OperationalError as e:
            log.error(f"DB connection error: {e}")
            conn = None
            last_period = None
            time.sleep(30)
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
