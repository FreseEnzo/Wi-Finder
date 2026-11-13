"""Coleta em voo: roda na Raspberry Pi e grava GPS + RSSI no SQLite."""

import signal
import time

from . import db
from .gps import GpsReader
from .scan import FREQS_24, scan


def run(db_path, iface="wlan0", port="/dev/serial0", baud=9600, band="2.4"):
    con = db.connect(db_path)
    gps = GpsReader(port, baud)
    gps.start()
    freqs = FREQS_24 if band == "2.4" else None

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    print(f"Coletando em {db_path} (interface {iface}, GPS {port}). Ctrl+C para parar.")
    total = 0
    try:
        while True:
            t0 = time.monotonic()
            aps, err = scan(iface, freqs)
            t1 = time.monotonic()

            fixes = gps.new_fixes()
            con.executemany(
                "INSERT INTO track VALUES (?,?,?,?,?,?)",
                [(f.t, f.lat, f.lon, f.alt, f.sats, f.hdop) for f in fixes],
            )

            if err:
                print(f"WiFi: {err}")
                con.commit()
                time.sleep(1)
                continue

            saved = 0
            for ap in aps:
                # O kernel devolve também resultados antigos em cache; só vale
                # o que foi ouvido durante esta varredura.
                if ap.last_seen_ms > (t1 - t0) * 1000 + 200:
                    continue
                # Posição do drone no instante em que o beacon foi ouvido.
                pos = gps.position_at(t1 - ap.last_seen_ms / 1000)
                if pos is None:
                    continue
                con.execute(
                    "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)",
                    (*pos, ap.bssid, ap.ssid, ap.freq, ap.rssi),
                )
                saved += 1
            con.commit()
            total += saved

            last = fixes[-1] if fixes else None
            gps_txt = f"{last.sats} sat, hdop {last.hdop}" if last else "SEM FIX"
            print(f"GPS: {gps_txt} | APs ouvidos: {len(aps)} | gravados: {saved} | total: {total}")
            if t1 - t0 < 0.2:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        con.commit()
        con.close()
        print(f"Encerrado. {total} amostras gravadas.")
