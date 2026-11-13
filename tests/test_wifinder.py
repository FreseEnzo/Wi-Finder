import statistics

from wifinder import db, estimate, map as map_, simulate
from wifinder.gps import Fix, NmeaParser, interpolate
from wifinder.scan import parse_iw_scan

IW_OUTPUT = """BSS aa:bb:cc:dd:ee:01(on wlan0) -- associated
\tlast seen: 1234.567s [boottime]
\tTSF: 0 usec (0d, 00:00:00)
\tfreq: 2437
\tsignal: -45.00 dBm
\tlast seen: 120 ms ago
\tSSID: Minha Rede
\tExtended capabilities:
\t\t * SSID List
BSS aa:bb:cc:dd:ee:02(on wlan0)
\tfreq: 5180.0
\tsignal: -71.00 dBm
\tlast seen: 3400 ms ago
\tSSID:
BSS aa:bb:cc:dd:ee:03(on wlan0)
\tfreq: 2412
"""


def test_parse_iw_scan():
    aps = parse_iw_scan(IW_OUTPUT)
    assert len(aps) == 2  # o terceiro bloco está incompleto
    assert aps[0] == ("aa:bb:cc:dd:ee:01", "Minha Rede", 2437, -45.0, 120)
    assert aps[1] == ("aa:bb:cc:dd:ee:02", "", 5180, -71.0, 3400)


def test_nmea():
    p = NmeaParser()
    gga = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    assert p.feed(gga) is None  # ainda sem data
    assert p.feed("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A") is None
    fix = p.feed(gga, mono=5.0)
    assert abs(fix.lat - 48.1173) < 1e-4 and abs(fix.lon - 11.516667) < 1e-4
    assert fix.alt == 545.4 and fix.sats == 8 and fix.mono == 5.0
    assert p.feed(gga.replace("*47", "*48")) is None  # checksum errado
    assert p.feed("$GPGGA,123519,,,,,0,00,,,M,,M,,*66") is None  # sem fix


def test_interpolate():
    fixes = [Fix(10, 100, 1.0, 2.0, 30, 8, 1), Fix(11, 101, 1.2, 2.4, 32, 8, 1)]
    t, lat, lon, alt = interpolate(fixes, 10.5)
    assert (t, alt) == (100.5, 31) and abs(lat - 1.1) < 1e-9 and abs(lon - 2.2) < 1e-9
    assert interpolate(fixes, 11.5)[:2] == (101.5, 1.2)  # depois do último: mantém posição
    assert interpolate(fixes, 20) is None
    assert interpolate([], 1) is None


def test_simulated_flight(tmp_path):
    path = tmp_path / "sim.db"
    simulate.run(path)
    con = db.connect(path)
    routers, track, _ = estimate.estimate(con)
    assert len(routers) == 12 and track
    errors = [r["error"] for r in routers]
    assert statistics.median(errors) < 25
    assert sum(r["error"] <= r["radius"] for r in routers) >= 10  # o raio provável cobre quase todos

    out = tmp_path / "mapa.html"
    routers[0]["ssid"] = "</script><script>alert(1)</script>"
    map_.write(out, routers, track, title="</script>x")
    assert "</script><script>alert" not in out.read_text()
    assert "</script>x" not in out.read_text()


ESP32_LOG = """# wifinder esp32 /v007.log
F 1000 1800000000.00 -23.5505000 -46.6333000 730.0 8 1.20
F 2000 1800000001.00 -23.5504000 -46.6333000 731.0 8 1.20
S 1500 AA:BB:CC:DD:EE:01 6 -55 4d696e686120526564652c2031
S 1500 AA:BB:CC:DD:EE:02 14 -80
S 2200 AA:BB:CC:DD:EE:01 6 -57 4d696e686120526564652c2031
S 9000 AA:BB:CC:DD:EE:01 6 -60 4d696e686120526564652c2031
lixo
S x y
"""


def test_esp32_import(tmp_path):
    from wifinder import esp32

    fixes, samples = esp32.parse_log(ESP32_LOG)
    assert len(fixes) == 2 and len(samples) == 4
    assert samples[0][4] == "Minha Rede, 1" and samples[1][4] == ""

    con = db.connect(tmp_path / "e.db")
    assert esp32.import_log(con, ESP32_LOG, "/v007.log") == (2, 3, 1)  # a de 9000 ms fica sem fix
    assert esp32.import_log(con, ESP32_LOG, "/v007.log") is None  # não importa de novo
    assert con.execute("SELECT count(*) FROM track").fetchone()[0] == 2
    rows = con.execute("SELECT t, lat, alt, bssid, ssid, freq, rssi FROM samples ORDER BY t").fetchall()
    assert len(rows) == 3
    t, lat, alt, bssid, ssid, freq, rssi = rows[0]
    assert t == 1800000000.5 and abs(lat + 23.55045) < 1e-9 and alt == 730.5
    assert bssid == "aa:bb:cc:dd:ee:01" and ssid == "Minha Rede, 1" and freq == 2437 and rssi == -55
    assert rows[1][5] == 2484  # canal 14
    assert rows[2][0] == 1800000001.2  # depois do último fix: mantém a posição, avança o tempo


class FakeSerial:
    """Imita o firmware do outro lado da USB."""

    def __init__(self):
        self.out = b""
        self.files = {"/v001.log": b"F 1 2 3 4 5 6 7\n", "/v002.log": b"S 1 aa 6 -50\n--- END fake ---\n"}

    def reset_input_buffer(self):
        self.out = b""

    def write(self, data):
        cmd = data.decode().strip().split(" ", 1)
        self.out += b"# status ignorado\n"
        if cmd[0] == "ls":
            self.out += b"--- LS ---\n" + b"".join(
                f"{n} {len(c)}\n".encode() for n, c in self.files.items()) + b"--- END LS ---\n"
        elif cmd[0] == "dump":
            c = self.files.get(cmd[1])
            self.out += (f"--- BEGIN {cmd[1]} {len(c)} ---\n".encode() + c + f"--- END {cmd[1]} ---\n".encode()
                         if c else b"err: arquivo nao existe\n")
        elif cmd[0] == "rm":
            self.out += b"ok\n" if self.files.pop(cmd[1], None) is not None else b"err\n"
        elif cmd[0] == "done":
            self.done = int(cmd[1])
            self.out += b"ok\n"

    def readline(self):
        i = self.out.find(b"\n") + 1
        line, self.out = self.out[:i], self.out[i:]
        return line

    def read(self, n):
        data, self.out = self.out[:n], self.out[n:]
        return data

    def close(self):
        pass


def test_esp32_pull(tmp_path, monkeypatch):
    from wifinder import esp32

    fake = FakeSerial()
    real = esp32.Board
    monkeypatch.setattr(esp32, "Board", lambda port, baud=115200: _board(real, fake))
    con = db.connect(tmp_path / "p.db")
    msgs = []
    esp32.pull(con, "/dev/fake", tmp_path / "logs", remove=True, log=lambda *a, **k: msgs.append(a[0]))
    assert (tmp_path / "logs" / "v001.log").read_bytes() == b"F 1 2 3 4 5 6 7\n"
    assert (tmp_path / "logs" / "v002.log").read_bytes().endswith(b"--- END fake ---\n")  # conteúdo bruto
    assert fake.files == {} and fake.done == 2
    assert con.execute("SELECT count(*) FROM imports").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM track").fetchone()[0] == 1


def _board(cls, fake):
    b = cls.__new__(cls)
    b.ser = fake
    return b


def test_esp32_end_to_end(tmp_path):
    """Voo simulado -> log no formato do firmware -> import -> estimativa -> mapa."""
    from wifinder import esp32

    log, path = tmp_path / "v001.log", tmp_path / "voo.db"
    simulate.run(path, esp32_log=log)
    con = db.connect(path)
    assert con.execute("SELECT count(*) FROM samples").fetchone()[0] == 0  # só truth
    fixes, saved, dropped = esp32.import_log(con, log.read_text(), log.name)
    assert fixes > 100 and saved > 500 and dropped == 0
    routers, track, _ = estimate.estimate(con)
    assert len(routers) == 12 and len(track) == fixes
    assert all(r["error"] is not None for r in routers)
    assert routers[0]["ssid"].startswith("sim-") and routers[0]["bssid"].startswith("02:00")
    map_.write(tmp_path / "mapa.html", routers, track)
    assert (tmp_path / "mapa.html").stat().st_size > 1000


def test_report(tmp_path):
    from wifinder import report

    path = tmp_path / "sim.db"
    simulate.run(path, routers=5)
    con = db.connect(path)
    routers, _, _ = estimate.estimate(con)
    track = con.execute("SELECT lat, lon, alt, t FROM track ORDER BY t").fetchall()
    out = tmp_path / "r.pdf"
    pages = report.write(out, routers, track, samples=100, basemap=False)  # sem internet
    assert pages == 3 and out.read_bytes()[:5] == b"%PDF-"
    x, y = report._merc(0, 0, 1)
    assert (x, y) == (256, 256)


def _voo(con, nets, steps=40):
    """Percurso reto de `steps` pontos; nets: {bssid: (ssid, canal, posição x do aparelho, deslocamento em dB)}."""
    from wifinder.geo import to_geo

    for k in range(steps):
        x = 5.0 * k
        lat, lon = to_geo(x, 0.0, -3.08, -60.07)
        con.execute("INSERT INTO track VALUES (?,?,?,?,?,?)", (1000.0 + k, lat, lon, 50.0, 9, 1.0))
        for bssid, (ssid, ch, rx, off) in nets.items():
            rssi = round(-45 - 25 * __import__("math").log10(max(abs(x - rx), 3.0)) + off)
            if rssi >= -92:
                con.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)",
                            (1000.0 + k, lat, lon, 50.0, bssid, ssid, 2407 + 5 * ch, rssi))
    con.commit()


def test_groups_networks_of_same_device(tmp_path):
    con = db.connect(tmp_path / "g.db")
    _voo(con, {
        "5a:6a:39:28:3b:52": ("Casa", 1, 60, 0),     # o mesmo rádio anuncia três redes
        "5a:6a:39:48:3b:52": ("", 1, 60, -1),
        "5a:6a:39:68:3b:52": ("Casa-Visitas", 1, 60, 1),
        "d8:9a:0d:ab:73:bd": ("Vizinho", 1, 60, 0),  # outro aparelho no mesmo lugar e canal
        "5a:6a:39:28:3b:53": ("Lote", 1, 150, 0),    # número de série vizinho, em outro lugar
    })
    routers, _, _ = estimate.estimate(con)
    by = {r["bssid"]: r for r in routers}
    assert len(routers) == 3
    casa = by["5a:6a:39:68:3b:52"]  # a rede com nome e sinal mais forte dá nome ao aparelho
    assert casa["ssid"] == "Casa-Visitas" and len(casa["nets"]) == 3
    assert len(by["d8:9a:0d:ab:73:bd"]["nets"]) == 1 and len(by["5a:6a:39:28:3b:53"]["nets"]) == 1


def test_standing_still_does_not_pull_estimate(tmp_path):
    from wifinder.geo import to_local

    con = db.connect(tmp_path / "p.db")
    _voo(con, {"aa:bb:cc:00:00:01": ("Alvo", 6, 100, 0)})
    # Dez minutos parado no começo do percurso, longe do aparelho.
    lat, lon = con.execute("SELECT lat, lon FROM track ORDER BY t LIMIT 1").fetchone()
    for k in range(600):
        con.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)",
                    (900.0 + k, lat, lon, 50.0, "aa:bb:cc:00:00:01", "Alvo", 2437, -88))
    con.commit()
    (r,), _, _ = estimate.estimate(con)
    x, _ = to_local(r["lat"], r["lon"], -3.08, -60.07)
    assert abs(x - 100) < 15 and r["status"] == "boa"


def test_library(tmp_path):
    from wifinder.library import Library

    lib = Library(tmp_path / "voos")
    log = tmp_path / "v020.log"
    simulate.run(tmp_path / "x.db", routers=4, esp32_log=log)
    data = log.read_bytes()
    assert lib.add_log("/v005.log", b"# wifinder esp32 /v005.log\n") == (None, "vazio")
    fid, status = lib.add_log("/v020.log", data[:len(data) // 2])
    assert status == "novo" and fid.endswith("_v020") and fid.startswith("2027-01-15")
    assert lib.add_log("/v020.log", data) == (fid, "atualizado")  # o mesmo voo, baixado de novo mais comprido
    assert lib.add_log("/v020.log", data) == (fid, "igual")
    other, status = lib.add_log("/v020.log", data.replace(b" -6", b" -7"))  # mesmo nome e hora, outro conteúdo
    assert status == "novo" and other == fid + "-2"
    nogps, _ = lib.add_log("../../v021.log", b"S 1500 AA:BB:CC:DD:EE:01 6 -55 41\n")
    assert nogps == "sem-gps_v021" and (tmp_path / "voos" / "sem-gps_v021.log").exists()

    flights = {f["id"]: f for f in lib.flights()}
    assert set(flights) == {fid, other, nogps}
    f = flights[fid]
    assert f["title"] == "Voo 20" and f["devices"] == 4 and f["fixes"] > 100 and f["distance"] > 1000 and f["preview"]
    assert flights[nogps]["devices"] is None and flights[nogps]["nets"] == 1
    lib.rename(fid, "  Sobrevoo da vila ")
    assert {x["id"]: x["title"] for x in lib.flights()}[fid] == "Sobrevoo da vila"

    routers, track, summary = lib.load([fid, other])  # dois voos juntos
    assert summary["aparelhos"] == 4 and len(track) == 2 * f["fixes"]
    lib.delete(other)
    assert other not in lib.ids()
    try:
        lib.path("../x")
        assert False
    except KeyError:
        pass


def test_app_http(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from wifinder import app as app_, esp32

    log = tmp_path / "v001.log"
    simulate.run(tmp_path / "x.db", routers=3, esp32_log=log)
    fake = FakeSerial()
    fake.files = {"/v001.log": log.read_bytes(), "/v002.log": b"# wifinder esp32 /v002.log\n"}
    real = esp32.Board
    monkeypatch.setattr(esp32, "Board", lambda port, baud=115200: _board(real, fake))
    monkeypatch.setattr(app_, "find_port", lambda: ("/dev/fake", "placa de teste"))

    a = app_.App(tmp_path / "voos")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (app_.Handler,), {"app": a}))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, data=None, headers=None):
        req = urllib.request.Request(base + path, data=data, headers=headers or {})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()

    try:
        assert b"Baixar voos da placa" in call("/")
        state = json.loads(call("/api/state"))
        assert state["device"]["port"] == "/dev/fake" and state["flights"] == []
        try:
            call("/api/pull", b"")  # sem o cabeçalho próprio é recusado
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 403
        assert json.loads(call("/api/pull", b"", {"X-WiFinder": "1"}))["error"] is None
        for _ in range(100):
            state = json.loads(call("/api/state"))
            if not state["job"]["running"] and state["job"]["finished"]:
                break
            threading.Event().wait(0.05)
        assert state["job"]["error"] is None
        assert [r["status"] for r in state["job"]["results"]] == ["novo", "vazio"]
        assert fake.done == 2 and len(fake.files) == 2  # nada apagado da placa
        (flight,) = state["flights"]
        assert flight["devices"] == 3
        page = call("/mapa?ids=" + flight["id"]).decode()
        assert "maplibre" in page and '"home": "/"' in page
        try:
            call("/mapa?ids=../../etc/passwd")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
        json.loads(call("/api/delete", json.dumps({"id": flight["id"]}).encode(), {"X-WiFinder": "1"}))
        assert json.loads(call("/api/state"))["flights"] == []
    finally:
        httpd.shutdown()
        httpd.server_close()
