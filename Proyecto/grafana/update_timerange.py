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
"""
import json
import os
import time
import logging
import tempfile
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('update_timerange')

DASHBOARD_PATH = os.environ.get('DASHBOARD_PATH', '/dashboards/realtime.json')
DB_HOST = os.environ.get('DB_HOST', 'timescaledb')
DB_PORT = int(os.environ.get('DB_PORT', '5432'))
DB_NAME = os.environ.get('DB_NAME', 'solar_monitor')
DB_USER = os.environ.get('DB_USER', 'solar')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'solar')
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '60'))


def get_solar_period(conn):
    """Returns (period, time_from, time_to) based on current time vs sunrise/sunset.

    period is one of: 'day', 'after_sunset', 'before_sunrise'
    time_from/time_to are the dashboard time range values for this period.
    During 'day', time_to is "now" (relative) so Grafana auto-updates without file writes.
    """
    now_utc = datetime.now(timezone.utc)
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
        return None

    if not row or not row[0] or not row[1]:
        log.error("Could not get sun times from DB")
        return None

    sunrise_today = row[0]
    sunset_today = row[1]
    sunrise_yesterday = row[2]
    sunset_yesterday = row[3]

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
    """Atomically update the dashboard JSON file with the new time range."""
    try:
        with open(DASHBOARD_PATH, 'r') as f:
            dashboard = json.load(f)
    except Exception as e:
        log.error(f"Could not read dashboard file: {e}")
        return False

    current_time = dashboard.get('time', {})
    if current_time.get('from') == time_from and current_time.get('to') == time_to:
        return True

    dashboard['time'] = {'from': time_from, 'to': time_to}

    dir_path = os.path.dirname(DASHBOARD_PATH)
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
        try:
            os.unlink(tmp_path)
        except:
            pass
        return False


def main():
    import psycopg2

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
                time.sleep(60)
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
            time.sleep(30)
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            time.sleep(60)


if __name__ == '__main__':
    main()