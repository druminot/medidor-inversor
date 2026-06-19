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
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Format logs as JSON (one line per record) for machine parsing."""

    def format(self, record):
        payload = {
            'ts': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging():
    fmt = os.environ.get('LOG_FORMAT', 'text').lower()
    level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    if fmt == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
    root.addHandler(handler)


_rate_limit_state = {}


def log_rate_limited(key, interval_sec, log_fn, message):
    now = time.time()
    state = _rate_limit_state.get(key, {'last': 0.0, 'count': 0})
    if now - state['last'] >= interval_sec:
        if state['count'] > 0:
            log_fn(f"{message} (suppressed {state['count']} similar in last {interval_sec}s)")
        else:
            log_fn(message)
        _rate_limit_state[key] = {'last': now, 'count': 0}
    else:
        state['count'] += 1
        _rate_limit_state[key] = state


setup_logging()
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


def _now_utc():
    """Return current UTC datetime. Wrapped in function for testability."""
    return datetime.now(timezone.utc)


def get_solar_period(conn):
    now_utc = _now_utc()
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
        log_rate_limited('db_query_error', 60, log.error, f"db_query_error: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None

    if not row or not all(row):
        log_rate_limited('sun_times_null', 60, log.error, "sun_times_null from_db")
        return None

    sunrise_today = row[0]
    sunset_today = row[1]
    sunrise_yesterday = row[2]
    sunset_yesterday = row[3]

    if not all([sunrise_today, sunset_today, sunrise_yesterday, sunset_yesterday]):
        log_rate_limited('sun_times_null_partial', 60, log.error, "sun_times_null_partial")
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


def _is_future_or_now(time_str):
    """Return True if time_str is 'now'/'now-*' or a timestamp >= now (UTC).

    Used to detect 'stale' absolute timestamps in the past that should be
    overwritten by the updater, while respecting user-selected ranges
    pointing to 'now' or future.
    """
    if not time_str:
        return False
    if time_str == 'now' or time_str.startswith('now'):
        return True
    try:
        ts_str = time_str.replace('Z', '+00:00') if time_str.endswith('Z') else time_str
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            return True
        return ts.timestamp() >= time.time()
    except (ValueError, TypeError):
        return False


def update_dashboard(time_from, time_to):
    try:
        with open(DASHBOARD_PATH) as f:
            dashboard = json.load(f)
    except Exception as e:
        log_rate_limited('dashboard_read_error', 60, log.error, f"dashboard_read_error: {e}")
        return False

    if not isinstance(dashboard, dict):
        log.error(f"Dashboard JSON is not a dict (type={type(dashboard).__name__})")
        return False

    current_time = dashboard.get('time')

    if isinstance(current_time, dict):
        current_from = current_time.get('from')
        current_to = current_time.get('to')

        if current_from == time_from and current_to == time_to:
            return True

        if current_from == time_from and time_to == 'now' and _is_future_or_now(current_to):
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
        log.info(
            f"dashboard_time_updated from={time_from} to={time_to} "
            f"prev_from={current_time.get('from') if isinstance(current_time, dict) else None} "
            f"prev_to={current_time.get('to') if isinstance(current_time, dict) else None}"
        )
        return True
    except PermissionError as e:
        log_rate_limited(
            'dashboard_write_permission',
            300,
            log.error,
            f"dashboard_write_permission_denied path={DASHBOARD_PATH} err={e}"
        )
    except OSError as e:
        log_rate_limited('dashboard_write_error', 60, log.error, f"dashboard_write_error: {e}")
    except Exception as e:
        log_rate_limited('dashboard_write_unexpected', 60, log.error, f"dashboard_write_unexpected: {e}")

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
    last_successful_period = None

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
                log_rate_limited('solar_period_unavailable', 60, log.error, "solar_period_unavailable")
                last_period = None
                time.sleep(CHECK_INTERVAL)
                continue

            period, time_from, time_to = result

            needs_rewrite = (
                period != last_period
                or last_successful_period != period
            )

            if needs_rewrite:
                log.info(
                    f"solar_period_change from={last_period} to={period} "
                    f"time_from={time_from} time_to={time_to}"
                )
                if update_dashboard(time_from, time_to):
                    last_period = period
                    last_successful_period = period
                else:
                    time.sleep(30)
                    continue

            time.sleep(CHECK_INTERVAL)

        except psycopg2.OperationalError as e:
            log_rate_limited('db_connection_error', 60, log.error, f"db_connection_error: {e}")
            conn = None
            last_period = None
            time.sleep(30)
        except Exception as e:
            log_rate_limited('unexpected_error', 60, log.error, f"unexpected_error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
