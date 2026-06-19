#!/usr/bin/env python3
"""
Updates the Grafana dashboard time range based on solar position.

Logic:
  - Between sunrise and sunset (daytime): show sunrise -> now
  - After sunset, before midnight: show sunrise -> sunset of today
  - After midnight, before sunrise: show sunrise -> sunset of yesterday

Uses sunrise_concepcion() and sunset_concepcion() PostgreSQL functions.
Writes directly to the dashboard JSON file; Grafana picks up changes automatically
via file provisioning (updateIntervalSeconds: 10).
"""
import json
import os
import time
import logging
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
UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', '300'))


def get_sun_times_from_db(conn):
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    sunrise_today = None
    sunset_today = None
    sunrise_yesterday = None
    sunset_yesterday = None

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sunrise_concepcion(%s::date),
                       sunset_concepcion(%s::date),
                       sunrise_concepcion(%s::date - 1),
                       sunset_concepcion(%s::date - 1)
            """, [today, today, today, today])
            row = cur.fetchone()
            if row:
                sunrise_today = row[0]
                sunset_today = row[1]
                sunrise_yesterday = row[2]
                sunset_yesterday = row[3]
    except Exception as e:
        log.error(f"DB query error: {e}")
        return None

    if not sunrise_today or not sunset_today:
        log.error("Could not get sun times from DB")
        return None

    return {
        'now_utc': now_utc,
        'sunrise_today': sunrise_today,
        'sunset_today': sunset_today,
        'sunrise_yesterday': sunrise_yesterday,
        'sunset_yesterday': sunset_yesterday,
    }


def compute_time_range(sun_times):
    now = sun_times['now_utc']
    sunrise_today = sun_times['sunrise_today']
    sunset_today = sun_times['sunset_today']
    sunrise_yesterday = sun_times['sunrise_yesterday']
    sunset_yesterday = sun_times['sunset_yesterday']

    if now >= sunrise_today and now < sunset_today:
        time_from = sunrise_today
        time_to = now
    elif now >= sunset_today:
        time_from = sunrise_today
        time_to = sunset_today
    else:
        time_from = sunrise_yesterday
        time_to = sunset_yesterday

    return time_from, time_to


def update_dashboard(time_from, time_to):
    from_str = time_from.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    to_str = time_to.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    try:
        with open(DASHBOARD_PATH, 'r') as f:
            dashboard = json.load(f)
    except Exception as e:
        log.error(f"Could not read dashboard file: {e}")
        return False

    current_time = dashboard.get('time', {})
    if current_time.get('from') == from_str and current_time.get('to') == to_str:
        log.info(f"Time range unchanged: {from_str} to {to_str}")
        return True

    dashboard['time'] = {'from': from_str, 'to': to_str}

    try:
        with open(DASHBOARD_PATH, 'w') as f:
            json.dump(dashboard, f, indent=2, ensure_ascii=False)
        log.info(f"Updated dashboard time range: {from_str} to {to_str}")
        return True
    except Exception as e:
        log.error(f"Could not write dashboard file: {e}")
        return False


def main():
    import psycopg2

    conn = None
    last_update = 0

    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg2.connect(
                    host=DB_HOST, port=DB_PORT,
                    dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
                )
                conn.autocommit = True

            sun_times = get_sun_times_from_db(conn)
            if sun_times:
                time_from, time_to = compute_time_range(sun_times)
                now = time.time()
                if now - last_update >= UPDATE_INTERVAL:
                    if update_dashboard(time_from, time_to):
                        last_update = now
                    else:
                        time.sleep(30)
                        continue
            else:
                log.error("Could not compute sun times")
                time.sleep(60)
                continue

            time.sleep(UPDATE_INTERVAL)

        except psycopg2.OperationalError as e:
            log.error(f"DB connection error: {e}")
            conn = None
            time.sleep(30)
        except Exception as e:
            log.error(f"Unexpected error: {e}")
            time.sleep(60)


if __name__ == '__main__':
    main()