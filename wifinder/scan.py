"""Varredura WiFi com `iw scan` (precisa de root)."""

import re
import subprocess
from collections import namedtuple

Ap = namedtuple("Ap", "bssid ssid freq rssi last_seen_ms")

FREQS_24 = [2412 + 5 * i for i in range(13)]  # canais 1 a 13

_BSS = re.compile(r"^BSS ([0-9a-f:]{17})", re.M)
_FREQ = re.compile(r"^\tfreq: (\d+)", re.M)
_SIGNAL = re.compile(r"^\tsignal: (-?[\d.]+) dBm", re.M)
_SEEN = re.compile(r"^\tlast seen: (\d+) ms ago", re.M)
_SSID = re.compile(r"^\tSSID: (.*)$", re.M)


def parse_iw_scan(text):
    aps = []
    starts = [m.start() for m in _BSS.finditer(text)]
    for begin, end in zip(starts, starts[1:] + [len(text)]):
        block = text[begin:end]
        freq, signal, seen = _FREQ.search(block), _SIGNAL.search(block), _SEEN.search(block)
        if not (freq and signal and seen):
            continue
        ssid = _SSID.search(block)
        aps.append(Ap(
            _BSS.match(block).group(1),
            ssid.group(1).strip() if ssid else "",
            int(freq.group(1)),
            float(signal.group(1)),
            int(seen.group(1)),
        ))
    return aps


def scan(iface, freqs=None):
    """Faz uma varredura. Retorna (lista de Ap, None) ou (None, mensagem de erro)."""
    cmd = ["iw", "dev", iface, "scan"]
    if freqs:
        cmd += ["freq", *map(str, freqs)]
    cmd.append("flush")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if p.returncode != 0:
        return None, p.stderr.strip() or f"iw saiu com código {p.returncode}"
    return parse_iw_scan(p.stdout), None
