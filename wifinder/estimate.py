"""Estima a posição de cada aparelho (roteador) a partir das amostras (posição, RSSI).

Método: centroide ponderado pelo sinal, só com os pontos onde a rede foi ouvida
mais forte. Antes disso as amostras são agrupadas em células de alguns metros,
para que ficar parado num lugar não puxe a estimativa para lá. Nas simulações
com posição verdadeira ele erra cerca de metade do que o ajuste de perda de
percurso usado até a versão 1.6 (mediana ~20 m contra ~40 m na cidade).

Redes do mesmo aparelho (um roteador que anuncia a rede principal, a de
visitantes, a da operadora...) são juntadas num só item: têm endereços quase
iguais, o mesmo canal e chegam com o mesmo sinal.
"""

import numpy as np

from .geo import to_geo, to_local

CELL = 8.0        # lado da célula de agrupamento, em metros
TOP_DB = 10.0     # só entram células até TOP_DB abaixo da mais forte
MAX_HDOP = 3.0    # fixes piores que isso (GPS ainda se acertando) são ignorados
MIN_SATS = 4
MAX_PTS = 400     # limite de amostras por aparelho mandadas para o mapa
MAX_GAP = 30.0    # segundos sem fix: dali em diante é outro trecho (ou outro voo)

BOA, MEDIA, FRACA = "boa", "média", "fraca"


# ------------------------------------------------------------- posição

def _cells(x, y, rssi, cell=CELL):
    """Agrupa as amostras em células: (x médio, y médio, RSSI médio)."""
    key = np.round(x / cell).astype(np.int64) * 1_000_003 + np.round(y / cell).astype(np.int64)
    _, inv = np.unique(key, return_inverse=True)
    n = np.bincount(inv)
    return np.bincount(inv, x) / n, np.bincount(inv, y) / n, np.bincount(inv, rssi) / n


def locate(x, y, rssi):
    """Posição de um aparelho. x, y em metros, rssi em dBm.

    Retorna dict com x, y, radius (raio provável em metros), spots (número de
    lugares distintos onde foi ouvido) e status: "boa", "média" ou "fraca".
    """
    cx, cy, cr = _cells(np.asarray(x, float), np.asarray(y, float), np.asarray(rssi, float))
    top = cr >= cr.max() - TOP_DB
    w = 10 ** (cr[top] / 10)
    px = float((w * cx[top]).sum() / w.sum())
    py = float((w * cy[top]).sum() / w.sum())

    # Raio provável: espalhamento dos pontos fortes + alcance sugerido pelo
    # sinal (sinal fraco = aparelho mais longe do caminho percorrido).
    spread = float(np.sqrt((w * ((cx[top] - px) ** 2 + (cy[top] - py) ** 2)).sum() / w.sum()))
    reach = 10 ** ((-50.0 - float(np.max(rssi))) / 30.0)
    radius = 20.0 + spread + reach

    spots = int(len(cx))
    if spots >= 8 and np.max(rssi) >= -80:
        status = BOA
    elif spots >= 3:
        status = MEDIA
    else:
        status = FRACA
    return dict(x=px, y=py, radius=radius, spots=spots, status=status)


# ---------------------------------------------------- redes do mesmo aparelho

def _same_device(a, b):
    """Dois BSSIDs que parecem ser o mesmo rádio anunciando várias redes."""
    if a["freq"] != b["freq"]:
        return False
    ma, mb = a["mac"], b["mac"]
    if ma == mb or ma[1] != mb[1] or ma[2] != mb[2] or ma[4] != mb[4]:
        return False
    if abs(ma[5] - mb[5]) > 3:
        return False
    # Só o último byte diferente é o padrão de aparelhos distintos do mesmo
    # lote (números de série vizinhos), não de redes do mesmo rádio.
    if ma[0] == mb[0] and ma[3] == mb[3]:
        return False
    common = a["by_t"].keys() & b["by_t"].keys()
    if not common:
        # Nunca ouvidos na mesma varredura: só junta se o final for idêntico.
        return ma[5] == mb[5]
    # Mesmo rádio: aparecem juntos na maioria das varreduras e com o mesmo sinal.
    if len(common) < 0.5 * min(len(a["by_t"]), len(b["by_t"])):
        return False
    diff = np.median([abs(a["by_t"][t] - b["by_t"][t]) for t in common])
    return diff <= 3.0


def _group(nets):
    """Junta as redes em aparelhos (união de pares parecidos)."""
    parent = list(range(len(nets)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(nets)):
        for j in range(i + 1, len(nets)):
            if _same_device(nets[i], nets[j]):
                parent[find(j)] = find(i)
    groups = {}
    for i, n in enumerate(nets):
        groups.setdefault(find(i), []).append(n)
    return list(groups.values())


def _mac(bssid):
    try:
        m = [int(p, 16) for p in bssid.split(":")]
    except ValueError:
        m = []
    return m if len(m) == 6 else [0, 0, 0, 0, 0, -99]


def channel_of(freq):
    if freq == 2484:
        return 14
    return int((freq - 2407) // 5) if freq < 3000 else int((freq - 5000) // 5)


# ------------------------------------------------------------------ voo

def load_track(con):
    """Trajetória [(lat, lon, alt, t)] sem os fixes ruins do começo (GPS ainda
    se acertando), que desenhariam um risco para longe do percurso real."""
    rows = con.execute("SELECT lat, lon, alt, t, sats, hdop FROM track ORDER BY t").fetchall()
    good = [r[:4] for r in rows
            if not ((r[5] is not None and r[5] > MAX_HDOP) or (r[4] is not None and r[4] < MIN_SATS))]
    return good or [r[:4] for r in rows]


def estimate(con, ground_alt=None, min_samples=None):
    """Lê as amostras do banco e devolve (aparelhos, trajetória, origem).

    Cada aparelho é um dict com ssid, bssid (da rede principal), nets (todas
    as redes dele), lat, lon, radius, status, samples, spots, rssi_max,
    channel e pts (onde foi ouvido). ground_alt e min_samples são aceitos por
    compatibilidade e não mudam a posição.
    """
    rows = con.execute(
        "SELECT bssid, ssid, lat, lon, rssi, freq, t FROM samples ORDER BY bssid, t"
    ).fetchall()
    track_q = con.execute("SELECT lat, lon, alt, t, sats, hdop FROM track ORDER BY t").fetchall()
    track = [p[:3] for p in load_track(con)]
    if not rows:
        return [], track, None

    # Amostras colhidas enquanto o GPS ainda não tinha posição confiável.
    bad = np.array([p[3] for p in track_q
                    if (p[5] is not None and p[5] > MAX_HDOP) or (p[4] is not None and p[4] < MIN_SATS)])
    if len(bad):
        tt = np.array([p[3] for p in track_q])
        st = np.array([r[6] for r in rows])
        near = tt[np.clip(np.searchsorted(tt, st), 1, len(tt) - 1) - 1]
        near2 = tt[np.clip(np.searchsorted(tt, st), 0, len(tt) - 1)]
        nearest = np.where(np.abs(st - near) <= np.abs(st - near2), near, near2)
        keep = ~np.isin(nearest, bad)
        if keep.any():
            rows = [r for r, k in zip(rows, keep) if k]

    lat0 = float(np.mean([r[2] for r in rows]))
    lon0 = float(np.mean([r[3] for r in rows]))
    truth = dict((b, (la, lo)) for b, la, lo in con.execute("SELECT * FROM truth"))

    nets = {}
    for bssid, ssid, lat, lon, rssi, freq, t in rows:
        n = nets.setdefault(bssid, dict(bssid=bssid, ssid="", freq=freq, mac=_mac(bssid), pts=[], by_t={}))
        n["ssid"] = ssid or n["ssid"]
        n["pts"].append((lat, lon, rssi))
        key = round(t, 2)
        n["by_t"][key] = max(rssi, n["by_t"].get(key, -999))

    routers = []
    for group in _group(list(nets.values())):
        for n in group:
            n["rssi_max"] = max(p[2] for p in n["pts"])
        group.sort(key=lambda n: (not n["ssid"], -n["rssi_max"], n["bssid"]))
        main = group[0]

        # Na mesma varredura as redes do aparelho chegam juntas: vale a mais forte.
        best = {}
        for n in group:
            for lat, lon, rssi in n["pts"]:
                k = (lat, lon)
                if k not in best or rssi > best[k]:
                    best[k] = rssi
        lat = np.array([k[0] for k in best])
        lon = np.array([k[1] for k in best])
        rssi = np.array(list(best.values()))
        x, y = to_local(lat, lon, lat0, lon0)
        res = locate(x, y, rssi)
        res["lat"], res["lon"] = to_geo(res.pop("x"), res.pop("y"), lat0, lon0)

        step = max(1, len(rssi) // MAX_PTS)
        res.update(
            bssid=main["bssid"], ssid=main["ssid"], samples=int(len(rssi)),
            rssi_max=float(rssi.max()), channel=channel_of(main["freq"]),
            nets=[dict(bssid=n["bssid"], ssid=n["ssid"], rssi_max=float(n["rssi_max"]),
                       samples=len(n["pts"])) for n in group],
            error=None, truth=None,
            pts=[[round(float(a), 6), round(float(b), 6), float(c)]
                 for a, b, c in list(zip(lat, lon, rssi))[::step]],
        )
        known = next((truth[n["bssid"]] for n in group if n["bssid"] in truth), None)
        if known:
            tx, ty = to_local(*known, lat0, lon0)
            ex, ey = to_local(res["lat"], res["lon"], lat0, lon0)
            res["error"] = float(np.hypot(tx - ex, ty - ey))
            res["truth"] = known
        routers.append(res)
    routers.sort(key=lambda r: (-r["rssi_max"], -r["samples"], r["bssid"]))
    return routers, track, (lat0, lon0)


def flight_summary(track, samples=0, routers=()):
    """Resumo do voo. track: [(lat, lon, alt[, t]), ...]."""
    s = {"fixes": len(track), "amostras": samples, "aparelhos": len(routers),
         "redes": sum(len(r.get("nets", [1])) for r in routers)}
    if track:
        x, y = to_local(np.array([p[0] for p in track]), np.array([p[1] for p in track]),
                        track[0][0], track[0][1])
        d = np.hypot(np.diff(x), np.diff(y))
        same = np.ones(len(d), bool)
        if len(track[0]) > 3:
            t = np.array([p[3] for p in track])
            # Com vários voos juntos, o intervalo entre eles não conta.
            same = (np.diff(t) >= 0) & (np.diff(t) <= MAX_GAP)
            s["inicio"] = float(t.min())
            s["duracao"] = float(np.diff(t)[same].sum())
        # Passos menores que o ruído do GPS parado não contam como percurso.
        s["distancia"] = float(d[same & (d >= 0.5)].sum())
        alts = [p[2] for p in track]
        s["alt_min"], s["alt_max"] = min(alts), max(alts)
    return s
