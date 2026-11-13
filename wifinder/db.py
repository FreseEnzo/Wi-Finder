"""Banco SQLite compartilhado pela coleta, pelo simulador e pela estimativa.

Tempos (coluna t) são segundos Unix em UTC, vindos do GPS.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS track (
    t REAL, lat REAL, lon REAL, alt REAL, sats INTEGER, hdop REAL
);
CREATE TABLE IF NOT EXISTS samples (
    t REAL, lat REAL, lon REAL, alt REAL,
    bssid TEXT, ssid TEXT, freq INTEGER, rssi REAL
);
CREATE INDEX IF NOT EXISTS samples_bssid ON samples (bssid);
-- Só o simulador preenche: posição verdadeira, para medir o erro.
CREATE TABLE IF NOT EXISTS truth (bssid TEXT PRIMARY KEY, lat REAL, lon REAL);
-- Logs do ESP32 já importados (evita importar duas vezes).
CREATE TABLE IF NOT EXISTS imports (name TEXT PRIMARY KEY, fixes INTEGER, samples INTEGER);
"""


def connect(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con
