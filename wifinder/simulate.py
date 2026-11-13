"""Gera um voo sintético no mesmo formato da coleta, com a posição verdadeira
dos roteadores, para validar a estimativa sem hardware."""

import math

import numpy as np

from . import db
from .geo import to_geo


# Ambientes. Na selva o drone voa logo acima da copa (canopy) e o sinal do
# roteador atravessa a vegetação até sair por cima: perda extra pelo modelo de
# Weissberger (ITU-R P.833) em 2,4 GHz, mais sombreamento forte. Metade dos
# roteadores fica numa clareira (raio clear_r), metade embaixo da mata.
AMBIENTES = {
    "cidade": dict(lat0=-23.5505, lon0=-46.6333, width=400, height=300, lane=40, alt=30,
                   routers=12, canopy=0.0, clear_r=0.0, expo=(2.2, 3.0), shadow=4.0,
                   noise=2.0, limiar=-88),
    "selva": dict(lat0=-2.6100, lon0=-60.2300, width=500, height=300, lane=25, alt=45,
                  routers=5, canopy=35.0, clear_r=15.0, expo=(2.0, 2.4), shadow=6.0,
                  noise=3.0, limiar=-90),
}


def perda_vegetacao(d_veg, f_ghz=2.4):
    """Atenuação (dB) por d_veg metros de folhagem, modelo de Weissberger."""
    fk = f_ghz ** 0.284
    return np.where(d_veg < 14, 0.45 * fk * d_veg, 1.33 * fk * np.power(d_veg, 0.588))


def run(db_path, ambiente="cidade", speed=5, scan_dt=1.5, routers=None, seed=1,
        esp32_log=None, **sobrescreve):
    """Gera o voo. Com esp32_log, grava a trajetória e as amostras num log no
    formato do firmware (como se o ESP32 tivesse voado) e deixa no banco só a
    tabela truth; o resto entra com `wifinder import`."""
    env = dict(AMBIENTES[ambiente], **sobrescreve)
    if routers is not None:
        env["routers"] = routers
    lat0, lon0, width, height, lane, alt, routers = (
        env[k] for k in ("lat0", "lon0", "width", "height", "lane", "alt", "routers"))
    rng = np.random.default_rng(seed)
    log = open(esp32_log, "w", encoding="utf-8") if esp32_log else None
    if log:
        log.write("# wifinder esp32 /v001.log (simulado)\n")

    # Trajetória em "cortador de grama".
    step = speed * scan_dt
    path = []
    for i, y in enumerate(np.arange(0, height + 1, lane)):
        xs = np.arange(0, width + 1, step)
        path += [(x, y) for x in (xs if i % 2 == 0 else xs[::-1])]
    path = np.array(path)

    rx = rng.uniform(-30, width + 30, routers)
    ry = rng.uniform(-30, height + 30, routers)
    p1m = rng.uniform(-45, -35, routers)    # RSSI a 1 m
    expo = rng.uniform(*env["expo"], routers)  # expoente de perda de percurso
    shadow = np.zeros(routers)              # sombreamento correlacionado no tempo
    # Raio da clareira de cada roteador (0 = embaixo da mata).
    clear = np.where(np.arange(routers) % 2 == 0, env["clear_r"], 0.0) if env["canopy"] else None

    con = db.connect(db_path)
    ground = 700.0
    t = 1_800_000_000.0
    n_samples = 0
    for k, (px, py) in enumerate(path):
        gx, gy = px + rng.normal(0, 2), py + rng.normal(0, 2)  # erro do GPS
        lat, lon = to_geo(gx, gy, lat0, lon0)
        ms = 5000 + int(k * scan_dt * 1000)  # relógio millis() do ESP32
        if log:
            log.write(f"F {ms} {t:.2f} {lat:.7f} {lon:.7f} {ground + alt:.1f} 9 1.00\n")
        else:
            con.execute("INSERT INTO track VALUES (?,?,?,?,?,?)",
                        (t, lat, lon, ground + alt, 9, 1.0))
        shadow = 0.8 * shadow + 0.6 * rng.normal(0, env["shadow"], routers)
        horiz = np.hypot(rx - px, ry - py)
        d = np.sqrt(horiz ** 2 + alt ** 2)
        rssi = p1m - 10 * expo * np.log10(d) + shadow + rng.normal(0, env["noise"], routers)
        if clear is not None:
            # Trecho da reta roteador->drone que passa dentro da folhagem: abaixo
            # da copa e fora da clareira.
            frac = np.clip(env["canopy"] / alt - clear / np.maximum(horiz, 1e-6), 0, 1)
            rssi -= perda_vegetacao(d * frac)
        rssi = np.round(rssi)
        for i in np.flatnonzero(rssi >= env["limiar"]):
            if log:
                # Rede ouvida 0,4 s depois do fix, como na varredura canal a canal.
                log.write(f"S {ms + 400} {_bssid(i).upper()} 6 {int(rssi[i])} "
                          f"{f'sim-{i:02d}'.encode().hex()}\n")
            else:
                con.execute(
                    "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)",
                    (t, lat, lon, ground + alt, _bssid(i), f"sim-{i:02d}", 2437, float(rssi[i])),
                )
            n_samples += 1
        t += scan_dt

    for i in range(routers):
        lat, lon = to_geo(rx[i], ry[i], lat0, lon0)
        con.execute("INSERT OR REPLACE INTO truth VALUES (?,?,?)", (_bssid(i), lat, lon))
    con.commit()
    con.close()
    if log:
        log.close()
    minutes = math.ceil(len(path) * scan_dt / 60)
    where = f"log {esp32_log} (importe com: wifinder import {db_path} {esp32_log})" if log else db_path
    print(f"Simulação ({ambiente}) gravada em {where}: {routers} roteadores, "
          f"{n_samples} amostras, voo de {minutes} min, {width}x{height} m, "
          f"faixas de {lane} m a {alt} m de altura.")


def _bssid(i):
    return f"02:00:00:00:00:{i:02x}"
