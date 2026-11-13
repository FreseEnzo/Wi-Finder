"""Leitura do GPS NEO-6M: sentenças NMEA pela serial, sem gpsd."""

import calendar
import threading
import time
from bisect import bisect_left
from collections import deque, namedtuple

# mono: time.monotonic() na leitura; t: segundos Unix UTC segundo o GPS.
Fix = namedtuple("Fix", "mono t lat lon alt sats hdop")


def checksum_ok(line):
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, cs = line[1:].partition("*")
    x = 0
    for ch in body:
        x ^= ord(ch)
    try:
        return x == int(cs[:2], 16)
    except ValueError:
        return False


def _deg(value, hemi):
    """Converte ddmm.mmmm (ou dddmm.mmmm) para graus decimais."""
    v = float(value)
    d = int(v // 100)
    deg = d + (v - d * 100) / 60
    return -deg if hemi in ("S", "W") else deg


class NmeaParser:
    """Junta a data do RMC com a posição do GGA e devolve um Fix por GGA válido."""

    def __init__(self):
        self.date = None  # (ano, mês, dia)

    def feed(self, line, mono=0.0):
        line = line.strip()
        if not checksum_ok(line):
            return None
        f = line[1:].partition("*")[0].split(",")
        kind = f[0][2:]
        try:
            if kind == "RMC" and len(f) > 9 and f[2] == "A" and len(f[9]) == 6:
                d = f[9]
                self.date = (2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
            elif kind == "GGA" and len(f) > 9 and f[6] not in ("", "0") and self.date:
                hms = f[1]
                secs = float(hms[4:])
                t = calendar.timegm(
                    (*self.date, int(hms[0:2]), int(hms[2:4]), 0)
                ) + secs
                return Fix(
                    mono, t, _deg(f[2], f[3]), _deg(f[4], f[5]), float(f[9]),
                    int(f[7] or 0), float(f[8] or 0),
                )
        except (ValueError, IndexError):
            pass
        return None


def interpolate(fixes, mono, max_gap=2.0):
    """Posição no instante `mono`, interpolada entre os fixes vizinhos.

    Retorna (t, lat, lon, alt), ou None se o fix mais próximo estiver a mais de
    `max_gap` segundos.
    """
    if not fixes:
        return None
    i = bisect_left([f.mono for f in fixes], mono)
    if i == 0:
        a = b = fixes[0]
    elif i == len(fixes):
        a = b = fixes[-1]
    else:
        a, b = fixes[i - 1], fixes[i]
    if min(abs(mono - a.mono), abs(mono - b.mono)) > max_gap:
        return None
    if b.mono == a.mono:
        return (a.t + (mono - a.mono), a.lat, a.lon, a.alt)
    k = (mono - a.mono) / (b.mono - a.mono)
    return tuple(p + k * (q - p) for p, q in zip(a[1:5], b[1:5]))


class GpsReader(threading.Thread):
    """Lê a serial em segundo plano e guarda o histórico recente de fixes."""

    def __init__(self, port, baud=9600):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self._lock = threading.Lock()
        self._fixes = deque(maxlen=900)
        self._new = []

    def run(self):
        import serial  # pyserial; só é necessário na Raspberry Pi

        parser = NmeaParser()
        while True:
            try:
                with serial.Serial(self.port, self.baud, timeout=2) as ser:
                    while True:
                        raw = ser.readline()
                        fix = parser.feed(
                            raw.decode("ascii", errors="ignore"), time.monotonic()
                        )
                        if fix:
                            with self._lock:
                                self._fixes.append(fix)
                                self._new.append(fix)
            except (serial.SerialException, OSError) as e:
                print(f"GPS: erro na serial {self.port}: {e}; tentando de novo")
                time.sleep(2)

    def new_fixes(self):
        """Fixes recebidos desde a última chamada."""
        with self._lock:
            out, self._new = self._new, []
        return out

    def position_at(self, mono):
        with self._lock:
            fixes = list(self._fixes)
        return interpolate(fixes, mono)
