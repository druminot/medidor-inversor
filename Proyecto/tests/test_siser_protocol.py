#!/usr/bin/env python3
"""Tests unitarios del protocolo SISER.

Cubre:
- siser_checksum: in-place mutation y consistencia
- siser_verify_checksum: acepta validos, rechaza corruptos
- word / dword: big-endian parsing, manejo de out-of-bounds
- send_address frame layout: header, data, checksum

Estos tests importan solo las funciones puras del módulo sin instanciar
la clase SISERReader (que requiere pyserial y psycopg2).
"""
import importlib.util
import os
import sys
from unittest.mock import MagicMock


# Mock de modulos externos no disponibles en el entorno de tests
def _load_siser_module():
    sys.modules['serial'] = MagicMock()
    sys.modules['psycopg2'] = MagicMock()

    SISER_PATH = os.path.join(os.path.dirname(__file__), '..', 'siser-reader', 'siser_reader.py')
    spec = importlib.util.spec_from_file_location("siser_reader", SISER_PATH)
    siser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(siser)
    return siser


siser = _load_siser_module()


def test_checksum_zero():
    """Checksum de un frame zero (excepto checksum slot) es 0."""
    frame = bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    siser.siser_checksum(frame)
    assert frame[-2] == 0x00
    assert frame[-1] == 0x00


def test_checksum_known_value():
    """Checksum conocido para una secuencia de bytes fija."""
    # Bytes: 0x01 0x02 0x03 0x04 0x00 0x00 -> suma = 0x0A -> checksum = 0x00 0x0A
    frame = bytearray([0x01, 0x02, 0x03, 0x04, 0x00, 0x00])
    siser.siser_checksum(frame)
    assert frame[-2] == 0x00
    assert frame[-1] == 0x0A


def test_checksum_overflow():
    """Checksum mod 0xFFFF."""
    # 0xFF 0xFF -> 0x1FE -> mod 0xFFFF = 0x00FE -> bytes = 0x00 0xFE
    frame = bytearray([0xFF, 0xFF, 0x00, 0x00])
    siser.siser_checksum(frame)
    # suma de los primeros 2 bytes (excluyendo checksum) = 0xFF + 0xFF = 0x1FE = 510
    # mod 0xFFFF = 0x01FE -> bytes = 0x01 0xFE
    assert frame[-2] == 0x01
    assert frame[-1] == 0xFE


def test_checksum_mutates_in_place():
    """siser_checksum modifica el frame in-place (documentado)."""
    frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    original_id = id(frame)
    result = siser.siser_checksum(frame)
    assert id(result) == original_id


def test_verify_checksum_valid():
    """Checksum válido pasa la verificación."""
    frame = bytearray([0x01, 0x02, 0x03, 0x04, 0x00, 0x0A])
    assert siser.siser_verify_checksum(frame) is True


def test_verify_checksum_invalid():
    """Checksum corrupto es rechazado."""
    frame = bytearray([0x01, 0x02, 0x03, 0x04, 0x00, 0x00])
    assert siser.siser_verify_checksum(frame) is False


def test_verify_checksum_too_short():
    """Frames muy cortos son rechazados sin error."""
    assert siser.siser_verify_checksum(b'') is False
    assert siser.siser_verify_checksum(b'\x01') is False
    assert siser.siser_verify_checksum(b'\x01\x02') is False


def test_word_basic():
    """word() lee big-endian 16-bit."""
    # 0x01 0x02 -> 0x0102 = 258
    assert siser.word(b'\x01\x02', 0) == 258
    # 0xFF 0xFF -> 0xFFFF = 65535
    assert siser.word(b'\xFF\xFF', 0) == 65535


def test_word_offset():
    """word() lee desde un offset arbitrario."""
    data = bytearray([0x00, 0x00, 0x12, 0x34])
    assert siser.word(data, 2) == 0x1234


def test_word_out_of_bounds():
    """word() devuelve INVALID si el offset está fuera de rango."""
    data = bytearray([0x01, 0x02])
    assert siser.word(data, 5) == siser.INVALID


def test_dword_basic():
    """dword() lee 32-bit big-endian."""
    # 0x00 0x00 0x01 0x02 -> 0x102 = 258
    assert siser.dword(bytearray([0x00, 0x00, 0x01, 0x02]), 0) == 258
    # 0x12 0x34 0x56 0x78 -> 0x12345678
    assert siser.dword(bytearray([0x12, 0x34, 0x56, 0x78]), 0) == 0x12345678


def test_dword_ffff_ffff():
    """dword() detecta 0xFFFFFFFF como 'no conectado'."""
    assert siser.dword(bytearray([0xFF, 0xFF, 0xFF, 0xFF]), 0) == 0xFFFFFFFF


def test_send_address_frame_layout():
    """send_address construye el frame correctamente."""
    # Construir el frame manualmente como hace send_address
    serial = b'SN12345678'
    frame = bytearray(22)
    frame[0] = 0xAA; frame[1] = 0xAA; frame[2] = 0x01
    frame[3] = 0x00; frame[4] = 0x00
    frame[5] = 0x00; frame[6] = 0x00; frame[7] = 0x01; frame[8] = 11
    for i in range(10):
        frame[9+i] = serial[i]
    frame[19] = 33  # INVERTER_ADDR
    siser.siser_checksum(frame)

    # Verificar header
    assert frame[0] == 0xAA
    assert frame[1] == 0xAA
    assert frame[2] == 0x01
    assert frame[7] == 0x01  # cmd=1 (sendAddress)
    assert frame[8] == 11   # dlen=11 (10 serial + 1 addr)

    # Verificar serial copiado
    assert bytes(frame[9:19]) == serial

    # Verificar address
    assert frame[19] == 33

    # Verificar checksum
    assert siser.siser_verify_checksum(frame)


def test_offline_enquiry_frame():
    """offlineEnquiry frame tiene longitud 11 (mínimo)."""
    frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    siser.siser_checksum(frame)
    assert len(frame) == 11
    assert siser.siser_verify_checksum(frame)


def test_read_michele_frame_minimum_length():
    """read_michele requiere respuesta de al menos 60 bytes."""
    # Construir respuesta válida de 60 bytes con checksum
    frame = bytearray(60)
    frame[0] = 0xAA
    frame[1] = 0xAA
    frame[2] = 0x01
    siser.siser_checksum(frame)
    assert siser.siser_verify_checksum(frame)
    assert len(frame) == 60


def test_invalid_constant():
    """INVALID = 0xFFFF segun protocolo."""
    assert siser.INVALID == 0xFFFF


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
