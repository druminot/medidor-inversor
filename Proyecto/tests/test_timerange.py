#!/usr/bin/env python3
"""Tests del modulo update_timerange: logica de periodos solares y dashboard time.

Cubre:
- _is_future_or_now: now, now-3h, futuro, pasado, malformed
- update_dashboard: estado stale -> corrige
- update_dashboard: estado correcto -> no reescribe
- update_dashboard: usuario pone now-3h -> respeta
- update_dashboard: usuario pone to futuro -> respeta
- update_dashboard: from stale (pasado) -> corrige
- get_solar_period: day (mock), after_sunset (mock), before_sunrise (mock)
"""
import importlib.util
import json
import os
import sys
import time
from unittest.mock import MagicMock


# Cargar update_timerange sin ejecutar main()
def _load_ut_module():
    path = os.path.join(os.path.dirname(__file__), '..', 'grafana', 'update_timerange.py')
    spec = importlib.util.spec_from_file_location("update_timerange", path)
    ut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ut)
    return ut


def _load_siser_module():
    """Mockea serial/psycopg2 para cargar siser_reader si fuera necesario."""
    sys.modules['serial'] = MagicMock()
    sys.modules['psycopg2'] = MagicMock()
    siser_path = os.path.join(os.path.dirname(__file__), '..', 'siser-reader', 'siser_reader.py')
    spec = importlib.util.spec_from_file_location("siser_reader", siser_path)
    siser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(siser)
    return siser


def test_is_future_or_now():
    ut = _load_ut_module()
    assert ut._is_future_or_now('now') is True
    assert ut._is_future_or_now('now-3h') is True
    assert ut._is_future_or_now('now-1d') is True
    future_iso = '2099-01-01T00:00:00.000Z'
    assert ut._is_future_or_now(future_iso) is True
    past_iso = '2020-01-01T00:00:00.000Z'
    assert ut._is_future_or_now(past_iso) is False
    assert ut._is_future_or_now('') is False
    assert ut._is_future_or_now(None) is False
    assert ut._is_future_or_now('not a date') is False


def _make_test_dashboard(file_path, time_from, time_to):
    """Crea un dashboard JSON de test con un campo time dado."""
    data = {
        'title': 'Test Dashboard',
        'panels': [],
        'time': {'from': time_from, 'to': time_to}
    }
    with open(str(file_path), 'w') as f:
        json.dump(data, f, indent=2)
    return data


def test_update_dashboard_stale_to_in_past(tmp_path):
    """Si el 'to' actual es timestamp absoluto en el pasado, debe reescribir a 'now'."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', '2026-06-19T14:49:43.000Z')

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', 'now')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time'] == {'from': '2026-06-19T12:23:44.000Z', 'to': 'now'}


def test_update_dashboard_already_correct(tmp_path):
    """Si el dashboard ya tiene los valores correctos, no reescribe (idempotente)."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', 'now')

    original_mtime = os.path.getmtime(str(dashboard_file))
    time.sleep(0.05)

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', 'now')
    assert result is True
    assert os.path.getmtime(str(dashboard_file)) == original_mtime, "File should not be rewritten"


def test_update_dashboard_respects_now_minus_3h(tmp_path):
    """Si el usuario puso to=now-3h, el updater no debe pisarlo durante el dia."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', 'now-3h')

    original_mtime = os.path.getmtime(str(dashboard_file))
    time.sleep(0.05)

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', 'now')
    assert result is True
    assert os.path.getmtime(str(dashboard_file)) == original_mtime, "User's now-3h choice must be respected"

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time']['to'] == 'now-3h'


def test_update_dashboard_respects_future_to(tmp_path):
    """Si el usuario puso un 'to' en el futuro, respetar (no pisar)."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', '2099-01-01T00:00:00.000Z')

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', 'now')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time']['to'] == '2099-01-01T00:00:00.000Z', "Future 'to' must be respected"


def test_update_dashboard_period_change_to_after_sunset(tmp_path):
    """day -> after_sunset: reescribe a (sunrise_today, sunset_today)."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', 'now')

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', '2026-06-19T21:22:24.000Z')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time'] == {
        'from': '2026-06-19T12:23:44.000Z',
        'to': '2026-06-19T21:22:24.000Z'
    }


def test_update_dashboard_period_change_to_before_sunrise(tmp_path):
    """after_sunset -> before_sunrise: reescribe a (sunrise_yesterday, sunset_yesterday)."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-19T12:23:44.000Z', '2026-06-19T21:22:24.000Z')

    result = ut.update_dashboard('2026-06-18T12:23:44.000Z', '2026-06-18T21:22:24.000Z')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time'] == {
        'from': '2026-06-18T12:23:44.000Z',
        'to': '2026-06-18T21:22:24.000Z'
    }


def test_update_dashboard_stale_from_in_past(tmp_path):
    """Si el 'from' esta stale (mucho en el pasado), corregir."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    _make_test_dashboard(dashboard_file, '2026-06-10T12:00:00.000Z', '2026-06-10T20:00:00.000Z')

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', '2026-06-19T21:22:24.000Z')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time'] == {
        'from': '2026-06-19T12:23:44.000Z',
        'to': '2026-06-19T21:22:24.000Z'
    }


def test_update_dashboard_handles_missing_time_field(tmp_path):
    """Si el dashboard no tiene campo 'time', debe agregarlo."""
    ut = _load_ut_module()
    dashboard_file = tmp_path / 'realtime.json'
    ut.DASHBOARD_PATH = str(dashboard_file)
    data = {'title': 'No time field', 'panels': []}
    with open(str(dashboard_file), 'w') as f:
        json.dump(data, f, indent=2)

    result = ut.update_dashboard('2026-06-19T12:23:44.000Z', 'now')
    assert result is True

    with open(str(dashboard_file)) as f:
        d = json.load(f)
    assert d['time'] == {'from': '2026-06-19T12:23:44.000Z', 'to': 'now'}


def test_get_solar_period_day(monkeypatch):
    """get_solar_period retorna 'day' cuando now esta entre sunrise y sunset."""
    from datetime import datetime, timezone
    ut = _load_ut_module()

    fake_now = datetime(2026, 6, 19, 15, 0, 0, tzinfo=timezone.utc)
    sunrise_today = datetime(2026, 6, 19, 12, 23, 44, tzinfo=timezone.utc)
    sunset_today = datetime(2026, 6, 19, 21, 22, 24, tzinfo=timezone.utc)
    sunrise_yesterday = datetime(2026, 6, 18, 12, 23, 44, tzinfo=timezone.utc)
    sunset_yesterday = datetime(2026, 6, 18, 21, 22, 24, tzinfo=timezone.utc)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (sunrise_today, sunset_today, sunrise_yesterday, sunset_yesterday)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(ut, '_now_utc', lambda: fake_now)

    period, time_from, time_to = ut.get_solar_period(mock_conn)
    assert period == 'day'
    assert time_to == 'now'
    assert '12:23:44' in time_from


def test_get_solar_period_after_sunset(monkeypatch):
    """get_solar_period retorna 'after_sunset' cuando now >= sunset_today."""
    from datetime import datetime, timezone
    ut = _load_ut_module()

    fake_now = datetime(2026, 6, 19, 23, 0, 0, tzinfo=timezone.utc)
    sunrise_today = datetime(2026, 6, 19, 12, 23, 44, tzinfo=timezone.utc)
    sunset_today = datetime(2026, 6, 19, 21, 22, 24, tzinfo=timezone.utc)
    sunrise_yesterday = datetime(2026, 6, 18, 12, 23, 44, tzinfo=timezone.utc)
    sunset_yesterday = datetime(2026, 6, 18, 21, 22, 24, tzinfo=timezone.utc)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (sunrise_today, sunset_today, sunrise_yesterday, sunset_yesterday)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(ut, '_now_utc', lambda: fake_now)

    period, time_from, time_to = ut.get_solar_period(mock_conn)
    assert period == 'after_sunset'
    assert time_to == '2026-06-19T21:22:24.000Z'
    assert '12:23:44' in time_from


def test_get_solar_period_before_sunrise(monkeypatch):
    """get_solar_period retorna 'before_sunrise' cuando now < sunrise_today."""
    from datetime import datetime, timezone
    ut = _load_ut_module()

    fake_now = datetime(2026, 6, 19, 5, 0, 0, tzinfo=timezone.utc)
    sunrise_today = datetime(2026, 6, 19, 12, 23, 44, tzinfo=timezone.utc)
    sunset_today = datetime(2026, 6, 19, 21, 22, 24, tzinfo=timezone.utc)
    sunrise_yesterday = datetime(2026, 6, 18, 12, 23, 44, tzinfo=timezone.utc)
    sunset_yesterday = datetime(2026, 6, 18, 21, 22, 24, tzinfo=timezone.utc)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (sunrise_today, sunset_today, sunrise_yesterday, sunset_yesterday)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(ut, '_now_utc', lambda: fake_now)

    period, time_from, time_to = ut.get_solar_period(mock_conn)
    assert period == 'before_sunrise'
    assert '2026-06-18' in time_from
    assert '2026-06-18' in time_to


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
