#!/usr/bin/env python3
"""Tests del modulo de logging.

Cubre:
- setup_logging con LOG_FORMAT=text/json
- log_rate_limited: 1ra llamada loguea, 2da suprime, despues del interval loguea
- log_rate_limited: keys diferentes son independientes
- read_rss_mb: lee /proc/self/status correctamente

Mock de modulos externos no disponibles en el entorno de tests.
"""
import importlib.util
import logging
import os
import sys
import time
from unittest.mock import MagicMock


# Cargar siser_reader sin ejecutarlo (sin pyserial/psycopg2)
def _load_siser_module():
    sys.modules['serial'] = MagicMock()
    sys.modules['psycopg2'] = MagicMock()

    SISER_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'siser-reader', 'siser_reader.py'
    )
    spec = importlib.util.spec_from_file_location("siser_reader", SISER_PATH)
    siser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(siser)
    return siser


def _load_update_timerange_module():
    UT_PATH = os.path.join(
        os.path.dirname(__file__), '..', 'grafana', 'update_timerange.py'
    )
    spec = importlib.util.spec_from_file_location("update_timerange", UT_PATH)
    ut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ut)
    return ut


def test_setup_logging_text_format(monkeypatch, capsys):
    """LOG_FORMAT=text produce logs legibles en formato tradicional."""
    monkeypatch.setenv('LOG_FORMAT', 'text')
    monkeypatch.setenv('LOG_LEVEL', 'INFO')
    siser = _load_siser_module()
    siser.setup_logging()
    siser.log.info("hello world")
    captured = capsys.readouterr()
    assert "hello world" in captured.err


def test_setup_logging_json_format(monkeypatch, capsys):
    """LOG_FORMAT=json produce logs parseables como JSON."""
    import json
    monkeypatch.setenv('LOG_FORMAT', 'json')
    monkeypatch.setenv('LOG_LEVEL', 'INFO')
    siser = _load_siser_module()
    siser.setup_logging()
    siser.log.info("test_json_event")
    captured = capsys.readouterr()
    assert "test_json_event" in captured.err
    lines = [line for line in captured.err.splitlines() if line.strip().startswith('{')]
    assert lines, "Expected at least one JSON line"
    parsed = json.loads(lines[-1])
    assert parsed['message'] == "test_json_event"


def test_json_formatter_valid_json():
    """JsonFormatter emite JSON valido con campos requeridos."""
    siser = _load_siser_module()
    formatter = siser.JsonFormatter()
    record = logging.LogRecord(
        name='test', level=logging.INFO, pathname='', lineno=0,
        msg='mensaje de prueba', args=(), exc_info=None
    )
    import json
    parsed = json.loads(formatter.format(record))
    assert 'ts' in parsed
    assert parsed['level'] == 'INFO'
    assert parsed['logger'] == 'test'
    assert parsed['message'] == 'mensaje de prueba'


def test_log_rate_limited_first_call_logs(monkeypatch):
    """Primera llamada dentro del interval siempre loguea."""
    siser = _load_siser_module()
    siser._rate_limit_state.clear()
    captured = []
    monkeypatch.setattr(siser.log, 'warning', lambda msg: captured.append(msg))
    siser.log_rate_limited('test_key_1', 60, siser.log.warning, "primer error")
    assert len(captured) == 1
    assert captured[0] == "primer error"


def test_log_rate_limited_second_call_suppressed(monkeypatch):
    """Segunda llamada dentro del interval NO loguea (incrementa counter)."""
    siser = _load_siser_module()
    siser._rate_limit_state.clear()
    captured = []
    monkeypatch.setattr(siser.log, 'warning', lambda msg: captured.append(msg))
    siser.log_rate_limited('test_key_2', 60, siser.log.warning, "primero")
    siser.log_rate_limited('test_key_2', 60, siser.log.warning, "segundo")
    siser.log_rate_limited('test_key_2', 60, siser.log.warning, "tercero")
    assert len(captured) == 1


def test_log_rate_limited_after_interval_logs(monkeypatch):
    """Despues del interval, loguea de nuevo + incluye count de suprimidos."""
    siser = _load_siser_module()
    siser._rate_limit_state.clear()
    captured = []
    monkeypatch.setattr(siser.log, 'warning', lambda msg: captured.append(msg))

    # Simular: ultima llamada fue hace 61s
    siser._rate_limit_state['test_key_3'] = {'last': time.time() - 61, 'count': 5}
    siser.log_rate_limited('test_key_3', 60, siser.log.warning, "nuevo error")
    assert len(captured) == 1
    assert "suppressed 5" in captured[0]
    assert "nuevo error" in captured[0]


def test_log_rate_limited_different_keys_independent(monkeypatch):
    """Keys separadas tienen rate limits independientes."""
    siser = _load_siser_module()
    siser._rate_limit_state.clear()
    captured = []
    monkeypatch.setattr(siser.log, 'warning', lambda msg: captured.append(msg))
    siser.log_rate_limited('key_A', 60, siser.log.warning, "A1")
    siser.log_rate_limited('key_B', 60, siser.log.warning, "B1")
    siser.log_rate_limited('key_A', 60, siser.log.warning, "A2")
    assert len(captured) == 2
    assert "A1" in captured[0]
    assert "B1" in captured[1]


def test_read_rss_mb_returns_number():
    """read_rss_mb retorna un float positivo (o None si /proc no existe)."""
    siser = _load_siser_module()
    rss = siser.read_rss_mb()
    if rss is not None:
        assert isinstance(rss, float)
        assert rss > 0


def test_update_timerange_setup_logging(monkeypatch, capsys):
    """update_timerange.setup_logging no falla con env vars."""
    monkeypatch.setenv('LOG_FORMAT', 'text')
    monkeypatch.setenv('LOG_LEVEL', 'INFO')
    ut = _load_update_timerange_module()
    ut.setup_logging()
    ut.log.info("test ut")
    captured = capsys.readouterr()
    assert "test ut" in captured.err


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
